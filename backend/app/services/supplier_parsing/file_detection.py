from pathlib import Path
import re

from app.core.exceptions import UnsupportedMediaTypeError

ALLOWED_EXTENSIONS = {".xls", ".xlsx", ".csv"}

OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"
HTML_SIGNATURE_RE = re.compile(rb"^\s*(?:\xef\xbb\xbf)?\s*(?:<!doctype\s+html|<html|<table|<meta)", re.IGNORECASE)


def sanitize_filename(filename: str | None) -> str:
    if not filename:
        return "lista_proveedor.csv"
    base = Path(filename).name.strip()
    base = re.sub(r"[^\w.\- ()áéíóúÁÉÍÓÚñÑ]", "_", base)
    return (base or "lista_proveedor.csv")[:120]


def detect_supplier_file_format(raw_bytes: bytes, filename: str | None = None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedMediaTypeError(
            f"Formato '{ext}' no soportado. Subí un archivo .xls, .xlsx o .csv."
        )

    if not raw_bytes or not raw_bytes.strip():
        raise UnsupportedMediaTypeError("El archivo subido está vacío.")

    head = raw_bytes[:2048]
    if head.startswith(OLE2_MAGIC):
        return "xls_biff"
    if head.startswith(ZIP_MAGIC):
        return "xlsx"
    if HTML_SIGNATURE_RE.search(head):
        return "xls_html"

    # Rechazar binarios desconocidos (ej. PDF disfrazado o ejecutable)
    if head.startswith(b"%PDF") or b"\x00\x00\x00" in head[:256]:
        raise UnsupportedMediaTypeError(
            "El contenido del archivo no corresponde a una planilla Excel o CSV válida."
        )

    return "csv"
