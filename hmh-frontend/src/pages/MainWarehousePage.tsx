/**
 * Main Warehouse — global stock received directly (no project).
 *
 * Only shows stock where project_id IS NULL (received into the central
 * main warehouse, not into a specific project).
 * Stock flow:
 *   Supplier Delivery → Main Warehouse (global) → Site Warehouse → Lot/Unit
 *
 * Actions (admin/office only):
 *   • View on-hand stock per item
 *   • Transfer stock to any site across any project
 *   • Delete (write-off) stock entries
 *   • Browse global movement history
 */

import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight, RefreshCw, History,
  AlertTriangle, X, ChevronDown, ChevronUp, Warehouse,
  PackagePlus, SlidersHorizontal, Wrench, Plus, Edit2, Trash2, MapPin,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import {
  warehouseApi,
  type GlobalWarehouseStockItem,
  type GlobalWarehouseMovement,
  type GlobalWarehouseSite,
  type ToolSiteLocation,
} from "@/api/warehouse";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";
import client from "@/api/client";

interface CatalogItem { id: string; name: string; default_unit: string | null; }

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n % 1 === 0 ? String(n) : n.toFixed(2);
}

const MOVEMENT_LABEL: Record<string, string> = {
  DELIVERY_RECEIVED:   "Delivery received",
  TRANSFER_OUT:        "Transferred to site",
  TRANSFER_IN:         "Received (return)",
  OPENING_BALANCE:     "Opening balance",
  ADJUSTMENT_ADD:      "Adjustment +",
  ADJUSTMENT_SUBTRACT: "Adjustment −",
  RETURN_TO_STORE:     "Return to store",
};

const MOVEMENT_COLOR: Record<string, string> = {
  TRANSFER_IN:         "text-green-600",
  DELIVERY_RECEIVED:   "text-green-600",
  OPENING_BALANCE:     "text-green-600",
  ADJUSTMENT_ADD:      "text-green-600",
  TRANSFER_OUT:        "text-amber-600",
  ADJUSTMENT_SUBTRACT: "text-destructive",
};

// ── Receive Stock Modal ───────────────────────────────────────────────────────

function ReceiveStockModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [items,       setItems]       = useState<CatalogItem[]>([]);
  const [itemId,      setItemId]      = useState("");
  const [quantity,    setQuantity]    = useState("");
  const [unitCost,    setUnitCost]    = useState("");
  const [supplierRef, setSupplierRef] = useState("");
  const [date,        setDate]        = useState(today);
  const [notes,       setNotes]       = useState("");
  const [saving,      setSaving]      = useState(false);
  const [error,       setError]       = useState("");

  useEffect(() => {
    client.get<{ data: CatalogItem[] }>("/items/").then(r => {
      setItems(r.data.data ?? []);
      if (r.data.data?.[0]) setItemId(r.data.data[0].id);
    }).catch(() => {});
  }, []);

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!itemId || !qty || qty <= 0) { setError("Material and quantity are required."); return; }
    setSaving(true); setError("");
    try {
      await warehouseApi.receiveStock({
        item_id:      itemId,
        quantity:     qty,
        unit_cost:    unitCost ? parseFloat(unitCost) : undefined,
        supplier_ref: supplierRef || undefined,
        movement_date: date || undefined,
        notes:        notes || undefined,
      });
      onDone();
      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to receive stock.");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Receive Stock</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        {/* Destination banner */}
        <div className="bg-primary/5 border border-primary/20 rounded-xl px-3 py-2 text-xs text-muted-foreground">
          Destination: <span className="font-medium text-foreground">Global Main Warehouse</span> — stock is company-wide until transferred to a site.
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Material *</label>
            <select value={itemId} onChange={e => setItemId(e.target.value)} className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm">
              <option value="">Select material…</option>
              {items.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Quantity *</label>
              <input type="number" min="0.001" step="any" value={quantity} onChange={e => setQuantity(e.target.value)} placeholder="0" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" autoFocus />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Unit Cost (R)</label>
              <input type="number" min="0" step="0.01" value={unitCost} onChange={e => setUnitCost(e.target.value)} placeholder="0.00" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Supplier / Invoice Ref</label>
            <input type="text" value={supplierRef} onChange={e => setSupplierRef(e.target.value)} placeholder="e.g. ABC Suppliers — INV-001" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Delivery Date</label>
              <input type="date" value={date} onChange={e => setDate(e.target.value)} className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Notes</label>
              <input type="text" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Optional" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
            </div>
          </div>
        </div>
        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex gap-2">
          <Button onClick={submit} disabled={saving} className="flex-1">{saving ? "Receiving…" : "Receive Stock"}</Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Adjust Stock Modal ────────────────────────────────────────────────────────

const ADJUSTMENT_OPTIONS: { value: string; label: string }[] = [
  { value: "DAMAGED",        label: "Damaged (remove)" },
  { value: "LOST",           label: "Lost (remove)" },
  { value: "RETURNED",       label: "Returned to stock (add)" },
  { value: "CORRECTION_ADD", label: "Correction + (add)" },
  { value: "CORRECTION_SUB", label: "Correction − (remove)" },
  { value: "OTHER_ADD",      label: "Other + (add)" },
  { value: "OTHER_SUB",      label: "Other − (remove)" },
];

function AdjustStockModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [items,    setItems]    = useState<CatalogItem[]>([]);
  const [itemId,   setItemId]   = useState("");
  const [adjType,  setAdjType]  = useState("DAMAGED");
  const [quantity, setQuantity] = useState("");
  const [date,     setDate]     = useState(today);
  const [notes,    setNotes]    = useState("");
  const [saving,   setSaving]   = useState(false);
  const [error,    setError]    = useState("");

  useEffect(() => {
    client.get<{ data: CatalogItem[] }>("/items/").then(r => {
      setItems(r.data.data ?? []);
      if (r.data.data?.[0]) setItemId(r.data.data[0].id);
    }).catch(() => {});
  }, []);

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!itemId || !qty || qty <= 0) { setError("Material and quantity are required."); return; }
    setSaving(true); setError("");
    try {
      await warehouseApi.adjustStock({
        item_id: itemId,
        adjustment_type: adjType,
        quantity: qty,
        movement_date: date || undefined,
        notes: notes || undefined,
      });
      onDone();
      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to adjust stock.");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Stock Adjustment</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        {/* Scope banner */}
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-xs text-amber-800">
          Adjusting <span className="font-medium">Global Main Warehouse</span> stock (project_id = null).
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Material *</label>
            <select value={itemId} onChange={e => setItemId(e.target.value)} className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm">
              <option value="">Select material…</option>
              {items.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Adjustment Type *</label>
            <select value={adjType} onChange={e => setAdjType(e.target.value)} className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm">
              {ADJUSTMENT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Quantity *</label>
              <input type="number" min="0.001" step="any" value={quantity} onChange={e => setQuantity(e.target.value)} placeholder="0" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" autoFocus />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Date</label>
              <input type="date" value={date} onChange={e => setDate(e.target.value)} className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Reason / Notes</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Explain the adjustment" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
        </div>
        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex gap-2">
          <Button onClick={submit} disabled={saving} className="flex-1">{saving ? "Saving…" : "Save Adjustment"}</Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Transfer-to-Site Modal ────────────────────────────────────────────────────
// Handles both project-scoped stock and global stock (project_id = null).
// For global stock, loads all sites company-wide and uses the global transfer endpoint.

function TransferModal({
  item,
  onClose,
  onDone,
}: {
  item:    GlobalWarehouseStockItem;
  onClose: () => void;
  onDone:  () => void;
}) {
  const isGlobal = item.project_id === null;
  const isTool   = item.item_type === "TOOL";

  // For global stock: list of all sites across all projects
  const [allSites,     setAllSites]     = useState<GlobalWarehouseSite[]>([]);
  // For project-scoped stock: sites within the item's project
  const [projectSites, setProjectSites] = useState<{ id: string; name: string }[]>([]);

  const [siteId,       setSiteId]       = useState("");
  const [quantity,     setQuantity]     = useState("");
  const [notes,        setNotes]        = useState("");
  const [loading,      setLoading]      = useState(false);
  const [sitesLoading, setSitesLoading] = useState(true);
  const [error,        setError]        = useState("");

  useEffect(() => {
    setSitesLoading(true);
    if (isGlobal) {
      warehouseApi.listAllSites()
        .then(s => {
          setAllSites(s);
          // Tools go to project warehouses only; materials can go anywhere
          const eligible = isTool ? s.filter(x => x.site_type === "warehouse") : s;
          if (eligible.length > 0) setSiteId(eligible[0].id);
        })
        .catch(() => setAllSites([]))
        .finally(() => setSitesLoading(false));
    } else {
      import("@/api/sites").then(({ sitesApi }) =>
        sitesApi.list(item.project_id!)
          .then(s => {
            setProjectSites(s);
            if (s.length > 0) setSiteId(s[0].id);
          })
          .catch(() => setProjectSites([]))
          .finally(() => setSitesLoading(false))
      );
    }
  }, [isGlobal, isTool, item.project_id]);

  // For tool transfers, restrict to project warehouse sites only
  const visibleSites = isGlobal
    ? (isTool ? allSites.filter(s => s.site_type === "warehouse") : allSites)
    : projectSites;
  const selectedSite = visibleSites.find(s => s.id === siteId);

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!siteId)          { setError("Select a site."); return; }
    if (!qty || qty <= 0) { setError("Enter a valid quantity."); return; }
    if (qty > item.on_hand) {
      setError(`Only ${fmt(item.on_hand)} ${item.unit ?? ""} available.`);
      return;
    }
    setLoading(true); setError("");
    try {
      if (isGlobal) {
        await warehouseApi.transferGlobalToSite(item.item_id, siteId, qty, notes || undefined);
      } else {
        await warehouseApi.transferToSite(item.project_id!, item.item_id, siteId, qty, notes || undefined);
      }
      onDone();
      onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Transfer failed.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">
            {isTool ? "Send Tool to Project Warehouse" : "Transfer to Site"}
          </h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        {/* Item context */}
        <div className="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 space-y-0.5">
          <p className="font-medium text-sm">{item.item_name}</p>
          <p className="text-xs text-muted-foreground">
            Available: <strong>{fmt(item.on_hand)} {item.unit ?? ""}</strong>
            {" · "}
            {isGlobal
              ? <span className="text-primary font-medium">Global Stock</span>
              : <>{item.project_code} {item.project_name}</>
            }
          </p>
        </div>

        {isTool && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-xs text-amber-800">
            Tools can only be sent to a <span className="font-medium">Project Warehouse</span>. They can be returned to the Main Warehouse from there.
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              {isTool
                ? "Destination Project Warehouse"
                : isGlobal ? "Destination site (any project)" : "Destination site"
              }
            </label>
            {sitesLoading ? (
              <div className="h-10 rounded-md border border-input bg-muted animate-pulse" />
            ) : visibleSites.length === 0 ? (
              <p className="text-xs text-muted-foreground bg-muted/40 rounded-md px-3 py-2.5">
                {isTool ? "No project warehouses found." : isGlobal ? "No active sites found." : `No sites in ${item.project_name}.`}
              </p>
            ) : (
              <select
                value={siteId}
                onChange={e => setSiteId(e.target.value)}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
              >
                {isGlobal
                  ? visibleSites.map(s => (
                      <option key={s.id} value={s.id}>
                        {s.project_code} — {s.name}
                      </option>
                    ))
                  : projectSites.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))
                }
              </select>
            )}
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Quantity ({item.unit ?? "units"})
            </label>
            <input
              type="number" min="0.001" step="any" max={item.on_hand}
              value={quantity}
              onChange={e => setQuantity(e.target.value)}
              placeholder={`Max ${fmt(item.on_hand)}`}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
              autoFocus
            />
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Notes (optional)</label>
            <input
              type="text" value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="e.g. For foundation pour"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
        </div>

        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

        {quantity && parseFloat(quantity) > 0 && selectedSite && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
            <span className="font-medium text-foreground">{fmt(parseFloat(quantity))} {item.unit ?? ""}</span>
            <ArrowRight className="w-3 h-3" />
            <span className="font-medium text-foreground">{selectedSite.name}</span>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <Button
            onClick={submit}
            disabled={loading || sitesLoading || visibleSites.length === 0}
            className="flex-1"
          >
            {loading ? "Transferring…" : isTool ? "Send to Project Warehouse" : "Transfer to Site"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Add Tool Modal ────────────────────────────────────────────────────────────

function AddToolModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name,     setName]     = useState("");
  const [quantity, setQuantity] = useState("");
  const [unit,     setUnit]     = useState("");
  const [notes,    setNotes]    = useState("");
  const [saving,   setSaving]   = useState(false);
  const [error,    setError]    = useState("");

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!name.trim())     { setError("Enter a tool name."); return; }
    if (!qty || qty <= 0) { setError("Enter a valid quantity."); return; }
    setSaving(true); setError("");
    try {
      await warehouseApi.addTool({
        name:     name.trim(),
        quantity: qty,
        unit:     unit.trim() || undefined,
        notes:    notes.trim() || undefined,
      });
      onDone();
      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to add tool.");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Add Tools to Main Warehouse</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="bg-primary/5 border border-primary/20 rounded-xl px-3 py-2 text-xs text-muted-foreground">
          Tools are re-usable and can be sent to sites and returned. If a tool with this name already exists its stock will be topped up.
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Tool name *</label>
            <input
              type="text" value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. Shovel, Drill, Spirit Level" autoFocus
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Quantity *</label>
              <input
                type="number" min="1" step="1" value={quantity}
                onChange={e => setQuantity(e.target.value)} placeholder="e.g. 100"
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Unit (optional)</label>
              <input
                type="text" value={unit} onChange={e => setUnit(e.target.value)}
                placeholder="e.g. pcs"
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Notes (optional)</label>
            <input
              type="text" value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="e.g. New purchase from supplier"
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
        </div>

        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

        <div className="flex gap-2">
          <Button onClick={submit} disabled={saving} className="flex-1">
            {saving ? "Adding…" : "Add to Warehouse"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Edit Tool Modal ───────────────────────────────────────────────────────────

function EditToolModal({
  tool,
  onClose,
  onDone,
}: {
  tool: GlobalWarehouseStockItem;
  onClose: () => void;
  onDone:  () => void;
}) {
  const [name,    setName]    = useState(tool.item_name);
  const [unit,    setUnit]    = useState(tool.unit ?? "");
  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState("");

  const submit = async () => {
    if (!name.trim()) { setError("Tool name cannot be blank."); return; }
    setSaving(true); setError("");
    try {
      await client.patch(`/items/${tool.item_id}`, {
        name: name.trim(),
        default_unit: unit.trim() || null,
      });
      onDone();
      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to update tool.");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Edit Tool</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Tool name *</label>
            <input
              type="text" value={name} onChange={e => setName(e.target.value)} autoFocus
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Unit (optional)</label>
            <input
              type="text" value={unit} onChange={e => setUnit(e.target.value)}
              placeholder="e.g. pcs"
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
        </div>
        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex gap-2">
          <Button onClick={submit} disabled={saving} className="flex-1">{saving ? "Saving…" : "Save Changes"}</Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── History row ───────────────────────────────────────────────────────────────

function HistoryRow({ m }: { m: GlobalWarehouseMovement }) {
  const isIn  = m.quantity_in > 0;
  const qty   = isIn ? m.quantity_in : m.quantity_out;
  const label = MOVEMENT_LABEL[m.movement_type] ?? m.movement_type.replace(/_/g, " ");
  const color = MOVEMENT_COLOR[m.movement_type] ?? "text-muted-foreground";

  return (
    <div className="flex items-start justify-between py-2.5 border-b border-border/40 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate">{m.item_name}</p>
        <p className="text-xs text-muted-foreground">
          {label}
          {" · "}<span className="text-foreground/70">{m.project_name}</span>
          {m.entered_by ? ` · ${m.entered_by}` : ""}
          {m.notes ? ` — ${m.notes}` : ""}
        </p>
      </div>
      <div className="text-right shrink-0 ml-3">
        <span className={cn("text-sm font-semibold", color)}>
          {isIn ? "+" : "−"}{fmt(qty)} {m.unit ?? ""}
        </span>
        <p className="text-xs text-muted-foreground">
          {m.movement_date ? formatDate(m.movement_date) : "—"}
        </p>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MainWarehousePage() {
  const [stock,         setStock]         = useState<GlobalWarehouseStockItem[]>([]);
  const [tools,         setTools]         = useState<GlobalWarehouseStockItem[]>([]);
  const [toolLocations, setToolLocations] = useState<ToolSiteLocation[]>([]);
  const [history,       setHistory]       = useState<GlobalWarehouseMovement[]>([]);
  const [loading,       setLoading]       = useState(false);
  const [histLoading,   setHistLoading]   = useState(false);
  const [locsLoading,   setLocsLoading]   = useState(false);
  const [showHistory,   setShowHistory]   = useState(false);
  const [showTools,     setShowTools]     = useState(false);
  const [error,         setError]         = useState("");

  const [transferItem,     setTransferItem]     = useState<GlobalWarehouseStockItem | null>(null);
  const [editTool,         setEditTool]         = useState<GlobalWarehouseStockItem | null>(null);
  const [deletingTool,     setDeletingTool]     = useState<GlobalWarehouseStockItem | null>(null);
  const [deleteError,      setDeleteError]      = useState("");
  const [showReceive,      setShowReceive]      = useState(false);
  const [showAdjust,       setShowAdjust]       = useState(false);
  const [showAddTool,      setShowAddTool]      = useState(false);
  const [deleteStockItem,  setDeleteStockItem]  = useState<GlobalWarehouseStockItem | null>(null);
  const [deleteStockNotes, setDeleteStockNotes] = useState("");
  const [deleteStockBusy,  setDeleteStockBusy]  = useState(false);

  const loadStock = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [s, t] = await Promise.all([
        warehouseApi.getGlobalStock(),
        warehouseApi.getGlobalTools(),
      ]);
      setStock(s);
      setTools(t);
    } catch {
      setError("Failed to load main warehouse stock.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadStock(); }, [loadStock]);

  const loadHistory = useCallback(async () => {
    setHistLoading(true);
    try {
      setHistory(await warehouseApi.getGlobalHistory(100));
    } catch { /* silent */ }
    finally { setHistLoading(false); }
  }, []);

  const toggleHistory = () => {
    if (!showHistory) {
      setShowHistory(true);
      if (history.length === 0) loadHistory();
    } else {
      setShowHistory(false);
    }
  };

  const loadToolLocations = useCallback(async () => {
    setLocsLoading(true);
    try {
      setToolLocations(await warehouseApi.getToolLocations());
    } catch { /* silent */ }
    finally { setLocsLoading(false); }
  }, []);

  const toggleTools = () => {
    setShowTools(p => {
      if (!p && toolLocations.length === 0) loadToolLocations();
      return !p;
    });
  };

  const handleDeleteTool = async (tool: GlobalWarehouseStockItem) => {
    setDeleteError("");
    const atSites = toolLocations.filter(l => l.item_id === tool.item_id);
    const totalAtSites = atSites.reduce((s, l) => s + l.on_hand, 0);
    if (totalAtSites > 0) {
      setDeleteError(
        `Cannot delete — ${fmt(totalAtSites)} ${tool.unit ?? "unit(s)"} of "${tool.item_name}" are still at sites. Return them to the main warehouse first.`
      );
      return;
    }
    if (!window.confirm(`Remove all "${tool.item_name}" from the warehouse? This cannot be undone.`)) return;
    try {
      if (tool.on_hand > 0) {
        await warehouseApi.adjustStock({
          item_id:         tool.item_id,
          adjustment_type: "CORRECTION_SUB",
          quantity:        tool.on_hand,
          notes:           "Tool removed from warehouse",
        });
      }
      await client.patch(`/items/${tool.item_id}`, { is_active: false });
      setDeletingTool(null);
      await loadStock();
      await loadToolLocations();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setDeleteError(detail ?? "Delete failed.");
    }
  };

  // Only show stock received into the global main warehouse (no project)
  const globalStock = stock.filter(i => i.project_id === null);

  // Derived KPIs
  const totalSkus   = globalStock.length;
  const totalOnHand = globalStock.reduce((s, i) => s + i.on_hand, 0);
  const lowStockCount = globalStock.filter(i => i.on_hand <= 5).length;

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Main Warehouse"
        description="Company-wide stock across all projects — view on-hand, transfer to sites, track movements."
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => setShowReceive(true)}>
              <PackagePlus className="w-4 h-4" />Receive Stock
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowAdjust(true)}>
              <SlidersHorizontal className="w-4 h-4" />Adjust
            </Button>
            <Button size="sm" variant="outline" onClick={loadStock} disabled={loading}>
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            </Button>
          </div>
        }
      />

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />{error}
        </div>
      )}

      {/* KPI bar */}
      {!loading && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-card border border-border rounded-xl p-4">
            <p className="text-xs text-muted-foreground">SKUs on hand</p>
            <p className="text-2xl font-bold mt-0.5">{totalSkus}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-4">
            <p className="text-xs text-muted-foreground">Total units</p>
            <p className="text-2xl font-bold mt-0.5">{fmt(totalOnHand)}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-4">
            <p className="text-xs text-muted-foreground">Low stock</p>
            <p className="text-2xl font-bold mt-0.5">{lowStockCount}</p>
            {lowStockCount > 0 && (
              <p className="text-xs text-amber-600 mt-0.5">{lowStockCount} SKU{lowStockCount !== 1 ? "s" : ""} ≤ 5 units</p>
            )}
          </div>
        </div>
      )}

      {/* Stock table — global main warehouse only */}
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-14 rounded-xl" />)}
        </div>
      ) : globalStock.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center space-y-2">
          <Warehouse className="w-10 h-10 text-muted-foreground mx-auto" />
          <p className="text-sm font-medium">Main warehouse is empty</p>
          <p className="text-xs text-muted-foreground">
            Stock arrives when deliveries are received with destination set to "Main Warehouse".
          </p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="grid grid-cols-[1fr_110px_100px_130px_auto] gap-0 border-b border-border bg-muted/40 px-4 py-2.5">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Item</span>
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide text-right">On Hand</span>
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide text-right">Unit</span>
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide hidden sm:block">Last Movement</span>
            <span className="w-36" />
          </div>

          {globalStock.map((item, i) => (
            <div
              key={item.item_id}
              className={cn(
                "grid grid-cols-[1fr_110px_100px_130px_auto] gap-0 items-center px-4 py-3 transition-colors hover:bg-muted/30",
                i < globalStock.length - 1 && "border-b border-border",
              )}
            >
              <p className="text-sm font-medium truncate pr-3">{item.item_name}</p>
              <p className="text-sm font-semibold text-right tabular-nums">{fmt(item.on_hand)}</p>
              <p className="text-xs text-muted-foreground text-right">{item.unit ?? "—"}</p>
              <p className="text-xs text-muted-foreground hidden sm:block">
                {item.last_movement ? formatDate(item.last_movement) : "—"}
              </p>
              <div className="flex items-center justify-end gap-1.5">
                <Button
                  size="sm" variant="outline"
                  className="h-8 text-xs gap-1.5 shrink-0"
                  onClick={() => setTransferItem(item)}
                >
                  <ArrowRight className="w-3 h-3" />
                  <span className="hidden sm:inline">Transfer to</span> Site
                </Button>
                <button
                  onClick={() => { setDeleteStockItem(item); setDeleteStockNotes(""); }}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                  title="Remove from warehouse"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tools panel */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <button
            className="flex items-center gap-2 flex-1 text-left hover:opacity-80 transition-opacity"
            onClick={toggleTools}
          >
            <Wrench className="w-4 h-4 text-primary" />
            <span className="font-semibold text-sm">Tools in Main Warehouse</span>
            {tools.length > 0 && (
              <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
                {tools.length}
              </span>
            )}
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAddTool(true)}
              className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 transition-colors px-2 py-1 rounded-lg hover:bg-primary/10 border border-primary/20"
              title="Add tools to warehouse"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Tool
            </button>
            {loading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-muted-foreground" />}
            <button onClick={toggleTools}>
              {showTools
                ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
                : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </button>
          </div>
        </div>

        {showTools && (
          <div className="border-t border-border">
            {loading ? (
              <div className="px-4 py-3 space-y-2">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 rounded-lg" />)}
              </div>
            ) : tools.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center px-4 py-6">
                No tools in main warehouse. Receive stock with a TOOL-type item to see it here.
              </p>
            ) : (
              <div className="divide-y divide-border">
                {deleteError && (
                  <div className="mx-4 my-2 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2 flex items-center gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                    {deleteError}
                    <button onClick={() => setDeleteError("")} className="ml-auto"><X className="w-3 h-3" /></button>
                  </div>
                )}
                {tools.map(tool => {
                  const siteLocations = toolLocations.filter(l => l.item_id === tool.item_id);
                  return (
                  <div key={tool.item_id} className="px-4 py-3 hover:bg-muted/30 transition-colors">
                    <div className="flex items-center gap-3">
                      <Wrench className="w-4 h-4 text-muted-foreground shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{tool.item_name}</p>
                        <p className="text-xs text-muted-foreground">
                          In warehouse: <strong>{fmt(tool.on_hand)} {tool.unit ?? ""}</strong>
                          {tool.last_movement ? ` · Last: ${formatDate(tool.last_movement)}` : ""}
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Button
                          size="sm" variant="outline"
                          className="h-8 text-xs gap-1.5"
                          onClick={() => setTransferItem(tool)}
                        >
                          <ArrowRight className="w-3 h-3" />
                          Send to Project
                        </Button>
                        <button
                          onClick={() => { setEditTool(tool); setDeleteError(""); }}
                          className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                          title="Edit tool"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDeleteTool(tool)}
                          className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                          title="Remove tool from warehouse"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    {/* Site distribution */}
                    {locsLoading ? (
                      <p className="text-xs text-muted-foreground mt-1.5 pl-7">Loading site locations…</p>
                    ) : siteLocations.length > 0 ? (
                      <div className="mt-2 pl-7 flex flex-wrap gap-1.5">
                        {siteLocations.map(loc => (
                          <span
                            key={loc.site_id}
                            className="inline-flex items-center gap-1 text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-2 py-0.5"
                          >
                            <MapPin className="w-2.5 h-2.5" />
                            {loc.project_name}
                            <span className="font-semibold">{fmt(loc.on_hand)}</span>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground mt-1 pl-7">All in main warehouse</p>
                    )}
                  </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Movement history */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <button
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/30 transition-colors"
          onClick={toggleHistory}
        >
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-primary" />
            <span className="font-semibold text-sm">Movement History</span>
            {history.length > 0 && (
              <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
                {history.length}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {histLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-muted-foreground" />}
            {showHistory
              ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
              : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
          </div>
        </button>

        {showHistory && (
          <div className="border-t border-border">
            {histLoading ? (
              <div className="px-4 py-3 space-y-2">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 rounded-lg" />)}
              </div>
            ) : history.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center px-4 py-6">
                No movements recorded yet.
              </p>
            ) : (
              <div className="px-4 py-2 max-h-80 overflow-y-auto">
                {history.map(m => <HistoryRow key={m.id} m={m} />)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Transfer modal */}
      {transferItem && (
        <TransferModal
          item={transferItem}
          onClose={() => setTransferItem(null)}
          onDone={loadStock}
        />
      )}

      {showReceive && (
        <ReceiveStockModal
          onClose={() => setShowReceive(false)}
          onDone={() => { loadStock(); loadHistory(); }}
        />
      )}

      {showAdjust && (
        <AdjustStockModal
          onClose={() => setShowAdjust(false)}
          onDone={() => { loadStock(); loadHistory(); }}
        />
      )}

      {showAddTool && (
        <AddToolModal
          onClose={() => setShowAddTool(false)}
          onDone={() => { loadStock(); loadToolLocations(); }}
        />
      )}

      {editTool && (
        <EditToolModal
          tool={editTool}
          onClose={() => setEditTool(null)}
          onDone={() => { loadStock(); setEditTool(null); }}
        />
      )}

      {/* Delete stock confirmation */}
      {deleteStockItem && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => !deleteStockBusy && setDeleteStockItem(null)}
        >
          <div
            className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-base">Remove from Warehouse</h3>
              <button
                onClick={() => setDeleteStockItem(null)}
                disabled={deleteStockBusy}
              >
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>

            <div className="bg-destructive/5 border border-destructive/20 rounded-xl px-4 py-3 space-y-0.5">
              <p className="font-medium text-sm">{deleteStockItem.item_name}</p>
              <p className="text-xs text-muted-foreground">
                On hand: <strong>{fmt(deleteStockItem.on_hand)} {deleteStockItem.unit ?? "units"}</strong>
                {" · "}
                <span className="text-primary font-medium">Global Stock</span>
              </p>
            </div>

            <p className="text-xs text-muted-foreground">
              This will write off the full on-hand quantity via a stock correction. This cannot be undone.
            </p>

            <div>
              <label className="text-xs text-muted-foreground block mb-1">Reason / Notes (optional)</label>
              <input
                type="text"
                value={deleteStockNotes}
                onChange={e => setDeleteStockNotes(e.target.value)}
                placeholder="e.g. Item discontinued, data cleanup"
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                disabled={deleteStockBusy}
              />
            </div>

            <div className="flex gap-2">
              <Button
                variant="destructive"
                className="flex-1"
                disabled={deleteStockBusy}
                onClick={async () => {
                  setDeleteStockBusy(true);
                  try {
                    await warehouseApi.adjustStock({
                      item_id:         deleteStockItem.item_id,
                      adjustment_type: "CORRECTION_SUB",
                      quantity:        deleteStockItem.on_hand,
                      notes:           deleteStockNotes || "Removed from main warehouse",
                    });
                    setDeleteStockItem(null);
                    const updated = await warehouseApi.getGlobalStock();
                    setStock(updated);
                  } catch (err: unknown) {
                    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
                    alert(detail ?? "Failed to remove stock.");
                  } finally {
                    setDeleteStockBusy(false);
                  }
                }}
              >
                {deleteStockBusy ? "Removing…" : "Remove Stock"}
              </Button>
              <Button
                variant="outline"
                onClick={() => setDeleteStockItem(null)}
                disabled={deleteStockBusy}
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
