from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.dependencies.auth import AdminUserDep, client_meta
from app.dependencies.database import DBSessionDep
from app.models import Skill
from app.schemas.skills import SkillCreate, SkillOut
from app.services import skills as skill_service

router = APIRouter(prefix="/cycles", tags=["skills"])


def _skill_out(skill: Skill) -> SkillOut:
    return SkillOut(
        skillId=skill.id,
        cycleId=skill.cycle_id,
        name=skill.name,
        number=skill.number,
        familyId=skill.family_id,
        ageRuleId=skill.age_rule_id,
        pathwayId=skill.pathway_id,
        schemeId=skill.scheme_id,
        capacity=skill.capacity,
        active=skill.active,
    )


@router.get("/{cycle_id}/skills", response_model=list[SkillOut])
async def list_skills(
    cycle_id: uuid.UUID,
    session: DBSessionDep,
    admin: AdminUserDep,
) -> list[SkillOut]:
    _ = admin
    skills = await skill_service.list_skills(session, cycle_id)
    return [_skill_out(s) for s in skills]


@router.post("/{cycle_id}/skills", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def create_skill(
    cycle_id: uuid.UUID,
    payload: SkillCreate,
    session: DBSessionDep,
    admin: AdminUserDep,
    request: Request,
) -> SkillOut:
    ip, ua = client_meta(request)
    skill = await skill_service.create_skill(
        session, cycle_id, payload, actor=admin, ip=ip, user_agent=ua
    )
    return _skill_out(skill)
