/**
 * Project Warehouse — operational stock management per project.
 *
 * Phase 3B: Warehouse belongs to PROJECT, not to a site/block.
 * Stock flow:  Delivery → Project Warehouse → Lot/Unit → Milestone Usage
 *
 * Sections:
 *   A) Incoming Deliveries   — recent + pending receipts
 *   B) Current Stock         — on-hand with shortage indicators
 *   C) Dispatch Queue        — pending material requests (approved, awaiting dispatch)
 *   D) Movement History      — all movements through this project warehouse
 *   E) Shortage Alerts       — items where on-hand < requested
 *
 * Uses:
 *   GET /projects/{id}/warehouse/         — stock (site_id=NULL)
 *   GET /projects/{id}/warehouse/history  — movements
 *   POST /projects/{id}/warehouse/transfer — dispatch to site/lot
 *   POST /projects/{id}/warehouse/return  — receive back from site
 *   GET /projects/{id}/deliveries/        — incoming deliveries
 *   GET /projects/{id}/material-requests/ — dispatch queue
 */

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Package, ArrowRight, ArrowLeft, RefreshCw, History,
  AlertTriangle, X, Truck, ChevronDown, ChevronUp,
  Warehouse, Clock, CheckCircle2, Plus, SlidersHorizontal,
  SendHorizonal, Vote, ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { deliveriesApi, type Delivery } from "@/api/deliveries";
import { materialRequestsApi, type MaterialRequest } from "@/api/materialRequests";
import {
  warehouseApi,
  type WarehouseStockItem,
  type WarehouseMovement,
} from "@/api/warehouse";
import {
  warehouseTransfersApi,
  type WarehouseTransferRequest,
} from "@/api/warehouseTransfers";
import { useAuthContext } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n % 1 === 0 ? String(n) : n.toFixed(2);
}

const MOVEMENT_LABEL: Record<string, string> = {
  DELIVERY_RECEIVED:   "Delivery received",
  TRANSFER_OUT:        "Dispatched to lot",
  TRANSFER_IN:         "Received (return)",
  OPENING_BALANCE:     "Opening balance",
  ADJUSTMENT_ADD:      "Adjustment +",
  ADJUSTMENT_SUBTRACT: "Adjustment −",
  RETURN_TO_STORE:     "Return",
};

const MOVEMENT_COLOR: Record<string, string> = {
  DELIVERY_RECEIVED: "text-green-600",
  TRANSFER_IN:       "text-green-600",
  OPENING_BALANCE:   "text-green-600",
  ADJUSTMENT_ADD:    "text-green-600",
  TRANSFER_OUT:      "text-amber-600",
  ADJUSTMENT_SUBTRACT: "text-destructive",
};

// ── Shared adjustment options ─────────────────────────────────────────────────

const ADJUST_OPTIONS = [
  { value: "CORRECTION_ADD", label: "Correction (Add)",    dir: "in"  },
  { value: "RETURNED",       label: "Returned to stock",   dir: "in"  },
  { value: "OTHER_ADD",      label: "Other (Add)",         dir: "in"  },
  { value: "CORRECTION_SUB", label: "Correction (Remove)", dir: "out" },
  { value: "DAMAGED",        label: "Damaged",             dir: "out" },
  { value: "LOST",           label: "Lost",                dir: "out" },
  { value: "OTHER_SUB",      label: "Other (Remove)",      dir: "out" },
] as const;

// ── Add Material Modal ────────────────────────────────────────────────────────

