/**
 * Labour Page — Job Cards with full approval chain.
 * Flow: Draft → Submit → Site Approve → Office Approve → (Owner if >R10k) → Payment Approve → Paid
 */
import { useEffect, useState, useCallback } from "react";
import { Plus, Check, X, ChevronRight, HardHat, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { jobCardsApi, type JobCard, type JobCardCreate, type JobCardStatus, type JobCardWorkType } from "@/api/jobCards";
import { projectsApi, type Project } from "@/api/projects";
import { cn } from "@/lib/utils";
import client from "@/api/client";

function fmt(n: number) {
  return `R${n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function timeAgo(iso: string) {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// Status display
const STATUS_STEPS: JobCardStatus[] = [
  "DRAFT", "SUBMITTED", "SITE_APPROVED", "OFFICE_APPROVED",
  "OWNER_APPROVED", "PAYMENT_APPROVED", "PAID",
];

const STATUS_LABEL: Record<JobCardStatus, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  SITE_APPROVED: "Site Approved",
  OFFICE_APPROVED: "Office Approved",
  OWNER_APPROVED: "Owner Approved",
  PAYMENT_APPROVED: "Payment Approved",
  PAID: "Paid",
  REJECTED: "Rejected",
};

const STATUS_BADGE: Record<JobCardStatus, "default" | "secondary" | "success" | "destructive" | "outline"> = {
  DRAFT: "outline",
  SUBMITTED: "secondary",
  SITE_APPROVED: "secondary",
  OFFICE_APPROVED: "default",
  OWNER_APPROVED: "default",
  PAYMENT_APPROVED: "success",
  PAID: "success",
  REJECTED: "destructive",
};

// ── Create modal ──────────────────────────────────────────────────────────────

interface Site { id: string; name: string; }

function CreateJobCardModal({ projectId, sites, onClose, onCreated }: {
  projectId: string; sites: Site[]; onClose: () => void; onCreated: () => void;
}) {
  const [form, setForm] = useState<JobCardCreate & { site_id: string }>({
    site_id: sites[0]?.id || "",
    work_description: "",
    work_type: "DAILY_LABOUR",
    worker_name: "",
    quantity: 1,
    unit: "days",
    rate: 0,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const total = (form.quantity || 0) * (form.rate || 0);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      await jobCardsApi.create(projectId, form);
      onCreated(); onClose();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-t-2xl sm:rounded-2xl w-full sm:max-w-md max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border shrink-0">
          <h2 className="text-base font-semibold">New Job Card</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>
        <form onSubmit={submit} className="flex-1 overflow-y-auto p-5 space-y-4">
          <div className="space-y-1.5">
            <Label>Site *</Label>
            <select value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" required>
              {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label>Work Description *</Label>
            <Input value={form.work_description} onChange={(e) => setForm({ ...form, work_description: e.target.value })} placeholder="e.g. Brickwork Lot 5" required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Work Type</Label>
              <select value={form.work_type} onChange={(e) => setForm({ ...form, work_type: e.target.value as JobCardWorkType })} className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
                {(["DAILY_LABOUR", "CONTRACT", "SUBCONTRACTOR", "OVERTIME"] as JobCardWorkType[]).map((t) => (
                  <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>Worker / Team</Label>
              <Input value={form.worker_name || ""} onChange={(e) => setForm({ ...form, worker_name: e.target.value })} placeholder="Name" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1.5">
              <Label>Qty</Label>
              <Input type="number" min="0.01" step="any" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: parseFloat(e.target.value) || 1 })} />
            </div>
            <div className="space-y-1.5">
              <Label>Unit</Label>
              <Input value={form.unit || ""} onChange={(e) => setForm({ ...form, unit: e.target.value })} placeholder="days" />
            </div>
            <div className="space-y-1.5">
              <Label>Rate (R)</Label>
              <Input type="number" min="0" step="0.01" value={form.rate} onChange={(e) => setForm({ ...form, rate: parseFloat(e.target.value) || 0 })} />
            </div>
          </div>
          <div className="bg-muted/40 rounded-lg p-3 flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Total</span>
            <span className={cn("text-lg font-bold", total >= 10000 ? "text-amber-500" : "")}>{fmt(total)}</span>
          </div>
          {total >= 10000 && (
            <div className="flex items-start gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
              <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-600 dark:text-amber-400">Owner approval required for amounts ≥ R10,000.</p>
            </div>
          )}
          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
        </form>
        <div className="px-5 pb-5 pt-3 border-t border-border shrink-0 flex gap-2">
          <Button disabled={loading} onClick={submit} className="flex-1">{loading ? "Creating…" : "Create Job Card"}</Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Job card detail / action modal ────────────────────────────────────────────

function JobCardModal({ jc, onClose, onUpdated }: { jc: JobCard; onClose: () => void; onUpdated: () => void }) {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [result, setResult] = useState("");

  const act = async (fn: () => Promise<unknown>, label: string) => {
    setLoading(label); setError("");
    try { await fn(); setResult(`${label} successful`); onUpdated(); }
    catch (err: unknown) { setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Action failed."); }
    finally { setLoading(null); }
  };

  // Which actions are available for this status
  const canSubmit = jc.status === "DRAFT";
  const canSiteApprove = jc.status === "SUBMITTED";
  const canOfficeApprove = jc.status === "SITE_APPROVED";
  const canOwnerApprove = jc.status === "OFFICE_APPROVED" && jc.owner_approval_required;
  const canPaymentApprove = jc.status === (jc.owner_approval_required ? "OWNER_APPROVED" : "OFFICE_APPROVED");
  const canPay = jc.status === "PAYMENT_APPROVED";
  const canReject = !["PAID", "REJECTED"].includes(jc.status);

  // Progress steps
  const steps = jc.owner_approval_required
    ? ["DRAFT", "SUBMITTED", "SITE_APPROVED", "OFFICE_APPROVED", "OWNER_APPROVED", "PAYMENT_APPROVED", "PAID"]
    : ["DRAFT", "SUBMITTED", "SITE_APPROVED", "OFFICE_APPROVED", "PAYMENT_APPROVED", "PAID"];

  const stepIndex = jc.status === "REJECTED" ? -1 : steps.indexOf(jc.status);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto animate-fade-in">
        <div className="sticky top-0 bg-card border-b border-border px-5 py-4 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-semibold">{jc.job_card_number}</h2>
              <Badge variant={STATUS_BADGE[jc.status]} className="text-xs">{STATUS_LABEL[jc.status]}</Badge>
              {jc.owner_approval_required && <Badge variant="secondary" className="text-xs">Owner Req.</Badge>}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              {jc.work_type.replace(/_/g, " ")} · {jc.worker_name || jc.team_name || "Unassigned"} · {timeAgo(jc.created_at)}
            </p>
          </div>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* Progress bar */}
          {jc.status !== "REJECTED" && (
            <div className="space-y-2">
              <div className="flex items-center gap-1">
                {steps.map((step, i) => (
                  <div key={step} className="flex items-center flex-1">
                    <div className={cn(
                      "w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold border shrink-0",
                      i < stepIndex ? "bg-green-500 border-green-500 text-white" :
                      i === stepIndex ? "bg-primary border-primary text-primary-foreground" :
                      "bg-muted border-border text-muted-foreground"
                    )}>
                      {i < stepIndex ? <Check className="w-3 h-3" /> : i + 1}
                    </div>
                    {i < steps.length - 1 && (
                      <div className={cn("flex-1 h-0.5 mx-0.5", i < stepIndex ? "bg-green-500" : "bg-muted")} />
                    )}
                  </div>
                ))}
              </div>
              <div className="flex justify-between text-[10px] text-muted-foreground">
                {steps.map((step, i) => (
                  <span key={step} className={cn("text-center", i === stepIndex ? "text-primary font-medium" : "")}>
                    {STATUS_LABEL[step as JobCardStatus].replace(" ", "\n")}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Details */}
          <div className="bg-muted/30 rounded-lg p-3 space-y-1.5 text-sm">
            <p className="font-medium">{jc.work_description}</p>
            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              <span>{jc.quantity} {jc.unit || ""} × {fmt(jc.rate)}</span>
              <span className="font-bold text-foreground text-base">{fmt(jc.total_amount)}</span>
            </div>
            {jc.work_date && <p className="text-xs text-muted-foreground">Work date: {jc.work_date}</p>}
            {jc.notes && <p className="text-xs text-muted-foreground">{jc.notes}</p>}
          </div>

          {/* Approval timestamps */}
          {[
            ["Submitted", jc.submitted_at],
            ["Site approved", jc.site_approved_at],
            ["Office approved", jc.office_approved_at],
            ["Owner approved", jc.owner_approved_at],
            ["Payment approved", jc.payment_approved_at],
          ].filter(([, t]) => t).map(([label, ts]) => (
            <div key={label as string} className="flex items-center justify-between text-xs border-b border-border pb-1.5">
              <span className="text-muted-foreground">{label as string}</span>
              <span className="flex items-center gap-1 text-green-600 dark:text-green-400 font-medium">
                <Check className="w-3 h-3" />{timeAgo(ts as string)}
              </span>
            </div>
          ))}

          {jc.rejection_reason && (
            <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-3 text-sm text-destructive">
              Rejected: {jc.rejection_reason}
            </div>
          )}

          {showReject && (
            <Input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="Rejection reason *" className="text-sm" autoFocus />
          )}

          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
          {result && <p className="text-sm text-green-600 dark:text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2">{result}</p>}

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-1">
            {canSubmit && <Button size="sm" onClick={() => act(() => jobCardsApi.submit(jc.id), "Submit")} disabled={loading !== null} className="h-8 text-xs">Submit</Button>}
            {canSiteApprove && <Button size="sm" onClick={() => act(() => jobCardsApi.siteApprove(jc.id), "Site approve")} disabled={loading !== null} className="h-8 text-xs"><Check className="w-3.5 h-3.5 mr-1" />Site Approve</Button>}
            {canOfficeApprove && <Button size="sm" onClick={() => act(() => jobCardsApi.officeApprove(jc.id), "Office approve")} disabled={loading !== null} className="h-8 text-xs"><Check className="w-3.5 h-3.5 mr-1" />Office Approve</Button>}
            {canOwnerApprove && <Button size="sm" onClick={() => act(() => jobCardsApi.ownerApprove(jc.id), "Owner approve")} disabled={loading !== null} className="h-8 text-xs"><Check className="w-3.5 h-3.5 mr-1" />Owner Approve</Button>}
            {canPaymentApprove && <Button size="sm" onClick={() => act(() => jobCardsApi.approvePayment(jc.id), "Approve payment")} disabled={loading !== null} className="h-8 text-xs"><Check className="w-3.5 h-3.5 mr-1" />Approve for Payment</Button>}
            {canPay && <Button size="sm" onClick={() => act(() => jobCardsApi.markPaid(jc.id), "Mark paid")} disabled={loading !== null} className="h-8 text-xs bg-green-600 hover:bg-green-700">Mark Paid</Button>}
            {canReject && !showReject && <Button size="sm" variant="outline" onClick={() => setShowReject(true)} disabled={loading !== null} className="h-8 text-xs text-destructive border-destructive/30"><X className="w-3.5 h-3.5 mr-1" />Reject</Button>}
            {showReject && <Button size="sm" variant="destructive" onClick={() => act(() => jobCardsApi.reject(jc.id, rejectReason), "Reject")} disabled={!rejectReason.trim() || loading !== null} className="h-8 text-xs">Confirm Reject</Button>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function LabourPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [sites, setSites] = useState<Site[]>([]);
  const [jobCards, setJobCards] = useState<JobCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [showCreate, setShowCreate] = useState(false);
  const [selected, setSelected] = useState<JobCard | null>(null);

  useEffect(() => {
    projectsApi.list(1, 100).then((r) => {
      setProjects(r.items);
      if (r.items.length) setProjectId(r.items[0].id);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const loadData = useCallback(async () => {
    if (!projectId) return;
    const [jcs, sitesRes] = await Promise.allSettled([
      jobCardsApi.list(projectId),
      client.get<{ data: Site[] }>(`/projects/${projectId}/sites/`),
    ]);
    if (jcs.status === "fulfilled") setJobCards(jcs.value);
    if (sitesRes.status === "fulfilled") setSites(sitesRes.value.data.data || []);
  }, [projectId]);

  useEffect(() => { if (projectId) loadData(); }, [projectId, loadData]);

  const filtered = statusFilter === "ALL" ? jobCards : jobCards.filter((j) => j.status === statusFilter);

  const pendingPayment = jobCards.filter((j) => ["OFFICE_APPROVED", "OWNER_APPROVED", "PAYMENT_APPROVED"].includes(j.status));
  const pendingPaymentAmount = pendingPayment.reduce((s, j) => s + j.total_amount, 0);

  const STATUS_FILTERS = ["ALL", "DRAFT", "SUBMITTED", "SITE_APPROVED", "OFFICE_APPROVED", "OWNER_APPROVED", "PAYMENT_APPROVED", "PAID", "REJECTED"];

  if (loading) return <div className="space-y-4">{[1,2,3].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>;

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Labour</h1>
          {pendingPayment.length > 0 && (
            <p className="text-sm text-amber-500 font-medium">
              {pendingPayment.length} job card{pendingPayment.length !== 1 ? "s" : ""} pending payment — {fmt(pendingPaymentAmount)}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="h-9 rounded-md border border-input bg-background px-3 text-sm max-w-[180px]">
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <Button size="sm" onClick={() => setShowCreate(true)}><Plus className="w-4 h-4" />New Job Card</Button>
        </div>
      </div>

      {/* Status filters */}
      <div className="flex overflow-x-auto gap-1 pb-1">
        {STATUS_FILTERS.map((s) => (
          <button key={s} onClick={() => setStatusFilter(s)} className={cn("shrink-0 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors", statusFilter === s ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}>
            {s === "ALL" ? `All (${jobCards.length})` : STATUS_LABEL[s as JobCardStatus] || s}
            {s !== "ALL" && <span className="ml-1 opacity-60">({jobCards.filter((j) => j.status === s).length})</span>}
          </button>
        ))}
      </div>

      {/* Approval chain explainer */}
      <div className="bg-card border border-border rounded-xl px-4 py-3 hidden sm:flex items-center gap-2 text-xs text-muted-foreground overflow-x-auto">
        {["Draft", "Submitted", "Site ✓", "Office ✓", "Owner ✓*", "Payment ✓", "Paid"].map((s, i, arr) => (
          <div key={s} className="flex items-center gap-2 shrink-0">
            <span>{s}</span>
            {i < arr.length - 1 && <ChevronRight className="w-3 h-3" />}
          </div>
        ))}
        <span className="ml-2 text-[10px]">* Owner approval only required for amounts ≥ R10,000</span>
      </div>

      {/* Job cards list */}
      {filtered.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center">
          <HardHat className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No job cards in this category.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((jc) => (
            <button key={jc.id} onClick={() => setSelected(jc)} className="w-full text-left bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-4 hover:bg-muted/30 active:scale-[0.99] transition-all">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-sm font-mono">{jc.job_card_number}</span>
                  <Badge variant={STATUS_BADGE[jc.status]} className="text-xs">{STATUS_LABEL[jc.status]}</Badge>
                  {jc.owner_approval_required && <Badge variant="secondary" className="text-[10px]">Owner Req.</Badge>}
                  <span className="text-sm font-bold ml-auto">{fmt(jc.total_amount)}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 truncate">
                  {jc.work_description} · {jc.worker_name || jc.team_name || "Unassigned"} · {timeAgo(jc.created_at)}
                </p>
              </div>
              <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
            </button>
          ))}
        </div>
      )}

      {showCreate && <CreateJobCardModal projectId={projectId} sites={sites} onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); loadData(); }} />}
      {selected && <JobCardModal jc={selected} onClose={() => setSelected(null)} onUpdated={() => { loadData(); setSelected(null); }} />}
    </div>
  );
}
