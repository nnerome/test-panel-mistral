"""GET /api/actions/{id} — the pending action's status (masked), for the UI's countdown."""

import uuid
from typing import Annotated

from db.engine import get_session_maker
from fastapi import APIRouter, Path
from fastapi import HTTPException

from api.actions.service import get_pending_action_view
from api.auth.dependencies import AuthenticatedDep
from api.schemas import PendingActionView

router = APIRouter(tags=["actions"])


@router.get("", operation_id="actions_get")
async def get_action(id: Annotated[uuid.UUID, Path()], ctx: AuthenticatedDep) -> PendingActionView:
    """Fetch one pending action of this session (masked card only); 404 if it is not yours."""
    found = await get_pending_action_view(get_session_maker(), ctx, id)
    if found is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "action not found"})
    action, card = found
    return PendingActionView(
        id=action.id,
        kind=action.kind,
        card_masked_number=f"**** **** **** {card.pan_last4}" if card else "****",
        card_label=card.label if card else "",
        status=action.status,
        created_at=action.created_at,
        expires_at=action.expires_at,
    )
