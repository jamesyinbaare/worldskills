"""Competition create / clone / validate / activate service."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, FieldError
from app.models import (
    AgeRule,
    Competition,
    CompetitionRegionZone,
    CompetitionStatus,
    Exercise,
    MarkingScheme,
    Pathway,
    Skill,
    Stage,
    User,
    Zone,
)
from app.schemas.competitions import CompetitionCreate, ValidationIssue
from app.services.audit import write_audit_event
from app.services.config_resolution import load_competition_config


async def _find_duplicate(
    session: AsyncSession,
    *,
    name: str,
    period_start: date,
    period_end: date,
    exclude_id: uuid.UUID | None = None,
) -> Competition | None:
    """Name collision with an existing cycle in an overlapping period."""
    stmt = select(Competition).where(
        Competition.name == name,
        Competition.period_start <= period_end,
        Competition.period_end >= period_start,
    )
    if exclude_id is not None:
        stmt = stmt.where(Competition.id != exclude_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def competition_to_dict(cycle: Competition) -> dict[str, Any]:
    return {
        "id": str(cycle.id),
        "name": cycle.name,
        "period": {"start": str(cycle.period_start), "end": str(cycle.period_end)},
        "timeZone": cycle.time_zone,
        "status": cycle.status.value if hasattr(cycle.status, "value") else cycle.status,
        "languages": cycle.languages,
        "description": cycle.description,
        "organisingBody": cycle.organising_body,
        "branding": cycle.branding,
    }


async def create_competition(
    session: AsyncSession,
    payload: CompetitionCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Competition:
    if payload.period.end <= payload.period.start:
        raise AppError(
            "VALIDATION_ERROR",
            "Invalid period",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=[FieldError("period.end", "BEFORE_START")],
        )

    dup = await _find_duplicate(
        session,
        name=payload.name,
        period_start=payload.period.start,
        period_end=payload.period.end,
    )
    if dup is not None:
        raise AppError(
            "COMPETITION_DUPLICATE",
            "A competition with this name already exists in an overlapping period",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("name", "DUPLICATE")],
        )

    description = payload.description.strip() if payload.description else None
    if description == "":
        description = None

    cycle = Competition(
        name=payload.name,
        period_start=payload.period.start,
        period_end=payload.period.end,
        time_zone=payload.timeZone,
        status=CompetitionStatus.DRAFT,
        languages=["en"],
        description=description,
        organising_body=payload.organisingBody,
        branding=payload.branding,
    )
    session.add(cycle)
    await session.flush()

    await write_audit_event(
        session,
        action="COMPETITION_CREATE",
        entity_type="Competition",
        entity_id=str(cycle.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=cycle.id,
        after=competition_to_dict(cycle),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(cycle)
    return cycle


async def list_competitions(session: AsyncSession) -> list[Competition]:
    result = await session.execute(select(Competition).order_by(Competition.created_at.desc()))
    return list(result.scalars().all())


async def list_open_for_registration(session: AsyncSession) -> list[dict]:
    """ACTIVE cycles whose registration window is currently open."""
    from datetime import datetime

    from app.models import RegistrationWindow

    now = datetime.utcnow()
    result = await session.execute(
        select(Competition, RegistrationWindow)
        .join(RegistrationWindow, RegistrationWindow.competition_id == Competition.id)
        .where(
            Competition.status == CompetitionStatus.ACTIVE,
            RegistrationWindow.opens_at <= now,
            RegistrationWindow.closes_at >= now,
        )
        .order_by(Competition.name)
    )
    out: list[dict] = []
    for competition, window in result.all():
        out.append(
            {
                "competitionId": competition.id,
                "name": competition.name,
                "status": competition.status.value,
                "description": competition.description,
                "window": {
                    "opensAt": window.opens_at.isoformat(),
                    "closesAt": window.closes_at.isoformat(),
                },
            }
        )
    return out


async def get_public_competition(session: AsyncSession, competition_id: uuid.UUID) -> dict:
    """Public about payload for an ACTIVE cycle with an open registration window."""
    from datetime import datetime

    from app.models import RegistrationWindow
    from app.services import skills as skill_service

    now = datetime.utcnow()
    result = await session.execute(
        select(Competition, RegistrationWindow)
        .join(RegistrationWindow, RegistrationWindow.competition_id == Competition.id)
        .where(
            Competition.id == competition_id,
            Competition.status == CompetitionStatus.ACTIVE,
            RegistrationWindow.opens_at <= now,
            RegistrationWindow.closes_at >= now,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise AppError(
            "COMPETITION_NOT_FOUND",
            "Competition not found or not open for registration",
            status_code=404,
        )
    cycle, window = row
    skills = await skill_service.list_available_skills(session, competition_id)
    return {
        "competitionId": cycle.id,
        "name": cycle.name,
        "description": cycle.description,
        "period": {"start": cycle.period_start, "end": cycle.period_end},
        "timeZone": cycle.time_zone,
        "window": {
            "opensAt": window.opens_at.isoformat(),
            "closesAt": window.closes_at.isoformat(),
        },
        "skills": [
            {
                "skillId": s["skillId"],
                "name": s["name"],
                "number": s.get("number"),
                "familyName": s.get("familyName"),
                "description": s.get("description"),
                "hasCriteriaDocument": bool(s.get("hasCriteriaDocument")),
                "criteriaFileName": s.get("criteriaFileName"),
            }
            for s in skills
        ],
    }


async def update_competition_public_profile(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    description: str | None,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Competition:
    cycle = await get_competition(session, competition_id)
    before = competition_to_dict(cycle)
    if description is not None:
        cleaned = description.strip()
        cycle.description = cleaned if cleaned else None
    await write_audit_event(
        session,
        action="COMPETITION_PUBLIC_PROFILE_UPDATE",
        entity_type="Competition",
        entity_id=str(cycle.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=cycle.id,
        before=before,
        after=competition_to_dict(cycle),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(cycle)
    return cycle


async def get_competition(session: AsyncSession, competition_id: uuid.UUID) -> Competition:
    result = await session.execute(
        select(Competition)
        .where(Competition.id == competition_id)
        .options(
            selectinload(Competition.skills),
            selectinload(Competition.stages).selectinload(Stage.exercise),
            selectinload(Competition.age_rules),
            selectinload(Competition.pathways),
            selectinload(Competition.marking_schemes),
            selectinload(Competition.exercises),
        )
    )
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=404)
    return cycle


async def clone_competition(
    session: AsyncSession,
    source_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Competition:
    source = await get_competition(session, source_id)

    new_cycle = Competition(
        name=f"{source.name} (copy)",
        period_start=source.period_start,
        period_end=source.period_end,
        time_zone=source.time_zone,
        status=CompetitionStatus.DRAFT,
        languages=list(source.languages or []),
        description=source.description,
        organising_body=source.organising_body,
        branding=source.branding,
    )
    session.add(new_cycle)
    await session.flush()

    age_map: dict[uuid.UUID, AgeRule] = {}
    for rule in source.age_rules:
        cloned = AgeRule(
            competition_id=new_cycle.id,
            name=rule.name,
            max_age=rule.max_age,
            reference_date=rule.reference_date,
        )
        session.add(cloned)
        await session.flush()
        age_map[rule.id] = cloned

    path_map: dict[uuid.UUID, Pathway] = {}
    for path in source.pathways:
        cloned = Pathway(competition_id=new_cycle.id, name=path.name)
        session.add(cloned)
        await session.flush()
        path_map[path.id] = cloned

    scheme_map: dict[uuid.UUID, MarkingScheme] = {}
    for scheme in source.marking_schemes:
        cloned = MarkingScheme(
            competition_id=new_cycle.id,
            name=scheme.name,
            document_object_key=scheme.document_object_key,
            document_file_name=scheme.document_file_name,
            document_content_type=scheme.document_content_type,
            document_scan_status=scheme.document_scan_status,
        )
        session.add(cloned)
        await session.flush()
        scheme_map[scheme.id] = cloned

    zone_map: dict[uuid.UUID, Zone] = {}
    for zone in (
        await session.execute(select(Zone).where(Zone.competition_id == source.id))
    ).scalars().all():
        cloned_zone = Zone(
            competition_id=new_cycle.id,
            name=zone.name,
            active=zone.active,
        )
        session.add(cloned_zone)
        await session.flush()
        zone_map[zone.id] = cloned_zone

    for mapping in (
        await session.execute(
            select(CompetitionRegionZone).where(CompetitionRegionZone.competition_id == source.id)
        )
    ).scalars().all():
        new_zone = zone_map.get(mapping.zone_id)
        if new_zone is None:
            continue
        session.add(
            CompetitionRegionZone(
                competition_id=new_cycle.id,
                region_id=mapping.region_id,
                zone_id=new_zone.id,
            )
        )
    await session.flush()

    skill_map: dict[uuid.UUID, Skill] = {}
    for skill in source.skills:
        cloned = Skill(
            competition_id=new_cycle.id,
            catalog_skill_id=skill.catalog_skill_id,
            name=skill.name,
            number=skill.number,
            family_id=skill.family_id,
            age_rule_id=age_map[skill.age_rule_id].id if skill.age_rule_id and skill.age_rule_id in age_map else None,
            max_age=skill.max_age,
            age_reference_date=skill.age_reference_date,
            open_category_enabled=skill.open_category_enabled,
            pathway_id=path_map[skill.pathway_id].id if skill.pathway_id and skill.pathway_id in path_map else None,
            scheme_id=scheme_map[skill.scheme_id].id if skill.scheme_id and skill.scheme_id in scheme_map else None,
            capacity=skill.capacity,
            active=skill.active,
            eligibility_rules=skill.eligibility_rules,
        )
        session.add(cloned)
        await session.flush()
        skill_map[skill.id] = cloned

    for stage in source.stages:
        remapped_qbz: dict[str, int] | None = None
        if stage.quota_by_zone:
            remapped_qbz = {}
            for old_zid, amount in stage.quota_by_zone.items():
                try:
                    old_uuid = uuid.UUID(str(old_zid))
                except ValueError:
                    continue
                new_z = zone_map.get(old_uuid)
                if new_z is not None:
                    remapped_qbz[str(new_z.id)] = int(amount)
        cloned = Stage(
            competition_id=new_cycle.id,
            skill_id=skill_map[stage.skill_id].id if stage.skill_id and stage.skill_id in skill_map else None,
            name=stage.name,
            order=stage.order,
            stage_type=stage.stage_type,
            selection_mode=stage.selection_mode,
            opens_at=stage.opens_at,
            closes_at=stage.closes_at,
            quota=stage.quota,
            quota_by_zone=remapped_qbz,
            min_score=stage.min_score,
            branch=dict(stage.branch) if stage.branch else None,
            submission_rules=dict(stage.submission_rules) if stage.submission_rules else None,
        )
        session.add(cloned)
        await session.flush()
        # Copy exercise as DRAFT (require re-publish on new cycle).
        if stage.exercise is not None:
            src_ex = stage.exercise
            session.add(
                Exercise(
                    stage_id=cloned.id,
                    competition_id=new_cycle.id,
                    title=src_ex.title,
                    brief=src_ex.brief,
                    deliverables=list(src_ex.deliverables or []),
                    status="DRAFT",
                    scheme_id=(
                        scheme_map[src_ex.scheme_id].id
                        if src_ex.scheme_id and src_ex.scheme_id in scheme_map
                        else None
                    ),
                    late_policy=src_ex.late_policy,
                    timed_duration_seconds=src_ex.timed_duration_seconds,
                    pack_object_key=src_ex.pack_object_key,
                    pack_file_name=src_ex.pack_file_name,
                    pack_content_type=src_ex.pack_content_type,
                    pack_scan_status=src_ex.pack_scan_status,
                )
            )

    await session.flush()
    await write_audit_event(
        session,
        action="COMPETITION_CLONE",
        entity_type="Competition",
        entity_id=str(new_cycle.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=new_cycle.id,
        before={"sourceCompetitionId": str(source.id)},
        after=competition_to_dict(new_cycle),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(new_cycle)
    return new_cycle


async def validate_competition(session: AsyncSession, competition_id: uuid.UUID) -> tuple[bool, list[ValidationIssue]]:
    from app.models import RegistrationFormDefinition, RegistrationWindow

    cfg = await load_competition_config(session, competition_id)
    issues: list[ValidationIssue] = []

    window = (
        await session.execute(select(RegistrationWindow).where(RegistrationWindow.competition_id == competition_id))
    ).scalar_one_or_none()
    if window is None:
        issues.append(
            ValidationIssue(
                code="CONFIG_INCOMPLETE",
                entity=str(competition_id),
                message="Registration window is not configured",
                link=f"/admin/competitions/{competition_id}#registration",
            )
        )

    form = (
        await session.execute(
            select(RegistrationFormDefinition).where(RegistrationFormDefinition.competition_id == competition_id)
        )
    ).scalar_one_or_none()
    if form is None:
        issues.append(
            ValidationIssue(
                code="CONFIG_INCOMPLETE",
                entity=str(competition_id),
                message="Registration form definition is missing",
                link=f"/admin/competitions/{competition_id}#registration",
            )
        )

    zones = list(
        (await session.execute(select(Zone).where(Zone.competition_id == competition_id, Zone.active.is_(True))))
        .scalars()
        .all()
    )
    uses_per_zone = any(
        (s.selection_mode or "PER_ZONE").upper() == "PER_ZONE" for s in cfg.stages
    )
    if uses_per_zone and not zones:
        issues.append(
            ValidationIssue(
                code="CONFIG_INCOMPLETE",
                entity=str(competition_id),
                message="Competition has PER_ZONE stages but no active zones",
                link=f"/admin/competitions/{competition_id}/zones",
            )
        )

    for skill in cfg.skills:
        has_age = skill.max_age is not None or skill.age_rule_id is not None
        if not has_age:
            issues.append(
                ValidationIssue(
                    code="CONFIG_INCOMPLETE",
                    entity=str(skill.id),
                    message=f"Skill '{skill.name}' has no age rule",
                    link=f"/admin/competitions/{competition_id}/skills/{skill.id}",
                )
            )
        skill_stages = [s for s in cfg.stages if s.skill_id == skill.id]
        if not skill_stages:
            issues.append(
                ValidationIssue(
                    code="CONFIG_INCOMPLETE",
                    entity=str(skill.id),
                    message=f"Skill '{skill.name}' has no pathway stages",
                    link=f"/admin/competitions/{competition_id}/skills/{skill.id}/pathway",
                )
            )
        else:
            for stage in skill_stages:
                mode = (stage.selection_mode or "PER_ZONE").upper()
                if mode == "NATIONAL_POOL":
                    if stage.quota is None:
                        issues.append(
                            ValidationIssue(
                                code="CONFIG_INCOMPLETE",
                                entity=str(stage.id),
                                message=f"Stage '{stage.name}' NATIONAL_POOL needs overall quota",
                                link=f"/admin/competitions/{competition_id}/skills/{skill.id}/pathway",
                            )
                        )
                elif not stage.quota_by_zone:
                    issues.append(
                        ValidationIssue(
                            code="CONFIG_INCOMPLETE",
                            entity=str(stage.id),
                            message=f"Stage '{stage.name}' PER_ZONE needs quotaByZone",
                            link=f"/admin/competitions/{competition_id}/skills/{skill.id}/pathway",
                        )
                    )
                ex = stage.exercise
                if ex is None or ex.status != "PUBLISHED" or not ex.scheme_id:
                    issues.append(
                        ValidationIssue(
                            code="CONFIG_INCOMPLETE",
                            entity=str(stage.id),
                            message=(
                                f"Stage '{stage.name}' on skill '{skill.name}' "
                                "needs a published Exercise with marking scheme"
                            ),
                            link=(
                                f"/admin/competitions/{competition_id}/skills/{skill.id}"
                                f"/stages/{stage.id}/exercise"
                            ),
                        )
                    )
        # Legacy skill-level pathway checks (optional once stages exist)
        if skill.pathway_id is None and not skill_stages:
            issues.append(
                ValidationIssue(
                    code="CONFIG_INCOMPLETE",
                    entity=str(skill.id),
                    message=f"Skill '{skill.name}' has no pathway",
                    link=f"/admin/competitions/{competition_id}/skills/{skill.id}",
                )
            )

    for stage in cfg.stages:
        ex = stage.exercise
        if ex is None or ex.status != "PUBLISHED" or not ex.scheme_id:
            issues.append(
                ValidationIssue(
                    code="EXERCISE_NOT_PUBLISHED"
                    if ex is not None and ex.status != "PUBLISHED"
                    else "CONFIG_INCOMPLETE",
                    entity=str(stage.id),
                    message=f"Stage '{stage.name}' has no published Exercise with scheme",
                    link=f"/admin/competitions/{competition_id}/stages/{stage.id}/exercise",
                )
            )
        effective_quota = stage.quota
        if effective_quota is None and stage.quota_by_zone:
            effective_quota = sum(int(v) for v in stage.quota_by_zone.values())
        if effective_quota is None:
            issues.append(
                ValidationIssue(
                    code="CONFIG_INCOMPLETE",
                    entity=str(stage.id),
                    message=f"Stage '{stage.name}' has no quota",
                    link=f"/admin/competitions/{competition_id}/stages/{stage.id}",
                )
            )

    # Quota consistency: later stage advancing more than prior stage admits
    by_skill: dict[uuid.UUID | None, list[Stage]] = {}
    for stage in cfg.stages:
        by_skill.setdefault(stage.skill_id, []).append(stage)
    for _skill_id, stages in by_skill.items():
        ordered = sorted(stages, key=lambda s: s.order)
        for i in range(1, len(ordered)):
            prior, curr = ordered[i - 1], ordered[i]
            prior_q = prior.quota
            if prior_q is None and prior.quota_by_zone:
                prior_q = sum(int(v) for v in prior.quota_by_zone.values())
            curr_q = curr.quota
            if curr_q is None and curr.quota_by_zone:
                curr_q = sum(int(v) for v in curr.quota_by_zone.values())
            if prior_q is not None and curr_q is not None and curr_q > prior_q:
                issues.append(
                    ValidationIssue(
                        code="QUOTA_INCONSISTENT",
                        entity=str(curr.id),
                        message=(
                            f"Stage '{curr.name}' quota ({curr_q}) exceeds "
                            f"upstream '{prior.name}' quota ({prior_q})"
                        ),
                        link=f"/admin/competitions/{competition_id}/stages/{curr.id}",
                    )
                )

    ok = len(issues) == 0
    return ok, issues


async def activate_competition(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Competition:
    cycle = await get_competition(session, competition_id)

    if cycle.status == CompetitionStatus.ACTIVE:
        return cycle  # idempotent

    from app.services import settings as settings_service

    if not await settings_service.allow_multiple_active_competitions(session):
        other = (
            await session.execute(
                select(Competition.id).where(
                    Competition.status == CompetitionStatus.ACTIVE,
                    Competition.id != competition_id,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if other is not None:
            raise AppError(
                "MULTIPLE_ACTIVE_NOT_ALLOWED",
                "Only one competition may be active at a time. Close or deactivate the current active competition first.",
                status_code=status.HTTP_409_CONFLICT,
            )

    ok, issues = await validate_competition(session, competition_id)
    if not ok:
        incomplete = [i for i in issues if i.code == "CONFIG_INCOMPLETE"]
        if incomplete:
            raise AppError(
                "CONFIG_INCOMPLETE",
                "Competition configuration is incomplete",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError(i.entity, i.code) for i in incomplete],
            )
        raise AppError(
            issues[0].code,
            issues[0].message,
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError(i.entity, i.code) for i in issues],
        )

    before = competition_to_dict(cycle)
    cycle.status = CompetitionStatus.ACTIVE
    await session.flush()
    await write_audit_event(
        session,
        action="COMPETITION_ACTIVATE",
        entity_type="Competition",
        entity_id=str(cycle.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=cycle.id,
        before=before,
        after=competition_to_dict(cycle),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(cycle)
    return cycle


async def update_competition_structural(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    name: str | None,
    actor: User,
) -> Competition:
    _ = actor
    cycle = await get_competition(session, competition_id)
    if name is not None:
        cycle.name = name
    await session.commit()
    await session.refresh(cycle)
    return cycle


async def competition_has_isolated_data(session: AsyncSession, cycle_a: uuid.UUID, cycle_b: uuid.UUID) -> bool:
    """True when skills from A are not visible under B (isolation check helper)."""
    a_skills = await session.execute(select(Skill.id).where(Skill.competition_id == cycle_a))
    b_skills = await session.execute(select(Skill.id).where(Skill.competition_id == cycle_b))
    a_ids = {row[0] for row in a_skills.all()}
    b_ids = {row[0] for row in b_skills.all()}
    return a_ids.isdisjoint(b_ids)
