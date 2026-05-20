/**
 * SiteWarehouse — shows current on-hand stock for a site and allows
 * transferring items to individual lots.
 *
 * Stock flow:  Delivery → Site Warehouse → Lot
 */
import { useCallback, useEffect, useState } from "react";
import { Package, ArrowRight, RefreshCw, History, AlertTriangle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { warehouseApi, type WarehouseStockItem, type WarehouseMovement } from "@/api/warehouse";
import { lotsApi, type Lot } from "@/api/lots";
import { cn } from "@/lib/utils";

// ── Transfer modal ─────────────────────────────────────────────────────────────

function TransferModal({
  siteId,
  item,
  lots,
  onClose,
  onDone,
}: {
  siteId:  string;
  item:    WarehouseStockItem;
  lots:    Lot[];
  onClose: () => void;
  onDone:  () => void;
}) {
  const [lotId,    setLotId]    = useState(lots[0]?.id ?? "");
  const [quantity, setQuantity] = useState("");
  const [notes,    setNotes]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const handleTransfer = async () => {
    const qty = parseFloat(quantity);
    if (!lotId)          { setError("Select a lot."); return; }
    if (!qty || qty <= 0){ setError("Enter a valid quantity."); return; }
    if (qty > item.on_hand) { setError(`Only ${item.on_hand} ${item.unit ?? ""} available.`); return; }
    setLoading(true); setError("");
    try {
      await warehouseApi.transferToLot(siteId, item.item_id, lotId, qty, notes || undefined);
      onDone();
      onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Transfer failed.");
    } finally { setLoading(false); }
  };

  const selectedLot = lots.find(l => l.id === lotId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Transfer to Lot</h3>
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
                <option key={l.id} value={l.id}>Lot {l.lot_number}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">
              Quantity ({item.unit ?? "units"})
            </label>
            <input
              type="number"
              min="0.001"
              step="any"
              max={item.on_hand}
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
              type="text"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="e.g. For slab pour"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
        </div>

        {error && (
          <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>
        )}

        {quantity && parseFloat(quantity) > 0 && selectedLot && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/50 rounded-lg px-3 py-2">
            <span className="font-medium text-foreground">{parseFloat(quantity)} {item.unit ?? ""}</span>
            <ArrowRight className="w-3 h-3" />
            <span className="font-medium text-foreground">Lot {selectedLot.lot_number}</span>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <Button onClick={handleTransfer} disabled={loading} className="flex-1">
            {loading ? "Transferring…" : "Transfer"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── History drawer ─────────────────────────────────────────────────────────────

function HistoryRow({ m }: { m: WarehouseMovement }) {
  const isIn  = m.quantity_in  > 0;
  const qty   = isIn ? m.quantity_in : m.quantity_out;
  const label = isIn ? "Received" : m.movement_type === "TRANSFER_OUT" ? "Transferred out" : "Issued";
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
          {isIn ? "+" : "-"}{qty} {m.unit ?? ""}
        </span>
        <p className="text-xs text-muted-foreground">
          {m.movement_date ? new Date(m.movement_date).toLocaleDateString("en-ZA") : "—"}
        </p>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface Props {
  siteId:    string;
  projectId: string;
}

export function SiteWarehouse({ siteId, projectId }: Props) {
  const [stock,        setStock]        = useState<WarehouseStockItem[]>([]);
  const [lots,         setLots]         = useState<Lot[]>([]);
  const [history,      setHistory]      = useState<WarehouseMovement[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [showHistory,  setShowHistory]  = useState(false);
  const [histLoading,  setHistLoading]  = useState(false);
  const [transferItem, setTransferItem] = useState<WarehouseStockItem | null>(null);
  const [error,        setError]        = useState("");

  const loadStock = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [s, l] = await Promise.all([
        warehouseApi.getStock(siteId),
        lotsApi.list(projectId),
      ]);
      setStock(s);
      setLots(l.filter(lot => lot.site_id === siteId));
    } catch {
      setError("Failed to load site warehouse.");
    } finally { setLoading(false); }
  }, [siteId, projectId]);

  const loadHistory = useCallback(async () => {
    setHistLoading(true);
    try {
      const h = await warehouseApi.getHistory(siteId);
      setHistory(h);
    } catch { /* silent */ }
    finally { setHistLoading(false); }
  }, [siteId]);

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
          <span className="font-semibold text-sm">Site Warehouse</span>
          {stock.length > 0 && (
            <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
              {stock.length} item{stock.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
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
          <AlertTriangle className="w-4 h-4 shrink-0" />{error}
        </div>
      )}

      {/* Stock list */}
      {loading ? (
        <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} className="h-14 rounded-xl" />)}</div>
      ) : stock.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-8 text-center">
          <Package className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No stock in site warehouse.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Stock arrives when deliveries are received against this site.
          </p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {stock.map((item, i) => (
            <div
              key={item.item_id}
              className={cn(
                "flex items-center gap-4 px-4 py-3 transition-colors",
                i < stock.length - 1 && "border-b border-border",
                "hover:bg-muted/30"
              )}
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{item.item_name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  On hand: <span className="font-semibold text-foreground">{item.on_hand} {item.unit ?? ""}</span>
                  {item.last_movement && (
                    <span className="ml-2">
                      · Last movement: {new Date(item.last_movement).toLocaleDateString("en-ZA")}
                    </span>
                  )}
                </p>
              </div>

              {/* Transfer button — only if lots are available */}
              {lots.length > 0 ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="shrink-0 gap-1.5 h-8 text-xs"
                  onClick={() => setTransferItem(item)}
                >
                  <ArrowRight className="w-3 h-3" />
                  Transfer to Lot
                </Button>
              ) : (
                <span className="text-xs text-muted-foreground shrink-0">No lots in site</span>
              )}
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
            {histLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-muted-foreground" />}
          </div>
          <div className="px-4 py-2 max-h-64 overflow-y-auto">
            {history.length === 0 ? (
              <p className="text-xs text-muted-foreground text-center py-4">No movements recorded yet.</p>
            ) : (
              history.map(m => <HistoryRow key={m.id} m={m} />)
            )}
          </div>
        </div>
      )}

      {/* Transfer modal */}
      {transferItem && (
        <TransferModal
          siteId={siteId}
          item={transferItem}
          lots={lots}
          onClose={() => setTransferItem(null)}
          onDone={loadStock}
        />
      )}
    </div>
  );
}
