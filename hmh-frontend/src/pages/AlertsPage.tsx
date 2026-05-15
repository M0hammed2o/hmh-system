import { useEffect, useState, useCallback } from "react";
import {
  Bell, AlertTriangle, AlertCircle, Info, CheckCircle2, Phone,
  MessageSquare, RefreshCw, Plus, Pencil, UserX, Send, Play,
  FileText, Clock, X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  alertsApi,
  type Alert, type AlertSeverity, type AlertStats,
  type AlertRecipient, type AlertRecipientCreate,
  type NotificationQueueEntry, type QueueStats,
} from "@/api/alerts";
import { cn } from "@/lib/utils";

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

const NOTIFICATION_STATUS_COLOR: Record<string, string> = {
  SENT:        "text-green-600 dark:text-green-400",
  MOCK_SENT:   "text-blue-500",
  PENDING:     "text-amber-500",
  FAILED:      "text-destructive",
  ACKNOWLEDGED:"text-green-600 dark:text-green-400",
  CANCELLED:   "text-muted-foreground",
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

// ── Alert card ────────────────────────────────────────────────────────────────

function AlertCard({ alert, onAck, onResolve }: { alert: Alert; onAck: (id: string) => void; onResolve: (id: string) => void }) {
  const [loading, setLoading] = useState<"ack" | "resolve" | null>(null);
  const [expanded, setExpanded] = useState(false);

  const handleAck = async () => {
    setLoading("ack");
    await onAck(alert.id);
    setLoading(null);
  };
  const handleResolve = async () => {
    setLoading("resolve");
    await onResolve(alert.id);
    setLoading(null);
  };

  const typeLabel = alert.alert_type.replace(/_/g, " ");

  return (
    <div className={cn("border rounded-xl p-4 space-y-2 transition-all", SEV_STYLE[alert.severity as AlertSeverity] || "border-border bg-card")}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <Badge variant={SEV_BADGE[alert.severity as AlertSeverity] || "outline"} className="text-xs">
              {alert.severity}
            </Badge>
            <span className="text-xs text-muted-foreground font-mono">{typeLabel}</span>
            <span className="text-xs text-muted-foreground ml-auto shrink-0">{timeAgo(alert.created_at)}</span>
          </div>
          <p className="font-semibold text-sm leading-snug">{alert.title}</p>
          <p className={cn("text-xs text-muted-foreground mt-0.5", !expanded && "line-clamp-2")}>{alert.message}</p>
          {alert.message.length > 100 && (
            <button onClick={() => setExpanded(!expanded)} className="text-xs text-primary mt-0.5">
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
        </div>
        <Badge variant={alert.status === "OPEN" ? "destructive" : alert.status === "ACKNOWLEDGED" ? "secondary" : "outline"} className="text-xs shrink-0">
          {alert.status}
        </Badge>
      </div>

      {alert.status === "OPEN" && (
        <div className="flex gap-2 pt-1">
          <Button size="sm" variant="outline" onClick={handleAck} disabled={loading !== null} className="h-7 text-xs px-2.5">
            {loading === "ack" ? "…" : <><CheckCircle2 className="w-3 h-3 mr-1" />Acknowledge</>}
          </Button>
          <Button size="sm" variant="outline" onClick={handleResolve} disabled={loading !== null} className="h-7 text-xs px-2.5">
            {loading === "resolve" ? "…" : <><X className="w-3 h-3 mr-1" />Resolve</>}
          </Button>
        </div>
      )}
    </div>
  );
}

// ── Queue entry card ──────────────────────────────────────────────────────────

function QueueCard({ entry }: { entry: NotificationQueueEntry }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border border-border bg-card rounded-xl p-4 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-muted-foreground shrink-0" />
          <span className="text-sm font-medium font-mono">{entry.phone_number}</span>
        </div>
        <span className={cn("text-xs font-medium", NOTIFICATION_STATUS_COLOR[entry.status])}>
          {entry.status}
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>Attempt {entry.attempt_count}</span>
        {entry.last_attempt_at && <span>Last: {timeAgo(entry.last_attempt_at)}</span>}
        {entry.requires_acknowledgement && (
          <span className={cn("font-medium", entry.acknowledged_at ? "text-green-600 dark:text-green-400" : "text-amber-500")}>
            {entry.acknowledged_at ? "ACKed" : "Awaiting ACK"}
          </span>
        )}
      </div>
      {entry.error_message && (
        <p className="text-xs text-destructive">{entry.error_message}</p>
      )}
      <button onClick={() => setExpanded(!expanded)} className="text-xs text-primary">
        {expanded ? "Hide message" : "View message"}
      </button>
      {expanded && (
        <pre className="text-xs bg-muted rounded-lg p-3 whitespace-pre-wrap font-mono mt-1">{entry.message_body}</pre>
      )}
    </div>
  );
}

// ── Add recipient modal ───────────────────────────────────────────────────────

function AddRecipientModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<AlertRecipientCreate>({
    name: "", phone_number: "",
    receives_critical_alerts: true,
    receives_daily_summary: true,
    receives_invoice_alerts: false,
    receives_delivery_alerts: false,
    receives_vehicle_alerts: false,
    receives_material_alerts: false,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await alertsApi.createRecipient(form);
      onSaved();
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to add recipient.";
      setError(msg);
    } finally { setLoading(false); }
  };

  const toggle = (field: keyof AlertRecipientCreate) =>
    setForm((f) => ({ ...f, [field]: !f[field] }));

  const checks: { field: keyof AlertRecipientCreate; label: string }[] = [
    { field: "receives_critical_alerts", label: "Critical alerts" },
    { field: "receives_daily_summary",   label: "Daily summary" },
    { field: "receives_material_alerts", label: "Material overuse" },
    { field: "receives_delivery_alerts", label: "Delivery issues" },
    { field: "receives_invoice_alerts",  label: "Invoice alerts" },
    { field: "receives_vehicle_alerts",  label: "Vehicle/fuel" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-5">Add WhatsApp Recipient</h2>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required placeholder="e.g. Mohammed" />
          </div>
          <div className="space-y-2">
            <Label>Phone (international format)</Label>
            <Input value={form.phone_number} onChange={(e) => setForm({ ...form, phone_number: e.target.value })} required placeholder="+27831234567" />
          </div>
          <div className="space-y-2">
            <Label>Label / Role</Label>
            <Input value={form.label || ""} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="e.g. Owner, Manager" />
          </div>
          <div className="space-y-2">
            <Label>Receives alerts for</Label>
            <div className="grid grid-cols-2 gap-2">
              {checks.map(({ field, label }) => (
                <label key={field} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!!form[field]}
                    onChange={() => toggle(field)}
                    className="rounded"
                  />
                  <span className="text-sm">{label}</span>
                </label>
              ))}
            </div>
          </div>
          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">{loading ? "Adding…" : "Add Recipient"}</Button>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Recipients panel ──────────────────────────────────────────────────────────

function RecipientsPanel({ recipients, onRefresh }: { recipients: AlertRecipient[]; onRefresh: () => void }) {
  const [showAdd, setShowAdd] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, string>>({});

  const handleTest = async (id: string) => {
    setTestingId(id);
    try {
      const res = await alertsApi.testRecipient(id);
      setTestResult((prev) => ({ ...prev, [id]: res.status }));
    } catch {
      setTestResult((prev) => ({ ...prev, [id]: "ERROR" }));
    } finally { setTestingId(null); }
  };

  const handleDeactivate = async (id: string) => {
    if (!confirm("Deactivate this recipient?")) return;
    await alertsApi.deactivateRecipient(id);
    onRefresh();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{recipients.length} recipient{recipients.length !== 1 ? "s" : ""}</p>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="w-4 h-4 mr-1" />Add Recipient
        </Button>
      </div>

      {recipients.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center">
          <Phone className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No WhatsApp recipients configured.</p>
          <p className="text-xs text-muted-foreground mt-1">Add a recipient to receive alerts on WhatsApp.</p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {recipients.map((r, i) => (
            <div key={r.id} className={cn("px-4 py-3 flex items-start gap-4", i < recipients.length - 1 && "border-b border-border")}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-medium text-sm">{r.name}</p>
                  {r.label && <Badge variant="outline" className="text-xs">{r.label}</Badge>}
                  {!r.is_active && <Badge variant="secondary" className="text-xs">Inactive</Badge>}
                </div>
                <p className="text-xs text-muted-foreground font-mono mt-0.5">{r.phone_number}</p>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {r.receives_critical_alerts && <span className="text-[10px] bg-destructive/10 text-destructive rounded px-1.5 py-0.5">Critical</span>}
                  {r.receives_daily_summary    && <span className="text-[10px] bg-primary/10 text-primary rounded px-1.5 py-0.5">Daily Summary</span>}
                  {r.receives_material_alerts  && <span className="text-[10px] bg-muted text-muted-foreground rounded px-1.5 py-0.5">Materials</span>}
                  {r.receives_delivery_alerts  && <span className="text-[10px] bg-muted text-muted-foreground rounded px-1.5 py-0.5">Deliveries</span>}
                  {r.receives_invoice_alerts   && <span className="text-[10px] bg-muted text-muted-foreground rounded px-1.5 py-0.5">Invoices</span>}
                  {r.receives_vehicle_alerts   && <span className="text-[10px] bg-muted text-muted-foreground rounded px-1.5 py-0.5">Vehicles</span>}
                </div>
                {testResult[r.id] && (
                  <p className={cn("text-xs mt-1 font-medium", testResult[r.id] === "MOCK_SENT" || testResult[r.id] === "SENT" ? "text-green-600 dark:text-green-400" : "text-destructive")}>
                    Test: {testResult[r.id]}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Button size="sm" variant="ghost" onClick={() => handleTest(r.id)} disabled={testingId === r.id} className="h-7 px-2 text-xs">
                  {testingId === r.id ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                </Button>
                {r.is_active && (
                  <Button size="sm" variant="ghost" onClick={() => handleDeactivate(r.id)} className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive">
                    <UserX className="w-3 h-3" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showAdd && <AddRecipientModal onClose={() => setShowAdd(false)} onSaved={onRefresh} />}
    </div>
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

// ── Tab definition ────────────────────────────────────────────────────────────

type Tab = "all" | "critical" | "materials" | "deliveries" | "invoices" | "vehicles" | "delays" | "queue" | "recipients";

const TABS: { id: Tab; label: string }[] = [
  { id: "all",        label: "All" },
  { id: "critical",   label: "Critical" },
  { id: "materials",  label: "Materials" },
  { id: "deliveries", label: "Deliveries" },
  { id: "invoices",   label: "Invoices" },
  { id: "vehicles",   label: "Vehicles" },
  { id: "delays",     label: "Delays" },
  { id: "queue",      label: "WhatsApp Queue" },
  { id: "recipients", label: "Recipients" },
];

const TAB_TYPE_FILTER: Partial<Record<Tab, string[]>> = {
  critical:   ["CRITICAL"],  // severity filter, not type
  materials:  ["MATERIAL_OVERUSE","BOQ_VARIANCE_OVERUSE","BOQ_ALLOCATION_EXCEEDED","LOW_STOCK","NEGATIVE_STOCK"],
  deliveries: ["DELIVERY_MISMATCH","DELIVERY_NOTE_MISSING","SIGNATURE_MISSING","DELIVERY_DISCREPANCY","DELIVERY_WITHOUT_PO","DELIVERY_SIGNATURE_MISSING"],
  invoices:   ["INVOICE_MISMATCH","INVOICE_UNMATCHED","INVOICE_MISSING_DELIVERY_NOTE","OVERDUE_PAYMENT"],
  vehicles:   ["VEHICLE_REPAIR_LOGGED","FUEL_USAGE_HIGH"],
  delays:     ["LOT_DELAYED","STAGE_DELAYED","SITE_DELAY"],
};

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  const [tab, setTab] = useState<Tab>("all");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [recipients, setRecipients] = useState<AlertRecipient[]>([]);
  const [queue, setQueue] = useState<NotificationQueueEntry[]>([]);
  const [queueStats, setQueueStats] = useState<QueueStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [summaryResult, setSummaryResult] = useState<{ summary_text: string; queued: number; send_counts: Record<string, number> } | null>(null);
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [processingQueue, setProcessingQueue] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<{ alerts_created: number } | null>(null);

  const loadAll = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    try {
      const [alertData, statsData, recipientData, queueData, qsData] = await Promise.allSettled([
        alertsApi.list({ limit: 200 }),
        alertsApi.stats(),
        alertsApi.listRecipients(),
        alertsApi.getQueue(undefined, 100),
        alertsApi.getQueueStats(),
      ]);
      if (alertData.status === "fulfilled")     setAlerts(alertData.value);
      if (statsData.status === "fulfilled")     setStats(statsData.value);
      if (recipientData.status === "fulfilled") setRecipients(recipientData.value);
      if (queueData.status === "fulfilled")     setQueue(queueData.value);
      if (qsData.status === "fulfilled")        setQueueStats(qsData.value);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleAck = async (id: string) => {
    await alertsApi.acknowledge(id);
    loadAll(true);
  };

  const handleResolve = async (id: string) => {
    await alertsApi.resolve(id);
    loadAll(true);
  };

  const handleScan = async () => {
    setScanning(true); setScanResult(null);
    try {
      const res = await import("@/api/client").then(m =>
        m.default.post<{ data: { alerts_created: number } }>("/alerts/scan")
      );
      setScanResult(res.data.data);
      loadAll(true);
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

  const handleProcessQueue = async () => {
    setProcessingQueue(true);
    try {
      await alertsApi.processQueue();
      loadAll(true);
    } finally { setProcessingQueue(false); }
  };

  // Filter alerts by current tab
  const filteredAlerts = (() => {
    if (tab === "all") return alerts;
    if (tab === "critical") return alerts.filter((a) => a.severity === "CRITICAL" || a.severity === "HIGH");
    const types = TAB_TYPE_FILTER[tab];
    if (types) return alerts.filter((a) => types.includes(a.alert_type));
    return alerts;
  })();

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Alerts</h1>
          <p className="text-sm text-muted-foreground">
            {stats ? `${stats.open} open · ${stats.critical_open} critical` : "Loading…"}
          </p>
        </div>
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
      </div>
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
          <StatBox label="Open" value={stats.open} icon={Bell} warn={stats.open > 0} />
          <StatBox label="Critical" value={stats.critical_open} icon={AlertCircle} warn={stats.critical_open > 0} />
          <StatBox label="Pending ACK" value={stats.pending_whatsapp_ack} icon={MessageSquare} warn={stats.pending_whatsapp_ack > 0} />
          <StatBox label="Send Failures" value={stats.failed_whatsapp_sends} icon={AlertTriangle} warn={stats.failed_whatsapp_sends > 0} />
        </div>
      )}

      {/* Tabs */}
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
            {t.id === "queue" && queueStats && (queueStats.pending + queueStats.failed) > 0 && (
              <span className="ml-1.5 bg-amber-500 text-white text-[10px] rounded-full px-1.5 py-0.5">
                {queueStats.pending + queueStats.failed}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {loading ? (
        <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
      ) : tab === "recipients" ? (
        <RecipientsPanel recipients={recipients} onRefresh={() => loadAll(true)} />
      ) : tab === "queue" ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex gap-3 text-xs text-muted-foreground">
              {queueStats && Object.entries(queueStats).map(([k, v]) => (
                <span key={k}><span className="font-medium text-foreground">{v}</span> {k}</span>
              ))}
            </div>
            <Button size="sm" variant="outline" onClick={handleProcessQueue} disabled={processingQueue} className="h-7 text-xs">
              <Play className="w-3 h-3 mr-1" />
              {processingQueue ? "Processing…" : "Process Queue"}
            </Button>
          </div>
          {queue.length === 0 ? (
            <div className="bg-card border border-border rounded-xl p-10 text-center">
              <MessageSquare className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">No messages in queue.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {queue.map((e) => <QueueCard key={e.id} entry={e} />)}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredAlerts.length === 0 ? (
            <div className="bg-card border border-border rounded-xl p-10 text-center">
              <CheckCircle2 className="w-8 h-8 text-green-500 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">No alerts in this category.</p>
            </div>
          ) : (
            filteredAlerts.map((a) => (
              <AlertCard key={a.id} alert={a} onAck={handleAck} onResolve={handleResolve} />
            ))
          )}
        </div>
      )}

      {summaryResult && (
        <SummaryModal result={summaryResult} onClose={() => setSummaryResult(null)} />
      )}
    </div>
  );
}
