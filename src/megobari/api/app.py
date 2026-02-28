"""FastAPI application factory and server startup."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from megobari.api.auth import require_auth

logger = logging.getLogger(__name__)

# Built dashboard lives at <project>/dashboard/dist/client (TanStack Start SPA)
_DASHBOARD_DIST = Path(__file__).parent.parent.parent.parent / "dashboard" / "dist" / "client"


def create_api(
    bot_data: dict,
    session_manager: object,
) -> FastAPI:
    """Create the FastAPI dashboard app with shared bot state."""
    app = FastAPI(
        title="Megobari Dashboard",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # Store shared references on app.state
    app.state.bot_data = bot_data
    app.state.session_manager = session_manager

    # CORS for Vite dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # Mount all API routes with auth
    from megobari.api.routes import (
        health,
        memories,
        messages,
        monitoring,
        personas,
        scheduling,
        sessions,
        summaries,
        usage,
        ws,
    )

    auth_dep = [Depends(require_auth)]
    app.include_router(health.router, prefix="/api", dependencies=auth_dep)
    app.include_router(sessions.router, prefix="/api", dependencies=auth_dep)
    app.include_router(usage.router, prefix="/api", dependencies=auth_dep)
    app.include_router(messages.router, prefix="/api", dependencies=auth_dep)
    app.include_router(summaries.router, prefix="/api", dependencies=auth_dep)
    app.include_router(personas.router, prefix="/api", dependencies=auth_dep)
    app.include_router(memories.router, prefix="/api", dependencies=auth_dep)
    app.include_router(scheduling.router, prefix="/api", dependencies=auth_dep)
    app.include_router(monitoring.router, prefix="/api", dependencies=auth_dep)
    # WebSocket handles its own auth via query param
    app.include_router(ws.router, prefix="/api")

    # Serve built frontend SPA (if it exists)
    _shell = _DASHBOARD_DIST / "_shell.html"
    if _DASHBOARD_DIST.is_dir():
        # Static assets (JS, CSS, images)
        app.mount(
            "/assets",
            StaticFiles(directory=str(_DASHBOARD_DIST / "assets")),
            name="dashboard-assets",
        )
        logger.info("Serving dashboard from %s", _DASHBOARD_DIST)

        # SPA catch-all: serve _shell.html for all non-API routes
        if _shell.exists():
            from starlette.responses import HTMLResponse

            _shell_html = _shell.read_text()

            @app.get("/{path:path}", include_in_schema=False)
            async def _spa_fallback(path: str) -> HTMLResponse:
                return HTMLResponse(_shell_html)

    return app


async def start_api_server(app: FastAPI, port: int = 8420) -> None:
    """Start uvicorn as a background asyncio task."""
    import uvicorn

    cfg = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(cfg)

    async def _run_server() -> None:
        try:
            await server.serve()
        except Exception:
            logger.error("Dashboard server crashed", exc_info=True)

    task = asyncio.create_task(_run_server(), name="dashboard-api")

    # Wait briefly to ensure the server actually binds
    await asyncio.sleep(0.5)
    if task.done() and task.exception():
        raise task.exception()
