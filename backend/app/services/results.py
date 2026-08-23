"""US-RES-01 — prepare / release results under embargo and issue certificates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import Capability, has_capability
from app.models import (
    Certificate,
    CertificateTemplate,
    Competitor,
    Competition,
    ResultEntry,
    ResultPublication,
    ResultsConfig,
    Shortlist,
    ShortlistEntry,
    Skill,
    Stage,
    User,
)
from app.schemas.results import (
    AdminResultItem,
    CertificateTemplateOut,
    CompetitorResultsOut,
    CorrectResultOut,
    PrepareResultsOut,
    PublicResultItem,
    PublicResultsOut,
    ReleaseResultsOut,
    ResultsConfigOut,
    ResultsConfigPut,
)
from app.services.audit import write_audit_event

_DEFAULT_TEMPLATE_BODIES: dict[str, str] = {
    "GOLD": "This certifies that {{name}} achieved Gold (rank {{rank}}, score {{score}}).",
    "SILVER": "This certifies that {{name}} achieved Silver (rank {{rank}}, score {{score}}).",
    "BRONZE": "This certifies that {{name}} achieved Bronze (rank {{rank}}, score {{score}}).",
    "FINALIST": "This certifies that {{name}} is a Finalist (rank {{rank}}, score {{score}}).",
    "ADVANCE": "This certifies that {{name}} advanced (rank {{rank}}, score {{score}}).",
    "WAITLIST": "This certifies that {{name}} is on the waitlist (rank {{rank}}, score {{score}}).",
}


def _render(template: str, context: dict[str, Any]) -> str:
    result = template
    for key, value in context.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def _cycle_local_now(cycle: Competition, *, now: datetime | None = None) -> datetime:
    """Wall-clock 'now' in the competition's IANA time zone (naive, for comparison with stored release_at)."""
    tz = ZoneInfo(cycle.time_zone)
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(tz).replace(tzinfo=None)


def _embargo_due(cycle: Competition, release_at: datetime, *, now: datetime | None = None) -> bool:
    return _cycle_local_now(cycle, now=now) >= release_at


async def _require_publish(actor: User) -> None:
    if not has_capability(actor.role, Capability.PUBLISH_RESULTS):
        raise AppError(
            "NOT_AUTHORISED",
            "Admin required to publish results",
            status_code=status.HTTP_403_FORBIDDEN,
            fields=[FieldError("role", "NOT_AUTHORISED")],
        )


async def _load_results_config(session: AsyncSession, competition_id: uuid.UUID) -> ResultsConfig:
    cfg = (
        await session.execute(select(ResultsConfig).where(ResultsConfig.competition_id == competition_id))
    ).scalar_one_or_none()
    if cfg is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Results embargo / audience config is missing",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("resultsConfig", "CONFIG_INCOMPLETE")],
        )
    if not cfg.audience:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Results audience is not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("audience", "CONFIG_INCOMPLETE")],
        )
    if cfg.release_at is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Results releaseAt is not configured",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("releaseAt", "CONFIG_INCOMPLETE")],
        )
    return cfg


def _config_to_out(competition_id: uuid.UUID, cfg: ResultsConfig | None) -> ResultsConfigOut:
    if cfg is None:
        return ResultsConfigOut(
            competitionId=competition_id,
            releaseAt=datetime.utcnow(),
            audience=["PUBLIC", "COMPETITOR"],
            neutralStatus="IN_PROGRESS",
            awardByRank={"1": "GOLD", "2": "SILVER", "3": "BRONZE"},
            defaultOutcome="FINALIST",
            configured=False,
        )
    return ResultsConfigOut(
        competitionId=competition_id,
        releaseAt=cfg.release_at,
        audience=list(cfg.audience or []),
        neutralStatus=cfg.neutral_status or "IN_PROGRESS",
        awardByRank={str(k): str(v) for k, v in (cfg.award_by_rank or {}).items()},
        defaultOutcome=cfg.default_outcome or "FINALIST",
        configured=True,
    )


async def get_results_config(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
) -> ResultsConfigOut:
    await _require_publish(actor)
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)
    cfg = (
        await session.execute(select(ResultsConfig).where(ResultsConfig.competition_id == competition_id))
    ).scalar_one_or_none()
    return _config_to_out(competition_id, cfg)


