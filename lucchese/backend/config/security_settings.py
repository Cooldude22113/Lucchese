"""
config/security_settings.py
Security-related configuration VALUES only (Rule 16: config stores values,
security enforces rules). The enforcement code lives in security/admin_auth.py.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Admin API key for protected /admin and /debug endpoints. The verification logic
# that consumes this lives in security/admin_auth.py.
ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")
