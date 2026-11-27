import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import io
import os
from pathlib import Path
import re
import time
from typing import Any
import unicodedata
from urllib.parse import urlparse

from app.core.config import settings
from app.core.exceptions import PayloadTooLargeError, UnprocessableEntityError
from app.services.supplier_parsing.file_detection import detect_supplier_file_format
from app.services.supplier_parsing.models import NormalizedRow, ParsedSupplierFile, ParseWarningItem
from app.services.supplier_parsing.readers import extract_raw_rows

DECIMAL_QUANT = Decimal("0.000001")

HEADER_ALIASES: dict[str, str] = {
    "codigo": "code",
    "cod": "code",
    "cod articulo": "code",
    "descripcion": "description",
    "detalle": "description",
    "articulo": "description",
    "empaque": "packaging_raw",
    "presentacion": "packaging_raw",
    "s iva": "price_net",
    "sin iva": "price_net",
    "precio s iva": "price_net",
    "c iva": "price_with_vat",
    "con iva": "price_with_vat",
    "precio c iva": "price_with_vat",
    "utilidad": "supplier_utility_pct",
    "c iva y utilidad paquete": "price_pack_with_utility",
    "unidades por paquete": "units_per_package",
    "uxp": "units_per_package",
    "c iva y utilidad unidad": "price_unit_with_utility",
    "img": "image_source_url",
    "imagen": "image_source_url",
    "foto": "image_source_url",
}

REQUIRED_FIELDS = ("code", "description", "price_net", "price_with_vat")

PACKAGING_ALIASES: dict[str, str] = {
    "UNIDAD": "UNIDAD",
    "1UNIDAD": "UNIDAD",
    "UNIDADES": "UNIDAD",
    "UND": "UNIDAD",
    "PAQUETE": "PAQUETE",
    "PAQUTE": "PAQUETE",
    "PAQUETES": "PAQUETE",
    "PAQ": "PAQUETE",
}

KNOWN_PACKAGINGS: set[str] = {
    "UNIDAD",
    "LIQUIDACION",
    "CAJA",
    "BLISTER",
    "PAQUETE",
    "SOBRE",
    "DOCENA",
    "ESTUCHE",
    "BOLSA",
    "SET",
    "EXHIBIDOR",
    "RELACION",
    "TUBO",
    "ROLLO",
    "POTE",
    "KILOS",
    "TACO",
    "BALDE",
    "SIN_DATO",
}

HTML_TAIL_SPLIT_RE = re.compile(r"['\"<>\s]")
THOUSANDS_ONLY_RE = re.compile(r"^-?\d{1,3}(?:\.\d{3})+$")
MULTI_SPACE_RE = re.compile(r"\s+")
LIQUIDA_TAG_RE = re.compile(r"^(LIQUIDA\d*)")


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_header_token(raw: Any) -> str:
    txt = strip_accents(str(raw or "")).lower()
    txt = re.sub(r"[$%/._\-()]+", " ", txt)
    txt = MULTI_SPACE_RE.sub(" ", txt).strip()
    return txt


def locate_header_mapping(rows: list[list[Any]]) -> tuple[int, dict[str, int]]:
    scan_limit = min(len(rows), 30)
    for idx in range(scan_limit):
        row = rows[idx]
        mapping: dict[str, int] = {}
        for col_idx, cell in enumerate(row):
            token = normalize_header_token(cell)
            field_name = HEADER_ALIASES.get(token)
            if field_name and field_name not in mapping:
                mapping[field_name] = col_idx

        if "code" in mapping and "description" in mapping:
            missing = [req for req in REQUIRED_FIELDS if req not in mapping]
            if missing:
                missing_labels = ", ".join(missing)
                raise UnprocessableEntityError(
                    f"La planilla no contiene las columnas obligatorias requeridas ({missing_labels})."
                )
            return idx, mapping

    raise UnprocessableEntityError(
        "No se encontró la fila de encabezados esperada ('Código', 'Descripción', '$ S/IVA', '$ C/IVA')."
    )


