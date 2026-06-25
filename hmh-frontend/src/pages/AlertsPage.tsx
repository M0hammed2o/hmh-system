import { lazy, Suspense, useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Bell, AlertTriangle, AlertCircle, CheckCircle2,
  MessageSquare, RefreshCw, FileText, X, ExternalLink, MapPin, Building2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  alertsApi,
  type Alert, type AlertSeverity, type AlertStats, type QueueStats, type AlertRecordContext,
} from "@/api/alerts";
import { cn } from "@/lib/utils";

const WhatsAppQueuePage        = lazy(() => import("./WhatsAppQueuePage"));
const NotificationSettingsPage = lazy(() => import("./NotificationSettingsPage"));

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso: string) {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const SEV_STYLE: Record<AlertSeverity, string> = {
  CRITICAL: "border-destructive/40 bg-destructive/5",
  HIGH:     "border-red-400/40 bg-red-500/5",
  MEDIUM:   "border-amber-400/40 bg-amber-500/5",
  LOW:      "border-border bg-card",
};

const SEV_BADGE: Record<AlertSeverity, "destructive" | "secondary" | "outline"> = {
  CRITICAL: "destructive",
  HIGH:     "destructive",
  MEDIUM:   "secondary",
  LOW:      "outline",
};

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatBox({ label, value, warn, icon: Icon }: { label: string; value: number | string; warn?: boolean; icon: React.ElementType }) {
  return (
    <div className={cn("border rounded-xl p-4 flex items-center gap-3", warn ? "border-amber-400/40 bg-amber-500/5" : "bg-card border-border")}>
      <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center shrink-0", warn ? "bg-amber-500/10 text-amber-500" : "bg-primary/10 text-primary")}>
        <Icon className="w-4 h-4" />
      </div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold leading-tight">{value}</p>
      </div>
    </div>
  );
}

// ── Alert navigation helpers ──────────────────────────────────────────────────

function alertDestination(alert: Alert): string {
  switch (alert.alert_type) {
    case "REQUEST_PENDING_TOO_LONG":
      return "/procurement";
    case "DELIVERY_WITHOUT_PO":
    case "DELIVERY_DISCREPANCY":
    case "DELIVERY_SIGNATURE_MISSING":
    case "SIGNATURE_MISSING":
    case "DELIVERY_MISMATCH":
    case "DELIVERY_NOTE_MISSING":
      return "/deliveries";
    case "INVOICE_MISMATCH":
    case "INVOICE_UNMATCHED":
    case "INVOICE_MISSING_DELIVERY_NOTE":
    case "INVOICE_CAPTURED":
    case "DUPLICATE_INVOICE":
      return "/reconciliation";
    case "OVERDUE_PAYMENT":
    case "PAYMENT_DUE":
    case "PAYMENT_COMPLETED":
    case "PARTIAL_PAYMENT_RECORDED":
      return "/payments";
    case "MATERIAL_OVERUSE":
    case "BOQ_VARIANCE_OVERUSE":
    case "BOQ_ALLOCATION_EXCEEDED":
    case "NEGATIVE_STOCK":
    case "LOW_STOCK":
    case "MISSING_REMAINING_STOCK_PHOTO":
    case "WAREHOUSE_TRANSFER_COMPLETED":
      return "/warehouse";
    case "MILESTONE_COMPLETED_ALERT":
    case "LOT_DELAYED":
    case "STAGE_DELAYED":
    case "SITE_DELAY":
      return "/milestones";
    case "OCR_EXTRACTION_FAILED":
      return "/gmail-inbox";
    default:
      return "/alerts";
  }
}

function destLabel(alert: Alert): string {
  switch (alert.alert_type) {
    case "REQUEST_PENDING_TOO_LONG":  return "Procurement";
    case "DELIVERY_WITHOUT_PO":
    case "DELIVERY_DISCREPANCY":
    case "DELIVERY_SIGNATURE_MISSING":
    case "SIGNATURE_MISSING":
    case "DELIVERY_MISMATCH":
    case "DELIVERY_NOTE_MISSING":     return "Deliveries";
    case "INVOICE_MISMATCH":
    case "INVOICE_UNMATCHED":
    case "INVOICE_MISSING_DELIVERY_NOTE":
    case "INVOICE_CAPTURED":
    case "DUPLICATE_INVOICE":         return "Reconciliation";
    case "OVERDUE_PAYMENT":
    case "PAYMENT_DUE":
    case "PAYMENT_COMPLETED":
    case "PARTIAL_PAYMENT_RECORDED":  return "Payments";
    case "MATERIAL_OVERUSE":
    case "BOQ_VARIANCE_OVERUSE":
    case "BOQ_ALLOCATION_EXCEEDED":
    case "NEGATIVE_STOCK":
    case "LOW_STOCK":
    case "MISSING_REMAINING_STOCK_PHOTO":
    case "WAREHOUSE_TRANSFER_COMPLETED": return "Warehouse";
    case "MILESTONE_COMPLETED_ALERT":
    case "LOT_DELAYED":
    case "STAGE_DELAYED":
    case "SITE_DELAY":                return "Milestones";
    case "OCR_EXTRACTION_FAILED":     return "Gmail Inbox";
    default:                          return "View";
  }
}

// ── Alert detail modal ────────────────────────────────────────────────────────

function AlertDetailModal({ alert, onClose }: { alert: Alert; onClose: () => void }) {
  const [ctx, setCtx] = useState<AlertRecordContext | null>(null);
  const [loading, setLoading] = useState(true);
  const dest  = alertDestination(alert);
  const label = destLabel(alert);

  useEffect(() => {
    alertsApi.getContext(alert.id)
      .then(setCtx)
      .catch(() => setCtx({}))
      .finally(() => setLoading(false));
  }, [alert.id]);

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40"
      onClick={onClose}
    >
      <div
        className="bg-card border border-border rounded-2xl w-full max-w-lg shadow-xl max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 pt-5 pb-3 shrink-0">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1.5">
              <Badge variant={SEV_BADGE[alert.severity as AlertSeverity] ?? "outline"} className="text-xs">
                {alert.severity}
              </Badge>
              <span className="text-xs text-muted-foreground font-mono">
                {alert.alert_type.replace(/_/g, " ")}
              </span>
              <span className="text-xs text-muted-foreground ml-auto shrink-0">{timeAgo(alert.created_at)}</span>
            </div>
            <h3 className="text-base font-semibold leading-snug">{alert.title}</h3>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 ml-3 mt-0.5 text-muted-foreground hover:text-foreground text-lg leading-none"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 px-5 pb-3 space-y-4">
          {/* Project / Site chips */}
          {(alert.project_name || alert.site_name) && (
            <div className="flex gap-2 flex-wrap">
              {alert.project_name && (
                <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-full border border-blue-200 dark:border-blue-800">
                  <Building2 className="w-3 h-3" />
                  {alert.project_name}
                </span>
              )}
              {alert.site_name && (
                <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 rounded-full border border-emerald-200 dark:border-emerald-800">
                  <MapPin className="w-3 h-3" />
                  {alert.site_name}
                </span>
              )}
            </div>
          )}

          {/* Alert message */}
          <p className="text-sm text-muted-foreground">{alert.message}</p>

          {/* Referenced record context */}
          {loading ? (
            <Skeleton className="h-28 rounded-xl" />
          ) : ctx && Object.keys(ctx).length > 0 ? (
            <div className="bg-muted/40 rounded-xl p-4 space-y-3 border border-border/50">
              {/* MR items */}
              {ctx.items && ctx.items.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-foreground mb-2">
                    Materials Requested — {ctx.items.length} item{ctx.items.length !== 1 ? "s" : ""}
                    {ctx.request_number && (
                      <span className="ml-2 font-mono font-normal text-muted-foreground">({ctx.request_number})</span>
                    )}
                  </p>
                  <div className="space-y-1 max-h-52 overflow-y-auto pr-1">
                    {ctx.items.map((item, i) => (
                      <div key={i} className="flex items-center justify-between text-xs bg-background rounded-lg px-3 py-2 border border-border/40">
                        <span className="font-medium truncate">{item.name}</span>
                        <span className="text-muted-foreground ml-3 shrink-0 font-mono">
                          {item.quantity} {item.unit}
                        </span>
                      </div>
                    ))}
                  </div>
                  {ctx.status && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Status: <span className="font-medium text-foreground">{ctx.status.replace(/_/g, " ")}</span>
                    </p>
                  )}
                </div>
              )}

              {/* Invoice / payment details */}
              {ctx.invoice_number && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs text-muted-foreground">Invoice</p>
                    <p className="text-sm font-semibold">{ctx.invoice_number}</p>
                  </div>
                  {ctx.amount !== undefined && (
                    <div>
                      <p className="text-xs text-muted-foreground">Amount</p>
                      <p className="text-sm font-semibold">
                        R {ctx.amount.toLocaleString("en-ZA", { minimumFractionDigits: 2 })}
                      </p>
                    </div>
                  )}
                  {ctx.due_date && (
                    <div>
                      <p className="text-xs text-muted-foreground">Due Date</p>
                      <p className="text-sm font-medium">{fmtDate(ctx.due_date)}</p>
                    </div>
                  )}
                  {ctx.supplier_name && (
                    <div>
                      <p className="text-xs text-muted-foreground">Supplier</p>
                      <p className="text-sm font-medium">{ctx.supplier_name}</p>
                    </div>
                  )}
                  {ctx.status && (
                    <div>
                      <p className="text-xs text-muted-foreground">Status</p>
                      <p className="text-sm font-medium">{ctx.status.replace(/_/g, " ")}</p>
                    </div>
                  )}
                </div>
              )}

              {/* Delivery details */}
              {ctx.delivery_number && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs text-muted-foreground">Delivery</p>
                    <p className="text-sm font-semibold">{ctx.delivery_number}</p>
                  </div>
                  {ctx.delivery_date && (
                    <div>
                      <p className="text-xs text-muted-foreground">Date</p>
                      <p className="text-sm font-medium">{fmtDate(ctx.delivery_date)}</p>
                    </div>
                  )}
                  <div>
                    <p className="text-xs text-muted-foreground">Signature</p>
                    <p className="text-sm font-medium">{ctx.has_signature ? "✓ Signed" : "✗ Missing"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">PO Linked</p>
                    <p className="text-sm font-medium">{ctx.has_po ? "✓ Yes" : "✗ No"}</p>
                  </div>
                  {ctx.status && (
                    <div>
                      <p className="text-xs text-muted-foreground">Status</p>
                      <p className="text-sm font-medium">{ctx.status.replace(/_/g, " ")}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="px-5 pb-5 pt-3 border-t border-border shrink-0 flex items-center justify-between gap-2">
          <Link
            to={dest}
            onClick={onClose}
            className="flex items-center gap-1.5 text-xs px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Go to {label}
          </Link>
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 text-xs px-4 py-2 border border-border rounded-lg hover:bg-muted transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Alert card ────────────────────────────────────────────────────────────────

function AlertCard({ alert }: { alert: Alert }) {
  const [showDetail, setShowDetail] = useState(false);
  const typeLabel = alert.alert_type.replace(/_/g, " ");

  return (
    <>
      <div
        className={cn(
          "border rounded-xl p-4 space-y-1.5 transition-all cursor-pointer hover:shadow-md hover:brightness-[0.97]",
          SEV_STYLE[alert.severity as AlertSeverity] ?? "border-border bg-card",
        )}
        onClick={() => setShowDetail(true)}
      >
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <Badge variant={SEV_BADGE[alert.severity as AlertSeverity] ?? "outline"} className="text-xs">
                {alert.severity}
              </Badge>
              <span className="text-xs text-muted-foreground font-mono">{typeLabel}</span>
              <span className="text-xs text-muted-foreground ml-auto shrink-0">{timeAgo(alert.created_at)}</span>
            </div>
            <p className="font-semibold text-sm leading-snug">{alert.title}</p>

            {/* Project / site chips */}
            {(alert.project_name || alert.site_name) && (
              <div className="flex gap-1.5 mt-1 flex-wrap">
                {alert.project_name && (
                  <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded border border-blue-200/60 dark:border-blue-800/60">
                    <Building2 className="w-2.5 h-2.5" />{alert.project_name}
                  </span>
                )}
                {alert.site_name && (
                  <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 rounded border border-emerald-200/60 dark:border-emerald-800/60">
                    <MapPin className="w-2.5 h-2.5" />{alert.site_name}
                  </span>
                )}
              </div>
            )}

            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{alert.message}</p>
          </div>
          <Badge
            variant={alert.status === "OPEN" ? "destructive" : alert.status === "ACKNOWLEDGED" ? "secondary" : "outline"}
            className="text-xs shrink-0"
          >
            {alert.status}
          </Badge>
        </div>
        <p className="text-xs text-primary/70">Click to view details →</p>
      </div>

      {showDetail && (
        <AlertDetailModal alert={alert} onClose={() => setShowDetail(false)} />
      )}
    </>
  );
}

// ── Summary modal ─────────────────────────────────────────────────────────────

function SummaryModal({ result, onClose }: { result: { summary_text: string; queued: number; send_counts: Record<string, number> }; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 space-y-4 animate-fade-in">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Daily Summary Generated</h2>
          <button onClick={onClose}><X className="w-4 h-4" /></button>
        </div>
        <pre className="text-xs bg-muted rounded-lg p-4 whitespace-pre-wrap font-mono">{result.summary_text}</pre>
        <div className="text-sm text-muted-foreground">
          Queued for {result.queued} recipient{result.queued !== 1 ? "s" : ""}.
          {Object.entries(result.send_counts).map(([k, v]) => (
            <span key={k} className="ml-2">{k}: {v}</span>
          ))}
        </div>
        <Button onClick={onClose} className="w-full">Close</Button>
      </div>
    </div>
  );
}

// ── Tab / Section definitions ─────────────────────────────────────────────────

type Tab     = "active" | "history" | "critical" | "materials" | "deliveries" | "invoices" | "vehicles" | "delays";
type Section = "alerts" | "whatsapp-queue" | "notification-settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "active",     label: "Active" },
  { id: "history",    label: "History" },
  { id: "critical",   label: "Critical" },
  { id: "materials",  label: "Materials" },
  { id: "deliveries", label: "Deliveries" },
  { id: "invoices",   label: "Invoices" },
  { id: "vehicles",   label: "Vehicles" },
  { id: "delays",     label: "Delays" },
];

const SECTIONS: { id: Section; label: string }[] = [
  { id: "alerts",                label: "Alerts" },
  { id: "whatsapp-queue",        label: "WhatsApp Queue" },
  { id: "notification-settings", label: "Notification Settings" },
];

const TAB_TYPE_FILTER: Partial<Record<Tab, string[]>> = {
  critical:   ["CRITICAL"],
  materials:  ["MATERIAL_OVERUSE","BOQ_VARIANCE_OVERUSE","BOQ_ALLOCATION_EXCEEDED","LOW_STOCK","NEGATIVE_STOCK"],
  deliveries: ["DELIVERY_MISMATCH","DELIVERY_NOTE_MISSING","SIGNATURE_MISSING","DELIVERY_DISCREPANCY","DELIVERY_WITHOUT_PO","DELIVERY_SIGNATURE_MISSING"],
  invoices:   ["INVOICE_MISMATCH","INVOICE_UNMATCHED","INVOICE_MISSING_DELIVERY_NOTE","OVERDUE_PAYMENT"],
  vehicles:   ["VEHICLE_REPAIR_LOGGED","FUEL_USAGE_HIGH"],
  delays:     ["LOT_DELAYED","STAGE_DELAYED","SITE_DELAY"],
};

// ── Skeleton loader ───────────────────────────────────────────────────────────

function SectionSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-24 rounded-xl" />
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  const [section, setSection]               = useState<Section>("alerts");
  const [tab, setTab]                       = useState<Tab>("active");
  const [alerts, setAlerts]                 = useState<Alert[]>([]);
  const [stats, setStats]                   = useState<AlertStats | null>(null);
  const [queueStats, setQueueStats]         = useState<QueueStats | null>(null);
  const [loading, setLoading]               = useState(true);
  const [refreshing, setRefreshing]         = useState(false);
  const [summaryResult, setSummaryResult]   = useState<{ summary_text: string; queued: number; send_counts: Record<string, number> } | null>(null);
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [scanning, setScanning]             = useState(false);
  const [scanResult, setScanResult]         = useState<{ alerts_created: number } | null>(null);

  const loadAll = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    try {
      const [alertData, statsData, qsData] = await Promise.allSettled([
        alertsApi.list({ limit: 200 }),
        alertsApi.stats(),
        alertsApi.getQueueStats(),
      ]);
      if (alertData.status === "fulfilled") setAlerts(alertData.value);
      if (statsData.status === "fulfilled") setStats(statsData.value);
      if (qsData.status === "fulfilled")   setQueueStats(qsData.value);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleScan = async () => {
    setScanning(true);
    setScanResult(null);
    try {
      const res = await import("@/api/client").then((m) =>
        m.default.post<{ data: { alerts_created: number } }>("/alerts/scan")
      );
      setScanResult(res.data.data);
      loadAll(true);
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data;
      alert(d?.message || d?.detail || "Scan failed — check your permissions.");
    } finally { setScanning(false); }
  };

  const handleDailySummary = async () => {
    setGeneratingSummary(true);
    try {
      const res = await alertsApi.generateDailySummary();
      setSummaryResult(res);
      loadAll(true);
    } finally { setGeneratingSummary(false); }
  };

  const filteredAlerts = useMemo(() => {
    if (tab === "active")   return alerts.filter((a) => a.status === "OPEN");
    if (tab === "history")  return alerts.filter((a) => a.status === "ACKNOWLEDGED" || a.status === "RESOLVED");
    if (tab === "critical") return alerts.filter((a) => a.severity === "CRITICAL" || a.severity === "HIGH");
    const types = TAB_TYPE_FILTER[tab];
    if (types) return alerts.filter((a) => types.includes(a.alert_type));
    return alerts;
  }, [alerts, tab]);

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Alerts</h1>
          <p className="text-sm text-muted-foreground">
            {section === "alerts"
              ? (stats ? `${stats.open} open · ${stats.critical_open} critical` : "Loading…")
              : section === "whatsapp-queue"
                ? "Message queue and delivery status"
                : "WhatsApp recipients and subscriptions"}
          </p>
        </div>
        {section === "alerts" && (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => loadAll(true)} disabled={refreshing}>
              <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
            </Button>
            <Button size="sm" variant="outline" onClick={handleScan} disabled={scanning} title="Scan for low stock, overdue invoices, pending MRs">
              {scanning ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Scan Alerts"}
            </Button>
            <Button size="sm" variant="outline" onClick={handleDailySummary} disabled={generatingSummary} className="hidden sm:flex">
              <FileText className="w-4 h-4 mr-1" />
              {generatingSummary ? "Generating…" : "Daily Summary"}
            </Button>
          </div>
        )}
      </div>

      {/* ── Section tabs ── */}
      <div className="flex border-b border-border">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setSection(s.id)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
              section === s.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {s.label}
            {s.id === "whatsapp-queue" && queueStats && (queueStats.pending + queueStats.failed) > 0 && (
              <span className="ml-1.5 bg-amber-500 text-white text-[10px] rounded-full px-1.5 py-0.5">
                {queueStats.pending + queueStats.failed}
              </span>
            )}
            {s.id === "alerts" && stats && stats.open > 0 && (
              <span className="ml-1.5 bg-destructive text-destructive-foreground text-[10px] rounded-full px-1.5 py-0.5">
                {stats.open}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Alerts section ── */}
      {section === "alerts" && (
        <>
          {scanResult && (
            <div className="bg-green-500/10 border border-green-500/30 rounded-xl px-4 py-3 text-sm text-green-700 dark:text-green-400">
              Scan complete — {scanResult.alerts_created} new alert{scanResult.alerts_created !== 1 ? "s" : ""} created.
            </div>
          )}

          {/* Stats row */}
          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[1,2,3,4].map((i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
            </div>
          ) : stats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <StatBox label="Open"          value={stats.open}                    icon={Bell}         warn={stats.open > 0} />
              <StatBox label="Critical"      value={stats.critical_open}           icon={AlertCircle}  warn={stats.critical_open > 0} />
              <StatBox label="Pending ACK"   value={stats.pending_whatsapp_ack}    icon={MessageSquare} warn={stats.pending_whatsapp_ack > 0} />
              <StatBox label="Send Failures" value={stats.failed_whatsapp_sends}   icon={AlertTriangle} warn={stats.failed_whatsapp_sends > 0} />
            </div>
          )}

          {/* Alert sub-tabs */}
          <div className="flex overflow-x-auto gap-1 pb-1 -mx-1 px-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                  tab === t.id
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                {t.label}
                {t.id === "active" && stats && stats.open > 0 && (
                  <span className="ml-1.5 bg-destructive text-destructive-foreground text-[10px] rounded-full px-1.5 py-0.5">
                    {stats.open}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Alert list */}
          {loading ? (
            <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
          ) : (
            <div className="space-y-2">
              {filteredAlerts.length === 0 ? (
                <div className="bg-card border border-border rounded-xl p-10 text-center">
                  <CheckCircle2 className="w-8 h-8 text-green-500 mx-auto mb-2" />
                  <p className="text-sm text-muted-foreground">
                    {tab === "active"  ? "All clear — no open alerts."
                    : tab === "history" ? "No alert history yet."
                    : "No alerts in this category."}
                  </p>
                </div>
              ) : (
                filteredAlerts.map((a) => (
                  <AlertCard key={a.id} alert={a} />
                ))
              )}
            </div>
          )}
        </>
      )}

      {/* ── WhatsApp Queue section ── */}
      {section === "whatsapp-queue" && (
        <Suspense fallback={<SectionSkeleton />}>
          <WhatsAppQueuePage />
        </Suspense>
      )}

      {/* ── Notification Settings section ── */}
      {section === "notification-settings" && (
        <Suspense fallback={<SectionSkeleton rows={5} />}>
          <NotificationSettingsPage />
        </Suspense>
      )}

      {summaryResult && (
        <SummaryModal result={summaryResult} onClose={() => setSummaryResult(null)} />
      )}
    </div>
  );
}
