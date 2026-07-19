"""Standard SCMS error envelope and domain exceptions."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response


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


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return envelope_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        fields=[f.to_dict() for f in exc.fields],
    )


_KNOWN_REASONS = {
    "INVALID_TIMEZONE",
    "AT_LEAST_ONE_LANGUAGE",
    "UNSUPPORTED_LANGUAGE",
    "BEFORE_START",
    "REQUIRED",
    "DUPLICATE",
    "INVALID_CAPACITY",
    "REASON_REQUIRED",
}


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    fields: list[dict[str, str]] = []
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
        fields.append({"name": name or "body", "reason": reason})
    return envelope_response(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        fields=fields,
    )


async def unhandled_error_handler(_request: Request, _exc: Exception) -> Response:
    return envelope_response(
        code="INTERNAL_ERROR",
        message="Internal server error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
