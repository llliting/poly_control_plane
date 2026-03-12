from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Live Trading Control Plane API"
    environment: str = "production"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str | None = None
    database_echo: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
