"""Per-turn telemetry write path (turn_records). Every failure is logged and swallowed:
recording a turn must never break the turn itself."""

import json
import logging

from api.orchestrator import TurnResult

logger = logging.getLogger("bnp.turnlog")


async def record_turn(session_maker, result: TurnResult, ctx) -> None:
    """Write the turn's turn_records row (idempotent on correlation_id). Never raises."""
    try:
        from db import accessors as acc

        async with session_maker() as session:
            # The UI shows the AI disclaimer at the start of every conversation; flag the first
            # recorded turn of the session so the trace shows it was displayed (no personal data).
            session_id = ctx.session_id if ctx else None
            if session_id is not None:
                result.disclaimer_shown = await acc.turn_records.count_for_session(session, session_id) == 0
            else:
                result.disclaimer_shown = True
            await acc.turn_records.record(
                session,
                correlation_id=result.correlation_id,
                session_id=session_id,
                intent=result.intent,
                auth_level=result.auth_level,
                refused=result.refused,
                human_offer=result.human_offer,
                error=result.error,
                timings=json.dumps([t.model_dump() for t in result.timings]),
                model=result.model,
                tokens=json.dumps(result.tokens) if result.tokens else None,
                disclaimer_shown=result.disclaimer_shown,
            )
            await session.commit()
    except Exception:
        logger.exception("failed to record turn %s", result.correlation_id)
