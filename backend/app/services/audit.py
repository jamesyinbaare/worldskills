"""Append-only audit event writer with HMAC tamper-evidence."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.errors import AppError
from app.models import AuditEvent


def _canonical_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def sign_audit_payload(payload: dict[str, Any]) -> str:
    digest = hmac.new(
        settings.audit_hmac_secret.encode("utf-8"),
        _canonical_payload(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def verify_audit_signature(event: AuditEvent) -> bool:
    payload = {
        "competitionId": str(event.competition_id) if event.competition_id else None,
        "actorId": str(event.actor_id) if event.actor_id else None,
        "actorRole": event.actor_role,
        "action": event.action,
        "entityType": event.entity_type,
        "entityId": event.entity_id,
        "before": event.before,
        "after": event.after,
        "reason": event.reason,
        "ip": event.ip,
        "userAgent": event.user_agent,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
    }
    expected = sign_audit_payload(payload)
    return hmac.compare_digest(expected, event.signature)


async def write_audit_event(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    competition_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent:
    timestamp = datetime.utcnow()
    payload = {
        "competitionId": str(competition_id) if competition_id else None,
        "actorId": str(actor_id) if actor_id else None,
        "actorRole": actor_role,
        "action": action,
        "entityType": entity_type,
        "entityId": entity_id,
        "before": before,
        "after": after,
        "reason": reason,
        "ip": ip,
        "userAgent": user_agent,
        "timestamp": timestamp.isoformat(),
    }
    try:
        event = AuditEvent(
            competition_id=competition_id,
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            reason=reason,
            ip=ip,
            user_agent=user_agent,
            timestamp=timestamp,
            signature=sign_audit_payload(payload),
        )
        session.add(event)
        await session.flush()
        return event
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            "AUDIT_WRITE_FAILED",
            "Audit event could not be written; action aborted",
            status_code=500,
        ) from exc
