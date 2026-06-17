/**
 * Phase 4 — Procurement Reconciliation
 * Dashboard + procurement chain records with variance checking.
 * Manual Approve / Reject workflows. No AI.
 */
import React, { lazy, Suspense, useEffect, useState } from "react";
const InvoiceReconciliationPage = lazy(() => import("./InvoiceReconciliationPage"));
import {
  CheckCircle2, AlertTriangle, Clock, XCircle, FileCheck2,
  ChevronDown, ChevronRight, RefreshCw, Plus, Trash2,
  ClipboardList, FileText, Package, Truck, Receipt,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import {
  reconciliationApi,
  type Reconciliation,
  type ReconciliationCreate,
  type ReconciliationDashboard,
  type ReconciliationStatus,
  type VarianceField,
  RECON_STATUS_LABELS,
} from "@/api/reconciliation";

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmt = (n: number) =>
  `R ${n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const fmtDate = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })
    : "—";

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ReconciliationStatus }) {
  const styles: Record<ReconciliationStatus, string> = {
    PENDING:           "bg-muted text-muted-foreground",
    MATCHED:           "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    VARIANCE_DETECTED: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
    APPROVED:          "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    REJECTED:          "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  };
  const icons: Record<ReconciliationStatus, React.ReactNode> = {
    PENDING:           <Clock className="w-3 h-3" />,
    MATCHED:           <CheckCircle2 className="w-3 h-3" />,
    VARIANCE_DETECTED: <AlertTriangle className="w-3 h-3" />,
    APPROVED:          <CheckCircle2 className="w-3 h-3" />,
    REJECTED:          <XCircle className="w-3 h-3" />,
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${styles[status]}`}>
      {icons[status]}
      {RECON_STATUS_LABELS[status]}
    </span>
  );
}

// ── Dashboard stat card ───────────────────────────────────────────────────────

function StatCard({
  label, value, icon: Icon, color,
}: {
  label: string; value: number; icon: React.ElementType; color: string;
}) {
  return (
    <div className={`bg-card border border-border rounded-xl p-4 flex items-center gap-3`}>
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-2xl font-bold leading-none">{value}</p>
        <p className="text-xs text-muted-foreground mt-1">{label}</p>
      </div>
    </div>
  );
}

// ── Variance table ────────────────────────────────────────────────────────────

function VarianceRow({ field }: { field: VarianceField }) {
  return (
    <tr className={field.has_variance ? "bg-amber-50/50 dark:bg-amber-900/10" : ""}>
      <td className="px-3 py-2 text-xs text-muted-foreground">{field.name}</td>
      <td className="px-3 py-2 text-xs text-right">{fmt(field.a_value)}</td>
      <td className="px-3 py-2 text-xs text-right">{fmt(field.b_value)}</td>
      <td className={`px-3 py-2 text-xs text-right font-medium ${
        field.has_variance
          ? field.diff > 0 ? "text-amber-600" : "text-destructive"
          : "text-success"
      }`}>
        {field.diff === 0 ? "—" : `${field.diff > 0 ? "+" : ""}${fmt(field.diff)}`}
      </td>
      <td className="px-3 py-2 text-xs text-center">
        {field.has_variance ? (
          <AlertTriangle className="w-3.5 h-3.5 text-amber-500 mx-auto" />
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5 text-success mx-auto" />
        )}
      </td>
    </tr>
  );
}

