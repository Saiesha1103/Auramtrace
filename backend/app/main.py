"""FastAPI application. Run: uvicorn app.main:app --reload  ·  Docs: /docs (Swagger), /redoc."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .errors import install_error_handlers
from .routers import auth, events, jobs, karigars, lots, organisations

API_PREFIX = "/api/v1"

DESCRIPTION = """
AURUMTRACE Phase 1 backend — fine-gold chain of custody.

* **Auth:** `POST /api/v1/auth/login` → `accessToken`; send `Authorization: Bearer <token>` (use the *Authorize* button).
* **Units:** weights in grams (max 3 decimals); fineness in parts per thousand (916.0 = 22K).
* **Fine gold** = net metal weight × fineness ÷ 1000, rounded half-up to 0.001 g.
* **Custody history is append-only.** Corrections are `reversal` events; nothing is updated or deleted.
* **Errors** always look like `{"error": {"code", "message", "details"}}`.
"""


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="AURUMTRACE API",
        version=__version__,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    install_error_handlers(app)
    for r in (auth.router, organisations.router, karigars.router, jobs.router, lots.router, events.router):
        app.include_router(r, prefix=API_PREFIX)

    @app.get("/health", tags=["Health"], summary="Liveness probe")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "env": s.env}

    return app


app = create_app()
