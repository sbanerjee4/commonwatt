"""chat handoff layer: threads, messages, extended audit actions

Adds the automated-agent + human-handoff chat storage against the real schema:
  - threads: one (event, building) conversation with handoff_mode auto/human
  - messages: append-only posted messages (system/agent/building_manager/operator)
and rebuilds the audit_log action CHECK to include the new chat_* actions.

The same revision runs on SQLite and Postgres. The audit_log CHECK is rebuilt
with batch_alter_table so SQLite (which cannot ALTER a CHECK in place) recreates
the table, while Postgres drops and re-adds the named constraint.

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


# Full allow-list AFTER this migration (kept in sync with db.models.AUDIT_ACTIONS).
_AUDIT_ACTIONS_NEW = (
    "approved",
    "rejected",
    "edited",
    "resolved",
    "protected_set",
    "protected_cleared",
    "reply_submitted",
    "capacity_updated",
    "chat_agent_reply",
    "chat_handoff_requested",
    "chat_operator_message",
    "chat_building_reply",
    "chat_thread_closed",
)

# Original allow-list (for downgrade).
_AUDIT_ACTIONS_OLD = (
    "approved",
    "rejected",
    "edited",
    "resolved",
    "protected_set",
    "protected_cleared",
    "reply_submitted",
    "capacity_updated",
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "threads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.String(length=64), nullable=False),
        sa.Column(
            "handoff_mode",
            sa.String(length=16),
            server_default="auto",
            nullable=False,
        ),
        sa.Column(
            "needs_human",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            _in_list("handoff_mode", ("auto", "human")),
            name=op.f("ck_threads_handoff_mode_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            name=op.f("fk_threads_building_id_buildings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_threads_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_threads")),
    )
    op.create_index(op.f("ix_threads_building_id"), "threads", ["building_id"], unique=False)
    op.create_index(op.f("ix_threads_event_id"), "threads", ["event_id"], unique=False)
    op.create_index("uq_threads_event_id", "threads", ["event_id", "building_id"], unique=True)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.String(length=64), nullable=False),
        sa.Column("sender_role", sa.String(length=32), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            _in_list(
                "sender_role",
                ("system", "agent", "building_manager", "operator"),
            ),
            name=op.f("ck_messages_sender_role_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["buildings.id"],
            name=op.f("fk_messages_building_id_buildings"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_messages_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["threads.id"],
            name=op.f("fk_messages_thread_id_threads"),
            ondelete="CASCADE",
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
    op.create_index(op.f("ix_messages_thread_id"), "messages", ["thread_id"], unique=False)

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
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
        op.f("ix_push_subscriptions_user_id"),
        "push_subscriptions",
        ["user_id"],
        unique=False,
    )

    # Rebuild the audit_log action CHECK to include the new chat_* actions.
    # batch_alter_table applies the naming convention, so the constraint is
    # referenced by its bare name ("action_allowed"), not the rendered
    # "ck_audit_log_action_allowed".
    naming = {"ck": "ck_%(table_name)s_%(constraint_name)s"}
    with op.batch_alter_table(
        "audit_log", schema=None, naming_convention=naming
    ) as batch:
        batch.drop_constraint("action_allowed", type_="check")
        batch.create_check_constraint(
            "action_allowed", _in_list("action", _AUDIT_ACTIONS_NEW)
        )


def downgrade() -> None:
    naming = {"ck": "ck_%(table_name)s_%(constraint_name)s"}
    with op.batch_alter_table(
        "audit_log", schema=None, naming_convention=naming
    ) as batch:
        batch.drop_constraint("action_allowed", type_="check")
        batch.create_check_constraint(
            "action_allowed", _in_list("action", _AUDIT_ACTIONS_OLD)
        )

    op.drop_index(op.f("ix_messages_thread_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_event_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_building_id"), table_name="messages")
    op.drop_table("messages")

    op.drop_index(op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions")
    op.drop_table("push_subscriptions")

    op.drop_index("uq_threads_event_id", table_name="threads")
    op.drop_index(op.f("ix_threads_event_id"), table_name="threads")
    op.drop_index(op.f("ix_threads_building_id"), table_name="threads")
    op.drop_table("threads")
