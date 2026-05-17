/**
 * Invoice Reconciliation — Proof Pack screen.
 * Accounting sees: Invoice + PO + Email Log + Delivery Note + Signature + Match Result.
 * One screen. One approval decision.
 */
import { useEffect, useState } from "react";
import {
  CheckCircle2, AlertTriangle, X, ExternalLink, FileText,
  Mail, Truck, ArrowLeft, Check, Download,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import client from "@/api/client";
import { API_BASE } from "@/lib/constants";

// Resolve a stored file path (/uploads/...) to a full backend URL
const SERVER_BASE = API_BASE.replace(/\/api\/v1\/?$/, "");
function fileUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  if (path.startsWith("http")) return path;
  return `${SERVER_BASE}${path}`;
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface ProofPack {
  invoice_id: string;
  project_id: string | null;
  invoice_number: string;
  invoice_date: string | null;
  due_date: string | null;
  total_amount: number;
  vat_amount: number;
  subtotal_amount: number;
  invoice_status: string;
  invoice_notes: string | null;

  supplier_name: string | null;
  supplier_email: string | null;
  supplier_vat: string | null;

  po_number: string | null;
  po_id: string | null;
  po_date: string | null;
  po_expected_delivery: string | null;
  po_items: Array<{
    description: string;
    quantity_ordered: number;
    quantity_received: number;
    unit: string | null;
    rate: number;
    line_total: number;
  }>;

  email_logs: Array<{
    sent_to: string;
    subject: string | null;
    status: string;
    sent_at: string | null;
    has_body: boolean;
  }>;

  delivery_number: string | null;
  delivery_id: string | null;
  delivery_date: string | null;
  delivery_note_image_url: string | null;
  delivery_note_download_url: string | null;
  signature_image_url: string | null;
  driver_name: string | null;
  driver_signature_url: string | null;
  signed_at: string | null;
  receiver_name: string | null;
  delivery_comments: string | null;

  match_status: string;
  quantity_match: boolean | null;
  amount_match: boolean | null;
  supplier_match: boolean | null;
  match_notes: string | null;
  checked_by: string | null;
  checked_at: string | null;
  reconciliation: {
    po_total: number | null;
    invoice_total: number | null;
    delivery_items: Array<{ description: string; quantity_expected: number; quantity_received: number }>;
    amount_variance: number | null;
    match_label: string;
  } | null;

  missing_delivery_note: boolean;
  missing_signature: boolean;
  is_matched: boolean;
}

interface InvoiceSummary {
  id: string;
  invoice_number: string;
  total_amount: number;
  status: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number) {
  return `R${Number(n).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}`;
}

const MATCH_BADGE: Record<string, { label: string; variant: "success" | "destructive" | "secondary" | "outline" }> = {
  MATCHED:               { label: "Matched",        variant: "success"     },
  QUANTITY_MISMATCH:     { label: "Variance",        variant: "destructive" },
  PRICE_MISMATCH:        { label: "Variance",        variant: "destructive" },
  MISMATCH:              { label: "Variance",        variant: "destructive" },
  SUPPLIER_MISMATCH:     { label: "Variance",        variant: "destructive" },
  PARTIALLY_MATCHED:     { label: "Partial Match",   variant: "secondary"   },
  MISSING_DELIVERY_NOTE: { label: "Partial Match",   variant: "secondary"   },
  MISSING_SIGNATURE:     { label: "Partial Match",   variant: "secondary"   },
  MISSING_INVOICE:       { label: "Partial Match",   variant: "secondary"   },
  AWAITING_APPROVAL:     { label: "Awaiting",        variant: "secondary"   },
  APPROVED_FOR_PAYMENT:  { label: "Approved",        variant: "success"     },
  UNLINKED:              { label: "Unlinked",        variant: "outline"     },
};

function ProofRow({
  label, value, url, ok, missing,
}: {
  label: string; value: string | null; url?: string | null; ok?: boolean; missing?: boolean;
}) {
  return (
    <div className="flex items-start justify-between py-2.5 border-b border-border last:border-0 gap-4">
      <span className="text-sm text-muted-foreground shrink-0">{label}</span>
      <div className="flex items-center gap-2 min-w-0">
        {missing ? (
          <span className="text-sm text-destructive italic flex items-center gap-1">
            <X className="w-3.5 h-3.5" />Missing
          </span>
        ) : ok !== undefined ? (
          ok
            ? <span className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" />{value}</span>
            : <span className="text-sm text-destructive flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" />{value}</span>
        ) : value ? (
          <span className="text-sm font-medium text-right truncate max-w-[200px]">{value}</span>
        ) : (
          <span className="text-sm text-muted-foreground italic">—</span>
        )}
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="w-3.5 h-3.5 text-muted-foreground hover:text-foreground shrink-0" />
          </a>
        )}
      </div>
    </div>
  );
}

