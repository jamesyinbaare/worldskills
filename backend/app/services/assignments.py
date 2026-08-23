"""Expert assignment, COI filtering, and segregation-of-duties enforcement."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, FieldError
from app.core.rbac import check_conflict_of_interest, check_segregation_of_duties
from app.models import (
    Competition,
    Competitor,
    ExpertAssignment,
    ExpertSkillArea,
    Score,
    Skill,
    Submission,
    User,
    UserRole,
    Zone,
)
from app.schemas.assignments import (
    AssignmentCreate,
    AssessorQueueOut,
    CoiFlagOut,
    MyAssignmentOut,
    QueueSubmissionOut,
)
from app.services.audit import write_audit_event

_ASSIGNABLE_ROLES = {UserRole.EXPERT, UserRole.CHIEF_EXPERT}


async def list_assignments(
    session: AsyncSession,
    competition_id: uuid.UUID,
    *,
    cycle_skill_id: uuid.UUID | None = None,
) -> list[ExpertAssignment]:
    stmt = select(ExpertAssignment).where(ExpertAssignment.competition_id == competition_id)
    if cycle_skill_id is not None:
        stmt = stmt.where(ExpertAssignment.skill_id == cycle_skill_id)
    result = await session.execute(stmt.order_by(ExpertAssignment.created_at.desc()))
    return list(result.scalars().all())


async def list_my_assignments(session: AsyncSession, *, actor: User) -> list[MyAssignmentOut]:
    """Named assignments for the signed-in expert (portal discovery via catalog skill areas)."""
    if actor.role not in _ASSIGNABLE_ROLES:
        raise AppError(
            "FORBIDDEN",
            "Only experts can list their assignments",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    catalog_ids = (
        await session.execute(
            select(ExpertSkillArea.catalog_skill_id).where(ExpertSkillArea.expert_id == actor.id)
        )
    ).scalars().all()
    if not catalog_ids:
        return []

    skills = (
        await session.execute(
            select(Skill)
            .where(
                Skill.catalog_skill_id.in_(list(catalog_ids)),
                Skill.active.is_(True),
            )
            .order_by(Skill.name)
        )
    ).scalars().all()

    out: list[MyAssignmentOut] = []
    for skill in skills:
        competition = await session.get(Competition, skill.competition_id)
        if competition is None:
            continue
        # Synthetic id: stable per competition+skill for portal keys
        synthetic = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"expert-skill:{actor.id}:{skill.competition_id}:{skill.id}",
        )
        out.append(
            MyAssignmentOut(
                assignmentId=synthetic,
                competitionId=competition.id,
                competitionName=competition.name,
                skillId=skill.id,
                skillName=skill.name,
                zoneId=None,
                zoneName="All zones",
            )
        )

    out.sort(key=lambda a: (a.competitionName.lower(), a.skillName.lower()))
    return out


def _assignment_to_dict(assignment: ExpertAssignment) -> dict[str, Any]:
    return {
        "id": str(assignment.id),
        "competitionId": str(assignment.competition_id),
        "expertId": str(assignment.expert_id),
        "skillId": str(assignment.skill_id),
        "zoneId": str(assignment.zone_id) if assignment.zone_id else None,
        "coiFlags": assignment.coi_flags or [],
    }


async def _compute_coi_flags(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    skill_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    expert: User,
) -> list[dict[str, Any]]:
    if expert.institution_id is None:
        return []

    stmt = select(Competitor).where(
        Competitor.competition_id == competition_id,
        Competitor.skill_id == skill_id,
        Competitor.institution_id == expert.institution_id,
    )
    if zone_id is not None:
        stmt = stmt.where(Competitor.zone_id == zone_id)
    result = await session.execute(stmt)
    conflicted = list(result.scalars().all())
    if not conflicted:
        # Still persist the institutional COI relationship even if no competitors yet
        return [
            {
                "institutionId": str(expert.institution_id),
                "reason": "SAME_INSTITUTION",
                "competitorIds": [],
            }
        ]

    return [
        {
            "institutionId": str(expert.institution_id),
            "reason": "SAME_INSTITUTION",
            "competitorIds": [str(c.id) for c in conflicted],
        }
    ]


def coi_flags_out(raw: list[dict[str, Any]] | None) -> list[CoiFlagOut]:
    flags: list[CoiFlagOut] = []
    for item in raw or []:
        flags.append(
            CoiFlagOut(
                institutionId=uuid.UUID(str(item["institutionId"])),
                reason=str(item.get("reason", "SAME_INSTITUTION")),
                competitorIds=[uuid.UUID(str(c)) for c in item.get("competitorIds", [])],
            )
        )
    return flags


async def _load_assignable_expert(session: AsyncSession, expert_id: uuid.UUID) -> User:
    expert = await session.get(User, expert_id)
    if (
        expert is None
        or not expert.is_active
        or expert.role not in _ASSIGNABLE_ROLES
    ):
        raise AppError(
            "INVALID_ASSIGNMENT",
            "Expert account is invalid or inactive",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("expertId", "INVALID_ASSIGNMENT")],
        )
    return expert


async def _load_active_skill(session: AsyncSession, competition_id: uuid.UUID, skill_id: uuid.UUID) -> Skill:
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.competition_id != competition_id or not skill.active:
        raise AppError(
            "INVALID_ASSIGNMENT",
            "Skill is invalid or inactive in this competition",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("skillId", "INVALID_ASSIGNMENT")],
        )
    return skill


async def _load_active_zone(session: AsyncSession, competition_id: uuid.UUID, zone_id: uuid.UUID) -> Zone:
    zone = await session.get(Zone, zone_id)
    if zone is None or zone.competition_id != competition_id or not zone.active:
        raise AppError(
            "INVALID_ASSIGNMENT",
            "Zone is invalid or inactive in this competition",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            fields=[FieldError("zoneId", "INVALID_ASSIGNMENT")],
        )
    return zone


async def create_assignment(
    session: AsyncSession,
    competition_id: uuid.UUID,
    payload: AssignmentCreate,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ExpertAssignment:
    expert = await _load_assignable_expert(session, payload.expertId)
    skill = await _load_active_skill(session, competition_id, payload.resolved_skill_id)
    if payload.zoneId is not None:
        await _load_active_zone(session, competition_id, payload.zoneId)

    if skill.catalog_skill_id is not None:
        from app.services import expert_skill_areas as expert_skill_areas_service

        has_area = await expert_skill_areas_service.expert_has_catalog_skill(
            session, expert_id=expert.id, catalog_skill_id=skill.catalog_skill_id
        )
        if not has_area:
            raise AppError(
                "INVALID_ASSIGNMENT",
                "Expert is not assigned to this catalog skill area",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                fields=[FieldError("expertId", "INVALID_ASSIGNMENT")],
            )

    # Reject mixing all-zones with a specific zone for the same expert+skill
    existing_rows = (
        await session.execute(
            select(ExpertAssignment).where(
                ExpertAssignment.competition_id == competition_id,
                ExpertAssignment.expert_id == payload.expertId,
                ExpertAssignment.skill_id == payload.resolved_skill_id,
            )
        )
    ).scalars().all()
    for row in existing_rows:
        if row.zone_id == payload.zoneId:
            raise AppError(
                "INVALID_ASSIGNMENT",
                "Assignment already exists",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("expertId", "DUPLICATE")],
            )
        if row.zone_id is None or payload.zoneId is None:
            raise AppError(
                "INVALID_ASSIGNMENT",
                "Cannot mix all-zones and zone-specific assignments for the same skill",
                status_code=status.HTTP_409_CONFLICT,
                fields=[FieldError("zoneId", "CONFLICT")],
            )

    flags = await _compute_coi_flags(
        session,
        competition_id=competition_id,
        skill_id=payload.resolved_skill_id,
        zone_id=payload.zoneId,
        expert=expert,
    )
    assignment = ExpertAssignment(
        competition_id=competition_id,
        expert_id=payload.expertId,
        skill_id=payload.resolved_skill_id,
        zone_id=payload.zoneId,
        coi_flags=flags,
    )
    session.add(assignment)
    await session.flush()

    await write_audit_event(
        session,
        action="ASSIGNMENT_CREATE",
        entity_type="ExpertAssignment",
        entity_id=str(assignment.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        after=_assignment_to_dict(assignment),
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(assignment)
    return assignment


async def delegate_assignment(
    session: AsyncSession,
    competition_id: uuid.UUID,
    assignment_id: uuid.UUID,
    new_expert_id: uuid.UUID,
    *,
    actor: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> ExpertAssignment:
    assignment = await session.get(ExpertAssignment, assignment_id)
    if assignment is None or assignment.competition_id != competition_id:
        raise AppError(
            "ASSIGNMENT_NOT_FOUND",
            "Assignment not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    new_expert = await _load_assignable_expert(session, new_expert_id)
    before = _assignment_to_dict(assignment)

    flags = await _compute_coi_flags(
        session,
        competition_id=competition_id,
        skill_id=assignment.skill_id,
        zone_id=assignment.zone_id,
        expert=new_expert,
    )
    assignment.expert_id = new_expert_id
    assignment.coi_flags = flags
    await session.flush()

    await write_audit_event(
        session,
        action="ASSIGNMENT_DELEGATE",
        entity_type="ExpertAssignment",
        entity_id=str(assignment.id),
        actor_id=actor.id,
        actor_role=actor.role.value,
        competition_id=competition_id,
        before=before,
        after=_assignment_to_dict(assignment),
        reason="Expert unavailable — queue delegated",
        ip=ip,
        user_agent=user_agent,
    )
    await session.commit()
    await session.refresh(assignment)
    return assignment


async def get_assessor_queue(
    session: AsyncSession,
    competition_id: uuid.UUID,
    expert_id: uuid.UUID,
) -> AssessorQueueOut:
    from app.models import MarkingScheme, Skill, Stage
    from app.services import expert_skill_areas as expert_skill_areas_service

    catalog_ids = await expert_skill_areas_service.list_catalog_skill_ids_for_expert(
        session, expert_id
    )
    if not catalog_ids:
        return AssessorQueueOut(submissions=[], items=[])

    skills = (
        await session.execute(
            select(Skill).where(
                Skill.competition_id == competition_id,
                Skill.catalog_skill_id.in_(catalog_ids),
                Skill.active.is_(True),
            )
        )
    ).scalars().all()
    if not skills:
        return AssessorQueueOut(submissions=[], items=[])

    # Optional zone restrictions from competition bookkeeping assignments
    assignments = (
        await session.execute(
            select(ExpertAssignment).where(
                ExpertAssignment.competition_id == competition_id,
                ExpertAssignment.expert_id == expert_id,
            )
        )
    ).scalars().all()
    zone_by_skill: dict[uuid.UUID, set[uuid.UUID | None]] = {}
    for a in assignments:
        zone_by_skill.setdefault(a.skill_id, set()).add(a.zone_id)

    expert = await session.get(User, expert_id)
    expert_institution = expert.institution_id if expert else None

    submissions_out: list[QueueSubmissionOut] = []

    for skill in skills:
        skill_id = skill.id
        blind = False
        if skill.scheme_id:
            scheme = await session.get(MarkingScheme, skill.scheme_id)
            if scheme and isinstance(scheme.rubric, dict):
                blind = bool(scheme.rubric.get("blindMode", False))

        allowed_zones = zone_by_skill.get(skill_id)
        comps_stmt = select(Competitor).where(
            Competitor.competition_id == competition_id,
            Competitor.skill_id == skill_id,
        )
        comps = (await session.execute(comps_stmt)).scalars().all()
        for comp in comps:
            if allowed_zones is not None:
                # None in set means all zones; otherwise require exact zone match
                if None not in allowed_zones and comp.zone_id not in allowed_zones:
                    continue
            if check_conflict_of_interest(
                expert_institution_id=str(expert_institution) if expert_institution else None,
                competitor_institution_id=str(comp.institution_id) if comp.institution_id else None,
            ):
                continue
            # Only scoreable states — must match assessment._SCOREABLE_STATES
            subs = (
                await session.execute(
                    select(Submission).where(
                        Submission.competition_id == competition_id,
                        Submission.competitor_id == comp.id,
                        Submission.state.in_(["ACCEPTED", "LATE"]),
                    )
                )
            ).scalars().all()
            for sub in subs:
                anon = sub.anon_code
                if not anon:
                    anon = f"A-{(comp.ref_no or str(comp.id))[-8:].upper()}"
                    sub.anon_code = anon
                # Prefer stage scheme blind flag if stage linked
                item_blind = blind
                if sub.stage_id:
                    from app.models import Exercise

                    ex = (
                        await session.execute(
                            select(Exercise).where(Exercise.stage_id == sub.stage_id)
                        )
                    ).scalar_one_or_none()
                    if ex and ex.scheme_id:
                        stage_scheme = await session.get(MarkingScheme, ex.scheme_id)
                        if stage_scheme and isinstance(stage_scheme.rubric, dict):
                            item_blind = bool(stage_scheme.rubric.get("blindMode", False))
                submissions_out.append(
                    QueueSubmissionOut(
                        submissionId=sub.id,
                        competitorId=None if item_blind else comp.id,
                        anonCode=anon,
                        state=sub.state,
                    )
                )

    await session.flush()
    return AssessorQueueOut(submissions=submissions_out, items=submissions_out)


async def assert_can_score(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    expert: User,
    competitor: Competitor,
    submission_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Refuse scoring when expert and competitor share a COI institution (US-SEC-01-AC2)."""
    if check_conflict_of_interest(
        expert_institution_id=str(expert.institution_id) if expert.institution_id else None,
        competitor_institution_id=str(competitor.institution_id) if competitor.institution_id else None,
    ):
        await write_audit_event(
            session,
            action="SCORE_REFUSED_COI",
            entity_type="Submission",
            entity_id=str(submission_id or competitor.id),
            actor_id=expert.id,
            actor_role=expert.role.value,
            competition_id=competition_id,
            after={
                "expertId": str(expert.id),
                "competitorId": str(competitor.id),
                "reason": "SAME_INSTITUTION",
            },
            reason="CONFLICT_OF_INTEREST",
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise AppError(
            "CONFLICT_OF_INTEREST",
            "Expert may not score a competitor from their own institution",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("competitorId", "CONFLICT_OF_INTEREST")],
        )


async def assert_can_moderate(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    score: Score,
    moderator: User,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Refuse moderation when moderator scored the same score (US-SEC-01-AC3)."""
    if not check_segregation_of_duties(
        scorer_id=str(score.assessor_id),
        moderator_id=str(moderator.id),
    ):
        await write_audit_event(
            session,
            action="MODERATE_REFUSED_SOD",
            entity_type="Score",
            entity_id=str(score.id),
            actor_id=moderator.id,
            actor_role=moderator.role.value,
            competition_id=competition_id,
            after={"scorerId": str(score.assessor_id), "moderatorId": str(moderator.id)},
            reason="SEGREGATION_VIOLATION",
            ip=ip,
            user_agent=user_agent,
        )
        await session.commit()
        raise AppError(
            "SEGREGATION_VIOLATION",
            "Scorer may not moderate their own score",
            status_code=status.HTTP_409_CONFLICT,
            fields=[FieldError("scoreId", "SEGREGATION_VIOLATION")],
        )
