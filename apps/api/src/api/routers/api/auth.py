"""Demo authentication routes: fictional-customer login, session info, step-up (OTP), logout.

The session cookie is HttpOnly + SameSite=Strict; only the SHA-256 of the token is stored."""

import uuid

from db import accessors as acc
from db.engine import get_session_maker
from env.assistant import env as assistant_env
from fastapi import APIRouter, Response

from api.auth import service
from api.auth.dependencies import AuthenticatedDep, SessionDep
from api.auth.service import SESSION_COOKIE
from api.schemas import LoginRequest, LoginResponse, LogoutResponse, SessionInfo, StepUpResponse, VerifyOtpRequest

router = APIRouter(tags=["auth"])


async def _session_info(ctx: service.SessionContext | None) -> SessionInfo:
    """Project the session for the response; anonymous callers get an empty level view."""
    if ctx is None:
        return SessionInfo(
            session_id=uuid.uuid4(),
            level="anonymous",
            customer_id=None,
            customer_name=None,
            expires_in_seconds=0,
        )
    customer_name = None
    if ctx.customer_id is not None:
        async with get_session_maker()() as session:
            customer = await acc.customers.get(session, ctx.customer_id)
            customer_name = customer.display_name if customer else None
    return SessionInfo(
        session_id=ctx.session_id,
        level=ctx.level,  # type: ignore[arg-type]
        customer_id=ctx.customer_id,
        customer_name=customer_name,
        expires_in_seconds=assistant_env.session_ttl_seconds,
    )


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=assistant_env.session_cookie_secure,  # false locally (http), true behind TLS in prod
        path="/",
        max_age=assistant_env.session_ttl_seconds,
    )


@router.post("/login", operation_id="auth_login")
async def login(body: LoginRequest, response: Response) -> LoginResponse:
    """Log in as one of the 3 fictional demo customers; returns a new authenticated session cookie."""
    ctx = await service.login(get_session_maker(), body.email.strip(), body.password)
    _set_cookie(response, ctx.token)
    return LoginResponse(session=await _session_info(ctx), token=ctx.token)


@router.post("/logout", operation_id="auth_logout")
async def logout(response: Response, ctx: SessionDep) -> LogoutResponse:
    """Destroy the server-side session and clear the cookie."""
    if ctx is not None:
        await service.destroy_session(get_session_maker(), ctx.token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return LogoutResponse(ok=True)


@router.get("/me", operation_id="auth_me")
async def me(ctx: SessionDep) -> SessionInfo:
    """Current session: auth level and bound customer, or anonymous."""
    return await _session_info(ctx)


@router.post("/step-up", operation_id="auth_step_up")
async def step_up(ctx: AuthenticatedDep) -> StepUpResponse:
    """Simulate sending a one-time code (shown in the response because this is a demo)."""
    otp_id, code, expires_at = await service.issue_otp(get_session_maker(), ctx)
    return StepUpResponse(
        otp_id=otp_id,
        expires_at=expires_at,
        demo_code=code if (assistant_env.demo_show_otp and assistant_env.demo_mode) else None,
    )


@router.post("/step-up/verify", operation_id="auth_step_up_verify")
async def step_up_verify(body: VerifyOtpRequest, ctx: AuthenticatedDep) -> SessionInfo:
    """Verify the one-time code; success raises the session to level `strong` server-side."""
    await service.verify_otp(get_session_maker(), ctx, body.code)
    refreshed = await service.resolve_session(get_session_maker(), ctx.token)
    assert refreshed is not None
    return await _session_info(refreshed)
