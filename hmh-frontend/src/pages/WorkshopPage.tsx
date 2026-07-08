/**
 * WorkshopPage — Office management of vehicle spare parts.
 *
 * Tabs:
 *   Requests — approve / reject workshop MRs from site staff
 *   Parts     — parts catalog (categories + items) with stock adjustment
 *   Suppliers — link suppliers to parts categories
 */

import { useEffect, useState, useCallback } from "react";
import {
  Wrench, ClipboardList, Package, Building2, CheckCircle2, Ban,
  ChevronRight, Plus, RefreshCw, Trash2, X, Pencil, TrendingDown,
  TrendingUp, AlertTriangle, Clock,
} from "lucide-react";
import {
  workshopApi,
  type WorkshopMR,
  type WorkshopMRStatus,
  type WorkshopItem,
  type WorkshopCategory,
  type WorkshopSupplierLink,
  type WorkshopItemCreate,
  type WorkshopItemUpdate,
  type WorkshopCategoryCreate,
} from "@/api/workshop";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ── Shared helpers ────────────────────────────────────────────────────────────

const MR_STATUS_BADGE: Record<string, string> = {
  DRAFT:     "bg-gray-100 text-gray-600 border-gray-200",
  SUBMITTED: "bg-blue-100 text-blue-700 border-blue-200",
  APPROVED:  "bg-green-100 text-green-700 border-green-200",
  REJECTED:  "bg-red-100 text-red-700 border-red-200",
};

const MR_STATUS_LABEL: Record<string, string> = {
  DRAFT:     "Draft",
  SUBMITTED: "Pending",
  APPROVED:  "Approved",
  REJECTED:  "Rejected",
};

const PRIORITY_BADGE: Record<string, string> = {
  LOW:    "bg-gray-100 text-gray-500 border-gray-200",
  NORMAL: "",
  HIGH:   "bg-amber-100 text-amber-700 border-amber-200",
  URGENT: "bg-red-100 text-red-700 border-red-200",
};

function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

// ── Modal shell ───────────────────────────────────────────────────────────────

