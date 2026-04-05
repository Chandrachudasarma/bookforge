"""Basic auth for POST/DELETE endpoints.

Username: demo
Password: from config auth.demo_password

GET endpoints stay open — visitors can browse jobs, download outputs,
and see templates without credentials.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

_password: str = ""


def init_auth(config) -> None:
    """Set the demo password from config. Called at startup."""
    global _password
    _password = config.get("auth.demo_password", "") or ""


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """FastAPI dependency — raises 401 if credentials are wrong.

    Use as: @router.post("/endpoint", dependencies=[Depends(require_auth)])
    """
    if not _password:
        # Auth not configured — allow all
        return credentials.username

    correct_password = secrets.compare_digest(credentials.password, _password)
    correct_username = secrets.compare_digest(credentials.username, "demo")

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Demo access required. Contact the administrator for credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username
