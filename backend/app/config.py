import json
from typing import Annotated, Any, Self
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> Any:
        if v is None or v == "":
            return ["http://localhost:3000", "http://127.0.0.1:3000"]
        if isinstance(v, str):
            raw = v.strip()
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url_host(cls, v: str) -> str:
        """Reject malformed DB hosts that cause IDNA errors at connect time (e.g. empty DNS labels)."""
        if v is None or not str(v).strip():
            return v
        raw = str(v).strip()
        parsed = urlparse(raw)
        scheme = (parsed.scheme or "").lower()
        if not scheme.startswith("postgresql"):
            return v
        host = parsed.hostname
        if host is None or host == "":
            raise ValueError(
                "DATABASE_URL has no hostname. For Docker Compose staging use host `cloud-sql-proxy` "
                "(see .env.staging.gcp.example). Example: "
                "postgresql+asyncpg://USER:PASSWORD@cloud-sql-proxy:5432/DBNAME"
            )
        if host.startswith(".") or host.endswith(".") or ".." in host:
            raise ValueError(
                f"DATABASE_URL hostname {host!r} is invalid (leading/trailing dot or empty label). "
                "This triggers IDNA errors at connection time. Use a plain hostname such as "
                "`cloud-sql-proxy` with no dots at the ends or doubled dots."
            )
        labels = host.split(".")
        if any(label == "" for label in labels):
            raise ValueError(
                f"DATABASE_URL hostname {host!r} contains an empty DNS label. "
                "Fix the host in DATABASE_URL (staging: `cloud-sql-proxy`)."
            )
        return v

    frontend_base_url: str = "http://localhost:3000"
    invite_token_expire_hours: int = 72
    password_min_length: int = 8
    temporary_password_length: int = 8

    # Nalo SMS (competitors / coaches)
    sms_enabled: bool = False
    nalo_sms_key: str = ""
    nalo_sms_sender_id: str = "WSkillsGH"
    nalo_sms_url: str = "https://sms.nalosolutions.com/smsbackend/Resl_Nalo/send-message/"


class LoggingSettings(BaseSettings):
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"  # "text" or "json"
    ENV: str = "dev"  # dev | staging | prod

    class Config:
        env_prefix = "APP_"


settings = Settings()  # type: ignore
logging_settings = LoggingSettings()  # type: ignore