function Modal({ title, onClose, children, wide = false }: {
  title: string; onClose: () => void; children: React.ReactNode; wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className={cn(
        "bg-card rounded-2xl shadow-xl w-full max-h-[90vh] overflow-y-auto",
        wide ? "max-w-2xl" : "max-w-md"
      )}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-border sticky top-0 bg-card z-10">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5 space-y-4">{children}</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 1 — Workshop MR Requests
// ─────────────────────────────────────────────────────────────────────────────

function RejectModal({ mr, onClose, onRejected }: {
  mr: WorkshopMR; onClose: () => void; onRejected: (mr: WorkshopMR) => void;
}) {
  const [reason,  setReason]  = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const submit = async () => {
    setLoading(true);
    setError("");
    try {
      const updated = await workshopApi.rejectMR(mr.id, reason.trim() || undefined);
      onRejected(updated);
    } catch {
      setError("Failed to reject MR.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={`Reject ${mr.mr_number}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Vehicle: <strong className="text-foreground">{mr.vehicle?.registration ?? mr.vehicle_id}</strong>
          {" · "}{mr.vehicle?.name}
        </p>
        <div className="space-y-1.5">
          <Label>Reason for rejection (optional)</Label>
          <textarea
            rows={3}
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder="Explain why the request is being rejected…"
            className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button variant="destructive" className="flex-1" onClick={submit} disabled={loading}>
            {loading ? "Rejecting…" : "Reject MR"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function MRRequestsTab() {
  const [mrs,       setMrs]       = useState<WorkshopMR[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState("");
  const [filter,    setFilter]    = useState<WorkshopMRStatus | "ALL">("ALL");
  const [expanded,  setExpanded]  = useState<string | null>(null);
  const [approving, setApproving] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<WorkshopMR | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    workshopApi.listMRs()
      .then(data => setMrs(data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())))
      .catch(() => setError("Failed to load workshop requests."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const displayed = filter === "ALL" ? mrs : mrs.filter(m => m.status === filter);

  const handleApprove = async (mr: WorkshopMR) => {
    setApproving(mr.id);
    try {
      const updated = await workshopApi.approveMR(mr.id);
      setMrs(prev => prev.map(m => m.id === updated.id ? updated : m));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail ?? "Failed to approve MR.");
    } finally {
      setApproving(null);
    }
  };

  const pending = mrs.filter(m => m.status === "SUBMITTED").length;

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3">
        {(["ALL", "SUBMITTED", "APPROVED", "REJECTED"] as const).map(s => {
          const count = s === "ALL" ? mrs.length : mrs.filter(m => m.status === s).length;
          return (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={cn(
                "rounded-xl border p-3 text-left transition-colors",
                filter === s ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted/40"
              )}
            >
              <p className="text-xs text-muted-foreground">{s === "ALL" ? "All MRs" : MR_STATUS_LABEL[s]}</p>
              <p className={cn("text-2xl font-bold mt-0.5",
                s === "SUBMITTED" && count > 0 ? "text-amber-600" : ""
              )}>{count}</p>
            </button>
          );
        })}
      </div>

      {pending > 0 && (
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span><strong>{pending}</strong> workshop request{pending !== 1 ? "s" : ""} waiting for your approval.</span>
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{displayed.length} request{displayed.length !== 1 ? "s" : ""}</p>
        <button
          onClick={load}
          disabled={loading}
          className="p-2 rounded-lg hover:bg-muted text-muted-foreground disabled:opacity-50"
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <div className="py-12 text-center text-muted-foreground text-sm">Loading…</div>
      ) : displayed.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground text-sm border border-border rounded-2xl">
          No workshop requests{filter !== "ALL" ? ` with status "${MR_STATUS_LABEL[filter]}"` : ""}.
        </div>
      ) : (
        <div className="bg-card border border-border rounded-2xl overflow-hidden divide-y divide-border">
          {displayed.map(mr => {
            const isOpen = expanded === mr.id;
            return (
              <div key={mr.id}>
                <button
                  className="w-full flex items-center gap-3 px-5 py-4 hover:bg-muted/30 text-left transition-colors"
                  onClick={() => setExpanded(isOpen ? null : mr.id)}
                >
                  {/* Status icon */}
                  <div className="shrink-0">
                    {mr.status === "APPROVED"  ? <CheckCircle2 className="w-5 h-5 text-green-500" /> :
                     mr.status === "SUBMITTED" ? <Clock        className="w-5 h-5 text-amber-500" /> :
                     mr.status === "REJECTED"  ? <Ban          className="w-5 h-5 text-red-500"   /> :
                                                 <Wrench       className="w-5 h-5 text-muted-foreground" />}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm">{mr.mr_number}</span>
                      <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium", MR_STATUS_BADGE[mr.status])}>
                        {MR_STATUS_LABEL[mr.status]}
                      </span>
                      {mr.priority !== "NORMAL" && (
                        <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium", PRIORITY_BADGE[mr.priority])}>
                          {mr.priority}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-0.5 truncate">{mr.reason}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {mr.vehicle?.registration ?? "—"} {mr.vehicle?.name ? `· ${mr.vehicle.name}` : ""}
                      {mr.site?.name ? ` · ${mr.site.name}` : ""}
                      {" · "}{mr.lines.length} part{mr.lines.length !== 1 ? "s" : ""}
                      {" · "}{shortDate(mr.created_at)}
                    </p>
                  </div>

                  <ChevronRight className={cn("w-4 h-4 text-muted-foreground shrink-0 transition-transform", isOpen && "rotate-90")} />
                </button>

                {isOpen && (
                  <div className="px-5 pb-5 pt-3 bg-muted/20 border-t border-border/50 space-y-4">
                    {/* Vehicle + site info */}
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <p className="text-xs text-muted-foreground mb-0.5">Vehicle</p>
                        <p className="font-medium">{mr.vehicle?.registration ?? mr.vehicle_id.slice(0, 8)}</p>
                        {mr.vehicle?.name && <p className="text-xs text-muted-foreground">{mr.vehicle.name}</p>}
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-0.5">Site</p>
                        <p className="font-medium">{mr.site?.name ?? mr.site_id.slice(0, 8)}</p>
                        {mr.site?.site_type && <p className="text-xs text-muted-foreground capitalize">{mr.site.site_type.replace(/_/g, " ")}</p>}
                      </div>
                    </div>

                    {/* Parts table */}
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Parts Requested</p>
                      <div className="border border-border rounded-xl overflow-hidden divide-y divide-border">
                        <div className="grid grid-cols-[1fr_auto] gap-2 px-3 py-2 bg-muted/50 text-xs font-medium text-muted-foreground">
                          <span>Part</span>
                          <span className="text-right">Qty</span>
                        </div>
                        {mr.lines.map((line, i) => (
                          <div key={line.id ?? i} className="grid grid-cols-[1fr_auto] gap-2 px-3 py-2.5 bg-card items-start">
                            <div>
                              <p className="text-sm font-medium">{line.item?.name ?? "Unknown"}</p>
                              {line.item?.part_number && (
                                <p className="text-xs text-muted-foreground">#{line.item.part_number}</p>
                              )}
                              {line.remarks && (
                                <p className="text-xs text-muted-foreground italic">{line.remarks}</p>
                              )}
                            </div>
                            <div className="text-right shrink-0">
                              <p className="text-sm font-semibold tabular-nums">
                                {line.quantity_requested} {line.item?.unit ?? ""}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Notes / dates */}
                    {(mr.notes || mr.needed_by_date) && (
                      <div className="text-sm space-y-1">
                        {mr.needed_by_date && (
                          <p className="text-muted-foreground">
                            Needed by: <span className="font-medium text-foreground">{shortDate(mr.needed_by_date)}</span>
                          </p>
                        )}
                        {mr.notes && <p className="text-muted-foreground italic">{mr.notes}</p>}
                      </div>
                    )}

                    {/* Rejection reason */}
                    {mr.rejection_reason && (
                      <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                        Rejected: {mr.rejection_reason}
                      </p>
                    )}

                    {/* Approval info */}
                    {mr.approved_at && (
                      <p className="text-sm text-green-700 bg-green-50 rounded-lg px-3 py-2">
                        Approved {shortDate(mr.approved_at)}
                      </p>
                    )}

                    {/* Actions */}
                    {mr.status === "SUBMITTED" && (
                      <div className="flex gap-2 pt-1">
                        <Button
                          className="flex-1"
                          disabled={approving === mr.id}
                          onClick={() => handleApprove(mr)}
                        >
                          {approving === mr.id ? "Approving…" : "Approve"}
                        </Button>
                        <Button
                          variant="outline"
                          className="flex-1 border-destructive text-destructive hover:bg-destructive/10"
                          disabled={approving === mr.id}
                          onClick={() => setRejectTarget(mr)}
                        >
                          Reject
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {rejectTarget && (
        <RejectModal
          mr={rejectTarget}
          onClose={() => setRejectTarget(null)}
          onRejected={updated => {
            setMrs(prev => prev.map(m => m.id === updated.id ? updated : m));
            setRejectTarget(null);
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 2 — Parts Catalog
// ─────────────────────────────────────────────────────────────────────────────

function StockAdjustModal({ item, onClose, onAdjusted }: {
  item: WorkshopItem; onClose: () => void; onAdjusted: (newQty: number) => void;
}) {
  const [delta,   setDelta]   = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const submit = async () => {
    const d = parseFloat(delta);
    if (isNaN(d) || d === 0) { setError("Enter a non-zero quantity."); return; }
    setLoading(true);
    setError("");
    try {
      const result = await workshopApi.adjustStock(item.id, d);
      onAdjusted(result.quantity_on_hand);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Adjustment failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={`Adjust Stock — ${item.name}`} onClose={onClose}>
      <div className="space-y-3">
        <div className="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3">
          <p className="text-xs text-muted-foreground">Current stock</p>
          <p className="text-2xl font-bold">{item.quantity_on_hand} <span className="text-sm font-normal text-muted-foreground">{item.unit}</span></p>
          {item.reorder_level != null && item.quantity_on_hand <= item.reorder_level && (
            <p className="text-xs text-amber-600 mt-0.5 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> Below reorder level ({item.reorder_level})
            </p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label>Quantity to add or remove</Label>
          <p className="text-xs text-muted-foreground">Enter a positive number to add stock, negative to remove.</p>
          <div className="flex gap-2">
            <button type="button" onClick={() => setDelta(d => String(Math.abs(parseFloat(d) || 0)))}
              className="px-3 py-2 rounded-lg border border-border bg-green-50 text-green-700 text-sm font-medium hover:bg-green-100">
              <TrendingUp className="w-4 h-4" />
            </button>
            <Input
              type="number"
              step="any"
              placeholder="e.g. 10 or -3"
              value={delta}
              onChange={e => setDelta(e.target.value)}
              className="flex-1"
              autoFocus
            />
            <button type="button" onClick={() => setDelta(d => String(-Math.abs(parseFloat(d) || 0)))}
              className="px-3 py-2 rounded-lg border border-border bg-red-50 text-red-700 text-sm font-medium hover:bg-red-100">
              <TrendingDown className="w-4 h-4" />
            </button>
          </div>
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>
            {loading ? "Saving…" : "Apply Adjustment"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function AddItemModal({
  categories,
  editItem,
  onClose,
  onSaved,
}: {
  categories: WorkshopCategory[];
  editItem: WorkshopItem | null;
  onClose: () => void;
  onSaved: (item: WorkshopItem) => void;
}) {
  const [form, setForm] = useState<WorkshopItemCreate>({
    category_id: editItem?.category_id ?? (categories[0]?.id ?? ""),
    name: editItem?.name ?? "",
    part_number: editItem?.part_number ?? "",
    unit: editItem?.unit ?? "each",
    description: editItem?.description ?? "",
    reorder_level: editItem?.reorder_level ?? null,
  });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const patch = (p: Partial<WorkshopItemCreate>) => setForm(prev => ({ ...prev, ...p }));

  const submit = async () => {
    if (!form.name.trim()) { setError("Name is required."); return; }
    if (!form.category_id) { setError("Select a category."); return; }
    setLoading(true);
    setError("");
    try {
      let saved: WorkshopItem;
      if (editItem) {
        const body: WorkshopItemUpdate = {
          name:         form.name.trim(),
          part_number:  form.part_number || null,
          unit:         form.unit,
          description:  form.description || null,
          reorder_level: form.reorder_level,
        };
        saved = await workshopApi.updateItem(editItem.id, body);
      } else {
        saved = await workshopApi.createItem({ ...form, name: form.name.trim() });
      }
      onSaved(saved);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to save item.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={editItem ? `Edit — ${editItem.name}` : "Add Part"} onClose={onClose}>
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label>Category *</Label>
          <select
            value={form.category_id}
            onChange={e => patch({ category_id: e.target.value })}
            disabled={!!editItem}
            className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-60"
          >
            <option value="">— Select —</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>Part name *</Label>
          <Input value={form.name} onChange={e => patch({ name: e.target.value })} placeholder="e.g. 235/65 R17 Tyre" autoFocus />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Part number</Label>
            <Input value={form.part_number ?? ""} onChange={e => patch({ part_number: e.target.value })} placeholder="OEM / supplier ref" />
          </div>
          <div className="space-y-1.5">
            <Label>Unit</Label>
            <Input value={form.unit} onChange={e => patch({ unit: e.target.value })} placeholder="each, litre, kg…" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label>Reorder level</Label>
          <Input
            type="number" min="0" step="any"
            value={form.reorder_level ?? ""}
            onChange={e => patch({ reorder_level: e.target.value ? parseFloat(e.target.value) : null })}
            placeholder="Alert when stock falls below…"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Description (optional)</Label>
          <textarea
            rows={2}
            value={form.description ?? ""}
            onChange={e => patch({ description: e.target.value })}
            placeholder="Specifications, notes…"
            className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>
            {loading ? "Saving…" : editItem ? "Save Changes" : "Add Part"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function AddCategoryModal({ onClose, onSaved }: {
  onClose: () => void; onSaved: (cat: WorkshopCategory) => void;
}) {
  const [form, setForm] = useState<WorkshopCategoryCreate>({ name: "", description: "" });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const submit = async () => {
    if (!form.name.trim()) { setError("Name is required."); return; }
    setLoading(true);
    setError("");
    try {
      const cat = await workshopApi.createCategory({ name: form.name.trim(), description: form.description || null });
      onSaved(cat);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to create category.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="New Category" onClose={onClose}>
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label>Category name *</Label>
          <Input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Tyres, Engine Oil, Filters" autoFocus />
        </div>
        <div className="space-y-1.5">
          <Label>Description</Label>
          <Input value={form.description ?? ""} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} placeholder="Optional" />
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>{loading ? "Saving…" : "Add Category"}</Button>
        </div>
      </div>
    </Modal>
  );
}

function PartsTab() {
  const [items,      setItems]      = useState<WorkshopItem[]>([]);
  const [categories, setCategories] = useState<WorkshopCategory[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [catFilter,  setCatFilter]  = useState("");
  const [activeOnly, setActiveOnly] = useState(true);

  const [adjustTarget, setAdjustTarget] = useState<WorkshopItem | null>(null);
  const [editTarget,   setEditTarget]   = useState<WorkshopItem | null>(null);
  const [showAddItem,  setShowAddItem]  = useState(false);
  const [showAddCat,   setShowAddCat]   = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      workshopApi.listItems(catFilter || undefined),
      workshopApi.listCategories(),
    ]).then(([items, cats]) => {
      setItems(items);
      setCategories(cats);
    }).finally(() => setLoading(false));
  }, [catFilter]);

  useEffect(() => { load(); }, [load]);

  const displayed = activeOnly ? items.filter(i => i.is_active) : items;

  const totalValue = displayed.reduce((s, i) => s + i.quantity_on_hand, 0);
  const lowStock   = displayed.filter(i => i.reorder_level != null && i.quantity_on_hand <= i.reorder_level);

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-card border border-border rounded-xl p-3">
          <p className="text-xs text-muted-foreground">Total Parts</p>
          <p className="text-2xl font-bold mt-0.5">{displayed.length}</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-3">
          <p className="text-xs text-muted-foreground">Categories</p>
          <p className="text-2xl font-bold mt-0.5">{categories.length}</p>
        </div>
        <div className={cn("border rounded-xl p-3", lowStock.length > 0 ? "bg-amber-50 border-amber-200" : "bg-card border-border")}>
          <p className="text-xs text-muted-foreground">Low Stock</p>
          <p className={cn("text-2xl font-bold mt-0.5", lowStock.length > 0 ? "text-amber-600" : "")}>{lowStock.length}</p>
        </div>
      </div>

      {/* Filters + actions */}
      <div className="flex flex-wrap gap-2 items-center justify-between">
        <div className="flex gap-2">
          <select
            value={catFilter}
            onChange={e => setCatFilter(e.target.value)}
            className="h-9 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none"
          >
            <option value="">All categories</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={e => setActiveOnly(e.target.checked)}
              className="rounded"
            />
            Active only
          </label>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowAddCat(true)}>
            <Plus className="w-3.5 h-3.5 mr-1" />Category
          </Button>
          <Button size="sm" onClick={() => setShowAddItem(true)}>
            <Plus className="w-3.5 h-3.5 mr-1" />Add Part
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="py-12 text-center text-muted-foreground text-sm">Loading…</div>
      ) : displayed.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground text-sm border border-border rounded-2xl">
          No parts in catalog. Add a category first, then add parts.
        </div>
      ) : (
        <div className="bg-card border border-border rounded-2xl overflow-hidden">
          <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-2 px-5 py-3 bg-muted/50 text-xs font-medium text-muted-foreground border-b border-border">
            <span>Part</span>
            <span className="text-right">Stock</span>
            <span className="text-right">Reorder</span>
            <span />
            <span />
          </div>
          <div className="divide-y divide-border">
            {displayed.map(item => {
              const isLow = item.reorder_level != null && item.quantity_on_hand <= item.reorder_level;
              const catName = item.category_name ?? categories.find(c => c.id === item.category_id)?.name;
              return (
                <div key={item.id} className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-2 px-5 py-3 items-center">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium truncate">{item.name}</p>
                      {!item.is_active && <Badge variant="outline" className="text-xs shrink-0">Inactive</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {catName && <span>{catName} · </span>}
                      {item.part_number && <span>#{item.part_number} · </span>}
                      {item.unit}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className={cn("text-sm font-semibold tabular-nums", isLow ? "text-amber-600" : item.quantity_on_hand === 0 ? "text-destructive" : "text-green-600")}>
                      {item.quantity_on_hand}
                    </p>
                    {isLow && <AlertTriangle className="w-3 h-3 text-amber-500 ml-auto" />}
                  </div>
                  <p className="text-xs text-muted-foreground text-right">
                    {item.reorder_level ?? "—"}
                  </p>
                  <button
                    onClick={() => setAdjustTarget(item)}
                    className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    title="Adjust stock"
                  >
                    <Package className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setEditTarget(item)}
                    className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    title="Edit item"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {adjustTarget && (
        <StockAdjustModal
          item={adjustTarget}
          onClose={() => setAdjustTarget(null)}
          onAdjusted={newQty => {
            setItems(prev => prev.map(i => i.id === adjustTarget.id ? { ...i, quantity_on_hand: newQty } : i));
            setAdjustTarget(null);
          }}
        />
      )}

      {(showAddItem || editTarget) && (
        <AddItemModal
          categories={categories}
          editItem={editTarget}
          onClose={() => { setShowAddItem(false); setEditTarget(null); }}
          onSaved={saved => {
            setItems(prev => {
              const idx = prev.findIndex(i => i.id === saved.id);
              if (idx >= 0) { const n = [...prev]; n[idx] = saved; return n; }
              return [saved, ...prev];
            });
            setShowAddItem(false);
            setEditTarget(null);
          }}
        />
      )}

      {showAddCat && (
        <AddCategoryModal
          onClose={() => setShowAddCat(false)}
          onSaved={cat => { setCategories(prev => [...prev, cat]); setShowAddCat(false); }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 3 — Supplier Links
// ─────────────────────────────────────────────────────────────────────────────

function AddSupplierLinkModal({ categories, suppliers, onClose, onSaved }: {
  categories: WorkshopCategory[];
  suppliers: Supplier[];
  onClose: () => void;
  onSaved: (link: WorkshopSupplierLink) => void;
}) {
  const [catId,     setCatId]     = useState(categories[0]?.id ?? "");
  const [suppId,    setSuppId]    = useState("");
  const [preferred, setPreferred] = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState("");

  const submit = async () => {
    if (!catId || !suppId) { setError("Select both category and supplier."); return; }
    setLoading(true);
    setError("");
    try {
      const link = await workshopApi.createSupplierLink({ category_id: catId, supplier_id: suppId, is_preferred: preferred });
      onSaved(link);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to create link.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="Link Supplier to Category" onClose={onClose}>
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label>Parts category *</Label>
          <select value={catId} onChange={e => setCatId(e.target.value)}
            className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary">
            <option value="">— Select —</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>Supplier *</Label>
          <select value={suppId} onChange={e => setSuppId(e.target.value)}
            className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary">
            <option value="">— Select —</option>
            {suppliers.filter(s => s.is_active).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={preferred} onChange={e => setPreferred(e.target.checked)} className="rounded" />
          Mark as preferred supplier for this category
        </label>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>{loading ? "Saving…" : "Link Supplier"}</Button>
        </div>
      </div>
    </Modal>
  );
}

function SuppliersTab() {
  const [links,      setLinks]      = useState<WorkshopSupplierLink[]>([]);
  const [categories, setCategories] = useState<WorkshopCategory[]>([]);
  const [suppliers,  setSuppliers]  = useState<Supplier[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [showAdd,    setShowAdd]    = useState(false);
  const [deleting,   setDeleting]   = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      workshopApi.listSupplierLinks(),
      workshopApi.listCategories(),
      suppliersApi.list(),
    ]).then(([l, c, s]) => {
      setLinks(l);
      setCategories(c);
      setSuppliers(s);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (linkId: string) => {
    setDeleting(linkId);
    try {
      await workshopApi.deleteSupplierLink(linkId);
      setLinks(prev => prev.filter(l => l.id !== linkId));
    } catch {
      alert("Failed to remove supplier link.");
    } finally {
      setDeleting(null);
    }
  };

  // Group by category
  const grouped = categories.map(cat => ({
    cat,
    links: links.filter(l => l.category_id === cat.id),
  })).filter(g => g.links.length > 0);

  const orphans = links.filter(l => !categories.some(c => c.id === l.category_id));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{links.length} supplier link{links.length !== 1 ? "s" : ""} across {grouped.length} categor{grouped.length !== 1 ? "ies" : "y"}</p>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="w-3.5 h-3.5 mr-1" /> Link Supplier
        </Button>
      </div>

      {loading ? (
        <div className="py-12 text-center text-muted-foreground text-sm">Loading…</div>
      ) : links.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground text-sm border border-border rounded-2xl">
          No supplier links yet. Link suppliers to parts categories so site staff can select them on MRs.
        </div>
      ) : (
        <div className="space-y-3">
          {grouped.map(({ cat, links: catLinks }) => (
            <div key={cat.id} className="bg-card border border-border rounded-2xl overflow-hidden">
              <div className="px-4 py-3 bg-muted/40 border-b border-border">
                <p className="font-semibold text-sm">{cat.name}</p>
                {cat.description && <p className="text-xs text-muted-foreground mt-0.5">{cat.description}</p>}
              </div>
              <div className="divide-y divide-border">
                {catLinks.map(link => {
                  const suppName = link.supplier?.name ?? suppliers.find(s => s.id === link.supplier_id)?.name ?? link.supplier_id.slice(0, 8);
                  const suppEmail = link.supplier?.email ?? suppliers.find(s => s.id === link.supplier_id)?.email;
                  return (
                    <div key={link.id} className="flex items-center gap-3 px-4 py-3">
                      <Building2 className="w-4 h-4 text-muted-foreground shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">{suppName}</p>
                        {suppEmail && <p className="text-xs text-muted-foreground">{suppEmail}</p>}
                      </div>
                      {link.is_preferred && (
                        <Badge variant="outline" className="text-xs border-green-200 text-green-700 bg-green-50">Preferred</Badge>
                      )}
                      <button
                        onClick={() => handleDelete(link.id)}
                        disabled={deleting === link.id}
                        className="p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
                        title="Remove link"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {orphans.length > 0 && (
            <div className="bg-card border border-dashed border-border rounded-2xl p-4">
              <p className="text-xs text-muted-foreground mb-2">Links with no matching category (stale):</p>
              {orphans.map(l => (
                <div key={l.id} className="flex items-center justify-between py-1">
                  <p className="text-sm">{l.supplier?.name ?? l.supplier_id.slice(0, 8)}</p>
                  <button onClick={() => handleDelete(l.id)} disabled={deleting === l.id}
                    className="p-1.5 text-muted-foreground hover:text-destructive">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {showAdd && (
        <AddSupplierLinkModal
          categories={categories}
          suppliers={suppliers}
          onClose={() => setShowAdd(false)}
          onSaved={link => { setLinks(prev => [...prev, link]); setShowAdd(false); }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

type Tab = "requests" | "parts" | "suppliers";

const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: "requests",  label: "Requests",  icon: ClipboardList },
  { key: "parts",     label: "Parts",     icon: Package      },
  { key: "suppliers", label: "Suppliers", icon: Building2    },
];

export default function WorkshopPage() {
  const [tab, setTab] = useState<Tab>("requests");

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
          <Wrench className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Workshop</h1>
          <p className="text-sm text-muted-foreground">Vehicle spare parts management</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px",
              tab === t.key
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "requests"  && <MRRequestsTab />}
      {tab === "parts"     && <PartsTab />}
      {tab === "suppliers" && <SuppliersTab />}
    </div>
  );
}
