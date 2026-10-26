"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routes import admin, auth, chat, portfolio, push


@asynccontextmanager
async def lifespan(app: FastAPI):
    _maybe_rebuild_db_on_startup()
    init_db()
    _maybe_reconcile_schema_on_startup()
    _maybe_seed_on_startup()
    yield


def _maybe_rebuild_db_on_startup() -> None:
    """Drop and recreate ALL tables from the current model, when explicitly asked.

    The live free-tier Postgres was bootstrapped by create_all on an OLDER model
    and was never migrated (no Shell, no preDeploy, unstamped DB — so `alembic
    upgrade head` restarts at 0001 and collides). create_all never ALTERs an
    existing table, so the live schema has drifted from the model in several
    places (the messages.sender_role CHECK, the call_history.est_payment column,
    and potentially more). Patching columns one at a time just surfaces the next
    drift as the next 500.

    Because ALL data here is seeded/simulated demo data (no real user content),
    the robust fix is to rebuild the schema from scratch so it EXACTLY matches
    the model, then let the seed repopulate it. This is DESTRUCTIVE, so it is
    gated behind its own explicit flag (COMMONWATT_REBUILD_DB) — NOT the seed
    flag — and must be turned off again after one boot. A failure is logged but
    never blocks startup.
    """
    import logging
    import os

    flag = os.environ.get("COMMONWATT_REBUILD_DB", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    log = logging.getLogger("uvicorn.error")
    try:
        from app.db import engine
        from db.models import Base

        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        log.warning("Startup DB REBUILD completed (COMMONWATT_REBUILD_DB): all tables dropped and recreated from the model. Turn the flag off now.")
    except Exception:  # noqa: BLE001 — never let a rebuild error crash the service
        log.exception("Startup DB rebuild failed; continuing.")


def _maybe_reconcile_schema_on_startup() -> None:
    """Idempotently reconcile CHECK-constraint drift the live DB can't self-heal.

    The deployed Postgres was bootstrapped by ``init_db()`` (create_all) on an
    OLDER model and never migrated (Render free tier has no Shell/preDeploy and
    the DB carries no ``alembic_version`` stamp, so ``alembic upgrade head``
    restarts at 0001 and collides with the existing tables). create_all never
    ALTERs an existing table, so every enum-style CHECK constraint stayed at its
    old value set — e.g. ``messages.sender_role`` without 'agent' and
    ``audit_log.action`` without the chat_* actions — and each new value 500s
    with a CheckViolation the moment the chat/handoff flow writes it.

    Rather than fight Alembic's version chain (or rely on the destructive
    rebuild flag), we drop and recreate each drifting CHECK to match the current
    model's allowed set. Idempotent (safe every boot), Postgres-only (SQLite
    enforces these loosely and create_all already builds the current constraints
    locally), gated by COMMONWATT_SEED_ON_STARTUP, and failure-tolerant per
    constraint so one failure never blocks the rest or crashes startup.
    """
    import logging
    import os

    flag = os.environ.get("COMMONWATT_SEED_ON_STARTUP", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return
    log = logging.getLogger("uvicorn.error")

    from sqlalchemy import text

    from app.db import engine
    from db.models import AUDIT_ACTIONS, EVENT_STATUSES, MESSAGE_SENDER_ROLES, REPLY_KINDS

    # Only meaningful on Postgres; SQLite's create_all already has it right.
    if engine.dialect.name != "postgresql":
        return

    # (table, column, canonical constraint name, legacy alias name, allowed values)
    checks = [
        ("messages", "sender_role", "ck_messages_sender_role_allowed", "sender_role_allowed", MESSAGE_SENDER_ROLES),
        ("audit_log", "action", "ck_audit_log_action_allowed", "action_allowed", AUDIT_ACTIONS),
        ("replies", "kind", "ck_replies_kind_allowed", "kind_allowed", REPLY_KINDS),
        ("events", "status", "ck_events_status_allowed", "status_allowed", EVENT_STATUSES),
    ]
    for table, column, cname, alias, values in checks:
        allowed = ", ".join(f"'{v}'" for v in values)
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {cname}"))
                conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {alias}"))
                conn.execute(
                    text(f"ALTER TABLE {table} ADD CONSTRAINT {cname} CHECK ({column} IN ({allowed}))")
                )
            log.info("Startup reconcile: %s.%s CHECK set to (%s).", table, column, allowed)
        except Exception:  # noqa: BLE001 — per-constraint; never block the rest or crash startup
            log.exception("Startup reconcile of %s.%s failed; continuing.", table, column)


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
