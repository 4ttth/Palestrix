"""PalestrIX core API application factory.

Run locally:
    uvicorn palestrix.main:app --reload --port 8000

OpenAPI: http://localhost:8000/api/v1/openapi.json
Swagger UI: http://localhost:8000/api/v1/docs
"""

import logging
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
    grading,
    instances,
    integrations,
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
    # Phase 7 boot guard: in production the app refuses to start on a
    # configuration that fails the hardening checks; in development the
    # findings are logged and startup continues.
    from .hardening import enforce_readiness

    enforce_readiness(get_settings())

    # Phase 2 contract: schema is created at startup; Phase 7 adds the
    # additive column upgrades for databases seeded by earlier phases
    # (palestrix/migrations.py). Anything beyond ADD COLUMN ships with real
    # Alembic migrations when the need first arises.
    Base.metadata.create_all(bind=engine)
    from .migrations import upgrade

    upgrade(engine)

    # The academy catalog ships in the repository (academy_catalog.py), so
    # the four learning paths exist on any database this app is pointed at
    # without a manual seed step. Insert-and-reconcile only: no path,
    # module, or completion is ever deleted here.
    if get_settings().academy_catalog_autoload:
        from sqlalchemy.exc import IntegrityError

        from .academy_catalog import ensure_catalog
        from .db import SessionLocal as _SessionLocal

        catalog_db = _SessionLocal()
        try:
            report = ensure_catalog(catalog_db)
            catalog_db.commit()
            if report["paths_created"] or report["modules_created"]:
                logging.getLogger("palestrix.academy").info(
                    "academy catalog: %d path(s), %d module(s) published",
                    len(report["paths_created"]),
                    len(report["modules_created"]),
                )
        except IntegrityError:
            # Another worker published first. The advisory lock in
            # ensure_catalog makes this rare, but two API hosts pointed at one
            # database would still meet here, and losing the race is a normal
            # outcome rather than a failure worth a traceback.
            catalog_db.rollback()
            logging.getLogger("palestrix.academy").info(
                "academy catalog already published by another worker"
            )
        except Exception:  # pragma: no cover - never block startup on content
            catalog_db.rollback()
            logging.getLogger("palestrix.academy").exception(
                "academy catalog could not be applied"
            )
        finally:
            catalog_db.close()

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

    # Phase 6: the sandbox coordinator detonator takes over when a dedicated
    # detonation host is configured; otherwise the demo detonator answers.
    from .sandbox import activate_configured_detonator

    activate_configured_detonator()

    # Phase 7: the multitenant cloud layer. LocalCloud (registry-only VLAN +
    # CIDR allocation) answers unless PALESTRIX_CLOUD_BACKEND swaps in the
    # OpenNebula or CloudStack adapter.
    from .tenancy import activate_configured_cloud

    activate_configured_cloud()

    # Phase 8: external platforms. Nothing answers by default;
    # PALESTRIX_CANVAS_ISSUER + .._CLIENT_ID activate the Canvas LMS adapter.
    from .integrations import activate_configured_platforms

    activate_configured_platforms()

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
    # Phase 7: baseline security headers on every response (the edge proxy
    # sets them too; the API does not rely on it).
    from .hardening import SecurityHeadersMiddleware

    app.add_middleware(
        SecurityHeadersMiddleware, production=settings.environment == "production"
    )

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(auth.router)
    api.include_router(users.router)
    api.include_router(courses.router)
    api.include_router(academy.router)
    api.include_router(labs.router)
    api.include_router(grading.router)
    api.include_router(instances.router)
    api.include_router(gamification.router)
    api.include_router(community.router)
    api.include_router(compete.router)
    api.include_router(sandbox.router)
    api.include_router(admin.router)
    api.include_router(plugins.router)
    api.include_router(webhooks.router)
    api.include_router(integrations.router)
    app.include_router(api)

    @app.get("/healthz", tags=["meta"])
    def healthz():
        return {"ok": True}

    return app


app = create_app()
