"""POST /api/handoffs/{id}/status — reserved (demo/admin + client header): an advisor takes or
closes a handoff request. Uniform 404 when the id does not exist."""

import uuid
from typing import Annotated

from db import accessors as acc
from db.engine import get_session_maker
from fastapi import APIRouter, Path

from api.auth.dependencies import DemoModeDep, ClientHeaderDep
from api.domain.errors import NotFoundError
from api.routers.api.handoffs.route import HandoffStatus, _view
from api.schemas import HandoffStatusBody, HandoffView

router = APIRouter(tags=["handoffs"])


@router.post("", operation_id="handoffs_set_status")
async def set_status(
    id: Annotated[uuid.UUID, Path()],
    body: HandoffStatusBody,
    _a: DemoModeDep,
    _h: ClientHeaderDep,
) -> HandoffView:
    """Move a handoff request to taken/closed (or back to open)."""
    async with get_session_maker()() as session:
        row = await acc.handoffs.get(session, id)
        if row is None:
            raise NotFoundError("handoff not found")
        await acc.handoffs.set_status(session, row, body.status)
        await session.commit()
    return _view(row)
