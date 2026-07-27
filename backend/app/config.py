from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    environment: str = "dev"
    super_admin_email: str = ""
    super_admin_password: str = ""
    super_admin_full_name: str = ""
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    audit_hmac_secret: str = "change-me-audit-secret"
    storage_root: str = "/app/storage/documents"
    storage_backend: str = "local"  # "local" | "gcs"
    gcs_bucket_name: str = ""
    gcs_project_id: str = ""
    gcs_credentials_path: str = ""
    gcs_documents_prefix: str = "world-skills"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
    )
    frontend_base_url: str = "http://localhost:3000"
    invite_token_expire_hours: int = 72
    password_min_length: int = 10


class LoggingSettings(BaseSettings):
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"  # "text" or "json"
    ENV: str = "dev"  # dev | staging | prod

    class Config:
        env_prefix = "APP_"


settings = Settings()  # type: ignore
logging_settings = LoggingSettings()  # type: ignore
