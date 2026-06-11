import React, { useEffect, useState } from "react";
import { WriteGuard } from "@/components/shared/WriteGuard";
import { Plus, CreditCard, CheckCircle2, Clock, FileText, AlertTriangle, Hammer, Camera, ChevronDown, ChevronUp, Sparkles, Upload, ChevronRight } from "lucide-react";
import { AttachmentStrip } from "@/components/shared/AttachmentStrip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { Tabs } from "@/components/shared/Tabs";
import { StatCard } from "@/components/shared/StatCard";
import { Modal } from "@/components/shared/Modal";
import { projectsApi, type Project } from "@/api/projects";
import { invoicesApi, type Invoice, type InvoiceCreate, type EnrichedInvoice } from "@/api/invoices";
import {
  paymentsApi,
  type Payment, type PaymentCreate, type PaymentStatus,
  type InvoiceReconciliation, type PaymentReport, type AgingReport,
  PAYMENT_METHODS,
} from "@/api/payments";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { jobCardsApi, type JobCard } from "@/api/jobCards";
import { formatCurrency, formatDate } from "@/lib/format";
import client from "@/api/client";

interface OutstandingInvoice {
  invoice_id:          string;
  invoice_number:      string;
  supplier_name:       string | null;
  total_amount:        number;
  total_paid:          number;
  outstanding_balance: number;
  due_date:            string | null;
  status:              string;
  is_overdue:          boolean;
}
interface OutstandingSummary {
  total_outstanding_invoices: number;
  overdue_amount: number;
  pending_payments_amount: number;
  outstanding_invoices: OutstandingInvoice[];
  overdue_count: number;
}

type RecordStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED" | "SENT" | "RECEIVED" | "MATCHED" | "PAID" | "CANCELLED";

const paymentStatusVariant: Record<PaymentStatus, "success" | "secondary" | "default" | "destructive" | "outline"> = {
  PAID:      "success",
  APPROVED:  "default",
  PENDING:   "secondary",
  FAILED:    "destructive",
  CANCELLED: "outline",
};

const invoiceStatusVariant: Record<string, "secondary" | "default" | "success" | "destructive" | "outline"> = {
  DRAFT:          "outline",
  SUBMITTED:      "secondary",
  APPROVED:       "default",
  REJECTED:       "destructive",
  SENT:           "default",
  RECEIVED:       "default",
  MATCHED:        "default",
  INVOICED:       "secondary",
  PARTIALLY_PAID: "secondary",   // Phase 3L
  OVERPAID:       "destructive", // Phase 3L
  PAID:           "success",
  CANCELLED:      "outline",
};

const PAGE_TABS = [
  { key: "payments", label: "Payments" },
  { key: "invoices", label: "Invoices" },
];

// ── OCR Review Panel ──────────────────────────────────────────────────────────

type OcrStatus = "idle" | "extracting" | "EXTRACTED" | "NEEDS_REVIEW" | "OCR_NOT_AVAILABLE" | "OCR_FAILED" | "FAILED";

interface OcrReview {
  invoice_number: string;
  total_amount:   string;
  vat_amount:     string;
  invoice_date:   string;
  due_date:       string;
  supplier_name:  string;
  po_number:      string;
  line_items:     Array<{ description: string | null; quantity: number | null; unit_price: number | null; line_total: number | null; unit: string | null }>;
  warnings:       string[];
}

