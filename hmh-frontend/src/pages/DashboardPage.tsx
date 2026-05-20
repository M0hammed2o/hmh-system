import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  FolderKanban, Users, Package, Bell, ShoppingCart, CreditCard,
  Truck, FileSpreadsheet, Droplet, AlertTriangle, ChevronRight, X, Warehouse,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/hooks/useAuth";
import { dashboardApi, type DashboardStats } from "@/api/dashboard";
import { alertsApi, type Alert } from "@/api/alerts";
import { formatCurrency } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAuthContext } from "@/context/AuthContext";

// ── Stat card ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  to?: string;
  warn?: boolean;
}

function StatCard({ title, value, icon: Icon, color, to, warn }: StatCardProps) {
  const inner = (
    <div className={cn(
      "bg-card border rounded-xl p-4 sm:p-5 flex items-start gap-4 transition-colors",
      warn ? "border-amber-500/40" : "border-border",
      to && "hover:bg-muted/40 active:scale-[0.98]",
    )}>
      <div className={`flex items-center justify-center w-11 h-11 sm:w-10 sm:h-10 rounded-lg shrink-0 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs sm:text-sm text-muted-foreground leading-snug">{title}</p>
        <p className="text-3xl sm:text-2xl font-bold mt-0.5 leading-none">{value}</p>
      </div>
      {to && <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0 self-center hidden sm:block" />}
    </div>
  );
  if (to) return <Link to={to}>{inner}</Link>;
  return inner;
}

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

// ── Module shortcuts ──────────────────────────────────────────────────────────

const moduleLinks = [
  { label: "Projects",        path: "/projects",   icon: FolderKanban,    color: "bg-primary/10 text-primary",         desc: "Construction projects" },
  { label: "BOQ",             path: "/boq",         icon: FileSpreadsheet, color: "bg-warning/10 text-warning",          desc: "Bills of quantities" },
  { label: "Procurement",     path: "/procurement", icon: ShoppingCart,    color: "bg-success/10 text-success",          desc: "Purchase orders" },
  { label: "Deliveries",      path: "/deliveries",  icon: Truck,           color: "bg-primary/10 text-primary",         desc: "Incoming deliveries" },
  { label: "Main Warehouse",  path: "/warehouse",   icon: Warehouse,       color: "bg-warning/10 text-warning",          desc: "Central stock & dispatch" },
  { label: "Stock",           path: "/stock",       icon: Package,         color: "bg-muted text-muted-foreground",      desc: "Stock ledger" },
  { label: "Payments",        path: "/payments",    icon: CreditCard,      color: "bg-success/10 text-success",          desc: "Payments" },
  { label: "Alerts",          path: "/alerts",      icon: Bell,            color: "bg-destructive/10 text-destructive", desc: "System alerts" },
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  const handleDismissAlert = async (id: string) => {
    try {
      await alertsApi.acknowledge(id);
      setAlerts(prev => prev.filter(a => a.id !== id));
    } catch { /* silent — alert still removed from UI */ }
  };

  useEffect(() => {
    dashboardApi
      .getStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));

    alertsApi
      .list({ status: "OPEN", limit: 5 })
      .then(setAlerts)
      .catch(() => setAlerts([]));
  }, []);

  if (authLoading) {
    return (
      <div className="space-y-4 animate-fade-in">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-48 rounded-xl" />
      </div>
    );
  }

  const firstName = user?.full_name?.split(" ")[0] ?? "";

  return (
    <div className="space-y-5 animate-fade-in">

      {/* Welcome */}
      <div>
        <h2 className="text-xl font-semibold">
          Welcome back{firstName ? `, ${firstName}` : ""}
        </h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          HMH Construction Management System
        </p>
      </div>

      {/* ── Alert banner — mobile prominent, desktop subtle ── */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Open Alerts ({alerts.length})
            </p>
            <Link to="/alerts" className="text-xs text-primary hover:underline">
              View all →
            </Link>
          </div>
          {alerts.map((a) => <AlertCard key={a.id} alert={a} onDismiss={handleDismissAlert} />)}
        </div>
      )}

      {/* ── Primary stat cards ── */}
      {statsLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : (
        <>
          {/* Row 1 — priority stats */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              title="Active Projects"
              value={stats?.active_projects ?? "—"}
              icon={FolderKanban}
              color="bg-primary/10 text-primary"
              to="/projects"
            />
            <StatCard
              title="Open Alerts"
              value={stats?.open_alerts ?? "—"}
              icon={Bell}
              color="bg-destructive/10 text-destructive"
              to="/alerts"
              warn={(stats?.open_alerts ?? 0) > 0}
            />
            <StatCard
              title="Pending Invoices"
              value={stats?.pending_invoices ?? "—"}
              icon={CreditCard}
              color="bg-warning/10 text-warning"
              to="/payments"
              warn={(stats?.pending_invoices ?? 0) > 0}
            />
            <StatCard
              title="Total Paid"
              value={stats ? formatCurrency(stats.total_paid_amount) : "—"}
              icon={CreditCard}
              color="bg-success/10 text-success"
            />
          </div>

          {/* Row 2 — secondary stats */}
          <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-1">
              <p className="text-xs text-muted-foreground">Active Sites</p>
              <p className="text-2xl font-bold">{stats?.active_sites ?? "—"}</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-1">
              <p className="text-xs text-muted-foreground">Open POs</p>
              <p className="text-2xl font-bold">{stats?.open_purchase_orders ?? "—"}</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-1">
              <p className="text-xs text-muted-foreground">Pending Payments</p>
              <p className="text-2xl font-bold">{stats?.pending_payments ?? "—"}</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
              <div className="flex items-center justify-center w-9 h-9 rounded-lg shrink-0 bg-primary/10 text-primary">
                <Droplet className="w-4 h-4" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Fuel Cost</p>
                <p className="text-lg font-bold leading-tight">
                  {stats ? formatCurrency(stats.fuel_total_cost) : "—"}
                </p>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── Module shortcuts ── */}
      <div className="bg-card border border-border rounded-xl p-4 sm:p-5">
        <h2 className="text-sm font-semibold mb-3">Quick Access</h2>
        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-3">
          {moduleLinks.map((m) => (
            <button
              key={m.path}
              onClick={() => navigate(m.path)}
              className="flex items-center gap-3 p-3 sm:p-3.5 rounded-lg border border-border hover:bg-muted active:scale-[0.97] transition-all text-left"
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
