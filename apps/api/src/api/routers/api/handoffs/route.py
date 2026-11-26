"""GET /api/handoffs — the advisor queue. Reserved route: demo mode only, else 404."""

import uuid
from typing import Literal

from db import accessors as acc
from db.engine import get_session_maker
from fastapi import APIRouter, Query

from api.auth.dependencies import DemoModeDep
from api.schemas import HandoffList, HandoffView

router = APIRouter(tags=["handoffs"])

HandoffStatus = Literal["open", "taken", "closed"]


@router.get("", operation_id="handoffs_list")
async def list_handoffs(
    _: DemoModeDep,
    status: HandoffStatus | None = "open",
    limit: int = Query(default=100, ge=1, le=500),
) -> HandoffList:
    """Handoff requests, newest first, filtered by status (default: open)."""
    async with get_session_maker()() as session:
        rows = await acc.handoffs.list_by_status(session, status=status, limit=limit)
    return HandoffList(count=len(rows), items=[_view(r) for r in rows])


def _view(r) -> HandoffView:
    return HandoffView(
        id=r.id,
        correlation_id=r.correlation_id,
        session_id=r.session_id,
        customer_id=r.customer_id,
        reason=r.reason,
        intent=r.intent,
        auth_level=r.auth_level,
        summary=r.summary,
        pending_action_id=r.pending_action_id,
        status=r.status,
        created_at=r.created_at,
    )