async def _ensure_certificate_templates(
    session: AsyncSession,
    competition_id: uuid.UUID,
    outcomes: set[str],
) -> None:
    existing = (
        await session.execute(
            select(CertificateTemplate).where(CertificateTemplate.competition_id == competition_id)
        )
    ).scalars().all()
    have = {t.outcome.upper() for t in existing}
    for outcome in outcomes:
        code = outcome.upper()
        if code in have:
            continue
        body = _DEFAULT_TEMPLATE_BODIES.get(
            code,
            f"This certifies that {{{{name}}}} achieved {code} (rank {{{{rank}}}}, score {{{{score}}}}).",
        )
        session.add(
            CertificateTemplate(
                competition_id=competition_id,
                outcome=code,
                language="en",
                body=body,
            )
        )
        have.add(code)


async def put_results_config(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: ResultsConfigPut,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ResultsConfigOut:
    await _require_publish(actor)
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)

    release_at = payload.releaseAt
    if release_at.tzinfo is not None:
        release_at = release_at.replace(tzinfo=None)

    cfg = (
        await session.execute(select(ResultsConfig).where(ResultsConfig.competition_id == competition_id))
    ).scalar_one_or_none()
    before = None
    if cfg is None:
        cfg = ResultsConfig(competition_id=competition_id)
        session.add(cfg)
    else:
        before = {
            "releaseAt": cfg.release_at.isoformat() if cfg.release_at else None,
            "audience": list(cfg.audience or []),
            "neutralStatus": cfg.neutral_status,
            "awardByRank": dict(cfg.award_by_rank or {}),
            "defaultOutcome": cfg.default_outcome,
        }

    cfg.release_at = release_at
    cfg.audience = list(payload.audience)
    cfg.neutral_status = payload.neutralStatus
    cfg.award_by_rank = dict(payload.awardByRank)
    cfg.default_outcome = payload.defaultOutcome

    if payload.ensureTemplates:
        outcomes = set(payload.awardByRank.values()) | {
            payload.defaultOutcome,
            "ADVANCE",
            "WAITLIST",
            "GOLD",
            "SILVER",
            "BRONZE",
            "FINALIST",
        }
        await _ensure_certificate_templates(session, competition_id, outcomes)

    await write_audit_event(
        session,
        action="RESULTS_CONFIG_UPSERT",
        entity_type="ResultsConfig",
        entity_id=str(competition_id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after={
            "releaseAt": cfg.release_at.isoformat(),
            "audience": list(cfg.audience),
            "neutralStatus": cfg.neutral_status,
            "awardByRank": dict(cfg.award_by_rank or {}),
            "defaultOutcome": cfg.default_outcome,
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(cfg)
    return _config_to_out(competition_id, cfg)


async def list_certificate_templates(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
) -> list[CertificateTemplateOut]:
    await _require_publish(actor)
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)
    rows = (
        await session.execute(
            select(CertificateTemplate)
            .where(CertificateTemplate.competition_id == competition_id)
            .order_by(CertificateTemplate.outcome.asc())
        )
    ).scalars().all()
    return [
        CertificateTemplateOut(
            templateId=t.id,
            competitionId=t.competition_id,
            outcome=t.outcome,
            language=t.language,
            body=t.body,
        )
        for t in rows
    ]


async def _template_for(
    session: AsyncSession, competition_id: uuid.UUID, outcome: str
) -> CertificateTemplate:
    tmpl = (
        await session.execute(
            select(CertificateTemplate).where(
                CertificateTemplate.competition_id == competition_id,
                CertificateTemplate.outcome == outcome,
            )
        )
    ).scalars().first()
    if tmpl is None:
        raise AppError(
            "TEMPLATE_MISSING",
            f"Certificate template missing for outcome {outcome}",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("certificateTemplate", "TEMPLATE_MISSING")],
        )
    return tmpl


def _outcome_for_rank(cfg: ResultsConfig, rank: int) -> str:
    mapping = {str(k): str(v) for k, v in (cfg.award_by_rank or {}).items()}
    return mapping.get(str(rank), cfg.default_outcome or "FINALIST")


async def _advancers_from_confirmed_finals(
    session: AsyncSession,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID | None,
) -> list[tuple[ShortlistEntry, Shortlist]]:
    stmt = (
        select(ShortlistEntry, Shortlist)
        .join(Shortlist, ShortlistEntry.shortlist_id == Shortlist.id)
        .where(
            Shortlist.competition_id == competition_id,
            Shortlist.state == "CONFIRMED",
            Shortlist.is_final_stage.is_(True),
            ShortlistEntry.outcome == "ADVANCE",
        )
    )
    if skill_id is not None:
        stmt = stmt.where(Shortlist.skill_id == skill_id)

    rows = (await session.execute(stmt)).all()
    return [(entry, shortlist) for entry, shortlist in rows]


async def _entries_from_confirmed_stage(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
) -> tuple[Stage, Shortlist, list[ShortlistEntry]]:
    stage = await session.get(Stage, stage_id)
    if stage is None or stage.competition_id != competition_id:
        raise AppError(
            "STAGE_NOT_FOUND",
            "Stage not found for this competition",
            status_code=404,
            fields=[FieldError("stageId", "NOT_FOUND")],
        )

    shortlist = (
        await session.execute(
            select(Shortlist).where(
                Shortlist.competition_id == competition_id,
                Shortlist.stage_id == stage_id,
                Shortlist.state == "CONFIRMED",
            )
        )
    ).scalars().first()
    if shortlist is None:
        raise AppError(
            "SCORING_INCOMPLETE",
            "No confirmed shortlist for this stage — confirm the shortlist before preparing results",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("shortlist", "SCORING_INCOMPLETE")],
        )

    entries = (
        await session.execute(
            select(ShortlistEntry)
            .where(
                ShortlistEntry.shortlist_id == shortlist.id,
                ShortlistEntry.outcome.in_(("ADVANCE", "WAITLIST")),
            )
            .order_by(ShortlistEntry.rank.asc().nullslast())
        )
    ).scalars().all()
    if not entries:
        raise AppError(
            "SCORING_INCOMPLETE",
            "Confirmed shortlist has no ADVANCE or WAITLIST entries to publish",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("shortlist", "SCORING_INCOMPLETE")],
        )
    return stage, shortlist, list(entries)


