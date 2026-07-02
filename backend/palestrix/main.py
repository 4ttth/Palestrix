"""PalestrIX core API application factory.

Run locally:
    uvicorn palestrix.main:app --reload --port 8000

OpenAPI: http://localhost:8000/api/v1/openapi.json
Swagger UI: http://localhost:8000/api/v1/docs
"""

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (register all tables on Base.metadata)
from .config import get_settings
from .db import Base, engine
from .api import (
    academy,
    admin,
    auth,
    community,
    compete,
    courses,
    gamification,
    instances,
    labs,
    plugins,
    sandbox,
    users,
    webhooks,
)

API_PREFIX = "/api/v1"

DESCRIPTION = """
The PalestrIX core API. Every platform function is exposed here; the web UI,
plugins, and external tools all consume this same contract.

Authentication: session bearer token (password or passkey login), API key
(X-Api-Key header), or OAuth2 client-credentials token. See docs/public-api.md
in the repository for the full guide, scopes, and webhook catalog.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 2 contract: schema is created at startup. Alembic migrations
    # take over the first time a deployed schema needs to change.
    Base.metadata.create_all(bind=engine)

    # Phase 2b: discover plugins (entry points + PALESTRIX_PLUGIN_PATHS)
    # and re-activate the ones the database says are enabled.
    from .db import SessionLocal
    from .plugins.registry import registry

    registry.discover()
    db = SessionLocal()
    try:
        registry.restore(db)
    finally:
        db.close()

    # Phase 4: configured adapters take over their kinds (Proxmox for "vm",
    # Docker for "container"), and the TTL reaper starts ticking. In a Redis
    # deployment the worker process runs its own reaper; this in-app one is
    # still harmless (reaping is idempotent).
    from .orchestration import activate_configured_adapters
    from .orchestration.reaper import start_reaper

    activate_configured_adapters()
    reaper = start_reaper()
    yield
    if reaper is not None:
        reaper.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PalestrIX API",
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(auth.router)
    api.include_router(users.router)
    api.include_router(courses.router)
    api.include_router(academy.router)
    api.include_router(labs.router)
    api.include_router(instances.router)
    api.include_router(gamification.router)
    api.include_router(community.router)
    api.include_router(compete.router)
    api.include_router(sandbox.router)
    api.include_router(admin.router)
    api.include_router(plugins.router)
    api.include_router(webhooks.router)
    app.include_router(api)

    @app.get("/healthz", tags=["meta"])
    def healthz():
        return {"ok": True}

    return app


app = create_app()
