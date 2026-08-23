"""Standard SCMS error envelope and domain exceptions."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

logger = logging.getLogger("app")

_GENERIC_5XX = (
    "Something went wrong. Please try again. "
    "If it continues, contact support and share the reference ID."
)
_GENERIC_503 = "The service is temporarily unavailable. Please try again shortly."

_STATUS_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "VALIDATION_ERROR",
    status.HTTP_429_TOO_MANY_REQUESTS: "TOO_MANY_REQUESTS",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
    status.HTTP_502_BAD_GATEWAY: "BAD_GATEWAY",
    status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
}

_SENSITIVE_CODES = frozenset(
    {
        "STORAGE_MISCONFIGURED",
        "DATABASE_NOT_CONFIGURED",
        "AUDIT_WRITE_FAILED",
        "INTERNAL_ERROR",
        "SERVICE_UNAVAILABLE",
        "BAD_GATEWAY",
        "HTTP_ERROR",
    }
)

_PUBLIC_BY_CODE: dict[str, str] = {
    "FORBIDDEN": "You do not have permission to do that.",
    "UNAUTHORIZED": "Please sign in again.",
    "INVALID_CREDENTIALS": "Invalid email or password.",
    "FILE_NOT_FOUND": "That file could not be found.",
    "FILE_TYPE": "That file type is not allowed.",
    "FILE_TOO_LARGE": "That file is too large.",
    "FILE_INFECTED": "That file could not be accepted. Please upload a different file.",
    "CONFIG_INCOMPLETE": (
        "This competition is not fully set up yet. Please contact an administrator."
    ),
    "NOT_FOUND": "We could not find what you were looking for.",
    "UPLOAD_OFFSET_MISMATCH": "The upload could not continue. Please try again.",
    "UPLOAD_SIZE_MISMATCH": "The upload size did not match. Please try again.",
    "UPLOAD_CHUNK_SIZE": "The upload could not continue. Please try again.",
    "UPLOAD_NOT_FOUND": "That upload session could not be found.",
    "VALIDATION_ERROR": "Some fields need attention before we can submit.",
    "STORAGE_MISCONFIGURED": _GENERIC_5XX,
    "DATABASE_NOT_CONFIGURED": _GENERIC_5XX,
    "AUDIT_WRITE_FAILED": _GENERIC_5XX,
    "INTERNAL_ERROR": _GENERIC_5XX,
    "BAD_GATEWAY": _GENERIC_5XX,
    "SERVICE_UNAVAILABLE": _GENERIC_503,
}

_LEAKY_MESSAGE = re.compile(
    r"(GCS_|DATABASE_|cloud-sql|asyncpg|traceback|not installed|"
    r"not configured\s*\(set |sqlalchemy|postgres://|postgresql)",
    re.IGNORECASE,
)


class FieldError:
    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "reason": self.reason}


class AppError(Exception):
    """Domain error that maps to the standard error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        fields: list[FieldError] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.fields = fields or []


def error_envelope(
    *,
    code: str,
    message: str,
    fields: list[dict[str, str]] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "fields": fields or [],
            "traceId": trace_id or str(uuid.uuid4()),
        }
    }


def envelope_response(
    *,
    code: str,
    message: str,
    status_code: int,
    fields: list[dict[str, str]] | None = None,
    trace_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_envelope(code=code, message=message, fields=fields, trace_id=trace_id),
    )


def public_message(code: str, status_code: int, internal_message: str) -> str:
    """Return a client-safe human message; keep internal_message for logs only."""
    if code.endswith("_MISCONFIGURED") or code in _SENSITIVE_CODES:
        if code == "SERVICE_UNAVAILABLE" or status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            return _GENERIC_503
        return _GENERIC_5XX
    if status_code >= 500:
        return _GENERIC_5XX
    if code in _PUBLIC_BY_CODE:
        return _PUBLIC_BY_CODE[code]
    if code.endswith("_NOT_FOUND"):
        return _PUBLIC_BY_CODE["NOT_FOUND"]
    if _LEAKY_MESSAGE.search(internal_message or ""):
        if status_code >= 500:
            return _GENERIC_5XX
        return "Something went wrong. Please try again."
    return internal_message or "Something went wrong. Please try again."


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "domain error code=%s detail=%s",
        exc.code,
        exc.message,
        extra={"code": exc.code, "status_code": exc.status_code, "detail": exc.message},
    )
    return envelope_response(
        code=exc.code,
        message=public_message(exc.code, exc.status_code, exc.message),
        status_code=exc.status_code,
        fields=[f.to_dict() for f in exc.fields],
    )


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    raw = exc.detail if isinstance(exc.detail, str) else ""
    if not raw:
        raw = _PUBLIC_BY_CODE.get(code, "Request failed")
    return envelope_response(
        code=code,
        message=public_message(code, exc.status_code, raw),
        status_code=exc.status_code,
    )


_KNOWN_REASONS = {
    "INVALID_TIMEZONE",
    "BEFORE_START",
    "REQUIRED",
    "DUPLICATE",
    "INVALID_CAPACITY",
    "REASON_REQUIRED",
    "ORDER_INVALID",
    "QUOTA_INVALID",
    "SCORE_RANGE",
    "BRANCH_TARGET_MISSING",
}


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    fields: list[dict[str, str]] = []
    messages: list[str] = []
    for err in exc.errors():
        loc = err.get("loc", ())
        name = ".".join(str(p) for p in loc if p != "body")
        msg = str(err.get("msg", ""))
        err_type = str(err.get("type", "INVALID")).upper().replace(".", "_")
        reason = err_type
        for known in _KNOWN_REASONS:
            if known in msg:
                reason = known
                break
        if err_type == "MISSING":
            reason = "REQUIRED"
        # Normalize opaque pydantic date errors into a stable reason
        if "DATE" in err_type and "PARSING" in err_type:
            reason = "INVALID_DATE"
        elif err_type in {"DATE_TYPE", "DATE_FROM_DATETIME_PARSING", "DATE_PARSING"}:
            reason = "INVALID_DATE"
        fields.append({"name": name or "body", "reason": reason})
        label = name or "field"
        if reason == "REQUIRED":
            messages.append(f"{label} is required")
        elif reason == "INVALID_DATE":
            messages.append(f"{label} must be a valid date")
        else:
            messages.append(f"{label}: {reason.replace('_', ' ').lower()}")

    summary = (
        messages[0]
        if len(messages) == 1
        else "Some fields need attention before we can submit."
    )
    return envelope_response(
        code="VALIDATION_ERROR",
        message=summary,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        fields=fields,
    )


async def unhandled_error_handler(_request: Request, _exc: Exception) -> Response:
    logger.exception("unhandled error", exc_info=_exc)
    return envelope_response(
        code="INTERNAL_ERROR",
        message=_GENERIC_5XX,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
