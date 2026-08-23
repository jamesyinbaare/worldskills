"""Cycle-scoped age rules, pathways, and marking schemes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.models import AgeRule, Competition, MarkingScheme, Pathway, User
from app.schemas.competition_config import AgeRuleCreate, MarkingSchemeCreate, PathwayConfigCreate
from app.services.audit import write_audit_event
from app.services.storage import ObjectStorage, get_object_storage


async def _require_cycle(session: AsyncSession, competition_id: uuid.UUID) -> Competition:
    result = await session.execute(select(Competition).where(Competition.id == competition_id))
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)
    return cycle


async def _require_cycle_mutable(session: AsyncSession, competition_id: uuid.UUID) -> Competition:
    return await _require_cycle(session, competition_id)


def age_rule_to_dict(rule: AgeRule) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "competitionId": str(rule.competition_id),
        "name": rule.name,
        "maxAge": rule.max_age,
        "referenceDate": rule.reference_date.isoformat() if rule.reference_date else None,
        "openCategoryEnabled": rule.open_category_enabled,
    }


def pathway_to_dict(path: Pathway) -> dict[str, Any]:
    return {
        "id": str(path.id),
        "competitionId": str(path.competition_id),
        "name": path.name,
    }


def scheme_to_dict(scheme: MarkingScheme) -> dict[str, Any]:
    return {
        "id": str(scheme.id),
        "competitionId": str(scheme.competition_id),
        "name": scheme.name,
        "documentFileName": scheme.document_file_name,
        "documentContentType": scheme.document_content_type,
        "documentScanStatus": scheme.document_scan_status,
    }


async def list_age_rules(session: AsyncSession, competition_id: uuid.UUID) -> list[AgeRule]:
    await _require_cycle(session, competition_id)
    result = await session.execute(
        select(AgeRule).where(AgeRule.competition_id == competition_id).order_by(AgeRule.name)
    )
    return list(result.scalars().all())


async def create_age_rule(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: AgeRuleCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AgeRule:
    await _require_cycle_mutable(session, competition_id)

    if not payload.name or not payload.name.strip():
        raise AppError(
            "VALIDATION_ERROR",
            "Name is required",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("name", "REQUIRED")],
        )

    rule = AgeRule(
        competition_id=competition_id,
        name=payload.name.strip(),
        max_age=payload.maxAge,
        reference_date=payload.referenceDate,
        open_category_enabled=payload.openCategoryEnabled,
    )
    session.add(rule)
    await session.flush()

    await write_audit_event(
        session,
        action="AGE_RULE_CREATE",
        entity_type="AgeRule",
        entity_id=str(rule.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after=age_rule_to_dict(rule),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(rule)
    return rule


async def list_pathways(session: AsyncSession, competition_id: uuid.UUID) -> list[Pathway]:
    await _require_cycle(session, competition_id)
    result = await session.execute(
        select(Pathway).where(Pathway.competition_id == competition_id).order_by(Pathway.name)
    )
    return list(result.scalars().all())


async def create_pathway(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: PathwayConfigCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Pathway:
    await _require_cycle_mutable(session, competition_id)

    if not payload.name or not payload.name.strip():
        raise AppError(
            "VALIDATION_ERROR",
            "Name is required",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("name", "REQUIRED")],
        )

    path = Pathway(competition_id=competition_id, name=payload.name.strip())
    session.add(path)
    await session.flush()

    await write_audit_event(
        session,
        action="PATHWAY_CREATE",
        entity_type="Pathway",
        entity_id=str(path.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after=pathway_to_dict(path),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(path)
    return path


async def list_marking_schemes(session: AsyncSession, competition_id: uuid.UUID) -> list[MarkingScheme]:
    await _require_cycle(session, competition_id)
    result = await session.execute(
        select(MarkingScheme)
        .where(MarkingScheme.competition_id == competition_id)
        .order_by(MarkingScheme.name)
    )
    return list(result.scalars().all())


async def create_marking_scheme(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: MarkingSchemeCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> MarkingScheme:
    await _require_cycle_mutable(session, competition_id)

    if not payload.name or not payload.name.strip():
        raise AppError(
            "VALIDATION_ERROR",
            "Name is required",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("name", "REQUIRED")],
        )

    scheme = MarkingScheme(
        competition_id=competition_id,
        name=payload.name.strip(),
        rubric={
            "blindMode": True,
            "criteria": [
                {"id": "c_overall", "name": "Overall", "type": "JUDGEMENT", "max": 100},
            ],
            "penalties": [],
        },
    )
    session.add(scheme)
    await session.flush()

    await write_audit_event(
        session,
        action="MARKING_SCHEME_CREATE",
        entity_type="MarkingScheme",
        entity_id=str(scheme.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after=scheme_to_dict(scheme),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(scheme)
    return scheme


_DOC_MIME = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


def _assert_doc_mime(content_type: str | None, filename: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    lower = filename.lower()
    if ct in _DOC_MIME:
        return ct
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    raise AppError(
        "FILE_TYPE",
        "Only PDF or DOCX documents are allowed",
        status_code=status.HTTP_400_BAD_REQUEST,
        fields=[FieldError("file", "FILE_TYPE")],
    )


async def _load_scheme(
    session: AsyncSession, competition_id: uuid.UUID, scheme_id: uuid.UUID
) -> MarkingScheme:
    scheme = (
        await session.execute(
            select(MarkingScheme).where(
                MarkingScheme.id == scheme_id, MarkingScheme.competition_id == competition_id
            )
        )
    ).scalar_one_or_none()
    if scheme is None:
        raise AppError("NOT_FOUND", "Marking scheme not found", status_code=404)
    return scheme


async def upload_scheme_document(
    session: AsyncSession,
    competition_id: uuid.UUID,
    scheme_id: uuid.UUID,
    *,
    actor: User,
    data: bytes,
    filename: str,
    content_type: str | None,
    ip: str | None = None,
    user_agent: str | None = None,
    storage: ObjectStorage | None = None,
) -> MarkingScheme:
    await _require_cycle_mutable(session, competition_id)
    scheme = await _load_scheme(session, competition_id, scheme_id)
    mime = _assert_doc_mime(content_type, filename)
    store = storage or get_object_storage()
    prior = (
        scheme.document_object_key,
        scheme.document_file_name,
        scheme.document_content_type,
        scheme.document_scan_status,
    )
    try:
        stored = store.put(
            data,
            prefix=f"cycles/{competition_id}/schemes/{scheme.id}/document",
            filename=filename,
        )
    except AppError:
        (
            scheme.document_object_key,
            scheme.document_file_name,
            scheme.document_content_type,
            scheme.document_scan_status,
        ) = prior
        raise

    before = scheme_to_dict(scheme)
    scheme.document_object_key = stored.key
    scheme.document_file_name = filename
    scheme.document_content_type = mime
    scheme.document_scan_status = "CLEAN"
    await session.flush()
    await write_audit_event(
        session,
        action="MARKING_SCHEME_DOCUMENT_UPLOAD",
        entity_type="MarkingScheme",
        entity_id=str(scheme.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=scheme_to_dict(scheme),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(scheme)
    return scheme


async def delete_scheme_document(
    session: AsyncSession,
    competition_id: uuid.UUID,
    scheme_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> MarkingScheme:
    await _require_cycle_mutable(session, competition_id)
    scheme = await _load_scheme(session, competition_id, scheme_id)
    before = scheme_to_dict(scheme)
    scheme.document_object_key = None
    scheme.document_file_name = None
    scheme.document_content_type = None
    scheme.document_scan_status = None
    await session.flush()
    await write_audit_event(
        session,
        action="MARKING_SCHEME_DOCUMENT_DELETE",
        entity_type="MarkingScheme",
        entity_id=str(scheme.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=scheme_to_dict(scheme),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(scheme)
    return scheme


async def download_scheme_document(
    session: AsyncSession,
    competition_id: uuid.UUID,
    scheme_id: uuid.UUID,
    *,
    actor: User,
    storage: ObjectStorage | None = None,
) -> tuple[bytes, str, str]:
    from app.core.rbac import is_admin_role
    from app.models import ExpertAssignment, Exercise, UserRole

    if actor.role == UserRole.COMPETITOR:
        raise AppError("UNAUTHORIZED", "Competitors cannot download scheme documents", status_code=401)

    scheme = await _load_scheme(session, competition_id, scheme_id)
    if not scheme.document_object_key or not scheme.document_file_name:
        raise AppError("FILE_NOT_FOUND", "No document attached", status_code=404)

    if not (
        is_admin_role(actor.role)
        or actor.role in {UserRole.CHIEF_EXPERT, UserRole.EXPERT}
    ):
        raise AppError("UNAUTHORIZED", "Not allowed", status_code=401)

    store = storage or get_object_storage()
    data = store.get(scheme.document_object_key)
    return (
        data,
        scheme.document_file_name,
        scheme.document_content_type or "application/octet-stream",
    )
