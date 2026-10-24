"""SQLAlchemy 2 declarative models for the Commonwatt schema.

Tables follow the "Data Models" section of the project design. The models hold
no business logic. CHECK constraints are declared by name so Alembic migrations
(task 1.3) produce stable constraint names on both SQLite and Postgres.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

ROLES = ("utility", "building_manager")
EVENT_STATUSES = ("draft", "approved", "rejected")
REPLY_KINDS = ("yes", "no", "offer")
AUDIT_ACTIONS = (
    "approved",
    "rejected",
    "edited",
    "resolved",
    "protected_set",
    "protected_cleared",
    "reply_submitted",
    "capacity_updated",
    # Chat / handoff layer (append-only; never remove a value).
    "chat_agent_reply",
    "chat_handoff_requested",
    "chat_operator_message",
    "chat_building_reply",
    "chat_thread_closed",
)

THREAD_MODES = ("auto", "human")
MESSAGE_SENDER_ROLES = ("system", "agent", "building_manager", "operator")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    """Render `column IN ('a', 'b')` for a CHECK constraint."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Utility(Base):
    """One row per utility company."""

    __tablename__ = "utilities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[str] = mapped_column(String(255))


class Zip(Base):
    """A Massachusetts zip code with its environmental-justice flag and centroid."""

    __tablename__ = "zips"

    zip: Mapped[str] = mapped_column(String(10), primary_key=True)
    ej: Mapped[bool] = mapped_column(Boolean, default=False)
    ej_source_id: Mapped[str | None] = mapped_column(String(255))
    centroid_lng: Mapped[float | None] = mapped_column(Float)
    centroid_lat: Mapped[float | None] = mapped_column(Float)


class ZipUtility(Base):
    """Territory mapping: each zip belongs to exactly one utility."""

    __tablename__ = "zip_utility"

    zip: Mapped[str] = mapped_column(
        String(10), ForeignKey("zips.zip", ondelete="CASCADE"), primary_key=True
    )
    utility_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("utilities.id", ondelete="RESTRICT"), index=True
    )
    town: Mapped[str | None] = mapped_column(String(255))
    source_id: Mapped[str] = mapped_column(String(255))


