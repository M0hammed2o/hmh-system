"""Register three further group companies.

Revision ID: 0077
Revises: 0076
Create Date: 2026-10-16

HMH Group operates under more trading names than the two the database was
seeded with. Kukhanya Kabusha, Premium Structures and Ophezulu are added so
projects, vehicles, procurement and reporting can be attributed to them the
same way as to the existing companies.

Only the name is written. Registration numbers, VAT numbers, addresses and
banking details are deliberately left NULL — inventing them would put
plausible-looking nonsense on documents that go to suppliers and SARS. The
office fills them in through the existing company admin screen.

Idempotent and additive: each company is inserted only if no company of that
name exists, so re-running changes nothing and an environment where the
office already created one keeps that record, with its id and whatever
details were captured. Nothing is updated or deleted.
"""

from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


NEW_COMPANIES = (
    "Kukhanya Kabusha",
    "Premium Structures",
    "Ophezulu",
)


def upgrade() -> None:
    conn = op.get_bind()
    for name in NEW_COMPANIES:
        # Matched case-insensitively and ignoring surrounding space: if the
        # office already added "ophezulu" by hand, that is the same company
        # and must be reused, not duplicated alongside this one.
        conn.exec_driver_sql(
            """
            INSERT INTO companies (id, name, created_at, updated_at)
            SELECT gen_random_uuid(), %(name)s, NOW(), NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM companies
                WHERE LOWER(TRIM(name)) = LOWER(TRIM(%(name)s))
            )
            """,
            {"name": name},
        )


def downgrade() -> None:
    """
    Remove the three companies — but only while nothing references them.

    A company that has acquired projects or supplier links is real
    operating data by then, and dropping it would orphan or cascade into that
    history. In that case this leaves the row alone: an unused company record
    is harmless, losing a project's attribution is not.
    """
    conn = op.get_bind()
    for name in NEW_COMPANIES:
        conn.exec_driver_sql(
            """
            DELETE FROM companies c
            WHERE LOWER(TRIM(c.name)) = LOWER(TRIM(%(name)s))
              AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.company_id = c.id)
              AND NOT EXISTS (
                  SELECT 1 FROM company_supplier_links l WHERE l.company_id = c.id
              )
            """,
            {"name": name},
        )
