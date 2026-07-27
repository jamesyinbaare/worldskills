"""Competition configuration resolution — fail closed with CONFIG_INCOMPLETE."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, FieldError
from app.models import AgeRule, Competition, MarkingScheme, Pathway, Skill, Stage


class ConfigIncompleteError(AppError):
    def __init__(self, message: str, *, entity: str | None = None) -> None:
        fields = [FieldError(entity, "CONFIG_INCOMPLETE")] if entity else []
        super().__init__(
            "CONFIG_INCOMPLETE",
            message,
            status_code=status.HTTP_409_CONFLICT,
            fields=fields,
        )


@dataclass
class ResolvedAgeRule:
    """Age rule resolved for a competition skill (embedded or legacy AgeRule row)."""

    max_age: int
    reference_date: Any
    open_category_enabled: bool


@dataclass
class CycleConfig:
    cycle: Competition
    skills: list[Skill]
    stages: list[Stage]
    age_rules: dict[uuid.UUID, AgeRule]
    pathways: dict[uuid.UUID, Pathway]
    schemes: dict[uuid.UUID, MarkingScheme]

    def require(self, key: str, value: Any, *, entity: str | None = None) -> Any:
        if value is None or value == "" or value == []:
            raise ConfigIncompleteError(f"Missing required config value: {key}", entity=entity or key)
        return value

    def skill(self, skill_id: uuid.UUID) -> Skill:
        for s in self.skills:
            if s.id == skill_id:
                return s
        raise ConfigIncompleteError(f"Skill {skill_id} not found in cycle config", entity=str(skill_id))

    def age_rule_for_skill(self, skill_id: uuid.UUID) -> ResolvedAgeRule | AgeRule:
        skill = self.skill(skill_id)
        # Preferred: embedded per-cycle-skill age rule
        if skill.max_age is not None:
            return ResolvedAgeRule(
                max_age=skill.max_age,
                reference_date=skill.age_reference_date,
                open_category_enabled=bool(skill.open_category_enabled)
                if skill.open_category_enabled is not None
                else False,
            )
        # Legacy: shared cycle AgeRule via FK
        rule_id = self.require("ageRuleId", skill.age_rule_id, entity=str(skill_id))
        rule = self.age_rules.get(rule_id)
        if rule is None:
            raise ConfigIncompleteError(f"Age rule missing for skill {skill_id}", entity=str(skill_id))
        return rule

    def stages_for_skill(self, skill_id: uuid.UUID) -> list[Stage]:
        return sorted(
            [s for s in self.stages if s.skill_id == skill_id],
            key=lambda s: s.order,
        )

    def stage(self, skill_id: uuid.UUID, order: int) -> Stage:
        for s in self.stages_for_skill(skill_id):
            if s.order == order:
                return s
        raise ConfigIncompleteError(
            f"Stage order {order} missing for skill {skill_id}",
            entity=str(skill_id),
        )

    def quota_by_zone(self, skill_id: uuid.UUID, order: int) -> dict[str, int]:
        stage = self.stage(skill_id, order)
        if stage.quota_by_zone:
            return {str(k): int(v) for k, v in stage.quota_by_zone.items()}
        if stage.quota is not None:
            # Legacy scalar quota — fail closed for per-zone resolution
            raise ConfigIncompleteError(
                f"Stage order {order} has no quotaByZone for skill {skill_id}",
                entity=str(stage.id),
            )
        raise ConfigIncompleteError(
            f"Stage order {order} has no quota for skill {skill_id}",
            entity=str(stage.id),
        )


async def load_competition_config(session: AsyncSession, competition_id: uuid.UUID) -> CompetitionConfig:
    stmt = (
        select(Competition)
        .where(Competition.id == competition_id)
        .options(
            selectinload(Competition.skills),
            selectinload(Competition.stages).selectinload(Stage.exercise),
            selectinload(Competition.age_rules),
            selectinload(Competition.pathways),
            selectinload(Competition.marking_schemes),
        )
    )
    result = await session.execute(stmt)
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("COMPETITION_NOT_FOUND", "Competition not found", status_code=status.HTTP_404_NOT_FOUND)

    return CycleConfig(
        cycle=cycle,
        skills=list(cycle.skills),
        stages=list(cycle.stages),
        age_rules={r.id: r for r in cycle.age_rules},
        pathways={p.id: p for p in cycle.pathways},
        schemes={s.id: s for s in cycle.marking_schemes},
    )


def config(competition_id: uuid.UUID) -> str:
    """Opaque handle style used in plan.md examples; real loading via load_competition_config."""
    return str(competition_id)
