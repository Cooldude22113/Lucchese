"""
app/factory.py
Application factory (Rule 2, Rule 21).

create_app() configures logging, runs the startup sequence, builds the FastAPI app,
attaches middleware, and registers all routers.
"""

from __future__ import annotations

from fastapi import FastAPI

from api.middleware.cors import add_cors
from app.lifecycle import run_startup
from app.router import include_all_routers
from observability.logging_config import configure_logging


def create_app() -> FastAPI:
    """Build and return the fully wired FastAPI application."""
    configure_logging()
    run_startup()

    app = FastAPI()
    add_cors(app)
    include_all_routers(app)
    return app
