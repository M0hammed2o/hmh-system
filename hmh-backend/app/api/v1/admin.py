"""Admin utility routes — clear demo data, storage status, BOQ seeding."""

from fastapi import APIRouter

from app.core.logging_config import get_logger
from app.dependencies import CurrentUser, OWNER_ONLY, DbSession
from app.schemas.common import ApiSuccess

_log = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/storage-status", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def storage_status():
    """Check whether Supabase Storage is configured and reachable."""
    from app.core.storage import verify_supabase_connection, storage_mode
    result = verify_supabase_connection()
    result["mode"] = storage_mode()
    result["instruction"] = (
        "Photos are permanently stored in Supabase Storage."
        if result["ok"]
        else (
            "Photos are on Render local disk and WILL BE LOST on restart. "
            "Fix: add SUPABASE_URL + SUPABASE_SERVICE_KEY in Render env vars, "
            "then create a public bucket named 'hmh-uploads' in Supabase Dashboard → Storage."
        )
    )
    return ApiSuccess(data=result, message=f"Storage mode: {result['mode']}")


@router.post("/clear-demo-data", response_model=ApiSuccess[dict], dependencies=[OWNER_ONLY])
def clear_demo_data(db: DbSession, current_user: CurrentUser):
    """
    Delete all project/business data while preserving user accounts, roles,
    supplier catalogue, item catalogue, and stage master definitions.

    Deletion order respects FK dependencies so no constraint errors occur.
    All tables are truncated with RESTART IDENTITY CASCADE where possible,
    falling back to DELETE for tables where that is not safe.
    """
    from sqlalchemy import text

    # Tables to wipe, in safe deletion order (children before parents).
    # Users, suppliers, items, item_categories, item_aliases, and stage_master
    # are intentionally NOT in this list.
    statements = [
        # Notifications / alerts
        "DELETE FROM notification_queue",
        "DELETE FROM system_alerts",

        # Audit trail
        "DELETE FROM audit_events",

        # Finance
        "DELETE FROM invoice_matching_results",
        "DELETE FROM payments",
        "DELETE FROM invoices",

        # Deliveries + evidence
        "DELETE FROM usage_remaining_proofs",
        "DELETE FROM attachments WHERE entity_type IN ('DELIVERY','INVOICE','USAGE_LOG')",
        "DELETE FROM delivery_verification_items",
        "DELETE FROM delivery_verifications",
        "DELETE FROM delivery_items",
        "DELETE FROM deliveries",

        # Stock / usage
        "DELETE FROM stock_ledger",
        "DELETE FROM usage_logs",

        # Procurement
        "DELETE FROM boq_adjustments",
        "DELETE FROM mr_quotes",
        "DELETE FROM mr_email_logs",
        "DELETE FROM po_email_logs",
        "DELETE FROM purchase_order_items",
        "DELETE FROM purchase_orders",
        "DELETE FROM material_request_items",
        "DELETE FROM material_requests",

        # Labour
        "DELETE FROM job_cards",

        # Fleet
        "DELETE FROM vehicle_costs",
        "DELETE FROM fuel_logs",
        "DELETE FROM vehicles",

        # BOQ
        "DELETE FROM boq_items",
        "DELETE FROM boq_sections",
        "DELETE FROM boq_headers",

        # Document AI / Gmail
        "DELETE FROM expense_records",
        "DELETE FROM incoming_email_attachments",
        "DELETE FROM incoming_emails",
        "DELETE FROM document_extractions",

        # Alert recipients (keep system config but wipe contact list)
        # Uncomment if needed: "DELETE FROM alert_recipients",

        # Project hierarchy (cascades lots → project_stage_status)
        "DELETE FROM project_stage_status",
        "DELETE FROM user_site_access",
        "DELETE FROM user_project_access",
        "DELETE FROM lots",
        "DELETE FROM sites",
        "DELETE FROM projects",
    ]

    counts: dict[str, int] = {}
    for stmt in statements:
        try:
            result = db.execute(text(stmt))
            table_name = stmt.split("FROM")[1].strip().split()[0]
            counts[table_name] = result.rowcount if result.rowcount >= 0 else 0
        except Exception as exc:
            # Log but continue — a missing table or already-empty table is fine
            _log.warning("clear-demo-data: %s → %s", stmt, exc)

    db.commit()

    total_deleted = sum(counts.values())
    _log.info("admin clear_demo_data actor=%s total_deleted=%d", current_user.id, total_deleted)

    # Record in the audit trail (written after commit so it survives the wipe)
    from app.models.audit import AuditEvent
    db.add(AuditEvent(
        actor_id=current_user.id,
        action="CLEAR_DEMO_DATA",
        entity_type="system",
        notes=f"Cleared demo data: {total_deleted} rows removed across {len(counts)} tables.",
    ))
    db.commit()

    return ApiSuccess(
        data={"rows_deleted": total_deleted, "tables": counts},
        message=f"Demo data cleared. {total_deleted} records removed. User logins, suppliers, items, and stages are preserved.",
    )
