import csv
import io
from typing import Any
import openpyxl

from app.core.exceptions import UnsupportedMediaTypeError, UnprocessableEntityError
from app.services.supplier_parsing import parse_and_normalize_supplier_bytes

HEADERS = [
    "Código",
    "Descripción",
    "Empaque",
    "$ S/IVA",
    "$ C/IVA",
    "Utilidad %",
    "$ C/IVA y Utilidad Paquete",
    "Unidades Por Paquete",
    "$ C/IVA y Utilidad Unidad",
    "IMG",
]


def make_csv_bytes(rows: list[list[Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(HEADERS)
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def make_xlsx_bytes(rows: list[list[Any]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Catálogo"
    ws.append(HEADERS)
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_parse_argentine_csv_with_junk_and_anomalies() -> None:
    sample_rows = [
        ["0", "", "", "0", "0", "10", "0", "1", "0", ""],
        [
            "191040",
            "*ADH SILICONA LIQUIDA  PRITT  30gr. (48) #",
            "1UNIDAD",
            "352,5",
            "426,525",
            "10",
            "469,177",
            "1",
            "469,177",
            "https://www.eloncemayorista.com.ar/system_files/articulos/imagenes/0030/191040.jpg?d=210721' width='142' height='80' >",
        ],
        [
            "193400",
            "ADH INSTANTANEO CBX 3gr. x12u.",
            "LIQUIDA       L",
            "3387,384",
            "4098,73464",
            "10",
            "4508,608",
            "12",
            "375,7173333",
            "https://www.eloncemayorista.com.ar/system_files/articulos/imagenes/0119/193400.PNG",
        ],
        [
            "321470",
            "ABR EAGLE HEAVY-DUTY 8539",
            "PAQUTE",
            "39422033,33",
            "10000000",
            "10",
            "11000000",
            "1",
            "11000000",
            "",
        ],
    ]
    parsed = parse_and_normalize_supplier_bytes(make_csv_bytes(sample_rows), "lista_2026-11-27.csv")

    assert parsed.detected_format == "csv"
    assert len(parsed.rows) == 3
    assert parsed.skipped_rows == 1
    assert parsed.invalid_rows == 0
    assert parsed.price_anomaly_count == 1

    by_code = {r.code: r for r in parsed.rows}
    r1 = by_code["191040"]
    assert r1.packaging == "UNIDAD"
    assert r1.star_prefix is True and r1.hash_suffix is True
    assert r1.description_clean == "ADH SILICONA LIQUIDA PRITT 30gr. (48)"
    assert r1.image_source_url == "https://www.eloncemayorista.com.ar/system_files/articulos/imagenes/0030/191040.jpg?d=210721"

    r2 = by_code["193400"]
    assert r2.packaging == "LIQUIDACION"
    assert r2.is_liquidation is True
    assert r2.liquidation_tag == "LIQUIDA"
    assert r2.units_per_package == 12

    r3 = by_code["321470"]
    assert r3.packaging == "PAQUETE"
    assert r3.price_anomaly is True
    assert r3.image_source_url is None


def test_parse_xlsx_and_html_xls_and_parity() -> None:
    xlsx_bytes = make_xlsx_bytes(
        [
            [0.0, None, None, 0.0, 0.0, 10.0, 0.0, 1.0, 0.0, None],
            [137080.0, "CUADERNO TAPA DURA A4", "Unidad", 1000.0, 1210.0, 10.0, 1331.0, 1.0, 1331.0, "https://evil.example.com/x.jpg"],
        ]
    )
    parsed_xlsx = parse_and_normalize_supplier_bytes(xlsx_bytes, "lista.xlsx")
    assert parsed_xlsx.detected_format == "xlsx"
    assert len(parsed_xlsx.rows) == 1
    assert parsed_xlsx.rows[0].code == "137080"
    assert parsed_xlsx.rows[0].packaging == "UNIDAD"
    assert parsed_xlsx.rows[0].image_source_url is None  # Host externo bloqueado

    html_xls = """
    <html><body><table>
      <tr><th>Código</th><th>Descripción</th><th>Empaque</th><th>$ S/IVA</th><th>$ C/IVA</th></tr>
      <tr><td>137080</td><td>CUADERNO TAPA DURA A4</td><td>UNIDAD</td><td>1.000,00</td><td>1.210,00</td></tr>
    </table></body></html>
    """.encode("utf-8")
    parsed_html = parse_and_normalize_supplier_bytes(html_xls, "lista.xls")
    assert parsed_html.detected_format == "xls_html"
    assert parsed_html.rows[0].code == "137080"
    assert str(parsed_html.rows[0].price_with_vat) == "1210.000000"


def test_reject_invalid_extension_and_missing_headers() -> None:
    try:
        parse_and_normalize_supplier_bytes(b"%PDF-1.7 fake", "lista.pdf")
        assert False, "Debió rechazar extensión PDF"
    except UnsupportedMediaTypeError:
        pass

    try:
        parse_and_normalize_supplier_bytes(b"ColA,ColB\n1,2\n", "mala.csv")
        assert False, "Debió rechazar columnas faltantes"
    except UnprocessableEntityError:
        pass
