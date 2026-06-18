/**
 * ProjectWarehouse — shows current Project Warehouse stock for a project
 * and allows transferring items to individual lots/units.
 *
 * Phase 3B: Warehouse ownership has moved from Site → Project.
 * Stock flow:  Delivery → Project Warehouse → Lot/Unit → Milestone Usage
 *
 * Uses /projects/{projectId}/warehouse/ endpoints (project-level, site_id=NULL).
 * The old /sites/{siteId}/warehouse/ endpoints remain as legacy aliases.
 */
import { useCallback, useEffect, useState } from "react";
import { Package, ArrowRight, RefreshCw, History, AlertTriangle, X, Plus, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  warehouseApi,
  type WarehouseStockItem,
  type WarehouseMovement,
} from "@/api/warehouse";
import { lotsApi, type Lot } from "@/api/lots";
import { ROLE_KEY } from "@/lib/constants";
import { cn } from "@/lib/utils";

// ── Transfer to Lot modal ─────────────────────────────────────────────────────

function TransferModal({
  projectId,
  item,
  lots,
  onClose,
  onDone,
}: {
  projectId: string;
  item:      WarehouseStockItem;
  lots:      Lot[];
  onClose:   () => void;
  onDone:    () => void;
}) {
  const [lotId,    setLotId]    = useState(lots[0]?.id ?? "");
  const [quantity, setQuantity] = useState("");
  const [notes,    setNotes]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const handleTransfer = async () => {
    const qty = parseFloat(quantity);
    if (!lotId)           { setError("Select a lot."); return; }
    if (!qty || qty <= 0) { setError("Enter a valid quantity."); return; }
    if (qty > item.on_hand) {
      setError(`Only ${item.on_hand} ${item.unit ?? ""} available.`);
      return;
    }
    setLoading(true); setError("");
    try {
      // Transfer from project warehouse to a lot within the same project
      await warehouseApi.transferToSite(
        projectId,
        item.item_id,
        lots.find(l => l.id === lotId)?.site_id ?? lotId, // site_id of the lot
        qty,
        notes || undefined,
      );
      onDone();
      onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Transfer failed.");
    } finally { setLoading(false); }
  };

  const selectedLot = lots.find(l => l.id === lotId);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Transfer to Lot / Unit</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 flex items-center gap-3">
          <Package className="w-4 h-4 text-primary shrink-0" />
          <div>
            <p className="font-medium text-sm">{item.item_name}</p>
            <p className="text-xs text-muted-foreground">
              Available: <strong>{item.on_hand} {item.unit ?? ""}</strong>
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Lot / Unit</label>
            <select
              value={lotId}
              onChange={e => setLotId(e.target.value)}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {lots.map(l => (
                <option key={l.id} value={l.id}>
                  {l.lot_number}{l.unit_type ? ` · ${l.unit_type}` : ""}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Quantity ({item.unit ?? "units"})
            </label>
            <input
              type="number" min="0.001" step="any" max={item.on_hand}
              value={quantity}
              onChange={e => setQuantity(e.target.value)}
              placeholder={`Max ${item.on_hand}`}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
              autoFocus
            />
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Notes (optional)</label>
            <input
              type="text" value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="e.g. For slab pour — Unit 12"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
        </div>

        {error && (
          <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {quantity && parseFloat(quantity) > 0 && selectedLot && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
            <span className="font-medium text-foreground">
              {parseFloat(quantity)} {item.unit ?? ""}
            </span>
            <ArrowRight className="w-3 h-3" />
            <span className="font-medium text-foreground">
              {selectedLot.lot_number}
              {selectedLot.unit_type ? ` · ${selectedLot.unit_type}` : ""}
            </span>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <Button onClick={handleTransfer} disabled={loading} className="flex-1">
            {loading ? "Transferring…" : "Transfer to Lot"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

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

const ADJUST_OPTIONS = [
  { value: "CORRECTION_ADD", label: "Correction (Add)",    dir: "in"  },
  { value: "RETURNED",       label: "Returned to stock",   dir: "in"  },
  { value: "OTHER_ADD",      label: "Other (Add)",         dir: "in"  },
  { value: "CORRECTION_SUB", label: "Correction (Remove)", dir: "out" },
  { value: "DAMAGED",        label: "Damaged",             dir: "out" },
  { value: "LOST",           label: "Lost",                dir: "out" },
  { value: "OTHER_SUB",      label: "Other (Remove)",      dir: "out" },
] as const;

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
              Current stock: <strong>{item.on_hand} {item.unit ?? ""}</strong>
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
            selected.dir === "in"
              ? "text-green-700 bg-green-50 dark:bg-green-950/20 dark:text-green-400"
              : "text-destructive bg-destructive/10",
          )}>
            <span>{selected.dir === "in" ? "+" : "−"}{qty} {item.unit ?? ""}</span>
            <span className="text-muted-foreground">→</span>
            <span>{newStock} {item.unit ?? ""} remaining</span>
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

// ── History row ───────────────────────────────────────────────────────────────

function HistoryRow({ m }: { m: WarehouseMovement }) {
  const isIn  = m.quantity_in > 0;
  const qty   = isIn ? m.quantity_in : m.quantity_out;
  const label = isIn
    ? (m.movement_type === "TRANSFER_IN" ? "Received (transfer)" : "Delivery received")
    : (m.movement_type === "TRANSFER_OUT" ? "Dispatched to lot" : "Issued");

  return (
    <div className="flex items-start justify-between py-2.5 border-b border-border/40 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-medium truncate">{m.item_name}</p>
        <p className="text-xs text-muted-foreground">
          {label} · {m.entered_by ?? "System"}
          {m.notes ? ` — ${m.notes}` : ""}
        </p>
      </div>
      <div className="text-right shrink-0 ml-3">
        <span className={cn("text-sm font-semibold", isIn ? "text-green-600" : "text-amber-600")}>
          {isIn ? "+" : "−"}{qty} {m.unit ?? ""}
        </span>
        <p className="text-xs text-muted-foreground">
          {m.movement_date
            ? new Date(m.movement_date).toLocaleDateString("en-ZA")
            : "—"}
        </p>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  projectId: string;
  siteId?:   string;   // kept for backward compat — not used for warehouse queries
}

export function ProjectWarehouse({ projectId, siteId }: Props) {
  const userRole    = localStorage.getItem(ROLE_KEY) || "";
  const canTransfer = userRole !== "READ_ONLY";

  const [stock,           setStock]           = useState<WarehouseStockItem[]>([]);
  const [lots,            setLots]            = useState<Lot[]>([]);
  const [history,         setHistory]         = useState<WarehouseMovement[]>([]);
  const [loading,         setLoading]         = useState(true);
  const [showHistory,     setShowHistory]     = useState(false);
  const [histLoading,     setHistLoading]     = useState(false);
  const [transferItem,    setTransferItem]    = useState<WarehouseStockItem | null>(null);
  const [showAddMaterial, setShowAddMaterial] = useState(false);
  const [adjustItem,      setAdjustItem]      = useState<WarehouseStockItem | null>(null);
  const [error,           setError]           = useState("");

  const loadStock = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [s, l] = await Promise.all([
        warehouseApi.getMainStock(projectId),   // Project Warehouse = site_id=NULL
        lotsApi.list(projectId),
      ]);
      setStock(s);
      setLots(l);
    } catch {
      setError("Failed to load project warehouse.");
    } finally { setLoading(false); }
  }, [projectId]);

  const loadHistory = useCallback(async () => {
    setHistLoading(true);
    try {
      const h = await warehouseApi.getMainHistory(projectId);
      setHistory(h);
    } catch { /* silent */ }
    finally { setHistLoading(false); }
  }, [projectId]);

  useEffect(() => { loadStock(); }, [loadStock]);

  const toggleHistory = () => {
    setShowHistory(p => !p);
    if (!showHistory && history.length === 0) loadHistory();
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Package className="w-4 h-4 text-primary" />
          <span className="font-semibold text-sm">Project Warehouse</span>
          {stock.length > 0 && (
            <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
              {stock.length} item{stock.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {canTransfer && (
            <button
              onClick={() => setShowAddMaterial(true)}
              className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 transition-colors px-2 py-1 rounded-lg hover:bg-primary/10 border border-primary/20"
              title="Add material to warehouse"
            >
              <Plus className="w-3.5 h-3.5" />
              Add
            </button>
          )}
          <button
            onClick={toggleHistory}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded-lg hover:bg-muted"
          >
            <History className="w-3.5 h-3.5" />
            History
          </button>
          <button
            onClick={loadStock}
            disabled={loading}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Refresh"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Stock list */}
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-14 rounded-xl" />)}
        </div>
      ) : stock.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-8 text-center">
          <Package className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No stock in project warehouse.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Stock arrives when deliveries are received for this project.
          </p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {stock.map((item, i) => (
            <div
              key={item.item_id}
              className={cn(
                "flex items-center gap-4 px-4 py-3 transition-colors hover:bg-muted/30",
                i < stock.length - 1 && "border-b border-border",
              )}
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{item.item_name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  On hand:{" "}
                  <span className="font-semibold text-foreground">
                    {item.on_hand} {item.unit ?? ""}
                  </span>
                  {item.last_movement && (
                    <span className="ml-2">
                      · Last movement:{" "}
                      {new Date(item.last_movement).toLocaleDateString("en-ZA")}
                    </span>
                  )}
                </p>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                {canTransfer && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 text-xs gap-1 text-muted-foreground hover:text-foreground px-2"
                    onClick={() => setAdjustItem(item)}
                    title="Adjust stock"
                  >
                    <SlidersHorizontal className="w-3 h-3" />
                  </Button>
                )}
                {canTransfer && lots.length > 0 ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5 h-8 text-xs"
                    onClick={() => setTransferItem(item)}
                  >
                    <ArrowRight className="w-3 h-3" />
                    To Lot
                  </Button>
                ) : lots.length === 0 ? (
                  <span className="text-xs text-muted-foreground">No lots</span>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Movement history */}
      {showHistory && (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center justify-between">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Warehouse History
            </span>
            {histLoading && (
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
            )}
          </div>
          <div className="px-4 py-2 max-h-64 overflow-y-auto">
            {history.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">
                No movements recorded yet.
              </p>
            ) : (
              history.map(m => <HistoryRow key={m.id} m={m} />)
            )}
          </div>
        </div>
      )}

      {/* Transfer modal */}
      {transferItem && (
        <TransferModal
          projectId={projectId}
          item={transferItem}
          lots={lots}
          onClose={() => setTransferItem(null)}
          onDone={loadStock}
        />
      )}

      {/* Add Material modal */}
      {showAddMaterial && (
        <AddMaterialModal
          projectId={projectId}
          onClose={() => setShowAddMaterial(false)}
          onDone={loadStock}
        />
      )}

      {/* Adjust Stock modal */}
      {adjustItem && (
        <AdjustStockModal
          projectId={projectId}
          item={adjustItem}
          onClose={() => setAdjustItem(null)}
          onDone={loadStock}
        />
      )}
    </div>
  );
}

/**
 * Backward-compatibility re-export.
 * Code still importing SiteWarehouse gets the ProjectWarehouse implementation.
 * @deprecated Use ProjectWarehouse directly.
 */
export { ProjectWarehouse as SiteWarehouse };