class Building(Base):
    """A BERDO-reporting building. `simulated` marks seeded enrollment and capacity."""

    __tablename__ = "buildings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    zip: Mapped[str] = mapped_column(String(10), ForeignKey("zips.zip", ondelete="RESTRICT"), index=True)
    address: Mapped[str] = mapped_column(String(512))
    property_type: Mapped[str | None] = mapped_column(String(255))
    gross_area_sf: Mapped[float | None] = mapped_column(Float)
    site_eui: Mapped[float | None] = mapped_column(Float)
    per_electricity: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    geocode_status: Mapped[str | None] = mapped_column(String(64))
    enrolled: Mapped[bool] = mapped_column(Boolean, default=False)
    enrolled_capacity_kw: Mapped[float | None] = mapped_column(Float)
    offered_capacity_kw: Mapped[float | None] = mapped_column(Float)
    protected: Mapped[bool] = mapped_column(Boolean, default=False)
    protected_reason: Mapped[str | None] = mapped_column(Text)
    protected_kind: Mapped[str | None] = mapped_column(String(64))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class User(Base):
    """Login identity. Exactly one of `utility_id` / `building_id` is set, matching `role`."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            _in_list("role", ROLES), name="role_allowed"
        ),
        CheckConstraint(
            "(role = 'utility' AND utility_id IS NOT NULL AND building_id IS NULL) "
            "OR (role = 'building_manager' AND building_id IS NOT NULL AND utility_id IS NULL)",
            name="role_scope_match",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(32))
    utility_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("utilities.id", ondelete="RESTRICT"), index=True
    )
    building_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("buildings.id", ondelete="RESTRICT"), index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Session(Base):
    """Server-side login session. Only the hash of the cookie token is stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class Event(Base):
    """A utility demand-response event. Versions live in `plan_buildings`."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(_in_list("status", EVENT_STATUSES), name="status_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    utility_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("utilities.id", ondelete="RESTRICT"), index=True
    )
    window_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    window_label: Mapped[str] = mapped_column(String(255))
    target_mw: Mapped[float] = mapped_column(Float)
    cap_pct: Mapped[float] = mapped_column(Float)
    heat_threshold_exceeded: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PlanBuilding(Base):
    """Membership of one building in one plan version of one event (draft or final)."""

    __tablename__ = "plan_buildings"

    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    plan_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    building_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("buildings.id", ondelete="RESTRICT"), primary_key=True
    )
    kw_requested: Mapped[float] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)


class CallHistory(Base):
    """A contact with a building. Written only when an event is approved (AC-48)."""

    __tablename__ = "call_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="RESTRICT"), index=True
    )
    building_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("buildings.id", ondelete="RESTRICT"), index=True
    )
    kw_requested: Mapped[float] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    est_payment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Reply(Base):
    """A building's answer to a call. Simulated rows are flagged `simulated=True`."""

    __tablename__ = "replies"
    __table_args__ = (
        CheckConstraint(_in_list("kind", REPLY_KINDS), name="kind_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("call_history.id", ondelete="RESTRICT"), index=True
    )
    building_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("buildings.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    offer_kw: Mapped[float | None] = mapped_column(Float)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class MeterRead(Base):
    """Interval meter reading for a called building during an event."""

    __tablename__ = "meter_reads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("call_history.id", ondelete="RESTRICT"), index=True
    )
    building_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("buildings.id", ondelete="RESTRICT"), index=True
    )
    interval_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    kw: Mapped[float] = mapped_column(Float)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class HeatDayInterval(Base):
    """Per-zip interval load for the heat-day replay (AC-34)."""

    __tablename__ = "heat_day_intervals"
    __table_args__ = (
        Index("ix_heat_day_intervals_day_interval", "day", "interval_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    utility_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("utilities.id", ondelete="RESTRICT"), index=True
    )
    day: Mapped[dt.date] = mapped_column(Date)
    interval_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    zip: Mapped[str] = mapped_column(String(10), ForeignKey("zips.zip", ondelete="RESTRICT"), index=True)
    load_kw: Mapped[float] = mapped_column(Float)
    participating_kw: Mapped[float] = mapped_column(Float, default=0.0)
    source_id: Mapped[str] = mapped_column(String(255))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class TraceStep(Base):
    """One step of the agent loop, streamed to the operator's trace panel."""

    __tablename__ = "trace_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    kind: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    plan_version: Mapped[int | None] = mapped_column(Integer)
    tool_name: Mapped[str | None] = mapped_column(String(128))
    rejected_by: Mapped[str | None] = mapped_column(String(255))


class PushSubscription(Base):
    """One browser Web Push subscription for a user (free notification channel)."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(String(512), unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Thread(Base):
    """One automated/human conversation for one (event, building) ask.

    `handoff_mode` is the switch: while "auto" the automated agent may post
    assistant messages; "human" silences the agent so only the operator's
    free text is posted. `needs_human` flags a thread for operator attention
    when an agent reply fell back (Bedrock error or a suppressed banned-word
    reply) without a mode flip.
    """

    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    building_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("buildings.id", ondelete="RESTRICT"), index=True
    )
    handoff_mode: Mapped[str] = mapped_column(
        String(16), default="auto", server_default="auto"
    )
    needs_human: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            _in_list("handoff_mode", THREAD_MODES), name="handoff_mode_allowed"
        ),
        Index("uq_threads_event_id", "event_id", "building_id", unique=True),
    )


class Message(Base):
    """One posted message in a thread. Append-only; rows are never deleted."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            _in_list("sender_role", MESSAGE_SENDER_ROLES),
            name="sender_role_allowed",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("threads.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    building_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("buildings.id", ondelete="RESTRICT"), index=True
    )
    sender_role: Mapped[str] = mapped_column(String(32))
    sender_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditLog(Base):
    """Append-only record of human and system actions. Rows are never deleted."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(_in_list("action", AUDIT_ACTIONS), name="action_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="RESTRICT"), index=True
    )
    building_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("buildings.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


__all__ = [
    "AUDIT_ACTIONS",
    "AuditLog",
    "Base",
    "Building",
    "CallHistory",
    "EVENT_STATUSES",
    "Event",
    "HeatDayInterval",
    "MESSAGE_SENDER_ROLES",
    "Message",
    "MeterRead",
    "PlanBuilding",
    "PushSubscription",
    "REPLY_KINDS",
    "ROLES",
    "Reply",
    "Session",
    "THREAD_MODES",
    "Thread",
    "TraceStep",
    "User",
    "Utility",
    "Zip",
    "ZipUtility",
]
