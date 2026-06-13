"""
api/middleware/cors.py
CORS configuration (Rule 2 boundary — HTTP middleware lives under api/).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://192.168.1.112:5173",
    "https://lucchese.app",
    "https://www.lucchese.app",
]


def add_cors(app: FastAPI) -> None:
    """Attach the CORS middleware with the Lucchese frontend origins."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
