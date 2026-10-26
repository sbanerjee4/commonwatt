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
    _maybe_reconcile_schema_on_startup()
    _maybe_seed_on_startup()
    yield


def _maybe_reconcile_schema_on_startup() -> None:
    """Idempotently reconcile schema drift the live DB can't self-heal.

    The deployed Postgres was bootstrapped by ``init_db()`` (create_all) on an
    OLDER model and never migrated (Render free tier has no Shell/preDeploy and
    the DB carries no ``alembic_version`` stamp, so ``alembic upgrade head``
    restarts at 0001 and collides with the existing tables). create_all never
    ALTERs an existing table, so the ``messages.sender_role`` CHECK constraint
    stayed at its old set — without 'agent' — and every automated-agent chat
    reply 500s with a CheckViolation.

    Rather than fight Alembic's version chain, we fix the one thing that is
    actually wrong: drop and recreate that CHECK to match the current model's
    allowed roles. Idempotent (safe every boot), Postgres-only (SQLite enforces
    these loosely and create_all already builds the current constraint locally),
    gated by COMMONWATT_SEED_ON_STARTUP, and failure-tolerant.
    """
    import logging
    import os

    flag = os.environ.get("COMMONWATT_SEED_ON_STARTUP", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    log = logging.getLogger("uvicorn.error")

    from sqlalchemy import text

    from app.db import engine
    from db.models import MESSAGE_SENDER_ROLES

    # Only meaningful on Postgres; SQLite's create_all already has it right.
    if engine.dialect.name != "postgresql":
        return

    allowed = ", ".join(f"'{r}'" for r in MESSAGE_SENDER_ROLES)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE messages DROP CONSTRAINT IF EXISTS ck_messages_sender_role_allowed")
            )
            conn.execute(
                text("ALTER TABLE messages DROP CONSTRAINT IF EXISTS sender_role_allowed")
            )
            conn.execute(
                text(
                    f"ALTER TABLE messages ADD CONSTRAINT ck_messages_sender_role_allowed "
                    f"CHECK (sender_role IN ({allowed}))"
                )
            )
        log.info("Startup schema reconcile: messages.sender_role CHECK set to (%s).", allowed)
    except Exception:  # noqa: BLE001 — never let a reconcile error crash the service
        log.exception("Startup schema reconcile failed; continuing (schema may be stale).")


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
