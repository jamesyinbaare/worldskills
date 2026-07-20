"""Pure pathway engine — branching, quotas/thresholds, finalist computation, tie-break."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
    date_of_birth: date | None = None
    ref_no: str | None = None
    jury_rank: int | None = None  # lower wins when JURY_DECISION is used


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


def _tie_break_sort_key(c: Candidate, rules: Sequence[str]) -> tuple:
    """Build a multi-key sort tuple from ordered tie-break rules (ascending = better)."""
    keys: list[Any] = []
    for rule in rules:
        r = (rule or "").upper()
        if r == "SCORE_DESC":
            keys.append(-c.score)
        elif r == "YOUNGER_FIRST":
            # Later DOB (younger) ranks first; missing DOB sorts last
            if c.date_of_birth is None:
                keys.append((1, 0))
            else:
                keys.append((0, -c.date_of_birth.toordinal()))
        elif r == "REF_NO_ASC":
            keys.append(c.ref_no or "\uffff")
        elif r == "JURY_DECISION":
            keys.append(c.jury_rank if c.jury_rank is not None else 10**9)
        else:
            # Unknown rule — fall through with competitor id for stability only at end
            pass
    keys.append(c.competitor_id)
    return tuple(keys)


def sort_candidates_with_tie_break(
    candidates: Sequence[Candidate],
    *,
    tie_break_rules: Sequence[str] | None = None,
) -> list[Candidate]:
    rules = list(tie_break_rules) if tie_break_rules else ["SCORE_DESC"]
    if "SCORE_DESC" not in {r.upper() for r in rules}:
        rules = ["SCORE_DESC", *rules]
    return sorted(candidates, key=lambda c: _tie_break_sort_key(c, rules))


def has_score_tie_at_quota_boundary(
    candidates: Sequence[Candidate],
    *,
    quota_by_zone: Mapping[str, int],
    min_score: int | None,
) -> bool:
    """True when two+ candidates share a score that straddles a zone quota cut."""
    by_zone: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_zone.setdefault(c.zone_id, []).append(c)

    for zone_id, group in by_zone.items():
        eligible = [
            c for c in group if min_score is None or c.score >= min_score
        ]
        if not eligible:
            continue
        n = int(quota_by_zone.get(zone_id, 0))
        if n <= 0 or n >= len(eligible):
            continue
        by_score: dict[float, list[Candidate]] = {}
        for c in eligible:
            by_score.setdefault(c.score, []).append(c)
        # Sort scores descending; find if the nth position sits inside a tied score group
        scores_desc = sorted(by_score.keys(), reverse=True)
        remaining = n
        for score in scores_desc:
            group_at = by_score[score]
            if remaining <= 0:
                break
            if len(group_at) > 1 and remaining < len(group_at):
                return True
            if remaining <= len(group_at) and remaining > 0 and len(group_at) > 1:
                # Quota lands inside or exactly at end of a tied group — if more than remaining
                # compete for the last slots, need tie-break
                if len(group_at) > remaining:
                    return True
            remaining -= len(group_at)
    return False


def apply_quota_threshold(
    candidates: Sequence[Candidate],
    *,
    quota_by_zone: Mapping[str, int],
    min_score: int | None,
    tie_break_rules: Sequence[str] | None = None,
) -> list[Candidate]:
    """Advance competitors within per-zone top-N and optional minimum score.

    When quota exceeds available eligible competitors in a zone, advance all available.
    """
    ranked = rank_for_shortlist(
        candidates,
        quota_by_zone=quota_by_zone,
        min_score=min_score,
        tie_break_rules=tie_break_rules,
    )
    return [
        Candidate(
            competitor_id=r.competitor_id,
            zone_id=r.zone_id,
            score=r.score,
            date_of_birth=next(
                (c.date_of_birth for c in candidates if c.competitor_id == r.competitor_id), None
            ),
            ref_no=next((c.ref_no for c in candidates if c.competitor_id == r.competitor_id), None),
            jury_rank=next(
                (c.jury_rank for c in candidates if c.competitor_id == r.competitor_id), None
            ),
        )
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
    tie_break_rules: Sequence[str] | None = None,
) -> list[RankedEntry]:
    """Rank per zone; mark ADVANCE / WAITLIST / EXCLUDED (BELOW_MIN_SCORE)."""
    by_zone: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_zone.setdefault(c.zone_id, []).append(c)

    results: list[RankedEntry] = []
    for zone_id, group in by_zone.items():
        ranked = sort_candidates_with_tie_break(group, tie_break_rules=tie_break_rules)
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
