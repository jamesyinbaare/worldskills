"""Persist SMS delivery attempts for competitors and coaches."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SmsDelivery
from app.services.sms.factory import get_sms_provider
from app.services.sms.phone import normalize_msisdn
from app.services.sms.types import SmsDeliveryResult

_MAX_ERROR_LEN = 2000
_MAX_PROVIDER_RESPONSE_LEN = 2000

MESSAGE_TYPE_EXERCISE_AVAILABLE = "EXERCISE_AVAILABLE"
MESSAGE_TYPE_SUBMISSION_RECEIVED = "SUBMISSION_RECEIVED"
MESSAGE_TYPE_SKILL_BROADCAST = "SKILL_BROADCAST"
MESSAGE_TYPE_REGISTRATION_CONFIRMATION = "REGISTRATION_CONFIRMATION"

RECIPIENT_COMPETITOR = "competitor"
RECIPIENT_COACH = "coach"


def _truncate(text: str | None, max_len: int) -> str | None:
    if text is None:
        return None
    s = text.strip()
    if not s:
        return None
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


async def create_delivery_log(
    session: AsyncSession,
    *,
    recipient_role: str,
    phone_number: str,
    msisdn: str,
    message_type: str,
    trigger: str,
    status: str,
    competitor_id: UUID | None = None,
    user_id: UUID | None = None,
    competition_id: UUID | None = None,
    stage_id: UUID | None = None,
    submission_id: UUID | None = None,
    triggered_by_user_id: UUID | None = None,
    retried_from_id: UUID | None = None,
    dedupe_key: str | None = None,
    error_message: str | None = None,
    provider_response: str | None = None,
) -> SmsDelivery:
    row = SmsDelivery(
        competitor_id=competitor_id,
        user_id=user_id,
        competition_id=competition_id,
        stage_id=stage_id,
        submission_id=submission_id,
        recipient_role=recipient_role,
        phone_number=phone_number,
        msisdn=msisdn,
        message_type=message_type,
        trigger=trigger,
        status=status,
        error_message=_truncate(error_message, _MAX_ERROR_LEN),
        provider="nalo",
        provider_response=_truncate(provider_response, _MAX_PROVIDER_RESPONSE_LEN),
        dedupe_key=dedupe_key,
        retried_from_id=retried_from_id,
        triggered_by_user_id=triggered_by_user_id,
        sent_at=datetime.utcnow() if status == "sent" else None,
    )
    session.add(row)
    await session.flush()
    return row


async def mark_delivery_sent(
    session: AsyncSession,
    delivery_id: UUID,
    *,
    provider_response: str | None = None,
) -> None:
    row = await session.get(SmsDelivery, delivery_id)
    if row is None:
        return
    row.status = "sent"
    row.sent_at = datetime.utcnow()
    row.error_message = None
    if provider_response is not None:
        row.provider_response = _truncate(provider_response, _MAX_PROVIDER_RESPONSE_LEN)
    await session.flush()


async def mark_delivery_failed(
    session: AsyncSession,
    delivery_id: UUID,
    *,
    error: str,
    provider_response: str | None = None,
) -> None:
    row = await session.get(SmsDelivery, delivery_id)
    if row is None:
        return
    row.status = "failed"
    row.error_message = _truncate(error, _MAX_ERROR_LEN)
    if provider_response is not None:
        row.provider_response = _truncate(provider_response, _MAX_PROVIDER_RESPONSE_LEN)
    await session.flush()


async def has_successful_dedupe(session: AsyncSession, dedupe_key: str) -> bool:
    prior = (
        await session.execute(
            select(SmsDelivery.id).where(
                SmsDelivery.dedupe_key == dedupe_key,
                SmsDelivery.status == "sent",
            ).limit(1)
        )
    ).scalar_one_or_none()
    return prior is not None


async def send_and_log_sms(
    session: AsyncSession,
    *,
    phone: str,
    message: str,
    message_type: str,
    trigger: str,
    recipient_role: str,
    competitor_id: UUID | None = None,
    user_id: UUID | None = None,
    competition_id: UUID | None = None,
    stage_id: UUID | None = None,
    submission_id: UUID | None = None,
    triggered_by_user_id: UUID | None = None,
    dedupe_key: str | None = None,
) -> tuple[SmsDeliveryResult, UUID | None]:
    """Normalize, optionally dedupe, send via provider, and persist delivery log."""
    if dedupe_key and await has_successful_dedupe(session, dedupe_key):
        return SmsDeliveryResult(sent=True, error="deduped"), None

    phone_raw = (phone or "").strip()
    try:
        msisdn = normalize_msisdn(phone_raw) if phone_raw else ""
    except ValueError as exc:
        row = await create_delivery_log(
            session,
            competitor_id=competitor_id,
            user_id=user_id,
            competition_id=competition_id,
            stage_id=stage_id,
            submission_id=submission_id,
            recipient_role=recipient_role,
            phone_number=phone_raw,
            msisdn="",
            message_type=message_type,
            trigger=trigger,
            status="failed",
            triggered_by_user_id=triggered_by_user_id,
            dedupe_key=dedupe_key,
            error_message=str(exc),
        )
        return SmsDeliveryResult(sent=False, error=str(exc)), row.id

    if not msisdn:
        row = await create_delivery_log(
            session,
            competitor_id=competitor_id,
            user_id=user_id,
            competition_id=competition_id,
            stage_id=stage_id,
            submission_id=submission_id,
            recipient_role=recipient_role,
            phone_number=phone_raw,
            msisdn="",
            message_type=message_type,
            trigger=trigger,
            status="failed",
            triggered_by_user_id=triggered_by_user_id,
            dedupe_key=dedupe_key,
            error_message="No phone number",
        )
        return SmsDeliveryResult(sent=False, error="No phone number"), row.id

    pending = await create_delivery_log(
        session,
        competitor_id=competitor_id,
        user_id=user_id,
        competition_id=competition_id,
        stage_id=stage_id,
        submission_id=submission_id,
        recipient_role=recipient_role,
        phone_number=phone_raw,
        msisdn=msisdn,
        message_type=message_type,
        trigger=trigger,
        status="pending",
        triggered_by_user_id=triggered_by_user_id,
        dedupe_key=dedupe_key,
    )
    await session.flush()

    result = await get_sms_provider().send_sms(msisdn, message)
    if result.sent:
        await mark_delivery_sent(session, pending.id)
    else:
        await mark_delivery_failed(session, pending.id, error=result.error or "SMS failed")
    return result, pending.id
