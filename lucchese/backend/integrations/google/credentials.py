"""
integrations/google/credentials.py
Service-account credential loading for Google APIs (Rule 11).

Lazily builds read-only Sheets credentials from the service-account file named in
config. Loading is deferred so importing this module never touches disk or the
network.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from config.integration_settings import GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEETS_SCOPES

_credentials: Any | None = None
_lock = Lock()


def get_credentials() -> Any:
    """Return cached service-account credentials, loading them once on first call."""
    global _credentials
    if _credentials is None:
        with _lock:
            if _credentials is None:
                from google.oauth2 import service_account

                _credentials = service_account.Credentials.from_service_account_file(
                    GOOGLE_CREDENTIALS_FILE, scopes=GOOGLE_SHEETS_SCOPES
                )
    return _credentials
