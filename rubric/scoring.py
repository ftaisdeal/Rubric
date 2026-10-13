"""Weighted total calculation. No UI or storage dependencies."""

from collections.abc import Mapping, Sequence

from .rubric import CRITERIA, MAX_SCORE, MIN_SCORE, Criterion


def total_score(
    scores: Mapping[str, int],
    weights: Mapping[str, float] | None = None,
    criteria: Sequence[Criterion] = CRITERIA,
) -> float | None:
    """Return the weighted total on a 0-100 scale, or None if incomplete.

    All 1s give 0 and all 5s give 100. Scores for ids that aren't in
    `criteria` are ignored; a criterion with no valid score makes the idea
    incomplete. `weights` (percentages by criterion id) override each
    criterion's default weight.
    """
    weights = weights or {}
    total_weight = sum(weights.get(c.id, c.weight) for c in criteria)
    if total_weight <= 0:
        return None
    weighted = 0.0
    for c in criteria:
        score = scores.get(c.id)
        if not isinstance(score, int) or not MIN_SCORE <= score <= MAX_SCORE:
            return None
        weighted += weights.get(c.id, c.weight) * (score - MIN_SCORE) / (MAX_SCORE - MIN_SCORE)
    return 100 * weighted / total_weight
