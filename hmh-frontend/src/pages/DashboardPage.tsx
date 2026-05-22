/**
 * DashboardPage — Operational Command Center
 *
 * Phase 3F: Answers "What needs attention right now?"
 *
 * Sections (priority order):
 *   1. Open Alerts (if any)
 *   2. Attention bar  — aggregated items requiring action
 *   3. Financial Ops  — invoices, overdue, payments
 *   4. Milestone Ops  — blocked, delayed, in-progress
 *   5. Warehouse Ops  — stock + recent transfers
 *   6. Project Cards  — per-project progress summary
 *   7. Vehicle/Fuel   — costs + flagged entries
 *   8. Quick Access   — navigation shortcuts
 */

import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  FolderKanban, Bell, ShoppingCart, CreditCard,
  Truck, FileSpreadsheet, AlertTriangle, ChevronRight, X, Warehouse,
  Package, HardHat, Flag, CheckCircle2, RefreshCw, Ban, Droplet, Car,
  TrendingDown, TrendingUp, ArrowRight, Clock,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/hooks/useAuth";
import { dashboardApi, type DashboardStats, type ProjectOperation, type OpsSummary } from "@/api/dashboard";
import { alertsApi, type Alert } from "@/api/alerts";
import { formatCurrency } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuthContext } from "@/context/AuthContext";

// ── Alert card ────────────────────────────────────────────────────────────────

const severityColor: Record<string, string> = {
  CRITICAL: "text-destructive bg-destructive/10 border-destructive/30",
  HIGH:     "text-destructive bg-destructive/10 border-destructive/20",
  MEDIUM:   "text-amber-600 bg-amber-500/10 border-amber-500/20 dark:text-amber-400",
  LOW:      "text-muted-foreground bg-muted border-border",
};

