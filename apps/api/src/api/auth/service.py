"""Session and OTP service. Demo-grade crypto on purpose: SHA-256 hashing and a random token —
the prototype's point is the flow (levels, single-use, expiry, attempts), not the KDF.

The session level lives only in the DB row; a customer cannot raise it by crafting a payload.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from db import accessors as acc
from db.engine import get_session_maker
from db.models.bank_session import BankSession
from env.assistant import env as assistant_env
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from api.domain.errors import AuthRequiredError, DomainError, StepUpRequiredError

SESSION_COOKIE = "bnp_session"
# The Studio gateway owns the auth cookies of the app's public domain, so a module's Set-Cookie
# may not reach the browser in a deployed app; the web frontend therefore also echoes the token
# in this header after login. Both transports resolve to the same server-side session row.
SESSION_HEADER = "X-Bnp-Session"
LEVELS = ("anonymous", "authenticated", "strong")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secrets_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


@dataclass(frozen=True)
class SessionContext:
    """What a request knows about its session. `customer_id` is None while anonymous."""

    session_id: uuid.UUID
    token: str
    level: str
    customer_id: uuid.UUID | None


async def create_session(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    customer_id: uuid.UUID | None = None,
    level: str = "anonymous",
) -> SessionContext:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    async with session_maker() as session:
        row = await acc.sessions.create(
            session,
            token_hash=hash_secret(token),
            level=level,
            expires_at=now + timedelta(seconds=assistant_env.session_ttl_seconds),
            last_seen_at=now,
            customer_id=customer_id,
        )
        await session.commit()
        return SessionContext(session_id=row.id, token=token, level=level, customer_id=customer_id)


async def resolve_session(session_maker: async_sessionmaker[AsyncSession], token: str | None) -> SessionContext | None:
    """Load the session for a bearer token, or None when absent/unknown/expired."""
    if not token:
        return None
    async with session_maker() as session:
        row = await acc.sessions.get_by_token_hash(session, hash_secret(token))
        if row is None or row.expires_at <= utcnow():
            return None
        await acc.sessions.touch(session, row, utcnow())
        await session.commit()
        return SessionContext(session_id=row.id, token=token, level=row.level, customer_id=row.customer_id)


async def destroy_session(session_maker: async_sessionmaker[AsyncSession], token: str) -> None:
    async with session_maker() as session:
        row = await acc.sessions.get_by_token_hash(session, hash_secret(token))
        if row is not None:
            await acc.sessions.delete(session, row)
            await session.commit()


def require_level(ctx: SessionContext, level: str) -> None:
    """Raise unless the session is at least at `level`. Levels only ever rise via the OTP flow."""
    order = {name: i for i, name in enumerate(LEVELS)}
    if order[ctx.level] < order[level]:
        if level == "strong":
            raise StepUpRequiredError("strong authentication required for this action")
        raise AuthRequiredError("login required")


async def login(session_maker: async_sessionmaker[AsyncSession], email: str, password: str) -> SessionContext:
    """Bind a fresh session to the customer at level `authenticated`."""
    async with session_maker() as session:
        customer = await acc.customers.get_by_email(session, email)
        if customer is None or not secrets_equal(customer.password_hash, hash_secret(password)):
            # Same error for unknown email and wrong password: no account enumeration.
            raise AuthRequiredError("invalid credentials", code="invalid_credentials")
        customer_id = customer.id
    return await create_session(session_maker, customer_id=customer_id, level="authenticated")


async def issue_otp(session_maker: async_sessionmaker[AsyncSession], ctx: SessionContext) -> tuple[uuid.UUID, str, datetime]:
    """Create a single-use 6-digit code for the session. Returns (otp_id, code, expires_at)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = utcnow()
    expires_at = now + timedelta(seconds=assistant_env.otp_ttl_seconds)
    async with session_maker() as session:
        row = await acc.sessions.get(session, ctx.session_id)
        if row is None:
            raise AuthRequiredError("session not found")
        await acc.otps.invalidate_active_for_session(session, ctx.session_id, now)
        otp = await acc.otps.create(session, session_id=ctx.session_id, code_hash=hash_secret(code), expires_at=expires_at)
        await session.commit()
        return otp.id, code, expires_at


class OtpError(DomainError):
    status_code = 401
    code = "otp_invalid"


async def verify_otp(session_maker: async_sessionmaker[AsyncSession], ctx: SessionContext, code: str) -> None:
    """Verify the session's active code: single-use, 5-minute expiry, max N attempts.

    Success raises the session to `strong` — a DB write, not a client-supplied claim.
    """
    now = utcnow()
    async with session_maker() as session:
        otp = await acc.otps.latest_active_for_session(session, ctx.session_id, now)
        if otp is None:
            raise OtpError("no active code or code expired", code="otp_expired")
        if otp.attempts >= assistant_env.otp_max_attempts:
            raise OtpError("too many attempts; request a new code", code="otp_locked")
        if not secrets_equal(otp.code_hash, hash_secret(code.strip())):
            await acc.otps.register_attempt(session, otp)
            await session.commit()
            remaining = assistant_env.otp_max_attempts - (otp.attempts + 1)
            raise OtpError(f"wrong code ({remaining} attempts left)", code="otp_wrong")
        await acc.otps.mark_used(session, otp, now)
        row = await acc.sessions.get(session, ctx.session_id)
        if row is None:
            raise AuthRequiredError("session not found")
        await acc.sessions.set_level(session, row, "strong", now)
        await session.commit()
