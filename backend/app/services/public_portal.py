"""US-PUB-01 — public competitor directory and privacy-controlled profiles."""

from __future__ import annotations

import base64
import time
import uuid
from threading import Lock
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import (
    Competitor,
    Cycle,
    Institution,
    PublicPortalConfig,
    Skill,
    Zone,
)
from app.schemas.public_portal import (
    PublicCompetitorDirectoryOut,
    PublicCompetitorListItem,
    PublicCompetitorProfileOut,
)
from app.services.consent import is_public_profile_visible

# Hard deny-list — never serialised regardless of cycle config (US-PUB-01-AC3)
_SENSITIVE_FIELD_KEYS = frozenset(
    {
        "dateOfBirth",
        "date_of_birth",
        "dob",
        "nationalId",
        "national_id",
        "passport",
        "email",
        "mobile",
        "whatsapp",
        "phone",
        "contacts",
        "guardianName",
        "guardianEmail",
        "guardianPhone",
        "guardian_name",
        "guardian_email",
        "guardian_phone",
        "registrationPayload",
        "registration_payload",
        "coach",
    }
)

_SAFE_PUBLIC_FIELDS = frozenset(
    {"displayName", "photo", "institution", "skill", "stageStatus", "zone", "competitorRef"}
)

# In-process rate buckets: (client_key, minute_epoch) → count
_rate_buckets: dict[tuple[str, int], int] = {}
_rate_lock = Lock()


def reset_rate_limits() -> None:
    """Test helper — clear in-memory rate buckets."""
    with _rate_lock:
        _rate_buckets.clear()


def _minute_bucket() -> int:
    return int(time.time() // 60)


def _check_rate_limit(client_key: str, limit: int) -> None:
    if limit < 1:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Public portal rate limit is not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("rateLimitPerMinute", "CONFIG_INCOMPLETE")],
        )
    minute = _minute_bucket()
    key = (client_key, minute)
    with _rate_lock:
        # Drop old buckets opportunistically
        stale = [k for k in _rate_buckets if k[1] < minute - 1]
        for k in stale:
            del _rate_buckets[k]
        count = _rate_buckets.get(key, 0) + 1
        _rate_buckets[key] = count
        if count > limit:
            raise AppError(
                "RATE_LIMITED",
                "Public portal request volume exceeded",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                fields=[FieldError("rate", "RATE_LIMITED")],
            )


async def load_portal_config(session: AsyncSession, cycle_id: uuid.UUID) -> PublicPortalConfig:
    cfg = (
        await session.execute(select(PublicPortalConfig).where(PublicPortalConfig.cycle_id == cycle_id))
    ).scalar_one_or_none()
    if cfg is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Public portal configuration is not set for this cycle",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("publicPortalConfig", "CONFIG_INCOMPLETE")],
        )
    if not cfg.public_fields:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Public field set is not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("publicFields", "CONFIG_INCOMPLETE")],
        )
    # Strip any mistakenly configured sensitive keys
    cleaned = [f for f in cfg.public_fields if f in _SAFE_PUBLIC_FIELDS and f not in _SENSITIVE_FIELD_KEYS]
    if not cleaned:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "No valid public fields configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("publicFields", "CONFIG_INCOMPLETE")],
        )
    cfg.public_fields = cleaned
    return cfg


def _display_name(competitor: Competitor) -> str | None:
    parts = [p for p in [competitor.given_names, competitor.family_name] if p]
    return " ".join(parts) if parts else None