function AlertCard({ alert, onDismiss }: { alert: Alert; onDismiss?: (id: string) => void }) {
  const { isReadOnly } = useAuthContext();
  return (
    <div className={cn("border rounded-xl px-4 py-3 flex items-start gap-3",
      severityColor[alert.severity] || severityColor.LOW)}>
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
      <Link to="/alerts" className="flex-1 min-w-0 block active:scale-[0.98] transition-transform">
        <p className="text-sm font-medium leading-snug truncate">{alert.title}</p>
        <p className="text-xs opacity-75 mt-0.5 line-clamp-1">{alert.message}</p>
      </Link>
      <Badge variant="outline" className="text-[10px] shrink-0 border-current opacity-80">{alert.severity}</Badge>
      {!isReadOnly && onDismiss && (
        <button onClick={(e) => { e.stopPropagation(); onDismiss(alert.id); }}
          className="shrink-0 p-0.5 rounded hover:bg-black/10 transition-colors opacity-60 hover:opacity-100">
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

// ── Ops summary section card ──────────────────────────────────────────────────

function OpsSectionCard({
  title, icon: Icon, color, children, to,
}: {
  title: string;
  icon: React.ElementType;
  color: string;
  children: React.ReactNode;
  to?: string;
}) {
  const inner = (
    <div className="bg-card border border-border rounded-2xl p-4 space-y-3 h-full">
      <div className="flex items-center gap-2">
        <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center shrink-0", color)}>
          <Icon className="w-3.5 h-3.5" />
        </div>
        <span className="text-sm font-semibold">{title}</span>
        {to && <ArrowRight className="w-3.5 h-3.5 text-muted-foreground ml-auto" />}
      </div>
      {children}
    </div>
  );
  if (to) return <Link to={to} className="hover:opacity-80 transition-opacity block h-full">{inner}</Link>;
  return <div className="h-full">{inner}</div>;
}

function OpsRow({ label, value, warn = false, crit = false }: {
  label: string; value: string | number; warn?: boolean; crit?: boolean;
}) {
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn(
        "font-semibold tabular-nums",
        crit ? "text-destructive" : warn ? "text-amber-600 dark:text-amber-400" : "text-foreground"
      )}>
        {value}
      </span>
    </div>
  );
}

// ── Project operation card ────────────────────────────────────────────────────

function ProjectOpCard({ op }: { op: ProjectOperation }) {
  const navigate = useNavigate();
  const pct = op.progress_pct;
  const progressColor =
    pct >= 75 ? "bg-green-500" : pct >= 40 ? "bg-blue-500" : pct > 0 ? "bg-amber-500" : "bg-muted-foreground/30";

  return (
    <div
      className="bg-card border border-border rounded-2xl p-4 space-y-3 hover:bg-muted/20 transition-colors cursor-pointer"
      onClick={() => navigate(`/projects`)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-sm truncate">{op.project_name}</p>
          {op.project_code && <p className="text-xs text-muted-foreground">{op.project_code}</p>}
        </div>
        <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
          {op.open_alerts > 0 && (
            <Link to="/alerts" onClick={e => e.stopPropagation()}
              className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full bg-destructive/10 text-destructive font-medium hover:bg-destructive/20">
              <AlertTriangle className="w-3 h-3" />{op.open_alerts}
            </Link>
          )}
          {op.active_material_requests > 0 && (
            <Link to="/procurement" onClick={e => e.stopPropagation()}
              className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 font-medium hover:opacity-80">
              <Package className="w-3 h-3" />{op.active_material_requests}
            </Link>
          )}
        </div>
      </div>

      {/* Progress */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>Progress</span>
          <span className="font-medium text-foreground">{pct}%</span>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div className={cn("h-full rounded-full transition-all duration-700", progressColor)}
            style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="bg-muted/40 rounded-lg py-1.5 px-1">
          <p className="text-base font-bold leading-none">{op.total_lots}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">Units</p>
        </div>
        <div className="bg-green-500/10 rounded-lg py-1.5 px-1">
          <p className="text-base font-bold leading-none text-green-600">{op.lots_completed}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">Done</p>
        </div>
        <div className="bg-blue-500/10 rounded-lg py-1.5 px-1">
          <p className="text-base font-bold leading-none text-blue-600">{op.lots_in_progress}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">Active</p>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs border-t border-border/50 pt-2">
        <div className="flex items-center gap-1 text-muted-foreground">
          <Flag className="w-3 h-3" />
          <span>
            <span className="font-medium text-foreground">{op.milestones_completed}</span>
            /{op.total_milestones} milestones
          </span>
        </div>
        {op.total_paid > 0 && (
          <span className="text-muted-foreground">
            Paid: <span className="font-medium text-foreground">{formatCurrency(op.total_paid)}</span>
          </span>
        )}
      </div>
    </div>
  );
}

// ── Quick Access ──────────────────────────────────────────────────────────────

const moduleLinks = [
  { label: "Procurement",  path: "/procurement",       icon: ShoppingCart,    color: "bg-primary/10 text-primary",         desc: "MRs & POs" },
  { label: "Deliveries",   path: "/deliveries",         icon: Truck,           color: "bg-success/10 text-success",          desc: "Receive stock" },
  { label: "Warehouse",    path: "/project-warehouse",  icon: Warehouse,       color: "bg-warning/10 text-warning",          desc: "Stock dispatch" },
  { label: "Milestones",   path: "/milestones",         icon: Flag,            color: "bg-primary/10 text-primary",          desc: "Progress" },
  { label: "BOQ",          path: "/boq",                icon: FileSpreadsheet, color: "bg-muted text-muted-foreground",      desc: "Bills of quantities" },
  { label: "Payments",     path: "/payments",           icon: CreditCard,      color: "bg-success/10 text-success",          desc: "Invoices & payments" },
  { label: "Alerts",       path: "/alerts",             icon: Bell,            color: "bg-destructive/10 text-destructive",  desc: "System alerts" },
  { label: "Labour",       path: "/labour",             icon: HardHat,         color: "bg-muted text-muted-foreground",      desc: "Job cards" },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate  = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [stats,      setStats]      = useState<DashboardStats | null>(null);
  const [operations, setOperations] = useState<ProjectOperation[]>([]);
  const [ops,        setOps]        = useState<OpsSummary | null>(null);
  const [alerts,     setAlerts]     = useState<Alert[]>([]);
  const [loading,    setLoading]    = useState(true);

  const handleDismissAlert = async (id: string) => {
    try {
      await alertsApi.acknowledge(id);
      setAlerts(prev => prev.filter(a => a.id !== id));
    } catch { /* silent */ }
  };

  const load = () => {
    setLoading(true);
    Promise.all([
      dashboardApi.getStats().catch(() => null),
      dashboardApi.getProjectOperations().catch(() => []),
      dashboardApi.getOpsSummary().catch(() => null),
      alertsApi.list({ status: "OPEN", limit: 5 }).catch(() => []),
    ]).then(([s, op, o, al]) => {
      setStats(s);
      setOperations(op);
      setOps(o);
      setAlerts(al);
    }).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (authLoading) {
    return (
      <div className="space-y-4 animate-fade-in">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-24 rounded-2xl" />)}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-44 rounded-2xl" />)}
        </div>
      </div>
    );
  }

  const firstName = user?.full_name?.split(" ")[0] ?? "";

  // Derive aggregated attention items
  const totalPendingMR  = operations.reduce((s, o) => s + o.active_material_requests, 0);
  const totalAlertCount = operations.reduce((s, o) => s + o.open_alerts, 0);
  const blockedMs       = ops?.milestones.blocked_count ?? 0;
  const overdueInv      = ops?.financial.overdue_count  ?? 0;

  const attentionItems = [
    totalPendingMR  > 0 && { label: `${totalPendingMR} pending MR${totalPendingMR !== 1 ? "s" : ""}`,    to: "/procurement",      crit: false },
    overdueInv      > 0 && { label: `${overdueInv} overdue invoice${overdueInv !== 1 ? "s" : ""}`,       to: "/payments",         crit: true  },
    blockedMs       > 0 && { label: `${blockedMs} blocked milestone${blockedMs !== 1 ? "s" : ""}`,       to: "/milestones",       crit: false },
    totalAlertCount > 0 && { label: `${totalAlertCount} open alert${totalAlertCount !== 1 ? "s" : ""}`,  to: "/alerts",           crit: totalAlertCount > 3 },
  ].filter(Boolean) as Array<{ label: string; to: string; crit: boolean }>;

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">
            {firstName ? `Welcome, ${firstName}` : "Dashboard"}
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">HMH Construction OS</p>
        </div>
        <div className="flex items-center gap-3">
          {stats && !loading && (
            <div className="hidden sm:flex items-center gap-4 text-xs text-muted-foreground">
              <span><strong className="text-foreground">{stats.active_projects}</strong> projects</span>
              {(stats.open_alerts ?? 0) > 0 && (
                <span className="text-destructive font-medium">
                  <strong>{stats.open_alerts}</strong> alerts
                </span>
              )}
              <span><strong className="text-foreground">{formatCurrency(stats.total_paid_amount)}</strong> paid</span>
            </div>
          )}
          <button onClick={load} disabled={loading}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground disabled:opacity-50">
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {/* ── Alert banner ── */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Open Alerts ({alerts.length})
            </p>
            <Link to="/alerts" className="text-xs text-primary hover:underline">View all →</Link>
          </div>
          {alerts.map(a => <AlertCard key={a.id} alert={a} onDismiss={handleDismissAlert} />)}
        </div>
      )}

      {/* ── Attention bar ── */}
      {attentionItems.length > 0 && !loading && (
        <div className="flex flex-wrap gap-2">
          {attentionItems.map((item, i) => (
            <Link key={i} to={item.to}
              className={cn(
                "flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-medium hover:opacity-80 transition-opacity",
                item.crit
                  ? "border-destructive/30 bg-destructive/5 text-destructive"
                  : "border-amber-200 bg-amber-50/60 text-amber-700 dark:border-amber-800/50 dark:bg-amber-950/20 dark:text-amber-400"
              )}>
              <AlertTriangle className="w-3 h-3 shrink-0" />
              {item.label}
            </Link>
          ))}
        </div>
      )}

      {/* ── Ops summary cards (2-column on tablet+) ── */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-36 rounded-2xl" />)}
        </div>
      ) : ops && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">

          {/* Financial */}
          <OpsSectionCard title="Financial Operations" icon={CreditCard} color="bg-amber-500/10 text-amber-600" to="/payments">
            <div className="space-y-1.5">
              <OpsRow label="Outstanding invoices"
                value={`${ops.financial.outstanding_invoice_count} (${formatCurrency(ops.financial.outstanding_total)})`}
                warn={ops.financial.outstanding_invoice_count > 0} />
              <OpsRow label="Overdue invoices"
                value={`${ops.financial.overdue_count} (${formatCurrency(ops.financial.overdue_total)})`}
                crit={ops.financial.overdue_count > 0} />
              <OpsRow label="Partially paid"    value={ops.financial.partially_paid_count} warn={ops.financial.partially_paid_count > 0} />
              <OpsRow label="Overpaid"          value={ops.financial.overpaid_count}       crit={ops.financial.overpaid_count > 0} />
              <OpsRow label="Payments this month" value={formatCurrency(ops.financial.payments_this_month)} />
            </div>
          </OpsSectionCard>

          {/* Milestones */}
          <OpsSectionCard title="Milestone Operations" icon={Flag} color="bg-primary/10 text-primary" to="/milestones">
            <div className="space-y-1.5">
              <OpsRow label="Blocked"         value={ops.milestones.blocked_count}       crit={ops.milestones.blocked_count > 0} />
              <OpsRow label="Delayed (30d+)"  value={ops.milestones.delayed_count}       warn={ops.milestones.delayed_count > 0} />
              <OpsRow label="In progress"     value={ops.milestones.in_progress_count} />
              <OpsRow label="Completed this week" value={ops.milestones.completed_this_week} />
            </div>
          </OpsSectionCard>

          {/* Warehouse */}
          <OpsSectionCard title="Warehouse Operations" icon={Warehouse} color="bg-warning/10 text-warning" to="/project-warehouse">
            <div className="space-y-1.5">
              <OpsRow label="Projects with stock"   value={ops.warehouse.projects_with_stock} />
              <OpsRow label="Dispatches (7 days)"   value={ops.warehouse.recent_transfer_count} />
            </div>
          </OpsSectionCard>

          {/* Vehicle / Fuel */}
          <OpsSectionCard title="Fleet & Fuel" icon={Car} color="bg-muted text-muted-foreground" to="/fuel">
            <div className="space-y-1.5">
              <OpsRow label="Fuel cost this month"  value={formatCurrency(ops.fuel.total_cost_this_month)} />
              <OpsRow label="Flagged entries"       value={ops.fuel.flagged_entries_count} warn={ops.fuel.flagged_entries_count > 0} />
            </div>
          </OpsSectionCard>
        </div>
      )}

      {/* ── Project operation cards ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Active Projects</h3>
          <Link to="/projects" className="text-xs text-primary hover:underline">All projects →</Link>
        </div>
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-48 rounded-2xl" />)}
          </div>
        ) : operations.length === 0 ? (
          <div className="bg-card border border-border rounded-2xl p-10 text-center text-sm text-muted-foreground">
            No active projects. <Link to="/projects" className="text-primary hover:underline">Create one →</Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {operations.map(op => <ProjectOpCard key={op.project_id} op={op} />)}
          </div>
        )}
      </div>

      {/* ── Quick Access ── */}
      <div className="bg-card border border-border rounded-2xl p-4 sm:p-5">
        <h3 className="text-sm font-semibold mb-3">Quick Access</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
          {moduleLinks.map(m => (
            <button key={m.path} onClick={() => navigate(m.path)}
              className="flex items-center gap-3 p-3 sm:p-3.5 rounded-xl border border-border hover:bg-muted active:scale-[0.97] transition-all text-left">
              <div className={cn("flex items-center justify-center w-9 h-9 rounded-lg shrink-0", m.color)}>
                <m.icon className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium leading-tight">{m.label}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5 leading-tight hidden sm:block">{m.desc}</p>
              </div>
            </button>
          ))}
        </div>
      </div>

    </div>
  );
}
