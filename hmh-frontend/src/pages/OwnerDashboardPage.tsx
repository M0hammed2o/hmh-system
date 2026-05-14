/**
 * Owner Mobile Dashboard — phone-first view of the entire business.
 * Large cards, tap targets, real data from existing APIs.
 */
import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  TrendingUp, Bell, Clock, Car, FileText, BarChart3,
  RefreshCw, ChevronRight, AlertTriangle, CheckCircle2,
  HardHat, MessageSquare, Package,
} from "lucide-react";
import { dashboardApi, type DashboardStats } from "@/api/dashboard";
import { alertsApi, type AlertStats } from "@/api/alerts";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import client from "@/api/client";

function fmt(n: number) {
  if (n >= 1_000_000) return `R${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `R${(n / 1_000).toFixed(0)}K`;
  return `R${n.toFixed(0)}`;
}

function timeGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

interface BigCard {
  label: string;
  value: string | number;
  icon: React.ElementType;
  to: string;
  variant?: "default" | "warn" | "danger" | "success";
  sub?: string;
}

function BigCard({ label, value, icon: Icon, to, variant = "default", sub }: BigCard) {
  const colors = {
    default: "bg-card border-border",
    warn:    "bg-amber-500/10 border-amber-500/40",
    danger:  "bg-destructive/10 border-destructive/40",
    success: "bg-green-500/10 border-green-500/40",
  };
  const textColors = {
    default: "text-foreground",
    warn:    "text-amber-600 dark:text-amber-400",
    danger:  "text-destructive",
    success: "text-green-600 dark:text-green-400",
  };
  const iconColors = {
    default: "bg-primary/10 text-primary",
    warn:    "bg-amber-500/20 text-amber-500",
    danger:  "bg-destructive/20 text-destructive",
    success: "bg-green-500/20 text-green-600 dark:text-green-400",
  };
  return (
    <Link to={to} className="block">
      <div className={cn("border rounded-2xl p-4 flex items-center gap-4 active:scale-95 transition-transform", colors[variant])}>
        <div className={cn("flex items-center justify-center w-12 h-12 rounded-xl shrink-0", iconColors[variant])}>
          <Icon className="w-6 h-6" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide leading-tight">{label}</p>
          <p className={cn("text-3xl font-bold leading-tight mt-0.5", textColors[variant])}>{value}</p>
          {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
        </div>
        <ChevronRight className="w-5 h-5 text-muted-foreground shrink-0" />
      </div>
    </Link>
  );
}

interface VehicleSpend { today: number; month: number; }

export default function OwnerDashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [alertStats, setAlertStats] = useState<AlertStats | null>(null);
  const [vehicleSpend, setVehicleSpend] = useState<VehicleSpend>({ today: 0, month: 0 });
  const [labourPending, setLabourPending] = useState<{ count: number; amount: number }>({ count: 0, amount: 0 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [userName, setUserName] = useState("");

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    try {
      const [dashRes, alertRes] = await Promise.allSettled([
        dashboardApi.getStats(),
        alertsApi.stats(),
      ]);
      if (dashRes.status === "fulfilled") setStats(dashRes.value);
      if (alertRes.status === "fulfilled") setAlertStats(alertRes.value);

      // Vehicle costs (sum all costs today and this month)
      try {
        const vcRes = await client.get<{ data: Array<{ amount: number; cost_date: string }> }>("/vehicles/");
        const vehicles = vcRes.data.data as Array<{ id: string }>;
        let todayCost = 0, monthCost = 0;
        const today = new Date().toISOString().split("T")[0];
        const monthStart = today.substring(0, 7);
        for (const v of vehicles.slice(0, 5)) {
          try {
            const costsRes = await client.get<{ data: Array<{ amount: number; cost_date: string }> }>(`/vehicles/${v.id}/costs`);
            for (const c of costsRes.data.data || []) {
              if (c.cost_date === today) todayCost += c.amount;
              if (c.cost_date?.startsWith(monthStart)) monthCost += c.amount;
            }
          } catch { /* ignore */ }
        }
        setVehicleSpend({ today: todayCost, month: monthCost });
      } catch { /* ignore */ }

      // Labour pending
      try {
        const projRes = await client.get<{ data: Array<{ id: string }> }>("/projects/", { params: { limit: 1 } });
        const projs = projRes.data.data;
        if (projs?.length) {
          const jcRes = await client.get<{ data: { pending_payment_count: number; pending_payment_amount: number } }>(
            `/projects/${projs[0].id}/job-cards/summary`
          );
          const d = jcRes.data.data;
          setLabourPending({ count: d.pending_payment_count, amount: d.pending_payment_amount });
        }
      } catch { /* ignore */ }

      // User name
      try {
        const meRes = await client.get<{ data: { full_name: string } }>("/users/me");
        setUserName(meRes.data.data.full_name.split(" ")[0]);
      } catch { /* ignore */ }

    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const criticalAlerts = alertStats?.critical_open || 0;
  const openAlerts = alertStats?.open || 0;
  const pendingWhatsApp = alertStats?.pending_whatsapp_ack || 0;

  if (loading) {
    return (
      <div className="space-y-4 max-w-lg mx-auto animate-fade-in">
        <Skeleton className="h-8 w-52 rounded-xl" />
        {[1,2,3,4,5,6].map((i) => <Skeleton key={i} className="h-20 rounded-2xl" />)}
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in max-w-lg mx-auto">
      {/* Greeting */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">{timeGreeting()}{userName ? `, ${userName}` : ""} 👋</h1>
          <p className="text-sm text-muted-foreground">
            {new Date().toLocaleDateString("en-ZA", { weekday: "long", day: "numeric", month: "long" })}
          </p>
        </div>
        <button onClick={() => load(true)} disabled={refreshing} className="p-2 rounded-lg hover:bg-muted">
          <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
        </button>
      </div>

      {/* Critical banner */}
      {criticalAlerts > 0 && (
        <Link to="/alerts">
          <div className="bg-destructive/10 border border-destructive/40 rounded-2xl p-4 flex items-center gap-3 active:scale-95 transition-transform">
            <AlertTriangle className="w-6 h-6 text-destructive shrink-0" />
            <div className="flex-1">
              <p className="font-semibold text-destructive text-sm">{criticalAlerts} critical alert{criticalAlerts !== 1 ? "s" : ""} require attention</p>
              <p className="text-xs text-destructive/80">Tap to view and acknowledge</p>
            </div>
            <ChevronRight className="w-5 h-5 text-destructive" />
          </div>
        </Link>
      )}

      {/* Spend section */}
      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Spend</p>
        <div className="grid grid-cols-1 gap-3">
          <BigCard
            label="Total Paid (Project)"
            value={fmt(stats?.total_paid_amount || 0)}
            icon={TrendingUp}
            to="/payments"
            variant="default"
          />
          <div className="grid grid-cols-2 gap-3">
            <BigCard label="Vehicle Costs Today" value={fmt(vehicleSpend.today)} icon={Car} to="/vehicles" />
            <BigCard label="Vehicle Costs Month" value={fmt(vehicleSpend.month)} icon={BarChart3} to="/vehicles" />
          </div>
        </div>
      </div>

      {/* Operations section */}
      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Operations</p>
        <div className="grid grid-cols-1 gap-3">
          <BigCard
            label="Open Alerts"
            value={openAlerts}
            icon={Bell}
            to="/alerts"
            variant={openAlerts > 0 ? "warn" : "default"}
            sub={criticalAlerts > 0 ? `${criticalAlerts} critical` : "All clear"}
          />
          <div className="grid grid-cols-2 gap-3">
            <BigCard
              label="Active Projects"
              value={stats?.active_projects || 0}
              icon={BarChart3}
              to="/projects"
            />
            <BigCard
              label="Pending Invoices"
              value={stats?.pending_invoices || 0}
              icon={FileText}
              to="/reconciliation"
              variant={(stats?.pending_invoices || 0) > 0 ? "warn" : "default"}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <BigCard
              label="Open POs"
              value={stats?.open_purchase_orders || 0}
              icon={Package}
              to="/procurement"
            />
            <BigCard
              label="Active Sites"
              value={stats?.active_sites || 0}
              icon={HardHat}
              to="/projects"
            />
          </div>
        </div>
      </div>

      {/* Approvals section */}
      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Pending Approvals</p>
        <div className="grid grid-cols-1 gap-3">
          {labourPending.count > 0 && (
            <BigCard
              label="Labour Awaiting Payment"
              value={`${labourPending.count} job card${labourPending.count !== 1 ? "s" : ""}`}
              icon={HardHat}
              to="/labour"
              variant="warn"
              sub={fmt(labourPending.amount) + " total"}
            />
          )}
          {pendingWhatsApp > 0 && (
            <BigCard
              label="WhatsApp ACK Pending"
              value={pendingWhatsApp}
              icon={MessageSquare}
              to="/whatsapp-queue"
              variant="warn"
              sub="Awaiting owner acknowledgement"
            />
          )}
          {labourPending.count === 0 && pendingWhatsApp === 0 && (
            <div className="bg-green-500/10 border border-green-500/30 rounded-2xl p-4 flex items-center gap-3">
              <CheckCircle2 className="w-6 h-6 text-green-500 shrink-0" />
              <p className="text-sm font-medium text-green-600 dark:text-green-400">No pending approvals</p>
            </div>
          )}
        </div>
      </div>

      {/* Quick access */}
      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Quick Access</p>
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: "Deliveries",     to: "/deliveries",    icon: Package },
            { label: "Stock",          to: "/stock",         icon: Package },
            { label: "Reconciliation", to: "/reconciliation",icon: FileText },
            { label: "WhatsApp Queue", to: "/whatsapp-queue",icon: MessageSquare },
          ].map(({ label, to, icon: Icon }) => (
            <Link key={to} to={to}>
              <div className="bg-card border border-border rounded-xl p-3 flex items-center gap-3 hover:bg-muted/40 active:scale-95 transition-all">
                <Icon className="w-5 h-5 text-muted-foreground shrink-0" />
                <span className="text-sm font-medium">{label}</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
