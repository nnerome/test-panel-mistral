"""POST /api/actions/{id}/cancel — cancel a pending action of this session."""

import uuid
from typing import Annotated

from db.engine import get_session_maker
from fastapi import APIRouter, Path

from api.actions.service import cancel_action
from api.auth.dependencies import AuthenticatedDep, ClientHeaderDep
from api.schemas import ConfirmResponse, PendingActionView

router = APIRouter(tags=["actions"])


@router.post("", operation_id="actions_cancel")
async def cancel(
    id: Annotated[uuid.UUID, Path()],
    ctx: AuthenticatedDep,
    _: ClientHeaderDep,
) -> ConfirmResponse:
    """Cancel a pending action of this session (client header required)."""
    outcome = await cancel_action(get_session_maker(), ctx=ctx, action_id=id)
    action = outcome["action"]
    return ConfirmResponse(
        action=PendingActionView(
            id=uuid.UUID(action["id"]),
            kind=action["kind"],
            card_masked_number=action["card_masked_number"],
            card_label=action["card_label"],
            status=action["status"],
            created_at=action["created_at"],
            expires_at=action["expires_at"],
        ),
        executed=False,
        result=outcome["result"],
    )
