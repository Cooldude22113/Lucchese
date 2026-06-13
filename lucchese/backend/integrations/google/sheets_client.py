"""
integrations/google/sheets_client.py
Thin Google Sheets API access (Rule 11).

Owns the spreadsheets() service handle and a single read helper. The sheet-specific
readers in integrations/sheets/ call get_values() instead of building the service
themselves. Service construction is lazy (defers credential load + network).
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from config.integration_settings import SPREADSHEET_ID
from integrations.google.credentials import get_credentials

_sheet: Any | None = None
_lock = Lock()


def _get_sheet() -> Any:
    """Return the cached spreadsheets() resource, building it once on first call."""
    global _sheet
    if _sheet is None:
        with _lock:
            if _sheet is None:
                from googleapiclient.discovery import build

                service = build("sheets", "v4", credentials=get_credentials())
                _sheet = service.spreadsheets()
    return _sheet


def get_values(cell_range: str, spreadsheet_id: str = SPREADSHEET_ID) -> list[list]:
    """Fetch a range's values; returns a list of rows (empty list if none)."""
    result = _get_sheet().values().get(
        spreadsheetId=spreadsheet_id,
        range=cell_range,
    ).execute()
    return result.get("values", [])