function OCRReviewPanel({
  suppliers,
  onApply,
}: {
  suppliers: Supplier[];
  onApply: (data: { invoice_number?: string; total_amount?: number; invoice_date?: string | null; due_date?: string | null; supplier_id?: string }) => void;
}) {
  const [status, setStatus] = useState<OcrStatus>("idle");
  const [review, setReview] = useState<OcrReview | null>(null);
  const [supplierSuggestions, setSupplierSuggestions] = useState<Array<{ id: string; name: string; score: number }>>([]);
  const [showLines, setShowLines] = useState(false);
  const [selectedSupplierId, setSelectedSupplierId] = useState("");

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("extracting");
    setReview(null);
    setSupplierSuggestions([]);

    try {
      const { visionApi } = await import("@/api/vision");
      const result = await visionApi.extract(file, "invoice");

      if (result.status === "OCR_NOT_AVAILABLE" || result.status === "OCR_FAILED" || result.status === "FAILED") {
        setStatus(result.status as OcrStatus);
        return;
      }

      const p = result.preview as {
        invoice_number?: string | null; total_amount?: number | null; vat_amount?: number | null;
        date?: string | null; due_date?: string | null;
        supplier_name?: string | null; po_number?: string | null;
        line_items?: Array<{ description: string | null; quantity: number | null; unit_price: number | null; line_total: number | null; unit: string | null }>;
      };

      const r: OcrReview = {
        invoice_number: p.invoice_number ?? "",
        total_amount:   p.total_amount != null ? String(p.total_amount) : "",
        vat_amount:     p.vat_amount != null ? String(p.vat_amount) : "",
        invoice_date:   p.date ?? "",
        due_date:       p.due_date ?? "",
        supplier_name:  p.supplier_name ?? "",
        po_number:      p.po_number ?? "",
        line_items:     p.line_items ?? [],
        warnings:       result.warnings ?? [],
      };
      setReview(r);
      setStatus(result.status as OcrStatus);

      // Fetch supplier suggestions if a name was extracted
      if (p.supplier_name) {
        try {
          const suggestions = await visionApi.suggestSupplier(p.supplier_name);
          setSupplierSuggestions(suggestions);
          if (suggestions.length > 0 && suggestions[0].score >= 0.5) {
            setSelectedSupplierId(suggestions[0].id);
          }
        } catch { /* silent */ }
      }
    } catch {
      setStatus("FAILED");
    } finally {
      e.target.value = "";
    }
  };

  const handleApply = () => {
    if (!review) return;
    onApply({
      invoice_number: review.invoice_number || undefined,
      total_amount:   parseFloat(review.total_amount) || undefined,
      invoice_date:   review.invoice_date || null,
      due_date:       review.due_date || null,
      supplier_id:    selectedSupplierId || undefined,
    });
  };

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Upload trigger */}
      <div className="bg-muted/30 px-3 py-2.5 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          <span className="text-xs font-medium">Extract from invoice file</span>
          <span className="text-[10px] text-muted-foreground">(PDF or image — review before applying)</span>
        </div>
        <label className="cursor-pointer">
          <input type="file" accept="image/*,.pdf" className="sr-only" onChange={handleFile} />
          <div className="flex items-center gap-1 text-xs text-primary hover:underline">
            <Upload className="w-3 h-3" />
            {status === "extracting" ? "Extracting…" : "Upload"}
          </div>
        </label>
      </div>

      {/* Status indicator */}
      {status !== "idle" && status !== "extracting" && (
        <div className={`px-3 py-1.5 text-[10px] font-medium flex items-center gap-1.5 ${
          status === "EXTRACTED"         ? "bg-green-50 text-green-700 border-b border-green-200" :
          status === "NEEDS_REVIEW"      ? "bg-amber-50 text-amber-700 border-b border-amber-200" :
          (status === "OCR_NOT_AVAILABLE" || status === "OCR_FAILED") ? "bg-muted text-muted-foreground border-b border-border" :
          "bg-destructive/10 text-destructive border-b border-destructive/20"
        }`}>
          {status === "EXTRACTED"         && <CheckCircle2 className="w-3 h-3" />}
          {status === "NEEDS_REVIEW"      && <AlertTriangle className="w-3 h-3" />}
          {(status === "OCR_NOT_AVAILABLE" || status === "OCR_FAILED") && <FileText className="w-3 h-3" />}
          {status === "EXTRACTED"         && "Fields extracted — review and apply below"}
          {status === "NEEDS_REVIEW"      && "Partial extraction — some fields may be missing. Review carefully."}
          {status === "OCR_NOT_AVAILABLE" && "OCR not configured — enter fields manually"}
          {status === "OCR_FAILED"        && "Google Vision configured but returned no text — check credentials. Enter fields manually."}
          {status === "FAILED"            && "Could not read file — enter fields manually"}
        </div>
      )}

      {/* Review fields */}
      {review && (
        <div className="p-3 space-y-3">
          {review.warnings.map((w, i) => (
            <p key={i} className="text-[10px] text-amber-600 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3 shrink-0" />{w}
            </p>
          ))}

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] text-muted-foreground block mb-0.5">Invoice Number</label>
              <input type="text" value={review.invoice_number}
                onChange={e => setReview({ ...review, invoice_number: e.target.value })}
                className="w-full h-7 rounded border border-input bg-background px-2 text-xs" />
            </div>
            <div>
              <label className="text-[10px] text-muted-foreground block mb-0.5">Total Amount (R)</label>
              <input type="number" step="0.01" value={review.total_amount}
                onChange={e => setReview({ ...review, total_amount: e.target.value })}
                className="w-full h-7 rounded border border-input bg-background px-2 text-xs" />
            </div>
            <div>
              <label className="text-[10px] text-muted-foreground block mb-0.5">Invoice Date</label>
              <input type="text" value={review.invoice_date} placeholder="DD/MM/YYYY"
                onChange={e => setReview({ ...review, invoice_date: e.target.value })}
                className="w-full h-7 rounded border border-input bg-background px-2 text-xs" />
            </div>
            <div>
              <label className="text-[10px] text-muted-foreground block mb-0.5">Due Date</label>
              <input type="text" value={review.due_date} placeholder="DD/MM/YYYY"
                onChange={e => setReview({ ...review, due_date: e.target.value })}
                className="w-full h-7 rounded border border-input bg-background px-2 text-xs" />
            </div>
            {review.vat_amount && (
              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">VAT Amount (R)</label>
                <input type="text" value={review.vat_amount} readOnly
                  className="w-full h-7 rounded border border-input bg-muted/30 px-2 text-xs text-muted-foreground" />
              </div>
            )}
            {review.po_number && (
              <div>
                <label className="text-[10px] text-muted-foreground block mb-0.5">PO Reference (found)</label>
                <div className="h-7 rounded border border-amber-200 bg-amber-50 px-2 text-xs text-amber-700 flex items-center">
                  {review.po_number}
                </div>
              </div>
            )}
          </div>

          {/* Supplier matching */}
          <div>
            <label className="text-[10px] text-muted-foreground block mb-0.5">
              Supplier
              {review.supplier_name && (
                <span className="text-primary ml-1">— extracted: "{review.supplier_name}"</span>
              )}
            </label>
            {supplierSuggestions.length > 0 ? (
              <div className="space-y-1">
                <p className="text-[10px] text-muted-foreground mb-1">Suggestions (click to select):</p>
                <div className="flex flex-wrap gap-1.5">
                  {supplierSuggestions.map(s => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setSelectedSupplierId(s.id)}
                      className={`text-xs px-2 py-1 rounded border transition-colors ${
                        selectedSupplierId === s.id
                          ? "bg-primary text-primary-foreground border-primary"
                          : "bg-background border-border hover:border-primary/50"
                      }`}
                    >
                      {s.name}
                      <span className="text-[9px] ml-1 opacity-60">{Math.round(s.score * 100)}%</span>
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setSelectedSupplierId("")}
                    className="text-xs px-2 py-1 rounded border border-border text-muted-foreground hover:border-primary/50"
                  >
                    Clear
                  </button>
                </div>
                {selectedSupplierId && (
                  <p className="text-[10px] text-green-600 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    {suppliers.find(s => s.id === selectedSupplierId)?.name} selected
                  </p>
                )}
              </div>
            ) : review.supplier_name ? (
              <p className="text-[10px] text-muted-foreground">No matching suppliers found. Select manually in the form below.</p>
            ) : (
              <p className="text-[10px] text-muted-foreground">No supplier name found in document. Select manually in the form below.</p>
            )}
          </div>

          {/* Line items (collapsible) */}
          {review.line_items.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setShowLines(v => !v)}
                className="flex items-center gap-1 text-[10px] text-primary hover:underline"
              >
                <ChevronRight className={`w-3 h-3 transition-transform ${showLines ? "rotate-90" : ""}`} />
                {review.line_items.length} line item{review.line_items.length !== 1 ? "s" : ""} extracted
              </button>
              {showLines && (
                <div className="mt-1 overflow-x-auto border border-border rounded">
                  <table className="w-full text-[10px] min-w-[360px]">
                    <thead>
                      <tr className="border-b border-border bg-muted/30">
                        <th className="text-left px-2 py-1 font-medium text-muted-foreground">Description</th>
                        <th className="text-right px-2 py-1 font-medium text-muted-foreground">Qty</th>
                        <th className="text-left px-2 py-1 font-medium text-muted-foreground">Unit</th>
                        <th className="text-right px-2 py-1 font-medium text-muted-foreground">Unit Price</th>
                        <th className="text-right px-2 py-1 font-medium text-muted-foreground">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {review.line_items.map((item, i) => (
                        <tr key={i} className="border-b border-border/40 last:border-0">
                          <td className="px-2 py-1">{item.description ?? "—"}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{item.quantity ?? "—"}</td>
                          <td className="px-2 py-1 text-muted-foreground">{item.unit ?? "—"}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{item.unit_price != null ? `R${item.unit_price.toFixed(2)}` : "—"}</td>
                          <td className="px-2 py-1 text-right font-medium tabular-nums">{item.line_total != null ? `R${item.line_total.toFixed(2)}` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          <Button
            type="button"
            size="sm"
            className="w-full h-7 text-xs"
            onClick={handleApply}
          >
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Apply extracted data to form
          </Button>
          <p className="text-[10px] text-muted-foreground text-center">
            Always verify extracted values before saving.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Capture Invoice Modal ─────────────────────────────────────────────────────

function CaptureInvoiceModal({
  projectId,
  suppliers,
  onClose,
  onCreated,
}: {
  projectId: string;
  suppliers: Supplier[];
  onClose: () => void;
  onCreated: (inv: Invoice) => void;
}) {
  const [form, setForm] = useState<InvoiceCreate>({
    invoice_number: "",
    supplier_id: suppliers[0]?.id ?? "",
    total_amount: 0,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const inv = await invoicesApi.create(projectId, form);
      onCreated(inv);
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Failed to capture invoice.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title="Capture Invoice" onClose={onClose} size="md">
      <form onSubmit={submit} className="p-6 space-y-4">
        <OCRReviewPanel
          suppliers={suppliers}
          onApply={(data) => setForm(prev => ({
            ...prev,
            ...(data.invoice_number != null && { invoice_number: data.invoice_number }),
            ...(data.total_amount   != null && { total_amount:   data.total_amount }),
            ...(data.invoice_date   !== undefined && { invoice_date: data.invoice_date }),
            ...(data.due_date       !== undefined && { due_date:     data.due_date }),
            ...(data.supplier_id    != null && data.supplier_id !== "" && { supplier_id: data.supplier_id }),
          }))}
        />

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Invoice Number <span className="text-destructive">*</span></Label>
            <Input
              value={form.invoice_number}
              onChange={(e) => setForm({ ...form, invoice_number: e.target.value })}
              required
              placeholder="e.g. INV-2024-001"
            />
          </div>
          <div className="space-y-2">
            <Label>Total Amount (R) <span className="text-destructive">*</span></Label>
            <Input
              type="number"
              step="0.01"
              value={form.total_amount}
              onChange={(e) => setForm({ ...form, total_amount: parseFloat(e.target.value) || 0 })}
              required
            />
          </div>
        </div>
        <div className="space-y-2">
          <Label>Supplier <span className="text-destructive">*</span></Label>
          <select
            value={form.supplier_id}
            onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            required
          >
            <option value="">— Select supplier —</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Invoice Date</Label>
            <Input type="date" value={form.invoice_date ?? ""} onChange={(e) => setForm({ ...form, invoice_date: e.target.value || null })} />
          </div>
          <div className="space-y-2">
            <Label>Due Date</Label>
            <Input type="date" value={form.due_date ?? ""} onChange={(e) => setForm({ ...form, due_date: e.target.value || null })} />
          </div>
        </div>
        {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex gap-2 pt-1">
          <Button type="submit" disabled={loading} className="flex-1">{loading ? "Saving…" : "Capture Invoice"}</Button>
          <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Capture Payment Modal ─────────────────────────────────────────────────────

function CapturePaymentModal({
  projectId,
  suppliers,
  onClose,
  onCreated,
}: {
  projectId: string;
  suppliers: Supplier[];
  onClose: () => void;
  onCreated: (p: Payment) => void;
}) {
  const [form, setForm] = useState<PaymentCreate>({
    payment_type: "SUPPLIER",
    amount_paid: 0,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const payment = await paymentsApi.create(projectId, form);
      onCreated(payment);
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Failed to capture payment.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title="Capture Payment" onClose={onClose} size="md">
      <form onSubmit={submit} className="p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Payment Type <span className="text-destructive">*</span></Label>
            <select
              value={form.payment_type}
              onChange={(e) => setForm({ ...form, payment_type: e.target.value as "SUPPLIER" | "LABOUR" | "OTHER" })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="SUPPLIER">Supplier</option>
              <option value="LABOUR">Labour</option>
              <option value="OTHER">Other</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label>Amount Paid (R) <span className="text-destructive">*</span></Label>
            <Input
              type="number"
              step="0.01"
              value={form.amount_paid}
              onChange={(e) => setForm({ ...form, amount_paid: parseFloat(e.target.value) || 0 })}
              required
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Supplier</Label>
            <select
              value={form.supplier_id ?? ""}
              onChange={(e) => setForm({ ...form, supplier_id: e.target.value || null })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— None —</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <Label>Payment Method</Label>
            <select
              value={(form as { payment_method?: string }).payment_method ?? ""}
              onChange={(e) => setForm({ ...form, payment_method: e.target.value || null } as PaymentCreate)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— Select method —</option>
              {PAYMENT_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        </div>
        <div className="space-y-2">
          <Label>Payment Reference</Label>
          <Input
            value={form.payment_reference ?? ""}
            onChange={(e) => setForm({ ...form, payment_reference: e.target.value || null })}
            placeholder="e.g. EFT-20240601"
          />
        </div>
        <div className="space-y-2">
          <Label>Payment Date</Label>
          <Input type="date" value={form.payment_date ?? ""} onChange={(e) => setForm({ ...form, payment_date: e.target.value || null })} />
        </div>
        {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex gap-2 pt-1">
          <Button type="submit" disabled={loading} className="flex-1">{loading ? "Saving…" : "Capture Payment"}</Button>
          <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PaymentsPage() {
  const [tab, setTab] = useState("payments");
  const [projects, setProjects] = useState<Project[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [payments, setPayments] = useState<Payment[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [enrichedInvoices, setEnrichedInvoices] = useState<EnrichedInvoice[]>([]);
  const [outstanding, setOutstanding] = useState<OutstandingSummary | null>(null);
  const [labourJcs, setLabourJcs] = useState<JobCard[]>([]);
  const [payingJc, setPayingJc] = useState<JobCard | null>(null);
  const [jcPayRef, setJcPayRef] = useState("");
  const [jcPayDate, setJcPayDate] = useState(new Date().toISOString().split("T")[0]);
  const [jcPayNotes, setJcPayNotes] = useState("");
  const [jcPaying, setJcPaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  // Phase 3L: reconciliation panel
  const [reconciliation, setReconciliation] = useState<InvoiceReconciliation | null>(null);
  const [reconcLoading, setReconcLoading]     = useState(false);
  // Phase 3L finalization: aging
  const [aging, setAging]         = useState<AgingReport | null>(null);
  const [agingLoading, setAgingLoading] = useState(false);
  // Phase 3L finalization: quick payment from reconciliation panel
  const [quickPayAmount, setQuickPayAmount]   = useState("");
  const [quickPayDate, setQuickPayDate]       = useState(new Date().toISOString().split("T")[0]);
  const [quickPayRef, setQuickPayRef]         = useState("");
  const [quickPayMethod, setQuickPayMethod]   = useState("EFT");
  const [quickPaying, setQuickPaying]         = useState(false);
  const [quickPayError, setQuickPayError]     = useState("");

  const showReconciliation = async (invoiceId: string) => {
    if (reconciliation?.invoice_id === invoiceId) { setReconciliation(null); return; }
    setReconcLoading(true);
    try {
      const r = await paymentsApi.getInvoiceReconciliation(invoiceId);
      setReconciliation(r);
      setQuickPayAmount(r.outstanding > 0 ? String(r.outstanding.toFixed(2)) : "");
      setQuickPayRef(""); setQuickPayMethod("EFT"); setQuickPayError("");
    }
    catch { /* silent */ }
    finally { setReconcLoading(false); }
  };

  const handleApprovePayment = async (paymentId: string) => {
    try {
      const updated = await paymentsApi.approve(paymentId);
      setPayments(prev => prev.map(p => p.id === paymentId ? updated : p));
    } catch { /* silent */ }
  };

  const handleQuickPay = async (supplierId: string | null) => {
    if (!selectedProjectId || !reconciliation) return;
    const amt = parseFloat(quickPayAmount);
    if (!amt || amt <= 0) { setQuickPayError("Enter a valid amount."); return; }
    setQuickPaying(true); setQuickPayError("");
    try {
      await paymentsApi.create(selectedProjectId, {
        payment_type: "SUPPLIER",
        invoice_id: reconciliation.invoice_id,
        supplier_id: supplierId,
        amount_paid: amt,
        payment_date: quickPayDate || null,
        payment_reference: quickPayRef || null,
        payment_method: quickPayMethod,
      });
      // Refresh reconciliation and payment list
      const [updated, pays] = await Promise.all([
        paymentsApi.getInvoiceReconciliation(reconciliation.invoice_id),
        paymentsApi.list(selectedProjectId),
      ]);
      setReconciliation(updated);
      setPayments(pays);
      setQuickPayAmount(updated.outstanding > 0 ? String(updated.outstanding.toFixed(2)) : "");
      setQuickPayRef("");
    } catch (err: unknown) {
      setQuickPayError((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Payment failed.");
    } finally { setQuickPaying(false); }
  };

  const [showCaptureInvoice, setShowCaptureInvoice] = useState(false);
  const [showCapturePayment, setShowCapturePayment] = useState(false);
  const [expandedPaymentId, setExpandedPaymentId] = useState<string | null>(null);

  // Load projects + suppliers on mount
  useEffect(() => {
    Promise.all([projectsApi.list(1, 100), suppliersApi.list()])
      .then(([projRes, ss]) => {
        setProjects(projRes.items);
        setSuppliers(ss);
        if (projRes.items.length > 0) {
          setSelectedProjectId(projRes.items[0].id);
        } else {
          setLoading(false);
        }
      })
      .catch(() => setLoading(false));
  }, []);

  // Load payments + invoices + labour job cards when project changes
  useEffect(() => {
    if (!selectedProjectId) return;
    setLoading(true);
    setLoadError("");
    jobCardsApi.list(selectedProjectId, "PAYMENT_APPROVED").then(setLabourJcs).catch(() => setLabourJcs([]));
    // Load aging lazily when Outstanding tab is opened
    setAging(null);
    Promise.all([
      paymentsApi.list(selectedProjectId),
      invoicesApi.list(selectedProjectId),
      invoicesApi.listEnriched(selectedProjectId).catch((): EnrichedInvoice[] => []),
      client.get<{ data: OutstandingSummary }>(`/projects/${selectedProjectId}/payments/outstanding-summary`)
        .then(r => r.data.data).catch(() => null),
    ])
      .then(([pays, invs, enriched, outstand]) => {
        setPayments(pays);
        setInvoices(invs);
        setEnrichedInvoices(enriched);
        setOutstanding(outstand);
      })
      .catch((err: unknown) => {
        const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
          || "Failed to load payments data.";
        setLoadError(msg);
      })
      .finally(() => setLoading(false));
  }, [selectedProjectId]);

  // Load aging when Outstanding tab is selected
  useEffect(() => {
    if (tab !== "outstanding" || !selectedProjectId || aging) return;
    setAgingLoading(true);
    paymentsApi.getAging(selectedProjectId)
      .then(setAging)
      .catch(() => {})
      .finally(() => setAgingLoading(false));
  }, [tab, selectedProjectId, aging]);

  const totalPaid   = payments.filter((p) => p.status === "PAID").reduce((s, p) => s + p.amount_paid, 0);
  const pendingPays = payments.filter((p) => p.status === "PENDING").length;
  const paidPays    = payments.filter((p) => p.status === "PAID").length;
  const pendingInvs = invoices.filter((i) => ["DRAFT", "SUBMITTED"].includes(i.status)).length;

  const totalOutstanding = enrichedInvoices.reduce((s, i) => s + i.outstanding_amount, 0);

  const handlePayLabour = async () => {
    if (!payingJc || !selectedProjectId) return;
    setJcPaying(true);
    try {
      await Promise.all([
        paymentsApi.create(selectedProjectId, {
          payment_type: "LABOUR",
          amount_paid: payingJc.total_amount,
          payment_date: jcPayDate || null,
          payment_reference: jcPayRef || payingJc.job_card_number,
          notes: jcPayNotes || `Labour payment for job card ${payingJc.job_card_number}`,
        } as PaymentCreate),
        jobCardsApi.markPaid(payingJc.id),
      ]);
      setLabourJcs(prev => prev.filter(j => j.id !== payingJc.id));
      setPayingJc(null); setJcPayRef(""); setJcPayDate(new Date().toISOString().split("T")[0]); setJcPayNotes("");
      paymentsApi.list(selectedProjectId).then(setPayments).catch(() => {});
    } catch {
      alert("Payment failed. Check backend logs.");
    } finally { setJcPaying(false); }
  };

  const [exportFrom, setExportFrom] = useState("");
  const [exportTo,   setExportTo]   = useState("");
  const [exporting,  setExporting]  = useState(false);

  const handleExportCSV = async () => {
    if (!selectedProjectId) return;
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (exportFrom) params.append("from_date", exportFrom);
      if (exportTo)   params.append("to_date",   exportTo);
      const url = `${client.defaults.baseURL}/projects/${selectedProjectId}/payments/export?${params}`;
      const res = await client.get(url, { responseType: "blob" });
      const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `payments_${selectedProjectId}_${exportFrom || "all"}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch { alert("Export failed."); }
    finally { setExporting(false); }
  };

  const PAGE_TABS_EXTRA = [
    { key: "payments", label: "Payments" },
    { key: "invoices", label: "Invoices" },
    { key: "outstanding", label: "Outstanding" },
    { key: "labour", label: "Labour" },
  ];

  const tabsWithCount = [
    { ...PAGE_TABS_EXTRA[0], count: payments.length },
    { ...PAGE_TABS_EXTRA[1], count: invoices.length },
    { ...PAGE_TABS_EXTRA[2], count: outstanding?.outstanding_invoices.length ?? 0 },
    { ...PAGE_TABS_EXTRA[3], count: labourJcs.length },
  ];

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Payments"
        description="Manage supplier invoices and payment records."
        actions={
          <WriteGuard>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowCaptureInvoice(true)} disabled={!selectedProjectId}>
                <FileText className="w-4 h-4" />
                Capture Invoice
              </Button>
              <Button size="sm" onClick={() => setShowCapturePayment(true)} disabled={!selectedProjectId}>
                <Plus className="w-4 h-4" />
                Capture Payment
              </Button>
            </div>
          </WriteGuard>
        }
      />

      {/* Project selector + CSV export */}
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs text-muted-foreground whitespace-nowrap">Project</label>
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
        </select>

        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <label className="text-xs text-muted-foreground">From</label>
          <input type="date" value={exportFrom} onChange={e => setExportFrom(e.target.value)}
                 className="h-9 rounded-md border border-input bg-background px-3 text-sm" />
          <label className="text-xs text-muted-foreground">To</label>
          <input type="date" value={exportTo} onChange={e => setExportTo(e.target.value)}
                 className="h-9 rounded-md border border-input bg-background px-3 text-sm" />
          <Button size="sm" variant="outline" onClick={handleExportCSV} disabled={exporting || !selectedProjectId}>
            <FileText className="w-3.5 h-3.5 mr-1" />
            {exporting ? "Exporting…" : "Export CSV"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Paid"           value={formatCurrency(totalPaid)}                              icon={CreditCard}   color="bg-success/10 text-success" />
        <StatCard title="Pending Payments"     value={pendingPays}                                             icon={Clock}        color="bg-warning/10 text-warning" />
        <StatCard title="Outstanding Invoices" value={formatCurrency(outstanding?.total_outstanding_invoices ?? 0)} icon={FileText} color="bg-destructive/10 text-destructive" />
        <StatCard title="Overdue Amount"       value={formatCurrency(outstanding?.overdue_amount ?? 0)}        icon={AlertTriangle} color="bg-destructive/10 text-destructive" />
      </div>

      <Tabs tabs={tabsWithCount} active={tab} onChange={setTab} />

      {loadError && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">
          {loadError}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">{[1,2,3].map((i) => <Skeleton key={i} className="h-14 rounded-xl" />)}</div>
      ) : tab === "payments" ? (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {payments.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">No payments recorded yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Reference</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Type</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Amount</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <React.Fragment key={p.id}>
                    <tr className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 font-mono text-xs">{p.payment_reference ?? p.id.slice(0, 8)}</td>
                      <td className="px-4 py-3 text-muted-foreground text-sm">{p.payment_type}</td>
                      <td className="px-4 py-3 font-semibold">{formatCurrency(p.amount_paid)}</td>
                      <td className="px-4 py-3 text-muted-foreground text-sm">{p.payment_date ? formatDate(p.payment_date) : "—"}</td>
                      <td className="px-4 py-3">
                        <Badge variant={paymentStatusVariant[p.status]}>{p.status}</Badge>
                      </td>
                      <td className="px-2 py-3">
                        <div className="flex items-center justify-end gap-1">
                          {p.status === "PENDING" && (
                            <WriteGuard>
                              <button
                                onClick={() => handleApprovePayment(p.id)}
                                className="text-xs text-green-600 hover:text-green-700 font-medium px-2 py-1 rounded hover:bg-green-500/10 transition-colors"
                                title="Approve payment"
                              >
                                Approve
                              </button>
                            </WriteGuard>
                          )}
                          <button
                            onClick={() => setExpandedPaymentId(prev => prev === p.id ? null : p.id)}
                            className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-primary transition-colors"
                            title="Proof of payment"
                          >
                            {expandedPaymentId === p.id
                              ? <ChevronUp className="w-4 h-4" />
                              : <Camera className="w-4 h-4" />}
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expandedPaymentId === p.id && (
                      <tr className="bg-muted/20 border-b border-border">
                        <td colSpan={6} className="px-4 py-3">
                          <AttachmentStrip
                            entityType="PAYMENT"
                            entityId={p.id}
                            attachmentType="PROOF"
                            accept="image/*,application/pdf"
                            label="Proof of Payment"
                          />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : tab === "invoices" ? (
        <div className="space-y-3">
          {totalOutstanding > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 text-xs text-amber-700 flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              Total outstanding across all invoices: <strong className="ml-1">{formatCurrency(totalOutstanding)}</strong>
            </div>
          )}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {enrichedInvoices.length === 0 ? (
              <div className="p-12 text-center text-sm text-muted-foreground">No invoices captured yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/50">
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground whitespace-nowrap">Invoice #</th>
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground">Supplier</th>
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">PO #</th>
                      <th className="text-right px-4 py-3 font-medium text-muted-foreground">Amount</th>
                      <th className="text-right px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Outstanding</th>
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Due Date</th>
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                      <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Match</th>
                    </tr>
                  </thead>
                  <tbody>
                    {enrichedInvoices.map((inv) => (
                      <React.Fragment key={inv.invoice_id}>
                      <tr className={`border-b border-border last:border-0 transition-colors ${inv.is_overdue ? "bg-destructive/5 hover:bg-destructive/10" : "hover:bg-muted/30"}`}>
                        <td className="px-4 py-3 font-mono text-xs font-medium">{inv.invoice_number}</td>
                        <td className="px-4 py-3 text-muted-foreground text-xs">{inv.supplier_name ?? "—"}</td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground hidden md:table-cell">{inv.po_number ?? "—"}</td>
                        <td className="px-4 py-3 text-right font-semibold">{formatCurrency(inv.total_amount)}</td>
                        <td className="px-4 py-3 text-right hidden sm:table-cell">
                          {inv.outstanding_amount > 0
                            ? <span className={inv.is_overdue ? "text-destructive font-semibold" : "text-amber-600 font-medium"}>{formatCurrency(inv.outstanding_amount)}</span>
                            : <span className="text-green-600 font-medium">Paid</span>
                          }
                        </td>
                        <td className="px-4 py-3 hidden sm:table-cell">
                          {inv.due_date ? (
                            <span className={inv.is_overdue ? "text-destructive font-medium text-xs" : "text-muted-foreground text-xs"}>
                              {inv.is_overdue && <AlertTriangle className="w-3 h-3 inline mr-1" />}
                              {formatDate(inv.due_date)}
                            </span>
                          ) : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={invoiceStatusVariant[inv.status as RecordStatus] ?? "outline"} className="text-xs">
                            {inv.status}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 hidden md:table-cell">
                          <span className={`text-xs font-medium ${
                            inv.match_status === "MATCHED" ? "text-green-600" :
                            inv.match_status === "UNLINKED" ? "text-muted-foreground" :
                            "text-amber-600"
                          }`}>
                            {inv.match_status?.replace(/_/g, " ") ?? "—"}
                          </span>
                        </td>
                        <td className="px-2 py-3">
                          <button
                            onClick={() => showReconciliation(inv.invoice_id)}
                            className="text-xs text-primary hover:underline whitespace-nowrap"
                            disabled={reconcLoading}
                          >
                            {reconciliation?.invoice_id === inv.invoice_id ? "Hide" : "Reconcile"}
                          </button>
                        </td>
                      </tr>
                      {/* Reconciliation panel inline */}
                      {reconciliation?.invoice_id === inv.invoice_id && (
                        <tr>
                          <td colSpan={8} className="px-4 py-4 bg-muted/20 border-b border-border">
                            <div className="space-y-4">
                              {/* Summary row */}
                              <div className="flex items-center gap-4 text-xs flex-wrap">
                                <span>Total: <strong>{formatCurrency(reconciliation.total_amount)}</strong></span>
                                <span className="text-green-600">Paid: <strong>{formatCurrency(reconciliation.total_paid)}</strong></span>
                                {reconciliation.outstanding > 0 && (
                                  <span className="text-amber-600 font-medium">Outstanding: {formatCurrency(reconciliation.outstanding)}</span>
                                )}
                                {reconciliation.is_overpaid && (
                                  <span className="text-destructive font-semibold">⚠ Overpaid by {formatCurrency(reconciliation.total_paid - reconciliation.total_amount)}</span>
                                )}
                                {reconciliation.due_date && (
                                  <span className="text-muted-foreground">Due: {formatDate(reconciliation.due_date)}</span>
                                )}
                              </div>

                              {/* Payment history */}
                              {reconciliation.payments.length === 0 ? (
                                <p className="text-xs text-muted-foreground">No payments recorded yet.</p>
                              ) : (
                                <div className="overflow-x-auto">
                                  <table className="w-full text-xs min-w-[480px]">
                                    <thead>
                                      <tr className="border-b border-border">
                                        <th className="text-left py-1 pr-3 font-medium text-muted-foreground">Date</th>
                                        <th className="text-right py-1 px-2 font-medium text-muted-foreground">Amount</th>
                                        <th className="text-left py-1 px-2 font-medium text-muted-foreground">Method</th>
                                        <th className="text-left py-1 px-2 font-medium text-muted-foreground">Reference</th>
                                        <th className="text-left py-1 pl-2 font-medium text-muted-foreground">Captured by</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {reconciliation.payments.map((p) => (
                                        <tr key={p.id} className="border-b border-border/40 last:border-0">
                                          <td className="py-1 pr-3 text-muted-foreground">{p.payment_date ? formatDate(p.payment_date) : "—"}</td>
                                          <td className="py-1 px-2 text-right font-semibold tabular-nums">{formatCurrency(p.amount_paid)}</td>
                                          <td className="py-1 px-2 text-muted-foreground">{p.payment_method ?? "—"}</td>
                                          <td className="py-1 px-2 font-mono text-muted-foreground">{p.payment_reference ?? "—"}</td>
                                          <td className="py-1 pl-2 text-muted-foreground">{p.captured_by_name ?? "—"}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}

                              {/* 3L-D: Quick payment form */}
                              {reconciliation.outstanding > 0 && (
                                <WriteGuard>
                                  <div className="bg-card border border-border rounded-lg p-3 space-y-2">
                                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Record Payment</p>
                                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                                      <div>
                                        <label className="text-[10px] text-muted-foreground block mb-0.5">Amount (R)</label>
                                        <input
                                          type="number" min="0.01" step="0.01"
                                          value={quickPayAmount}
                                          onChange={e => setQuickPayAmount(e.target.value)}
                                          className="w-full h-8 rounded border border-input bg-background px-2 text-xs"
                                        />
                                      </div>
                                      <div>
                                        <label className="text-[10px] text-muted-foreground block mb-0.5">Date</label>
                                        <input
                                          type="date"
                                          value={quickPayDate}
                                          onChange={e => setQuickPayDate(e.target.value)}
                                          className="w-full h-8 rounded border border-input bg-background px-2 text-xs"
                                        />
                                      </div>
                                      <div>
                                        <label className="text-[10px] text-muted-foreground block mb-0.5">Method</label>
                                        <select
                                          value={quickPayMethod}
                                          onChange={e => setQuickPayMethod(e.target.value)}
                                          className="w-full h-8 rounded border border-input bg-background px-2 text-xs"
                                        >
                                          {PAYMENT_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
                                        </select>
                                      </div>
                                      <div>
                                        <label className="text-[10px] text-muted-foreground block mb-0.5">Reference</label>
                                        <input
                                          type="text"
                                          value={quickPayRef}
                                          onChange={e => setQuickPayRef(e.target.value)}
                                          placeholder="EFT ref / cheque #"
                                          className="w-full h-8 rounded border border-input bg-background px-2 text-xs"
                                        />
                                      </div>
                                    </div>
                                    {quickPayError && <p className="text-[10px] text-destructive">{quickPayError}</p>}
                                    <Button
                                      size="sm"
                                      className="h-7 text-xs"
                                      disabled={quickPaying}
                                      onClick={() => handleQuickPay(inv.supplier_id ?? null)}
                                    >
                                      {quickPaying ? "Saving…" : "Record Payment"}
                                    </Button>
                                  </div>
                                </WriteGuard>
                              )}

                              {/* 3L-E: Invoice attachment */}
                              <div>
                                <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Invoice Document</p>
                                <AttachmentStrip
                                  entityType="INVOICE"
                                  entityId={inv.invoice_id}
                                  attachmentType="INVOICE_COPY"
                                  accept="image/*,application/pdf"
                                  compact
                                />
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : tab === "outstanding" ? (
        /* Outstanding tab */
        <div className="space-y-4">
          {/* Aging bands */}
          {agingLoading && <p className="text-xs text-muted-foreground">Loading aging report…</p>}
          {aging && (
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              {([
                { key: "current", label: "Current",   color: "bg-muted/40 text-foreground" },
                { key: "1_30",    label: "1–30 days", color: "bg-amber-50 text-amber-700 border-amber-200" },
                { key: "31_60",   label: "31–60 days",color: "bg-orange-50 text-orange-700 border-orange-200" },
                { key: "61_90",   label: "61–90 days",color: "bg-red-50 text-red-700 border-red-200" },
                { key: "90_plus", label: "90+ days",  color: "bg-destructive/10 text-destructive border-destructive/30" },
              ] as const).map(({ key, label, color }) => {
                const band = aging[key];
                return (
                  <div key={key} className={`border rounded-xl px-3 py-3 ${color}`}>
                    <p className="text-[10px] font-medium uppercase tracking-wide opacity-70">{label}</p>
                    <p className="text-lg font-bold tabular-nums">{formatCurrency(band.total_outstanding)}</p>
                    <p className="text-[10px] opacity-70">{band.count} invoice{band.count !== 1 ? "s" : ""}</p>
                  </div>
                );
              })}
            </div>
          )}

          {outstanding && outstanding.overdue_count > 0 && (
            <div className="bg-destructive/10 border border-destructive/30 rounded-xl px-4 py-3 flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span><strong>{outstanding.overdue_count}</strong> overdue invoice{outstanding.overdue_count !== 1 ? "s" : ""} — total overdue: <strong>{formatCurrency(outstanding.overdue_amount)}</strong></span>
            </div>
          )}

          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {!outstanding || outstanding.outstanding_invoices.length === 0 ? (
              <div className="p-12 text-center text-sm text-muted-foreground">No outstanding invoices. All up to date.</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Invoice #</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Supplier</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">Total</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">Outstanding</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Due Date</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {outstanding.outstanding_invoices.map((inv) => (
                    <tr key={inv.invoice_id} className={`border-b border-border last:border-0 ${inv.is_overdue ? "bg-destructive/5" : "hover:bg-muted/30"} transition-colors`}>
                      <td className="px-4 py-3 font-mono text-xs">{inv.invoice_number}</td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">{inv.supplier_name ?? "—"}</td>
                      <td className="px-4 py-3 text-right text-muted-foreground text-sm">{formatCurrency(inv.total_amount)}</td>
                      <td className="px-4 py-3 text-right font-semibold">
                        <span className={inv.is_overdue ? "text-destructive" : "text-amber-600"}>
                          {formatCurrency(inv.outstanding_balance ?? inv.total_amount)}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {inv.due_date ? (
                          <span className={inv.is_overdue ? "text-destructive font-medium text-xs" : "text-muted-foreground text-xs"}>
                            {inv.is_overdue && <AlertTriangle className="w-3 h-3 inline mr-1" />}
                            {formatDate(inv.due_date)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={invoiceStatusVariant[inv.status] ?? "outline"} className="text-xs">{inv.status.replace(/_/g, " ")}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      ) : null}

      {/* ── Labour tab ── */}
      {tab === "labour" && (
        <div className="space-y-4">
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 text-xs text-amber-700 flex items-center gap-2">
            <Hammer className="w-3.5 h-3.5 shrink-0" />
            These job cards are approved for payment. Click Pay to record the labour payment and mark them as Paid.
          </div>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {labourJcs.length === 0 ? (
              <div className="p-12 text-center text-sm text-muted-foreground">No job cards pending payment. Approve payment on the Labour page first.</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Job Card #</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Worker / Team</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Description</th>
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">Amount</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {labourJcs.map(jc => (
                    <tr key={jc.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 font-mono text-xs font-medium">{jc.job_card_number}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{jc.worker_name || jc.team_name || "—"}</td>
                      <td className="px-4 py-3 text-xs max-w-48 truncate">{jc.work_description}</td>
                      <td className="px-4 py-3 text-right font-semibold">{formatCurrency(jc.total_amount)}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{jc.work_date ? formatDate(jc.work_date) : "—"}</td>
                      <td className="px-4 py-3">
                        <WriteGuard>
                          <Button size="sm" className="h-7 text-xs" onClick={() => { setPayingJc(jc); setJcPayRef(jc.job_card_number); }}>Pay</Button>
                        </WriteGuard>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Pay labour modal */}
          {payingJc && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
              <div className="bg-card border border-border rounded-xl w-full max-w-sm p-6 space-y-4 animate-fade-in">
                <h2 className="font-semibold text-base">Record Labour Payment</h2>
                <p className="text-sm text-muted-foreground">{payingJc.job_card_number} — {formatCurrency(payingJc.total_amount)}</p>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Payment Reference</label>
                  <Input value={jcPayRef} onChange={e => setJcPayRef(e.target.value)} placeholder={payingJc.job_card_number} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Payment Date</label>
                  <Input type="date" value={jcPayDate} onChange={e => setJcPayDate(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs text-muted-foreground">Notes (optional)</label>
                  <Input value={jcPayNotes} onChange={e => setJcPayNotes(e.target.value)} placeholder="e.g. EFT, cash, etc." />
                </div>
                <div className="flex gap-2">
                  <Button onClick={handlePayLabour} disabled={jcPaying} className="flex-1">{jcPaying ? "Paying…" : "Confirm Payment"}</Button>
                  <Button variant="outline" onClick={() => setPayingJc(null)} className="flex-1">Cancel</Button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {showCaptureInvoice && selectedProjectId && (
        <CaptureInvoiceModal
          projectId={selectedProjectId}
          suppliers={suppliers}
          onClose={() => setShowCaptureInvoice(false)}
          onCreated={(inv) => { setInvoices((prev) => [inv, ...prev]); setShowCaptureInvoice(false); }}
        />
      )}
      {showCapturePayment && selectedProjectId && (
        <CapturePaymentModal
          projectId={selectedProjectId}
          suppliers={suppliers}
          onClose={() => setShowCapturePayment(false)}
          onCreated={(p) => { setPayments((prev) => [p, ...prev]); setShowCapturePayment(false); }}
        />
      )}
    </div>
  );
}
