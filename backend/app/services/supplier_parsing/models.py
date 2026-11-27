from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class NormalizedRow:
    code: str
    description: str
    description_clean: str
    search_text: str
    star_prefix: bool
    hash_suffix: bool
    packaging_raw: str
    packaging: str
    is_liquidation: bool
    liquidation_tag: str | None
    price_net: Decimal
    price_with_vat: Decimal
    supplier_utility_pct: Decimal
    price_pack_with_utility: Decimal
    units_per_package: int
    price_unit_with_utility: Decimal
    vat_rate_detected: Decimal | None
    price_anomaly: bool
    image_source_url: str | None
    row_fingerprint: str


@dataclass(slots=True)
class ParseWarningItem:
    row: int
    code: str
    message: str


@dataclass(slots=True)
class ParsedSupplierFile:
    detected_format: str
    file_hash: str
    content_hash: str
    rows: list[NormalizedRow]
    skipped_rows: int = 0
    invalid_rows: int = 0
    price_anomaly_count: int = 0
    warnings: list[ParseWarningItem] = field(default_factory=list)
    canonical_csv_text: str = ""
