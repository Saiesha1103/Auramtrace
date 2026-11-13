"""FastAPI application. Run: uvicorn app.main:app --reload  ·  Docs: /docs (Swagger), /redoc."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .errors import install_error_handlers
from .routers import (
    auth,
    events,
    exceptions,
    investigations,
    jobs,
    karigars,
    lots,
    organisations,
    production,
    reconciliations,
    returns,
    settlements,
    transfers,
)

API_PREFIX = "/api/v1"

DESCRIPTION = """
AURUMTRACE API — Fine-gold chain of custody, reconciliation engine, and AI investigation.

* **Auth:** `POST /api/v1/auth/login` → `accessToken`; send `Authorization: Bearer <token>` (use the *Authorize* button).
* **Units:** weights in grams (max 3 decimals); fineness in parts per thousand (916.0 = 22K).
* **Fine gold** = net metal weight × fineness ÷ 1000, rounded half-up to 0.001 g.
* **Custody history is append-only.** Corrections are `reversal` events; nothing is updated or deleted.
* **Transfers:** Multi-level karigar transfers with explicit receiver acknowledgement and custody lineage.
* **Production:** Manufacturing stage tracking, physical measurements, and audited superseding measurements.
* **Returns:** Finished jewellery, scrap, dust, and WIP returns with declared vs verified assayed fineness.
* **Reconciliation:** Deterministic fine-gold bridge snapshots and automated anomaly detection.
* **AI Investigation:** Evidence-grounded investigation assistant with 12 read-only tools.
* **Settlement:** Versioned commercial settlement rules with mandatory human authorization.
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
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for r in (
        auth.router,
        organisations.router,
        karigars.router,
        jobs.router,
        lots.router,
        events.router,
        transfers.router,
        production.router,
        returns.router,
        reconciliations.router,
        exceptions.router,
        investigations.router,
        settlements.router,
    ):
        app.include_router(r, prefix=API_PREFIX)

    @app.get("/health", tags=["Health"], summary="Liveness probe")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "env": s.env}

    return app


app = create_app()