// ── Proof Pack Detail ─────────────────────────────────────────────────────────

function ProofPackDetail({ proof, onBack, onApproved }: {
  proof: ProofPack; onBack: () => void; onApproved: () => void;
}) {
  const [approving,      setApproving]      = useState(false);
  const [matching,       setMatching]       = useState(false);
  const [matchNotes,     setMatchNotes]     = useState(proof.match_notes ?? "");
  const [manualDelivery, setManualDelivery] = useState(proof.delivery_id ?? "");
  const [manualPo,       setManualPo]       = useState(proof.po_id ?? "");
  const [error, setError] = useState("");
  const [matchMsg, setMatchMsg] = useState("");

  // Searchable options for deliveries and POs — loaded from the API
  const [deliveryOptions, setDeliveryOptions] = useState<Array<{ id: string; delivery_number: string | null; delivery_date: string; supplier_name: string | null }>>([]);
  const [poOptions,       setPoOptions]       = useState<Array<{ id: string; po_number: string; status: string }>>([]);

  useEffect(() => {
    // Load deliveries for the project linked to this invoice (via supplier_id)
    if (!proof.po_id && !proof.delivery_id) {
      // Try to get project_id from proof.po_id context — use supplier as hint
      // Load all recent deliveries and POs regardless
    }
    // Load all deliveries (limit 50 most recent)
    client.get<{ data: { items?: unknown[]; total?: number } | unknown[] }>("/deliveries/", { params: { limit: 50 } })
      .then(r => {
        const data = r.data.data;
        const list = Array.isArray(data) ? data : (data as { items?: unknown[] }).items ?? [];
        setDeliveryOptions(list as typeof deliveryOptions);
      })
      .catch(() => {});
  }, [proof.invoice_id, proof.po_id, proof.delivery_id]);

  const matchCfg = MATCH_BADGE[proof.match_status] || MATCH_BADGE.UNLINKED;
  const canApprove = ["SUBMITTED", "RECEIVED", "MATCHED"].includes(proof.invoice_status);

  const handleApprove = async () => {
    setApproving(true);
    try {
      await client.post(`/invoices/${proof.invoice_id}/approve-payment`);
      onApproved();
      onBack();
    } catch {
      setError("Failed to approve.");
    } finally { setApproving(false); }
  };

  const handleManualMatch = async (status: string) => {
    setMatching(true); setMatchMsg(""); setError("");
    try {
      await client.patch(`/invoices/${proof.invoice_id}/match`, {
        delivery_id:       manualDelivery || null,
        purchase_order_id: manualPo       || null,
        match_status:      status,
        notes:             matchNotes     || null,
      });
      setMatchMsg(`Marked as ${status === "MATCHED" ? "Matched" : status.replace(/_/g, " ")}.`);
    } catch {
      setError("Failed to save match. Try again.");
    } finally { setMatching(false); }
  };

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl">
      {/* Header */}
      <div className="flex items-start gap-3">
        <button onClick={onBack} className="p-2 rounded-lg hover:bg-muted mt-0.5">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-bold">#{proof.invoice_number}</h1>
            <Badge variant={matchCfg.variant}>{matchCfg.label}</Badge>
            <Badge variant="outline" className="text-xs">{proof.invoice_status}</Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">{proof.supplier_name}</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xl font-bold">{fmt(proof.total_amount)}</p>
          <p className="text-xs text-muted-foreground">incl. VAT</p>
        </div>
      </div>

      {/* Issues banner */}
      {(proof.missing_delivery_note || proof.missing_signature || !proof.is_matched) && (
        <div className="bg-destructive/10 border border-destructive/30 rounded-xl p-4 space-y-1">
          <p className="text-sm font-semibold text-destructive">Issues found — do not pay until resolved:</p>
          {proof.missing_delivery_note && <p className="text-xs text-destructive">• Delivery note image is missing</p>}
          {proof.missing_signature && <p className="text-xs text-destructive">• Receiver signature is missing</p>}
          {!proof.is_matched && proof.match_status !== "UNLINKED" && (
            <p className="text-xs text-destructive">• Invoice quantities/amounts do not match delivery</p>
          )}
        </div>
      )}

      {/* Invoice */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-muted-foreground" />
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Supplier Invoice</p>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs gap-1"
            onClick={() => window.print()}
            title="Print invoice details"
          >
            <Download className="w-3 h-3" />
            Print Invoice
          </Button>
        </div>
        <ProofRow label="Supplier" value={proof.supplier_name} />
        <ProofRow label="VAT Number" value={proof.supplier_vat} />
        <ProofRow label="Invoice Date" value={proof.invoice_date} />
        <ProofRow label="Due Date" value={proof.due_date} />
        <ProofRow label="Subtotal" value={fmt(proof.subtotal_amount)} />
        <ProofRow label="VAT" value={fmt(proof.vat_amount)} />
        <ProofRow label="Total" value={fmt(proof.total_amount)} />
        {proof.invoice_notes && <p className="text-xs text-muted-foreground mt-2 italic">{proof.invoice_notes}</p>}
      </div>

      {/* Purchase Order */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <FileText className="w-4 h-4 text-muted-foreground" />
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Purchase Order</p>
        </div>
        {proof.po_number ? (
          <>
            <ProofRow label="PO Number" value={proof.po_number} ok={true} />
            <ProofRow label="PO Date" value={proof.po_date} />
            <ProofRow label="Expected Delivery" value={proof.po_expected_delivery} />
            {proof.po_items.length > 0 && (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/50">
                      <th className="text-left px-2 py-1.5 font-medium text-muted-foreground">Item</th>
                      <th className="text-right px-2 py-1.5 font-medium text-muted-foreground">Ordered</th>
                      <th className="text-right px-2 py-1.5 font-medium text-muted-foreground">Received</th>
                      <th className="text-right px-2 py-1.5 font-medium text-muted-foreground">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {proof.po_items.map((item, i) => {
                      const outstanding = item.quantity_ordered - item.quantity_received;
                      return (
                        <tr key={i} className="border-b border-border last:border-0">
                          <td className="px-2 py-1.5">{item.description}</td>
                          <td className="px-2 py-1.5 text-right">{item.quantity_ordered} {item.unit || ""}</td>
                          <td className={cn("px-2 py-1.5 text-right", outstanding > 0 ? "text-amber-500" : "text-green-600 dark:text-green-400")}>
                            {item.quantity_received}
                            {outstanding > 0 && <span className="text-muted-foreground ml-1">(-{outstanding})</span>}
                          </td>
                          <td className="px-2 py-1.5 text-right font-medium">{fmt(item.line_total)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : (
          <ProofRow label="PO" value="Not linked" missing={true} />
        )}
      </div>

      {/* Supplier Email */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <Mail className="w-4 h-4 text-muted-foreground" />
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Supplier Email Log</p>
        </div>
        {proof.email_logs.length === 0 ? (
          <ProofRow label="Email" value="No email sent" missing />
        ) : (
          proof.email_logs.map((log, i) => (
            <div key={i} className="flex items-center justify-between py-2 border-b border-border last:border-0 text-sm">
              <span className="text-muted-foreground">{log.sent_to}</span>
              <div className="flex items-center gap-2">
                <span className={cn("text-xs font-medium", log.status === "sent" ? "text-green-600 dark:text-green-400" : "text-amber-500")}>
                  {log.status === "sent" ? "Sent" : log.status}
                </span>
                {log.sent_at && <span className="text-xs text-muted-foreground">{log.sent_at.slice(0, 10)}</span>}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Delivery Proof */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <Truck className="w-4 h-4 text-muted-foreground" />
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Delivery Proof</p>
          </div>
          {proof.delivery_note_image_url && (
            <div className="flex gap-1">
              <a href={fileUrl(proof.delivery_note_image_url)} target="_blank" rel="noopener noreferrer">
                <Button size="sm" variant="outline" className="h-7 text-xs gap-1">
                  <ExternalLink className="w-3 h-3" />
                  View Note
                </Button>
              </a>
              <a href={fileUrl(proof.delivery_note_download_url ?? proof.delivery_note_image_url)} download>
                <Button size="sm" variant="outline" className="h-7 text-xs gap-1">
                  <Download className="w-3 h-3" />
                  Download
                </Button>
              </a>
            </div>
          )}
        </div>
        <ProofRow label="Delivery Note #" value={proof.delivery_number} missing={!proof.delivery_number} />
        <ProofRow label="Delivery Date" value={proof.delivery_date} />
        <ProofRow label="Received By" value={proof.receiver_name} />
        {proof.driver_name && <ProofRow label="Driver" value={proof.driver_name} />}
        <ProofRow
          label="Delivery Note File"
          value={proof.delivery_note_image_url ? "Attached" : null}
          url={fileUrl(proof.delivery_note_image_url)}
          missing={proof.missing_delivery_note}
        />
        <ProofRow
          label="Receiver Signature"
          value={proof.signature_image_url ? "Captured" : null}
          url={fileUrl(proof.signature_image_url)}
          missing={proof.missing_signature}
        />
        {proof.driver_signature_url && (
          <ProofRow
            label="Driver Signature"
            value="Captured"
            url={fileUrl(proof.driver_signature_url)}
          />
        )}
        {proof.delivery_note_image_url && (
          <div className="mt-3">
            <img
              src={fileUrl(proof.delivery_note_image_url)}
              alt="Delivery note"
              className="max-h-48 rounded-lg border border-border object-contain w-full"
            />
          </div>
        )}
        {proof.delivery_comments && <p className="text-xs text-muted-foreground mt-2 italic">{proof.delivery_comments}</p>}
      </div>

      {/* Reconciliation comparison: PO vs Invoice vs Delivery */}
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <Check className="w-4 h-4 text-muted-foreground" />
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Reconciliation</p>
        </div>

        {/* Totals comparison */}
        <div className="overflow-x-auto mb-3">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left px-2 py-1.5 font-medium text-muted-foreground">Document</th>
                <th className="text-right px-2 py-1.5 font-medium text-muted-foreground">Total</th>
                <th className="text-right px-2 py-1.5 font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody>
              {proof.po_number && proof.reconciliation?.po_total != null && (
                <tr className="border-b border-border">
                  <td className="px-2 py-1.5 font-medium">Purchase Order</td>
                  <td className="px-2 py-1.5 text-right">{fmt(proof.reconciliation.po_total)}</td>
                  <td className="px-2 py-1.5 text-right"><Badge variant="outline" className="text-xs">Reference</Badge></td>
                </tr>
              )}
              <tr className="border-b border-border">
                <td className="px-2 py-1.5 font-medium">Supplier Invoice</td>
                <td className="px-2 py-1.5 text-right">{fmt(proof.total_amount)}</td>
                <td className="px-2 py-1.5 text-right">
                  <Badge variant={matchCfg.variant} className="text-xs">{matchCfg.label}</Badge>
                </td>
              </tr>
              {proof.delivery_id && (
                <tr className="border-b border-border last:border-0">
                  <td className="px-2 py-1.5 font-medium">Recorded Delivery</td>
                  <td className="px-2 py-1.5 text-right text-muted-foreground">
                    {proof.reconciliation?.delivery_items?.length
                      ? `${proof.reconciliation.delivery_items.length} line(s)`
                      : "—"}
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <Badge
                      variant={proof.missing_delivery_note ? "secondary" : "success"}
                      className="text-xs"
                    >
                      {proof.missing_delivery_note ? "No file" : "File attached"}
                    </Badge>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Variance */}
        {proof.reconciliation?.amount_variance != null && proof.reconciliation.amount_variance > 0 && (
          <div className="flex items-center gap-2 py-2 border-t border-border text-sm">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
            <span className="text-amber-600 dark:text-amber-400">
              Amount variance: {fmt(proof.reconciliation.amount_variance)}
            </span>
          </div>
        )}

        <ProofRow label="Overall Result" value={proof.reconciliation?.match_label ?? matchCfg.label} ok={proof.is_matched} />
        {proof.quantity_match !== null && (
          <ProofRow label="Quantity" value={proof.quantity_match ? "Quantities match" : "Quantities differ"} ok={proof.quantity_match} />
        )}
        {proof.amount_match !== null && (
          <ProofRow label="Amount" value={proof.amount_match ? "Amounts match" : "Amounts differ"} ok={proof.amount_match} />
        )}
        {proof.supplier_match !== null && (
          <ProofRow label="Supplier" value={proof.supplier_match ? "Supplier confirmed" : "Supplier mismatch"} ok={proof.supplier_match} />
        )}
        {proof.match_notes && <p className="text-xs text-muted-foreground mt-2 italic">{proof.match_notes}</p>}
        {proof.checked_at && (
          <p className="text-xs text-muted-foreground mt-2">
            Reviewed {proof.checked_at.slice(0, 10)}{proof.checked_by ? ` · ID ${proof.checked_by.slice(0, 8)}` : ""}
          </p>
        )}
      </div>

      {/* Manual matching panel */}
      <div className="bg-card border border-border rounded-xl p-4 space-y-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Manual Matching</p>
        <p className="text-xs text-muted-foreground">
          Link this invoice to the correct Purchase Order (PO) and delivery note, then set the match status.
        </p>
        <div className="grid grid-cols-1 gap-2">

          {/* Delivery dropdown */}
          <div>
            <label className="text-[10px] text-muted-foreground block mb-0.5">
              Link to Delivery Note {proof.delivery_id && <span className="text-green-600">✓ currently linked</span>}
            </label>
            <select
              value={manualDelivery}
              onChange={e => setManualDelivery(e.target.value)}
              className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs"
            >
              <option value="">— No delivery linked —</option>
              {proof.delivery_id && !deliveryOptions.find(d => d.id === proof.delivery_id) && (
                <option value={proof.delivery_id}>Current: {proof.delivery_number ?? proof.delivery_id.slice(0, 8)}</option>
              )}
              {deliveryOptions.map(d => (
                <option key={d.id} value={d.id}>
                  {d.delivery_number ?? d.id.slice(0, 8)}
                  {d.supplier_name ? ` · ${d.supplier_name}` : ""}
                  {d.delivery_date ? ` · ${d.delivery_date.slice(0, 10)}` : ""}
                </option>
              ))}
            </select>
          </div>

          {/* PO dropdown — load inline */}
          <div>
            <label className="text-[10px] text-muted-foreground block mb-0.5">
              Link to Purchase Order (PO) {proof.po_id && <span className="text-green-600">✓ currently linked</span>}
            </label>
            <select
              value={manualPo}
              onChange={e => setManualPo(e.target.value)}
              className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs"
            >
              <option value="">— No PO linked —</option>
              {proof.po_id && proof.po_number && (
                <option value={proof.po_id}>{proof.po_number} (current)</option>
              )}
              {poOptions.map(p => (
                <option key={p.id} value={p.id}>{p.po_number} · {p.status}</option>
              ))}
            </select>
            {poOptions.length === 0 && (
              <button
                type="button"
                className="text-[10px] text-primary hover:underline mt-0.5"
                onClick={() => {
                  // Load POs for the project linked to this invoice
                  const pid = proof.project_id;
                  const url = pid
                    ? `/projects/${pid}/purchase-orders/`
                    : "/purchase-orders/";
                  client.get<{ data: Array<{ id: string; po_number: string; status: string }> }>(url)
                    .then(r => { setPoOptions(r.data.data || []); })
                    .catch(() => {});
                }}
              >
                Load POs…
              </button>
            )}
          </div>

          <div>
            <label className="text-[10px] text-muted-foreground block mb-0.5">Notes</label>
            <input
              className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs"
              placeholder="Reason for manual match…"
              value={matchNotes}
              onChange={e => setMatchNotes(e.target.value)}
            />
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button
            size="sm" variant="outline" className="text-xs h-7"
            disabled={matching}
            onClick={() => handleManualMatch("MATCHED")}
          >
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Mark as Matched
          </Button>
          <Button
            size="sm" variant="outline" className="text-xs h-7"
            disabled={matching}
            onClick={() => handleManualMatch("PARTIALLY_MATCHED")}
          >
            Mark as Partial Match
          </Button>
          <Button
            size="sm" variant="outline" className="text-xs h-7"
            disabled={matching}
            onClick={() => handleManualMatch("AWAITING_APPROVAL")}
          >
            Mark as Reviewed
          </Button>
        </div>
        {matchMsg && <p className="text-xs text-green-600">{matchMsg}</p>}
      </div>

      {/* Actions */}
      {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3">{error}</p>}

      {canApprove && (
        <Button
          onClick={handleApprove}
          disabled={approving || !proof.is_matched}
          className="w-full"
          title={!proof.is_matched ? "Invoice must be matched before payment approval" : ""}
        >
          <CheckCircle2 className="w-4 h-4 mr-2" />
          {approving ? "Approving…" : "Approve for Payment"}
        </Button>
      )}
      {!proof.is_matched && canApprove && (
        <p className="text-xs text-center text-muted-foreground -mt-2">
          Approval is disabled until invoice is matched. Use Manual Override above.
        </p>
      )}
    </div>
  );
}

// ── Invoice list ──────────────────────────────────────────────────────────────

export default function InvoiceReconciliationPage() {
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [selected, setSelected] = useState<ProofPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState<string | null>(null);
  const [error, setError] = useState("");

  const loadInvoices = () => {
    setLoading(true);
    client.get<{ data: { items?: InvoiceSummary[]; total?: number } | InvoiceSummary[] }>("/invoices/", {
      params: { limit: 100 }
    })
      .then((res) => {
        const data = res.data.data;
        if (Array.isArray(data)) {
          setInvoices(data);
        } else if (data && "items" in data) {
          setInvoices((data as { items: InvoiceSummary[] }).items || []);
        }
      })
      .catch(() => setError("Failed to load invoices."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadInvoices(); }, []);

  const openInvoice = async (id: string) => {
    setDetailLoading(id);
    try {
      const res = await client.get<{ data: ProofPack }>(`/invoices/${id}/proof`);
      setSelected(res.data.data);
    } catch {
      setError("Failed to load proof pack. The invoice may not have a linked PO or delivery yet.");
    } finally { setDetailLoading(null); }
  };

  if (selected) {
    return (
      <ProofPackDetail
        proof={selected}
        onBack={() => setSelected(null)}
        onApproved={loadInvoices}
      />
    );
  }

  const STATUS_BADGE: Record<string, "success" | "destructive" | "secondary" | "outline"> = {
    MATCHED: "success", APPROVED: "success", PAID: "success",
    SUBMITTED: "secondary", RECEIVED: "secondary",
    REJECTED: "destructive", CANCELLED: "destructive",
  };

  return (
    <div className="space-y-5 animate-fade-in">

      <div>
        <h1 className="text-xl font-bold">Invoice Reconciliation</h1>
        <p className="text-sm text-muted-foreground">
          Match every invoice to its PO, delivery note, and signature before approving payment.
        </p>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive flex items-center justify-between">
          {error}
          <button onClick={() => setError("")} className="shrink-0 ml-3"><X className="w-4 h-4" /></button>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>
      ) : invoices.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <FileText className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No invoices to reconcile.</p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Invoice #</th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Amount</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 font-medium font-mono">{inv.invoice_number}</td>
                  <td className="px-4 py-3 text-right hidden sm:table-cell">{fmt(inv.total_amount)}</td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_BADGE[inv.status] || "outline"} className="text-xs">
                      {inv.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => openInvoice(inv.id)}
                      disabled={detailLoading === inv.id}
                      className="h-7 text-xs"
                    >
                      {detailLoading === inv.id ? "Loading…" : "View Proof Pack"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
