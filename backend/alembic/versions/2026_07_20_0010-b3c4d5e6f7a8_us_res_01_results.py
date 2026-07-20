"""US-RES-01: results embargo, publications, certificates."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "results_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("release_at", sa.DateTime(), nullable=False),
        sa.Column("audience", sa.JSON(), nullable=False),
        sa.Column("neutral_status", sa.String(length=64), nullable=False),
        sa.Column("award_by_rank", sa.JSON(), nullable=False),
        sa.Column("default_outcome", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id"),
    )
    op.create_index("ix_results_configs_cycle_id", "results_configs", ["cycle_id"])

    op.create_table(
        "certificate_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id", "outcome", "language", name="uq_certificate_templates_cycle_outcome_lang"),
    )
    op.create_index("ix_certificate_templates_cycle_id", "certificate_templates", ["cycle_id"])

    op.create_table(
        "result_publications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("release_at", sa.DateTime(), nullable=False),
        sa.Column("audience", sa.JSON(), nullable=False),
        sa.Column("neutral_status", sa.String(length=64), nullable=False),
        sa.Column("prepared_at", sa.DateTime(), nullable=False),
        sa.Column("prepared_by", sa.UUID(), nullable=True),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("released_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prepared_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["released_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_result_publications_cycle_id", "result_publications", ["cycle_id"])
    op.create_index("ix_result_publications_skill_id", "result_publications", ["skill_id"])

    op.create_table(
        "result_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("supersedes_id", sa.UUID(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["publication_id"], ["result_publications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["result_entries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_result_entries_publication_id", "result_entries", ["publication_id"])
    op.create_index("ix_result_entries_cycle_id", "result_entries", ["cycle_id"])
    op.create_index("ix_result_entries_skill_id", "result_entries", ["skill_id"])
    op.create_index("ix_result_entries_competitor_id", "result_entries", ["competitor_id"])

    op.create_table(
        "certificates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("publication_id", sa.UUID(), nullable=False),
        sa.Column("result_entry_id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("rendered_body", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("supersedes_id", sa.UUID(), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publication_id"], ["result_publications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_entry_id"], ["result_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["certificates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_certificates_cycle_id", "certificates", ["cycle_id"])
    op.create_index("ix_certificates_publication_id", "certificates", ["publication_id"])
    op.create_index("ix_certificates_result_entry_id", "certificates", ["result_entry_id"])
    op.create_index("ix_certificates_competitor_id", "certificates", ["competitor_id"])


def downgrade() -> None:
    op.drop_index("ix_certificates_competitor_id", table_name="certificates")
    op.drop_index("ix_certificates_result_entry_id", table_name="certificates")
    op.drop_index("ix_certificates_publication_id", table_name="certificates")
    op.drop_index("ix_certificates_cycle_id", table_name="certificates")
    op.drop_table("certificates")

    op.drop_index("ix_result_entries_competitor_id", table_name="result_entries")
    op.drop_index("ix_result_entries_skill_id", table_name="result_entries")
    op.drop_index("ix_result_entries_cycle_id", table_name="result_entries")
    op.drop_index("ix_result_entries_publication_id", table_name="result_entries")
    op.drop_table("result_entries")

    op.drop_index("ix_result_publications_skill_id", table_name="result_publications")
    op.drop_index("ix_result_publications_cycle_id", table_name="result_publications")
    op.drop_table("result_publications")

    op.drop_index("ix_certificate_templates_cycle_id", table_name="certificate_templates")
    op.drop_table("certificate_templates")

    op.drop_index("ix_results_configs_cycle_id", table_name="results_configs")
    op.drop_table("results_configs")
