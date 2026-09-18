"""Viterbi decoding with optional sliding window."""

from __future__ import annotations

from math import exp, inf, log

from .emission import emission_log_probability
from .road_graph import RoadNetwork
from .transition import transition_log_probability
from .types import NavigationState, RoadCandidate


def viterbi_decode(
    states: list[NavigationState],
    candidate_sets: list[list[RoadCandidate]],
    network: RoadNetwork,
) -> tuple[list[RoadCandidate | None], list[float]]:
    """Return best candidate per timestep and path log-score at each step.

    Empty candidate sets yield None at that timestep (fail-safe / off-road).
    """
    n = len(states)
    if n == 0:
        return [], []
    if len(candidate_sets) != n:
        raise ValueError("states and candidate_sets length mismatch")

    # Find first non-empty
    path: list[RoadCandidate | None] = [None] * n
    path_scores = [-inf] * n

    # Dynamic programming tables per time: list of scores / backpointers
    scores: list[list[float]] = []
    backptr: list[list[int]] = []

    for t in range(n):
        cands = candidate_sets[t]
        if not cands:
            scores.append([])
            backptr.append([])
            continue

        if t == 0 or not scores[t - 1]:
            # Restart chain after gap / start
            cur_scores = [emission_log_probability(states[t], c) for c in cands]
            cur_bp = [-1] * len(cands)
        else:
            prev_cands = candidate_sets[t - 1]
            cur_scores = []
            cur_bp = []
            for cur in cands:
                best = -inf
                best_j = -1
                emit = emission_log_probability(states[t], cur)
                for j, prev in enumerate(prev_cands):
                    score = (
                        scores[t - 1][j]
                        + transition_log_probability(
                            states[t - 1], states[t], prev, cur, network
                        )
                        + emit
                    )
                    if score > best:
                        best = score
                        best_j = j
                cur_scores.append(best)
                cur_bp.append(best_j)
        scores.append(cur_scores)
        backptr.append(cur_bp)

    # Backtrack contiguous segments ending at last non-empty
    t = n - 1
    while t >= 0:
        if not scores[t]:
            t -= 1
            continue
        # find start of this contiguous non-empty run
        start = t
        while start > 0 and scores[start - 1]:
            start -= 1
        best_i = max(range(len(scores[t])), key=lambda i: scores[t][i])
        path_scores[t] = scores[t][best_i]
        for k in range(t, start - 1, -1):
            path[k] = candidate_sets[k][best_i]
            path_scores[k] = scores[k][best_i]
            best_i = backptr[k][best_i]
            if best_i < 0:
                break
        t = start - 1

    return path, path_scores


def logsumexp(values: list[float]) -> float:
    if not values:
        return -inf
    m = max(values)
    if m == -inf:
        return -inf
    return m + log(sum(exp(v - m) for v in values))


def candidate_confidence(
    state: NavigationState,
    matched: RoadCandidate,
    candidates: list[RoadCandidate],
) -> float:
    """Softmax weight of the matched candidate among current emissions.

    Not 1.0 merely because a candidate exists.
    """
    if matched is None or not candidates:
        return 0.0
    scores = [emission_log_probability(state, c) for c in candidates]
    matched_score = emission_log_probability(state, matched)
    return float(exp(matched_score - logsumexp(scores)))