def parse_code_cell(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return ""
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return str(val).strip()
    txt = str(val).strip()
    if re.fullmatch(r"\d+\.0+", txt):
        return txt.split(".", 1)[0]
    return txt


def parse_supplier_decimal(val: Any) -> Decimal | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int):
        return Decimal(val).quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)
    if isinstance(val, float):
        # Paridad exacta entre BIFF8 float64 (ej. 9999999.99999) y exportación CSV
        return Decimal(str(round(val, 6))).quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)

    txt = str(val).strip().replace("$", "").replace(" ", "")
    if txt == "":
        return None

    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif THOUSANDS_ONLY_RE.match(txt):
        txt = txt.replace(".", "")

    try:
        return Decimal(txt).quantize(DECIMAL_QUANT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def normalize_packaging(raw_val: Any) -> tuple[str, str, bool, str | None, bool]:
    raw_str = str(raw_val or "")
    cleaned = MULTI_SPACE_RE.sub(" ", strip_accents(raw_str).upper()).strip()
    if not cleaned:
        return raw_str.strip(), "SIN_DATO", False, None, False

    if cleaned.startswith("LIQUIDA"):
        m = LIQUIDA_TAG_RE.match(cleaned)
        tag = m.group(1) if m else "LIQUIDA"
        return raw_str.strip(), "LIQUIDACION", True, tag, False

    mapped = PACKAGING_ALIASES.get(cleaned, cleaned)
    is_unknown = mapped not in KNOWN_PACKAGINGS
    return raw_str.strip(), mapped, False, None, is_unknown


def sanitize_image_url(raw_val: Any, allowed_hosts: set[str] | None = None) -> str | None:
    if raw_val is None:
        return None
    raw_str = str(raw_val).strip()
    if not raw_str:
        return None

    candidate = HTML_TAIL_SPLIT_RE.split(raw_str, maxsplit=1)[0].strip()
    if not candidate:
        return None

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return None

    hosts = allowed_hosts if allowed_hosts is not None else settings.allowed_image_hosts_set
    if hosts and parsed.hostname and parsed.hostname.lower() not in hosts:
        return None

    return candidate


def clean_description_and_flags(raw_desc: str) -> tuple[str, bool, bool]:
    text = raw_desc.strip()
    star_prefix = text.startswith("*")
    hash_suffix = text.endswith("#")

    cleaned = text
    if star_prefix:
        cleaned = cleaned.lstrip("*").strip()
    if hash_suffix:
        cleaned = cleaned.rstrip("#").strip()
    cleaned = MULTI_SPACE_RE.sub(" ", cleaned)
    return cleaned or text, star_prefix, hash_suffix


def build_search_text(code: str, description_clean: str) -> str:
    norm_desc = MULTI_SPACE_RE.sub(" ", strip_accents(description_clean).upper()).strip()
    return f"{code.upper()} {norm_desc}".strip()


def detect_vat_and_anomaly(price_net: Decimal, price_with_vat: Decimal) -> tuple[Decimal | None, bool]:
    if price_net < 0 or price_with_vat < 0:
        return None, True
    if price_net == 0:
        return (Decimal("0.0000"), False) if price_with_vat == 0 else (None, True)
    if price_with_vat < price_net:
        return None, True

    ratio = price_with_vat / price_net
    for std_rate, expected_ratio in (
        (Decimal("0.21"), Decimal("1.21")),
        (Decimal("0.105"), Decimal("1.105")),
        (Decimal("0.00"), Decimal("1.00")),
    ):
        if abs(ratio - expected_ratio) <= Decimal("0.003"):
            return std_rate, False

    return None, True


def compute_row_fingerprint(
    *,
    code: str,
    description: str,
    packaging_raw: str,
    packaging: str,
    price_net: Decimal,
    price_with_vat: Decimal,
    supplier_utility_pct: Decimal,
    price_pack_with_utility: Decimal,
    units_per_package: int,
    price_unit_with_utility: Decimal,
    image_source_url: str | None,
) -> str:
    # Cuantizamos precios a 2 decimales para paridad total entre .xls y .csv
    q2 = Decimal("0.01")
    payload = "|".join(
        [
            code,
            description,
            packaging_raw,
            packaging,
            str(price_net.quantize(q2, rounding=ROUND_HALF_UP)),
            str(price_with_vat.quantize(q2, rounding=ROUND_HALF_UP)),
            str(supplier_utility_pct.quantize(q2, rounding=ROUND_HALF_UP)),
            str(price_pack_with_utility.quantize(q2, rounding=ROUND_HALF_UP)),
            str(units_per_package),
            str(price_unit_with_utility.quantize(q2, rounding=ROUND_HALF_UP)),
            image_source_url or "",
        ]
    )
    return f"sha1:{hashlib.sha1(payload.encode('utf-8')).hexdigest()}"


def _cell(row: list[Any], idx: int | None) -> Any:
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def parse_and_normalize_supplier_bytes(
    raw_bytes: bytes,
    filename: str | None = None,
    *,
    max_upload_mb: int | None = None,
) -> ParsedSupplierFile:
    limit_mb = max_upload_mb if max_upload_mb is not None else settings.import_max_upload_mb
    if len(raw_bytes) > limit_mb * 1024 * 1024:
        raise PayloadTooLargeError(
            f"El archivo supera el límite máximo permitido de {limit_mb} MB."
        )

    detected_format = detect_supplier_file_format(raw_bytes, filename)
    file_hash = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
    raw_rows = extract_raw_rows(raw_bytes, detected_format)

    header_idx, col_map = locate_header_mapping(raw_rows)

    normalized_by_code: dict[str, NormalizedRow] = {}
    warnings: list[ParseWarningItem] = []
    unknown_packagings: dict[str, int] = {}
    skipped_rows = 0
    invalid_rows = 0
    anomaly_count = 0

    for r_offset, row in enumerate(raw_rows[header_idx + 1 :], start=header_idx + 2):
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            skipped_rows += 1
            continue

        code = parse_code_cell(_cell(row, col_map.get("code")))
        desc_raw = str(_cell(row, col_map.get("description")) or "").strip()
        p_net = parse_supplier_decimal(_cell(row, col_map.get("price_net")))
        p_vat = parse_supplier_decimal(_cell(row, col_map.get("price_with_vat")))

        # Descarte automático de fila basura inicial (código 0 y descripción vacía con precios 0)
        if code in ("", "0") and desc_raw == "" and (p_net in (None, Decimal("0"))) and (p_vat in (None, Decimal("0"))):
            skipped_rows += 1
            continue

        if not code or code == "0" or not re.fullmatch(r"[A-Za-z0-9.\-]{1,24}", code):
            invalid_rows += 1
            if len(warnings) < 100:
                warnings.append(ParseWarningItem(row=r_offset, code=code or "", message="Código inválido o vacío."))
            continue

        if not desc_raw:
            invalid_rows += 1
            if len(warnings) < 100:
                warnings.append(ParseWarningItem(row=r_offset, code=code, message="Descripción vacía."))
            continue

        if p_net is None or p_vat is None or p_net < 0 or p_vat < 0:
            invalid_rows += 1
            if len(warnings) < 100:
                warnings.append(
                    ParseWarningItem(row=r_offset, code=code, message="Importes $ S/IVA o $ C/IVA inválidos.")
                )
            continue

        if code in normalized_by_code:
            if len(warnings) < 100:
                warnings.append(
                    ParseWarningItem(
                        row=r_offset,
                        code=code,
                        message="Código duplicado en el archivo; se conservó la primera aparición.",
                    )
                )
            skipped_rows += 1
            continue

        util_pct = parse_supplier_decimal(_cell(row, col_map.get("supplier_utility_pct")))
        if util_pct is None:
            util_pct = Decimal("0")

        uxp_dec = parse_supplier_decimal(_cell(row, col_map.get("units_per_package")))
        units_per_package = int(uxp_dec) if uxp_dec is not None and uxp_dec >= 1 else 1

        p_pack_util = parse_supplier_decimal(_cell(row, col_map.get("price_pack_with_utility")))
        if p_pack_util is None:
            p_pack_util = (p_vat * (Decimal("1") + util_pct / Decimal("100"))).quantize(
                DECIMAL_QUANT, rounding=ROUND_HALF_UP
            )

        p_unit_util = parse_supplier_decimal(_cell(row, col_map.get("price_unit_with_utility")))
        if p_unit_util is None:
            p_unit_util = (p_pack_util / Decimal(units_per_package)).quantize(
                DECIMAL_QUANT, rounding=ROUND_HALF_UP
            )

        packaging_raw, packaging, is_liq, liq_tag, is_unknown_pkg = normalize_packaging(
            _cell(row, col_map.get("packaging_raw"))
        )
        if is_unknown_pkg:
            unknown_packagings[packaging] = unknown_packagings.get(packaging, 0) + 1

        desc_clean, star_prefix, hash_suffix = clean_description_and_flags(desc_raw)
        search_text = build_search_text(code, desc_clean)
        vat_rate, is_anomaly = detect_vat_and_anomaly(p_net, p_vat)
        if is_anomaly:
            anomaly_count += 1

        img_url = sanitize_image_url(_cell(row, col_map.get("image_source_url")))
        fingerprint = compute_row_fingerprint(
            code=code,
            description=desc_raw,
            packaging_raw=packaging_raw,
            packaging=packaging,
            price_net=p_net,
            price_with_vat=p_vat,
            supplier_utility_pct=util_pct,
            price_pack_with_utility=p_pack_util,
            units_per_package=units_per_package,
            price_unit_with_utility=p_unit_util,
            image_source_url=img_url,
        )

        normalized_by_code[code] = NormalizedRow(
            code=code,
            description=desc_raw,
            description_clean=desc_clean,
            search_text=search_text,
            star_prefix=star_prefix,
            hash_suffix=hash_suffix,
            packaging_raw=packaging_raw,
            packaging=packaging,
            is_liquidation=is_liq,
            liquidation_tag=liq_tag,
            price_net=p_net,
            price_with_vat=p_vat,
            supplier_utility_pct=util_pct,
            price_pack_with_utility=p_pack_util,
            units_per_package=units_per_package,
            price_unit_with_utility=p_unit_util,
            vat_rate_detected=vat_rate,
            price_anomaly=is_anomaly,
            image_source_url=img_url,
            row_fingerprint=fingerprint,
        )

    for pkg_name, pkg_count in unknown_packagings.items():
        if len(warnings) < 100:
            warnings.append(
                ParseWarningItem(
                    row=0,
                    code="",
                    message=f"Empaque nuevo detectado: '{pkg_name}' ({pkg_count} artículos).",
                )
            )

    valid_rows = list(normalized_by_code.values())
    if not valid_rows:
        raise UnprocessableEntityError("El archivo no contiene ningún artículo válido para importar.")

    total_evaluated = len(valid_rows) + invalid_rows
    if total_evaluated >= 20 and (invalid_rows / total_evaluated) > 0.05:
        raise UnprocessableEntityError(
            f"El archivo presenta demasiadas filas con errores ({invalid_rows} inválidas de {total_evaluated}). Revisá el formato."
        )

    sorted_rows = sorted(valid_rows, key=lambda item: item.code)
    canonical_csv = render_canonical_csv(sorted_rows)
    # Hash canónico basado en fingerprints ordenados (idéntico entre .xls y .csv del mismo contenido)
    canonical_hash_input = "\n".join(r.row_fingerprint for r in sorted_rows)
    content_hash = f"sha256:{hashlib.sha256(canonical_hash_input.encode('utf-8')).hexdigest()}"

    return ParsedSupplierFile(
        detected_format=detected_format,
        file_hash=file_hash,
        content_hash=content_hash,
        rows=sorted_rows,
        skipped_rows=skipped_rows,
        invalid_rows=invalid_rows,
        price_anomaly_count=anomaly_count,
        warnings=warnings,
        canonical_csv_text=canonical_csv,
    )


def render_canonical_csv(rows: list[NormalizedRow]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "code",
            "description",
            "description_clean",
            "packaging_raw",
            "packaging",
            "is_liquidation",
            "liquidation_tag",
            "price_net",
            "price_with_vat",
            "supplier_utility_pct",
            "price_pack_with_utility",
            "units_per_package",
            "price_unit_with_utility",
            "vat_rate_detected",
            "price_anomaly",
            "image_source_url",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.code,
                r.description,
                r.description_clean,
                r.packaging_raw,
                r.packaging,
                "1" if r.is_liquidation else "0",
                r.liquidation_tag or "",
                f"{r.price_net:.6f}",
                f"{r.price_with_vat:.6f}",
                f"{r.supplier_utility_pct:.2f}",
                f"{r.price_pack_with_utility:.6f}",
                r.units_per_package,
                f"{r.price_unit_with_utility:.6f}",
                f"{r.vat_rate_detected:.3f}" if r.vat_rate_detected is not None else "",
                "1" if r.price_anomaly else "0",
                r.image_source_url or "",
            ]
        )
    return buf.getvalue()


def save_canonical_csv(import_id: str, csv_text: str) -> str:
    tmp_dir = Path(settings.import_tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_dir / f"{import_id}.csv"
    tmp_file = tmp_dir / f"{import_id}.csv.tmp"
    tmp_file.write_text(csv_text, encoding="utf-8")
    os.replace(tmp_file, target)
    return str(target)


def delete_canonical_csv(path_str: str | None) -> None:
    if not path_str:
        return
    try:
        Path(path_str).unlink(missing_ok=True)
    except OSError:
        pass


def cleanup_expired_canonical_csvs() -> int:
    tmp_dir = Path(settings.import_tmp_dir)
    if not tmp_dir.exists():
        return 0
    cutoff = time.time() - (settings.import_tmp_retention_days * 86400)
    removed = 0
    for item in tmp_dir.glob("*.csv"):
        try:
            if item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue
    return removed
