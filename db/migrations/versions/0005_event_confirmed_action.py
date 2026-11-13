"""audit_log action 'confirmed' (operator confirms an event)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12 00:00:00

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAMING = {"ck": "ck_%(table_name)s_%(constraint_name)s"}

_ACTIONS_OLD = (
    "approved", "rejected", "edited", "resolved", "protected_set",
    "protected_cleared", "reply_submitted", "capacity_updated",
    "chat_agent_reply", "chat_handoff_requested", "chat_building_reply",
    "chat_operator_message", "chat_thread_closed",
)
_ACTIONS_NEW = _ACTIONS_OLD + ("confirmed",)


def _in_list(column, values):
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _set_actions(values) -> None:
    with op.batch_alter_table("audit_log", schema=None, naming_convention=_NAMING) as b:
        b.drop_constraint("action_allowed", type_="check")
        b.create_check_constraint("action_allowed", _in_list("action", values))


def upgrade() -> None:
    _set_actions(_ACTIONS_NEW)


def downgrade() -> None:
    _set_actions(_ACTIONS_OLD)
