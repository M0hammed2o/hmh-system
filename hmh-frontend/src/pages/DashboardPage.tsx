import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  FolderKanban, Bell, ShoppingCart, CreditCard,
  Truck, FileSpreadsheet, AlertTriangle, ChevronRight, X, Warehouse,
  Package, HardHat, Flag, CheckCircle2, Clock, RefreshCw,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/hooks/useAuth";
import { dashboardApi, type DashboardStats, type ProjectOperation } from "@/api/dashboard";
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
    <div className={cn(
      "border rounded-xl px-4 py-3 flex items-start gap-3",
      severityColor[alert.severity] || severityColor.LOW,
    )}>
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
      <Link to="/alerts" className="flex-1 min-w-0 block active:scale-[0.98] transition-transform">
        <p className="text-sm font-medium leading-snug truncate">{alert.title}</p>
        <p className="text-xs opacity-75 mt-0.5 line-clamp-1">{alert.message}</p>
      </Link>
      <Badge variant="outline" className="text-[10px] shrink-0 border-current opacity-80">
        {alert.severity}
      </Badge>
      {!isReadOnly && onDismiss && (
        <button
          onClick={(e) => { e.stopPropagation(); onDismiss(alert.id); }}
          className="shrink-0 p-0.5 rounded hover:bg-black/10 transition-colors opacity-60 hover:opacity-100"
          title="Dismiss alert"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}

// ── Project operation card ─────────────────────────────────────────────────────

function ProjectOpCard({ op }: { op: ProjectOperation }) {
  const navigate = useNavigate();
  const progressColor =
    op.progress_pct >= 75 ? "bg-green-500" :
    op.progress_pct >= 40 ? "bg-blue-500" :
    op.progress_pct >  0  ? "bg-amber-500" :
    "bg-muted-foreground/30";

  return (
    <div
      className="bg-card border border-border rounded-2xl p-4 sm:p-5 space-y-4 hover:bg-muted/20 transition-colors cursor-pointer"
      onClick={() => navigate(`/projects`)}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-sm truncate">{op.project_name}</p>
          {op.project_code && (
            <p className="text-xs text-muted-foreground">{op.project_code}</p>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {op.open_alerts > 0 && (
            <Link
              to="/alerts"
              onClick={e => e.stopPropagation()}
              className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-destructive/10 text-destructive font-medium hover:bg-destructive/20"
            >
              <AlertTriangle className="w-3 h-3" />
              {op.open_alerts}
            </Link>
          )}
          {op.active_material_requests > 0 && (
            <Link
              to="/procurement"
              onClick={e => e.stopPropagation()}
              className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 font-medium hover:opacity-80"
            >
              <Package className="w-3 h-3" />
              {op.active_material_requests}
            </Link>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>Progress</span>
          <span className="font-medium text-foreground">{op.progress_pct}%</span>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all duration-700", progressColor)}
            style={{ width: `${op.progress_pct}%` }}
          />
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="bg-muted/40 rounded-lg py-2 px-1">
          <p className="text-lg font-bold leading-none">{op.total_lots}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">Units</p>
        </div>
        <div className="bg-green-500/10 rounded-lg py-2 px-1">
          <p className="text-lg font-bold leading-none text-green-600">{op.lots_completed}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">Done</p>
        </div>
        <div className="bg-blue-500/10 rounded-lg py-2 px-1">
          <p className="text-lg font-bold leading-none text-blue-600">{op.lots_in_progress}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">Active</p>
        </div>
      </div>

      {/* Milestones + spend */}
      <div className="flex items-center justify-between text-xs border-t border-border/50 pt-3">
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

// ── Module shortcuts ──────────────────────────────────────────────────────────

const moduleLinks = [
  { label: "Procurement",       path: "/procurement", icon: ShoppingCart,    color: "bg-primary/10 text-primary",         desc: "Material requests & POs" },
  { label: "Deliveries",        path: "/deliveries",  icon: Truck,           color: "bg-success/10 text-success",          desc: "Receive deliveries" },
  { label: "Warehouse",         path: "/warehouse",   icon: Warehouse,       color: "bg-warning/10 text-warning",          desc: "Stock & dispatch" },
  { label: "Milestones",        path: "/milestones",  icon: Flag,            color: "bg-primary/10 text-primary",          desc: "Progress & photos" },
  { label: "BOQ",               path: "/boq",          icon: FileSpreadsheet, color: "bg-muted text-muted-foreground",      desc: "Bills of quantities" },
  { label: "Payments",          path: "/payments",    icon: CreditCard,      color: "bg-success/10 text-success",          desc: "Invoices & payments" },
  { label: "Alerts",            path: "/alerts",      icon: Bell,            color: "bg-destructive/10 text-destructive",  desc: "System alerts" },
  { label: "Labour",            path: "/labour",      icon: HardHat,         color: "bg-muted text-muted-foreground",      desc: "Job cards" },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [stats,      setStats]      = useState<DashboardStats | null>(null);
  const [operations, setOperations] = useState<ProjectOperation[]>([]);
  const [alerts,     setAlerts]     = useState<Alert[]>([]);
  const [opsLoading, setOpsLoading] = useState(true);

  const handleDismissAlert = async (id: string) => {
    try {
      await alertsApi.acknowledge(id);
      setAlerts(prev => prev.filter(a => a.id !== id));
    } catch { /* silent */ }
  };

  const load = () => {
    setOpsLoading(true);
    Promise.all([
      dashboardApi.getStats().catch(() => null),
      dashboardApi.getProjectOperations().catch(() => []),
      alertsApi.list({ status: "OPEN", limit: 5 }).catch(() => []),
    ]).then(([s, ops, al]) => {
      setStats(s);
      setOperations(ops);
      setAlerts(al);
    }).finally(() => setOpsLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (authLoading) {
    return (
      <div className="space-y-4 animate-fade-in">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-52 rounded-2xl" />)}
        </div>
      </div>
    );
  }

  const firstName = user?.full_name?.split(" ")[0] ?? "";

  return (
    <div className="space-y-5 animate-fade-in">

      {/* Welcome */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">
            Welcome back{firstName ? `, ${firstName}` : ""}
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            HMH Construction OS
          </p>
        </div>
        <div className="flex items-center gap-3">
          {stats && (
            <div className="hidden sm:flex items-center gap-4 text-xs text-muted-foreground">
              <span><strong className="text-foreground">{stats.active_projects}</strong> active projects</span>
              <span className={cn(stats.open_alerts > 0 && "text-destructive font-medium")}>
                <strong>{stats.open_alerts}</strong> open alerts
              </span>
              <span><strong className="text-foreground">{formatCurrency(stats.total_paid_amount)}</strong> total paid</span>
            </div>
          )}
          <button
            onClick={load}
            disabled={opsLoading}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={cn("w-4 h-4", opsLoading && "animate-spin")} />
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
          {alerts.map((a) => <AlertCard key={a.id} alert={a} onDismiss={handleDismissAlert} />)}
        </div>
      )}

      {/* ── Operational summary ── */}
      {!opsLoading && operations.length > 0 && (() => {
        const totalPendingMR  = operations.reduce((s, o) => s + o.active_material_requests, 0);
        const totalAlerts     = operations.reduce((s, o) => s + o.open_alerts, 0);
        if (totalPendingMR === 0 && totalAlerts === 0) return null;
        return (
          <div className="flex flex-wrap gap-2">
            {totalPendingMR > 0 && (
              <Link to="/procurement"
                className="flex items-center gap-2 px-3 py-2 rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800/50 text-xs font-medium text-amber-700 dark:text-amber-400 hover:opacity-80 transition-opacity">
                <Package className="w-3.5 h-3.5" />
                {totalPendingMR} pending material request{totalPendingMR !== 1 ? "s" : ""} — needs review
              </Link>
            )}
            {totalAlerts > 0 && (
              <Link to="/alerts"
                className="flex items-center gap-2 px-3 py-2 rounded-xl border border-destructive/20 bg-destructive/5 text-xs font-medium text-destructive hover:opacity-80 transition-opacity">
                <AlertTriangle className="w-3.5 h-3.5" />
                {totalAlerts} open alert{totalAlerts !== 1 ? "s" : ""} across projects
              </Link>
            )}
          </div>
        );
      })()}

      {/* ── Project operations ── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold">Active Projects</h3>
          <Link to="/projects" className="text-xs text-primary hover:underline">All projects →</Link>
        </div>
        {opsLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-52 rounded-2xl" />)}
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
          {moduleLinks.map((m) => (
            <button
              key={m.path}
              onClick={() => navigate(m.path)}
              className="flex items-center gap-3 p-3 sm:p-3.5 rounded-xl border border-border hover:bg-muted active:scale-[0.97] transition-all text-left"
            >
              <div className={`flex items-center justify-center w-9 h-9 rounded-lg shrink-0 ${m.color}`}>
                <m.icon className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium leading-tight">{m.label}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5 leading-tight hidden sm:block">
                  {m.desc}
                </p>
              </div>
            </button>
          ))}
        </div>
      </div>

    </div>
  );
}
