import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  FolderKanban, Users, Package, Bell, ShoppingCart, CreditCard, Truck, FileSpreadsheet, Droplet,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/useAuth";
import { dashboardApi, type DashboardStats } from "@/api/dashboard";
import { formatCurrency } from "@/lib/format";

interface StatCardProps {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
}

function StatCard({ title, value, icon: Icon, color }: StatCardProps) {
  return (
    <div className="bg-card border border-border rounded-xl p-5 flex items-start gap-4">
      <div className={`flex items-center justify-center w-10 h-10 rounded-lg shrink-0 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-sm text-muted-foreground">{title}</p>
        <p className="text-2xl font-bold mt-0.5">{value}</p>
      </div>
    </div>
  );
}

const moduleLinks = [
  { label: "Projects",    path: "/projects",    icon: FolderKanban,    color: "bg-primary/10 text-primary",         desc: "Manage construction projects" },
  { label: "BOQ",         path: "/boq",          icon: FileSpreadsheet, color: "bg-warning/10 text-warning",          desc: "Bills of quantities" },
  { label: "Procurement", path: "/procurement",  icon: ShoppingCart,    color: "bg-success/10 text-success",          desc: "Purchase orders & suppliers" },
  { label: "Deliveries",  path: "/deliveries",   icon: Truck,           color: "bg-primary/10 text-primary",         desc: "Incoming material deliveries" },
  { label: "Stock",       path: "/stock",        icon: Package,         color: "bg-warning/10 text-warning",          desc: "On-site stock ledger" },
  { label: "Payments",    path: "/payments",     icon: CreditCard,      color: "bg-success/10 text-success",          desc: "Supplier & labour payments" },
  { label: "Alerts",      path: "/alerts",       icon: Bell,            color: "bg-destructive/10 text-destructive", desc: "System notifications" },
  { label: "Users",       path: "/users",        icon: Users,           color: "bg-primary/10 text-primary",         desc: "User management & access" },
];

export default function DashboardPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  useEffect(() => {
    dashboardApi
      .getStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, []);

  if (authLoading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Welcome */}
      <div>
        <h2 className="text-lg font-semibold">
          Welcome back{user ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Here's an overview of the HMH construction management system.
        </p>
      </div>

      {/* Stat cards — real data */}
      {statsLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Active Projects"
            value={stats?.active_projects ?? "—"}
            icon={FolderKanban}
            color="bg-primary/10 text-primary"
          />
          <StatCard
            title="Open Alerts"
            value={stats?.open_alerts ?? "—"}
            icon={Bell}
            color="bg-destructive/10 text-destructive"
          />
          <StatCard
            title="Open Purchase Orders"
            value={stats?.open_purchase_orders ?? "—"}
            icon={ShoppingCart}
            color="bg-warning/10 text-warning"
          />
          <StatCard
            title="Total Paid"
            value={stats ? formatCurrency(stats.total_paid_amount) : "—"}
            icon={CreditCard}
            color="bg-success/10 text-success"
          />
        </div>
      )}

      {/* Secondary stats row */}
      {!statsLoading && stats && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-card border border-border rounded-xl p-4 flex justify-between items-center">
            <p className="text-sm text-muted-foreground">Active Sites</p>
            <p className="text-xl font-bold">{stats.active_sites}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-4 flex justify-between items-center">
            <p className="text-sm text-muted-foreground">Pending Invoices</p>
            <p className="text-xl font-bold">{stats.pending_invoices}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-4 flex justify-between items-center">
            <p className="text-sm text-muted-foreground">Pending Payments</p>
            <p className="text-xl font-bold">{stats.pending_payments}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-4 flex items-center gap-3">
            <div className="flex items-center justify-center w-9 h-9 rounded-lg shrink-0 bg-primary/10 text-primary">
              <Droplet className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Fuel Cost (all)</p>
              <p className="text-lg font-bold">{formatCurrency(stats.fuel_total_cost)}</p>
            </div>
          </div>
        </div>
      )}

      {/* Module grid */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-sm font-semibold mb-4">Modules</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {moduleLinks.map((m) => (
            <button
              key={m.path}
              onClick={() => navigate(m.path)}
              className="flex items-start gap-3 p-3.5 rounded-lg border border-border hover:bg-muted transition-colors text-left"
            >
              <div className={`flex items-center justify-center w-9 h-9 rounded-lg shrink-0 ${m.color}`}>
                <m.icon className="w-4 h-4" />
              </div>
              <div>
                <p className="text-sm font-medium">{m.label}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{m.desc}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
