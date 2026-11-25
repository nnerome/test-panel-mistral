"""GET /api/feedback/recent — reserved route (demo mode or X-Admin-Token): recent feedback rows,
optionally filtered by rating. Aggregates for review; excerpts stay in the DB for the export
script rather than being echoed back here."""

from typing import Literal

from db import accessors as acc
from db.engine import get_session_maker
from fastapi import APIRouter, Query

from api.auth.dependencies import AdminOrDemoDep
from api.schemas import FeedbackList, FeedbackView

router = APIRouter(tags=["feedback"])


@router.get("", operation_id="feedback_recent")
async def recent(
    _: AdminOrDemoDep,
    rating: Literal["up", "down"] | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> FeedbackList:
    """Recent feedback (newest first), optionally only one rating. Reserved: 404 outside demo/admin."""
    async with get_session_maker()() as session:
        rows = await acc.feedback.list_recent(session, rating=rating, limit=limit)
    return FeedbackList(
        count=len(rows),
        items=[
            FeedbackView(id=r.id, correlation_id=r.correlation_id, rating=r.rating, reason=r.reason, comment=r.comment, created_at=r.created_at)
            for r in rows
        ],
    )
