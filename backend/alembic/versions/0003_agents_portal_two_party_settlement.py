"""agents, karigar portal, two-party settlement, occasion dates

* users.karigar_id                  - karigar logins (role=karigar) linked to one karigar record
* job_orders.occasion_date / label  - the customer's fixed date (wedding, festival)
* settlement_worksheets             - karigar acceptance/dispute and payment fields
* agent_runs                        - persisted runs of proactive agents, with tool traces

Enum columns are stored as plain strings (native_enum=False, no CHECK), so the new
UserRole.karigar and SettlementStatus values need no type change.

Revision ID: 0003_agents_portal
Revises: 0002_phase2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_agents_portal"
down_revision: Union[str, Sequence[str], None] = "0002_phase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("karigar_id", sa.Uuid(), nullable=True))
        b.create_foreign_key("fk_users_karigar_id", "karigars", ["karigar_id"], ["id"], ondelete="RESTRICT")
        b.create_unique_constraint("uq_users_karigar_id", ["karigar_id"])

    with op.batch_alter_table("job_orders") as b:
        b.add_column(sa.Column("occasion_date", sa.Date(), nullable=True))
        b.add_column(sa.Column("occasion_label", sa.String(length=80), nullable=True))

    with op.batch_alter_table("settlement_worksheets") as b:
        b.add_column(sa.Column("karigar_response_by_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("karigar_response_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("dispute_reason", sa.Text(), nullable=True))
        b.add_column(sa.Column("paid_by_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("payment_ref", sa.String(length=120), nullable=True))
        b.create_foreign_key("fk_sw_karigar_response_by", "users", ["karigar_response_by_id"], ["id"], ondelete="RESTRICT")
        b.create_foreign_key("fk_sw_paid_by", "users", ["paid_by_id"], ["id"], ondelete="RESTRICT")

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("trace_json", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_runs_organisation_id"), "agent_runs", ["organisation_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_kind"), "agent_runs", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_kind"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_organisation_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    with op.batch_alter_table("settlement_worksheets") as b:
        b.drop_constraint("fk_sw_paid_by", type_="foreignkey")
        b.drop_constraint("fk_sw_karigar_response_by", type_="foreignkey")
        for c in ("payment_ref", "paid_at", "paid_by_id", "dispute_reason", "karigar_response_at", "karigar_response_by_id"):
            b.drop_column(c)
    with op.batch_alter_table("job_orders") as b:
        b.drop_column("occasion_label")
        b.drop_column("occasion_date")
    with op.batch_alter_table("users") as b:
        b.drop_constraint("uq_users_karigar_id", type_="unique")
        b.drop_constraint("fk_users_karigar_id", type_="foreignkey")
        b.drop_column("karigar_id")