function VarianceSection({ recon }: { recon: Reconciliation }) {
  const vd = recon.variance_data;
  if (!vd || vd.comparisons.length === 0) {
    return (
      <p className="text-xs text-muted-foreground italic">
        No variance data. Link an invoice and click Recompute.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {vd.comparisons.map((comp) => (
        <div key={comp.label}>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
            {comp.label}
          </p>
          <table className="w-full text-sm border border-border rounded-lg overflow-hidden">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="px-3 py-1.5 text-xs text-left text-muted-foreground font-medium">Field</th>
                <th className="px-3 py-1.5 text-xs text-right text-muted-foreground font-medium">
                  {comp.fields[0]?.a_label}
                </th>
                <th className="px-3 py-1.5 text-xs text-right text-muted-foreground font-medium">
                  {comp.fields[0]?.b_label}
                </th>
                <th className="px-3 py-1.5 text-xs text-right text-muted-foreground font-medium">Δ Diff</th>
                <th className="px-3 py-1.5 text-xs text-center text-muted-foreground font-medium">Match</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {comp.fields.map((f) => (
                <VarianceRow key={f.name} field={f} />
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {vd.has_variance && (
        <p className="text-xs text-amber-600 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5" />
          {vd.total_variances} variance{vd.total_variances !== 1 ? "s" : ""} detected (threshold: R {vd.threshold_rands?.toFixed(2)})
        </p>
      )}
      {!vd.has_variance && vd.comparisons.length > 0 && (
        <p className="text-xs text-success flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5" />
          All amounts match within tolerance.
        </p>
      )}
    </div>
  );
}

// ── Chain summary row ─────────────────────────────────────────────────────────

function ChainPill({
  label, present, icon: Icon,
}: { label: string; present: boolean; icon: React.ElementType }) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded font-mono ${
      present ? "bg-success/15 text-success" : "bg-muted text-muted-foreground/50"
    }`}>
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}

// ── Reconciliation detail modal ───────────────────────────────────────────────

function ReconciliationDetailModal({
  recon,
  onClose,
  onSaved,
}: {
  recon: Reconciliation;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [notes, setNotes] = useState(recon.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [recomputing, setRecomputing] = useState(false);
  const [error, setError] = useState("");
  const [current, setCurrent] = useState<Reconciliation>(recon);

  const canReview = !["APPROVED", "REJECTED"].includes(current.status);

  const handleAction = async (status: "APPROVED" | "REJECTED") => {
    setSaving(true);
    setError("");
    try {
      const updated = await reconciliationApi.update(current.id, { status, notes: notes || null });
      setCurrent(updated);
      onSaved();
    } catch {
      setError("Failed to save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleRecompute = async () => {
    setRecomputing(true);
    setError("");
    try {
      const updated = await reconciliationApi.recompute(current.id);
      setCurrent(updated);
      onSaved();
    } catch {
      setError("Recompute failed.");
    } finally {
      setRecomputing(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={`Reconciliation — ${current.reconciliation_number}`}
      size="lg"
    >
      <div className="p-6 space-y-5 max-h-[80vh] overflow-y-auto">
        {/* Status + chain */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <StatusBadge status={current.status} />
          <div className="flex items-center gap-1.5 flex-wrap">
            <ChainPill label="MR"   present={!!current.material_request_id} icon={ClipboardList} />
            <ChainPill label="Q"    present={!!current.quotation_id}        icon={FileText} />
            <ChainPill label="PO"   present={!!current.purchase_order_id}   icon={Package} />
            <ChainPill label="Del"  present={!!current.delivery_id}         icon={Truck} />
            <ChainPill label="Inv"  present={!!current.invoice_id}          icon={Receipt} />
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={handleRecompute}
            disabled={recomputing}
            className="h-7 text-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${recomputing ? "animate-spin" : ""}`} />
            Recompute
          </Button>
        </div>

        {/* Document links */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {current.po && (
            <div className="bg-muted/30 rounded-lg p-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Purchase Order</p>
              <p className="text-sm font-mono font-semibold">{current.po.po_number}</p>
              {current.po.supplier_name && <p className="text-xs text-muted-foreground">{current.po.supplier_name}</p>}
              <p className="text-xs text-muted-foreground">{fmtDate(current.po.po_date)}</p>
              <div className="mt-2 flex gap-3 text-xs">
                <span>Net: {fmt(current.po.subtotal_amount)}</span>
                <span>VAT: {fmt(current.po.vat_amount)}</span>
                <span className="font-medium">Total: {fmt(current.po.total_amount)}</span>
              </div>
            </div>
          )}

          {current.invoice ? (
            <div className="bg-muted/30 rounded-lg p-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Invoice</p>
              <p className="text-sm font-mono font-semibold">{current.invoice.invoice_number}</p>
              <p className="text-xs text-muted-foreground">{fmtDate(current.invoice.invoice_date)}</p>
              {current.invoice.due_date && (
                <p className="text-xs text-muted-foreground">Due: {fmtDate(current.invoice.due_date)}</p>
              )}
              <div className="mt-2 flex gap-3 text-xs">
                {current.invoice.subtotal_amount != null && (
                  <span>Net: {fmt(current.invoice.subtotal_amount)}</span>
                )}
                <span className="font-medium">Total: {fmt(current.invoice.total_amount)}</span>
              </div>
            </div>
          ) : (
            <div className="bg-muted/20 rounded-lg p-3 border border-dashed border-border">
              <p className="text-xs text-muted-foreground">No invoice linked yet.</p>
            </div>
          )}

          {current.quotation && (
            <div className="bg-muted/30 rounded-lg p-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Quotation</p>
              <p className="text-sm font-mono font-semibold">{current.quotation.quote_number}</p>
              <p className="text-xs text-muted-foreground">{fmtDate(current.quotation.quote_date)}</p>
              <div className="mt-2 flex gap-3 text-xs">
                <span>Net: {fmt(current.quotation.net_amount)}</span>
                <span className="font-medium">Gross: {fmt(current.quotation.gross_amount)}</span>
              </div>
            </div>
          )}

          {current.delivery && (
            <div className="bg-muted/30 rounded-lg p-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Delivery</p>
              <p className="text-sm font-mono font-semibold">{current.delivery.delivery_number ?? "—"}</p>
              <p className="text-xs text-muted-foreground">{fmtDate(current.delivery.delivery_date)}</p>
              <p className="text-xs text-muted-foreground">{current.delivery.items_count} items</p>
            </div>
          )}

          {current.material_request && (
            <div className="bg-muted/30 rounded-lg p-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Material Request</p>
              <p className="text-sm font-mono font-semibold">{current.material_request.mr_number}</p>
            </div>
          )}
        </div>

        {/* Variance section */}
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Variance Analysis</p>
          <VarianceSection recon={current} />
        </div>

        {/* Review section */}
        {current.status !== "PENDING" && (
          <div className="border-t border-border pt-4 text-xs text-muted-foreground">
            {current.reviewed_by_name && (
              <p>Reviewed by: <span className="text-foreground font-medium">{current.reviewed_by_name}</span></p>
            )}
            {current.reviewed_at && (
              <p>Reviewed at: {fmtDate(current.reviewed_at)}</p>
            )}
          </div>
        )}

        {/* Notes + actions */}
        <div className="space-y-3 border-t border-border pt-4">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Review Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
              placeholder="Add notes for this reconciliation review…"
              disabled={!canReview}
            />
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          {canReview && (
            <div className="flex items-center justify-between gap-2">
              <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive border-destructive/40 hover:bg-destructive/10"
                  onClick={() => handleAction("REJECTED")}
                  disabled={saving}
                >
                  <XCircle className="w-3.5 h-3.5 mr-1.5" />
                  Reject
                </Button>
                <Button
                  size="sm"
                  onClick={() => handleAction("APPROVED")}
                  disabled={saving}
                >
                  <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                  {saving ? "Saving…" : "Approve Match"}
                </Button>
              </div>
            </div>
          )}

          {!canReview && (
            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}

// ── Create reconciliation modal ───────────────────────────────────────────────

function CreateReconciliationModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [poId, setPoId] = useState("");
  const [invoiceId, setInvoiceId] = useState("");
  const [quotationId, setQuotationId] = useState("");
  const [deliveryId, setDeliveryId] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!poId.trim()) { setError("Purchase Order ID is required."); return; }
    setSaving(true);
    setError("");
    try {
      const body: ReconciliationCreate = {
        purchase_order_id: poId.trim(),
        invoice_id:   invoiceId.trim()   || null,
        quotation_id: quotationId.trim() || null,
        delivery_id:  deliveryId.trim()  || null,
        notes: notes.trim() || null,
      };
      await reconciliationApi.create(body);
      onCreated();
      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to create reconciliation.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="New Reconciliation Record" size="md">
      <div className="p-6 space-y-4">
        <p className="text-xs text-muted-foreground">
          Link a Purchase Order to its Invoice, Delivery, and Quotation.
          Variances will be computed automatically.
        </p>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Purchase Order ID <span className="text-destructive">*</span></label>
            <input
              type="text"
              value={poId}
              onChange={(e) => setPoId(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs font-mono"
              placeholder="UUID of the Purchase Order"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Invoice ID (optional)</label>
            <input
              type="text"
              value={invoiceId}
              onChange={(e) => setInvoiceId(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs font-mono"
              placeholder="Link invoice to enable PO vs Invoice comparison"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Quotation ID (optional)</label>
              <input
                type="text"
                value={quotationId}
                onChange={(e) => setQuotationId(e.target.value)}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs font-mono"
                placeholder="Auto-resolved from PO if blank"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Delivery ID (optional)</label>
              <input
                type="text"
                value={deliveryId}
                onChange={(e) => setDeliveryId(e.target.value)}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs font-mono"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
            />
          </div>
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={handleSubmit} disabled={saving || !poId.trim()}>
            {saving ? "Creating…" : "Create & Compute Variances"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ── Reconciliation list row ───────────────────────────────────────────────────

function ReconciliationRow({
  recon,
  onView,
  onDelete,
}: {
  recon: Reconciliation;
  onView: () => void;
  onDelete: () => void;
}) {
  const vd = recon.variance_data;
  return (
    <tr className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
      <td className="px-4 py-3">
        <p className="text-sm font-mono font-semibold">{recon.reconciliation_number}</p>
        <p className="text-xs text-muted-foreground">{fmtDate(recon.created_at)}</p>
      </td>
      <td className="px-4 py-3">
        {recon.po ? (
          <>
            <p className="text-sm font-medium">{recon.po.po_number}</p>
            {recon.po.supplier_name && (
              <p className="text-xs text-muted-foreground">{recon.po.supplier_name}</p>
            )}
          </>
        ) : (
          <span className="text-xs text-muted-foreground italic">—</span>
        )}
      </td>
      <td className="px-4 py-3 hidden md:table-cell">
        {recon.invoice ? (
          <span className="text-sm font-mono">{recon.invoice.invoice_number}</span>
        ) : (
          <span className="text-xs text-muted-foreground italic">Not linked</span>
        )}
      </td>
      <td className="px-4 py-3 hidden sm:table-cell">
        {vd ? (
          <span className={`text-xs font-medium ${vd.has_variance ? "text-amber-600" : "text-success"}`}>
            {vd.has_variance ? `${vd.total_variances} variance${vd.total_variances !== 1 ? "s" : ""}` : "No variance"}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={recon.status} />
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-1">
          <Button size="sm" variant="outline" onClick={onView} className="h-7 text-xs">
            Review
          </Button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
            title="Delete"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ReconciliationPage() {
  const [activeTab, setActiveTab] = useState<"records" | "proof-packs">("records");
  const [dashboard, setDashboard] = useState<ReconciliationDashboard | null>(null);
  const [records, setRecords] = useState<Reconciliation[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<ReconciliationStatus | "ALL">("ALL");
  const [selected, setSelected] = useState<Reconciliation | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const [dash, recs] = await Promise.all([
        reconciliationApi.dashboard(),
        reconciliationApi.list(
          statusFilter !== "ALL" ? { status: statusFilter } : undefined
        ),
      ]);
      setDashboard(dash);
      setRecords(recs);
    } catch {
      setError("Failed to load reconciliation data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [statusFilter]);

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this reconciliation record?")) return;
    try {
      await reconciliationApi.delete(id);
      load();
    } catch {
      setError("Failed to delete record.");
    }
  };

  const STATUS_FILTERS: Array<{ label: string; value: ReconciliationStatus | "ALL" }> = [
    { label: "All",              value: "ALL" },
    { label: "Pending",          value: "PENDING" },
    { label: "Matched",          value: "MATCHED" },
    { label: "Variance",         value: "VARIANCE_DETECTED" },
    { label: "Approved",         value: "APPROVED" },
    { label: "Rejected",         value: "REJECTED" },
  ];

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header + Tabs */}
      <div>
        <h1 className="text-xl font-bold">Reconciliation</h1>
        <div className="flex gap-1 mt-3 border-b border-border">
          <button
            onClick={() => setActiveTab("records")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === "records"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Reconciliation Records
          </button>
          <button
            onClick={() => setActiveTab("proof-packs")}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === "proof-packs"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Invoice Proof Packs
          </button>
        </div>
      </div>

      {/* Proof Packs tab */}
      {activeTab === "proof-packs" && (
        <Suspense fallback={<div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" /></div>}>
          <InvoiceReconciliationPage />
        </Suspense>
      )}

      {/* Records tab content below */}
      {activeTab === "records" && <>

      {/* Dashboard stats */}
      {dashboard && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard
            label="Pending Review"
            value={dashboard.pending}
            icon={Clock}
            color="bg-muted text-muted-foreground"
          />
          <StatCard
            label="Matched"
            value={dashboard.matched}
            icon={CheckCircle2}
            color="bg-success/10 text-success"
          />
          <StatCard
            label="Variances"
            value={dashboard.variance_detected}
            icon={AlertTriangle}
            color="bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400"
          />
          <StatCard
            label="Awaiting Approval"
            value={dashboard.awaiting_review}
            icon={FileCheck2}
            color="bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400"
          />
        </div>
      )}

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Records section */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border flex-wrap">
          <div className="flex items-center gap-1.5 flex-wrap">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setStatusFilter(f.value)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                  statusFilter === f.value
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                }`}
              >
                {f.label}
                {f.value !== "ALL" && dashboard && (
                  <span className="ml-1 opacity-70">
                    ({dashboard[f.value.toLowerCase() as keyof ReconciliationDashboard] as number})
                  </span>
                )}
              </button>
            ))}
          </div>
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="w-3.5 h-3.5 mr-1.5" />
            New Record
          </Button>
        </div>

        {/* Table */}
        {loading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 rounded-lg" />)}
          </div>
        ) : records.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            <FileCheck2 className="w-8 h-8 mx-auto mb-2 text-muted-foreground/50" />
            {statusFilter !== "ALL"
              ? `No ${RECON_STATUS_LABELS[statusFilter as ReconciliationStatus]} records.`
              : "No reconciliation records yet. Click New Record to start."}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">Record #</th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">Purchase Order</th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground hidden md:table-cell">Invoice</th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground hidden sm:table-cell">Variance</th>
                <th className="text-left px-4 py-2.5 text-xs font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <ReconciliationRow
                  key={r.id}
                  recon={r}
                  onView={() => setSelected(r)}
                  onDelete={() => handleDelete(r.id)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modals */}
      {selected && (
        <ReconciliationDetailModal
          recon={selected}
          onClose={() => setSelected(null)}
          onSaved={load}
        />
      )}

      {showCreate && (
        <CreateReconciliationModal
          onClose={() => setShowCreate(false)}
          onCreated={load}
        />
      )}

      </>}
    </div>
  );
}
