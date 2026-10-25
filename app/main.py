"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routes import admin, auth, chat, portfolio, push


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _maybe_seed_on_startup()
    yield


def _maybe_seed_on_startup() -> None:
    """Optionally (re)seed the demo data at boot.

    Render's free tier has no Shell and no preDeployCommand, so there is no way
    to run `python -m db.seed` by hand after a deploy — which is how the live DB
    ends up stale (e.g. building1@demo still pointing at an old building id).
    When COMMONWATT_SEED_ON_STARTUP is truthy we run the idempotent seed here.
    It is safe to run every boot: the seed upserts, so after the first fix it is
    a no-op. A failure is logged but never blocks startup — a seeding error must
    not take the whole API down.
    """
    import logging
    import os

    flag = os.environ.get("COMMONWATT_SEED_ON_STARTUP", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    try:
        from db.seed import main as seed_main

        seed_main()
        logging.getLogger("uvicorn.error").info("Startup seed completed (COMMONWATT_SEED_ON_STARTUP).")
    except Exception:  # noqa: BLE001 — never let a seed error crash the service
        logging.getLogger("uvicorn.error").exception("Startup seed failed; continuing without reseed.")


app = FastAPI(title="CommonWatt", lifespan=lifespan)

# Allow the Vite dev server (web/, port 5173) to call the API from the
# browser. Override COMMONWATT_CORS_ORIGINS (comma-separated) in deploy.
import os
_origins = os.environ.get(
    "COMMONWATT_CORS_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(push.router)
app.include_router(portfolio.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    from server.data import load_buildings
    return {"status": "ok", "buildings": len(load_buildings())}
