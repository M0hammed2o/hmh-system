/**
 * Owner View — project-focused snapshot.
 *
 * Sections:
 *   1. Project selector
 *   2. Project details card (name, sites, lots, status, progress)
 *   3. Fuel total for the year
 *   4. Quick Access (Deliveries, Warehouse, Reconciliation, WhatsApp Queue, Milestones)
 *
 * Removed: Vehicle Costs Today/Month, Open Alerts card, Pending Invoices,
 *          Open POs, Active Sites, Active Projects, Total Paid, Pending Approvals.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  RefreshCw, ChevronRight, AlertTriangle,
  Truck, Warehouse, FileCheck2, MessageSquare, Flag,
  Droplet, FolderKanban, CheckCircle2,
} from "lucide-react";
import { dashboardApi, type ProjectOperation, type DashboardStats } from "@/api/dashboard";
import { sitesApi } from "@/api/sites";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import client from "@/api/client";

// ── helpers ────────────────────────────────────────────────────────────────────

function fmtR(n: number) {
  if (n >= 1_000_000) return `R${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `R${(n / 1_000).toFixed(0)}K`;
  return `R${n.toFixed(0)}`;
}

function timeGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

// ── Quick-access tile ─────────────────────────────────────────────────────────

function QuickTile({
  label, to, icon: Icon,
}: { label: string; to: string; icon: React.ElementType }) {
  return (
    <Link to={to}>
      <div className="bg-card border border-border rounded-xl p-3 flex items-center gap-3 hover:bg-muted/40 active:scale-95 transition-all">
        <Icon className="w-5 h-5 text-muted-foreground shrink-0" />
        <span className="text-sm font-medium">{label}</span>
        <ChevronRight className="w-4 h-4 text-muted-foreground ml-auto shrink-0" />
      </div>
    </Link>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ACTIVE:    "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    PLANNED:   "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    PAUSED:    "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
    COMPLETED: "bg-muted text-muted-foreground",
  };
  return (
    <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-full", colors[status] ?? colors.PLANNED)}>
      {status}
    </span>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OwnerDashboardPage() {
  const [operations,   setOperations]   = useState<ProjectOperation[]>([]);
  const [stats,        setStats]        = useState<DashboardStats | null>(null);
  const [selectedId,   setSelectedId]   = useState<string>("");
  const [siteCount,    setSiteCount]    = useState<number | null>(null);
  const [projectStatus, setProjectStatus] = useState<string>("ACTIVE");
  const [fuelYear,     setFuelYear]     = useState<number | null>(null);
  const [userName,     setUserName]     = useState("");
  const [loading,      setLoading]      = useState(true);
  const [refreshing,   setRefreshing]   = useState(false);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true); else setRefreshing(true);
    try {
      const [ops, st] = await Promise.allSettled([
        dashboardApi.getProjectOperations(),
        dashboardApi.getStats(),
      ]);

      const opList: ProjectOperation[] = ops.status === "fulfilled" ? ops.value : [];
      const statsVal: DashboardStats | null = st.status === "fulfilled" ? st.value : null;

      setOperations(opList);
      setStats(statsVal);

      if (opList.length > 0 && !selectedId) {
        setSelectedId(opList[0].project_id);
      }

      // Fuel total for the year — use stats aggregate
      if (statsVal) setFuelYear(statsVal.fuel_total_cost ?? null);

      // User name
      try {
        const me = await client.get<{ data: { full_name: string } }>("/users/me");
        setUserName(me.data.data.full_name.split(" ")[0]);
      } catch { /* ignore */ }

    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedId]);

  useEffect(() => { load(); }, []);   // intentionally run once on mount

  // When selected project changes, fetch site count and project status
  useEffect(() => {
    if (!selectedId) return;
    setSiteCount(null);
    setProjectStatus("ACTIVE");

    sitesApi.list(selectedId)
      .then(s => setSiteCount(s.length))
      .catch(() => setSiteCount(0));

    // Fetch project status from the project list
    client.get<{ data: { status?: string }[] }>("/projects/", { params: { limit: 100 } })
      .then(res => {
        const proj = (res.data.data as Array<{ id?: string; status?: string }>)
          .find(p => p.id === selectedId);
        if (proj?.status) setProjectStatus(proj.status);
      })
      .catch(() => {});
  }, [selectedId]);

  const selected = operations.find(op => op.project_id === selectedId);

  const progressColor =
    (selected?.progress_pct ?? 0) >= 75 ? "bg-green-500"
    : (selected?.progress_pct ?? 0) >= 40 ? "bg-blue-500"
    : (selected?.progress_pct ?? 0) > 0 ? "bg-amber-500"
    : "bg-muted-foreground/30";

  if (loading) {
    return (
      <div className="space-y-4 max-w-lg mx-auto animate-fade-in">
        <Skeleton className="h-8 w-52 rounded-xl" />
        <Skeleton className="h-10 rounded-xl" />
        <Skeleton className="h-48 rounded-2xl" />
        <Skeleton className="h-20 rounded-2xl" />
        {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-12 rounded-xl" />)}
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in max-w-lg mx-auto">

      {/* ── Greeting ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">
            {timeGreeting()}{userName ? `, ${userName}` : ""} 👋
          </h1>
          <p className="text-sm text-muted-foreground">
            {new Date().toLocaleDateString("en-ZA", {
              weekday: "long", day: "numeric", month: "long",
            })}
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="p-2 rounded-lg hover:bg-muted disabled:opacity-50"
        >
          <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
        </button>
      </div>

      {/* ── Project selector ── */}
      {operations.length > 0 && (
        <div>
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide block mb-1.5">
            Select Project
          </label>
          <select
            value={selectedId}
            onChange={e => setSelectedId(e.target.value)}
            className="w-full h-10 rounded-xl border border-border bg-card px-3 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary/30"
          >
            {operations.map(op => (
              <option key={op.project_id} value={op.project_id}>
                {op.project_code ? `${op.project_code} — ` : ""}{op.project_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* ── Project details card ── */}
      {selected ? (
        <Link to="/projects" className="block">
          <div className="bg-card border border-border rounded-2xl p-5 space-y-4 hover:bg-muted/20 active:scale-[0.98] transition-all">
            {/* Header */}
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-bold text-base leading-tight truncate">{selected.project_name}</p>
                {selected.project_code && (
                  <p className="text-xs text-muted-foreground mt-0.5">{selected.project_code}</p>
                )}
              </div>
              <StatusBadge status={projectStatus} />
            </div>

            {/* Stats row */}
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-muted/40 rounded-xl py-2.5 px-2">
                <p className="text-xl font-bold leading-none">
                  {siteCount !== null ? siteCount : "—"}
                </p>
                <p className="text-[11px] text-muted-foreground mt-0.5">Sites</p>
              </div>
              <div className="bg-muted/40 rounded-xl py-2.5 px-2">
                <p className="text-xl font-bold leading-none">{selected.total_lots}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">Lots</p>
              </div>
              <div className="bg-green-500/10 rounded-xl py-2.5 px-2">
                <p className="text-xl font-bold leading-none text-green-600">{selected.lots_completed}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">Completed</p>
              </div>
            </div>

            {/* Progress */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Overall progress</span>
                <span className="font-semibold text-foreground">{selected.progress_pct}%</span>
              </div>
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className={cn("h-full rounded-full transition-all duration-700", progressColor)}
                  style={{ width: `${selected.progress_pct}%` }}
                />
              </div>
            </div>

            {/* Milestones summary */}
            <div className="flex items-center justify-between text-xs border-t border-border/50 pt-3">
              <span className="text-muted-foreground flex items-center gap-1">
                <Flag className="w-3 h-3" />
                <strong className="text-foreground">{selected.milestones_completed}</strong>
                /{selected.total_milestones} milestones done
              </span>
              {selected.open_alerts > 0 && (
                <span className="flex items-center gap-1 text-destructive font-medium">
                  <AlertTriangle className="w-3 h-3" />
                  {selected.open_alerts} alert{selected.open_alerts !== 1 ? "s" : ""}
                </span>
              )}
              {selected.open_alerts === 0 && (
                <span className="flex items-center gap-1 text-green-600">
                  <CheckCircle2 className="w-3 h-3" />
                  No open alerts
                </span>
              )}
            </div>
          </div>
        </Link>
      ) : (
        <div className="bg-card border border-border rounded-2xl p-6 text-center text-sm text-muted-foreground">
          <FolderKanban className="w-8 h-8 mx-auto mb-2 opacity-30" />
          No projects found.{" "}
          <Link to="/projects" className="text-primary hover:underline">Create one →</Link>
        </div>
      )}

      {/* ── Fuel total (year-to-date) ── */}
      <div className="bg-card border border-border rounded-2xl p-4 flex items-center gap-4">
        <div className="w-11 h-11 rounded-xl bg-amber-500/10 flex items-center justify-center shrink-0">
          <Droplet className="w-5 h-5 text-amber-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Fuel Cost (Year-to-date)</p>
          <p className="text-2xl font-bold leading-tight mt-0.5">
            {fuelYear != null ? fmtR(fuelYear) : "—"}
          </p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            {fuelYear == null ? "Live data unavailable" : "Aggregate across all projects"}
          </p>
        </div>
        <Link to="/fuel" className="shrink-0 p-1.5 rounded-lg hover:bg-muted">
          <ChevronRight className="w-5 h-5 text-muted-foreground" />
        </Link>
      </div>

      {/* ── Quick Access ── */}
      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Quick Access</p>
        <div className="space-y-2">
          <QuickTile label="Deliveries"     to="/deliveries"        icon={Truck} />
          <QuickTile label="Stock / Warehouse" to="/warehouse"      icon={Warehouse} />
          <QuickTile label="Reconciliation" to="/reconciliation"    icon={FileCheck2} />
          <QuickTile label="WhatsApp Queue" to="/whatsapp-queue"    icon={MessageSquare} />
          <QuickTile label="Milestones"     to="/milestones"        icon={Flag} />
        </div>
      </div>

    </div>
  );
}
