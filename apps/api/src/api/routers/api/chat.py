"""POST /api/chat — one assistant turn, streamed as SSE.

Public (no customer login needed): the FAQ path works anonymously. A session cookie is issued
on first call so every turn is attributable server-side (anonymous level). Event types:
`delta` (streamed text), `sources`, `pending_action`, `turn` (full JSON incl. per-stage
timings, intent, guardrails, correlation id), `error`, `done`."""

import asyncio
import json
from collections.abc import AsyncIterator

from db.engine import get_session_maker
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from mistralai_capabilities.fastapi.sse import event_stream_response, format_sse

from api.auth.service import SESSION_COOKIE, create_session, resolve_session
from env.assistant import env as assistant_env
from api.orchestrator import OrchestratorDeps, run_turn
from api.runtime import ensure_ready, get_runtime
from api.schemas import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("", operation_id="chat_turn", response_class=StreamingResponse)
async def chat(body: ChatRequest, request: Request):
    """Stream one chatbot turn as server-sent events; works anonymously for public FAQ."""
    runtime = get_runtime(request)
    session_maker = get_session_maker()
    await ensure_ready(runtime)

    ctx = await resolve_session(session_maker, request.cookies.get(SESSION_COOKIE))
    new_ctx = None
    if ctx is None:
        ctx = await create_session(session_maker)  # anonymous session, cookie set below
        new_ctx = ctx

    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    async def emit(event: dict) -> None:
        await queue.put(event)

    async def produce() -> None:
        try:
            # Tests inject scripted stage implementations through app.state.bnp_orch_overrides.
            overrides = dict(getattr(request.app.state, "bnp_orch_overrides", None) or {})
            result = await run_turn(
                body.message,
                ctx,
                orch=OrchestratorDeps(
                    client=runtime.client,
                    bank=runtime.bank,
                    embedder=runtime.embedder,
                    **overrides,
                ),
                emit=emit,
            )
            for source in result.sources:
                await queue.put({"type": "sources", "source": source})
            if result.pending_action:
                await queue.put({"type": "pending_action", "action": result.pending_action})
            await queue.put({"type": "turn", "turn": json.loads(result.model_dump_json())})
        except Exception:  # never leave the stream hanging; details stay in the server logs
            import logging

            logging.getLogger("bnp.chat").exception("turn failed")
            await queue.put({"type": "error", "message": "internal error"})
        finally:
            await queue.put(sentinel)

    task = asyncio.create_task(produce())

    async def events() -> AsyncIterator[str]:
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield format_sse(data=item, event=str(item["type"]))
        await task
        yield format_sse(data={}, event="done")

    response: StreamingResponse = event_stream_response(events())
    if new_ctx is not None:
        response.set_cookie(
            SESSION_COOKIE,
            new_ctx.token,
            httponly=True,
            samesite="strict",
            secure=assistant_env.session_cookie_secure,
            path="/",
            max_age=assistant_env.session_ttl_seconds,
        )
    return response
