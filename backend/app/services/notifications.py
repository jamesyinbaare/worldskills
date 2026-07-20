"""US-NOT-01 — event-driven multi-channel notifications with preferences."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import (
    NotificationOutbox,
    NotificationPreference,
    NotificationTemplate,
    User,
)
from app.services.audit import write_audit_event


class ChannelSender(Protocol):
    def send(self, *, channel: str, to: str, subject: str, body: str) -> None: ...


class StubChannelSender:
    """Default sender — always succeeds."""

    def send(self, *, channel: str, to: str, subject: str, body: str) -> None:
        _ = (channel, to, subject, body)


class SelectiveFailSender:
    """Fails configured channels (for fallback tests)."""

    def __init__(self, fail_channels: set[str] | None = None) -> None:
        self.fail_channels = {c.upper() for c in (fail_channels or set())}
        self.attempts: list[tuple[str, str]] = []

    def send(self, *, channel: str, to: str, subject: str, body: str) -> None:
        _ = (subject, body)
        ch = channel.upper()
        self.attempts.append((ch, to))
        if ch in self.fail_channels:
            raise RuntimeError(f"{ch} delivery failed")


@dataclass
class EmitResult:
    status: str
    channel: str | None
    outbox_id: uuid.UUID | None
    language: str | None = None
    error: str | None = None


def render_template(text: str, context: dict[str, Any]) -> str:
    result = text
    for key, value in context.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def _contact_for_channel(prefs: NotificationPreference, channel: str) -> str | None:
    ch = channel.upper()
    if ch == "EMAIL":
        return prefs.email
    if ch == "SMS":
        return prefs.phone
    if ch == "WHATSAPP":
        return prefs.whatsapp or prefs.phone
    return None


async def emit(
    session: AsyncSession,
    *,
    event: str,
    recipient_id: uuid.UUID,
    context: dict[str, Any] | None = None,
    cycle_id: uuid.UUID | None = None,
    recipient_role: str = "USER",
    dedupe_key: str | None = None,
    sender: ChannelSender | None = None,
    actor: User | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> EmitResult:
    """Render + send a notification for a domain event (spec NotificationService.emit)."""
    context = dict(context or {})
    channel_sender = sender or StubChannelSender()

    # Deduplicate deadline reminders etc.
    if dedupe_key:
        prior = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.dedupe_key == dedupe_key,
                    NotificationOutbox.status.in_(["SENT", "FALLBACK_SENT", "QUEUED"]),
                )
            )
        ).scalar_one_or_none()
        if prior is not None:
            return EmitResult(
                status=prior.status,
                channel=prior.channel,
                outbox_id=prior.id,
                language=prior.language,
            )

    prefs = (
        await session.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == recipient_id)
        )
    ).scalar_one_or_none()
    if prefs is None:
        raise AppError(
            "NO_CONTACT_CHANNEL",
            "Recipient has no notification preferences / channels",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("recipientId", "NO_CONTACT_CHANNEL")],
        )

    # Product is English-only — ignore recipient language preference.
    language = "en"
    tmpl = (
        await session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.event_key == event,
                NotificationTemplate.language == language,
            )
        )
    ).scalars().first()

    if tmpl is None:
        raise AppError(
            "TEMPLATE_MISSING",
            f"No English template for event '{event}'",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("event", "TEMPLATE_MISSING")],
        )

    # Opt-out for non-essential
    if prefs.opt_out_non_essential and not tmpl.essential:
        row = NotificationOutbox(
            cycle_id=cycle_id,
            recipient_role=recipient_role,
            recipient_id=recipient_id,
            template=event,
            event_key=event,
            payload=context,
            language=language,
            status="SKIPPED",
            error="OPT_OUT_NON_ESSENTIAL",
            dedupe_key=dedupe_key,
        )
        session.add(row)
        await session.flush()
        if actor is not None:
            await write_audit_event(
                session,
                action="NOTIFICATION_SKIPPED",
                entity_type="NotificationOutbox",
                entity_id=str(row.id),
                actor_id=actor.id,
                actor_role=actor.role.value,
                cycle_id=cycle_id,
                after={"event": event, "reason": "OPT_OUT_NON_ESSENTIAL"},
                ip=ip,
                user_agent=user_agent,
            )
        await session.commit()
        return EmitResult(status="SKIPPED", channel=None, outbox_id=row.id, language=language)

    subject = render_template(tmpl.subject, context)
    body = render_template(tmpl.body, context)

    preferred = (prefs.preferred_channel or "EMAIL").upper()
    fallback = (prefs.fallback_channel or "SMS").upper() if prefs.fallback_channel else None

    channels_to_try = [preferred]
    if fallback and fallback != preferred:
        channels_to_try.append(fallback)

    # Ensure at least one channel has a contact
    contacts = {ch: _contact_for_channel(prefs, ch) for ch in channels_to_try}
    if not any(contacts.values()):
        raise AppError(
            "NO_CONTACT_CHANNEL",
            "Recipient has no valid contact on preferred/fallback channels",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("recipientId", "NO_CONTACT_CHANNEL")],
        )

    row = NotificationOutbox(
        cycle_id=cycle_id,
        recipient_role=recipient_role,
        recipient_id=recipient_id,
        template=event,
        event_key=event,
        payload=context,
        language=language,
        rendered_subject=subject,
        rendered_body=body,
        status="QUEUED",
        dedupe_key=dedupe_key,
        created_at=datetime.utcnow(),
    )
    session.add(row)
    await session.flush()

    last_error: str | None = None
    for idx, channel in enumerate(channels_to_try):
        to = contacts.get(channel)
        if not to:
            last_error = f"NO_CONTACT_FOR_{channel}"
            continue
        try:
            channel_sender.send(channel=channel, to=to, subject=subject, body=body)
            row.channel = channel
            row.status = "SENT" if idx == 0 else "FALLBACK_SENT"
            row.error = last_error  # retain primary failure if fallback used
            if actor is not None:
                await write_audit_event(
                    session,
                    action="NOTIFICATION_SENT",
                    entity_type="NotificationOutbox",
                    entity_id=str(row.id),
                    actor_id=actor.id,
                    actor_role=actor.role.value,
                    cycle_id=cycle_id,
                    after={
                        "event": event,
                        "channel": channel,
                        "status": row.status,
                        "language": language,
                    },
                    ip=ip,
                    user_agent=user_agent,
                )
            await session.commit()
            await session.refresh(row)
            return EmitResult(
                status=row.status,
                channel=channel,
                outbox_id=row.id,
                language=language,
                error=row.error,
            )
        except Exception as exc:  # noqa: BLE001 — delivery stubs may raise anything
            last_error = str(exc)
            row.error = last_error
            await session.flush()
            continue

    row.status = "FAILED"
    row.error = last_error or "DELIVERY_FAILED"
    if actor is not None:
        await write_audit_event(
            session,
            action="NOTIFICATION_FAILED",
            entity_type="NotificationOutbox",
            entity_id=str(row.id),
            actor_id=actor.id,
            actor_role=actor.role.value,
            cycle_id=cycle_id,
            after={"event": event, "error": row.error},
            ip=ip,
            user_agent=user_agent,
        )
    await session.commit()
    await session.refresh(row)
    return EmitResult(
        status="FAILED",
        channel=row.channel,
        outbox_id=row.id,
        language=language,
        error=row.error,
    )
