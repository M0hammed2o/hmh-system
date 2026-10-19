"""Register HMH Group and Minerat as company records.

Revision ID: 0079
Revises: 0078
Create Date: 2026-10-19

Fixes a regression found by authenticated testing against live production.

The two original trading names were never rows in `companies`. They existed
only as hardcoded `<option>` values written into `projects.client_name`, and
as fixed letterhead keys in `email_service`. The companies table was used for
something narrower — linking approved suppliers — and nobody had needed a row
there for them.

Migration 0077 then added the three new companies, and the project company
selector was changed to read the table instead of its hardcoded list. The
result on production: staff could select Kukhanya Kabusha, Premium Structures
or Ophezulu when creating a project, but no longer HMH Group or Minerat —
the two they actually use. Verified on the live site: the companies table
held exactly three rows, and both existing projects carry
`client_name = 'Minerat Construction & Civils'` with no `company_id`.

The names here are byte-identical to what the old hardcoded options wrote, so
a project already carrying one of them matches a real row rather than
rendering as an unrecognised leftover.

Idempotent and additive, like 0077: inserts only where no company of that
name exists, matched case- and whitespace-insensitively, so an environment
where the office already created one keeps that record and its id. Only the
name is written — registration and VAT numbers appear on supplier-facing
documents and are not for a migration to invent.
"""

from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


# Exactly as the retired hardcoded <option> values wrote them.
EXISTING_COMPANIES = (
    "HMH Group",
    "Minerat Construction & Civils",
)


def upgrade() -> None:
    conn = op.get_bind()
    for name in EXISTING_COMPANIES:
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
    Remove them again — but only while nothing references them.

    A company that has acquired projects or supplier links is real operating
    data by then, and dropping it would orphan that history. An unused
    company row is harmless; losing a project's attribution is not.
    """
    conn = op.get_bind()
    for name in EXISTING_COMPANIES:
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
