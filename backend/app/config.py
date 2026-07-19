import json
from typing import Annotated, Any, Self


from pydantic import Field
from pydantic_settings import BaseSettings, NoDecode

class Settings(BaseSettings):
    database_url: str = ""
    environment: str = "dev"
    super_admin_email: str = ""  # Required: Email for the initial SUPER_ADMIN user
    super_admin_password: str = ""  # Required: Password for the initial SUPER_ADMIN user
    super_admin_full_name: str = ""  # Required: Full name for the initial SUPER_ADMIN user
    # Comma-separated in env (CORS_ORIGINS); browser origins allowed for credentialed API calls
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
    )



class LoggingSettings(BaseSettings):
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"  # "text" or "json"
    ENV: str = "dev"  # dev | staging | prod

    class Config:
        env_prefix = "APP_"



settings = Settings()  # type: ignore
logging_settings = LoggingSettings() # type: ignore
