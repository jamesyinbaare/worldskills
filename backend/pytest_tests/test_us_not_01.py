"""US-NOT-01 — event-driven multi-channel notifications with preferences."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.core.security import get_password_hash
from app.dependencies.database import TestingDatabaseSessionManager as DBManager
from app.models import (
    NotificationOutbox,
    NotificationPreference,
    NotificationTemplate,
    User,
    UserRole,
)
from app.services.notifications import SelectiveFailSender, emit, render_template


async def _ensure_templates(session) -> None:
    desired = [
        ("PROJECT_REMINDER", "en", "Reminder for {{name}}", "Hello {{name}}, deadline is {{deadline}}.", False),
        ("RESULT_PUBLISHED", "en", "Results for {{name}}", "Your result is ready, {{name}}.", True),
    ]
    for event_key, language, subject, body, essential in desired:
        existing = (
            await session.execute(
                select(NotificationTemplate).where(
                    NotificationTemplate.event_key == event_key,
                    NotificationTemplate.language == language,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                NotificationTemplate(
                    event_key=event_key,
                    language=language,
                    subject=subject,
                    body=body,
                    essential=essential,
                    created_at=datetime.utcnow(),
                )
            )


async def _seed_user_prefs_templates(
    session_manager: DBManager,
    *,
    language: str = "en",
    opt_out: bool = False,
    preferred: str = "EMAIL",
    fallback: str = "SMS",
) -> tuple[User, uuid.UUID]:
    async with session_manager.session() as session:
        user = User(
            email=f"notify-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Notify Me",
            hashed_password=get_password_hash("pass-123"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        session.add(
            NotificationPreference(
                user_id=user.id,
                preferred_channel=preferred,
                fallback_channel=fallback,
                language=language,
                email=user.email,
                phone="+233200000001",
                whatsapp="+233200000001",
                opt_out_non_essential=opt_out,
                updated_at=datetime.utcnow(),
            )
        )
        await _ensure_templates(session)
        await session.commit()
        return user, user.id


@pytest.mark.asyncio
async def test_US_NOT_01_AC1_event_notification(session_manager: DBManager) -> None:
    user, uid = await _seed_user_prefs_templates(session_manager)
    async with session_manager.session() as session:
        result = await emit(
            session,
            event="PROJECT_REMINDER",
            recipient_id=uid,
            context={"name": "Ada", "deadline": "2026-08-01"},
            cycle_id=None,
            actor=user,
        )
        assert result.status == "SENT"
        assert result.channel == "EMAIL"
        assert result.outbox_id is not None

        row = await session.get(NotificationOutbox, result.outbox_id)
        assert row is not None
        assert row.status == "SENT"
        assert row.channel == "EMAIL"
        assert row.rendered_subject == "Reminder for Ada"
        assert "Ada" in (row.rendered_body or "")
        assert "2026-08-01" in (row.rendered_body or "")


@pytest.mark.asyncio
async def test_US_NOT_01_AC2_channel_fallback(session_manager: DBManager) -> None:
    user, uid = await _seed_user_prefs_templates(session_manager)
    sender = SelectiveFailSender(fail_channels={"EMAIL"})
    async with session_manager.session() as session:
        result = await emit(
            session,
            event="PROJECT_REMINDER",
            recipient_id=uid,
            context={"name": "Ada", "deadline": "soon"},
            sender=sender,
            actor=user,
        )
        assert result.status == "FALLBACK_SENT"
        assert result.channel == "SMS"
        assert result.error  # primary failure logged
        assert [a[0] for a in sender.attempts] == ["EMAIL", "SMS"]

        row = await session.get(NotificationOutbox, result.outbox_id)
        assert row is not None
        assert row.status == "FALLBACK_SENT"
        assert row.channel == "SMS"
        assert row.error


@pytest.mark.asyncio
async def test_US_NOT_01_AC3_opt_out_respected(session_manager: DBManager) -> None:
    user, uid = await _seed_user_prefs_templates(session_manager, opt_out=True)
    async with session_manager.session() as session:
        skipped = await emit(
            session,
            event="PROJECT_REMINDER",
            recipient_id=uid,
            context={"name": "Ada", "deadline": "soon"},
            actor=user,
        )
        assert skipped.status == "SKIPPED"

        essential = await emit(
            session,
            event="RESULT_PUBLISHED",
            recipient_id=uid,
            context={"name": "Ada"},
            actor=user,
        )
        assert essential.status == "SENT"
        assert essential.channel == "EMAIL"

        rows = (
            await session.execute(
                select(NotificationOutbox).where(NotificationOutbox.recipient_id == uid)
            )
        ).scalars().all()
        statuses = {r.event_key: r.status for r in rows}
        assert statuses["PROJECT_REMINDER"] == "SKIPPED"
        assert statuses["RESULT_PUBLISHED"] == "SENT"


@pytest.mark.asyncio
async def test_US_NOT_01_AC4_english_only(session_manager: DBManager) -> None:
    """Recipient language preference is ignored; English template is always used."""
    user, uid = await _seed_user_prefs_templates(session_manager, language="fr")
    async with session_manager.session() as session:
        result = await emit(
            session,
            event="PROJECT_REMINDER",
            recipient_id=uid,
            context={"name": "Ada", "deadline": "tomorrow"},
            actor=user,
        )
        assert result.status == "SENT"
        assert result.language == "en"
        row = await session.get(NotificationOutbox, result.outbox_id)
        assert row is not None
        assert row.rendered_subject == "Reminder for Ada"
        assert "Hello Ada" in (row.rendered_body or "")


@pytest.mark.asyncio
async def test_US_NOT_01_template_missing_and_no_contact(session_manager: DBManager) -> None:
    async with session_manager.session() as session:
        user = User(
            email=f"bare-{uuid.uuid4().hex[:6]}@example.com",
            full_name="Bare",
            hashed_password=get_password_hash("pass-123"),
            role=UserRole.COMPETITOR,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        uid = user.id

    async with session_manager.session() as session:
        with pytest.raises(AppError) as exc:
            await emit(session, event="UNKNOWN_EVENT", recipient_id=uid, context={})
        assert exc.value.code == "NO_CONTACT_CHANNEL"

    async with session_manager.session() as session:
        session.add(
            NotificationPreference(
                user_id=uid,
                preferred_channel="EMAIL",
                fallback_channel=None,
                language="en",
                email="bare@example.com",
                opt_out_non_essential=False,
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()

    async with session_manager.session() as session:
        with pytest.raises(AppError) as exc2:
            await emit(session, event="UNKNOWN_EVENT", recipient_id=uid, context={})
        assert exc2.value.code == "TEMPLATE_MISSING"


def test_render_template_helper() -> None:
    assert render_template("Hi {{name}}", {"name": "Ada"}) == "Hi Ada"
