"""notify in-app channel: messages, push_subscriptions, outbound_messages

Restores the model surface the free in-app chat + push + notify layer needs,
which the auth refactor dropped from db/models.py:

  - new tables: messages, push_subscriptions, outbound_messages
  - users: phone, sms_opted_out
  - events: closed_at
  - audit_log: provider column + extended action CHECK (sms_* and chat_*)

CHECK + column edits go through op.batch_alter_table so the same revision runs
on SQLite (table rebuild) and Postgres (native ALTER). Timestamp defaults use
sa.func.now(), compiled per dialect.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 15:45:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_AUDIT_ACTIONS = (
    "'approved', 'rejected', 'edited', 'resolved', 'protected_set', "
    "'protected_cleared', 'reply_submitted', 'capacity_updated'"
)
_NEW_AUDIT_ACTIONS = (
    _OLD_AUDIT_ACTIONS
    + ", 'sms_sent', 'sms_skipped', 'sms_failed', "
    "'chat_building_reply', 'chat_operator_message', 'chat_thread_closed'"
)


def upgrade() -> None:
    # --- users: notification channel fields ---
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("phone", sa.String(length=32), nullable=True))
        batch.add_column(
            sa.Column(
                "sms_opted_out", sa.Boolean(), server_default="0", nullable=False
            )
        )

    # --- events: in-app thread close marker ---
    with op.batch_alter_table("events") as batch:
        batch.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))

    # --- audit_log: provider column + extended action CHECK ---
    # Carry the project naming convention so the batch knows the real
    # constraint name is ck_audit_log_action_allowed, dropped by its logical
    # name "action_allowed".
    naming = {"ck": "ck_%(table_name)s_%(constraint_name)s"}
    with op.batch_alter_table("audit_log", naming_convention=naming) as batch:
        batch.add_column(sa.Column("provider", sa.String(length=32), nullable=True))
        batch.drop_constraint("action_allowed", type_="check")
        batch.create_check_constraint(
            "action_allowed", f"action IN ({_NEW_AUDIT_ACTIONS})"
        )

    # --- messages: in-app (event, building) thread ---
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.String(length=64), nullable=False),
        sa.Column("sender_role", sa.String(length=32), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "sender_role IN ('system', 'building_manager', 'operator')",
            name=op.f("ck_messages_sender_role_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            name=op.f("fk_messages_building_id_buildings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_messages_event_id_events"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            name=op.f("fk_messages_sender_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(op.f("ix_messages_building_id"), "messages", ["building_id"], unique=False)
    op.create_index(op.f("ix_messages_event_id"), "messages", ["event_id"], unique=False)
    op.create_index("ix_messages_building_id_id", "messages", ["building_id", "id"], unique=False)

    # --- push_subscriptions: browser Web Push ---
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_push_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_push_subscriptions_endpoint")),
    )
    op.create_index(
        op.f("ix_push_subscriptions_user_id"), "push_subscriptions", ["user_id"], unique=False
    )

    # --- outbound_messages: durable send log (any channel) ---
    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("template", sa.String(length=64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_sid", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_outbound_messages_event_id_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_outbound_messages_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_messages")),
    )
    op.create_index(
        op.f("ix_outbound_messages_event_id"), "outbound_messages", ["event_id"], unique=False
    )
    op.create_index(
        op.f("ix_outbound_messages_user_id"), "outbound_messages", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_outbound_messages_user_id"), table_name="outbound_messages")
    op.drop_index(op.f("ix_outbound_messages_event_id"), table_name="outbound_messages")
    op.drop_table("outbound_messages")

    op.drop_index(op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions")
    op.drop_table("push_subscriptions")

    op.drop_index("ix_messages_building_id_id", table_name="messages")
    op.drop_index(op.f("ix_messages_event_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_building_id"), table_name="messages")
    op.drop_table("messages")

    naming = {"ck": "ck_%(table_name)s_%(constraint_name)s"}
    with op.batch_alter_table("audit_log", naming_convention=naming) as batch:
        batch.drop_constraint("action_allowed", type_="check")
        batch.create_check_constraint(
            "action_allowed", f"action IN ({_OLD_AUDIT_ACTIONS})"
        )
        batch.drop_column("provider")

    with op.batch_alter_table("events") as batch:
        batch.drop_column("closed_at")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("sms_opted_out")
        batch.drop_column("phone")
