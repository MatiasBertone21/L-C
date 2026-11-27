from pathlib import Path
import tempfile

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_APP_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "L&C Stock & POS API"
    app_version: str = "0.5.0"
    environment: str = "development"
    port: int = 8000

    mongo_uri: str = ""
    mongo_db_name: str = "lc_inventory"

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    internal_api_key: str = ""

    seed_admin_email: str = "admin@librerialc.com.ar"
    seed_admin_password: str = ""
    seed_user_email: str = "ventas@librerialc.com.ar"
    seed_user_password: str = ""

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    supplier_default_code: str = "elonce"
    supplier_image_allowed_hosts: str = "www.eloncemayorista.com.ar,eloncemayorista.com.ar"
    business_timezone: str = "America/Argentina/Buenos_Aires"
    import_max_upload_mb: int = 15
    import_min_rows_ratio: float = 0.5
    import_tmp_dir: str = str(Path(tempfile.gettempdir()) / "lc-import-tmp")
    import_tmp_retention_days: int = 7

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_import_tmp_outside_repo(self) -> "Settings":
        resolved_tmp = Path(self.import_tmp_dir).resolve()
        try:
            resolved_tmp.relative_to(_BACKEND_APP_ROOT)
            is_inside_backend = True
        except ValueError:
            is_inside_backend = False

        if is_inside_backend:
            raise ValueError(
                f"IMPORT_TMP_DIR ({resolved_tmp}) no puede apuntar dentro del directorio backend ({_BACKEND_APP_ROOT})."
            )
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return origins or ["http://localhost:5173"]

    @property
    def allowed_image_hosts_set(self) -> set[str]:
        return {
            host.strip().lower()
            for host in self.supplier_image_allowed_hosts.split(",")
            if host.strip()
        }


settings = Settings()
