"""Competition skill association + capacity enforcement (US-SKL-01 revised)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, FieldError
from app.models import (
    AgeRule,
    CatalogSkill,
    Competition,
    MarkingScheme,
    Pathway,
    Skill,
    Stage,
    User,
)
from app.schemas.skills import (
    AgeRuleEmbed,
    CycleSkillAssociate,
    CycleSkillPatch,
    SkillCreate,
)
from app.services.audit import write_audit_event


def skill_to_dict(skill: Skill) -> dict[str, Any]:
    return {
        "id": str(skill.id),
        "competitionId": str(skill.competition_id),
        "catalogSkillId": str(skill.catalog_skill_id) if skill.catalog_skill_id else None,
        "name": skill.name,
        "number": skill.number,
        "familyId": skill.family_id,
        "ageRuleId": str(skill.age_rule_id) if skill.age_rule_id else None,
        "maxAge": skill.max_age,
        "ageReferenceDate": skill.age_reference_date.isoformat() if skill.age_reference_date else None,
        "openCategoryEnabled": skill.open_category_enabled,
        "pathwayId": str(skill.pathway_id) if skill.pathway_id else None,
        "schemeId": str(skill.scheme_id) if skill.scheme_id else None,
        "capacity": skill.capacity,
        "schoolQuota": skill.school_quota,
        "active": skill.active,
    }


def age_rule_embed(skill: Skill) -> AgeRuleEmbed | None:
    if skill.max_age is None:
        return None
    return AgeRuleEmbed(
        maxAge=skill.max_age,
        referenceDate=skill.age_reference_date,
        openCategoryEnabled=bool(skill.open_category_enabled)
        if skill.open_category_enabled is not None
        else False,
    )


def enforce_skill_capacity(skill: Skill, *, occupied_count: int) -> None:
    """Block a new registration when the skill is at configured capacity."""
    if skill.capacity is None:
        return
    if occupied_count >= skill.capacity:
        raise AppError(
            "SKILL_CAPACITY_REACHED",
            f"Skill '{skill.name}' is at capacity ({skill.capacity})",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("skillId", "SKILL_CAPACITY_REACHED")],
        )


async def _require_cycle_mutable(session: AsyncSession, competition_id: uuid.UUID) -> Competition:
    result = await session.execute(select(Competition).where(Competition.id == competition_id))
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)
    return cycle


async def _resolve_in_cycle(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    model: type,
    entity_id: uuid.UUID | None,
    field_name: str,
) -> uuid.UUID | None:
    if entity_id is None:
        return None
    result = await session.execute(
        select(model).where(model.id == entity_id, model.competition_id == competition_id)  # type: ignore[attr-defined]
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError(
            "CONFIG_INCOMPLETE",
            f"{field_name} is not resolvable in this competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError(field_name, "CONFIG_INCOMPLETE")],
        )
    return entity_id


async def list_skills(session: AsyncSession, competition_id: uuid.UUID) -> list[Skill]:
    result = await session.execute(
        select(Skill)
        .options(selectinload(Skill.catalog_skill).selectinload(CatalogSkill.family))
        .where(Skill.competition_id == competition_id)
        .order_by(Skill.name)
    )
    return list(result.scalars().all())


async def list_available_skills(session: AsyncSession, competition_id: uuid.UUID) -> list[dict]:
    """Active cycle skills for competitor/institution registration pickers."""
    skills = await list_skills(session, competition_id)
    legacy_rule_ids = {
        skill.age_rule_id
        for skill in skills
        if skill.active and skill.max_age is None and skill.age_rule_id is not None
    }
    age_rules: dict[uuid.UUID, AgeRule] = {}
    if legacy_rule_ids:
        result = await session.execute(select(AgeRule).where(AgeRule.id.in_(legacy_rule_ids)))
        age_rules = {row.id: row for row in result.scalars().all()}

    out: list[dict] = []
    for skill in skills:
        if not skill.active:
            continue
        family_name = None
        description = None
        catalog = skill.__dict__.get("catalog_skill")
        if catalog is not None:
            description = catalog.description
            family = catalog.__dict__.get("family")
            if family is not None:
                family_name = family.name

        max_age = skill.max_age
        reference_date = skill.age_reference_date
        open_category = (
            bool(skill.open_category_enabled)
            if skill.open_category_enabled is not None
            else False
        )
        if max_age is None and skill.age_rule_id is not None:
            rule = age_rules.get(skill.age_rule_id)
            if rule is not None:
                max_age = rule.max_age
                reference_date = rule.reference_date
                open_category = bool(rule.open_category_enabled)

        out.append(
            {
                "skillId": skill.id,
                "name": skill.name,
                "number": skill.number,
                "familyName": family_name,
                "description": description,
                "active": True,
                "hasCriteriaDocument": bool(
                    skill.criteria_object_key and skill.criteria_file_name
                ),
                "criteriaFileName": skill.criteria_file_name,
                "maxAge": max_age,
                "referenceDate": reference_date,
                "openCategoryEnabled": open_category,
            }
        )
    return out


async def skill_has_pathway(session: AsyncSession, skill_id: uuid.UUID) -> bool:
    result = await session.execute(
        select(func.count()).select_from(Stage).where(Stage.skill_id == skill_id)
    )
    return int(result.scalar_one()) > 0


async def associate_skill(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: CompetitionSkillAssociate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Skill:
    await _require_cycle_mutable(session, competition_id)

    catalog = await session.get(CatalogSkill, payload.skillId)
    if catalog is None or not catalog.active:
        raise AppError(
            "CONFIG_INCOMPLETE",
            "Catalog skill is not resolvable or inactive",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("skillId", "CONFIG_INCOMPLETE")],
        )
    await session.refresh(catalog, attribute_names=["family"])

    dup = await session.execute(
        select(Skill).where(Skill.competition_id == competition_id, Skill.catalog_skill_id == catalog.id)
    )
    if dup.scalar_one_or_none() is not None:
        raise AppError(
            "SKILL_DUPLICATE",
            "This catalog skill is already associated to the competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("skillId", "DUPLICATE")],
        )

    # Name uniqueness within cycle (denormalized from catalog)
    name_dup = await session.execute(
        select(Skill).where(Skill.competition_id == competition_id, Skill.name == catalog.name)
    )
    if name_dup.scalar_one_or_none() is not None:
        raise AppError(
            "SKILL_DUPLICATE",
            "A skill with this name already exists in the competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("name", "DUPLICATE")],
        )

    skill = Skill(
        competition_id=competition_id,
        catalog_skill_id=catalog.id,
        name=catalog.name,
        number=catalog.number,
        family_id=str(catalog.family_id),
        max_age=payload.ageRule.maxAge,
        age_reference_date=payload.ageRule.referenceDate,
        open_category_enabled=payload.ageRule.openCategoryEnabled,
        capacity=payload.capacity,
        active=True,
    )
    session.add(skill)
    await session.flush()

    await write_audit_event(
        session,
        action="SKILL_ASSOCIATE",
        entity_type="Skill",
        entity_id=str(skill.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after=skill_to_dict(skill),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(skill)
    return skill


async def patch_cycle_skill(
    session: AsyncSession,
    competition_id: uuid.UUID,
    cycle_skill_id: uuid.UUID,
    payload: CycleSkillPatch,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Skill:
    await _require_cycle_mutable(session, competition_id)
    skill = await session.get(Skill, cycle_skill_id)
    if skill is None or skill.competition_id != competition_id:
        raise AppError("SKILL_NOT_FOUND", "Competition skill not found", status_code=status.HTTP_404_NOT_FOUND)

    before = skill_to_dict(skill)
    data = payload.model_dump(exclude_unset=True)
    if "ageRule" in data and data["ageRule"] is not None:
        rule = payload.ageRule
        assert rule is not None
        skill.max_age = rule.maxAge
        skill.age_reference_date = rule.referenceDate
        skill.open_category_enabled = rule.openCategoryEnabled
    if "capacity" in data:
        skill.capacity = data["capacity"]
    if "schoolQuota" in data:
        skill.school_quota = data["schoolQuota"]
    if "active" in data and data["active"] is not None:
        skill.active = data["active"]

    await write_audit_event(
        session,
        action="SKILL_UPDATE",
        entity_type="Skill",
        entity_id=str(skill.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=skill_to_dict(skill),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(skill)
    return skill


async def create_skill(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: SkillCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Skill:
    """Create or associate a competition skill.

    Preferred path: skillId + ageRule (catalog association).
    Legacy path: name + ageRuleId (kept for transitional tests/clients).
    """
    if payload.skillId is not None:
        if payload.ageRule is None:
            raise AppError(
                "VALIDATION_ERROR",
                "ageRule is required when associating a catalog skill",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                fields=[FieldError("ageRule", "REQUIRED")],
            )
        return await associate_skill(
            session,
            competition_id,
            CycleSkillAssociate(
                skillId=payload.skillId,
                ageRule=payload.ageRule,
                capacity=payload.capacity,
            ),
            actor=actor,
            ip=ip,
            user_agent=user_agent,
        )

    await _require_cycle_mutable(session, competition_id)

    if not payload.name or not payload.name.strip():
        raise AppError(
            "VALIDATION_ERROR",
            "Name is required",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("name", "REQUIRED")],
        )

    if payload.capacity is not None and payload.capacity <= 0:
        raise AppError(
            "VALIDATION_ERROR",
            "Invalid capacity",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("capacity", "INVALID_CAPACITY")],
        )

    dup = await session.execute(
        select(Skill).where(Skill.competition_id == competition_id, Skill.name == payload.name)
    )
    if dup.scalar_one_or_none() is not None:
        raise AppError(
            "SKILL_DUPLICATE",
            "A skill with this name already exists in the competition",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("name", "DUPLICATE")],
        )

    age_rule_id = await _resolve_in_cycle(
        session, competition_id=competition_id, model=AgeRule, entity_id=payload.ageRuleId, field_name="ageRuleId"
    )
    pathway_id = await _resolve_in_cycle(
        session, competition_id=competition_id, model=Pathway, entity_id=payload.pathwayId, field_name="pathwayId"
    )
    scheme_id = await _resolve_in_cycle(
        session,
        competition_id=competition_id,
        model=MarkingScheme,
        entity_id=payload.schemeId,
        field_name="schemeId",
    )

    # Mirror linked AgeRule onto embedded columns when present
    max_age = None
    age_ref = None
    open_cat = None
    if age_rule_id is not None:
        age = await session.get(AgeRule, age_rule_id)
        if age is not None:
            max_age = age.max_age
            age_ref = age.reference_date
            open_cat = age.open_category_enabled

    if payload.ageRule is not None:
        max_age = payload.ageRule.maxAge
        age_ref = payload.ageRule.referenceDate
        open_cat = payload.ageRule.openCategoryEnabled

    skill = Skill(
        competition_id=competition_id,
        name=payload.name,
        number=payload.number,
        family_id=payload.familyId,
        age_rule_id=age_rule_id,
        max_age=max_age,
        age_reference_date=age_ref,
        open_category_enabled=open_cat,
        pathway_id=pathway_id,
        scheme_id=scheme_id,
        capacity=payload.capacity,
        school_quota=payload.schoolQuota,
        active=True,
    )
    session.add(skill)
    await session.flush()

    await write_audit_event(
        session,
        action="SKILL_CREATE",
        entity_type="Skill",
        entity_id=str(skill.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after=skill_to_dict(skill),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(skill)
    return skill


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


async def _load_cycle_skill(
    session: AsyncSession, competition_id: uuid.UUID, skill_id: uuid.UUID
) -> Skill:
    skill = (
        await session.execute(
            select(Skill).where(Skill.id == skill_id, Skill.competition_id == competition_id)
        )
    ).scalar_one_or_none()
    if skill is None:
        raise AppError("SKILL_NOT_FOUND", "Skill not found in competition", status_code=404)
    return skill


async def upload_skill_criteria_document(
    session: AsyncSession,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    *,
    actor: User,
    data: bytes,
    filename: str,
    content_type: str | None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Skill:
    from app.services.storage import get_object_storage

    await _require_cycle_mutable(session, competition_id)
    skill = await _load_cycle_skill(session, competition_id, skill_id)
    mime = _assert_doc_mime(content_type, filename)
    store = get_object_storage()
    stored = store.put(
        data,
        prefix=f"cycles/{competition_id}/skills/{skill.id}/criteria",
        filename=filename,
    )
    before = skill_to_dict(skill)
    skill.criteria_object_key = stored.key
    skill.criteria_file_name = filename
    skill.criteria_content_type = mime
    skill.criteria_scan_status = "CLEAN"
    await session.flush()
    await write_audit_event(
        session,
        action="SKILL_CRITERIA_DOCUMENT_UPLOAD",
        entity_type="Skill",
        entity_id=str(skill.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=skill_to_dict(skill),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(skill)
    return skill


async def delete_skill_criteria_document(
    session: AsyncSession,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Skill:
    await _require_cycle_mutable(session, competition_id)
    skill = await _load_cycle_skill(session, competition_id, skill_id)
    before = skill_to_dict(skill)
    skill.criteria_object_key = None
    skill.criteria_file_name = None
    skill.criteria_content_type = None
    skill.criteria_scan_status = None
    await session.flush()
    await write_audit_event(
        session,
        action="SKILL_CRITERIA_DOCUMENT_DELETE",
        entity_type="Skill",
        entity_id=str(skill.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=skill_to_dict(skill),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(skill)
    return skill


async def download_skill_criteria_document(
    session: AsyncSession,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    *,
    actor: User,
) -> tuple[bytes, str, str]:
    from app.core.rbac import is_admin_role
    from app.models import Competitor, UserRole
    from app.services.storage import get_object_storage

    skill = await _load_cycle_skill(session, competition_id, skill_id)
    if not skill.criteria_object_key or not skill.criteria_file_name:
        raise AppError("FILE_NOT_FOUND", "No criteria document attached", status_code=404)

    role = actor.role
    if is_admin_role(role) or role in {UserRole.EXPERT, UserRole.CHIEF_EXPERT}:
        pass
    elif role == UserRole.COMPETITOR:
        competitor = (
            await session.execute(
                select(Competitor).where(
                    Competitor.user_id == actor.id,
                    Competitor.competition_id == competition_id,
                    Competitor.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        if competitor is None:
            raise AppError(
                "FORBIDDEN",
                "Not registered for this skill",
                status_code=status.HTTP_403_FORBIDDEN,
            )
    elif role == UserRole.INSTITUTION:
        if actor.institution_id is None:
            raise AppError("FORBIDDEN", "Institution membership required", status_code=403)
        if not skill.active:
            raise AppError("FORBIDDEN", "Skill is not active", status_code=403)
    else:
        raise AppError("FORBIDDEN", "Not allowed to download criteria", status_code=403)

    store = get_object_storage()
    data = store.get(skill.criteria_object_key)
    return (
        data,
        skill.criteria_file_name,
        skill.criteria_content_type or "application/octet-stream",
    )


async def download_public_skill_criteria_document(
    session: AsyncSession,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
) -> tuple[bytes, str, str]:
    """Criteria download for open-registration competitions (no auth)."""
    from datetime import datetime

    from app.models import Competition, CompetitionStatus, RegistrationWindow
    from app.services.storage import get_object_storage

    now = datetime.utcnow()
    open_row = (
        await session.execute(
            select(Competition.id)
            .join(RegistrationWindow, RegistrationWindow.competition_id == Competition.id)
            .where(
                Competition.id == competition_id,
                Competition.status == CompetitionStatus.ACTIVE,
                RegistrationWindow.opens_at <= now,
                RegistrationWindow.closes_at >= now,
            )
        )
    ).scalar_one_or_none()
    if open_row is None:
        raise AppError(
            "COMPETITION_NOT_FOUND",
            "Competition not found or not open for registration",
            status_code=404,
        )

    skill = await _load_cycle_skill(session, competition_id, skill_id)
    if not skill.active:
        raise AppError("FORBIDDEN", "Skill is not active", status_code=403)
    if not skill.criteria_object_key or not skill.criteria_file_name:
        raise AppError("FILE_NOT_FOUND", "No criteria document attached", status_code=404)

    store = get_object_storage()
    data = store.get(skill.criteria_object_key)
    return (
        data,
        skill.criteria_file_name,
        skill.criteria_content_type or "application/octet-stream",
    )