async def prepare_results(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
    skill_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> PrepareResultsOut:
    await _require_publish(actor)
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)

    cfg = await _load_results_config(session, competition_id)

    planned: list[tuple[ShortlistEntry, uuid.UUID, str]] = []
    publication_skill_id = skill_id
    publication_stage_id = stage_id

    if stage_id is not None:
        stage, shortlist, entries = await _entries_from_confirmed_stage(
            session, competition_id, stage_id
        )
        publication_skill_id = stage.skill_id or shortlist.skill_id
        if skill_id is not None and publication_skill_id != skill_id:
            raise AppError(
                "VALIDATION_ERROR",
                "Selected stage does not belong to the selected skill",
                status_code=422,
                fields=[FieldError("stageId", "SKILL_MISMATCH")],
            )
        for entry in entries:
            if shortlist.is_final_stage and entry.outcome == "ADVANCE":
                outcome = _outcome_for_rank(cfg, entry.rank)
            elif entry.outcome == "ADVANCE":
                outcome = "ADVANCE"
            else:
                outcome = entry.outcome
            sid = publication_skill_id
            if sid is None:
                raise AppError(
                    "CONFIG_INCOMPLETE",
                    "Stage skill is missing",
                    status_code=409,
                    fields=[FieldError("skillId", "CONFIG_INCOMPLETE")],
                )
            await _template_for(session, competition_id, outcome)
            planned.append((entry, sid, outcome))
    else:
        rows = await _advancers_from_confirmed_finals(session, competition_id, skill_id)
        if not rows:
            raise AppError(
                "SCORING_INCOMPLETE",
                "No confirmed finalist shortlist entries to publish",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("shortlist", "SCORING_INCOMPLETE")],
            )
        for entry, shortlist in rows:
            outcome = _outcome_for_rank(cfg, entry.rank)
            await _template_for(session, competition_id, outcome)
            sid = shortlist.skill_id
            if sid is None:
                raise AppError(
                    "CONFIG_INCOMPLETE",
                    "Shortlist skill is missing",
                    status_code=409,
                    fields=[FieldError("skillId", "CONFIG_INCOMPLETE")],
                )
            planned.append((entry, sid, outcome))

    # Replace existing embargoed publication for same scope
    existing_q = select(ResultPublication).where(
        ResultPublication.competition_id == competition_id,
        ResultPublication.state == "EMBARGOED",
    )
    if publication_stage_id is not None:
        existing_q = existing_q.where(ResultPublication.stage_id == publication_stage_id)
    else:
        existing_q = existing_q.where(ResultPublication.stage_id.is_(None))
        if publication_skill_id is None:
            existing_q = existing_q.where(ResultPublication.skill_id.is_(None))
        else:
            existing_q = existing_q.where(ResultPublication.skill_id == publication_skill_id)
    existing = (await session.execute(existing_q)).scalars().all()
    for pub in existing:
        await session.delete(pub)
    await session.flush()

    publication = ResultPublication(
        competition_id=competition_id,
        skill_id=publication_skill_id,
        stage_id=publication_stage_id,
        state="EMBARGOED",
        release_at=cfg.release_at,
        audience=list(cfg.audience),
        neutral_status=cfg.neutral_status or "IN_PROGRESS",
        prepared_at=datetime.utcnow(),
        prepared_by=actor.id,
    )
    session.add(publication)
    await session.flush()

    for entry, sid, outcome in planned:
        session.add(
            ResultEntry(
                publication_id=publication.id,
                competition_id=competition_id,
                skill_id=sid,
                competitor_id=entry.competitor_id,
                outcome=outcome,
                score=entry.score,
                rank=entry.rank,
                version=1,
                is_current=True,
                payload={
                    "zoneId": str(entry.zone_id),
                    "stageId": str(publication_stage_id) if publication_stage_id else None,
                },
            )
        )

    await write_audit_event(
        session,
        action="RESULTS_PREPARE",
        entity_type="ResultPublication",
        entity_id=str(publication.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after={
            "state": "EMBARGOED",
            "skillId": str(publication_skill_id) if publication_skill_id else None,
            "stageId": str(publication_stage_id) if publication_stage_id else None,
            "entryCount": len(planned),
            "releaseAt": cfg.release_at.isoformat(),
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(publication)

    return PrepareResultsOut(
        publicationId=publication.id,
        state=publication.state,
        skillId=publication_skill_id,
        stageId=publication_stage_id,
        entryCount=len(planned),
        releaseAt=publication.release_at,
    )


async def _find_publication(
    session: AsyncSession,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID | None,
    *,
    stage_id: uuid.UUID | None = None,
    state: str | None = "EMBARGOED",
) -> ResultPublication:
    q = select(ResultPublication).where(ResultPublication.competition_id == competition_id)
    if state:
        q = q.where(ResultPublication.state == state)
    if stage_id is not None:
        q = q.where(ResultPublication.stage_id == stage_id)
    else:
        q = q.where(ResultPublication.stage_id.is_(None))
        if skill_id is None:
            q = q.where(ResultPublication.skill_id.is_(None))
        else:
            q = q.where(ResultPublication.skill_id == skill_id)
    q = q.order_by(ResultPublication.prepared_at.desc())
    pub = (await session.execute(q)).scalars().first()
    if pub is None:
        if stage_id is not None:
            raise AppError(
                "RESULTS_NOT_PREPARED",
                "No prepared results for this stage",
                status_code=409,
                fields=[FieldError("stageId", "RESULTS_NOT_PREPARED")],
            )
        if skill_id is not None and state == "EMBARGOED":
            raise AppError(
                "RESULTS_NOT_PREPARED",
                "No prepared results for this skill",
                status_code=409,
                fields=[FieldError("skillId", "RESULTS_NOT_PREPARED")],
            )
        raise AppError(
            "RESULTS_NOT_PREPARED",
            "No prepared results to release",
            status_code=409,
            fields=[FieldError("competitionId", "RESULTS_NOT_PREPARED")],
        )
    return pub


async def _issue_certificate(
    session: AsyncSession,
    *,
    publication: ResultPublication,
    entry: ResultEntry,
    competitor: Competitor | None,
    version: int = 1,
    supersedes_id: uuid.UUID | None = None,
) -> Certificate:
    tmpl = await _template_for(session, entry.competition_id, entry.outcome)
    name = " ".join(
        p for p in [(competitor.given_names if competitor else None), (competitor.family_name if competitor else None)] if p
    ) or (competitor.ref_no if competitor else str(entry.competitor_id))
    body = _render(
        tmpl.body,
        {
            "name": name,
            "outcome": entry.outcome,
            "rank": entry.rank or "",
            "score": entry.score if entry.score is not None else "",
            "refNo": competitor.ref_no if competitor else "",
        },
    )
    cert = Certificate(
        competition_id=entry.competition_id,
        publication_id=publication.id,
        result_entry_id=entry.id,
        competitor_id=entry.competitor_id,
        outcome=entry.outcome,
        rendered_body=body,
        version=version,
        is_current=True,
        supersedes_id=supersedes_id,
        issued_at=datetime.utcnow(),
    )
    session.add(cert)
    await session.flush()
    return cert


async def release_results(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
    manual: bool = False,
    skill_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> ReleaseResultsOut:
    await _require_publish(actor)
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)

    publication = await _find_publication(
        session,
        competition_id,
        skill_id,
        stage_id=stage_id,
        state="EMBARGOED",
    )

    if not manual and not _embargo_due(cycle, publication.release_at, now=now):
        raise AppError(
            "EMBARGO_ACTIVE",
            "Embargo has not lifted; wait for releaseAt or use manual release",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("embargo", "EMBARGO_ACTIVE")],
        )

    entries = (
        await session.execute(
            select(ResultEntry).where(
                ResultEntry.publication_id == publication.id,
                ResultEntry.is_current.is_(True),
            )
        )
    ).scalars().all()

    cert_count = 0
    for entry in entries:
        await _template_for(session, competition_id, entry.outcome)
        competitor = await session.get(Competitor, entry.competitor_id)
        await _issue_certificate(session, publication=publication, entry=entry, competitor=competitor)
        cert_count += 1

    released_at = datetime.utcnow()
    before = {"state": publication.state}
    publication.state = "RELEASED"
    publication.released_at = released_at
    publication.released_by = actor.id

    await write_audit_event(
        session,
        action="RESULTS_RELEASE",
        entity_type="ResultPublication",
        entity_id=str(publication.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after={
            "state": "RELEASED",
            "releasedAt": released_at.isoformat(),
            "manual": manual,
            "certificateCount": cert_count,
            "audience": publication.audience,
            "stageId": str(publication.stage_id) if publication.stage_id else None,
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(publication)

    return ReleaseResultsOut(
        publicationId=publication.id,
        releasedAt=released_at,
        state="RELEASED",
        certificateCount=cert_count,
    )


async def correct_result(
    session: AsyncSession,
    result_id: uuid.UUID,
    *,
    changes: dict[str, Any],
    reason: str,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> CorrectResultOut:
    await _require_publish(actor)
    if not reason or not str(reason).strip():
        raise AppError(
            "VALIDATION_ERROR",
            "Correction reason is required",
            status_code=422,
            fields=[FieldError("reason", "REQUIRED")],
        )

    old = await session.get(ResultEntry, result_id)
    if old is None or not old.is_current:
        raise AppError("RESULT_NOT_FOUND", "Current result not found", status_code=404)

    publication = await session.get(ResultPublication, old.publication_id)
    if publication is None:
        raise AppError("RESULTS_NOT_PREPARED", "Publication missing", status_code=409)
    if publication.state != "RELEASED":
        raise AppError(
            "EMBARGO_ACTIVE",
            "Corrections apply to released results",
            status_code=409,
            fields=[FieldError("state", "EMBARGO_ACTIVE")],
        )

    new_outcome = str(changes.get("outcome", old.outcome))
    new_score = changes.get("score", old.score)
    new_rank = changes.get("rank", old.rank)
    if new_score is not None:
        new_score = int(new_score)
    if new_rank is not None:
        new_rank = int(new_rank)

    await _template_for(session, old.competition_id, new_outcome)

    old.is_current = False
    new_entry = ResultEntry(
        publication_id=old.publication_id,
        competition_id=old.competition_id,
        skill_id=old.skill_id,
        competitor_id=old.competitor_id,
        outcome=new_outcome,
        score=new_score,
        rank=new_rank,
        version=old.version + 1,
        is_current=True,
        supersedes_id=old.id,
        payload=dict(old.payload or {}),
    )
    session.add(new_entry)
    await session.flush()

    old_certs = (
        await session.execute(
            select(Certificate).where(
                Certificate.competitor_id == old.competitor_id,
                Certificate.publication_id == publication.id,
                Certificate.is_current.is_(True),
            )
        )
    ).scalars().all()
    old_cert_id = old_certs[0].id if old_certs else None
    for c in old_certs:
        c.is_current = False

    competitor = await session.get(Competitor, old.competitor_id)
    cert = await _issue_certificate(
        session,
        publication=publication,
        entry=new_entry,
        competitor=competitor,
        version=new_entry.version,
        supersedes_id=old_cert_id,
    )

    await write_audit_event(
        session,
        action="RESULTS_CORRECT",
        entity_type="ResultEntry",
        entity_id=str(new_entry.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=old.competition_id,
        before={
            "resultId": str(old.id),
            "outcome": old.outcome,
            "score": old.score,
            "rank": old.rank,
            "version": old.version,
        },
        after={
            "resultId": str(new_entry.id),
            "outcome": new_entry.outcome,
            "score": new_entry.score,
            "rank": new_entry.rank,
            "version": new_entry.version,
            "changes": changes,
        },
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()

    return CorrectResultOut(
        resultId=new_entry.id,
        version=new_entry.version,
        publicationId=publication.id,
        outcome=new_entry.outcome,
        certificateId=cert.id,
    )


def _audience_allows_public(audience: list | None) -> bool:
    return "PUBLIC" in (audience or [])


def _audience_allows_competitor(audience: list | None) -> bool:
    return "COMPETITOR" in (audience or []) or "PUBLIC" in (audience or [])


async def get_public_results(
    session: AsyncSession,
    competition_id: uuid.UUID,
) -> PublicResultsOut:
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)

    publications = (
        await session.execute(
            select(ResultPublication).where(ResultPublication.competition_id == competition_id)
        )
    ).scalars().all()

    if not publications:
        cfg = (
            await session.execute(select(ResultsConfig).where(ResultsConfig.competition_id == competition_id))
        ).scalar_one_or_none()
        return PublicResultsOut(
            state="EMBARGOED",
            status=(cfg.neutral_status if cfg else "IN_PROGRESS"),
            results=[],
        )

    released = [p for p in publications if p.state == "RELEASED"]
    if not released:
        neutral = publications[0].neutral_status or "IN_PROGRESS"
        return PublicResultsOut(state="EMBARGOED", status=neutral, results=[])

    visible_pubs = [p for p in released if _audience_allows_public(p.audience)]
    if not visible_pubs:
        neutral = released[0].neutral_status or "IN_PROGRESS"
        return PublicResultsOut(state="EMBARGOED", status=neutral, results=[])

    items: list[PublicResultItem] = []
    for pub in visible_pubs:
        entries = (
            await session.execute(
                select(ResultEntry).where(
                    ResultEntry.publication_id == pub.id,
                    ResultEntry.is_current.is_(True),
                )
            )
        ).scalars().all()
        for entry in entries:
            cert = (
                await session.execute(
                    select(Certificate).where(
                        Certificate.result_entry_id == entry.id,
                        Certificate.is_current.is_(True),
                    )
                )
            ).scalars().first()
            competitor = await session.get(Competitor, entry.competitor_id)
            items.append(
                PublicResultItem(
                    resultId=entry.id,
                    competitorId=entry.competitor_id,
                    skillId=entry.skill_id,
                    outcome=entry.outcome,
                    score=entry.score,
                    rank=entry.rank,
                    certificateId=cert.id if cert else None,
                    refNo=competitor.ref_no if competitor else None,
                )
            )

    latest_release = max((p.released_at for p in visible_pubs if p.released_at), default=None)
    return PublicResultsOut(
        state="RELEASED",
        status=None,
        releasedAt=latest_release,
        results=items,
    )


async def get_competitor_results(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
) -> CompetitorResultsOut:
    competitor = (
        await session.execute(
            select(Competitor).where(
                Competitor.competition_id == competition_id,
                Competitor.user_id == actor.id,
            )
        )
    ).scalar_one_or_none()
    if competitor is None:
        raise AppError(
            "COMPETITOR_NOT_FOUND",
            "No competitor profile linked to this account for the competition",
            status_code=404,
        )

    publications = (
        await session.execute(
            select(ResultPublication).where(ResultPublication.competition_id == competition_id)
        )
    ).scalars().all()
    relevant = [
        p
        for p in publications
        if p.skill_id is None or p.skill_id == competitor.skill_id
    ]

    if not relevant or all(p.state != "RELEASED" for p in relevant):
        neutral = relevant[0].neutral_status if relevant else "IN_PROGRESS"
        if not relevant:
            cfg = (
                await session.execute(
                    select(ResultsConfig).where(ResultsConfig.competition_id == competition_id)
                )
            ).scalar_one_or_none()
            neutral = cfg.neutral_status if cfg else "IN_PROGRESS"
        return CompetitorResultsOut(state="EMBARGOED", status=neutral, result=None, certificate=None)

    released = [p for p in relevant if p.state == "RELEASED"]
    pub = next((p for p in released if _audience_allows_competitor(p.audience)), None)
    if pub is None:
        return CompetitorResultsOut(
            state="EMBARGOED",
            status=released[0].neutral_status if released else "IN_PROGRESS",
            result=None,
            certificate=None,
        )

    entry = (
        await session.execute(
            select(ResultEntry).where(
                ResultEntry.publication_id == pub.id,
                ResultEntry.competitor_id == competitor.id,
                ResultEntry.is_current.is_(True),
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        return CompetitorResultsOut(state="RELEASED", status=None, result=None, certificate=None)

    cert = (
        await session.execute(
            select(Certificate).where(
                Certificate.result_entry_id == entry.id,
                Certificate.is_current.is_(True),
            )
        )
    ).scalars().first()

    return CompetitorResultsOut(
        state="RELEASED",
        status=None,
        result=PublicResultItem(
            resultId=entry.id,
            competitorId=entry.competitor_id,
            skillId=entry.skill_id,
            outcome=entry.outcome,
            score=entry.score,
            rank=entry.rank,
            certificateId=cert.id if cert else None,
            refNo=competitor.ref_no,
        ),
        certificate=cert.rendered_body if cert else None,
    )


def _competitor_display_name(competitor: Competitor | None) -> str | None:
    if competitor is None:
        return None
    parts = [p for p in (competitor.given_names, competitor.family_name) if p]
    return " ".join(parts) if parts else None


async def list_admin_results(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
    skill_id: uuid.UUID | None = None,
    q: str | None = None,
    state: str | None = None,
) -> list[AdminResultItem]:
    await _require_publish(actor)
    cycle = await session.get(Competition, competition_id)
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)

    stmt = (
        select(ResultEntry, ResultPublication, Skill, Competitor, Stage)
        .join(ResultPublication, ResultPublication.id == ResultEntry.publication_id)
        .join(Skill, Skill.id == ResultEntry.skill_id)
        .outerjoin(Competitor, Competitor.id == ResultEntry.competitor_id)
        .outerjoin(Stage, Stage.id == ResultPublication.stage_id)
        .where(
            ResultEntry.competition_id == competition_id,
            ResultEntry.is_current.is_(True),
        )
    )
    if skill_id is not None:
        stmt = stmt.where(ResultEntry.skill_id == skill_id)
    if state and state.strip():
        stmt = stmt.where(ResultPublication.state == state.strip().upper())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Skill.name.ilike(term),
                Competitor.ref_no.ilike(term),
                Competitor.given_names.ilike(term),
                Competitor.family_name.ilike(term),
                ResultEntry.outcome.ilike(term),
                Stage.name.ilike(term),
            )
        )
    stmt = stmt.order_by(Skill.name.asc(), ResultEntry.rank.asc().nullslast(), Competitor.ref_no.asc())
    rows = (await session.execute(stmt)).all()
    return [
        AdminResultItem(
            resultId=entry.id,
            publicationId=pub.id,
            competitionId=entry.competition_id,
            skillId=entry.skill_id,
            skillName=skill.name,
            stageId=pub.stage_id,
            stageName=stage.name if stage else None,
            competitorId=entry.competitor_id,
            competitorRef=comp.ref_no if comp else None,
            competitorName=_competitor_display_name(comp),
            outcome=entry.outcome,
            score=entry.score,
            rank=entry.rank,
            version=entry.version,
            publicationState=pub.state,
            releaseAt=pub.release_at,
            releasedAt=pub.released_at,
        )
        for entry, pub, skill, comp, stage in rows
    ]
