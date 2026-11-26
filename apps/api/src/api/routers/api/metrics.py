"""GET /api/metrics — aggregated turn metrics over a sliding window (turn_records + feedback +
pending_actions). Reserved route: demo mode only, else a uniform 404. Aggregates
only — the response never contains message or answer content. Percentiles: nearest-rank."""

from db.engine import get_session_maker
from fastapi import APIRouter, Query

from api.auth.dependencies import DemoModeDep
from api.metrics.service import compute_metrics
from api.schemas import MetricsView

router = APIRouter(tags=["metrics"])


@router.get("", operation_id="metrics_get")
async def get_metrics(
    _: DemoModeDep,
    window_minutes: int = Query(default=60, ge=1, le=10080),
) -> MetricsView:
    """Aggregate metrics for the last `window_minutes` (default 60); empty window -> nulls."""
    data = await compute_metrics(get_session_maker(), window_minutes)
    return MetricsView(**data)
