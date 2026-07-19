"""Cycle configuration resolution — fail closed with CONFIG_INCOMPLETE."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AppError, FieldError
from app.models import AgeRule, Cycle, MarkingScheme, Pathway, Skill, Stage


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
class CycleConfig:
    cycle: Cycle
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

    def age_rule_for_skill(self, skill_id: uuid.UUID) -> AgeRule:
        skill = self.skill(skill_id)
        rule_id = self.require("ageRuleId", skill.age_rule_id, entity=str(skill_id))
        rule = self.age_rules.get(rule_id)
        if rule is None:
            raise ConfigIncompleteError(f"Age rule missing for skill {skill_id}", entity=str(skill_id))
        return rule


async def load_cycle_config(session: AsyncSession, cycle_id: uuid.UUID) -> CycleConfig:
    stmt = (
        select(Cycle)
        .where(Cycle.id == cycle_id)
        .options(
            selectinload(Cycle.skills),
            selectinload(Cycle.stages),
            selectinload(Cycle.age_rules),
            selectinload(Cycle.pathways),
            selectinload(Cycle.marking_schemes),
        )
    )
    result = await session.execute(stmt)
    cycle = result.scalar_one_or_none()
    if cycle is None:
        raise AppError("CYCLE_NOT_FOUND", "Cycle not found", status_code=status.HTTP_404_NOT_FOUND)

    return CycleConfig(
        cycle=cycle,
        skills=list(cycle.skills),
        stages=list(cycle.stages),
        age_rules={r.id: r for r in cycle.age_rules},
        pathways={p.id: p for p in cycle.pathways},
        schemes={s.id: s for s in cycle.marking_schemes},
    )


def config(cycle_id: uuid.UUID) -> str:
    """Opaque handle style used in plan.md examples; real loading via load_cycle_config."""
    return str(cycle_id)
