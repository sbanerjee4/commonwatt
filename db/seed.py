"""Demo territory seed. Buildings and zips are REAL BERDO rows; enrollment is simulated.

The three seeded buildings (129860, 114120, 100901) and their zips
(02128/02132/02136) are real BERDO records read from fixtures/berdo.json via
`server.data.buildings_by_id`, so the demo facility accounts point at building
ids that actually exist in `server/data.py`. The EJ flags come from
`server.data.EJ_ZIPS` (02128 and 02136 are EJ; 02132 is not). The utility and
zip-to-utility rows remain a single demo utility. Enrollment status and
capacity are still simulated demo values, so every building row carries
`simulated=True`.

Run from the repository root after `alembic upgrade head`:

    python -m db.seed

Seeding is idempotent: rows are upserted by primary key, so re-running updates
the rows in place and never duplicates them. Foreign keys are enforced for the
seed's session, and a violation aborts the whole seed with an error that names
the offending row.
"""

from __future__ import annotations

import bcrypt
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.config import SessionLocal
from db.models import (
    Building,
    CallHistory,
    Event,
    PlanBuilding,
    User,
    Utility,
    Zip,
    ZipUtility,
)
from server.data import buildings_by_id

# --- Demo territory constants. Buildings/zips are real BERDO rows; the utility
# and enrollment are simulated demo values. ---

# Real Boston BERDO zips. EJ flags match server.data.EJ_ZIPS: 02128 and 02136
# are EJ; 02132 is not.
PLACEHOLDER_ZIP_EJ = "02128"
PLACEHOLDER_ZIP_PROTECTED = "02132"
PLACEHOLDER_ZIP_THIRD = "02136"

PLACEHOLDER_SOURCE_ID = "berdo:fixtures/berdo.json"
PLACEHOLDER_UTILITY_ID = "placeholder-utility"
PLACEHOLDER_UTILITY_NAME = "PLACEHOLDER Utility (demo only)"

# Real BERDO building ids, read from fixtures/berdo.json at seed time. Index 0
# ('129860') is the building seed_demo_event wires its approved event to.
PLACEHOLDER_BUILDING_IDS = ("129860", "114120", "100901")
PLACEHOLDER_PROTECTED_BUILDING_ID = "114120"
PLACEHOLDER_PROTECTED_REASON = (
    "Simulated demo flag: this building is marked protected for the demo only."
)

# --- DEMO-ONLY credentials (task 1.5). Plaintext lives here for the README and
# the demo login only. The database stores bcrypt hashes, never these strings.
DEMO_UTILITY_PASSWORD = "demo-utility-pass"
DEMO_BUILDING_PASSWORD = "demo-building-pass"
# (email, plaintext password, role, utility_id, building_id)
DEMO_ACCOUNTS: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    ("utility@demo", DEMO_UTILITY_PASSWORD, "utility", PLACEHOLDER_UTILITY_ID, None),
    ("building1@demo", DEMO_BUILDING_PASSWORD, "building_manager", None, PLACEHOLDER_BUILDING_IDS[0]),
    ("building2@demo", DEMO_BUILDING_PASSWORD, "building_manager", None, PLACEHOLDER_BUILDING_IDS[1]),
    ("building3@demo", DEMO_BUILDING_PASSWORD, "building_manager", None, PLACEHOLDER_BUILDING_IDS[2]),
)


class PlaceholderSeedError(RuntimeError):
    """Raised when a seeded row violates a schema constraint. Names the row."""


def _upsert(session: Session, model: type, pk: str, values: dict, label: str) -> None:
    """Insert the row keyed by `pk`, or update it in place if it already exists.

    The flush surfaces CHECK and FK violations here, so the error can name the row.
    On failure the whole seed is rolled back, so no partial placeholder territory
    is left behind.
    """
    row = session.get(model, pk)
    if row is None:
        session.add(model(**values))
    else:
        for name, value in values.items():
            setattr(row, name, value)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise PlaceholderSeedError(f"{label} violates a schema constraint: {exc.orig}") from exc


def _enable_sqlite_foreign_keys(session: Session) -> None:
    """SQLite ignores foreign keys unless enabled per connection. Postgres needs nothing."""
    if session.get_bind().dialect.name == "sqlite":
        session.execute(text("PRAGMA foreign_keys = ON"))


