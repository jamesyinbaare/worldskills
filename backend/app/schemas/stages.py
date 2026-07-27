"""Schemas for US-STG-01 skill pathway configuration."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class StagePathwayItem(BaseModel):
    order: int = Field(ge=1)
    type: str = Field(min_length=1, max_length=64)
    selectionMode: str = Field(default="PER_ZONE")
    # Deprecated: marking scheme now lives on Exercise (US-SUB-01). Ignored if sent.
    schemeId: UUID | None = None
    opensAt: datetime | None = None
    closesAt: datetime | None = None
    branch: dict | None = None
    quotaByZone: dict[str, int] | None = None
    quota: int | None = Field(default=None, ge=0)
    minScore: int | None = None

    @field_validator("type")
    @classmethod
    def type_virtual_or_physical(cls, v: str) -> str:
        stripped = v.strip().upper()
        if not stripped:
            raise ValueError("REQUIRED")
        if stripped not in {"VIRTUAL", "PHYSICAL"}:
            raise ValueError("INVALID_TYPE")
        return stripped

    @field_validator("selectionMode")
    @classmethod
    def selection_mode_valid(cls, v: str) -> str:
        mode = (v or "PER_ZONE").strip().upper()
        if mode not in {"PER_ZONE", "NATIONAL_POOL"}:
            raise ValueError("INVALID_SELECTION_MODE")
        return mode

    @field_validator("quotaByZone")
    @classmethod
    def quotas_non_negative(cls, v: dict[str, int] | None) -> dict[str, int] | None:
        if v is None:
            return None
        if not v:
            raise ValueError("QUOTA_INVALID")
        for key, amount in v.items():
            if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
                raise ValueError("QUOTA_INVALID")
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

    @model_validator(mode="after")
    def quota_for_selection_mode(self) -> "StagePathwayItem":
        mode = self.selectionMode
        if mode == "PER_ZONE":
            if not self.quotaByZone:
                raise ValueError("QUOTA_INVALID")
        elif mode == "NATIONAL_POOL":
            if self.quota is None:
                raise ValueError("QUOTA_INVALID")
        return self


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
    selectionMode: str
    schemeId: UUID | None = None  # from published Exercise when present
    exerciseStatus: str | None = None  # DRAFT | PUBLISHED | None
    opensAt: datetime | None = None
    closesAt: datetime | None = None
    branch: dict | None = None
    quotaByZone: dict[str, int] | None = None
    minScore: int | None = None
    quota: int | None = None


class PathwayOut(BaseModel):
    stages: list[StageOut]
    finalistsPerSkill: int
