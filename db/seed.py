"""PLACEHOLDER territory seed (task 1.4). NOT REAL DATA.

Every value in this module is a hardcoded placeholder, chosen only so the
account rows added in task 1.5 have valid foreign keys to reference. No dataset,
network call, geocoder, or fixture is read. Task 1b replaces these rows with the
real territory (BERDO buildings, zip-to-utility mapping, EJ zips). Until then,
every seeded row carries `simulated=True` where the table has that column.

Run from the repository root after `alembic upgrade head`:

    python -m db.seed

Seeding is idempotent: rows are upserted by primary key, so re-running updates
the placeholder rows in place and never duplicates them. Foreign keys are
enforced for the seed's session, and a violation aborts the whole seed with an
error that names the offending row.
"""

from __future__ import annotations

import bcrypt
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.config import SessionLocal
from db.models import Building, User, Utility, Zip, ZipUtility

# --- PLACEHOLDER constants. Replaced by task 1b. Not real Massachusetts data. ---

# Placeholder zip codes sit outside the real MA range (01xxx-02xxx), so no one
# can mistake them for a real zip's EJ status.
PLACEHOLDER_ZIP_EJ = "00001"
PLACEHOLDER_ZIP_PROTECTED = "00002"
PLACEHOLDER_ZIP_THIRD = "00003"

PLACEHOLDER_SOURCE_ID = "PLACEHOLDER:task-1.4"
PLACEHOLDER_UTILITY_ID = "placeholder-utility"
PLACEHOLDER_UTILITY_NAME = "PLACEHOLDER Utility (demo only)"

PLACEHOLDER_BUILDING_IDS = ("PH-BLDG-1", "PH-BLDG-2", "PH-BLDG-3")
PLACEHOLDER_PROTECTED_BUILDING_ID = "PH-BLDG-2"
PLACEHOLDER_PROTECTED_REASON = (
    "PLACEHOLDER: flagged protected for the demo. Replace with real data in task 1b."
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
        (PLACEHOLDER_ZIP_THIRD, False),
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
        _upsert(
            session,
            Building,
            building_id,
            {
                **spec,
                "address": f"PLACEHOLDER address for {building_id} (not a real building)",
                "property_type": None,
                "gross_area_sf": None,
                "site_eui": None,
                "per_electricity": None,
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


def main() -> None:
    """Seed the database named by DATABASE_URL (default: local SQLite file)."""
    with SessionLocal() as session:
        seed_placeholder_territory(session)
        seed_demo_accounts(session)
    print(
        "Seeded PLACEHOLDER territory (task 1.4) and demo accounts (task 1.5). "
        "Replace with real data in task 1b."
    )


if __name__ == "__main__":
    main()
