import os
import time

import httpx
from fastapi import HTTPException, Request
from jose import JWTError, jwt

TENANT_ID = os.getenv("AZURE_AD_TENANT_ID", "")
CLIENT_ID = os.getenv("AZURE_AD_CLIENT_ID", "")
AUTH_ENABLED = bool(TENANT_ID and CLIENT_ID)

_JWKS_URL = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
_ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"

_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600.0


async def _get_jwks() -> dict:
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(_JWKS_URL)
        r.raise_for_status()
        _jwks_cache = r.json()
        _jwks_fetched_at = now
    return _jwks_cache


async def validate_azure_token(token: str) -> dict:
    """Validate an Azure AD ID token and return its decoded claims.

    Raises HTTPException(401) on any validation failure.
    Claims dict contains `oid` (user's Azure AD object ID) among others.
    """
    if not AUTH_ENABLED:
        raise HTTPException(status_code=401, detail="Authentication not configured")
    try:
        jwks = await _get_jwks()
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=_ISSUER,
            options={"verify_at_hash": False},
        )
        return claims
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {exc}")


async def get_current_user_optional(request: Request) -> dict | None:
    """Return decoded claims if a valid Bearer token is present, else None.

    Never raises — callers use None to mean "anonymous user".
    """
    if not AUTH_ENABLED:
        return None
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        return await validate_azure_token(token)
    except HTTPException:
        return None


async def require_auth(request: Request) -> dict:
    """Dependency that enforces authentication; raises 401 if no valid token."""
    user = await get_current_user_optional(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
