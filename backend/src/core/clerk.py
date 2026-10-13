
import asyncio
import time
from collections import OrderedDict
import structlog
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions, RequestState
from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError

from src.core.settings import settings
from src.db.base import AsyncSessionLocal
from src.db.repositories.user_repo import get_user, upsert_user

log = structlog.get_logger()
bearer_scheme = HTTPBearer(auto_error=False)
clerk_client = Clerk(bearer_auth=settings.clerk_secret_key)
# Cache only the local email/provisioning result. JWT signature, expiry and
# authorized party checks still run on every request. This is not an access cache.
_local_profiles: OrderedDict[str, tuple[float, str]] = OrderedDict()
_profile_inflight: dict[str, asyncio.Future] = {}
PROFILE_TTL_SECONDS = 300
PROFILE_CACHE_LIMIT = 1024


def _get_primary_email(user) -> str | None:
    primary_email_address_id = getattr(user, "primary_email_address_id", None)
    email_addresses = getattr(user, "email_addresses", None) or []

    for email_address in email_addresses:
        if getattr(email_address, "id", None) == primary_email_address_id:
            email = getattr(email_address, "email_address", None)
            if email:
                return email

    for email_address in email_addresses:
        email = getattr(email_address, "email_address", None)
        if email:
            return email

    return None


async def _resolve_email(
    clerk_user_id: str,
    request_state: RequestState,
    fallback_email: str | None = None,
) -> str:
    payload = request_state.payload or {}
    email = payload.get("email")
    if isinstance(email, str) and email:
        return email
    if fallback_email:
        # Signed JWT identity is authoritative; Clerk webhooks update email.
        return fallback_email

    try:
        user = await clerk_client.users.get_async(user_id=clerk_user_id)
    except Exception:
        if fallback_email:
            return fallback_email
        raise

    email = _get_primary_email(user)
    if email:
        return email

    if fallback_email:
        return fallback_email

    raise ValueError("Clerk user is missing a primary email address")


async def _ensure_local_user(clerk_user_id: str, email: str) -> None:
    async with AsyncSessionLocal() as db:
        existing_user = await get_user(db, clerk_user_id)
        if existing_user is not None:
            return

        try:
            await upsert_user(db, clerk_user_id, email)
        except Exception as exc:
            await db.rollback()

            if existing_user is not None:
                log.warning(
                    "Unable to refresh local user record",
                    clerk_user_id=clerk_user_id,
                    error=str(exc),
                )
                return

            log.error(
                "Unable to provision local user",
                clerk_user_id=clerk_user_id,
                error=str(exc),
            )
            raise HTTPException(
                status_code=503,
                detail="Authenticated user could not be provisioned",
            ) from exc


async def _local_email(clerk_user_id: str, request_state: RequestState) -> str:
    cached = _local_profiles.get(clerk_user_id)
    if cached and cached[0] > time.monotonic():
        _local_profiles.move_to_end(clerk_user_id)
        return cached[1]
    if clerk_user_id in _profile_inflight:
        return await asyncio.shield(_profile_inflight[clerk_user_id])
    future = asyncio.get_running_loop().create_future()
    _profile_inflight[clerk_user_id] = future
    try:
        async with AsyncSessionLocal() as db:
            existing = await get_user(db, clerk_user_id)
            existing_email = existing.email if existing is not None else None
        async with asyncio.timeout(10):
            email = await _resolve_email(clerk_user_id, request_state, existing_email)
        if existing is None:
            await _ensure_local_user(clerk_user_id, email)
        _local_profiles[clerk_user_id] = (time.monotonic()+PROFILE_TTL_SECONDS, email)
        _local_profiles.move_to_end(clerk_user_id)
        while len(_local_profiles) > PROFILE_CACHE_LIMIT:
            _local_profiles.popitem(last=False)
        future.set_result(email)
        return email
    except BaseException as error:
        if isinstance(error, asyncio.CancelledError):
            future.cancel()
        else:
            future.set_exception(error)
            future.exception()  # Retrieve when this caller has no waiting peers.
        raise
    finally:
        _profile_inflight.pop(clerk_user_id, None)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """
    FastAPI dependency injected into every protected route.
    Verifies the Clerk JWT and returns the user payload.
    Raises 401 if the token is invalid or expired.
    """
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        async with asyncio.timeout(10):
            request_state = await clerk_client.authenticate_request_async(
                request,
                AuthenticateRequestOptions(secret_key=settings.clerk_secret_key, authorized_parties=[origin.strip() for origin in settings.allowed_origins.split(',')]),
            )

        if not request_state.is_authenticated or not request_state.payload:
            raise HTTPException(
                status_code=401,
                detail=request_state.message or "Invalid or expired token",
            )

        clerk_user_id = request_state.payload.get("sub")
        if not isinstance(clerk_user_id, str) or not clerk_user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        email = await _local_email(clerk_user_id, request_state)

        return {
            "clerk_user_id": clerk_user_id,
            "email": email,
        }
    except HTTPException:
        raise
    except TimeoutError:
        raise HTTPException(503, detail="Sign-in verification timed out. Please retry.") from None
    except SQLAlchemyError:
        raise HTTPException(503, detail="User database is temporarily unavailable. Please retry.") from None
    except Exception as exc:
        log.warning("Clerk token verification failed", reason=type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid or expired token")