def _encode_cursor(competitor_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(str(competitor_id).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> uuid.UUID | None:
    if not cursor:
        return None
    try:
        pad = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + pad).decode()
        return uuid.UUID(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(
            "INVALID_CURSOR",
            "Pagination cursor is invalid",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("cursor", "INVALID_CURSOR")],
        ) from exc


def _refuse_bulk_export(*, limit: int | None, max_page_size: int, fmt: str | None) -> None:
    if fmt and fmt.lower() in {"csv", "xlsx", "jsonl", "export", "bulk"}:
        raise AppError(
            "EXPORT_REFUSED",
            "Bulk personal export is not permitted on the public portal",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            fields=[FieldError("format", "EXPORT_REFUSED")],
        )
    if limit is not None and limit > max_page_size:
        raise AppError(
            "EXPORT_REFUSED",
            "Requested page size exceeds the public portal maximum",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            fields=[FieldError("limit", "EXPORT_REFUSED")],
        )


async def _resolve_names(
    session: AsyncSession, competitors: list[Competitor]
) -> dict[str, dict[uuid.UUID, str]]:
    skill_ids = {c.skill_id for c in competitors if c.skill_id}
    zone_ids = {c.zone_id for c in competitors if c.zone_id}
    inst_ids = {c.institution_id for c in competitors if c.institution_id}

    skills: dict[uuid.UUID, str] = {}
    if skill_ids:
        rows = (await session.execute(select(Skill).where(Skill.id.in_(skill_ids)))).scalars().all()
        skills = {r.id: r.name for r in rows}
    zones: dict[uuid.UUID, str] = {}
    if zone_ids:
        rows = (await session.execute(select(Zone).where(Zone.id.in_(zone_ids)))).scalars().all()
        zones = {r.id: r.name for r in rows}
    institutions: dict[uuid.UUID, str] = {}
    if inst_ids:
        rows = (
            await session.execute(select(Institution).where(Institution.id.in_(inst_ids)))
        ).scalars().all()
        institutions = {r.id: r.name for r in rows}
    return {"skill": skills, "zone": zones, "institution": institutions}


def _project_public_fields(
    competitor: Competitor,
    *,
    allowed: list[str],
    names: dict[str, dict[uuid.UUID, str]],
) -> dict[str, Any]:
    full: dict[str, Any] = {
        "displayName": _display_name(competitor),
        "photo": competitor.photo_key,
        "institution": names["institution"].get(competitor.institution_id) if competitor.institution_id else None,
        "skill": names["skill"].get(competitor.skill_id) if competitor.skill_id else None,
        "stageStatus": competitor.status,
        "zone": names["zone"].get(competitor.zone_id) if competitor.zone_id else None,
        "competitorRef": competitor.ref_no,
    }
    out: dict[str, Any] = {}
    for key in allowed:
        if key in _SENSITIVE_FIELD_KEYS:
            continue
        if key in full:
            out[key] = full[key]
    # Never leak keys from competitor.__dict__
    for forbidden in _SENSITIVE_FIELD_KEYS:
        out.pop(forbidden, None)
    return out


async def list_public_competitors(
    session: AsyncSession,
    cycle_id: uuid.UUID,
    *,
    skill_id: uuid.UUID | None = None,
    zone_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    fmt: str | None = None,
    client_key: str = "anonymous",
) -> PublicCompetitorDirectoryOut:
    cycle = await session.get(Cycle, cycle_id)
    if cycle is None:
        raise AppError("CYCLE_NOT_FOUND", "Cycle not found", status_code=404)

    cfg = await load_portal_config(session, cycle_id)
    _refuse_bulk_export(limit=limit, max_page_size=cfg.max_page_size, fmt=fmt)
    _check_rate_limit(f"dir:{cycle_id}:{client_key}", cfg.rate_limit_per_minute)

    page_size = limit if limit is not None else min(20, cfg.max_page_size)
    page_size = min(page_size, cfg.max_page_size)

    after_id = _decode_cursor(cursor)

    stmt = (
        select(Competitor)
        .where(
            Competitor.cycle_id == cycle_id,
            Competitor.public_profile_visible.is_(True),
            Competitor.consent_public_at.is_not(None),
        )
        .order_by(Competitor.id.asc())
        .limit(page_size + 1)
    )
    if skill_id is not None:
        stmt = stmt.where(Competitor.skill_id == skill_id)
    if zone_id is not None:
        stmt = stmt.where(Competitor.zone_id == zone_id)
    if after_id is not None:
        stmt = stmt.where(Competitor.id > after_id)

    rows = list((await session.execute(stmt)).scalars().all())
    # Defence in depth — consent helper
    rows = [c for c in rows if is_public_profile_visible(c)]

    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = _encode_cursor(rows[-1].id)

    names = await _resolve_names(session, rows)
    allowed = list(cfg.public_fields)
    items: list[PublicCompetitorListItem] = []
    for c in rows:
        projected = _project_public_fields(c, allowed=allowed, names=names)
        items.append(
            PublicCompetitorListItem(
                competitorId=c.id,
                displayName=projected.get("displayName"),
                photo=projected.get("photo"),
                institution=projected.get("institution"),
                skill=projected.get("skill"),
                stageStatus=projected.get("stageStatus"),
                zone=projected.get("zone"),
            )
        )

    return PublicCompetitorDirectoryOut(items=items, nextCursor=next_cursor)


async def get_public_competitor_profile(
    session: AsyncSession,
    competitor_key: str,
    *,
    client_key: str = "anonymous",
) -> PublicCompetitorProfileOut:
    """Resolve by UUID or ref_no; 404 for non-public (no oracle)."""
    competitor: Competitor | None = None
    try:
        cid = uuid.UUID(competitor_key)
        competitor = await session.get(Competitor, cid)
    except ValueError:
        competitor = (
            await session.execute(select(Competitor).where(Competitor.ref_no == competitor_key))
        ).scalar_one_or_none()

    # Uniform 404 — do not reveal whether the competitor exists without consent
    if competitor is None or not is_public_profile_visible(competitor):
        raise AppError(
            "PROFILE_NOT_PUBLIC",
            "Competitor profile is not publicly visible",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    cfg = await load_portal_config(session, competitor.cycle_id)
    _check_rate_limit(f"prof:{competitor.cycle_id}:{client_key}", cfg.rate_limit_per_minute)

    names = await _resolve_names(session, [competitor])
    projected = _project_public_fields(competitor, allowed=list(cfg.public_fields), names=names)

    return PublicCompetitorProfileOut(
        competitorId=competitor.id,
        public=True,
        competitorRef=projected.get("competitorRef") or competitor.ref_no,
        displayName=projected.get("displayName"),
        photo=projected.get("photo"),
        institution=projected.get("institution"),
        skill=projected.get("skill"),
        stageStatus=projected.get("stageStatus"),
        zone=projected.get("zone"),
    )
