"""Public homepage live registration statistics (PII-safe aggregates)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Competitor,
    Competition,
    CompetitionStatus,
    ExpertAssignment,
    RegistrationWindow,
    Skill,
    User,
)
from app.schemas.public_portal import (
    PublicStatsCompetitionOut,
    PublicStatsExpertOut,
    PublicStatsOut,
    PublicStatsSkillOut,
    PublicStatsTotalsOut,
)

# Statuses that count as "registered" for public homepage KPIs.
REGISTERED_STATUSES = frozenset(
    {
        "PENDING_REVIEW",
        "REGISTERED",
        "ACTIVE_IN_STAGE",
        "FINALIST",
        "CONSENT_PENDING",
        "ELIGIBLE",
    }
)

# Fixed in-process rate limit for the global stats endpoint (per client key / minute).
STATS_RATE_LIMIT_PER_MINUTE = 120


async def _open_competitions(
    session: AsyncSession,
) -> list[tuple[uuid.UUID, str]]:
    """ACTIVE cycles whose registration window is currently open."""
    now = datetime.utcnow()
    result = await session.execute(
        select(Competition.id, Competition.name)
        .join(RegistrationWindow, RegistrationWindow.competition_id == Competition.id)
        .where(
            Competition.status == CompetitionStatus.ACTIVE,
            RegistrationWindow.opens_at <= now,
            RegistrationWindow.closes_at >= now,
        )
        .order_by(Competition.name)
    )
    return [(row[0], row[1]) for row in result.all()]


async def get_public_stats(session: AsyncSession) -> PublicStatsOut:
    generated_at = datetime.utcnow().isoformat() + "Z"
    open_cycles = await _open_competitions(session)
    if not open_cycles:
        return PublicStatsOut(
            generatedAt=generated_at,
            competitions=[],
            totals=PublicStatsTotalsOut(),
            skills=[],
        )

    competition_ids = [cid for cid, _ in open_cycles]
    competitions_out = [
        PublicStatsCompetitionOut(competitionId=cid, name=name) for cid, name in open_cycles
    ]

    skills_result = await session.execute(
        select(Skill)
        .where(
            Skill.competition_id.in_(competition_ids),
            Skill.active.is_(True),
        )
        .order_by(Skill.competition_id, Skill.name)
    )
    skills = list(skills_result.scalars().all())

    counts_result = await session.execute(
        select(
            Competitor.competition_id,
            Competitor.skill_id,
            func.count(Competitor.id),
        )
        .where(
            Competitor.competition_id.in_(competition_ids),
            Competitor.status.in_(REGISTERED_STATUSES),
            Competitor.skill_id.is_not(None),
        )
        .group_by(Competitor.competition_id, Competitor.skill_id)
    )
    count_by_skill: dict[tuple[uuid.UUID, uuid.UUID], int] = {
        (row[0], row[1]): int(row[2]) for row in counts_result.all() if row[1] is not None
    }

    experts_result = await session.execute(
        select(
            ExpertAssignment.competition_id,
            ExpertAssignment.skill_id,
            ExpertAssignment.expert_id,
            User.full_name,
        )
        .join(User, User.id == ExpertAssignment.expert_id)
        .where(
            ExpertAssignment.competition_id.in_(competition_ids),
            User.is_active.is_(True),
        )
        .order_by(User.full_name)
    )
    experts_by_skill: dict[tuple[uuid.UUID, uuid.UUID], dict[uuid.UUID, str]] = {}
    all_expert_ids: set[uuid.UUID] = set()
    for competition_id, skill_id, expert_id, full_name in experts_result.all():
        key = (competition_id, skill_id)
        bucket = experts_by_skill.setdefault(key, {})
        if expert_id not in bucket:
            bucket[expert_id] = full_name
            all_expert_ids.add(expert_id)

    skills_out: list[PublicStatsSkillOut] = []
    total_competitors = 0
    for skill in skills:
        key = (skill.competition_id, skill.id)
        registered = count_by_skill.get(key, 0)
        total_competitors += registered
        expert_map = experts_by_skill.get(key, {})
        experts = [
            PublicStatsExpertOut(expertId=eid, fullName=ename)
            for eid, ename in sorted(expert_map.items(), key=lambda item: item[1].lower())
        ]
        skills_out.append(
            PublicStatsSkillOut(
                competitionId=skill.competition_id,
                skillId=skill.id,
                name=skill.name,
                number=skill.number,
                competitorsRegistered=registered,
                capacity=skill.capacity,
                experts=experts,
            )
        )

    return PublicStatsOut(
        generatedAt=generated_at,
        competitions=competitions_out,
        totals=PublicStatsTotalsOut(
            competitorsRegistered=total_competitors,
            skillAreas=len(skills_out),
            expertsAssigned=len(all_expert_ids),
        ),
        skills=skills_out,
    )
