/**
 * MonthlySubcontractorSummaryPage
 * Aggregated view of subcontractor work done claims by month, project, supplier.
 * Supports filtering and shows paid vs pending breakdown per supplier.
 */

import { useEffect, useState } from "react";
import { BarChart2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { workDoneApi, type WorkDoneSummary } from "@/api/workDone";
import { projectsApi, type Project } from "@/api/projects";
import { cn } from "@/lib/utils";

const fmt = (n: number) =>
  `R${Number(n).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STATUS_COLOR: Record<string, string> = {
  DRAFT:           "bg-muted/60 text-muted-foreground",
  SUBMITTED:       "bg-blue-100 text-blue-700",
  SITE_APPROVED:   "bg-cyan-100 text-cyan-700",
  OFFICE_APPROVED: "bg-amber-100 text-amber-700",
  PAID:            "bg-green-100 text-green-700",
  REJECTED:        "bg-red-100 text-red-700",
};

export default function MonthlySubcontractorSummaryPage() {
  const [projects,  setProjects]  = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [month,     setMonth]     = useState(new Date().toISOString().slice(0, 7));
  const [summary,   setSummary]   = useState<WorkDoneSummary | null>(null);
  const [loading,   setLoading]   = useState(false);

  useEffect(() => {
    projectsApi.list().then(r => setProjects(r.items)).catch(() => {});
  }, []);

  const load = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const data = await workDoneApi.monthlySummary(projectId, {
        month: month + "-01",
      });
      setSummary(data);
    } finally { setLoading(false); }
  };

  useEffect(() => { if (projectId) load(); }, [projectId, month]);

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2">
          <BarChart2 className="w-5 h-5" />
          Monthly Subcontractor Summary
        </h1>
        <p className="text-sm text-muted-foreground">Aggregated progress claims by month and subcontractor</p>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap items-center">
        <select value={projectId} onChange={e => setProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm flex-1 min-w-[180px]">
          <option value="">— Select project —</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
        <input type="month" value={month} onChange={e => setMonth(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        />
        <Button variant="ghost" size="sm" onClick={load} disabled={loading || !projectId}>
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </Button>
      </div>

      {!projectId ? (
        <div className="text-center py-12 text-sm text-muted-foreground">
          Select a project and month to view the summary.
        </div>
      ) : loading ? (
        <div className="space-y-3">
          {[1, 2].map(i => <Skeleton key={i} className="h-32 rounded-xl" />)}
        </div>
      ) : !summary || summary.total_records === 0 ? (
        <div className="text-center py-12 text-sm text-muted-foreground">
          No claims found for this month and project.
        </div>
      ) : (
        <>
          {/* Totals strip */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Total Claims",    value: summary.total_records.toString(), sub: "" },
              { label: "Total Value",     value: fmt(summary.total_amount),        sub: "" },
              { label: "Paid",            value: fmt(summary.paid_amount),         sub: `${fmt(summary.pending_amount)} pending` },
            ].map(({ label, value, sub }) => (
              <div key={label} className="border border-border rounded-xl p-3 bg-card text-center space-y-0.5">
                <p className="text-[11px] text-muted-foreground">{label}</p>
                <p className="font-bold text-base">{value}</p>
                {sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
              </div>
            ))}
          </div>

          {/* Per-supplier breakdown */}
          <div className="space-y-3">
            {summary.by_supplier.map(sup => {
              const paidPct = sup.total_amount > 0
                ? Math.round((sup.paid_amount / sup.total_amount) * 100)
                : 0;
              return (
                <div key={sup.supplier_id} className="border border-border rounded-xl bg-card overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                    <div>
                      <p className="font-semibold text-sm">{sup.supplier_name}</p>
                      <p className="text-xs text-muted-foreground">{sup.count} claim{sup.count !== 1 ? "s" : ""}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-bold">{fmt(sup.total_amount)}</p>
                      <p className="text-xs text-muted-foreground">{fmt(sup.paid_amount)} paid</p>
                    </div>
                  </div>

                  {/* Progress bar */}
                  <div className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-green-500 rounded-full transition-all"
                          style={{ width: `${paidPct}%` }} />
                      </div>
                      <span className="text-xs text-muted-foreground w-8 text-right">{paidPct}%</span>
                    </div>
                  </div>

                  {/* Status badges */}
                  <div className="px-4 pb-3 flex gap-1.5 flex-wrap">
                    {Object.entries(sup.statuses).map(([status, count]) => (
                      <span key={status}
                        className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", STATUS_COLOR[status] ?? "bg-muted text-muted-foreground")}>
                        {status.replace(/_/g, " ")}: {count}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          <p className="text-xs text-muted-foreground text-center">
            Municipality claim data: {summary.total_records} items · {fmt(summary.total_amount)} total · {fmt(summary.paid_amount)} paid
          </p>
        </>
      )}
    </div>
  );
}
