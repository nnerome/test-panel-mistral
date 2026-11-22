"""POST /api/actions/{id}/confirm — the ONLY place a state change executes.

Requires: the session's strong auth level AND the custom header set by our own frontend
(CSRF defence; the cookie is SameSite=Strict). Idempotent: a replay or concurrent double-click
returns the stored result, never executes twice."""

import uuid
from typing import Annotated

from db.engine import get_session_maker
from fastapi import APIRouter, Path

from api.actions.service import confirm_action
from api.auth.dependencies import ClientHeaderDep, StrongDep
from api.runtime import get_runtime
from api.schemas import ConfirmResponse, PendingActionView
from fastapi import Request

router = APIRouter(tags=["actions"])


@router.post("", operation_id="actions_confirm")
async def confirm(
    id: Annotated[uuid.UUID, Path()],
    request: Request,
    ctx: StrongDep,
    _: ClientHeaderDep,
) -> ConfirmResponse:
    """Confirm and execute a pending action of this session (strong auth + client header required)."""
    runtime = get_runtime(request)
    outcome = await confirm_action(get_session_maker(), ctx=ctx, action_id=id, bank=runtime.bank)
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
        executed=outcome["executed"],
        result=outcome["result"],
    )
