"""
security/admin_auth.py
Admin API key enforcement (Rule 16: config stores the value, security enforces it).

The ADMIN_API_KEY value is read from config/security_settings.py. This module owns
the rule: how the X-Admin-Key header is verified. Used as a FastAPI dependency on
protected /admin and /debug routes.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from config.security_settings import ADMIN_API_KEY


async def verify_admin_key(x_admin_key: str = Header(None)) -> str:
    """
    FastAPI dependency. Raises 401 if the admin key is unconfigured or the
    supplied X-Admin-Key header does not match.
    """
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Admin API key not configured")
    if not x_admin_key or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return x_admin_key
