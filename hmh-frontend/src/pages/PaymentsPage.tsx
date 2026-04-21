import { useEffect, useState } from "react";
import { Plus, CreditCard, CheckCircle2, Clock, FileText } from "lucide-react";
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
import { invoicesApi, type Invoice, type InvoiceCreate } from "@/api/invoices";
import { paymentsApi, type Payment, type PaymentCreate, type PaymentStatus } from "@/api/payments";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { formatCurrency, formatDate } from "@/lib/format";

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

  // Load payments + invoices when project changes
  useEffect(() => {
    if (!selectedProjectId) return;
    setLoading(true);
    setLoadError("");
    Promise.all([
      paymentsApi.list(selectedProjectId),
      invoicesApi.list(selectedProjectId),
    ])
      .then(([pays, invs]) => {
        setPayments(pays);
        setInvoices(invs);
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

  const tabsWithCount = [
    { ...PAGE_TABS[0], count: payments.length },
    { ...PAGE_TABS[1], count: invoices.length },
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

      {/* Project selector */}
      <div className="flex items-center gap-3">
        <label className="text-xs text-muted-foreground whitespace-nowrap">Project</label>
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
        </select>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Total Paid"       value={formatCurrency(totalPaid)} icon={CreditCard}   color="bg-success/10 text-success" />
        <StatCard title="Pending Payments" value={pendingPays}               icon={Clock}        color="bg-warning/10 text-warning" />
        <StatCard title="Paid Payments"    value={paidPays}                  icon={CheckCircle2} color="bg-success/10 text-success" />
        <StatCard title="Pending Invoices" value={pendingInvs}               icon={FileText}     color="bg-secondary/10 text-secondary-foreground" />
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
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {invoices.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">No invoices captured yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Invoice #</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Amount</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Invoice Date</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Due Date</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((inv) => (
                  <tr key={inv.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs">{inv.invoice_number}</td>
                    <td className="px-4 py-3 font-semibold">{formatCurrency(inv.total_amount)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{inv.invoice_date ? formatDate(inv.invoice_date) : "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{inv.due_date ? formatDate(inv.due_date) : "—"}</td>
                    <td className="px-4 py-3">
                      <Badge variant={invoiceStatusVariant[inv.status]}>{inv.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
