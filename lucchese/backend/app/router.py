"""
app/router.py
Wire every API route module onto the app (Rule 2, Rule 21).

Entrypoint-level composition: this is the one place that knows the full set of
routers. Lower-level modules never import this.
"""

from __future__ import annotations

from fastapi import FastAPI

from api.routes import (
    admin_routes,
    business_routes,
    chat_routes,
    conversation_routes,
    debug_routes,
    document_routes,
    health_routes,
    state_routes,
    upload_routes,
    voice_routes,
)


def include_all_routers(app: FastAPI) -> None:
    """Register all route modules with the application."""
    for module in (
        chat_routes,
        admin_routes,
        debug_routes,
        conversation_routes,
        upload_routes,
        document_routes,
        health_routes,
        voice_routes,
        business_routes,
        state_routes,
    ):
        app.include_router(module.router)
