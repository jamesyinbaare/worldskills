"""Pure pathway engine — branching, quotas/thresholds, finalist computation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class StageNode:
    order: int
    stage_type: str
    branch: Mapping[str, Any] | None
    quota_by_zone: Mapping[str, int]
    min_score: int | None


@dataclass(frozen=True)
class Candidate:
    competitor_id: str
    zone_id: str
    score: float


def _zone_quota_total(stage: StageNode) -> int:
    return sum(int(v) for v in stage.quota_by_zone.values())


def _branch_target_orders(stage: StageNode) -> list[int]:
    if not stage.branch:
        return []
    targets: list[int] = []
    default = stage.branch.get("default")
    if default is not None:
        targets.append(int(default))
    by_family = stage.branch.get("byFamily") or {}
    for value in by_family.values():
        targets.append(int(value))
    # unique preserving order
    seen: set[int] = set()
    out: list[int] = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def resolve_next_stage(
    stages: Sequence[StageNode],
    *,
    current_order: int,
    family_id: str | None = None,
) -> StageNode:
    """Pick the next stage for a skill given branching config."""
    by_order = {s.order: s for s in stages}
    current = by_order.get(current_order)
    if current is None:
        raise KeyError(f"No stage with order {current_order}")

    target_order: int | None = None
    if current.branch:
        by_family = current.branch.get("byFamily") or {}
        if family_id and family_id in by_family:
            target_order = int(by_family[family_id])
        elif current.branch.get("default") is not None:
            target_order = int(current.branch["default"])
    if target_order is None:
        target_order = current_order + 1

    nxt = by_order.get(target_order)
    if nxt is None:
        raise KeyError(f"Branch target order {target_order} not in pathway")
    return nxt


def apply_quota_threshold(
    candidates: Sequence[Candidate],
    *,
    quota_by_zone: Mapping[str, int],
    min_score: int | None,
) -> list[Candidate]:
    """Advance competitors within per-zone top-N and optional minimum score.

    When quota exceeds available eligible competitors in a zone, advance all available.
    """
    ranked = rank_for_shortlist(candidates, quota_by_zone=quota_by_zone, min_score=min_score)
    return [
        Candidate(competitor_id=r.competitor_id, zone_id=r.zone_id, score=r.score)
        for r in ranked
        if r.outcome == "ADVANCE"
    ]


@dataclass(frozen=True)
class RankedEntry:
    competitor_id: str
    zone_id: str
    score: float
    rank: int
    outcome: str  # ADVANCE | WAITLIST | EXCLUDED
    reason: str | None = None


def rank_for_shortlist(
    candidates: Sequence[Candidate],
    *,
    quota_by_zone: Mapping[str, int],
    min_score: int | None,
) -> list[RankedEntry]:
    """Rank per zone; mark ADVANCE / WAITLIST / EXCLUDED (BELOW_MIN_SCORE)."""
    by_zone: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_zone.setdefault(c.zone_id, []).append(c)

    results: list[RankedEntry] = []
    for zone_id, group in by_zone.items():
        ranked = sorted(group, key=lambda c: (-c.score, c.competitor_id))
        n = int(quota_by_zone.get(zone_id, 0))
        advanced_count = 0
        for idx, c in enumerate(ranked, start=1):
            if min_score is not None and c.score < min_score:
                results.append(
                    RankedEntry(
                        competitor_id=c.competitor_id,
                        zone_id=c.zone_id,
                        score=c.score,
                        rank=idx,
                        outcome="EXCLUDED",
                        reason="BELOW_MIN_SCORE",
                    )
                )
                continue
            if advanced_count < n:
                results.append(
                    RankedEntry(
                        competitor_id=c.competitor_id,
                        zone_id=c.zone_id,
                        score=c.score,
                        rank=idx,
                        outcome="ADVANCE",
                        reason=None,
                    )
                )
                advanced_count += 1
            else:
                results.append(
                    RankedEntry(
                        competitor_id=c.competitor_id,
                        zone_id=c.zone_id,
                        score=c.score,
                        rank=idx,
                        outcome="WAITLIST",
                        reason=None,
                    )
                )
    return results


def compute_finalists_per_skill(stages: Sequence[StageNode]) -> int:
    """Sum zone quotas on leaf stages of the pathway graph."""
    if not stages:
        return 0
    by_order = {s.order: s for s in stages}
    branch_targets: set[int] = set()
    for s in stages:
        branch_targets.update(_branch_target_orders(s))

    def outgoing(stage: StageNode) -> list[int]:
        targets = _branch_target_orders(stage)
        if targets:
            return [t for t in targets if t in by_order]
        nxt = stage.order + 1
        # Linear continuation only when the next order is not a sibling branch arm.
        if nxt in by_order and nxt not in branch_targets:
            return [nxt]
        return []

    leaves = [s for s in stages if not outgoing(s)]
    if not leaves:
        leaves = [max(stages, key=lambda s: s.order)]
    return sum(_zone_quota_total(leaf) for leaf in leaves)