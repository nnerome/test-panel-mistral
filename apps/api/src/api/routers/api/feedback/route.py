"""POST /api/feedback — rate one turn (thumbs up/down, optional reason + comment).

The correlation_id must belong to a turn of THIS session, otherwise a uniform 404 (no existence
leak). One row per (session, turn): a second submission updates it (upsert), never duplicates.
All free text is scrubbed of PAN-like digit runs and truncated server-side; message/answer
excerpts are stored only for "down" ratings."""

from db import accessors as acc
from db.engine import get_session_maker
from fastapi import APIRouter

from api.auth.dependencies import ClientHeaderDep, SessionDep
from api.domain.errors import NotFoundError
from api.domain.masking import scrub_secrets
from api.schemas import FeedbackRequest, FeedbackView

router = APIRouter(tags=["feedback"])


def _clean(text: str | None, limit: int) -> str | None:
    """Scrub PAN-like runs, truncate to `limit`, drop empty strings."""
    if text is None:
        return None
    cleaned = scrub_secrets(text)[:limit].strip()
    return cleaned or None


@router.post("", operation_id="feedback_create")
async def create_feedback(body: FeedbackRequest, ctx: SessionDep, _: ClientHeaderDep) -> FeedbackView:
    """Record feedback for one of this session's turns (custom header required, CSRF defence)."""
    if ctx is None:
        raise NotFoundError("turn not found")
    async with get_session_maker()() as session:
        turn = await acc.turn_records.get(session, body.correlation_id)
        if turn is None or turn.session_id != ctx.session_id:
            raise NotFoundError("turn not found")  # uniform 404: another session's turn == nonexistent
        comment = _clean(body.comment, 280)
        if body.rating == "down":
            reason = body.reason
            message_excerpt = _clean(body.message_excerpt, 500)
            answer_excerpt = _clean(body.answer_excerpt, 500)
        else:
            reason = body.reason
            message_excerpt = None  # excerpts exist only for "down"
            answer_excerpt = None
        row = await acc.feedback.upsert(
            session,
            session_id=ctx.session_id,
            correlation_id=body.correlation_id,
            rating=body.rating,
            reason=reason,
            comment=comment,
            message_excerpt=message_excerpt,
            answer_excerpt=answer_excerpt,
        )
        await session.commit()
    return FeedbackView(
        id=row.id,
        correlation_id=row.correlation_id,
        rating=row.rating,
        reason=row.reason,
        comment=row.comment,
        created_at=row.created_at,
    )
