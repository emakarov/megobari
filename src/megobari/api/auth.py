"""Bearer token authentication for dashboard API."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from megobari.db.engine import get_session
from megobari.db.repository import Repository

_security = HTTPBearer()


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> None:
    """Validate bearer token against dashboard_tokens table in DB."""
    token = credentials.credentials
    async with get_session() as session:
        repo = Repository(session)
        dt = await repo.verify_dashboard_token(token)
        if dt is None:
            raise HTTPException(status_code=401, detail="Invalid token")
