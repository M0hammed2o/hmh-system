import { useEffect, useState } from "react";
import { Bell, AlertTriangle, AlertCircle, Info, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { Tabs } from "@/components/shared/Tabs";
import { StatCard } from "@/components/shared/StatCard";
import { alertsApi, type Alert, type AlertSeverity, type AlertStatus } from "@/api/alerts";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const severityConfig: Record<AlertSeverity, { label: string; color: string; icon: React.ElementType }> = {
  CRITICAL: { label: "Critical", color: "bg-destructive/10 text-destructive border-destructive/20", icon: AlertCircle },
  HIGH:     { label: "High",     color: "bg-red-500/10 text-red-500 border-red-500/20",            icon: AlertTriangle },
  MEDIUM:   { label: "Medium",   color: "bg-warning/10 text-warning border-warning/20",             icon: AlertTriangle },
  LOW:      { label: "Low",      color: "bg-muted text-muted-foreground border-border",             icon: Info },
};

const severityBadgeVariant: Record<AlertSeverity, "destructive" | "warning" | "secondary" | "outline"> = {
  CRITICAL: "destructive",
  HIGH: "destructive",
  MEDIUM: "warning",
  LOW: "outline",
};

const statusBadgeVariant: Record<AlertStatus, "destructive" | "secondary" | "success"> = {
  OPEN: "destructive",
  ACKNOWLEDGED: "secondary",
  RESOLVED: "success",
};

const SEVERITY_TABS = [
  { key: "all",      label: "All" },
  { key: "CRITICAL", label: "Critical" },
  { key: "HIGH",     label: "High" },
  { key: "MEDIUM",   label: "Medium" },
  { key: "LOW",      label: "Low" },
];

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState("all");
  const [actioning, setActioning] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    alertsApi
      .list({ limit: 200 })
      .then(setAlerts)
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = severityFilter === "all"
    ? alerts
    : alerts.filter((a) => a.severity === severityFilter);

  const openCount        = alerts.filter((a) => a.status === "OPEN").length;
  const criticalCount    = alerts.filter((a) => a.severity === "CRITICAL").length;
  const acknowledgedCount = alerts.filter((a) => a.status === "ACKNOWLEDGED").length;
  const resolvedCount    = alerts.filter((a) => a.status === "RESOLVED").length;

  const tabsWithCount = SEVERITY_TABS.map((t) => ({
    ...t,
    count: t.key === "all" ? alerts.length : alerts.filter((a) => a.severity === t.key).length,
  }));

  const handleAction = async (alert: Alert, newStatus: AlertStatus) => {
    setActioning(alert.id);
    try {
      const updated = await alertsApi.update(alert.id, { status: newStatus });
      setAlerts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
    } catch {
      // silently fail — alert stays unchanged
    } finally {
      setActioning(null);
    }
  };

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Alerts"
        description="System alerts for BOQ overruns, stock issues, overdue payments, and delivery exceptions."
        meta={`${openCount} open`}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="Open"         value={openCount}         icon={AlertCircle}  color="bg-destructive/10 text-destructive" />
        <StatCard title="Critical"     value={criticalCount}     icon={AlertTriangle} color="bg-destructive/10 text-destructive" />
        <StatCard title="Acknowledged" value={acknowledgedCount} icon={Bell}          color="bg-warning/10 text-warning" />
        <StatCard title="Resolved"     value={resolvedCount}     icon={CheckCircle2}  color="bg-success/10 text-success" />
      </div>

      <Tabs tabs={tabsWithCount} active={severityFilter} onChange={setSeverityFilter} />

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.length === 0 ? (
            <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">
              No alerts for this filter.
            </div>
          ) : (
            filtered.map((alert) => {
              const cfg = severityConfig[alert.severity];
              const SeverityIcon = cfg.icon;
              const isActioning = actioning === alert.id;
              return (
                <div
                  key={alert.id}
                  className={cn(
                    "bg-card border rounded-xl p-5",
                    alert.status === "RESOLVED" ? "opacity-60 border-border" : cfg.color
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 shrink-0">
                      <SeverityIcon className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-3 flex-wrap">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="font-semibold text-sm">{alert.title}</p>
                          <Badge variant={severityBadgeVariant[alert.severity]}>
                            {severityConfig[alert.severity].label}
                          </Badge>
                          <Badge variant={statusBadgeVariant[alert.status]}>
                            {alert.status === "ACKNOWLEDGED" ? "Acknowledged"
                              : alert.status === "RESOLVED" ? "Resolved"
                              : "Open"}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {alert.status === "OPEN" && (
                            <button
                              disabled={isActioning}
                              onClick={() => handleAction(alert, "ACKNOWLEDGED")}
                              className="text-xs text-primary hover:underline font-medium disabled:opacity-50"
                            >
                              {isActioning ? "…" : "Acknowledge"}
                            </button>
                          )}
                          {alert.status !== "RESOLVED" && (
                            <button
                              disabled={isActioning}
                              onClick={() => handleAction(alert, "RESOLVED")}
                              className="text-xs text-muted-foreground hover:text-foreground hover:underline disabled:opacity-50"
                            >
                              {isActioning ? "…" : "Resolve"}
                            </button>
                          )}
                        </div>
                      </div>
                      <p className="text-sm mt-1.5 text-current opacity-80">{alert.message}</p>
                      <div className="flex items-center gap-3 mt-2 text-xs opacity-60 flex-wrap">
                        {alert.project_id && (
                          <span className="font-mono">{alert.project_id.slice(0, 8)}</span>
                        )}
                        <span className="font-mono text-xs">{alert.alert_type}</span>
                        <span>·</span>
                        <span>{formatDateTime(alert.created_at)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
