"""
Karatos GUI Server
Professional Agent Dashboard — FastAPI backend serving REST API + Static SPA frontend.
"""
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from utils.logger import get_logger

logger = get_logger()

# Reference to agent — set by main.py before startup
_agent = None
_gui_port = 7860


def set_agent(agent):
    global _agent
    _agent = agent


def get_agent():
    return _agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"[GUI] Dashboard server starting on port {_gui_port}")
    yield
    logger.info("[GUI] Dashboard server shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Karatos Dashboard",
        version="1.0.0",
        docs_url="/api/docs",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    from gui.api.routes.dashboard import router as dashboard_router
    from gui.api.routes.settings import router as settings_router
    from gui.api.routes.credentials import router as credentials_router
    from gui.api.routes.chat import router as chat_router
    from gui.api.routes.telemetry import router as telemetry_router
    from gui.api.routes.memory_api import router as memory_router
    from gui.api.routes.logs import router as logs_router
    from gui.api.routes.mcp_api import router as mcp_router

    app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])
    app.include_router(settings_router, prefix="/api/settings", tags=["Settings"])
    app.include_router(credentials_router, prefix="/api/credentials", tags=["Credentials"])
    app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
    app.include_router(telemetry_router, prefix="/api/telemetry", tags=["Telemetry"])
    app.include_router(memory_router, prefix="/api/memory", tags=["Memory"])
    app.include_router(logs_router, prefix="/api/logs", tags=["Logs"])
    app.include_router(mcp_router, prefix="/api/mcp", tags=["MCP"])

    # Serve static SPA
    frontend_dir = Path(__file__).parent / "frontend"
    if frontend_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve SPA — all non-API routes return index.html"""
            file_path = frontend_dir / full_path
            if full_path and file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_dir / "index.html"))

    return app


async def start_server(agent, port: int = 7860):
    """Start the GUI server as an async task."""
    import uvicorn
    global _gui_port
    _gui_port = port
    set_agent(agent)
    app = create_app()

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info(f"[GUI] 🖥️  Dashboard available at http://localhost:{port}")
    try:
        await server.serve()
    except SystemExit:
        logger.error(f"[GUI] ❌ Port {port} is unavailable. Try a different port with --gui-port <port>")
    except OSError as e:
        logger.error(f"[GUI] ❌ Could not bind to port {port}: {e}. Try --gui-port <port>")
