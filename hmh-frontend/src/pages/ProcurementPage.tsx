/**
 * Procurement Page — MR → Approve → PO → Email workflow.
 */
import { useEffect, useState, useCallback } from "react";
import { WriteGuard } from "@/components/shared/WriteGuard";
import {
  Plus, Check, X, ChevronRight, AlertTriangle, Mail,
  MailCheck, RefreshCw, FileText, ShoppingCart, Warehouse, ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { projectsApi, type Project } from "@/api/projects";
import {
  procurementApi,
  type MaterialRequest, type MRCreate, type MRItemCreate,
  type MRQuote, type PurchaseOrder, type MRPriority, type DeliveryDestination,
} from "@/api/procurement";
import { warehouseApi, type WarehouseStockItem } from "@/api/warehouse";
import { cn } from "@/lib/utils";
import client from "@/api/client";
import { EmailDraftModal } from "@/components/EmailDraftModal";

/** Human-readable labels for delivery_destination values. */
const DEST_LABEL: Record<DeliveryDestination, string> = {
  SITE_STORE:      "Project Warehouse",
  MAIN_WAREHOUSE:  "Main Warehouse (bulk)",
  LOT:             "Direct to Lot",
};

function timeAgo(iso: string) {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const STATUS_BADGE: Record<string, "default" | "secondary" | "outline" | "destructive" | "success"> = {
  DRAFT: "outline", SUBMITTED: "secondary", PENDING_APPROVAL: "secondary",
  APPROVED: "success", REJECTED: "destructive", CONVERTED_TO_PO: "default",
  ORDERED: "default", PARTIALLY_RECEIVED: "secondary", RECEIVED: "success", CLOSED: "outline",
};

const PRIORITY_COLOR: Record<MRPriority, string> = {
  URGENT: "text-red-500 bg-red-500/10",
  HIGH: "text-amber-500 bg-amber-500/10",
  NORMAL: "text-blue-500 bg-blue-500/10",
  LOW: "text-muted-foreground bg-muted",
};

interface Site { id: string; name: string; }
interface Supplier { id: string; name: string; email: string | null; }

// ── Create MR Modal ───────────────────────────────────────────────────────────

function CreateMRModal({ projectId, sites, onClose, onCreated }: {
  projectId: string; sites: Site[]; onClose: () => void; onCreated: () => void;
}) {
  const [siteId, setSiteId] = useState(sites[0]?.id || "");
  const [priority, setPriority] = useState<MRPriority>("NORMAL");
  const [destination, setDestination] = useState<DeliveryDestination>("SITE_STORE");
  const [notes, setNotes] = useState("");
  const [neededBy, setNeededBy] = useState("");
  const [items, setItems] = useState<MRItemCreate[]>([{ description: "", requested_quantity: 1, unit: "" }]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const addItem = () => setItems([...items, { description: "", requested_quantity: 1, unit: "" }]);
  const removeItem = (i: number) => setItems(items.filter((_, idx) => idx !== i));
  const updateItem = (i: number, field: keyof MRItemCreate, value: string | number) =>
    setItems(items.map((it, idx) => idx === i ? { ...it, [field]: value } : it));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!siteId) return;
    setLoading(true); setError("");
    try {
      await procurementApi.createMR(projectId, {
        site_id: siteId, priority, delivery_destination: destination,
        notes: notes || undefined, needed_by_date: neededBy || undefined,
        items: items.filter((i) => i.description.trim()),
      } as MRCreate);
      onCreated(); onClose();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-t-2xl sm:rounded-2xl w-full sm:max-w-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border shrink-0">
          <h2 className="text-base font-semibold">New Material Request</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>
        <form onSubmit={submit} className="flex-1 overflow-y-auto p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Site *</Label>
              <select value={siteId} onChange={(e) => setSiteId(e.target.value)} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" required>
                {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>Priority</Label>
              <select value={priority} onChange={(e) => setPriority(e.target.value as MRPriority)} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
                {(["URGENT", "HIGH", "NORMAL", "LOW"] as MRPriority[]).map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Delivery Destination</Label>
              <select value={destination} onChange={(e) => setDestination(e.target.value as DeliveryDestination)} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
                <option value="SITE_STORE">Project Warehouse (from supplier)</option>
                <option value="MAIN_WAREHOUSE">Main Warehouse (bulk purchase only)</option>
                <option value="LOT">Direct to Lot</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>Needed By</Label>
              <Input type="date" value={neededBy} onChange={(e) => setNeededBy(e.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Notes</Label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Reason or additional info" />
          </div>
          <div className="space-y-2">
            <Label>Items *</Label>
            {items.map((item, i) => (
              <div key={i} className="grid grid-cols-[1fr_80px_60px_20px] gap-2 items-center">
                <Input value={item.description} onChange={(e) => updateItem(i, "description", e.target.value)} placeholder="Description *" className="h-8 text-sm" />
                <Input type="number" min="0.01" step="any" value={item.requested_quantity} onChange={(e) => updateItem(i, "requested_quantity", parseFloat(e.target.value) || 1)} className="h-8 text-sm" />
                <Input value={item.unit || ""} onChange={(e) => updateItem(i, "unit", e.target.value)} placeholder="Unit" className="h-8 text-sm" />
                {items.length > 1 && <button type="button" onClick={() => removeItem(i)} className="text-muted-foreground hover:text-destructive"><X className="w-3.5 h-3.5" /></button>}
              </div>
            ))}
            <button type="button" onClick={addItem} className="text-xs text-primary hover:underline flex items-center gap-1"><Plus className="w-3 h-3" />Add item</button>
          </div>
          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
        </form>
        <div className="px-5 pb-5 pt-3 border-t border-border shrink-0 flex gap-2">
          <Button disabled={loading} onClick={submit} className="flex-1">{loading ? "Creating…" : "Create Request"}</Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── MR Detail Modal ───────────────────────────────────────────────────────────

function MRDetailModal({ mr, suppliers, onClose, onUpdated }: {
  mr: MaterialRequest; suppliers: Supplier[]; onClose: () => void; onUpdated: () => void;
}) {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [overBoqReason, setOverBoqReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [showConvert, setShowConvert] = useState(false);
  const [convertSupplierId, setConvertSupplierId] = useState(suppliers[0]?.id || "");
  const [convertItems, setConvertItems] = useState(
    mr.items.map((i) => ({ description: i.description, quantity: i.requested_quantity, unit: i.unit || "", rate: 0, item_id: i.item_id }))
  );
  const [quotes, setQuotes] = useState<MRQuote[]>([]);
  const [showMREmail, setShowMREmail] = useState(false);

  // ── "Fulfil from Main Warehouse" section ────────────────────────────────
  const [showMainStock, setShowMainStock]           = useState(false);
  const [mainStock,     setMainStock]               = useState<WarehouseStockItem[]>([]);
  const [mainStockLoading, setMainStockLoading]     = useState(false);
  const [transferQty,   setTransferQty]             = useState<Record<string, string>>({});
  const [transferring,  setTransferring]            = useState<string | null>(null);

  const loadMainStock = async () => {
    setMainStockLoading(true);
    try {
      const s = await warehouseApi.getMainStock(mr.project_id);
      setMainStock(s);
      const initQty: Record<string, string> = {};
      s.forEach(item => { initQty[item.item_id] = ""; });
      setTransferQty(initQty);
    } catch { setMainStock([]); }
    finally { setMainStockLoading(false); }
  };

  const handleFulfilFromMain = async (item: WarehouseStockItem) => {
    const qty = parseFloat(transferQty[item.item_id] || "0");
    if (!qty || qty <= 0) return;
    if (qty > item.on_hand) return;
    setTransferring(item.item_id);
    try {
      await warehouseApi.transferToSite(mr.project_id, item.item_id, mr.site_id, qty,
        `Fulfilment for ${mr.request_number}`);
      setResult(`Transferred ${qty} ${item.unit ?? ""} of ${item.item_name} to project warehouse.`);
      loadMainStock();   // refresh stock
      onUpdated();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Transfer failed.");
    } finally { setTransferring(null); }
  };

  useEffect(() => { procurementApi.listQuotes(mr.id).then(setQuotes).catch(() => {}); }, [mr.id]);

  const act = async (fn: () => Promise<unknown>, label: string) => {
    setLoading(label); setError("");
    try { await fn(); setResult(`${label} successful.`); onUpdated(); }
    catch (err: unknown) {
      const d = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data;
      setError(d?.message || d?.detail || "Action failed.");
    }
    finally { setLoading(null); }
  };

  const handleConvert = async () => {
    const supplierName = suppliers.find(s => s.id === convertSupplierId)?.name ?? "the supplier";
    const destLabel = mr.delivery_destination === "MAIN_WAREHOUSE"
      ? "Main Warehouse (bulk stock)"
      : "Site Warehouse";
    const confirmed = window.confirm(
      `Are you sure you want to place this order with ${supplierName}?\n\n` +
      `Destination: ${destLabel}\n\n` +
      `This will create a Purchase Order (PO) and notify your team that the order is being placed. ` +
      `This action cannot be undone without cancelling the PO.`
    );
    if (!confirmed) return;

    await act(async () => {
      const res = await procurementApi.convertToPO(
        mr.id, convertSupplierId,
        convertItems.map((i) => ({ description: i.description, quantity: i.quantity, unit: i.unit, rate: i.rate, item_id: i.item_id || undefined })),
      );
      setResult(`Purchase Order (PO) ${res.po_number} created. Order placed with ${supplierName}.`);
    }, "convert");
    setShowConvert(false);
  };

  const canApprove = ["SUBMITTED", "PENDING_APPROVAL"].includes(mr.status);
  const canConvert = mr.status === "APPROVED";

  return (
    <>
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg max-h-[85vh] overflow-y-auto animate-fade-in">
        <div className="sticky top-0 bg-card border-b border-border px-5 py-4 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="font-semibold">{mr.request_number}</h2>
              <Badge variant={STATUS_BADGE[mr.status] || "outline"} className="text-xs">{mr.status.replace(/_/g, " ")}</Badge>
              {mr.over_boq && <Badge variant="destructive" className="text-xs"><AlertTriangle className="w-3 h-3 mr-0.5" />Over BOQ</Badge>}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">{mr.priority} · {DEST_LABEL[mr.delivery_destination] ?? mr.delivery_destination} · {timeAgo(mr.created_at)}</p>
          </div>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* Items */}
          <div className="bg-muted/30 rounded-lg divide-y divide-border">
            {mr.items.map((item) => (
              <div key={item.id} className="flex items-center justify-between px-3 py-2.5">
                <span className="text-sm">{item.description || "Item"}</span>
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-medium">{item.requested_quantity} {item.unit || ""}</span>
                  {item.over_boq_quantity && item.over_boq_quantity > 0 && (
                    <span className="text-destructive">+{item.over_boq_quantity} over</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {mr.notes && <p className="text-sm text-muted-foreground bg-muted/30 rounded-lg px-3 py-2">{mr.notes}</p>}

          {/* ── Email status ── */}
          {mr.status === "APPROVED" && (
            <div className="bg-muted/30 rounded-lg px-3 py-3 space-y-1.5">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-muted-foreground">Supplier Email</p>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs gap-1"
                  disabled={loading === "email"}
                  onClick={() => act(async () => {
                    const { materialRequestsApi } = await import("@/api/materialRequests");
                    return materialRequestsApi.sendEmail(mr.id);
                  }, "email")}
                >
                  {loading === "email" ? "Sending…" : mr.email_log?.sent_at ? "Resend Email" : "Send Email"}
                </Button>
              </div>
              {mr.email_log ? (
                <div className="flex items-center gap-2 text-xs">
                  <span className={
                    mr.email_log.status === "SENT"      ? "text-green-600 font-medium" :
                    mr.email_log.status === "MOCK_SENT" ? "text-blue-600 font-medium"  :
                    "text-destructive font-medium"
                  }>
                    {mr.email_log.status === "MOCK_SENT" ? "MOCK SENT" : mr.email_log.status}
                  </span>
                  <span className="text-muted-foreground">→ {mr.email_log.sent_to_email}</span>
                  {mr.email_log.sent_at && (
                    <span className="text-muted-foreground">
                      · {new Date(mr.email_log.sent_at).toLocaleString()}
                    </span>
                  )}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No email sent yet.</p>
              )}
              {mr.email_log?.error_message && (
                <p className="text-xs text-destructive">{mr.email_log.error_message}</p>
              )}
            </div>
          )}

          {quotes.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-2">Quotes ({quotes.length})</p>
              <div className="space-y-1.5">
                {quotes.map((q) => (
                  <div key={q.id} className={cn("flex items-center justify-between px-3 py-2 rounded-lg border text-sm", q.is_selected ? "border-green-500/40 bg-green-500/5" : "border-border")}>
                    <span>{q.description}</span>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">R{q.unit_price.toFixed(2)}/{q.unit || "unit"}</span>
                      {q.is_selected && <Check className="w-3.5 h-3.5 text-green-500" />}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {mr.over_boq && canApprove && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 space-y-2">
              <p className="text-xs font-medium text-amber-600 dark:text-amber-400">⚠ Over BOQ — reason required to approve.</p>
              <Input value={overBoqReason} onChange={(e) => setOverBoqReason(e.target.value)} placeholder="Reason for approving over-BOQ request" className="text-sm h-8" />
            </div>
          )}

          {showReject && (
            <Input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="Rejection reason *" className="text-sm" autoFocus />
          )}

          {/* ── Fulfil from Main Warehouse (SITE_STORE requests only) ── */}
          {canConvert && mr.delivery_destination === "SITE_STORE" && (
            <div className="rounded-lg border border-border overflow-hidden">
              <button
                className="w-full flex items-center justify-between px-3 py-2.5 bg-muted/30 hover:bg-muted/50 transition-colors text-left"
                onClick={() => { setShowMainStock(p => !p); if (!showMainStock && mainStock.length === 0) loadMainStock(); }}
              >
                <div className="flex items-center gap-2">
                  <Warehouse className="w-4 h-4 text-primary" />
                  <span className="text-xs font-semibold">Fulfil from Main Warehouse</span>
                </div>
                <span className="text-xs text-muted-foreground">
                  {showMainStock ? "Hide" : "Check stock →"}
                </span>
              </button>

              {showMainStock && (
                <div className="p-3 space-y-2 border-t border-border">
                  {mainStockLoading ? (
                    <p className="text-xs text-muted-foreground">Loading main warehouse stock…</p>
                  ) : mainStock.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      Main warehouse has no stock for this project.
                      Use "Order from Supplier to Project Warehouse" below if stock is not available.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-xs text-muted-foreground">
                        Transfer items from Main Warehouse directly to this site.
                        No supplier order needed.
                      </p>
                      {mainStock.map(item => (
                        <div key={item.item_id} className="flex items-center gap-2 text-xs">
                          <div className="flex-1 min-w-0">
                            <span className="font-medium truncate">{item.item_name}</span>
                            <span className="text-muted-foreground ml-1">
                              ({item.on_hand} {item.unit ?? ""} available)
                            </span>
                          </div>
                          <input
                            type="number" min="0.001" step="any"
                            max={item.on_hand}
                            placeholder="qty"
                            value={transferQty[item.item_id] ?? ""}
                            onChange={e => setTransferQty(prev => ({ ...prev, [item.item_id]: e.target.value }))}
                            className="w-20 h-7 rounded border border-input bg-background px-2 text-xs text-right"
                          />
                          <Button
                            size="sm"
                            className="h-7 text-xs px-2 gap-1"
                            disabled={!transferQty[item.item_id] || parseFloat(transferQty[item.item_id]) <= 0
                                      || parseFloat(transferQty[item.item_id]) > item.on_hand
                                      || transferring === item.item_id}
                            onClick={() => handleFulfilFromMain(item)}
                          >
                            {transferring === item.item_id
                              ? <RefreshCw className="w-3 h-3 animate-spin" />
                              : <><ArrowRight className="w-3 h-3" />Transfer</>}
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {showConvert && (
            <div className="bg-muted/30 rounded-lg p-3 space-y-3 border border-primary/20">
              <div className="flex items-center gap-2">
                <ShoppingCart className="w-4 h-4 text-primary" />
                <p className="text-xs font-semibold">
                  {mr.delivery_destination === "MAIN_WAREHOUSE"
                    ? "Bulk Purchase to Main Warehouse"
                    : "Order from Supplier to Project Warehouse"}
                </p>
              </div>
              <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                ⚠ This will place an order with the supplier. Review rates before confirming.
              </p>
              <div className="space-y-1.5">
                <Label className="text-xs">Supplier *</Label>
                <select value={convertSupplierId} onChange={(e) => setConvertSupplierId(e.target.value)} className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs">
                  {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}{s.email ? ` (${s.email})` : ""}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Unit Rates (R excl. VAT)</Label>
                {convertItems.map((item, i) => (
                  <div key={i} className="grid grid-cols-[1fr_100px] gap-2 items-center">
                    <span className="text-xs bg-muted rounded px-2 py-1 truncate">{item.description} × {item.quantity}</span>
                    <Input type="number" min="0" step="0.01" value={item.rate} onChange={(e) => setConvertItems((prev) => prev.map((it, idx) => idx === i ? { ...it, rate: parseFloat(e.target.value) || 0 } : it))} placeholder="Rate" className="h-7 text-xs" />
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={handleConvert} disabled={loading === "convert" || !convertSupplierId} className="flex-1 h-8 text-xs bg-primary">
                  {loading === "convert" ? "Placing Order…" : "✓ Place Order (Create PO)"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setShowConvert(false)} className="h-8 text-xs">Cancel</Button>
              </div>
            </div>
          )}

          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
          {result && <p className="text-sm text-green-600 dark:text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2">{result}</p>}

          <div className="flex flex-wrap gap-2">
            <WriteGuard>
              {canApprove && <Button size="sm" onClick={() => act(() => procurementApi.approveMR(mr.id, overBoqReason || undefined), "approve")} disabled={loading !== null || (mr.over_boq && !overBoqReason.trim())} className="h-8 text-xs"><Check className="w-3.5 h-3.5 mr-1" />{loading === "approve" ? "Approving…" : "Approve"}</Button>}
              {["SUBMITTED", "PENDING_APPROVAL", "DRAFT"].includes(mr.status) && !showReject && <Button size="sm" variant="outline" onClick={() => setShowReject(true)} className="h-8 text-xs"><X className="w-3.5 h-3.5 mr-1" />Reject</Button>}
              {showReject && <Button size="sm" variant="destructive" onClick={() => act(() => procurementApi.rejectMR(mr.id, rejectReason), "reject")} disabled={!rejectReason.trim() || loading !== null} className="h-8 text-xs">{loading === "reject" ? "Rejecting…" : "Confirm Reject"}</Button>}
              {mr.status === "DRAFT" && <Button size="sm" variant="outline" onClick={() => act(() => procurementApi.submitMR(mr.id), "submit")} disabled={loading !== null} className="h-8 text-xs">{loading === "submit" ? "Submitting…" : "Submit"}</Button>}
              {canConvert && !showConvert && (
                <Button size="sm" variant="outline" onClick={() => setShowConvert(true)} className="h-8 text-xs">
                  <ShoppingCart className="w-3.5 h-3.5 mr-1" />
                  {mr.delivery_destination === "MAIN_WAREHOUSE"
                    ? "Bulk Purchase to Main Warehouse"
                    : "Order from Supplier to Project Warehouse"}
                </Button>
              )}
            </WriteGuard>
            {["APPROVED"].includes(mr.status) && (
              <Button size="sm" variant="outline" onClick={() => setShowMREmail(true)} className="h-8 text-xs">
                <Mail className="w-3.5 h-3.5 mr-1" />Email Supplier
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>

    {/* MR Supplier Enquiry email draft */}
    <EmailDraftModal
      open={showMREmail}
      onClose={() => setShowMREmail(false)}
      mode="mr"
      entityId={mr.id}
      title={`Email Supplier — ${mr.request_number}`}
    />
    </>
  );
}

// ── PO Detail Modal ───────────────────────────────────────────────────────────

function PODetailModal({ po, onClose, onUpdated }: { po: PurchaseOrder; onClose: () => void; onUpdated: () => void; }) {
  const [loading, setLoading] = useState<string | null>(null);
  const [emailResult, setEmailResult] = useState<{ sent_to: string; status: string; is_mock: boolean } | null>(null);
  const [showDeliveryCharge, setShowDeliveryCharge] = useState(false);
  const [deliveryChargeAmt, setDeliveryChargeAmt] = useState("");
  const [emailLog, setEmailLog] = useState<Array<{ sent_to: string; status: string; sent_at: string | null }>>([]);
  const [error, setError] = useState("");
  // Email draft
  const [draft, setDraft] = useState<{ exists: boolean; to_email?: string; subject?: string; body_html?: string } | null>(null);
  const [showDraft, setShowDraft] = useState(false);
  const [draftSubject, setDraftSubject] = useState("");
  const [draftTo, setDraftTo] = useState("");

  useEffect(() => { procurementApi.getEmailLog(po.id).then(setEmailLog).catch(() => {}); }, [po.id]);

  const handlePrepareDraft = async () => {
    setLoading("draft"); setError("");
    try {
      const res = await client.post<{ data: { to_email: string; subject: string; body_html: string } }>(
        `/purchase-orders/${po.id}/prepare-email`
      );
      const d = res.data.data;
      setDraft({ exists: true, to_email: d.to_email, subject: d.subject, body_html: d.body_html });
      setDraftSubject(d.subject);
      setDraftTo(d.to_email);
      setShowDraft(true);
    } catch (e: unknown) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to prepare draft.");
    } finally { setLoading(null); }
  };

  const handleApprove = async () => {
    setLoading("approve");
    try { await procurementApi.approvePO(po.id); onUpdated(); }
    catch (err: unknown) { setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed."); }
    finally { setLoading(null); }
  };

  const handleEmail = async () => {
    setLoading("email"); setError("");
    try { const r = await procurementApi.sendEmail(po.id); setEmailResult(r); onUpdated(); }
    catch (err: unknown) { setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed."); }
    finally { setLoading(null); }
  };

  const handleMarkSent = async () => {
    setLoading("marksent"); setError("");
    try {
      await client.post(`/purchase-orders/${po.id}/mark-sent`);
      onUpdated();
    }
    catch (err: unknown) { setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed."); }
    finally { setLoading(null); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg max-h-[85vh] overflow-y-auto animate-fade-in">
        <div className="sticky top-0 bg-card border-b border-border px-5 py-4 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2"><h2 className="font-semibold">{po.po_number}</h2><Badge variant={STATUS_BADGE[po.status] || "outline"} className="text-xs">{po.status.replace(/_/g, " ")}</Badge>{po.sent_at && <MailCheck className="w-4 h-4 text-green-500" />}</div>
            <p className="text-xs text-muted-foreground mt-0.5">Total: R{po.total_amount.toLocaleString()}</p>
          </div>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="bg-muted/30 rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-border bg-muted/50"><th className="text-left px-3 py-2 font-medium text-muted-foreground">Item</th><th className="text-right px-3 py-2 font-medium text-muted-foreground">Ordered</th><th className="text-right px-3 py-2 font-medium text-muted-foreground">Recv</th><th className="text-right px-3 py-2 font-medium text-muted-foreground">Total</th></tr></thead>
              <tbody>
                {po.order_items.map((item) => {
                  const outstanding = item.quantity_ordered - (item.quantity_received || 0);
                  return (
                    <tr key={item.id} className="border-b border-border last:border-0">
                      <td className="px-3 py-2">{item.description}</td>
                      <td className="px-3 py-2 text-right">{item.quantity_ordered} {item.unit || ""}</td>
                      <td className={cn("px-3 py-2 text-right", outstanding > 0 ? "text-amber-500" : "text-green-600 dark:text-green-400")}>{item.quantity_received || 0}{outstanding > 0 && <span className="text-muted-foreground ml-1">(-{outstanding.toFixed(1)})</span>}</td>
                      <td className="px-3 py-2 text-right font-medium">R{(item.line_total || 0).toLocaleString()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Delivery charge */}
          {["APPROVED", "DRAFT", "SUBMITTED"].includes(po.status) && !showDeliveryCharge && (
            <button
              className="text-xs text-primary hover:underline"
              onClick={() => setShowDeliveryCharge(true)}
            >
              + Add Supplier Delivery Charge
            </button>
          )}
          {showDeliveryCharge && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-2">
              <p className="text-xs font-semibold text-blue-800">Add Delivery Charge to PO</p>
              <div className="flex items-center gap-2">
                <label className="text-xs text-muted-foreground whitespace-nowrap">Amount (R)</label>
                <input
                  type="number" min="0" step="0.01"
                  value={deliveryChargeAmt}
                  onChange={e => setDeliveryChargeAmt(e.target.value)}
                  placeholder="e.g. 350.00"
                  className="flex-1 h-7 rounded border border-input bg-background px-2 text-xs"
                />
                <Button
                  size="sm"
                  className="h-7 text-xs"
                  disabled={!deliveryChargeAmt || loading === "delivery_charge"}
                  onClick={async () => {
                    setLoading("delivery_charge"); setError("");
                    try {
                      await client.post(`/purchase-orders/${po.id}/items`, {
                        description:      "Supplier Delivery Charge",
                        quantity_ordered: 1,
                        unit:             "service",
                        rate:             parseFloat(deliveryChargeAmt),
                      });
                      setDeliveryChargeAmt("");
                      setShowDeliveryCharge(false);
                      onUpdated();
                    } catch (e: unknown) {
                      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to add charge.");
                    } finally { setLoading(null); }
                  }}
                >
                  {loading === "delivery_charge" ? "Adding…" : "Add"}
                </Button>
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowDeliveryCharge(false)}>Cancel</Button>
              </div>
              <p className="text-[10px] text-blue-600">
                PO total will update. To reject delivery, use "Prepare Email Draft" and inform the supplier.
              </p>
            </div>
          )}

          {emailResult && (
            <div className={cn("rounded-lg p-3 text-sm border", emailResult.status === "sent" ? "bg-green-500/10 border-green-500/30 text-green-600 dark:text-green-400" : "bg-destructive/10 border-destructive/30 text-destructive")}>
              {emailResult.is_mock ? `Mock email stored — SMTP disabled. To: ${emailResult.sent_to}` : `Email sent to ${emailResult.sent_to}`}
            </div>
          )}

          {emailLog.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1.5">Email History</p>
              {emailLog.map((log, i) => (
                <div key={i} className="flex items-center justify-between text-xs py-1.5 border-b border-border last:border-0">
                  <span className="text-muted-foreground">{log.sent_to}</span>
                  <div className="flex items-center gap-2">
                    <span className={log.status === "sent" ? "text-green-600 dark:text-green-400" : "text-destructive"}>{log.status}</span>
                    {log.sent_at && <span className="text-muted-foreground">{timeAgo(log.sent_at)}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}

          {/* PO lifecycle: DRAFT → APPROVED → SENT */}
          <div className="text-xs text-muted-foreground bg-muted/30 rounded-lg px-3 py-2">
            Lifecycle: <span className="font-mono text-[10px]">DRAFT → APPROVED → SENT → PARTIALLY_RECEIVED / RECEIVED → MATCHED → PAID</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {["DRAFT", "SUBMITTED"].includes(po.status) && <Button size="sm" onClick={handleApprove} disabled={loading === "approve"} className="h-8 text-xs"><Check className="w-3.5 h-3.5 mr-1" />{loading === "approve" ? "Approving…" : "Approve Purchase Order (PO)"}</Button>}
            {["APPROVED", "SENT"].includes(po.status) && (
              <Button size="sm" variant="outline" onClick={() => setShowDraft(true)} className="h-8 text-xs">
                <Mail className="w-3.5 h-3.5 mr-1" />Email Supplier
              </Button>
            )}
            {["APPROVED"].includes(po.status) && !po.sent_at && (
              <Button size="sm" variant="outline" onClick={handleMarkSent} disabled={loading === "marksent"} className="h-8 text-xs">
                <MailCheck className="w-3.5 h-3.5 mr-1" />
                {loading === "marksent" ? "Marking…" : "Mark as Sent (Manual)"}
              </Button>
            )}
            {po.sent_at && <span className="text-xs text-green-600 flex items-center gap-1"><MailCheck className="w-3.5 h-3.5" />Order Placed — Sent {new Date(po.sent_at).toLocaleDateString()}</span>}
          </div>
        </div>
      </div>

      {/* PO email draft — full compose modal */}
      <EmailDraftModal
        open={showDraft}
        onClose={() => setShowDraft(false)}
        mode="po"
        entityId={po.id}
        title={`Email Supplier — ${po.po_number}`}
      />
    </div>
  );
}

// ── Capture External PO Modal ─────────────────────────────────────────────────

interface ExtPOItem { description: string; quantity: string; unit: string; rate: string; }
const blankExtItem = (): ExtPOItem => ({ description: "", quantity: "1", unit: "", rate: "0" });

function CaptureExternalPOModal({
  projectId, suppliers, sites, onClose, onDone,
}: {
  projectId: string; suppliers: Supplier[]; sites: Site[];
  onClose: () => void; onDone: () => void;
}) {
  const [supplierId,   setSupplierId]   = useState(suppliers[0]?.id ?? "");
  const [siteId,       setSiteId]       = useState("");
  const [extRef,       setExtRef]       = useState("");
  const [destination,  setDestination]  = useState<"SITE_STORE" | "MAIN_WAREHOUSE">("SITE_STORE");
  const [expDate,      setExpDate]      = useState("");
  const [notes,        setNotes]        = useState("");
  const [items,        setItems]        = useState<ExtPOItem[]>([blankExtItem()]);
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");

  const updateItem = (i: number, field: keyof ExtPOItem, val: string) =>
    setItems(prev => prev.map((row, idx) => idx === i ? { ...row, [field]: val } : row));

  const submit = async () => {
    const validItems = items.filter(i => i.description.trim() && parseFloat(i.quantity) > 0);
    if (!supplierId)          { setError("Select a supplier."); return; }
    if (validItems.length === 0) { setError("Add at least one item."); return; }
    setLoading(true); setError("");
    try {
      await client.post(`/projects/${projectId}/purchase-orders/capture`, {
        supplier_id:            supplierId,
        site_id:                siteId || null,
        external_reference:     extRef.trim() || null,
        delivery_destination:   destination,
        expected_delivery_date: expDate || null,
        notes:                  notes || null,
        items: validItems.map(i => ({
          description:       i.description.trim(),
          quantity_ordered:  parseFloat(i.quantity),
          unit:              i.unit.trim() || null,
          rate:              parseFloat(i.rate) || 0,
        })),
      });
      onDone();
      onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Failed to capture PO.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-t-2xl sm:rounded-2xl w-full sm:max-w-lg max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border shrink-0">
          <div>
            <h2 className="text-base font-semibold">Capture External Purchase Order</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Record a PO placed by phone, WhatsApp, email or handwritten form.
            </p>
          </div>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Supplier + Ref */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Supplier *</Label>
              <select value={supplierId} onChange={e => setSupplierId(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" required>
                {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>External PO / Ref Number</Label>
              <Input value={extRef} onChange={e => setExtRef(e.target.value)}
                placeholder="Supplier's PO ref" />
            </div>
          </div>

          {/* Destination + Site */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Delivery Destination</Label>
              <select value={destination} onChange={e => setDestination(e.target.value as "SITE_STORE" | "MAIN_WAREHOUSE")}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
                <option value="SITE_STORE">Project Warehouse</option>
                <option value="MAIN_WAREHOUSE">Main Warehouse (bulk)</option>
              </select>
            </div>
            {destination === "SITE_STORE" && (
              <div className="space-y-1.5">
                <Label>Site (optional)</Label>
                <select value={siteId} onChange={e => setSiteId(e.target.value)}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
                  <option value="">— Any site —</option>
                  {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            )}
          </div>

          {/* Expected date + notes */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Expected Delivery</Label>
              <Input type="date" value={expDate} onChange={e => setExpDate(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Notes</Label>
              <Input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Optional" />
            </div>
          </div>

          {/* Items */}
          <div className="space-y-2">
            <Label>Items *</Label>
            {items.map((item, i) => (
              <div key={i} className="grid grid-cols-[1fr_80px_60px_80px_18px] gap-2 items-center">
                <Input value={item.description}
                  onChange={e => updateItem(i, "description", e.target.value)}
                  placeholder="Description *" className="h-8 text-sm" />
                <Input type="number" min="0.01" step="any" value={item.quantity}
                  onChange={e => updateItem(i, "quantity", e.target.value)}
                  className="h-8 text-sm" />
                <Input value={item.unit} onChange={e => updateItem(i, "unit", e.target.value)}
                  placeholder="Unit" className="h-8 text-sm" />
                <Input type="number" min="0" step="0.01" value={item.rate}
                  onChange={e => updateItem(i, "rate", e.target.value)}
                  placeholder="Rate R" className="h-8 text-sm" />
                {items.length > 1 && (
                  <button type="button" onClick={() => setItems(p => p.filter((_, idx) => idx !== i))}
                    className="text-muted-foreground hover:text-destructive">
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
            <button type="button" onClick={() => setItems(p => [...p, blankExtItem()])}
              className="text-xs text-primary hover:underline flex items-center gap-1">
              <Plus className="w-3 h-3" />Add item
            </button>
          </div>

          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
        </div>

        <div className="px-5 pb-5 pt-3 border-t border-border shrink-0 flex gap-2">
          <Button disabled={loading} onClick={submit} className="flex-1">
            {loading ? "Capturing…" : "Capture External PO"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ProcurementPage() {
  const [tab, setTab] = useState<"mr" | "po">("mr");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [sites, setSites] = useState<Site[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [mrs, setMRs] = useState<MaterialRequest[]>([]);
  const [pos, setPOs] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showCaptureExternal, setShowCaptureExternal] = useState(false);
  const [selectedMR, setSelectedMR] = useState<MaterialRequest | null>(null);
  const [selectedPO, setSelectedPO] = useState<PurchaseOrder | null>(null);
  const [mrFilter, setMrFilter] = useState("ALL");

  useEffect(() => {
    projectsApi.list(1, 100).then((r) => {
      setProjects(r.items);
      if (r.items.length) setProjectId(r.items[0].id);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const loadData = useCallback(async () => {
    if (!projectId) return;
    const [mrData, poData] = await Promise.allSettled([
      procurementApi.listMRs(projectId),
      procurementApi.listPOs(projectId),
    ]);
    if (mrData.status === "fulfilled") setMRs(mrData.value);
    if (poData.status === "fulfilled") setPOs(poData.value);
    try {
      const [sitesRes, suppliersRes] = await Promise.all([
        client.get<{ data: Site[] }>(`/projects/${projectId}/sites/`),
        client.get<{ data: Supplier[] }>("/suppliers/"),
      ]);
      setSites(sitesRes.data.data || []);
      setSuppliers(suppliersRes.data.data || []);
    } catch { /* ignore */ }
  }, [projectId]);

  useEffect(() => { loadData(); }, [loadData]);

  const filteredMRs = mrFilter === "ALL" ? mrs : mrs.filter((m) => m.status === mrFilter);
  const pendingCount = mrs.filter((m) => ["SUBMITTED", "PENDING_APPROVAL"].includes(m.status)).length;
  const overBoqCount = mrs.filter((m) => m.over_boq && !["REJECTED", "CLOSED"].includes(m.status)).length;

  if (loading) return <div className="space-y-4">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>;

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Procurement</h1>
          <p className="text-sm text-muted-foreground">
            {pendingCount > 0 && <span className="text-amber-500 font-medium">{pendingCount} awaiting approval</span>}
            {pendingCount > 0 && overBoqCount > 0 && " · "}
            {overBoqCount > 0 && <span className="text-destructive font-medium">{overBoqCount} over BOQ</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="h-9 rounded-md border border-input bg-background px-3 text-sm max-w-[180px]">
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          {tab === "mr" && <Button size="sm" onClick={() => setShowCreate(true)}><Plus className="w-4 h-4" />New MR</Button>}
          {tab === "po" && <Button size="sm" variant="outline" onClick={() => setShowCaptureExternal(true)}><FileText className="w-4 h-4" />Capture External PO</Button>}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1">
        {(["mr", "po"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={cn("px-4 py-2 rounded-lg text-sm font-medium transition-colors", tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
            {t === "mr" ? `Material Requests (${mrs.length})` : `Purchase Orders (${pos.length})`}
          </button>
        ))}
      </div>

      {/* MR tab */}
      {tab === "mr" && (
        <div className="space-y-3">
          <div className="flex overflow-x-auto gap-1 pb-1">
            {["ALL", "DRAFT", "SUBMITTED", "PENDING_APPROVAL", "APPROVED", "REJECTED", "CONVERTED_TO_PO"].map((s) => (
              <button key={s} onClick={() => setMrFilter(s)} className={cn("shrink-0 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors", mrFilter === s ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
                {s.replace(/_/g, " ")}
              </button>
            ))}
          </div>
          {filteredMRs.length === 0 ? (
            <div className="bg-card border border-border rounded-xl p-10 text-center">
              <FileText className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">No material requests.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredMRs.map((mr) => (
                <button key={mr.id} onClick={() => setSelectedMR(mr)} className="w-full text-left bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-4 hover:bg-muted/30 active:scale-[0.99] transition-all">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm">{mr.request_number}</span>
                      <Badge variant={STATUS_BADGE[mr.status] || "outline"} className="text-xs">{mr.status.replace(/_/g, " ")}</Badge>
                      {mr.over_boq && <Badge variant="destructive" className="text-xs">Over BOQ</Badge>}
                      <span className={cn("text-[10px] font-medium rounded px-1.5 py-0.5", PRIORITY_COLOR[mr.priority])}>{mr.priority}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{mr.items.length} item{mr.items.length !== 1 ? "s" : ""} · {DEST_LABEL[mr.delivery_destination] ?? mr.delivery_destination} · {timeAgo(mr.created_at)}</p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* PO tab */}
      {tab === "po" && (
        <div className="space-y-2">
          {pos.length === 0 ? (
            <div className="bg-card border border-border rounded-xl p-10 text-center">
              <ShoppingCart className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">No purchase orders yet. Approve an MR and convert it.</p>
            </div>
          ) : (
            pos.map((po) => (
              <button key={po.id} onClick={() => setSelectedPO(po)} className="w-full text-left bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-4 hover:bg-muted/30 active:scale-[0.99] transition-all">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm">{po.po_number}</span>
                    <Badge variant={STATUS_BADGE[po.status] || "outline"} className="text-xs">{po.status.replace(/_/g, " ")}</Badge>
                    {po.sent_at && <MailCheck className="w-3.5 h-3.5 text-green-500" />}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">R{po.total_amount.toLocaleString()} · {po.order_items.length} items · {timeAgo(po.created_at)}</p>
                </div>
                <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
              </button>
            ))
          )}
        </div>
      )}

      {showCreate && <CreateMRModal projectId={projectId} sites={sites} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); loadData(); }} />}
      {showCaptureExternal && (
        <CaptureExternalPOModal
          projectId={projectId}
          suppliers={suppliers}
          sites={sites}
          onClose={() => setShowCaptureExternal(false)}
          onDone={() => { setShowCaptureExternal(false); loadData(); }}
        />
      )}
      {selectedMR && <MRDetailModal mr={selectedMR} suppliers={suppliers} onClose={() => setSelectedMR(null)} onUpdated={() => { loadData(); setSelectedMR(null); }} />}
      {selectedPO && <PODetailModal po={selectedPO} onClose={() => setSelectedPO(null)} onUpdated={() => { loadData(); setSelectedPO(null); }} />}
    </div>
  );
}
