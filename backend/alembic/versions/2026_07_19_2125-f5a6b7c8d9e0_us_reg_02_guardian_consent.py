"""US-REG-02: guardian consent columns + consent_requests table."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("registration_form_definitions", sa.Column("minor_age_under", sa.Integer(), nullable=True))
    op.add_column("registration_form_definitions", sa.Column("minor_reference_date", sa.Date(), nullable=True))

    op.add_column("competitors", sa.Column("guardian_name", sa.String(length=200), nullable=True))
    op.add_column("competitors", sa.Column("guardian_email", sa.String(length=255), nullable=True))
    op.add_column("competitors", sa.Column("guardian_phone", sa.String(length=32), nullable=True))
    op.add_column("competitors", sa.Column("consent_participation_at", sa.DateTime(), nullable=True))
    op.add_column("competitors", sa.Column("consent_participation_by", sa.String(length=255), nullable=True))
    op.add_column("competitors", sa.Column("consent_public_at", sa.DateTime(), nullable=True))
    op.add_column("competitors", sa.Column("consent_public_by", sa.String(length=255), nullable=True))
    op.add_column(
        "competitors",
        sa.Column("public_profile_visible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "consent_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["competitors.id"],
            name=op.f("fk_consent_requests_competitor_id_competitors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consent_requests")),
        sa.UniqueConstraint("token", name=op.f("uq_consent_requests_token")),
    )
    op.create_index(op.f("ix_consent_requests_competitor_id"), "consent_requests", ["competitor_id"], unique=False)
    op.create_index(op.f("ix_consent_requests_token"), "consent_requests", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_consent_requests_token"), table_name="consent_requests")
    op.drop_index(op.f("ix_consent_requests_competitor_id"), table_name="consent_requests")
    op.drop_table("consent_requests")
    op.drop_column("competitors", "public_profile_visible")
    op.drop_column("competitors", "consent_public_by")
    op.drop_column("competitors", "consent_public_at")
    op.drop_column("competitors", "consent_participation_by")
    op.drop_column("competitors", "consent_participation_at")
    op.drop_column("competitors", "guardian_phone")
    op.drop_column("competitors", "guardian_email")
    op.drop_column("competitors", "guardian_name")
    op.drop_column("registration_form_definitions", "minor_reference_date")
    op.drop_column("registration_form_definitions", "minor_age_under")
