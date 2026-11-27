from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "L&C Stock & POS API"
    app_version: str = "0.4.0"
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

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return origins or ["http://localhost:5173"]


settings = Settings()
