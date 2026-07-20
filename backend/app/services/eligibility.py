"""Eligibility & age screening (US-ELG-01) — per-skill limits, fail closed, auditable overrides."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import is_admin_role
from app.models import Competitor, Skill, User
from app.schemas.eligibility import EligibilityOverrideIn, EligibilityOverrideOut, ScreenOut
from app.services.audit import write_audit_event
from app.services.config_resolution import ConfigIncompleteError, load_cycle_config
from app.services.consent import compute_age

_RULE_AGE = "AGE_EXCEEDS_LIMIT"


def _now() -> datetime:
    return datetime.utcnow()


async def screen_competitor(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    *,
    actor: User | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    commit: bool = True,
) -> ScreenOut:
    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)
    if competitor.date_of_birth is None:
        raise AppError(
            "VALIDATION_ERROR",
            "Competitor date of birth is required for screening",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("dateOfBirth", "REQUIRED")],
        )

    cfg = await load_cycle_config(session, competitor.cycle_id)
    try:
        age_rule = cfg.age_rule_for_skill(competitor.skill_id)
    except ConfigIncompleteError:
        raise
    if age_rule.reference_date is None:
        raise ConfigIncompleteError(
            "Age rule reference date missing — screening blocked",
            entity=str(competitor.skill_id),
        )

    skill = await session.get(Skill, competitor.skill_id)
    age = compute_age(competitor.date_of_birth, on=age_rule.reference_date)
    failed: list[str] = []

    # Age ≤ max_age is eligible (exact boundary inclusive — DoD)
    if age > age_rule.max_age:
        failed.append(_RULE_AGE)

    rules = (skill.eligibility_rules if skill else None) or {}
    required_nats = rules.get("requireNationality") or []
    if required_nats:
        if not competitor.nationality or competitor.nationality not in required_nats:
            failed.append("ELIGIBILITY_FAILED:nationality")

    if rules.get("requireEnrolmentAttestation"):
        if not competitor.enrolment_attested:
            failed.append("ELIGIBILITY_FAILED:enrolment")

    if not failed:
        competitor.eligibility_status = "ELIGIBLE"
        competitor.eligibility_failed_rules = []
        competitor.eligibility_category = "COMPETITIVE"
        if competitor.status == "INELIGIBLE":
            competitor.status = "PENDING_REVIEW"
        eligible = True
        category = "COMPETITIVE"
    elif _RULE_AGE in failed and age_rule.open_category_enabled:
        other = [r for r in failed if r != _RULE_AGE]
        if other:
            competitor.eligibility_status = "INELIGIBLE"
            competitor.eligibility_failed_rules = failed
            competitor.eligibility_category = None
            competitor.status = "INELIGIBLE"
            eligible = False
            category = None
        else:
            # Over age with open category enabled → demonstration/open, not competitive
            competitor.eligibility_status = "OPEN_CATEGORY"
            competitor.eligibility_failed_rules = [_RULE_AGE]
            competitor.eligibility_category = "OPEN"
            eligible = True
            category = "OPEN"
    else:
        competitor.eligibility_status = "INELIGIBLE"
        competitor.eligibility_failed_rules = failed
        competitor.eligibility_category = None
        competitor.status = "INELIGIBLE"
        eligible = False
        category = None

    await write_audit_event(
        session,
        action="ELIGIBILITY_SCREEN",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor.id if actor else None,
        actor_role=actor.role.value if actor else "SYSTEM",
        cycle_id=competitor.cycle_id,
        after={
            "eligible": eligible,
            "status": competitor.eligibility_status,
            "failedRules": failed,
            "category": category,
            "ageAtReference": age,
        },
        ip=ip,
        user_agent=user_agent,
    )
    if commit:
        await session.commit()
        await session.refresh(competitor)
    else:
        await session.flush()

    return ScreenOut(
        competitorId=competitor.id,
        eligible=eligible,
        status=competitor.eligibility_status or "UNKNOWN",
        failedRules=list(competitor.eligibility_failed_rules or []),
        category=competitor.eligibility_category,
        ageAtReference=age,
    )


async def override_eligibility(
    session: AsyncSession,
    competitor_id: uuid.UUID,
    payload: EligibilityOverrideIn,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> EligibilityOverrideOut:
    if not is_admin_role(actor.role):
        raise AppError("FORBIDDEN", "Admin role required", status_code=403)

    if payload.reason is None or not str(payload.reason).strip():
        raise AppError(
            "REASON_REQUIRED",
            "Override reason is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("reason", "REASON_REQUIRED")],
        )

    competitor = await session.get(Competitor, competitor_id)
    if competitor is None:
        raise AppError("COMPETITOR_NOT_FOUND", "Competitor not found", status_code=404)

    reason = payload.reason.strip()
    before = {
        "eligibility_status": competitor.eligibility_status,
        "category": competitor.eligibility_category,
    }

    if payload.value:
        competitor.eligibility_status = "ELIGIBLE"
        competitor.eligibility_failed_rules = []
        competitor.eligibility_category = (payload.category or "COMPETITIVE").upper()
        if competitor.status == "INELIGIBLE":
            competitor.status = "PENDING_REVIEW"
        eligible = True
    else:
        competitor.eligibility_status = "INELIGIBLE"
        competitor.eligibility_category = None
        competitor.status = "INELIGIBLE"
        if not competitor.eligibility_failed_rules:
            competitor.eligibility_failed_rules = ["OVERRIDE_INELIGIBLE"]
        eligible = False

    competitor.eligibility_override_reason = reason
    competitor.eligibility_override_at = _now()
    competitor.eligibility_override_by = actor.id

    await write_audit_event(
        session,
        action="ELIGIBILITY_OVERRIDE",
        entity_type="Competitor",
        entity_id=str(competitor.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        cycle_id=competitor.cycle_id,
        before=before,
        after={
            "eligible": eligible,
            "status": competitor.eligibility_status,
            "category": competitor.eligibility_category,
            "reason": reason,
        },
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(competitor)

    return EligibilityOverrideOut(
        competitorId=competitor.id,
        eligible=eligible,
        status=competitor.eligibility_status or "UNKNOWN",
        reason=reason,
        category=competitor.eligibility_category,
    )
