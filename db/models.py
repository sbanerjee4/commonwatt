"""SQLAlchemy models for CommonWatt SMS notifications.

Scoped to the sms-notifications spec. State is persisted in SQLite
(per steering/stack.md). All SMS state lives in these tables:
users (phone, sms_opted_out), outbound_messages, replies, audit_log.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Utility(Base):
    __tablename__ = "utilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kw_enrolled: Mapped[int] = mapped_column(Integer, default=0)
    kw_requested: Mapped[int] = mapped_column(Integer, default=0)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[str] = mapped_column(String)  # "utility" | "building_manager"
    utility_id: Mapped[Optional[int]] = mapped_column(ForeignKey("utilities.id"))
    building_id: Mapped[Optional[int]] = mapped_column(ForeignKey("buildings.id"))
    password_hash: Mapped[str] = mapped_column(String, default="")

    # SMS fields (spec 18.1, 9.1).
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    # E.164, e.g. "+12025551234".
    sms_opted_out: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[Optional[int]] = mapped_column(ForeignKey("utilities.id"))
    status: Mapped[str] = mapped_column(String, default="draft")
    # "draft" | "approved" | "closed"
    window_label: Mapped[str] = mapped_column(String, default="")
    reason_text: Mapped[str] = mapped_column(String, default="")
    target_mw: Mapped[int] = mapped_column(Integer, default=0)
    estimated_payment: Mapped[int] = mapped_column(Integer, default=0)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    building_links: Mapped[list["EventBuilding"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    @property
    def building_ids(self) -> list[int]:
        return [link.building_id for link in self.building_links]


class EventBuilding(Base):
    """Join: which buildings are asked in an event."""

    __tablename__ = "event_buildings"

    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), primary_key=True)
    building_id: Mapped[int] = mapped_column(
        ForeignKey("buildings.id"), primary_key=True
    )

    event: Mapped["Event"] = relationship(back_populates="building_links")


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("events.id"), nullable=True
    )
    template: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String)  # "twilio" | "simulated"
    status: Mapped[str] = mapped_column(String, default="pending")
    # "pending" | "sent" | "failed" | "skipped"
    provider_sid: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    kind: Mapped[str] = mapped_column(String)  # "yes" | "no" | "counter"
    kw: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Message(Base):
    """One message in an (event, building) chat thread.

    The in-app channel: the system posts the ask, the building manager replies,
    and an operator can post free text to take over. The thread is the
    conversation; structured YES/NO/kW answers still land in `replies` too, so
    the backfill logic is unchanged.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    building_id: Mapped[int] = mapped_column(
        ForeignKey("buildings.id"), nullable=False
    )
    sender_role: Mapped[str] = mapped_column(String)
    # "system" | "building_manager" | "operator"
    sender_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    body: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("events.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String)
    # sms_sent | sms_skipped | sms_failed | sms_received | sms_opted_out |
    # sms_opted_in | sms_webhook_invalid_signature | sms_unregistered_sender |
    # sms_unrecognized_body
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
