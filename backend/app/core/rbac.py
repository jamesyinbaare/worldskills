"""RBAC capabilities, segregation of duties, and conflict-of-interest primitives."""

from __future__ import annotations

from enum import Enum

from app.models import UserRole


class Capability(str, Enum):
    CONFIGURE_CYCLE = "configure_cycle"
    PUBLISH_TEST_PROJECT = "publish_test_project"
    SCORE_SUBMISSION = "score_submission"
    MODERATE_SCORE = "moderate_score"
    APPROVE_SHORTLIST = "approve_shortlist"
    NOMINATE_COMPETITOR = "nominate_competitor"
    REGISTER_SUBMIT = "register_submit"
    RULE_ON_APPEAL = "rule_on_appeal"
    PUBLISH_RESULTS = "publish_results"


# plan.md RBAC matrix (default roles) + US-RES-01 publish results (Secretariat Admin)
_ROLE_CAPABILITIES: dict[UserRole, set[Capability]] = {
    UserRole.SUPER_ADMIN: set(Capability),
    UserRole.ADMIN: {
        Capability.CONFIGURE_CYCLE,
        Capability.PUBLISH_TEST_PROJECT,
        Capability.APPROVE_SHORTLIST,
        Capability.RULE_ON_APPEAL,
        Capability.PUBLISH_RESULTS,
        Capability.MODERATE_SCORE,
    },
    UserRole.CHIEF_EXPERT: {
        Capability.PUBLISH_TEST_PROJECT,
        Capability.SCORE_SUBMISSION,
        Capability.MODERATE_SCORE,
        Capability.APPROVE_SHORTLIST,
    },
    UserRole.EXPERT: {Capability.SCORE_SUBMISSION},
    UserRole.MODERATOR: {Capability.MODERATE_SCORE},
    UserRole.INSTITUTION: {Capability.NOMINATE_COMPETITOR},
    UserRole.COMPETITOR: {Capability.REGISTER_SUBMIT},
    UserRole.APPEALS_OFFICER: {Capability.RULE_ON_APPEAL},
}


def has_capability(role: UserRole, capability: Capability) -> bool:
    return capability in _ROLE_CAPABILITIES.get(role, set())


def is_admin_role(role: UserRole) -> bool:
    return role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}


def check_segregation_of_duties(*, scorer_id: str, moderator_id: str) -> bool:
    """Return True if SoD is satisfied (different actors)."""
    return scorer_id != moderator_id


def check_conflict_of_interest(
    *,
    expert_institution_id: str | None,
    competitor_institution_id: str | None,
) -> bool:
    """Return True if there is a conflict of interest."""
    if expert_institution_id is None or competitor_institution_id is None:
        return False
    return expert_institution_id == competitor_institution_id
