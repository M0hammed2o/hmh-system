/**
 * WorkDonePage — Subcontractor Progress/Payment Claim
 * Flow: Draft → Submit → Site Approve → Office Approve → Paid (or Rejected)
 * Duplicate payment protection enforced server-side.
 */

import { useEffect, useState, useCallback } from "react";
import { Plus, X, CheckCircle, XCircle, AlertTriangle, ClipboardList, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { workDoneApi, type WorkDone, type WorkDoneCreate, type WorkDoneStatus } from "@/api/workDone";
import { projectsApi, type Project } from "@/api/projects";
import { cn } from "@/lib/utils";
import client from "@/api/client";

interface Site      { id: string; name: string; }
interface Lot       { id: string; lot_number: string; description: string | null; }
interface Milestone { id: string; stage_name: string; status: string; }
interface Supplier  { id: string; name: string; }

const fmt = (n: number) =>
  `R${Number(n).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STATUS_LABEL: Record<WorkDoneStatus, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  SITE_APPROVED: "Site Approved",
  OFFICE_APPROVED: "Office Approved",
  PAID: "Paid",
  REJECTED: "Rejected",
};

const STATUS_COLOR: Record<WorkDoneStatus, string> = {
  DRAFT: "bg-muted text-muted-foreground",
  SUBMITTED: "bg-blue-100 text-blue-700",
  SITE_APPROVED: "bg-cyan-100 text-cyan-700",
  OFFICE_APPROVED: "bg-amber-100 text-amber-700",
  PAID: "bg-green-100 text-green-700",
  REJECTED: "bg-red-100 text-red-700",
};

// ── Create modal ──────────────────────────────────────────────────────────────

function CreateModal({
  projectId, sites, suppliers,
  onClose, onCreated,
}: {
  projectId: string;
  sites: Site[];
  suppliers: Supplier[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState<WorkDoneCreate>({
    site_id: sites[0]?.id || "",
    supplier_id: "",
    work_description: "",
    quantity: 1,
    unit: "m2",
    rate: 0,
    month: new Date().toISOString().slice(0, 7) + "-01",
  });
  const [lots,       setLots]       = useState<Lot[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Load lots when site changes
  useEffect(() => {
    if (!form.site_id) { setLots([]); return; }
    client.get<{ data: { items?: Lot[]; lots?: Lot[] } | Lot[] }>(
      `/projects/${projectId}/lots/`, { params: { site_id: form.site_id, limit: 200 } }
    ).then(r => {
      const raw = r.data.data;
      const arr: Lot[] = Array.isArray(raw) ? raw : ((raw as { items?: Lot[]; lots?: Lot[] }).items ?? (raw as { lots?: Lot[] }).lots ?? []);
      setLots(arr);
    }).catch(() => setLots([]));
  }, [form.site_id, projectId]);

  // Load milestones when site changes
  useEffect(() => {
    if (!form.site_id) { setMilestones([]); return; }
    client.get<{ data: Milestone[] }>(
      `/projects/${projectId}/stage-statuses/`, { params: { site_id: form.site_id, limit: 200 } }
    ).then(r => setMilestones(r.data.data ?? []))
     .catch(() => setMilestones([]));
  }, [form.site_id, projectId]);

  const total = (form.quantity || 0) * (form.rate || 0);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      await workDoneApi.create(projectId, form);
      onCreated(); onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string; detail?: string } } })
        ?.response?.data?.message
        || (err as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail
        || "Failed to create record.";
      setError(msg);
    } finally { setLoading(false); }
  };

  const f = (field: keyof WorkDoneCreate, val: unknown) =>
    setForm(prev => ({ ...prev, [field]: val }));

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-t-2xl sm:rounded-2xl w-full sm:max-w-lg max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border shrink-0">
          <h2 className="text-base font-semibold">New Work Done Claim</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>
        <form onSubmit={submit} className="flex-1 overflow-y-auto p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2 space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Subcontractor *</label>
              <select value={form.supplier_id} onChange={e => f("supplier_id", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" required>
                <option value="">— Select —</option>
                {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Site *</label>
              <select value={form.site_id} onChange={e => f("site_id", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm" required>
                {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Month *</label>
              <input type="month" required
                value={form.month.slice(0, 7)}
                onChange={e => f("month", e.target.value + "-01")}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
            {lots.length > 0 && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Lot</label>
                <select value={form.lot_id || ""}
                  onChange={e => f("lot_id", e.target.value || undefined)}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
                  <option value="">— None —</option>
                  {lots.map(l => (
                    <option key={l.id} value={l.id}>
                      {l.lot_number}{l.description ? ` — ${l.description}` : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {milestones.length > 0 && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Milestone</label>
                <select value={form.stage_status_id || ""}
                  onChange={e => f("stage_status_id", e.target.value || undefined)}
                  className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
                  <option value="">— None —</option>
                  {milestones.map(m => (
                    <option key={m.id} value={m.id}>{m.stage_name} ({m.status})</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Work Description *</label>
            <textarea rows={2} required value={form.work_description}
              onChange={e => f("work_description", e.target.value)}
              placeholder="Describe the work done…"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Qty *</label>
              <input type="number" step="0.001" min="0" required value={form.quantity}
                onChange={e => f("quantity", parseFloat(e.target.value) || 0)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Unit</label>
              <input type="text" value={form.unit || ""} placeholder="m2, m, hrs"
                onChange={e => f("unit", e.target.value || null)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Rate (R) *</label>
              <input type="number" step="0.01" min="0" required value={form.rate}
                onChange={e => f("rate", parseFloat(e.target.value) || 0)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
          </div>

          <div className="rounded-lg bg-muted/40 border border-border px-3 py-2 text-sm flex items-center justify-between">
            <span className="text-muted-foreground">Total</span>
            <span className="font-bold text-lg">{fmt(total)}</span>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Comments</label>
            <textarea rows={2} value={form.comments || ""}
              onChange={e => f("comments", e.target.value || null)}
              placeholder="Any additional notes…"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </form>
        <div className="flex gap-2 px-5 py-4 border-t border-border shrink-0">
          <Button variant="outline" onClick={onClose} disabled={loading} className="flex-1">Cancel</Button>
          <Button type="submit" disabled={loading || !form.supplier_id} className="flex-1"
            onClick={e => {
              const form_el = (e.target as HTMLButtonElement).closest("div")?.previousElementSibling?.querySelector("form");
              form_el?.requestSubmit();
            }}>
            {loading ? "Saving…" : "Create Claim"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Reject modal ──────────────────────────────────────────────────────────────

function RejectModal({ onClose, onReject }: { onClose: () => void; onReject: (reason: string) => void }) {
  const [reason, setReason] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4">
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-5 space-y-4">
        <h3 className="font-semibold">Reject Claim</h3>
        <textarea rows={3} value={reason} onChange={e => setReason(e.target.value)}
          placeholder="Reason for rejection…"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
        />
        <div className="flex gap-2">
          <Button variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          <Button variant="destructive" disabled={!reason.trim()} onClick={() => onReject(reason.trim())} className="flex-1">
            Reject
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Row card ──────────────────────────────────────────────────────────────────

function WorkDoneRow({ wd, supplierMap, onAction }: {
  wd: WorkDone;
  supplierMap: Record<string, string>;
  onAction: (action: string, id: string) => void;
}) {
  return (
    <div className="border border-border rounded-xl p-4 bg-card hover:bg-muted/20 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs text-muted-foreground">{wd.work_done_number}</span>
            <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-full", STATUS_COLOR[wd.status])}>
              {STATUS_LABEL[wd.status]}
            </span>
          </div>
          <p className="text-sm font-medium mt-1 truncate">{wd.work_description}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {supplierMap[wd.supplier_id] || "Unknown Supplier"} · {wd.month.slice(0, 7)}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="font-bold text-base">{fmt(wd.amount)}</p>
          <p className="text-xs text-muted-foreground">{wd.quantity} {wd.unit || ""} × {fmt(wd.rate)}</p>
        </div>
      </div>

      {wd.rejection_reason && (
        <div className="mt-2 flex items-start gap-1.5 text-xs text-destructive bg-destructive/10 rounded-lg px-2 py-1.5">
          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
          <span>{wd.rejection_reason}</span>
        </div>
      )}

      <div className="mt-3 flex gap-1.5 flex-wrap">
        {wd.status === "DRAFT" && (
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onAction("submit", wd.id)}>
            Submit
          </Button>
        )}
        {wd.status === "REJECTED" && (
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onAction("submit", wd.id)}>
            Re-submit
          </Button>
        )}
        {wd.status === "SUBMITTED" && (
          <>
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onAction("site-approve", wd.id)}>
              <CheckCircle className="w-3 h-3 mr-1" />Site Approve
            </Button>
            <Button size="sm" variant="outline" className="h-7 text-xs text-destructive hover:bg-destructive/10"
              onClick={() => onAction("reject", wd.id)}>
              <XCircle className="w-3 h-3 mr-1" />Reject
            </Button>
          </>
        )}
        {wd.status === "SITE_APPROVED" && (
          <>
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onAction("office-approve", wd.id)}>
              <CheckCircle className="w-3 h-3 mr-1" />Office Approve
            </Button>
            <Button size="sm" variant="outline" className="h-7 text-xs text-destructive hover:bg-destructive/10"
              onClick={() => onAction("reject", wd.id)}>
              <XCircle className="w-3 h-3 mr-1" />Reject
            </Button>
          </>
        )}
        {wd.status === "OFFICE_APPROVED" && (
          <Button size="sm" className="h-7 text-xs bg-green-600 hover:bg-green-700 text-white"
            onClick={() => onAction("mark-paid", wd.id)}>
            Mark Paid
          </Button>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function WorkDonePage() {
  const [projects,   setProjects]   = useState<Project[]>([]);
  const [sites,      setSites]      = useState<Site[]>([]);
  const [suppliers,  setSuppliers]  = useState<Supplier[]>([]);
  const [records,    setRecords]    = useState<WorkDone[]>([]);
  const [loading,    setLoading]    = useState(false);
  const [projectId,  setProjectId]  = useState("");
  const [filterStatus, setFilterStatus] = useState<WorkDoneStatus | "">("");
  const [filterMonth,  setFilterMonth]  = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [rejectId,   setRejectId]   = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const supplierMap = Object.fromEntries(suppliers.map(s => [s.id, s.name]));

  useEffect(() => {
    projectsApi.list().then(setProjects).catch(() => {});
    client.get<{ data: Supplier[] }>("/suppliers/", { params: { include_inactive: false } })
      .then(r => setSuppliers(r.data.data ?? []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!projectId) { setRecords([]); setSites([]); return; }
    client.get<{ data: { items: Site[] } }>(`/projects/${projectId}/sites/`, { params: { limit: 200 } })
      .then(r => setSites(r.data.data?.items ?? []))
      .catch(() => {});
  }, [projectId]);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filterStatus) params.status = filterStatus;
      if (filterMonth)  params.month  = filterMonth + "-01";
      const data = await workDoneApi.list(projectId, params as Parameters<typeof workDoneApi.list>[1]);
      setRecords(data);
    } finally { setLoading(false); }
  }, [projectId, filterStatus, filterMonth]);

  useEffect(() => { load(); }, [load]);

  const doAction = async (action: string, id: string) => {
    if (action === "reject") { setRejectId(id); return; }
    setActionLoading(true);
    try {
      if (action === "submit")         await workDoneApi.submit(id);
      else if (action === "site-approve") await workDoneApi.siteApprove(id);
      else if (action === "office-approve") await workDoneApi.officeApprove(id);
      else if (action === "mark-paid") await workDoneApi.markPaid(id);
      await load();
    } catch (err: unknown) {
      alert((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Action failed.");
    } finally { setActionLoading(false); }
  };

  const doReject = async (reason: string) => {
    if (!rejectId) return;
    setActionLoading(true);
    try {
      await workDoneApi.reject(rejectId, reason);
      setRejectId(null);
      await load();
    } finally { setActionLoading(false); }
  };

  const pendingCount = records.filter(r => ["SUBMITTED", "SITE_APPROVED", "OFFICE_APPROVED"].includes(r.status)).length;
  const paidTotal    = records.filter(r => r.status === "PAID").reduce((s, r) => s + r.amount, 0);

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <ClipboardList className="w-5 h-5" />
            Work Done / Progress Claims
          </h1>
          <p className="text-sm text-muted-foreground">Subcontractor progress and payment claims</p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(true)} disabled={!projectId}>
          <Plus className="w-4 h-4 mr-1" />New Claim
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <select value={projectId} onChange={e => setProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm flex-1 min-w-[160px]">
          <option value="">— Select project —</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value as WorkDoneStatus | "")}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm">
          <option value="">All statuses</option>
          {(["DRAFT","SUBMITTED","SITE_APPROVED","OFFICE_APPROVED","PAID","REJECTED"] as WorkDoneStatus[]).map(s => (
            <option key={s} value={s}>{STATUS_LABEL[s]}</option>
          ))}
        </select>
        <input type="month" value={filterMonth} onChange={e => setFilterMonth(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          placeholder="Month"
        />
        <Button variant="ghost" size="sm" onClick={load} disabled={loading || !projectId}>
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </Button>
      </div>

      {/* Summary strip */}
      {records.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Total Records", value: records.length.toString() },
            { label: "Pending Payment", value: pendingCount.toString() },
            { label: "Paid This Filter", value: fmt(paidTotal) },
          ].map(({ label, value }) => (
            <div key={label} className="border border-border rounded-xl p-3 bg-card text-center">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="font-bold text-base">{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* List */}
      {!projectId ? (
        <div className="text-center py-12 text-muted-foreground text-sm">
          Select a project to view work done claims.
        </div>
      ) : loading ? (
        <div className="space-y-3">
          {[1,2,3].map(i => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : records.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground text-sm">
          No work done claims found. Create one to get started.
        </div>
      ) : (
        <div className="space-y-3">
          {records.map(wd => (
            <WorkDoneRow key={wd.id} wd={wd} supplierMap={supplierMap} onAction={doAction} />
          ))}
        </div>
      )}

      {showCreate && projectId && (
        <CreateModal
          projectId={projectId}
          sites={sites}
          suppliers={suppliers}
          onClose={() => setShowCreate(false)}
          onCreated={load}
        />
      )}

      {rejectId && (
        <RejectModal
          onClose={() => setRejectId(null)}
          onReject={doReject}
        />
      )}

      {actionLoading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/20">
          <div className="bg-card border border-border rounded-2xl p-6">
            <div className="h-8 w-8 rounded-full border-4 border-primary border-t-transparent animate-spin mx-auto" />
          </div>
        </div>
      )}
    </div>
  );
}
