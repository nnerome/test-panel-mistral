"""FastAPI dependencies: resolve the session cookie, enforce levels and the custom header.

The cookie is HttpOnly + SameSite=Strict (set where the response is built); state-changing
endpoints additionally require our own frontend's custom header — a cross-site form cannot
set custom headers, which is the prototype's CSRF defence."""

from typing import Annotated

from env.assistant import env as assistant_env
from fastapi import Depends, Header, HTTPException, Request

from api.auth.service import SessionContext, resolve_session, SESSION_COOKIE, SESSION_HEADER


def session_token(request: Request) -> str | None:
    """The bearer token for this request: our X-Bnp-Session header first, then the cookie.

    The web app echoes the token from the login response in the header because behind the
    Studio gateway the module's Set-Cookie may not reach the browser (the gateway owns the
    domain's auth cookies); locally the cookie alone works."""
    return request.headers.get(SESSION_HEADER) or request.cookies.get(SESSION_COOKIE)


async def session_from_request(request: Request) -> SessionContext | None:
    from db.engine import get_session_maker

    return await resolve_session(get_session_maker(), session_token(request))


SessionDep = Annotated[SessionContext | None, Depends(session_from_request)]


async def require_authenticated(ctx: SessionDep) -> SessionContext:
    from api.domain.errors import AuthRequiredError

    if ctx is None or ctx.level == "anonymous" or ctx.customer_id is None:
        raise AuthRequiredError("login required")
    return ctx


AuthenticatedDep = Annotated[SessionContext, Depends(require_authenticated)]


async def require_strong(ctx: AuthenticatedDep) -> SessionContext:
    from api.domain.errors import StepUpRequiredError

    if ctx.level != "strong":
        raise StepUpRequiredError("strong authentication required for this action")
    return ctx


StrongDep = Annotated[SessionContext, Depends(require_strong)]


def _header_name() -> str:
    return assistant_env.client_header_name.lower()


async def require_client_header(
    request: Request,
    x_bnp_client: Annotated[str | None, Header(alias=assistant_env.client_header_name)] = None,
) -> None:
    """State-changing endpoints call this: the header must be the value only our web app sets."""
    if not assistant_env.require_client_header:
        return
    if x_bnp_client != assistant_env.client_header_value:
        raise HTTPException(status_code=403, detail={"code": "missing_client_header", "message": "custom header required"})


ClientHeaderDep = Annotated[None, Depends(require_client_header)]
