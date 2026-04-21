import { useEffect, useState } from "react";
import { Plus, ShoppingCart, FileText, CheckCircle2, ChevronDown, ChevronRight, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import { PageHeader } from "@/components/shared/PageHeader";
import { Tabs } from "@/components/shared/Tabs";
import { StatCard } from "@/components/shared/StatCard";
import { projectsApi, type Project } from "@/api/projects";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import {
  purchaseOrdersApi,
  type PurchaseOrder,
  type RecordStatus,
  type VatMode,
  type POItemCreate,
} from "@/api/purchaseOrders";
import { materialRequestsApi, type MaterialRequest, type MRStatus } from "@/api/materialRequests";
import { formatCurrency, formatDate } from "@/lib/format";

type POStatus = Extract<RecordStatus, "DRAFT" | "SUBMITTED" | "APPROVED" | "SENT" | "RECEIVED" | "CANCELLED">;

const poStatusVariant: Record<POStatus, "outline" | "secondary" | "success" | "default" | "destructive" | "warning"> = {
  DRAFT: "outline",
  SUBMITTED: "secondary",
  APPROVED: "success",
  SENT: "default",
  RECEIVED: "success",
  CANCELLED: "destructive",
};

const mrStatusVariant: Record<MRStatus, "outline" | "secondary" | "success" | "destructive"> = {
  DRAFT: "outline",
  SUBMITTED: "secondary",
  APPROVED: "success",
  REJECTED: "destructive",
};

const PAGE_TABS = [
  { key: "po", label: "Purchase Orders" },
  { key: "mr", label: "Material Requests" },
];

// Status workflow: which action is available in each state
const STATUS_ACTIONS: Partial<Record<POStatus, { label: string; next: RecordStatus; variant: "default" | "outline" | "secondary" }>> = {
  DRAFT:      { label: "Submit for Approval", next: "SUBMITTED", variant: "outline" },
  SUBMITTED:  { label: "Approve",             next: "APPROVED",  variant: "default" },
  APPROVED:   { label: "Mark as Sent",        next: "SENT",      variant: "secondary" },
};

// ─── Add Item Form ─────────────────────────────────────────────────────────────
function AddItemForm({ poId, onAdded }: { poId: string; onAdded: (poId: string) => void }) {
  const [desc, setDesc] = useState("");
  const [qty, setQty] = useState("1");
  const [unit, setUnit] = useState("");
  const [rate, setRate] = useState("");
  const [vatMode, setVatMode] = useState<VatMode>("INCLUSIVE");
  const [saving, setSaving] = useState(false);

  const handleAdd = async () => {
    if (!desc.trim() || !qty) return;
    setSaving(true);
    try {
      const body: POItemCreate = {
        description: desc.trim(),
        quantity_ordered: parseFloat(qty),
        unit: unit.trim() || null,
        rate: rate ? parseFloat(rate) : null,
        vat_mode: vatMode,
        vat_rate: 15,
      };
      await purchaseOrdersApi.addItem(poId, body);
      setDesc(""); setQty("1"); setUnit(""); setRate("");
      onAdded(poId);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-3 pt-3 border-t border-border/50">
      <p className="text-xs font-medium text-muted-foreground mb-2">Add Line Item</p>
      <div className="flex flex-wrap gap-2 items-end">
        <div className="flex-1 min-w-[160px]">
          <input
            type="text"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="Description *"
            className="w-full h-8 rounded border border-input bg-background px-2 text-xs"
          />
        </div>
        <div className="w-16">
          <input
            type="number"
            min="0.01"
            step="any"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder="Qty"
            className="w-full h-8 rounded border border-input bg-background px-2 text-xs"
          />
        </div>
        <div className="w-16">
          <input
            type="text"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            placeholder="Unit"
            className="w-full h-8 rounded border border-input bg-background px-2 text-xs"
          />
        </div>
        <div className="w-24">
          <input
            type="number"
            min="0"
            step="0.01"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            placeholder="Rate (R)"
            className="w-full h-8 rounded border border-input bg-background px-2 text-xs"
          />
        </div>
        <div className="w-28">
          <select
            value={vatMode}
            onChange={(e) => setVatMode(e.target.value as VatMode)}
            className="w-full h-8 rounded border border-input bg-background px-2 text-xs"
          >
            <option value="INCLUSIVE">VAT Incl.</option>
            <option value="EXCLUSIVE">VAT Excl.</option>
          </select>
        </div>
        <Button size="sm" className="h-8 text-xs px-3" onClick={handleAdd} disabled={saving || !desc.trim()}>
          {saving ? "Adding…" : "Add"}
        </Button>
      </div>
    </div>
  );
}

// ─── PO Detail Row ──────────────────────────────────────────────────────────────
function PORow({
  po,
  supplierName,
  onStatusChange,
  onItemAdded,
}: {
  po: PurchaseOrder;
  supplierName: string;
  onStatusChange: (poId: string, next: RecordStatus) => Promise<void>;
  onItemAdded: (poId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [updating, setUpdating] = useState(false);
  const status = po.status as POStatus;
  const action = STATUS_ACTIONS[status];

  const handleAction = async () => {
    if (!action) return;
    setUpdating(true);
    try {
      await onStatusChange(po.id, action.next);
    } finally {
      setUpdating(false);
    }
  };

  return (
    <>
      <tr className="border-b border-border hover:bg-muted/30 transition-colors">
        <td className="px-4 py-3">
          <button onClick={() => setExpanded((v) => !v)} className="text-muted-foreground hover:text-foreground">
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        </td>
        <td className="px-4 py-3 font-mono font-medium text-xs">{po.po_number}</td>
        <td className="px-4 py-3 text-sm">{supplierName}</td>
        <td className="px-4 py-3">
          <Badge variant={poStatusVariant[status]}>{status}</Badge>
        </td>
        <td className="px-4 py-3 text-right tabular-nums font-medium">{formatCurrency(po.subtotal_amount)}</td>
        <td className="px-4 py-3 text-right tabular-nums text-muted-foreground text-xs">{formatCurrency(po.vat_amount)}</td>
        <td className="px-4 py-3 text-right tabular-nums font-semibold text-xs">{formatCurrency(po.total_amount)}</td>
        <td className="px-4 py-3 text-xs text-muted-foreground">{formatDate(po.po_date)}</td>
        <td className="px-4 py-3">
          {action && (
            <Button
              size="sm"
              variant={action.variant}
              className="h-7 text-xs px-2"
              onClick={handleAction}
              disabled={updating}
            >
              <Send className="w-3 h-3 mr-1" />
              {updating ? "…" : action.label}
            </Button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border bg-muted/20">
          <td colSpan={9} className="px-8 py-3">
            {po.order_items.length > 0 ? (
              <table className="w-full text-xs mb-1">
                <thead>
                  <tr className="text-muted-foreground">
                    <th className="text-left pb-1.5 font-medium">Description</th>
                    <th className="text-right pb-1.5 font-medium">Qty</th>
                    <th className="text-right pb-1.5 font-medium">Unit</th>
                    <th className="text-right pb-1.5 font-medium">Rate</th>
                    <th className="text-right pb-1.5 font-medium">VAT</th>
                    <th className="text-right pb-1.5 font-medium">Excl. VAT</th>
                    <th className="text-right pb-1.5 font-medium">Incl. VAT</th>
                  </tr>
                </thead>
                <tbody>
                  {po.order_items.map((item) => (
                    <tr key={item.id} className="border-t border-border/50">
                      <td className="py-1.5">{item.description}</td>
                      <td className="py-1.5 text-right tabular-nums">{item.quantity_ordered}</td>
                      <td className="py-1.5 text-right text-muted-foreground">{item.unit ?? "—"}</td>
                      <td className="py-1.5 text-right tabular-nums">{item.rate != null ? formatCurrency(item.rate) : "—"}</td>
                      <td className="py-1.5 text-right tabular-nums text-muted-foreground">
                        <span className="text-[10px] mr-0.5">{item.vat_mode === "INCLUSIVE" ? "incl" : "excl"}</span>
                        {item.line_vat_amount != null ? formatCurrency(item.line_vat_amount) : "—"}
                      </td>
                      <td className="py-1.5 text-right tabular-nums">{item.line_excl_vat != null ? formatCurrency(item.line_excl_vat) : "—"}</td>
                      <td className="py-1.5 text-right tabular-nums font-medium">{item.line_total != null ? formatCurrency(item.line_total) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border">
                    <td colSpan={5} className="py-1.5 text-right text-muted-foreground font-medium">Totals</td>
                    <td className="py-1.5 text-right tabular-nums font-semibold">{formatCurrency(po.subtotal_amount)}</td>
                    <td className="py-1.5 text-right tabular-nums font-semibold">{formatCurrency(po.total_amount)}</td>
                  </tr>
                </tfoot>
              </table>
            ) : (
              <p className="text-xs text-muted-foreground mb-2">No line items yet.</p>
            )}
            {/* Only allow adding items on DRAFT POs */}
            {status === "DRAFT" && (
              <AddItemForm poId={po.id} onAdded={onItemAdded} />
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ─── New PO Modal ──────────────────────────────────────────────────────────────
function NewPOModal({
  open,
  onClose,
  suppliers,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  suppliers: Supplier[];
  onSubmit: (supplierId: string, notes: string) => Promise<void>;
}) {
  const [supplierId, setSupplierId] = useState(suppliers[0]?.id ?? "");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (suppliers.length > 0 && !supplierId) setSupplierId(suppliers[0].id);
  }, [suppliers, supplierId]);

  const handleSubmit = async () => {
    if (!supplierId) return;
    setSaving(true);
    try {
      await onSubmit(supplierId, notes.trim());
      setNotes("");
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="New Purchase Order" onClose={onClose} size="sm">
      <div className="p-6 space-y-4">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Supplier *</label>
          <select
            value={supplierId}
            onChange={(e) => setSupplierId(e.target.value)}
            className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Notes</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
          />
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={handleSubmit} disabled={saving || !supplierId}>
            {saving ? "Creating…" : "Create PO"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────────
export default function ProcurementPage() {
  const [tab, setTab] = useState("po");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [materialRequests, setMaterialRequests] = useState<MaterialRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [showNewPO, setShowNewPO] = useState(false);

  useEffect(() => {
    Promise.all([
      projectsApi.list(1, 100),
      suppliersApi.list(),
    ])
      .then(([projRes, suppRes]) => {
        setProjects(projRes.items);
        setSuppliers(suppRes);
        if (projRes.items.length > 0) setSelectedProjectId(projRes.items[0].id);
      })
      .catch(() => {})
      .finally(() => setLoadingProjects(false));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setLoading(true);
    Promise.all([
      purchaseOrdersApi.list(selectedProjectId),
      materialRequestsApi.list(selectedProjectId),
    ])
      .then(([pos, mrs]) => {
        setPurchaseOrders(pos);
        setMaterialRequests(mrs);
      })
      .catch(() => {
        setPurchaseOrders([]);
        setMaterialRequests([]);
      })
      .finally(() => setLoading(false));
  }, [selectedProjectId]);

  const supplierMap = Object.fromEntries(suppliers.map((s) => [s.id, s.name]));

  const draftPOs = purchaseOrders.filter((p) => p.status === "DRAFT").length;
  const pendingApproval = purchaseOrders.filter((p) => p.status === "SUBMITTED").length;
  const approvedPOs = purchaseOrders.filter((p) => ["APPROVED", "SENT"].includes(p.status)).length;
  const totalPOValue = purchaseOrders
    .filter((p) => p.status !== "CANCELLED")
    .reduce((sum, p) => sum + p.total_amount, 0);

  const tabsWithCount = [
    { ...PAGE_TABS[0], count: purchaseOrders.length },
    { ...PAGE_TABS[1], count: materialRequests.length },
  ];

  const handleCreatePO = async (supplierId: string, notes: string) => {
    const created = await purchaseOrdersApi.create(selectedProjectId, {
      supplier_id: supplierId,
      notes: notes || null,
      items: [],
    });
    setPurchaseOrders((prev) => [created, ...prev]);
  };

  const handleStatusChange = async (poId: string, next: RecordStatus) => {
    const updated = await purchaseOrdersApi.update(poId, { status: next });
    setPurchaseOrders((prev) => prev.map((p) => (p.id === poId ? updated : p)));
  };

  // Re-fetch a single PO after items added (to get updated totals)
  const handleItemAdded = async (poId: string) => {
    const updated = await purchaseOrdersApi.get(poId);
    setPurchaseOrders((prev) => prev.map((p) => (p.id === poId ? updated : p)));
  };

  if (loadingProjects) {
    return (
      <div className="space-y-5 animate-fade-in">
        <Skeleton className="h-12 rounded-xl" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Procurement"
        description="Manage material requests and purchase orders."
        actions={
          selectedProjectId ? (
            <Button size="sm" onClick={() => setShowNewPO(true)}>
              <Plus className="w-4 h-4" />
              {tab === "po" ? "New PO" : "New Request"}
            </Button>
          ) : undefined
        }
      />

      {/* Project selector */}
      <div>
        <label className="text-xs text-muted-foreground block mb-1">Project</label>
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[240px]"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total PO Value" value={formatCurrency(totalPOValue)} icon={ShoppingCart} color="bg-primary/10 text-primary" />
        <StatCard title="Approved / Sent" value={approvedPOs} icon={CheckCircle2} color="bg-success/10 text-success" />
        <StatCard title="Pending Approval" value={pendingApproval} icon={FileText} color="bg-warning/10 text-warning" />
        <StatCard title="Drafts" value={draftPOs} icon={ShoppingCart} color="bg-muted-foreground/10 text-muted-foreground" />
      </div>

      <Tabs tabs={tabsWithCount} active={tab} onChange={setTab} />

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
        </div>
      ) : tab === "po" ? (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {purchaseOrders.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">
              No purchase orders for this project.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-4 py-3 w-8" />
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">PO Number</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Supplier</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Subtotal</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">VAT</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Total</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">PO Date</th>
                  <th className="px-4 py-3 font-medium text-muted-foreground">Action</th>
                </tr>
              </thead>
              <tbody>
                {purchaseOrders.map((po) => (
                  <PORow
                    key={po.id}
                    po={po}
                    supplierName={supplierMap[po.supplier_id] ?? po.supplier_id}
                    onStatusChange={handleStatusChange}
                    onItemAdded={handleItemAdded}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {materialRequests.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">
              No material requests for this project.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Request #</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Requested</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Needed By</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Items</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Notes</th>
                </tr>
              </thead>
              <tbody>
                {materialRequests.map((mr) => (
                  <tr key={mr.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-mono font-medium text-xs">{mr.request_number}</td>
                    <td className="px-4 py-3">
                      <Badge variant={mrStatusVariant[mr.status]}>{mr.status}</Badge>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{formatDate(mr.requested_date)}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {mr.needed_by_date ? formatDate(mr.needed_by_date) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{mr.items.length}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground max-w-[200px] truncate" title={mr.notes ?? ""}>
                      {mr.notes ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <NewPOModal
        open={showNewPO}
        onClose={() => setShowNewPO(false)}
        suppliers={suppliers}
        onSubmit={handleCreatePO}
      />
    </div>
  );
}
