"""Aggregate turn metrics over a sliding window, computed in Python from turn_records.

Percentile method: NEAREST-RANK. Sort the sample ascending and take the value at 1-based rank
ceil(p/100 * n) — i.e. the smallest value whose cumulative share of the sample is >= p. With an
empty sample every percentile is null (an empty window answers nulls, never an error).

The response is aggregates only: no message or answer content ever leaves this module.
End-to-end latency per turn is the sum of the per-stage timings EXCLUDING the
"guardrails+classification (parallel)" group, which overlaps the moderation+classification
stages it summarises.
"""

import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from db import accessors as acc

STAGES = ("moderation", "classification", "agent_faq", "agent_account", "agent_action", "output_check")
PARALLEL_STAGE = "guardrails+classification (parallel)"


def percentile_nearest_rank(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile of `values` at p (0-100); None on an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return round(ordered[rank - 1], 1)


def _latency_block(samples: list[float]) -> dict:
    return {
        "p50": percentile_nearest_rank(samples, 50),
        "p95": percentile_nearest_rank(samples, 95),
        "n": len(samples),
    }


async def compute_metrics(session_maker, window_minutes: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    async with session_maker() as session:
        turns = await acc.turn_records.list_since(session, since)
        rated, down = await acc.feedback.count_since(session, since)
        actions = await acc.pending_actions.list_since(session, since)

    total = len(turns)
    by_intent = Counter(t.intent for t in turns)
    refused = sum(1 for t in turns if t.refused)
    offers = sum(1 for t in turns if t.human_offer)
    errors = sum(1 for t in turns if t.error)

    stage_samples: dict[str, list[float]] = {stage: [] for stage in STAGES}
    e2e_samples: list[float] = []
    for turn in turns:
        try:
            timings = json.loads(turn.timings or "[]")
        except Exception:
            timings = []
        turn_total = 0.0
        for entry in timings:
            stage = entry.get("stage")
            ms = entry.get("ms") or 0.0
            if stage == PARALLEL_STAGE:
                continue  # overlaps moderation + classification; excluded from the e2e sum
            turn_total += ms
            if stage in stage_samples:
                stage_samples[stage].append(ms)
        e2e_samples.append(turn_total)

    status_counts = Counter(a.status for a in actions)
    return {
        "window_minutes": window_minutes,
        "since": since,
        "turns_total": total,
        "by_intent": dict(by_intent),
        "refused_rate": (refused / total) if total else None,
        "human_offer_rate": (offers / total) if total else None,
        "error_rate": (errors / total) if total else None,
        "downvotes_rated": rated,
        "downvotes_down": down,
        "downvote_rate": (down / rated) if rated else None,
        "latency_ms": {stage: _latency_block(stage_samples[stage]) for stage in STAGES},
        "end_to_end_ms": _latency_block(e2e_samples),
        "actions": {
            "proposed": len(actions),
            "pending": status_counts.get("pending", 0),
            "confirmed": status_counts.get("confirmed", 0),
            "cancelled": status_counts.get("cancelled", 0),
            "expired": status_counts.get("expired", 0),
        },
        "method": "nearest-rank",
    }
