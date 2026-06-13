"""
main.py
Backend entrypoint. Run with: uvicorn main:app  (from backend/)

All construction lives in app/factory.py; this file just exposes the ASGI app.
"""

from __future__ import annotations

from app.factory import create_app

app = create_app()
