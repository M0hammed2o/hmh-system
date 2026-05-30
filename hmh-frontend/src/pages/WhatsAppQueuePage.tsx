/**
 * WhatsApp Queue — shows all outbound notification messages with status,
 * retry count, and message body preview. Supports manual queue processing.
 */
import { useEffect, useState, useCallback } from "react";
import { MessageSquare, RefreshCw, Play, CheckCircle2, X, AlertTriangle, Clock, CheckCheck, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { alertsApi, type NotificationQueueEntry, type QueueStats, type NotificationStatus } from "@/api/alerts";
import { cn } from "@/lib/utils";

function timeAgo(iso: string) {
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const STATUS_CONFIG: Record<NotificationStatus, { label: string; icon: React.ElementType; color: string; badge: "success" | "destructive" | "secondary" | "outline" }> = {
  SENT:        { label: "Sent",        icon: CheckCircle2, color: "text-green-600 dark:text-green-400",  badge: "success"     },
  DELIVERED:   { label: "Delivered",   icon: CheckCheck,   color: "text-green-700 dark:text-green-300",  badge: "success"     },
  READ:        { label: "Read",        icon: BookOpen,     color: "text-blue-600 dark:text-blue-400",    badge: "success"     },
  MOCK_SENT:   { label: "Mock Sent",   icon: CheckCircle2, color: "text-blue-500",                       badge: "secondary"   },
  PENDING:     { label: "Pending",     icon: Clock,        color: "text-amber-500",                       badge: "secondary"   },
  FAILED:      { label: "Failed",      icon: AlertTriangle,color: "text-destructive",                    badge: "destructive" },
  ACKNOWLEDGED:{ label: "Acknowledged",icon: CheckCircle2, color: "text-green-600 dark:text-green-400",  badge: "success"     },
  CANCELLED:   { label: "Cancelled",   icon: X,            color: "text-muted-foreground",                badge: "outline"     },
};

const STATUS_TABS: Array<{ key: NotificationStatus | "ALL"; label: string }> = [
  { key: "ALL",          label: "All"         },
  { key: "PENDING",      label: "Pending"     },
  { key: "MOCK_SENT",    label: "Mock Sent"   },
  { key: "SENT",         label: "Sent"        },
  { key: "DELIVERED",    label: "Delivered"   },
  { key: "READ",         label: "Read"        },
  { key: "FAILED",       label: "Failed"      },
  { key: "ACKNOWLEDGED", label: "Acknowledged"},
  { key: "CANCELLED",    label: "Cancelled"   },
];

function QueueEntryCard({ entry }: { entry: NotificationQueueEntry }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = STATUS_CONFIG[entry.status] || STATUS_CONFIG.PENDING;
  const Icon = cfg.icon;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-2">
      {/* Header row */}
      <div className="flex items-start gap-3">
        <Icon className={cn("w-4 h-4 shrink-0 mt-0.5", cfg.color)} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium font-mono">{entry.phone_number}</span>
            <Badge variant={cfg.badge} className="text-xs">{cfg.label}</Badge>
            {entry.is_test && (
              <Badge variant="outline" className="text-xs border-amber-400 text-amber-600 bg-amber-50 dark:bg-amber-950/30 dark:text-amber-400">
                TEST
              </Badge>
            )}
            {entry.requires_acknowledgement && (
              <Badge variant={entry.acknowledged_at ? "success" : "secondary"} className="text-xs">
                {entry.acknowledged_at ? "ACK'd" : "Awaiting ACK"}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
            <span>Attempts: {entry.attempt_count}</span>
            {entry.last_attempt_at && <span>Last: {timeAgo(entry.last_attempt_at)}</span>}
            {entry.next_attempt_at && entry.status === "PENDING" && (
              <span className="text-amber-500">Next retry: {timeAgo(entry.next_attempt_at)}</span>
            )}
            <span className="ml-auto">{timeAgo(entry.created_at)}</span>
          </div>
        </div>
      </div>

      {/* Error */}
      {entry.error_message && (
        <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-1.5">
          Error: {entry.error_message}
        </p>
      )}

      {/* Message body toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-primary hover:underline"
      >
        {expanded ? "Hide message" : "View message body"}
      </button>
      {expanded && (
        <pre className="text-xs bg-muted/60 rounded-lg p-3 whitespace-pre-wrap font-mono text-muted-foreground border border-border leading-relaxed">
          {entry.message_body}
        </pre>
      )}
    </div>
  );
}

export default function WhatsAppQueuePage() {
  const [queue, setQueue] = useState<NotificationQueueEntry[]>([]);
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [statusFilter, setStatusFilter] = useState<NotificationStatus | "ALL">("ALL");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [processing, setProcessing] = useState(false);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    const [queueRes, statsRes] = await Promise.allSettled([
      alertsApi.getQueue(statusFilter === "ALL" ? undefined : statusFilter, 200),
      alertsApi.getQueueStats(),
    ]);
    if (queueRes.status === "fulfilled") setQueue(queueRes.value);
    if (statsRes.status === "fulfilled") setStats(statsRes.value);
    setLoading(false);
    setRefreshing(false);
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const handleProcess = async () => {
    setProcessing(true);
    await alertsApi.processQueue().catch(() => {});
    setProcessing(false);
    load(true);
  };

  const hasPending = (stats?.pending || 0) + (stats?.failed || 0) > 0;

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">WhatsApp Queue</h1>
          <p className="text-sm text-muted-foreground">
            {stats
              ? `${stats.pending} pending · ${stats.mock_sent} mock sent · ${stats.sent} real sent · ${stats.failed} failed`
              : "Loading…"
            }
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => load(true)} disabled={refreshing}>
            <RefreshCw className={cn("w-4 h-4", refreshing && "animate-spin")} />
          </Button>
          {hasPending && (
            <Button size="sm" onClick={handleProcess} disabled={processing}>
              <Play className="w-4 h-4 mr-1" />
              {processing ? "Processing…" : "Process Queue"}
            </Button>
          )}
        </div>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {[
            { key: "pending",      label: "Pending",       val: stats.pending,       warn: stats.pending > 0 },
            { key: "mock_sent",    label: "Mock Sent",     val: stats.mock_sent,     warn: false },
            { key: "sent",         label: "Sent",          val: stats.sent,          warn: false },
            { key: "failed",       label: "Failed",        val: stats.failed,        warn: stats.failed > 0 },
            { key: "acknowledged", label: "Acknowledged",  val: stats.acknowledged,  warn: false },
            { key: "cancelled",    label: "Cancelled",     val: stats.cancelled,     warn: false },
          ].map(({ key, label, val, warn }) => (
            <div key={key} className={cn("border rounded-xl p-3 text-center", warn ? "bg-amber-500/10 border-amber-500/30" : "bg-card border-border")}>
              <p className={cn("text-2xl font-bold", warn ? "text-amber-500" : "")}>{val}</p>
              <p className="text-xs text-muted-foreground">{label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Mock mode notice */}
      <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3 flex items-start gap-3">
        <MessageSquare className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-blue-600 dark:text-blue-400">Demo Mode — WhatsApp Disabled</p>
          <p className="text-xs text-blue-600/80 dark:text-blue-400/80 mt-0.5">
            SMTP_ENABLED=false. All messages are stored as MOCK_SENT with full message body.
            Set WHATSAPP_ENABLED=true and provide Meta credentials to send real messages.
          </p>
        </div>
      </div>

      {/* Status filter tabs */}
      <div className="flex overflow-x-auto gap-1 pb-1">
        {STATUS_TABS.map(({ key, label }) => {
          const count = key === "ALL"
            ? queue.length
            : queue.filter((e) => e.status === key).length;
          return (
            <button
              key={key}
              onClick={() => setStatusFilter(key)}
              className={cn(
                "shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                statusFilter === key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              )}
            >
              {label} ({count})
            </button>
          );
        })}
      </div>

      {/* Queue list */}
      {loading ? (
        <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
      ) : queue.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <MessageSquare className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No messages in this queue.</p>
          <p className="text-xs text-muted-foreground mt-1">Messages appear here when alerts are created or daily summaries are generated.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {queue.map((entry) => <QueueEntryCard key={entry.id} entry={entry} />)}
        </div>
      )}
    </div>
  );
}
