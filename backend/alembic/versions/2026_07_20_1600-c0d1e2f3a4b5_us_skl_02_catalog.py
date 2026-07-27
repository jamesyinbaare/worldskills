"""US-SKL-02 catalog + cycle association — Alembic migration."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "families",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "catalog_skills",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=True),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_catalog_skills_family_id"), "catalog_skills", ["family_id"])

    op.add_column("skills", sa.Column("catalog_skill_id", sa.UUID(), nullable=True))
    op.add_column("skills", sa.Column("max_age", sa.Integer(), nullable=True))
    op.add_column("skills", sa.Column("age_reference_date", sa.Date(), nullable=True))
    op.add_column("skills", sa.Column("open_category_enabled", sa.Boolean(), nullable=True))
    op.create_foreign_key(
        op.f("fk_skills_catalog_skill_id_catalog_skills"),
        "skills",
        "catalog_skills",
        ["catalog_skill_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_skills_catalog_skill_id"), "skills", ["catalog_skill_id"])
    op.create_unique_constraint(
        "uq_skills_cycle_id_catalog_skill_id",
        "skills",
        ["cycle_id", "catalog_skill_id"],
    )

    # Backfill embedded age fields from linked age_rules where present
    op.execute(
        """
        UPDATE skills AS s
        SET max_age = a.max_age,
            age_reference_date = a.reference_date,
            open_category_enabled = a.open_category_enabled
        FROM age_rules AS a
        WHERE s.age_rule_id = a.id
          AND s.max_age IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("uq_skills_cycle_id_catalog_skill_id", "skills", type_="unique")
    op.drop_index(op.f("ix_skills_catalog_skill_id"), table_name="skills")
    op.drop_constraint(op.f("fk_skills_catalog_skill_id_catalog_skills"), "skills", type_="foreignkey")
    op.drop_column("skills", "open_category_enabled")
    op.drop_column("skills", "age_reference_date")
    op.drop_column("skills", "max_age")
    op.drop_column("skills", "catalog_skill_id")
    op.drop_index(op.f("ix_catalog_skills_family_id"), table_name="catalog_skills")
    op.drop_table("catalog_skills")
    op.drop_table("families")
