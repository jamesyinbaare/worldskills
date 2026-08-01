"""US-SUB-01 — configure and publish Exercise per stage."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import Competition, Exercise, MarkingScheme, Stage, User, UserRole
from app.schemas.competition_config import ExerciseRubricOut, ExerciseRubricPut
from app.schemas.exercises import DeliverableItem, ExercisePut
from app.services.audit import write_audit_event
from app.services.storage import ObjectStorage, get_object_storage


def exercise_to_dict(ex: Exercise) -> dict[str, Any]:
    return {
        "id": str(ex.id),
        "stageId": str(ex.stage_id),
        "competitionId": str(ex.competition_id),
        "title": ex.title,
        "brief": ex.brief,
        "deliverables": ex.deliverables or [],
        "status": ex.status,
        "schemeId": str(ex.scheme_id) if ex.scheme_id else None,
        "latePolicy": ex.late_policy,
        "timedDurationSeconds": ex.timed_duration_seconds,
        "packFileName": ex.pack_file_name,
        "packContentType": ex.pack_content_type,
        "packScanStatus": ex.pack_scan_status,
        "availabilityNotifiedAt": (
            ex.availability_notified_at.isoformat() if ex.availability_notified_at else None
        ),
    }


def rubric_meta(scheme: MarkingScheme | None) -> tuple[bool, bool | None, int]:
    if scheme is None or not isinstance(scheme.rubric, dict):
        return False, None, 0
    criteria = scheme.rubric.get("criteria") or []
    has = isinstance(criteria, list) and len(criteria) > 0
    blind = bool(scheme.rubric.get("blindMode", False))
    return has, blind, len(criteria) if isinstance(criteria, list) else 0


def scheme_has_rubric_criteria(scheme: MarkingScheme | None) -> bool:
    has, _, _ = rubric_meta(scheme)
    return has



def deliverables_to_submission_rules(ex: Exercise) -> dict[str, Any]:
    """Map Exercise deliverables to legacy submission_rules shape for US-SUB-02."""
    required: list[dict[str, Any]] = []
    for item in ex.deliverables or []:
        if not isinstance(item, dict):
            continue
        if item.get("required") is False:
            continue
        max_bytes = item.get("maxSizeBytes")
        max_mb = int(max_bytes / (1024 * 1024)) if max_bytes else None
        required.append(
            {
                "code": item.get("code"),
                "label": item.get("label"),
                "formats": list(item.get("allowedTypes") or []),
                "maxMb": max_mb,
            }
        )
    return {
        "requiredDeliverables": required,
        "latePolicy": ex.late_policy or "block",
        "timedDurationSeconds": ex.timed_duration_seconds,
    }


async def _require_cycle_mutable(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    for_publish: bool = False,
) -> Competition:
    _ = for_publish
    result = await session.execute(select(Competition).where(Competition.id == competition_id))
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)
    return cycle


async def _load_stage(
    session: AsyncSession, competition_id: uuid.UUID, stage_id: uuid.UUID
) -> Stage:
    result = await session.execute(
        select(Stage).where(Stage.id == stage_id, Stage.competition_id == competition_id)
    )
    stage = result.scalar_one_or_none()
    if stage is None:
        raise AppError("STAGE_NOT_FOUND", "Stage not found in cycle", status_code=status.HTTP_404_NOT_FOUND)
    return stage


async def _resolve_scheme(
    session: AsyncSession, *, competition_id: uuid.UUID, scheme_id: uuid.UUID
) -> uuid.UUID:
    result = await session.execute(
        select(MarkingScheme).where(MarkingScheme.id == scheme_id, MarkingScheme.competition_id == competition_id)
    )
    if result.scalar_one_or_none() is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "schemeId is not resolvable in this competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("schemeId", "CONFIG_INCOMPLETE")],
        )
    return scheme_id


def _serialize_deliverables(items: list[DeliverableItem]) -> list[dict[str, Any]]:
    return [
        {
            "code": d.code,
            "label": d.label,
            "required": d.required,
            "allowedTypes": list(d.allowedTypes or []),
            "maxSizeBytes": d.maxSizeBytes,
        }
        for d in items
    ]


async def get_exercise(
    session: AsyncSession, competition_id: uuid.UUID, stage_id: uuid.UUID
) -> Exercise:
    await _load_stage(session, competition_id, stage_id)
    result = await session.execute(
        select(Exercise).where(Exercise.stage_id == stage_id, Exercise.competition_id == competition_id)
    )
    ex = result.scalar_one_or_none()
    if ex is None:
        raise AppError("EXERCISE_NOT_FOUND", "Exercise not found", status_code=status.HTTP_404_NOT_FOUND)
    return ex


async def get_exercise_for_actor(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    *,
    actor: User,
) -> Exercise:
    """Admins/experts see any exercise; competitors only PUBLISHED when registered."""
    from app.core.rbac import Capability, has_capability, is_admin_role
    from app.models import Competitor

    ex = await get_exercise(session, competition_id, stage_id)

    if is_admin_role(actor.role) or has_capability(actor.role, Capability.PUBLISH_TEST_PROJECT):
        return ex

    if actor.role == UserRole.EXPERT:
        return ex

    if actor.role == UserRole.COMPETITOR:
        if ex.status != "PUBLISHED":
            raise AppError(
                "EXERCISE_NOT_PUBLISHED",
                "Exercise is not available until published",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        competitor = (
            await session.execute(
                select(Competitor).where(
                    Competitor.user_id == actor.id,
                    Competitor.competition_id == competition_id,
                )
            )
        ).scalar_one_or_none()
        if competitor is None:
            raise AppError(
                "UNAUTHORIZED",
                "Not registered in this competition",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        stage = await _load_stage(session, competition_id, stage_id)
        if stage.skill_id is not None and competitor.skill_id != stage.skill_id:
            raise AppError(
                "FORBIDDEN",
                "Stage is not part of your skill pathway",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        from app.services.stages import assert_stage_available

        assert_stage_available(stage)
        return ex

    raise AppError("UNAUTHORIZED", "Not allowed to view exercise", status_code=status.HTTP_401_UNAUTHORIZED)


async def upsert_exercise(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: ExercisePut,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Exercise:
    await _require_cycle_mutable(session, competition_id)
    stage = await _load_stage(session, competition_id, stage_id)

    if payload.schemeId is not None:
        await _resolve_scheme(session, competition_id=competition_id, scheme_id=payload.schemeId)

    result = await session.execute(select(Exercise).where(Exercise.stage_id == stage_id))
    existing = result.scalar_one_or_none()
    before = exercise_to_dict(existing) if existing else None

    deliverables = _serialize_deliverables(payload.deliverables)

    if existing is None:
        ex = Exercise(
            stage_id=stage_id,
            competition_id=competition_id,
            title=payload.title,
            brief=payload.brief,
            deliverables=deliverables,
            status="DRAFT",
            scheme_id=payload.schemeId,
            late_policy=payload.latePolicy,
            timed_duration_seconds=payload.timedDurationSeconds,
        )
        session.add(ex)
        action = "EXERCISE_CREATE"
    else:
        if existing.status == "PUBLISHED":
            # Editing a published exercise keeps PUBLISHED unless explicitly unpublished.
            pass
        ex = existing
        ex.title = payload.title
        ex.brief = payload.brief
        ex.deliverables = deliverables
        ex.scheme_id = payload.schemeId
        ex.late_policy = payload.latePolicy
        ex.timed_duration_seconds = payload.timedDurationSeconds
        action = "EXERCISE_UPDATE"

    # Keep legacy submission_rules in sync for SUB-02 consumers.
    stage.submission_rules = deliverables_to_submission_rules(ex)

    await session.flush()
    await write_audit_event(
        session,
        action=action,
        entity_type="Exercise",
        entity_id=str(ex.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=exercise_to_dict(ex),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(ex)
    return ex


async def _assert_publishable(session: AsyncSession, ex: Exercise) -> None:
    _ = session
    fields: list[FieldError] = []
    if not ex.deliverables:
        fields.append(FieldError("deliverables", "REQUIRED"))
    if fields:
        raise AppError(
            "VALIDATION_ERROR",
            "Exercise is incomplete for publish",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=fields,
        )


async def publish_exercise(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Exercise:
    await _require_cycle_mutable(session, competition_id, for_publish=True)
    ex = await get_exercise(session, competition_id, stage_id)
    await _assert_publishable(session, ex)
    if ex.scheme_id:
        await _resolve_scheme(session, competition_id=competition_id, scheme_id=ex.scheme_id)
    before = exercise_to_dict(ex)
    ex.status = "PUBLISHED"
    stage = await session.get(Stage, stage_id)
    if stage is not None:
        stage.submission_rules = deliverables_to_submission_rules(ex)
    await session.flush()
    await write_audit_event(
        session,
        action="EXERCISE_PUBLISH",
        entity_type="Exercise",
        entity_id=str(ex.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=exercise_to_dict(ex),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(ex)

    # Best-effort SMS when exercise is immediately available
    try:
        from app.services import competition_sms

        await competition_sms.notify_exercise_available(
            session,
            competition_id=competition_id,
            stage_id=stage_id,
            trigger="exercise_publish",
            actor=actor,
            commit=True,
        )
        await session.refresh(ex)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "EXERCISE_AVAILABLE SMS failed after publish competition=%s stage=%s",
            competition_id,
            stage_id,
        )
    return ex


async def unpublish_exercise(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Exercise:
    await _require_cycle_mutable(session, competition_id, for_publish=True)
    ex = await get_exercise(session, competition_id, stage_id)
    before = exercise_to_dict(ex)
    ex.status = "DRAFT"
    ex.availability_notified_at = None
    await session.flush()
    await write_audit_event(
        session,
        action="EXERCISE_UNPUBLISH",
        entity_type="Exercise",
        entity_id=str(ex.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=exercise_to_dict(ex),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(ex)
    return ex


async def get_exercise_for_stage(
    session: AsyncSession, stage_id: uuid.UUID
) -> Exercise | None:
    result = await session.execute(select(Exercise).where(Exercise.stage_id == stage_id))
    return result.scalar_one_or_none()


_PACK_MIME = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


def _assert_pack_mime(content_type: str | None, filename: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    lower = filename.lower()
    if ct in _PACK_MIME:
        return ct
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    raise AppError(
        "FILE_TYPE",
        "Only PDF or DOCX packs are allowed",
        status_code=status.HTTP_400_BAD_REQUEST,
        fields=[FieldError("file", "FILE_TYPE")],
    )


async def upload_exercise_pack(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    *,
    actor: User,
    data: bytes,
    filename: str,
    content_type: str | None,
    ip: str | None = None,
    user_agent: str | None = None,
    storage: ObjectStorage | None = None,
) -> Exercise:
    await _require_cycle_mutable(session, competition_id)
    ex = await get_exercise(session, competition_id, stage_id)
    mime = _assert_pack_mime(content_type, filename)
    store = storage or get_object_storage()
    prior_key = ex.pack_object_key
    prior_name = ex.pack_file_name
    prior_ct = ex.pack_content_type
    prior_scan = ex.pack_scan_status
    try:
        stored = store.put(
            data,
            prefix=f"cycles/{competition_id}/exercises/{ex.id}/pack",
            filename=filename,
        )
    except AppError:
        ex.pack_object_key = prior_key
        ex.pack_file_name = prior_name
        ex.pack_content_type = prior_ct
        ex.pack_scan_status = prior_scan
        raise

    before = exercise_to_dict(ex)
    ex.pack_object_key = stored.key
    ex.pack_file_name = filename
    ex.pack_content_type = mime
    ex.pack_scan_status = "CLEAN"
    await session.flush()
    await write_audit_event(
        session,
        action="EXERCISE_PACK_UPLOAD",
        entity_type="Exercise",
        entity_id=str(ex.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=exercise_to_dict(ex),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(ex)
    return ex


async def delete_exercise_pack(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Exercise:
    await _require_cycle_mutable(session, competition_id)
    ex = await get_exercise(session, competition_id, stage_id)
    before = exercise_to_dict(ex)
    ex.pack_object_key = None
    ex.pack_file_name = None
    ex.pack_content_type = None
    ex.pack_scan_status = None
    await session.flush()
    await write_audit_event(
        session,
        action="EXERCISE_PACK_DELETE",
        entity_type="Exercise",
        entity_id=str(ex.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=exercise_to_dict(ex),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(ex)
    return ex


async def download_exercise_pack(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    *,
    actor: User,
    storage: ObjectStorage | None = None,
) -> tuple[bytes, str, str]:
    from app.core.rbac import Capability, has_capability, is_admin_role
    from app.models import Competitor

    ex = await get_exercise(session, competition_id, stage_id)
    if not ex.pack_object_key or not ex.pack_file_name:
        raise AppError("FILE_NOT_FOUND", "No pack attached", status_code=404)

    if actor.role == UserRole.COMPETITOR:
        if ex.status != "PUBLISHED":
            raise AppError(
                "EXERCISE_NOT_PUBLISHED",
                "Pack is not available until the exercise is published",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        competitor = (
            await session.execute(
                select(Competitor).where(
                    Competitor.user_id == actor.id,
                    Competitor.competition_id == competition_id,
                )
            )
        ).scalar_one_or_none()
        if competitor is None:
            raise AppError("UNAUTHORIZED", "Not registered in this competition", status_code=401)
        stage = await _load_stage(session, competition_id, stage_id)
        from app.services.stages import assert_stage_available

        assert_stage_available(stage)
    elif not (
        is_admin_role(actor.role)
        or has_capability(actor.role, Capability.PUBLISH_TEST_PROJECT)
        or actor.role == UserRole.EXPERT
    ):
        raise AppError("UNAUTHORIZED", "Not allowed to download pack", status_code=401)

    store = storage or get_object_storage()
    data = store.get(ex.pack_object_key)
    return data, ex.pack_file_name, ex.pack_content_type or "application/octet-stream"


async def get_exercise_rubric(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
) -> ExerciseRubricOut:
    ex = await get_exercise(session, competition_id, stage_id)
    if not ex.scheme_id:
        raise AppError(
            "NOT_FOUND",
            "No rubric configured for this exercise yet",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    scheme = await session.get(MarkingScheme, ex.scheme_id)
    if scheme is None:
        raise AppError("NOT_FOUND", "Rubric not found", status_code=404)
    rubric = scheme.rubric if isinstance(scheme.rubric, dict) else {}
    criteria = list(rubric.get("criteria") or [])
    penalties = list(rubric.get("penalties") or [])
    return ExerciseRubricOut(
        schemeId=scheme.id,
        competitionId=competition_id,
        stageId=stage_id,
        exerciseId=ex.id,
        name=scheme.name,
        blindMode=bool(rubric.get("blindMode", False)),
        criteria=criteria,
        penalties=penalties,
        hasRubricCriteria=len(criteria) > 0,
    )


async def put_exercise_rubric(
    session: AsyncSession,
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: ExerciseRubricPut,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ExerciseRubricOut:
    await _require_cycle_mutable(session, competition_id)
    stage = await _load_stage(session, competition_id, stage_id)

    # Ensure exercise exists (create a stub draft if needed via get or minimal upsert)
    ex = (
        await session.execute(
            select(Exercise).where(
                Exercise.stage_id == stage_id,
                Exercise.competition_id == competition_id,
            )
        )
    ).scalar_one_or_none()
    if ex is None:
        ex = Exercise(
            stage_id=stage_id,
            competition_id=competition_id,
            title=stage.name or "Exercise",
            brief=None,
            deliverables=[],
            status="DRAFT",
            scheme_id=None,
        )
        session.add(ex)
        await session.flush()

    criteria_out: list[dict[str, Any]] = []
    for idx, c in enumerate(payload.criteria):
        cid = (c.id or "").strip() or f"c{idx + 1}"
        criteria_out.append(
            {
                "id": cid,
                "name": c.name,
                "type": c.type,
                "max": c.max,
            }
        )
    penalties_out: list[dict[str, Any]] = []
    for p in payload.penalties:
        item: dict[str, Any] = {"code": p.code, "deduction": p.deduction}
        if p.cap is not None:
            item["cap"] = p.cap
        penalties_out.append(item)

    rubric_json: dict[str, Any] = {
        "blindMode": payload.blindMode,
        "criteria": criteria_out,
        "penalties": penalties_out,
    }

    scheme: MarkingScheme | None = None
    if ex.scheme_id:
        scheme = await session.get(MarkingScheme, ex.scheme_id)
    if scheme is None:
        scheme_name = f"Rubric — {ex.title or stage.name}"
        scheme = MarkingScheme(
            competition_id=competition_id,
            name=scheme_name[:120],
            rubric=rubric_json,
        )
        session.add(scheme)
        await session.flush()
        ex.scheme_id = scheme.id
    else:
        scheme.rubric = rubric_json

    await session.flush()
    await write_audit_event(
        session,
        action="EXERCISE_RUBRIC_UPDATE",
        entity_type="MarkingScheme",
        entity_id=str(scheme.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after={
            "schemeId": str(scheme.id),
            "exerciseId": str(ex.id),
            "blindMode": payload.blindMode,
            "criteriaCount": len(criteria_out),
            "penaltiesCount": len(penalties_out),
        },
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(scheme)
    await session.refresh(ex)

    return ExerciseRubricOut(
        schemeId=scheme.id,
        competitionId=competition_id,
        stageId=stage_id,
        exerciseId=ex.id,
        name=scheme.name,
        blindMode=payload.blindMode,
        criteria=criteria_out,
        penalties=penalties_out,
        hasRubricCriteria=len(criteria_out) > 0,
    )


async def load_scheme_for_exercise(
    session: AsyncSession, ex: Exercise
) -> MarkingScheme | None:
    if not ex.scheme_id:
        return None
    return await session.get(MarkingScheme, ex.scheme_id)
