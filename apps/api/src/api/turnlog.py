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
            await acc.turn_records.record(
                session,
                correlation_id=result.correlation_id,
                session_id=ctx.session_id if ctx else None,
                intent=result.intent,
                auth_level=result.auth_level,
                refused=result.refused,
                human_offer=result.human_offer,
                error=result.error,
                timings=json.dumps([t.model_dump() for t in result.timings]),
                model=result.model,
                tokens=json.dumps(result.tokens) if result.tokens else None,
            )
            await session.commit()
    except Exception:
        logger.exception("failed to record turn %s", result.correlation_id)