def seed_placeholder_territory(session: Session) -> None:
    """Upsert the placeholder utility, zips, zip-to-utility rows, and buildings.

    Commits once at the end. Re-running is a no-op in row count.
    """
    _enable_sqlite_foreign_keys(session)

    _upsert(
        session,
        Utility,
        PLACEHOLDER_UTILITY_ID,
        {
            "id": PLACEHOLDER_UTILITY_ID,
            "name": PLACEHOLDER_UTILITY_NAME,
            "source_id": PLACEHOLDER_SOURCE_ID,
        },
        f"utilities row {PLACEHOLDER_UTILITY_ID!r}",
    )

    zips = (
        (PLACEHOLDER_ZIP_EJ, True),
        (PLACEHOLDER_ZIP_PROTECTED, False),
        (PLACEHOLDER_ZIP_THIRD, True),
    )
    for zip_code, ej in zips:
        _upsert(
            session,
            Zip,
            zip_code,
            {
                "zip": zip_code,
                "ej": ej,
                "ej_source_id": None,
                "centroid_lng": None,
                "centroid_lat": None,
            },
            f"zips row {zip_code!r}",
        )

    for zip_code, _ in zips:
        _upsert(
            session,
            ZipUtility,
            zip_code,
            {
                "zip": zip_code,
                "utility_id": PLACEHOLDER_UTILITY_ID,
                "town": None,
                "source_id": PLACEHOLDER_SOURCE_ID,
            },
            f"zip_utility row {zip_code!r}",
        )

    # Real BERDO data per building, keyed by id. Missing fields fall back to None.
    records = buildings_by_id()
    buildings = (
        {
            "id": PLACEHOLDER_BUILDING_IDS[0],
            "zip": PLACEHOLDER_ZIP_EJ,
            "protected": False,
            "protected_reason": None,
            "enrolled": True,
            "enrolled_capacity_kw": 100.0,
        },
        {
            "id": PLACEHOLDER_BUILDING_IDS[1],
            "zip": PLACEHOLDER_ZIP_PROTECTED,
            "protected": True,
            "protected_reason": PLACEHOLDER_PROTECTED_REASON,
            "enrolled": False,
            "enrolled_capacity_kw": None,
        },
        {
            "id": PLACEHOLDER_BUILDING_IDS[2],
            "zip": PLACEHOLDER_ZIP_THIRD,
            "protected": False,
            "protected_reason": None,
            "enrolled": True,
            "enrolled_capacity_kw": 50.0,
        },
    )
    for spec in buildings:
        building_id = spec["id"]
        record = records.get(building_id)
        _upsert(
            session,
            Building,
            building_id,
            {
                **spec,
                "address": getattr(record, "address", None),
                "property_type": getattr(record, "property_type", None),
                "gross_area_sf": getattr(record, "gross_area_sf", None),
                "site_eui": getattr(record, "site_eui_kbtuft2", None),
                "per_electricity": getattr(record, "per_electricity", None),
                "lng": None,
                "lat": None,
                "geocode_status": None,
                "offered_capacity_kw": None,
                "protected_kind": None,
                "simulated": True,
            },
            f"buildings row {building_id!r}",
        )

    session.commit()


def _hash_password(plaintext: str) -> str:
    """Return a bcrypt hash with a fresh random salt."""
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _password_verifies(plaintext: str, stored_hash: str) -> bool:
    """True when `plaintext` matches `stored_hash`. A malformed stored hash counts as no match."""
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("ascii"))
    except ValueError:
        return False


def seed_demo_accounts(session: Session) -> None:
    """Upsert the four demo accounts (task 1.5) keyed by email.

    Requires the placeholder territory from `seed_placeholder_territory` to exist.
    Keeps the existing row id on re-run. Rehashes the password only when the stored
    hash no longer verifies. Creates no sessions or sign-up/reset rows.
    Commits once at the end. Re-running leaves the row count unchanged.
    """
    _enable_sqlite_foreign_keys(session)
    for email, plaintext, role, utility_id, building_id in DEMO_ACCOUNTS:
        values = {"role": role, "utility_id": utility_id, "building_id": building_id}
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            session.add(User(email=email, password_hash=_hash_password(plaintext), **values))
        else:
            for name, value in values.items():
                setattr(user, name, value)
            if not _password_verifies(plaintext, user.password_hash):
                user.password_hash = _hash_password(plaintext)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise PlaceholderSeedError(
                f"users row {email!r} violates a schema constraint: {exc.orig}"
            ) from exc
    session.commit()


