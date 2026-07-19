"""Schemas for US-STG-01 skill pathway configuration."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class StagePathwayItem(BaseModel):
    order: int = Field(ge=1)
    type: str = Field(min_length=1, max_length=64)
    schemeId: UUID
    opensAt: datetime | None = None
    closesAt: datetime | None = None
    branch: dict | None = None
    quotaByZone: dict[str, int] = Field(min_length=1)
    minScore: int | None = None

    @field_validator("type")
    @classmethod
    def type_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("REQUIRED")
        return stripped

    @field_validator("quotaByZone")
    @classmethod
    def quotas_non_negative(cls, v: dict[str, int]) -> dict[str, int]:
        if not v:
            raise ValueError("QUOTA_INVALID")
        for key, amount in v.items():
            if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
                raise ValueError("QUOTA_INVALID")
            # zone id must be parseable as UUID string
            try:
                UUID(str(key))
            except (ValueError, TypeError) as exc:
                raise ValueError("QUOTA_INVALID") from exc
        return {str(k): int(amount) for k, amount in v.items()}

    @field_validator("minScore")
    @classmethod
    def score_range(cls, v: int | None) -> int | None:
        if v is not None and (v < 0 or v > 100):
            raise ValueError("SCORE_RANGE")
        return v

    @field_validator("branch")
    @classmethod
    def branch_shape(cls, v: dict | None) -> dict | None:
        if v is None:
            return None
        if "default" not in v and "byFamily" not in v:
            raise ValueError("BRANCH_TARGET_MISSING")
        if "default" in v and v["default"] is not None:
            try:
                int(v["default"])
            except (TypeError, ValueError) as exc:
                raise ValueError("BRANCH_TARGET_MISSING") from exc
        by_family = v.get("byFamily")
        if by_family is not None:
            if not isinstance(by_family, dict):
                raise ValueError("BRANCH_TARGET_MISSING")
            for target in by_family.values():
                try:
                    int(target)
                except (TypeError, ValueError) as exc:
                    raise ValueError("BRANCH_TARGET_MISSING") from exc
        return v


class PathwayPut(BaseModel):
    stages: list[StagePathwayItem] = Field(min_length=1)
    controlledChangeReason: str | None = None

    @model_validator(mode="after")
    def orders_contiguous_unique(self) -> "PathwayPut":
        orders = sorted(s.order for s in self.stages)
        if len(orders) != len(set(orders)):
            raise ValueError("ORDER_INVALID")
        expected = list(range(1, len(orders) + 1))
        if orders != expected:
            raise ValueError("ORDER_INVALID")
        return self


class StageOut(BaseModel):
    stageId: UUID
    order: int
    type: str
    schemeId: UUID | None = None
    opensAt: datetime | None = None
    closesAt: datetime | None = None
    branch: dict | None = None
    quotaByZone: dict[str, int] | None = None
    minScore: int | None = None
    quota: int | None = None


class PathwayOut(BaseModel):
    stages: list[StageOut]
    finalistsPerSkill: int
