"""US-REG-01: registration windows, forms, competitor profile columns, idempotency."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("competitors", sa.Column("given_names", sa.String(length=100), nullable=True))
    op.add_column("competitors", sa.Column("family_name", sa.String(length=100), nullable=True))
    op.add_column("competitors", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("competitors", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("competitors", sa.Column("mobile", sa.String(length=32), nullable=True))
    op.add_column("competitors", sa.Column("whatsapp", sa.String(length=32), nullable=True))
    op.add_column("competitors", sa.Column("national_id", sa.String(length=64), nullable=True))
    op.add_column("competitors", sa.Column("photo_key", sa.String(length=512), nullable=True))
    op.add_column("competitors", sa.Column("coach", sa.JSON(), nullable=True))
    op.add_column("competitors", sa.Column("flags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column("competitors", sa.Column("registration_payload", sa.JSON(), nullable=True))
    op.create_index(op.f("ix_competitors_national_id"), "competitors", ["national_id"], unique=False)
    op.create_unique_constraint("uq_competitors_cycle_id_ref_no", "competitors", ["cycle_id", "ref_no"])

    op.create_table(
        "registration_windows",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("opens_at", sa.DateTime(), nullable=False),
        sa.Column("closes_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], name=op.f("fk_registration_windows_cycle_id_cycles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registration_windows")),
        sa.UniqueConstraint("cycle_id", name=op.f("uq_registration_windows_cycle_id")),
    )
    op.create_index(op.f("ix_registration_windows_cycle_id"), "registration_windows", ["cycle_id"], unique=True)

    op.create_table(
        "registration_form_definitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("max_skills", sa.Integer(), nullable=False),
        sa.Column("photo_max_mb", sa.Integer(), nullable=False),
        sa.Column("photo_formats", sa.JSON(), nullable=False),
        sa.Column("national_id_pattern", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["cycles.id"],
            name=op.f("fk_registration_form_definitions_cycle_id_cycles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registration_form_definitions")),
        sa.UniqueConstraint("cycle_id", name=op.f("uq_registration_form_definitions_cycle_id")),
    )
    op.create_index(
        op.f("ix_registration_form_definitions_cycle_id"), "registration_form_definitions", ["cycle_id"], unique=True
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], name=op.f("fk_idempotency_records_cycle_id_cycles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_records")),
        sa.UniqueConstraint("cycle_id", "key", name="uq_idempotency_records_cycle_key"),
    )
    op.create_index(op.f("ix_idempotency_records_cycle_id"), "idempotency_records", ["cycle_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_idempotency_records_cycle_id"), table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index(op.f("ix_registration_form_definitions_cycle_id"), table_name="registration_form_definitions")
    op.drop_table("registration_form_definitions")
    op.drop_index(op.f("ix_registration_windows_cycle_id"), table_name="registration_windows")
    op.drop_table("registration_windows")
    op.drop_constraint("uq_competitors_cycle_id_ref_no", "competitors", type_="unique")
    op.drop_index(op.f("ix_competitors_national_id"), table_name="competitors")
    op.drop_column("competitors", "registration_payload")
    op.drop_column("competitors", "flags")
    op.drop_column("competitors", "coach")
    op.drop_column("competitors", "photo_key")
    op.drop_column("competitors", "national_id")
    op.drop_column("competitors", "whatsapp")
    op.drop_column("competitors", "mobile")
    op.drop_column("competitors", "email")
    op.drop_column("competitors", "date_of_birth")
    op.drop_column("competitors", "family_name")
    op.drop_column("competitors", "given_names")
