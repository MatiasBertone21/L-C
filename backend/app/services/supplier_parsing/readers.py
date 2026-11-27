import csv
from html.parser import HTMLParser
import io
from typing import Any
import zipfile

import openpyxl
import xlrd

from app.core.exceptions import UnprocessableEntityError

MAX_UNCOMPRESSED_XLSX_BYTES = 150 * 1024 * 1024


def read_xls_biff_rows(raw_bytes: bytes) -> list[list[Any]]:
    try:
        book = xlrd.open_workbook(file_contents=raw_bytes)
    except Exception as exc:
        raise UnprocessableEntityError(f"No se pudo abrir el archivo Excel (.xls): {exc}") from exc

    if book.nsheets == 0:
        raise UnprocessableEntityError("El archivo Excel (.xls) no contiene hojas.")

    # Priorizar hoja llamada Catálogo si existe
    target_sheet = book.sheet_by_index(0)
    for idx in range(book.nsheets):
        sh = book.sheet_by_index(idx)
        if "cat" in sh.name.lower() and sh.nrows > 0:
            target_sheet = sh
            break

    rows: list[list[Any]] = []
    for r_idx in range(target_sheet.nrows):
        rows.append([target_sheet.cell_value(r_idx, c_idx) for c_idx in range(target_sheet.ncols)])
    return rows


def read_xlsx_rows(raw_bytes: bytes) -> list[list[Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            if total_uncompressed > MAX_UNCOMPRESSED_XLSX_BYTES:
                raise UnprocessableEntityError(
                    "El archivo .xlsx descomprimido excede el límite de seguridad permitido."
                )
    except zipfile.BadZipFile as exc:
        raise UnprocessableEntityError("El archivo .xlsx está dañado o no es un archivo ZIP válido.") from exc

    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise UnprocessableEntityError(f"No se pudo leer el archivo Excel (.xlsx): {exc}") from exc

    try:
        if not wb.sheetnames:
            raise UnprocessableEntityError("El archivo .xlsx no contiene hojas.")

        sheet_name = wb.sheetnames[0]
        for candidate in wb.sheetnames:
            if "cat" in candidate.lower():
                sheet_name = candidate
                break

        ws = wb[sheet_name]
        rows: list[list[Any]] = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))
        return rows
    finally:
        wb.close()


class _HTMLTableExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell_parts: list[str] | None = None
        self._cell_img_src: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "tr":
            self._current_row = []
        elif t in ("td", "th") and self._current_row is not None:
            self._current_cell_parts = []
            self._cell_img_src = None
        elif t == "img" and self._current_cell_parts is not None:
            attr_map = {k.lower(): (v or "") for k, v in attrs}
            if attr_map.get("src"):
                self._cell_img_src = attr_map["src"]

    def handle_data(self, data: str) -> None:
        if self._current_cell_parts is not None:
            self._current_cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th") and self._current_row is not None and self._current_cell_parts is not None:
            text_val = "".join(self._current_cell_parts).strip()
            if not text_val and self._cell_img_src:
                text_val = self._cell_img_src
            self._current_row.append(text_val)
            self._current_cell_parts = None
            self._cell_img_src = None
        elif t == "tr" and self._current_row is not None:
            if any(cell != "" for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None


def _decode_text_bytes(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def read_html_table_rows(raw_bytes: bytes) -> list[list[Any]]:
    text = _decode_text_bytes(raw_bytes)
    parser = _HTMLTableExtractor()
    parser.feed(text)
    if not parser.rows:
        raise UnprocessableEntityError("No se encontraron filas de tabla dentro del archivo HTML/.xls.")
    return parser.rows


def read_csv_rows(raw_bytes: bytes) -> list[list[Any]]:
    text = _decode_text_bytes(raw_bytes)
    sample = text[:8192]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        if first_line.count(";") > first_line.count(","):
            delimiter = ";"
        elif first_line.count("\t") > first_line.count(","):
            delimiter = "\t"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [row for row in reader]


def extract_raw_rows(raw_bytes: bytes, detected_format: str) -> list[list[Any]]:
    if detected_format == "xls_biff":
        return read_xls_biff_rows(raw_bytes)
    if detected_format == "xlsx":
        return read_xlsx_rows(raw_bytes)
    if detected_format == "xls_html":
        return read_html_table_rows(raw_bytes)
    return read_csv_rows(raw_bytes)
