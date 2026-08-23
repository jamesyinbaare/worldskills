import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from sqlalchemy import text

from app.api import appeals as appeals_api
from app.api import assignments as assignments_api
from app.api import auth as auth_api
from app.api import catalog as catalog_api
from app.api import consent as consent_api
from app.api import competition_config as competition_config_api
from app.api import competitor_portal as competitor_portal_api
from app.api import competitions as competitions_api
from app.api import competitors_admin as competitors_admin_api
from app.api import institution_portal as institution_portal_api

from app.api import eligibility as eligibility_api
from app.api import exercises as exercises_api
from app.api import geography as geography_api
from app.api import governance as governance_api
from app.api import users as users_api
from app.api import institutions as institutions_api
from app.api import lifecycle as lifecycle_api
from app.api import nominations as nominations_api
from app.api import public_portal as public_portal_api
from app.api import registrations as registrations_api
from app.api import scheduling as scheduling_api
from app.api import settings as settings_api
from app.api import skills as skills_api
from app.api import sponsors as sponsors_api
from app.api import stages as stages_api
from app.api import submissions as submissions_api
from app.api import assessment as assessment_api
from app.api import results as results_api
from app.api import shortlists as shortlists_api
from app.config import logging_settings, settings
from app.core.errors import (
    AppError,
    app_error_handler,
    envelope_response,
    http_exception_handler,
    public_message,
    unhandled_error_handler,
    validation_error_handler,
)
from app.dependencies.database import get_sessionmanager, initialize_db
from app.initial_data import ensure_super_admin_user

SENSITIVE_KEYS = {"password", "token", "authorization"}
_SKIP_LOG_PATHS = frozenset({"/health", "/ready", "/metrics"})


class CustomFormatter(logging.Formatter):
    def __init__(self, use_json: bool = False, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.use_json = use_json
        self.default_attrs = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys())

    def format(self, record: logging.LogRecord) -> str:
        extra = {
            k: ("***" if k.lower() in SENSITIVE_KEYS else v)
            for k, v in record.__dict__.items()
            if k not in self.default_attrs
        }

        if self.use_json:
            payload = {
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                **extra,
            }
            if record.exc_info:
                payload["exception"] = self.formatException(record.exc_info)
            return json.dumps(payload, default=str)

        base = super().format(record)
        if extra:
            extra_info = " ".join(f"{k}={v}" for k, v in extra.items())
            return f"{base} | {extra_info}"
        return base


def setup_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_configured", False):
        return
    root._configured = True  # type: ignore[attr-defined]
    root.setLevel(logging_settings.LOG_LEVEL)
    handler = logging.StreamHandler()
    formatter = CustomFormatter(
        use_json=logging_settings.LOG_FORMAT == "json",
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    handler.setFormatter(formatter)
    handler.setLevel(logging.NOTSET)
    root.handlers.clear()
    root.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    sessionmanager = get_sessionmanager()
    async with initialize_db(sessionmanager):
        async with sessionmanager.session() as session:
            await ensure_super_admin_user(session)
        yield


app = FastAPI(title="Skills Competition Management System", lifespan=lifespan)

app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_error_handler)


class RequestLoggingMiddleware:
    """Pure ASGI request logger — avoids BaseHTTPMiddleware task/hang issues."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "") or ""
        if path in _SKIP_LOG_PATHS:
            await self.app(scope, receive, send)
            return

        start_time = time.monotonic()
        status_code = 500
        method = scope.get("method", "")
        response_started = False

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except AppError as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            self.logger.warning(
                "request domain error",
                extra={
                    "method": method,
                    "path": path,
                    "code": exc.code,
                    "detail": exc.message,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            if not response_started:
                response = envelope_response(
                    code=exc.code,
                    message=public_message(exc.code, exc.status_code, exc.message),
                    status_code=exc.status_code,
                    fields=[f.to_dict() for f in exc.fields],
                )
                await response(scope, receive, send)
            return
        except Exception:
            duration_ms = (time.monotonic() - start_time) * 1000
            self.logger.error(
                "request failed",
                exc_info=True,
                extra={
                    "method": method,
                    "path": path,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            # Do not re-raise: ServerErrorMiddleware would re-raise after handling and
            # break ASGI test clients; keep a single INTERNAL_ERROR envelope for clients.
            if not response_started:
                response = envelope_response(
                    code="INTERNAL_ERROR",
                    message=public_message("INTERNAL_ERROR", 500, "Internal server error"),
                    status_code=500,
                )
                await response(scope, receive, send)
            return
        else:
            duration_ms = (time.monotonic() - start_time) * 1000
            self.logger.info(
                "request completed",
                extra={
                    "method": method,
                    "path": path,
                    "status": status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )


app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(auth_api.router)
app.include_router(catalog_api.router)
app.include_router(geography_api.router)
app.include_router(competitions_api.router)
app.include_router(competition_config_api.router)
app.include_router(skills_api.router)
app.include_router(stages_api.router)
app.include_router(exercises_api.router)
app.include_router(submissions_api.router)
app.include_router(assessment_api.router)
app.include_router(shortlists_api.router)
app.include_router(results_api.router)
app.include_router(assignments_api.router)
app.include_router(nominations_api.router)
app.include_router(registrations_api.router)
app.include_router(competitors_admin_api.router)
app.include_router(competitor_portal_api.router)
app.include_router(institution_portal_api.router)
app.include_router(consent_api.router)
app.include_router(eligibility_api.router)
app.include_router(lifecycle_api.router)
app.include_router(appeals_api.router)
app.include_router(scheduling_api.router)
app.include_router(public_portal_api.router)
app.include_router(users_api.router)
app.include_router(institutions_api.router)
app.include_router(sponsors_api.router)
app.include_router(governance_api.router)
app.include_router(settings_api.router)


@app.get("/", status_code=status.HTTP_200_OK)
def root() -> dict[str, Any]:
    return {"success": True, "service": "scms"}


@app.get("/health", status_code=status.HTTP_200_OK)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", status_code=status.HTTP_200_OK)
async def ready() -> dict[str, str]:
    """Readiness: process is up and can obtain a working DB connection."""
    try:
        manager = get_sessionmanager()
        async with manager.session() as session:
            await session.execute(text("SELECT 1"))
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "SERVICE_UNAVAILABLE",
            "database unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return {"status": "ready"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
