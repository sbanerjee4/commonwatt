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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

ROLES = ("utility", "building_manager")
EVENT_STATUSES = ("draft", "approved", "rejected")
REPLY_KINDS = ("yes", "no", "offer", "counter")
AUDIT_ACTIONS = (
    "approved",
    "rejected",
    "edited",
    "resolved",
    "protected_set",
    "protected_cleared",
    "reply_submitted",
    "capacity_updated",
    # In-app notification channel (SMS -> in-app pivot). send_sms in
    # notify/models.py and the chat routes write these.
    "sms_sent",
    "sms_skipped",
    "sms_failed",
    "chat_building_reply",
    "chat_operator_message",
    "chat_thread_closed",
    # Inbound SMS webhook (app/routes/sms.py).
    "sms_webhook_invalid_signature",
    "sms_unregistered_sender",
    "sms_opted_out",
    "sms_opted_in",
    "sms_unrecognized_body",
    "sms_no_active_event",
    "sms_received",
)

# Message sender roles for the in-app (event, building) thread.
MESSAGE_SENDER_ROLES = ("system", "building_manager", "operator")


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
    # Notification channel fields. `phone` is the SMS/simulated destination
    # (null = no SMS destination; in-app delivery needs none). `sms_opted_out`
    # suppresses outbound messages regardless of channel.
    phone: Mapped[str | None] = mapped_column(String(32))
    sms_opted_out: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
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
    # Set when an operator closes the in-app thread for this event.
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    plan_memberships: Mapped[list["PlanBuilding"]] = relationship(
        "PlanBuilding", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def building_ids(self) -> list[str]:
        """Distinct building ids in this event's current plan version.

        The in-app chat channel and notify access checks ask "is this
        building in this event?" via `building_id in event.building_ids`.
        """
        seen: list[str] = []
        for pb in self.plan_memberships:
            if pb.plan_version == self.current_version and pb.building_id not in seen:
                seen.append(pb.building_id)
        return seen


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
    """A building's answer to a call or an in-app/SMS event thread.

    Two provenances share this table:
      - approved-call flow: `call_id` set, kinds yes/no/offer, `offer_kw`;
      - in-app chat + inbound SMS: `event_id` set (no call row), kind may be
        "counter" with the countered amount in `kw`.
    Exactly one of `call_id` / `event_id` identifies the context.
    """

    __tablename__ = "replies"
    __table_args__ = (
        CheckConstraint(_in_list("kind", REPLY_KINDS), name="kind_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("call_history.id", ondelete="RESTRICT"), index=True
    )
    event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="RESTRICT"), index=True
    )
    building_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("buildings.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    offer_kw: Mapped[float | None] = mapped_column(Float)
    # Countered kW for an in-app/SMS "counter" reply.
    kw: Mapped[float | None] = mapped_column(Float)
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


class AuditLog(Base):
    """Append-only record of human and system actions. Rows are never deleted."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(_in_list("action", AUDIT_ACTIONS), name="action_allowed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
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
    # Notification channel that produced this row ("inapp", "simulated",
    # "twilio"); null for non-notification actions.
    provider: Mapped[str | None] = mapped_column(String(32))
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    """One entry in the in-app (event, building) conversation thread.

    The free in-app channel that replaced SMS. The system posts a
    `building_ask` as a `system` message; the building manager replies as
    `building_manager`; an operator can post free text as `operator`.
    """

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            _in_list("sender_role", MESSAGE_SENDER_ROLES), name="sender_role_allowed"
        ),
        Index("ix_messages_building_id_id", "building_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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


class PushSubscription(Base):
    """A browser Web Push subscription for one user (free nudge channel)."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboundMessage(Base):
    """Durable log of one outbound notification attempt, any channel.

    `send_sms` in notify/models.py owns this row: one per attempt, written
    "pending" before the provider call and updated to "sent"/"failed" after.
    Channel-agnostic — the SMS, simulated, and in-app providers all record
    here; the in-app provider ALSO posts a `Message` into the thread.
    """

    __tablename__ = "outbound_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="RESTRICT"), index=True
    )
    template: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    provider_sid: Mapped[str | None] = mapped_column(String(128))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


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
    "OutboundMessage",
    "PlanBuilding",
    "PushSubscription",
    "REPLY_KINDS",
    "ROLES",
    "Reply",
    "Session",
    "TraceStep",
    "User",
    "Utility",
    "Zip",
    "ZipUtility",
]
