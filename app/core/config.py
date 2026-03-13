from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Live Trading Control Plane API"
    environment: str = "production"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str | None = None
    database_echo: bool = False
    ingest_api_key: str | None = None
    action_executor_enabled: bool = False
    action_executor_runner_key: str | None = None
    action_executor_poll_ms: int = 1000
    action_executor_timeout_secs: int = 120
    action_executor_max_output_chars: int = 4000
    action_command_map_json: str | None = None
    polymarket_data_host: str = "https://data-api.polymarket.com"
    polymarket_overview_wallet: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
