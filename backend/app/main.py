import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.api import assignments as assignments_api
from app.api import auth as auth_api
from app.api import consent as consent_api
from app.api import cycles as cycles_api
from app.api import eligibility as eligibility_api
from app.api import nominations as nominations_api
from app.api import registrations as registrations_api
from app.api import skills as skills_api
from app.api import stages as stages_api
from app.api import submissions as submissions_api
from app.api import assessment as assessment_api
from app.api import shortlists as shortlists_api
from app.config import logging_settings, settings
from app.core.errors import (
    AppError,
    app_error_handler,
    envelope_response,
    unhandled_error_handler,
    validation_error_handler,
)
from app.dependencies.database import get_sessionmanager, initialize_db
from app.initial_data import ensure_super_admin_user

SENSITIVE_KEYS = {"password", "token", "authorization"}


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
app.add_exception_handler(Exception, unhandled_error_handler)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("http")

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/health", "/metrics"}:
            return await call_next(request)

        start_time = time.monotonic()
        try:
            response = await call_next(request)
            duration_ms = (time.monotonic() - start_time) * 1000
            self.logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return response
        except AppError as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            self.logger.warning(
                "request domain error",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "code": exc.code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return envelope_response(
                code=exc.code,
                message=exc.message,
                status_code=exc.status_code,
                fields=[f.to_dict() for f in exc.fields],
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            self.logger.error(
                "request failed",
                exc_info=exc,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            if logging_settings.ENV == "dev":
                raise
            return envelope_response(
                code="INTERNAL_ERROR",
                message="Internal server error",
                status_code=500,
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
app.include_router(cycles_api.router)
app.include_router(skills_api.router)
app.include_router(stages_api.router)
app.include_router(submissions_api.router)
app.include_router(assessment_api.router)
app.include_router(shortlists_api.router)
app.include_router(assignments_api.router)
app.include_router(nominations_api.router)
app.include_router(registrations_api.router)
app.include_router(consent_api.router)
app.include_router(eligibility_api.router)


@app.get("/", status_code=status.HTTP_200_OK)
def root() -> dict[str, Any]:
    return {"success": True, "service": "scms"}


@app.get("/health", status_code=status.HTTP_200_OK)
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