def seed_demo_event(session: Session) -> None:
    """Seed one approved demo event so a live chat thread can exist.

    Idempotent: keyed by the demo window label. Creates an approved Event for
    the placeholder utility, a PlanBuilding row (current version) for the first
    demo building, and a CallHistory row so a parsed chat reply has a call_id.
    """
    import datetime as dt

    _enable_sqlite_foreign_keys(session)
    label = "DEMO Tue 2-6PM"
    event = session.scalar(select(Event).where(Event.window_label == label))
    if event is None:
        now = dt.datetime(2026, 7, 1, 18, 0, tzinfo=dt.timezone.utc)
        event = Event(
            utility_id=PLACEHOLDER_UTILITY_ID,
            window_start=now,
            window_end=now + dt.timedelta(hours=4),
            window_label=label,
            target_mw=20.0,
            cap_pct=0.35,
            status="approved",
            current_version=1,
        )
        session.add(event)
        session.flush()

    bld = PLACEHOLDER_BUILDING_IDS[0]
    pb = session.get(PlanBuilding, (event.id, event.current_version, bld))
    if pb is None:
        session.add(
            PlanBuilding(
                event_id=event.id,
                plan_version=event.current_version,
                building_id=bld,
                kw_requested=20.0,
                reason="placeholder peak-load demo",
            )
        )
    call = session.scalar(
        select(CallHistory).where(
            CallHistory.event_id == event.id, CallHistory.building_id == bld
        )
    )
    if call is None:
        session.add(
            CallHistory(
                event_id=event.id,
                building_id=bld,
                kw_requested=20.0,
                reason="placeholder peak-load demo",
            )
        )
    session.commit()


def seed_all_buildings(session: Session) -> None:
    """Seed EVERY BERDO building (and its zip) into the DB.

    The planner ranks a portfolio over the full in-memory dataset
    (``server.data.load_buildings`` — ~2k buildings), but approve persists
    ``plan_buildings`` / ``call_history`` / ``threads`` rows that FK to the
    ``buildings`` table. If only the 3 demo buildings are in that table, approve
    hits a foreign-key violation the moment the planner picks any other building.
    So the DB's ``buildings`` universe must match the planner's: we upsert every
    building here, plus each building's zip (buildings.zip FKs to zips.zip) and a
    zip_utility row tying it to the placeholder utility.

    Idempotent and bulk-oriented: existing ids are skipped, so re-running is
    cheap. Enrollment/capacity stay simulated; buildings carry ``simulated=True``.
    """
    from server.data import load_buildings

    _enable_sqlite_foreign_keys(session)
    records = load_buildings()

    # --- zips: one row per distinct building zip, tied to the placeholder utility
    existing_zips = set(session.execute(select(Zip.zip)).scalars())
    seen_zips: set[str] = set()
    for b in records:
        z = b.zip
        if not z or z in seen_zips or z in existing_zips:
            continue
        seen_zips.add(z)
        session.add(Zip(zip=z, ej=bool(b.is_ej), ej_source_id=None,
                        centroid_lng=None, centroid_lat=None))
    session.flush()

    existing_zu = set(session.execute(select(ZipUtility.zip)).scalars())
    for z in sorted(seen_zips | existing_zips):
        if z in existing_zu:
            continue
        session.add(ZipUtility(zip=z, utility_id=PLACEHOLDER_UTILITY_ID,
                              town=None, source_id=PLACEHOLDER_SOURCE_ID))
    session.flush()

    # --- buildings: insert any not already present (the 3 placeholders already are)
    existing_bids = set(session.execute(select(Building.id)).scalars())
    added = 0
    for b in records:
        if b.building_id in existing_bids:
            continue
        if not b.zip:
            continue  # buildings.zip is NOT NULL + FKs to zips; skip zip-less rows
        lng, lat = (b.lng_lat or (None, None))
        session.add(Building(
            id=b.building_id,
            zip=b.zip,
            address=b.address or "Unknown",
            property_type=b.property_type,
            gross_area_sf=b.gross_area_sf,
            site_eui=b.site_eui_kbtuft2,
            per_electricity=b.per_electricity,
            lng=lng,
            lat=lat,
            geocode_status="geocoded" if b.lng_lat else None,
            enrolled=False,
            enrolled_capacity_kw=None,
            offered_capacity_kw=None,
            protected=bool(b.is_protected),
            protected_reason=None,
            protected_kind=None,
            simulated=True,
        ))
        added += 1
    session.commit()
    print(f"Seeded {added} additional BERDO buildings into the DB (total universe now matches the planner).")


def main() -> None:
    """Seed the database named by DATABASE_URL (default: local SQLite file)."""
    with SessionLocal() as session:
        seed_placeholder_territory(session)
        seed_all_buildings(session)
        seed_demo_accounts(session)
        seed_demo_event(session)
    print(
        "Seeded demo territory (real BERDO buildings 129860/114120/100901 and "
        "zips 02128/02132/02136), all BERDO buildings for planner FK integrity, "
        "demo accounts, and a demo approved event with a chat thread target. "
        "Enrollment and capacity are simulated."
    )


if __name__ == "__main__":
    main()
