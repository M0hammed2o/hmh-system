import { useEffect, useState } from "react";
import { Plus, CreditCard, CheckCircle2, Clock, FileText, AlertTriangle, Hammer } from "lucide-react";
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
import { paymentsApi, type Payment, type PaymentCreate, type PaymentStatus } from "@/api/payments";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { jobCardsApi, type JobCard } from "@/api/jobCards";
import { formatCurrency, formatDate } from "@/lib/format";
import client from "@/api/client";

interface OutstandingInvoice {
  invoice_id: string;
  invoice_number: string;
  supplier_name: string | null;
  total_amount: number;
  due_date: string | null;
  status: string;
  is_overdue: boolean;
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

const invoiceStatusVariant: Record<RecordStatus, "secondary" | "default" | "success" | "destructive" | "outline"> = {
  DRAFT:      "outline",
  SUBMITTED:  "secondary",
  APPROVED:   "default",
  REJECTED:   "destructive",
  SENT:       "default",
  RECEIVED:   "default",
  MATCHED:    "default",
  PAID:       "success",
  CANCELLED:  "outline",
};

const PAGE_TABS = [
  { key: "payments", label: "Payments" },
  { key: "invoices", label: "Invoices" },
];

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
  const [extracting, setExtracting] = useState(false);
  const [extractMsg, setExtractMsg] = useState("");

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
        {/* AI Extraction — upload invoice PDF/image to auto-fill fields */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-2">
          <p className="text-xs font-medium text-blue-800">✨ Extract from invoice file</p>
          <div className="flex items-center gap-2">
            <input
              type="file"
              accept="image/*,.pdf"
              id="invoice-upload"
              className="text-xs flex-1 file:mr-2 file:text-xs file:rounded file:border-0 file:bg-blue-100 file:text-blue-700 file:px-2 file:py-1"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                setExtracting(true); setExtractMsg("");
                try {
                  const { visionApi } = await import("@/api/vision");
                  const result = await visionApi.extract(f, "invoice");
                  if (result.status === "OCR_NOT_AVAILABLE") {
                    setExtractMsg("AI Vision not configured. Enter fields manually.");
                  } else {
                    const p = result.preview as { invoice_number?: string | null; total_amount?: number | null; date?: string | null; supplier_name?: string | null };
                    setForm(prev => ({
                      ...prev,
                      invoice_number: p.invoice_number ?? prev.invoice_number,
                      total_amount:   p.total_amount   ?? prev.total_amount,
                      invoice_date:   p.date           ?? prev.invoice_date,
                    }));
                    setExtractMsg(result.status === "NEEDS_REVIEW"
                      ? "⚠ Partial extraction — review all fields."
                      : "✓ Fields extracted — confirm before saving.");
                  }
                } catch {
                  setExtractMsg("Extraction failed. Enter manually.");
                } finally { setExtracting(false); }
              }}
            />
            {extracting && <span className="text-xs text-blue-600">Extracting…</span>}
          </div>
          {extractMsg && <p className="text-[10px] text-blue-700">{extractMsg}</p>}
        </div>

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
            <Label>Payment Reference</Label>
            <Input
              value={form.payment_reference ?? ""}
              onChange={(e) => setForm({ ...form, payment_reference: e.target.value || null })}
              placeholder="e.g. EFT-20240601"
            />
          </div>
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
  const [showCaptureInvoice, setShowCaptureInvoice] = useState(false);
  const [showCapturePayment, setShowCapturePayment] = useState(false);

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
                </tr>
              </thead>
              <tbody>
                {payments.map((p) => (
                  <tr key={p.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs">{p.payment_reference ?? p.id.slice(0, 8)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{p.payment_type}</td>
                    <td className="px-4 py-3 font-semibold">{formatCurrency(p.amount_paid)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{p.payment_date ? formatDate(p.payment_date) : "—"}</td>
                    <td className="px-4 py-3">
                      <Badge variant={paymentStatusVariant[p.status]}>{p.status}</Badge>
                    </td>
                  </tr>
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
                      <tr key={inv.invoice_id} className={`border-b border-border last:border-0 transition-colors ${inv.is_overdue ? "bg-destructive/5 hover:bg-destructive/10" : "hover:bg-muted/30"}`}>
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
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* Outstanding tab */
        <div className="space-y-4">
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
                    <th className="text-right px-4 py-3 font-medium text-muted-foreground">Amount</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Due Date</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {outstanding.outstanding_invoices.map((inv) => (
                    <tr key={inv.invoice_id} className={`border-b border-border last:border-0 ${inv.is_overdue ? "bg-destructive/5" : "hover:bg-muted/30"} transition-colors`}>
                      <td className="px-4 py-3 font-mono text-xs">{inv.invoice_number}</td>
                      <td className="px-4 py-3 text-muted-foreground">{inv.supplier_name ?? "—"}</td>
                      <td className="px-4 py-3 text-right font-semibold">{formatCurrency(inv.total_amount)}</td>
                      <td className="px-4 py-3">
                        {inv.due_date ? (
                          <span className={inv.is_overdue ? "text-destructive font-medium" : "text-muted-foreground"}>
                            {inv.is_overdue && <AlertTriangle className="w-3 h-3 inline mr-1" />}
                            {formatDate(inv.due_date)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={invoiceStatusVariant[inv.status as keyof typeof invoiceStatusVariant] ?? "outline"}>{inv.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

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
                        <Button size="sm" className="h-7 text-xs" onClick={() => { setPayingJc(jc); setJcPayRef(jc.job_card_number); }}>Pay</Button>
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
