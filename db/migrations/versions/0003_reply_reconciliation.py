"""reply reconciliation + extended audit/reply CHECKs for chat & SMS routes

The in-app chat routes and the inbound SMS webhook record an event-scoped
reply (no call_history row) and a "counter" kind with a `kw` amount. This
revision makes `replies` serve both that flow and the approved-call flow:

  - replies.call_id becomes nullable (in-app/SMS replies have no call);
  - replies gains event_id (FK events) and kw (countered amount);
  - replies.kind CHECK adds 'counter';
  - audit_log.action CHECK adds the inbound-SMS webhook actions.

Batch mode so the SQLite table rebuild and Postgres ALTER share one revision.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24 15:55:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAMING = {"ck": "ck_%(table_name)s_%(constraint_name)s"}

_OLD_REPLY_KINDS = "'yes', 'no', 'offer'"
_NEW_REPLY_KINDS = "'yes', 'no', 'offer', 'counter'"

_AUDIT_BASE = (
    "'approved', 'rejected', 'edited', 'resolved', 'protected_set', "
    "'protected_cleared', 'reply_submitted', 'capacity_updated', "
    "'sms_sent', 'sms_skipped', 'sms_failed', 'chat_building_reply', "
    "'chat_operator_message', 'chat_thread_closed'"
)
_AUDIT_SMS = (
    ", 'sms_webhook_invalid_signature', 'sms_unregistered_sender', "
    "'sms_opted_out', 'sms_opted_in', 'sms_unrecognized_body', "
    "'sms_no_active_event', 'sms_received'"
)
_OLD_AUDIT_ACTIONS = _AUDIT_BASE
_NEW_AUDIT_ACTIONS = _AUDIT_BASE + _AUDIT_SMS


def upgrade() -> None:
    # --- replies: event_id + kw columns, nullable call_id, +counter kind ---
    with op.batch_alter_table("replies", naming_convention=_NAMING) as batch:
        batch.add_column(sa.Column("event_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("kw", sa.Float(), nullable=True))
        batch.alter_column(
            "call_id", existing_type=sa.Integer(),
            nullable=True, existing_nullable=False,
        )
        batch.create_foreign_key(
            batch.f("fk_replies_event_id_events"),
            "events",
            ["event_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.drop_constraint("kind_allowed", type_="check")
        batch.create_check_constraint("kind_allowed", f"kind IN ({_NEW_REPLY_KINDS})")
    op.create_index(op.f("ix_replies_event_id"), "replies", ["event_id"], unique=False)

    # --- audit_log: add inbound-SMS webhook actions to the CHECK;
    #     make user_id nullable for anonymous/system audit events ---
    with op.batch_alter_table("audit_log", naming_convention=_NAMING) as batch:
        batch.alter_column(
            "user_id", existing_type=sa.Integer(),
            nullable=True, existing_nullable=False,
        )
        batch.drop_constraint("action_allowed", type_="check")
        batch.create_check_constraint(
            "action_allowed", f"action IN ({_NEW_AUDIT_ACTIONS})"
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_log", naming_convention=_NAMING) as batch:
        batch.drop_constraint("action_allowed", type_="check")
        batch.create_check_constraint(
            "action_allowed", f"action IN ({_OLD_AUDIT_ACTIONS})"
        )
        batch.alter_column(
            "user_id", existing_type=sa.Integer(),
            nullable=False, existing_nullable=True,
        )

    op.drop_index(op.f("ix_replies_event_id"), table_name="replies")
    with op.batch_alter_table("replies", naming_convention=_NAMING) as batch:
        batch.drop_constraint("kind_allowed", type_="check")
        batch.create_check_constraint("kind_allowed", f"kind IN ({_OLD_REPLY_KINDS})")
        batch.drop_constraint(batch.f("fk_replies_event_id_events"), type_="foreignkey")
        batch.alter_column(
            "call_id", existing_type=sa.Integer(),
            nullable=False, existing_nullable=True,
        )
        batch.drop_column("kw")
        batch.drop_column("event_id")
