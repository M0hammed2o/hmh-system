/**
 * Main Warehouse — company-wide central stock.
 *
 * Stock flow:
 *   Delivery → Main Warehouse → Project Warehouse → Lot/Unit → Milestone usage
 *
 * This page (admin/office only):
 *   • See what's on hand in the company Main Warehouse
 *   • Dispatch to Project Warehouse (per project)
 *   • Receive returns from Project Warehouses
 *   • Browse movement history
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Package, ArrowRight, ArrowLeft, RefreshCw, History,
  AlertTriangle, X, ChevronDown, ChevronUp, Warehouse,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import {
  warehouseApi,
  type WarehouseStockItem,
  type WarehouseMovement,
} from "@/api/warehouse";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n % 1 === 0 ? String(n) : n.toFixed(2);
}

const MOVEMENT_LABEL: Record<string, string> = {
  DELIVERY_RECEIVED: "Delivery received",
  TRANSFER_OUT:      "Dispatched to site",
  TRANSFER_IN:       "Received (return)",
  OPENING_BALANCE:   "Opening balance",
  ADJUSTMENT_ADD:    "Adjustment +",
  ADJUSTMENT_SUBTRACT: "Adjustment −",
  RETURN_TO_STORE:   "Return to store",
};

const MOVEMENT_COLOR: Record<string, string> = {
  TRANSFER_IN:       "text-green-600",
  DELIVERY_RECEIVED: "text-green-600",
  OPENING_BALANCE:   "text-green-600",
  ADJUSTMENT_ADD:    "text-green-600",
  TRANSFER_OUT:      "text-amber-600",
  ADJUSTMENT_SUBTRACT: "text-destructive",
};

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

  const selectedSite = sites.find(s => s.id === siteId);

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!siteId)          { setError("Select a site."); return; }
    if (!qty || qty <= 0) { setError("Enter a valid quantity."); return; }
    if (qty > item.on_hand) { setError(`Only ${item.on_hand} ${item.unit ?? ""} available.`); return; }
    setLoading(true); setError("");
    try {
      await warehouseApi.transferToSite(projectId, item.item_id, siteId, qty, notes || undefined);
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
          <h3 className="font-semibold text-base">Dispatch to Site</h3>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        {/* Item summary */}
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
            <label className="text-xs text-muted-foreground block mb-1">Destination site</label>
            <select
              value={siteId}
              onChange={e => setSiteId(e.target.value)}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
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
          <Button onClick={submit} disabled={loading} className="flex-1">
            {loading ? "Dispatching…" : "Dispatch"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Return-from-Site Modal ────────────────────────────────────────────────────

function ReturnModal({
  projectId,
  sites,
  onClose,
  onDone,
}: {
  projectId: string;
  sites:     Site[];
  onClose:   () => void;
  onDone:    () => void;
}) {
  const [siteId,     setSiteId]     = useState(sites[0]?.id ?? "");
  const [siteStock,  setSiteStock]  = useState<WarehouseStockItem[]>([]);
  const [stockLoading, setStockLoading] = useState(false);
  const [itemId,     setItemId]     = useState("");
  const [quantity,   setQuantity]   = useState("");
  const [notes,      setNotes]      = useState("");
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");

  // Load site stock when site changes
  useEffect(() => {
    if (!siteId) return;
    setStockLoading(true);
    setItemId("");
    warehouseApi.getStock(siteId)
      .then(s => { setSiteStock(s); if (s.length > 0) setItemId(s[0].item_id); })
      .catch(() => setSiteStock([]))
      .finally(() => setStockLoading(false));
  }, [siteId]);

  const selectedItem = siteStock.find(s => s.item_id === itemId);
  const selectedSite = sites.find(s => s.id === siteId);

  const submit = async () => {
    const qty = parseFloat(quantity);
    if (!siteId)          { setError("Select a site."); return; }
    if (!itemId)          { setError("Select an item."); return; }
    if (!qty || qty <= 0) { setError("Enter a valid quantity."); return; }
    if (selectedItem && qty > selectedItem.on_hand) {
      setError(`Only ${fmt(selectedItem.on_hand)} ${selectedItem.unit ?? ""} available at ${selectedSite?.name}.`);
      return;
    }
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
          {/* Site selector */}
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Source site</label>
            <select
              value={siteId}
              onChange={e => setSiteId(e.target.value)}
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>

          {/* Item selector — populated from site stock */}
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Item to return</label>
            {stockLoading ? (
              <div className="h-10 rounded-md border border-input bg-muted animate-pulse" />
            ) : siteStock.length === 0 ? (
              <p className="text-xs text-muted-foreground bg-muted/40 rounded-md px-3 py-2.5">
                No stock in {selectedSite?.name ?? "this site"}'s warehouse.
              </p>
            ) : (
              <select
                value={itemId}
                onChange={e => setItemId(e.target.value)}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
              >
                {siteStock.map(s => (
                  <option key={s.item_id} value={s.item_id}>
                    {s.item_name} — {fmt(s.on_hand)} {s.unit ?? ""} available
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Quantity */}
          {selectedItem && (
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                Quantity to return ({selectedItem.unit ?? "units"})
              </label>
              <input
                type="number" min="0.001" step="any" max={selectedItem.on_hand}
                value={quantity}
                onChange={e => setQuantity(e.target.value)}
                placeholder={`Max ${fmt(selectedItem.on_hand)}`}
                className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
                autoFocus
              />
            </div>
          )}

          {/* Notes */}
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Notes (optional)</label>
            <input
              type="text" value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="e.g. Excess from completed slab"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
        </div>

        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

        {quantity && parseFloat(quantity) > 0 && selectedItem && selectedSite && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
            <span className="font-medium text-foreground">{selectedSite.name}</span>
            <ArrowLeft className="w-3 h-3" />
            <span className="font-medium text-foreground">{fmt(parseFloat(quantity))} {selectedItem.unit ?? ""}</span>
            <span className="text-muted-foreground">→ Main Warehouse</span>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <Button
            onClick={submit}
            disabled={loading || siteStock.length === 0 || !itemId}
            className="flex-1"
          >
            {loading ? "Processing…" : "Receive Return"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── History row ───────────────────────────────────────────────────────────────

function HistoryRow({ m }: { m: WarehouseMovement }) {
  const isIn = m.quantity_in > 0;
  const qty  = isIn ? m.quantity_in : m.quantity_out;
  const label = MOVEMENT_LABEL[m.movement_type] ?? m.movement_type.replace(/_/g, " ");
  const color = MOVEMENT_COLOR[m.movement_type] ?? "text-muted-foreground";

  return (
    <div className="flex items-start justify-between py-2.5 border-b border-border/40 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate">{m.item_name}</p>
        <p className="text-xs text-muted-foreground">
          {label}
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
  const [projects,  setProjects]  = useState<Project[]>([]);
  const [sites,     setSites]     = useState<Site[]>([]);
  const [projectId, setProjectId] = useState("");

  const [stock,    setStock]    = useState<WarehouseStockItem[]>([]);
  const [history,  setHistory]  = useState<WarehouseMovement[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [histLoading, setHistLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [error,    setError]    = useState("");

  // Modals
  const [dispatchItem, setDispatchItem] = useState<WarehouseStockItem | null>(null);
  const [showReturn,   setShowReturn]   = useState(false);

  // Load projects on mount
  useEffect(() => {
    projectsApi.list(1, 100, "ACTIVE").then(r => {
      setProjects(r.items);
      if (r.items.length > 0) setProjectId(r.items[0].id);
    }).catch(() => {});
  }, []);

  // Load sites when project changes
  useEffect(() => {
    if (!projectId) { setSites([]); return; }
    sitesApi.list(projectId).then(setSites).catch(() => setSites([]));
  }, [projectId]);

  // Load main warehouse stock
  const loadStock = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const s = await warehouseApi.getMainStock(projectId);
      setStock(s);
    } catch {
      setError("Failed to load main warehouse stock.");
    } finally { setLoading(false); }
  }, [projectId]);

  useEffect(() => { loadStock(); }, [loadStock]);

  // Load history lazily
  const loadHistory = useCallback(async () => {
    if (!projectId) return;
    setHistLoading(true);
    try {
      const h = await warehouseApi.getMainHistory(projectId, 100);
      setHistory(h);
    } catch { /* silent */ }
    finally { setHistLoading(false); }
  }, [projectId]);

  const toggleHistory = () => {
    setShowHistory(p => !p);
    if (!showHistory && history.length === 0) loadHistory();
  };

  const totalSkus     = stock.length;
  const totalOnHand   = stock.reduce((s, i) => s + i.on_hand, 0);
  const recentHistory = history.slice(0, 5);

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Main Warehouse"
        description="Central project stock — dispatch to sites, receive returns, track every movement."
        actions={
          projectId ? (
            <div className="flex gap-2">
              <Button
                size="sm" variant="outline"
                onClick={() => setShowReturn(true)}
                disabled={sites.length === 0}
              >
                <ArrowLeft className="w-4 h-4" />
                Receive Return
              </Button>
            </div>
          ) : undefined
        }
      />

      {/* Project selector */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={projectId}
          onChange={e => setProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[220px]"
        >
          <option value="">— Select project —</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button
          onClick={loadStock}
          disabled={loading}
          className="h-9 w-9 flex items-center justify-center rounded-md border border-input bg-background hover:bg-muted text-muted-foreground disabled:opacity-50 transition-colors"
          title="Refresh"
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />{error}
        </div>
      )}

      {/* KPI bar */}
      {!loading && projectId && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div className="bg-card border border-border rounded-xl p-4">
            <p className="text-xs text-muted-foreground">SKUs on hand</p>
            <p className="text-2xl font-bold mt-0.5">{totalSkus}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-4">
            <p className="text-xs text-muted-foreground">Total units</p>
            <p className="text-2xl font-bold mt-0.5">{fmt(totalOnHand)}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-4">
            <p className="text-xs text-muted-foreground">Sites</p>
            <p className="text-2xl font-bold mt-0.5">{sites.length}</p>
          </div>
        </div>
      )}

      {/* Stock table */}
      {!projectId ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">
          Select a project to view main warehouse stock.
        </div>
      ) : loading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-14 rounded-xl" />)}
        </div>
      ) : stock.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center space-y-2">
          <Warehouse className="w-10 h-10 text-muted-foreground mx-auto" />
          <p className="text-sm font-medium">Main warehouse is empty</p>
          <p className="text-xs text-muted-foreground">
            Stock arrives when deliveries are received with destination set to "Main Warehouse".
          </p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_120px_100px_140px_auto] gap-0 border-b border-border bg-muted/40 px-4 py-2.5">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Item</span>
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide text-right">On Hand</span>
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide text-right">Unit</span>
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide hidden sm:block">Last Movement</span>
            <span className="w-32" />
          </div>

          {stock.map((item, i) => (
            <div
              key={item.item_id}
              className={cn(
                "grid grid-cols-[1fr_120px_100px_140px_auto] gap-0 items-center px-4 py-3 transition-colors hover:bg-muted/30",
                i < stock.length - 1 && "border-b border-border"
              )}
            >
              <p className="text-sm font-medium truncate pr-3">{item.item_name}</p>
              <p className="text-sm font-semibold text-right tabular-nums">{fmt(item.on_hand)}</p>
              <p className="text-xs text-muted-foreground text-right">{item.unit ?? "—"}</p>
              <p className="text-xs text-muted-foreground hidden sm:block">
                {item.last_movement ? formatDate(item.last_movement) : "—"}
              </p>
              <div className="flex justify-end">
                {sites.length > 0 ? (
                  <Button
                    size="sm" variant="outline"
                    className="h-8 text-xs gap-1.5 shrink-0"
                    onClick={() => setDispatchItem(item)}
                  >
                    <ArrowRight className="w-3 h-3" />
                    <span className="hidden sm:inline">Dispatch to</span> Site
                  </Button>
                ) : (
                  <span className="text-xs text-muted-foreground">No sites</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Movement history */}
      {projectId && (
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
      )}

      {/* Dispatch modal */}
      {dispatchItem && (
        <DispatchModal
          projectId={projectId}
          item={dispatchItem}
          sites={sites}
          onClose={() => setDispatchItem(null)}
          onDone={loadStock}
        />
      )}

      {/* Return modal */}
      {showReturn && (
        <ReturnModal
          projectId={projectId}
          sites={sites}
          onClose={() => setShowReturn(false)}
          onDone={loadStock}
        />
      )}
    </div>
  );
}