function AddMaterialModal({
  projectId, onClose, onDone,
}: { projectId: string; onClose: () => void; onDone: () => void }) {
  const [name,     setName]     = useState("");
  const [quantity, setQuantity] = useState("");
  const [unit,     setUnit]     = useState("");
  const [notes,    setNotes]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!name.trim())        { setError("Enter a material name."); return; }
    if (!qty || qty <= 0)    { setError("Enter a valid quantity."); return; }
    setLoading(true); setError("");
    try {
      await warehouseApi.addProjectMaterial(projectId, {
        name: name.trim(),
        quantity: qty,
        unit: unit.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      onDone(); onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Failed to add material.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Add Material to Warehouse</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Material name</label>
            <input type="text" value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. Bag of screws, Cable ties" autoFocus
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Quantity</label>
              <input type="number" min="0.001" step="any" value={quantity}
                onChange={e => setQuantity(e.target.value)} placeholder="e.g. 10"
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Unit (optional)</label>
              <input type="text" value={unit} onChange={e => setUnit(e.target.value)}
                placeholder="e.g. pcs, bags"
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Notes (optional)</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="e.g. For gate installation"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
        </div>
        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex gap-2 pt-1">
          <Button onClick={submit} disabled={loading} className="flex-1">
            {loading ? "Adding…" : "Add to Warehouse"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Adjust Stock Modal ────────────────────────────────────────────────────────

function AdjustStockModal({
  projectId, item, onClose, onDone,
}: { projectId: string; item: WarehouseStockItem; onClose: () => void; onDone: () => void }) {
  const [adjType,  setAdjType]  = useState("CORRECTION_ADD");
  const [quantity, setQuantity] = useState("");
  const [notes,    setNotes]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const selected = ADJUST_OPTIONS.find(o => o.value === adjType);
  const qty      = parseFloat(quantity) || 0;
  const newStock = selected?.dir === "in"
    ? item.on_hand + qty
    : Math.max(0, item.on_hand - qty);

  const submit = async () => {
    if (!qty || qty <= 0) { setError("Enter a valid quantity."); return; }
    setLoading(true); setError("");
    try {
      await warehouseApi.adjustProjectStock(projectId, {
        item_id: item.item_id,
        adjustment_type: adjType,
        quantity: qty,
        notes: notes.trim() || undefined,
      });
      onDone(); onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Adjustment failed.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Adjust Stock</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>
        <div className="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 flex items-center gap-3">
          <Package className="w-4 h-4 text-primary shrink-0" />
          <div>
            <p className="font-medium text-sm">{item.item_name}</p>
            <p className="text-xs text-muted-foreground">
              Current stock: <strong>{fmt(item.on_hand)} {item.unit ?? ""}</strong>
            </p>
          </div>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Adjustment type</label>
            <select value={adjType} onChange={e => setAdjType(e.target.value)}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm">
              <optgroup label="Add Stock">
                {ADJUST_OPTIONS.filter(o => o.dir === "in").map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </optgroup>
              <optgroup label="Remove Stock">
                {ADJUST_OPTIONS.filter(o => o.dir === "out").map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </optgroup>
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Quantity ({item.unit ?? "units"})
            </label>
            <input type="number" min="0.001" step="any" value={quantity}
              onChange={e => setQuantity(e.target.value)} placeholder="Enter quantity" autoFocus
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Notes (optional)</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="Reason for adjustment"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
        </div>
        {qty > 0 && selected && (
          <div className={cn(
            "flex items-center gap-2 text-xs rounded-lg px-3 py-2 font-medium",
            selected.dir === "in" ? "text-green-700 bg-green-50" : "text-destructive bg-destructive/10",
          )}>
            <span>{selected.dir === "in" ? "+" : "−"}{qty} {item.unit ?? ""}</span>
            <span className="text-muted-foreground">→</span>
            <span>{fmt(newStock)} {item.unit ?? ""} remaining</span>
          </div>
        )}
        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex gap-2 pt-1">
          <Button onClick={submit} disabled={loading} className="flex-1">
            {loading ? "Adjusting…" : "Confirm Adjustment"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Dispatch-to-Site Modal ────────────────────────────────────────────────────

function DispatchModal({
  projectId,
  item,
  sites,
  onClose,
  onDone,
}: {
  projectId: string;
  item:      WarehouseStockItem;
  sites:     Site[];
  onClose:   () => void;
  onDone:    () => void;
}) {
  const [siteId,   setSiteId]   = useState(sites[0]?.id ?? "");
  const [quantity, setQuantity] = useState("");
  const [notes,    setNotes]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

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
      await warehouseApi.transferToSite(projectId, item.item_id, siteId, qty, notes || undefined);
      onDone();
      onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Dispatch failed.");
    } finally { setLoading(false); }
  };

  const selectedSite = sites.find(s => s.id === siteId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Dispatch to Site</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 flex items-center gap-3">
          <Package className="w-4 h-4 text-primary shrink-0" />
          <div>
            <p className="font-medium text-sm">{item.item_name}</p>
            <p className="text-xs text-muted-foreground">
              Available: <strong>{fmt(item.on_hand)} {item.unit ?? ""}</strong>
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Destination site / block</label>
            <select value={siteId} onChange={e => setSiteId(e.target.value)}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm">
              {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Quantity ({item.unit ?? "units"})
            </label>
            <input type="number" min="0.001" step="any" max={item.on_hand}
              value={quantity} onChange={e => setQuantity(e.target.value)}
              placeholder={`Max ${fmt(item.on_hand)}`} autoFocus
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Notes (optional)</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="e.g. For foundation pour"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
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
          <Button onClick={submit} disabled={loading} className="flex-1">
            {loading ? "Dispatching…" : "Dispatch"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Return Modal ──────────────────────────────────────────────────────────────

function ReturnModal({
  projectId, sites, onClose, onDone,
}: { projectId: string; sites: Site[]; onClose: () => void; onDone: () => void; }) {
  const [siteId,     setSiteId]     = useState(sites[0]?.id ?? "");
  const [siteStock,  setSiteStock]  = useState<WarehouseStockItem[]>([]);
  const [stkLoading, setStkLoading] = useState(false);
  const [itemId,     setItemId]     = useState("");
  const [quantity,   setQuantity]   = useState("");
  const [notes,      setNotes]      = useState("");
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");

  useEffect(() => {
    if (!siteId) return;
    setStkLoading(true); setItemId("");
    warehouseApi.getStock(siteId)
      .then(s => { setSiteStock(s); if (s.length) setItemId(s[0].item_id); })
      .catch(() => setSiteStock([]))
      .finally(() => setStkLoading(false));
  }, [siteId]);

  const selectedItem = siteStock.find(s => s.item_id === itemId);
  const selectedSite = sites.find(s => s.id === siteId);

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!siteId) { setError("Select a site."); return; }
    if (!itemId) { setError("Select an item."); return; }
    if (!qty || qty <= 0) { setError("Enter a valid quantity."); return; }
    setLoading(true); setError("");
    try {
      await warehouseApi.returnFromSite(projectId, itemId, siteId, qty, notes || undefined);
      onDone();
      onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Return failed.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Receive Return from Site</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Source site / block</label>
            <select value={siteId} onChange={e => setSiteId(e.target.value)}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm">
              {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Item to return</label>
            {stkLoading
              ? <div className="h-10 rounded-md border border-input bg-muted animate-pulse" />
              : siteStock.length === 0
              ? <p className="text-xs text-muted-foreground bg-muted/40 rounded-md px-3 py-2.5">
                  No stock at {selectedSite?.name ?? "this site"}.
                </p>
              : <select value={itemId} onChange={e => setItemId(e.target.value)}
                  className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm">
                  {siteStock.map(s => (
                    <option key={s.item_id} value={s.item_id}>
                      {s.item_name} — {fmt(s.on_hand)} {s.unit ?? ""} available
                    </option>
                  ))}
                </select>
            }
          </div>
          {selectedItem && (
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                Quantity to return ({selectedItem.unit ?? "units"})
              </label>
              <input type="number" min="0.001" step="any" max={selectedItem.on_hand}
                value={quantity} onChange={e => setQuantity(e.target.value)}
                placeholder={`Max ${fmt(selectedItem.on_hand)}`} autoFocus
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
            </div>
          )}
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Notes (optional)</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="e.g. Excess from completed slab"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
        </div>

        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

        <div className="flex gap-2 pt-1">
          <Button onClick={submit} disabled={loading || siteStock.length === 0 || !itemId} className="flex-1">
            {loading ? "Processing…" : "Receive Return"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Section: Incoming Deliveries ──────────────────────────────────────────────

function IncomingDeliveries({ deliveries }: { deliveries: Delivery[] }) {
  const recent = deliveries.slice(0, 8);
  const statusColor: Record<string, string> = {
    RECEIVED:           "text-green-600",
    PARTIALLY_RECEIVED: "text-amber-600",
    PENDING:            "text-blue-600",
    MATCHED:            "text-green-600",
    DISPUTED:           "text-destructive",
  };

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border bg-muted/30">
        <div className="flex items-center gap-2">
          <Truck className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Incoming Deliveries</span>
          <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
            {deliveries.length}
          </span>
        </div>
      </div>
      {recent.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center px-4 py-6">
          No deliveries recorded for this project.
        </p>
      ) : (
        <div className="divide-y divide-border/40">
          {recent.map(d => (
            <div key={d.id} className="flex items-center justify-between px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">
                  {d.delivery_number ?? d.id.slice(0, 8)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDate(d.delivery_date)}
                  {d.supplier_delivery_note_number
                    ? ` · DN: ${d.supplier_delivery_note_number}` : ""}
                </p>
              </div>
              <span className={cn(
                "text-xs font-medium shrink-0 ml-2",
                statusColor[d.delivery_status] ?? "text-muted-foreground",
              )}>
                {d.delivery_status.replace(/_/g, " ")}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Section: Dispatch Queue ───────────────────────────────────────────────────

function DispatchQueue({ mrs }: { mrs: MaterialRequest[] }) {
  const pending = mrs.filter(m =>
    m.status === "APPROVED" || m.status === "SUBMITTED" || m.status === "PENDING_APPROVAL"
  ).slice(0, 8);

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border bg-muted/30">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-amber-600" />
          <span className="text-sm font-semibold">Dispatch Queue</span>
          {pending.length > 0 && (
            <span className="text-xs bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 rounded-full px-2 py-0.5">
              {pending.length} pending
            </span>
          )}
        </div>
      </div>
      {pending.length === 0 ? (
        <div className="flex items-center gap-2 px-4 py-4 text-xs text-green-700 dark:text-green-400">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          No pending material requests — all caught up.
        </div>
      ) : (
        <div className="divide-y divide-border/40">
          {pending.map(mr => (
            <div key={mr.id} className="px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{mr.request_number}</span>
                <span className={cn(
                  "text-xs px-1.5 py-0.5 rounded font-medium",
                  mr.status === "APPROVED"
                    ? "bg-green-100 text-green-700"
                    : "bg-amber-100 text-amber-700"
                )}>
                  {mr.status.replace(/_/g, " ")}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {mr.items.length} item{mr.items.length !== 1 ? "s" : ""}
                {mr.needed_by_date
                  ? ` · Needed by ${formatDate(mr.needed_by_date)}` : ""}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Section: Shortage Alerts ─────────────────────────────────────────────────

function ShortageAlerts({
  stock, mrs,
}: { stock: WarehouseStockItem[]; mrs: MaterialRequest[]; }) {
  // Find items requested but with zero/low stock
  const requestedItems = new Map<string, { name: string; requested: number; unit: string | null }>();
  for (const mr of mrs.filter(m => m.status === "APPROVED" || m.status === "SUBMITTED")) {
    for (const item of mr.items) {
      if (!item.description) continue;
      const key = item.description.toLowerCase().trim();
      const existing = requestedItems.get(key);
      const qty = item.requested_quantity ?? item.quantity_requested ?? 0;
      if (existing) {
        existing.requested += qty;
      } else {
        requestedItems.set(key, { name: item.description, requested: qty, unit: item.unit });
      }
    }
  }

  // Check stock on-hand vs requested (by item_name match, approximate)
  const shortages = stock.filter(s => {
    const key = s.item_name.toLowerCase().trim();
    const req = requestedItems.get(key);
    return req && s.on_hand < req.requested;
  });

  if (shortages.length === 0 && requestedItems.size === 0) return null;

  return (
    <div className={cn(
      "border rounded-xl overflow-hidden",
      shortages.length > 0
        ? "border-amber-200 bg-amber-50/50 dark:border-amber-900/50 dark:bg-amber-950/10"
        : "border-border bg-card"
    )}>
      <div className="px-4 py-3 border-b border-inherit">
        <div className="flex items-center gap-2">
          <AlertTriangle className={cn("w-4 h-4", shortages.length > 0 ? "text-amber-600" : "text-muted-foreground")} />
          <span className="text-sm font-semibold">
            {shortages.length > 0 ? `${shortages.length} Shortage${shortages.length !== 1 ? "s" : ""}` : "Stock Levels"}
          </span>
        </div>
      </div>
      {shortages.length === 0 ? (
        <p className="text-xs text-green-700 dark:text-green-400 px-4 py-3 flex items-center gap-2">
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
          All requested items have sufficient stock.
        </p>
      ) : (
        <div className="divide-y divide-border/40">
          {shortages.map(s => {
            const key = s.item_name.toLowerCase().trim();
            const req = requestedItems.get(key);
            const gap = (req?.requested ?? 0) - s.on_hand;
            return (
              <div key={s.item_id} className="flex items-center justify-between px-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate text-amber-700 dark:text-amber-400">
                    {s.item_name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    On hand: {fmt(s.on_hand)} · Requested: {fmt(req?.requested)} {s.unit ?? ""}
                  </p>
                </div>
                <span className="text-xs font-semibold text-amber-600 shrink-0 ml-2">
                  −{fmt(gap)} {s.unit ?? ""}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Request Project Transfer Modal ───────────────────────────────────────────

function RequestTransferModal({
  fromProjectId,
  projects,
  stock,
  onClose,
  onDone,
}: {
  fromProjectId: string;
  projects: Project[];
  stock: WarehouseStockItem[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [toProjectId, setToProjectId] = useState("");
  const [itemId,      setItemId]      = useState(stock[0]?.item_id ?? "");
  const [quantity,    setQuantity]    = useState("");
  const [reason,      setReason]      = useState("");
  const [notes,       setNotes]       = useState("");
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState("");

  const selectedItem = stock.find(s => s.item_id === itemId);
  const otherProjects = projects.filter(p => p.id !== fromProjectId);

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!toProjectId)     { setError("Select a destination project."); return; }
    if (!itemId)          { setError("Select an item."); return; }
    if (!qty || qty <= 0) { setError("Enter a valid quantity."); return; }
    if (!reason.trim())   { setError("Provide a reason for the transfer."); return; }
    setLoading(true); setError("");
    try {
      await warehouseTransfersApi.submitRequest(fromProjectId, {
        to_project_id: toProjectId,
        item_id: itemId,
        quantity: qty,
        reason: reason.trim(),
        notes: notes.trim() || undefined,
      });
      onDone(); onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string; message?: string } } })?.response?.data;
      setError(d?.message ?? d?.detail ?? "Transfer request failed.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-md p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-base">Request Project Transfer</h3>
            <p className="text-xs text-muted-foreground mt-0.5">Requires 3 office approvals before stock moves</p>
          </div>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Destination project</label>
            <select value={toProjectId} onChange={e => setToProjectId(e.target.value)}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm">
              <option value="">— Select project —</option>
              {otherProjects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Item</label>
            {stock.length === 0 ? (
              <p className="text-xs text-muted-foreground bg-muted/40 rounded-md px-3 py-2.5">No stock in warehouse.</p>
            ) : (
              <select value={itemId} onChange={e => setItemId(e.target.value)}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm">
                {stock.map(s => (
                  <option key={s.item_id} value={s.item_id}>
                    {s.item_name} — {fmt(s.on_hand)} {s.unit ?? ""} available
                  </option>
                ))}
              </select>
            )}
          </div>

          {selectedItem && (
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                Quantity ({selectedItem.unit ?? "units"})
              </label>
              <input type="number" min="0.001" step="any" max={selectedItem.on_hand}
                value={quantity} onChange={e => setQuantity(e.target.value)}
                placeholder={`Max ${fmt(selectedItem.on_hand)}`}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
            </div>
          )}

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Reason <span className="text-destructive">*</span></label>
            <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2}
              placeholder="e.g. Excess stock no longer needed on this project"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none" />
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Additional notes (optional)</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="Any extra details"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
        </div>

        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

        <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2">
          <p className="text-xs text-amber-700 dark:text-amber-400">
            This request will be sent to the office for approval. Stock will only move once 3 approvals are received (or overridden by the owner).
          </p>
        </div>

        <div className="flex gap-2 pt-1">
          <Button onClick={submit} disabled={loading || stock.length === 0} className="flex-1">
            <SendHorizonal className="w-3.5 h-3.5" />
            {loading ? "Submitting…" : "Submit Request"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Transfer Requests Panel ───────────────────────────────────────────────────

function TransferRequestsPanel({
  transfers,
  onVote,
  onOverride,
  onReject,
  role,
}: {
  transfers: WarehouseTransferRequest[];
  onVote: (id: string) => void;
  onOverride: (id: string) => void;
  onReject: (id: string, reason: string) => void;
  role: string;
}) {
  const [rejectId,     setRejectId]     = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectLoading, setRejectLoading] = useState(false);

  const isOffice = ["OWNER", "OFFICE_ADMIN", "OFFICE_USER", "PROCUREMENT_LEAD"].includes(role);
  const isOwner  = role === "OWNER";

  const statusBadge = (status: string) => {
    if (status === "EXECUTED") return <Badge variant="success">Executed</Badge>;
    if (status === "REJECTED") return <Badge variant="destructive">Rejected</Badge>;
    return <Badge variant="secondary">Pending Approval</Badge>;
  };

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <SendHorizonal className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Project Transfer Requests</span>
          {transfers.filter(t => t.status === "PENDING").length > 0 && (
            <span className="text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 rounded-full px-2 py-0.5 font-medium">
              {transfers.filter(t => t.status === "PENDING").length} pending
            </span>
          )}
        </div>
      </div>

      {transfers.length === 0 ? (
        <p className="text-xs text-muted-foreground text-center px-4 py-6">No transfer requests for this project.</p>
      ) : (
        <div className="divide-y divide-border/40">
          {transfers.map(tr => (
            <div key={tr.id} className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-medium">{tr.item_name ?? "Unknown item"}</p>
                    {statusBadge(tr.status)}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {fmt(tr.quantity)} {tr.unit ?? ""} · From: <span className="font-medium">{tr.from_project_name}</span>
                    {" → "}To: <span className="font-medium">{tr.to_project_name}</span>
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Requested by {tr.requested_by_name ?? "—"} · {formatDate(tr.requested_at)}
                  </p>
                  <p className="text-xs text-foreground/80 mt-1 italic">"{tr.reason}"</p>
                </div>
              </div>

              {tr.status === "PENDING" && (
                <>
                  {/* Vote progress */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-[11px] text-muted-foreground">
                      <span>Approvals</span>
                      <span>{tr.vote_count} / {tr.votes_required}</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{ width: `${Math.min((tr.vote_count / tr.votes_required) * 100, 100)}%` }}
                      />
                    </div>
                    {tr.votes.map(v => (
                      <div key={v.id} className="flex items-center gap-1.5 text-[11px]">
                        <CheckCircle2 className="w-3 h-3 text-green-500 shrink-0" />
                        <span>{v.voted_by_name ?? "—"}</span>
                        {v.is_override && <span className="text-amber-600 text-[10px]">(override)</span>}
                      </div>
                    ))}
                  </div>

                  {/* Actions */}
                  {isOffice && (
                    <div className="flex gap-2 flex-wrap">
                      <Button size="sm" variant="outline" className="h-7 text-xs gap-1"
                        onClick={() => onVote(tr.id)}>
                        <Vote className="w-3 h-3" />Approve
                      </Button>
                      {isOwner && (
                        <Button size="sm" variant="outline" className="h-7 text-xs gap-1 border-amber-500 text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/20"
                          onClick={() => onOverride(tr.id)}>
                          <ShieldCheck className="w-3 h-3" />Override
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive hover:text-destructive"
                        onClick={() => setRejectId(tr.id)}>
                        Reject
                      </Button>
                    </div>
                  )}
                </>
              )}

              {tr.status === "REJECTED" && tr.rejection_reason && (
                <p className="text-xs text-destructive bg-destructive/10 rounded px-2 py-1">
                  Rejected: {tr.rejection_reason}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Inline reject dialog */}
      {rejectId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setRejectId(null)}>
          <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-5 space-y-4" onClick={e => e.stopPropagation()}>
            <h3 className="font-semibold text-sm">Reject Transfer Request</h3>
            <textarea value={rejectReason} onChange={e => setRejectReason(e.target.value)} rows={3}
              placeholder="Reason for rejection"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none" />
            <div className="flex gap-2">
              <Button size="sm" variant="destructive" disabled={!rejectReason.trim() || rejectLoading}
                onClick={async () => {
                  setRejectLoading(true);
                  await onReject(rejectId, rejectReason.trim());
                  setRejectId(null); setRejectReason(""); setRejectLoading(false);
                }}>
                {rejectLoading ? "Rejecting…" : "Confirm Reject"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setRejectId(null)}>Cancel</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ProjectWarehousePage() {
  const [searchParams] = useSearchParams();
  const { role } = useAuthContext();
  const [projects,   setProjects]   = useState<Project[]>([]);
  const [sites,      setSites]      = useState<Site[]>([]);
  const [projectId,  setProjectId]  = useState(searchParams.get("project") ?? "");

  const [stock,      setStock]      = useState<WarehouseStockItem[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [mrs,        setMRs]        = useState<MaterialRequest[]>([]);
  const [history,    setHistory]    = useState<WarehouseMovement[]>([]);
  const [transfers,  setTransfers]  = useState<WarehouseTransferRequest[]>([]);
  const [loading,    setLoading]    = useState(false);
  const [showHist,   setShowHist]   = useState(false);
  const [histLoad,   setHistLoad]   = useState(false);
  const [error,      setError]      = useState("");

  const [dispatchItem,    setDispatchItem]    = useState<WarehouseStockItem | null>(null);
  const [showReturn,      setShowReturn]      = useState(false);
  const [showAddMaterial, setShowAddMaterial] = useState(false);
  const [adjustItem,      setAdjustItem]      = useState<WarehouseStockItem | null>(null);
  const [showTransfer,    setShowTransfer]    = useState(false);

  useEffect(() => {
    projectsApi.list(1, 100, "ACTIVE").then(r => {
      setProjects(r.items);
      // Only auto-select first project when no ?project= param provided
      if (!searchParams.get("project") && r.items.length > 0) setProjectId(r.items[0].id);
    }).catch(() => {});
  }, [searchParams]);

  useEffect(() => {
    if (!projectId) { setSites([]); return; }
    sitesApi.list(projectId).then(setSites).catch(() => setSites([]));
  }, [projectId]);

  const loadAll = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const [s, d, m, t] = await Promise.all([
        warehouseApi.getMainStock(projectId),
        deliveriesApi.list(projectId),
        materialRequestsApi.list(projectId),
        warehouseTransfersApi.listForProject(projectId),
      ]);
      setStock(s);
      setDeliveries(d);
      setMRs(m);
      setTransfers(t);
    } catch { setError("Failed to load project warehouse data."); }
    finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const loadHistory = useCallback(async () => {
    if (!projectId) return;
    setHistLoad(true);
    try { setHistory(await warehouseApi.getMainHistory(projectId, 100)); }
    catch { /* silent */ }
    finally { setHistLoad(false); }
  }, [projectId]);

  const toggleHist = () => {
    setShowHist(p => !p);
    if (!showHist && history.length === 0) loadHistory();
  };

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Project Warehouse"
        description="Operational stock for each project — incoming, on-hand, dispatch queue, and history."
        actions={
          projectId ? (
            <div className="flex gap-2 flex-wrap">
              <Button size="sm" variant="outline"
                onClick={() => setShowAddMaterial(true)}>
                <Plus className="w-4 h-4" />Add Material
              </Button>
              <Button size="sm" variant="outline"
                onClick={() => setShowReturn(true)} disabled={sites.length === 0}>
                <ArrowLeft className="w-4 h-4" />Receive Return
              </Button>
              <Button size="sm" variant="outline"
                onClick={() => setShowTransfer(true)} disabled={stock.length === 0}>
                <SendHorizonal className="w-4 h-4" />Request Transfer
              </Button>
            </div>
          ) : undefined
        }
      />

      {/* Project selector */}
      <div className="flex flex-wrap gap-3 items-center">
        <select value={projectId} onChange={e => setProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[220px]">
          <option value="">— Select project —</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button onClick={loadAll} disabled={loading}
          className="h-9 w-9 flex items-center justify-center rounded-md border border-input bg-background hover:bg-muted text-muted-foreground disabled:opacity-50 transition-colors"
          title="Refresh">
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />{error}
        </div>
      )}

      {!projectId ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">
          <Warehouse className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
          Select a project to view its warehouse.
        </div>
      ) : loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : (
        <div className="space-y-4">

          {/* A) Incoming Deliveries */}
          <IncomingDeliveries deliveries={deliveries} />

          {/* B) Current Stock */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Package className="w-4 h-4 text-primary" />
                <span className="text-sm font-semibold">Current Stock</span>
                {stock.length > 0 && (
                  <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
                    {stock.length} SKU{stock.length !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
            </div>
            {stock.length === 0 ? (
              <div className="p-8 text-center">
                <Package className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground">No stock in project warehouse.</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Stock arrives when deliveries are received for this project.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <div className="grid grid-cols-[1fr_110px_80px_120px_auto] gap-0 border-b border-border bg-muted/20 px-4 py-2 min-w-[420px]">
                  {["Item", "On Hand", "Unit", "Last Movement", ""].map((h, i) => (
                    <span key={i} className="text-xs font-semibold text-muted-foreground uppercase tracking-wide text-right first:text-left last:w-28">{h}</span>
                  ))}
                </div>
                {stock.map((item, i) => (
                  <div key={item.item_id}
                    className={cn(
                      "grid grid-cols-[1fr_110px_80px_120px_auto] gap-0 items-center px-4 py-3 hover:bg-muted/30 transition-colors",
                      i < stock.length - 1 && "border-b border-border"
                    )}>
                    <p className="text-sm font-medium truncate pr-2">{item.item_name}</p>
                    <p className="text-sm font-semibold text-right tabular-nums">{fmt(item.on_hand)}</p>
                    <p className="text-xs text-muted-foreground text-right">{item.unit ?? "—"}</p>
                    <p className="text-xs text-muted-foreground hidden sm:block text-right">
                      {item.last_movement ? formatDate(item.last_movement) : "—"}
                    </p>
                    <div className="flex justify-end gap-1.5 pl-3">
                      <Button size="sm" variant="ghost"
                        className="h-7 text-xs gap-1 shrink-0 text-muted-foreground hover:text-foreground px-2"
                        onClick={() => setAdjustItem(item)}
                        title="Adjust stock">
                        <SlidersHorizontal className="w-3 h-3" />
                      </Button>
                      {sites.length > 0 ? (
                        <Button size="sm" variant="outline"
                          className="h-7 text-xs gap-1 shrink-0"
                          onClick={() => setDispatchItem(item)}>
                          <ArrowRight className="w-3 h-3" />
                          <span className="hidden sm:inline">Dispatch</span>
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">No sites</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* C) Dispatch Queue */}
          <DispatchQueue mrs={mrs} />

          {/* E) Shortages */}
          <ShortageAlerts stock={stock} mrs={mrs} />

          {/* F) Transfer Requests */}
          <TransferRequestsPanel
            transfers={transfers}
            role={role ?? ""}
            onVote={async (id) => {
              try { await warehouseTransfersApi.castVote(id); await loadAll(); }
              catch (e: unknown) {
                const d = (e as { response?: { data?: { message?: string } } })?.response?.data;
                alert(d?.message ?? "Vote failed.");
              }
            }}
            onOverride={async (id) => {
              try { await warehouseTransfersApi.overrideApprove(id, "Owner override"); await loadAll(); }
              catch (e: unknown) {
                const d = (e as { response?: { data?: { message?: string } } })?.response?.data;
                alert(d?.message ?? "Override failed.");
              }
            }}
            onReject={async (id, reason) => {
              try { await warehouseTransfersApi.reject(id, reason); await loadAll(); }
              catch (e: unknown) {
                const d = (e as { response?: { data?: { message?: string } } })?.response?.data;
                alert(d?.message ?? "Reject failed.");
              }
            }}
          />

          {/* D) Movement History */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <button className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/30 transition-colors"
              onClick={toggleHist}>
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
                {histLoad && <RefreshCw className="w-3.5 h-3.5 animate-spin text-muted-foreground" />}
                {showHist ? <ChevronUp className="w-4 h-4 text-muted-foreground" />
                           : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
              </div>
            </button>

            {showHist && (
              <div className="border-t border-border">
                {histLoad ? (
                  <div className="px-4 py-3 space-y-2">
                    {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 rounded-lg" />)}
                  </div>
                ) : history.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center px-4 py-6">
                    No movements recorded yet.
                  </p>
                ) : (
                  <div className="px-4 py-2 max-h-80 overflow-y-auto divide-y divide-border/40">
                    {history.map(m => {
                      const isIn = m.quantity_in > 0;
                      const qty  = isIn ? m.quantity_in : m.quantity_out;
                      const label = MOVEMENT_LABEL[m.movement_type] ?? m.movement_type.replace(/_/g, " ");
                      return (
                        <div key={m.id} className="flex items-start justify-between py-2.5">
                          <div className="min-w-0">
                            <p className="text-sm font-medium truncate">{m.item_name}</p>
                            <p className="text-xs text-muted-foreground">
                              {label}{m.entered_by ? ` · ${m.entered_by}` : ""}{m.notes ? ` — ${m.notes}` : ""}
                            </p>
                          </div>
                          <div className="text-right shrink-0 ml-3">
                            <span className={cn("text-sm font-semibold", MOVEMENT_COLOR[m.movement_type] ?? "text-muted-foreground")}>
                              {isIn ? "+" : "−"}{fmt(qty)} {m.unit ?? ""}
                            </span>
                            <p className="text-xs text-muted-foreground">
                              {m.movement_date ? formatDate(m.movement_date) : "—"}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      {dispatchItem && (
        <DispatchModal
          projectId={projectId}
          item={dispatchItem}
          sites={sites}
          onClose={() => setDispatchItem(null)}
          onDone={loadAll}
        />
      )}
      {showReturn && (
        <ReturnModal
          projectId={projectId}
          sites={sites}
          onClose={() => setShowReturn(false)}
          onDone={loadAll}
        />
      )}
      {showAddMaterial && (
        <AddMaterialModal
          projectId={projectId}
          onClose={() => setShowAddMaterial(false)}
          onDone={loadAll}
        />
      )}
      {adjustItem && (
        <AdjustStockModal
          projectId={projectId}
          item={adjustItem}
          onClose={() => setAdjustItem(null)}
          onDone={loadAll}
        />
      )}
      {showTransfer && projectId && (
        <RequestTransferModal
          fromProjectId={projectId}
          projects={projects}
          stock={stock}
          onClose={() => setShowTransfer(false)}
          onDone={loadAll}
        />
      )}
    </div>
  );
}
