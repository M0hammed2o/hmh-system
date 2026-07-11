/**
 * Notification Settings — Phase 3Q.1.
 * Recipient management + category subscriptions + project scoping.
 * Office-only page.
 */

import React, { useEffect, useState } from "react";
import {
  Plus, Trash2, Send, CheckCircle2, AlertTriangle,
  MessageSquare, RefreshCw, Edit2, X, Clock, CreditCard,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/shared/Modal";
import { PageHeader } from "@/components/shared/PageHeader";
import { projectsApi, type Project } from "@/api/projects";
import {
  notificationSettingsApi,
  type AlertRecipient,
  type RecipientCreate,
  type QueueStats,
  ALERT_CATEGORIES,
} from "@/api/notificationSettings";

// ── Recipient Form Modal ──────────────────────────────────────────────────────

function RecipientModal({
  open,
  existing,
  projects,
  onClose,
  onSaved,
}: {
  open: boolean;
  existing: AlertRecipient | null;
  projects: Project[];
  onClose: () => void;
  onSaved: (r: AlertRecipient) => void;
}) {
  const [name, setName]               = useState(existing?.name ?? "");
  const [phone, setPhone]             = useState(existing?.phone_number ?? "");
  const [label, setLabel]             = useState(existing?.label ?? "");
  const [projectId, setProjectId]     = useState(existing?.project_id ?? "");
  const [cats, setCats]               = useState<Record<string, boolean>>(() => {
    const base: Record<string, boolean> = {};
    for (const c of ALERT_CATEGORIES) {
      base[c.key] = existing ? (existing[c.key as keyof AlertRecipient] as boolean) : (c.key === "receives_critical_alerts" || c.key === "receives_daily_summary");
    }
    return base;
  });
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState("");

  useEffect(() => {
    setName(existing?.name ?? "");
    setPhone(existing?.phone_number ?? "");
    setLabel(existing?.label ?? "");
    setProjectId(existing?.project_id ?? "");
    const next: Record<string, boolean> = {};
    for (const c of ALERT_CATEGORIES) {
      next[c.key] = existing ? (existing[c.key as keyof AlertRecipient] as boolean) : (c.key === "receives_critical_alerts" || c.key === "receives_daily_summary");
    }
    setCats(next);
  }, [existing, open]);

  const handleSave = async () => {
    if (!name.trim() || !phone.trim()) return;
    setSaving(true); setError("");
    try {
      const payload: RecipientCreate = {
        name: name.trim(),
        phone_number: phone.trim(),
        label: label.trim() || null,
        project_id: projectId || null,
        ...cats,
      };
      let saved: AlertRecipient;
      if (existing) {
        saved = await notificationSettingsApi.updateRecipient(existing.id, payload);
      } else {
        saved = await notificationSettingsApi.createRecipient(payload);
      }
      onSaved(saved);
      onClose();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to save.");
    } finally { setSaving(false); }
  };

  return (
    <Modal open={open} title={existing ? "Edit Recipient" : "Add Recipient"} onClose={onClose} size="md">
      <div className="p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label>Name *</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Site Manager" />
          </div>
          <div className="space-y-1.5">
            <Label>WhatsApp Number *</Label>
            <Input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+27831234567" />
          </div>
          <div className="space-y-1.5">
            <Label>Label (optional)</Label>
            <Input value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. Owner" />
          </div>
          <div className="space-y-1.5">
            <Label>Project scope</Label>
            <select
              value={projectId}
              onChange={e => setProjectId(e.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— All projects —</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">Alert categories</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {ALERT_CATEGORIES.map(cat => (
              <label key={cat.key} className="flex items-start gap-2.5 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={cats[cat.key] ?? false}
                  onChange={e => setCats(prev => ({ ...prev, [cat.key]: e.target.checked }))}
                  className="mt-0.5 accent-primary"
                />
                <div>
                  <p className="text-sm font-medium group-hover:text-primary transition-colors">{cat.label}</p>
                  <p className="text-[11px] text-muted-foreground">{cat.description}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}

        <div className="flex gap-2 pt-1">
          <Button onClick={handleSave} disabled={saving || !name.trim() || !phone.trim()} className="flex-1">
            {saving ? "Saving…" : existing ? "Save Changes" : "Add Recipient"}
          </Button>
          <Button variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
        </div>
      </div>
    </Modal>
  );
}

// ── Category badge pills ──────────────────────────────────────────────────────

function CategoryPills({ recipient }: { recipient: AlertRecipient }) {
  const active = ALERT_CATEGORIES.filter(c => recipient[c.key as keyof AlertRecipient]);
  if (active.length === 0) return <span className="text-xs text-muted-foreground">None</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {active.map(c => (
        <span key={c.key} className="text-[10px] bg-primary/10 text-primary rounded px-1.5 py-0.5 font-medium">
          {c.label}
        </span>
      ))}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function NotificationSettingsPage() {
  const [recipients, setRecipients] = useState<AlertRecipient[]>([]);
  const [projects, setProjects]     = useState<Project[]>([]);
  const [stats, setStats]           = useState<QueueStats | null>(null);
  const [loading, setLoading]       = useState(true);
  const [showInactive, setShowInactive] = useState(false);
  const [showModal, setShowModal]   = useState(false);
  const [editTarget, setEditTarget] = useState<AlertRecipient | null>(null);
  const [testingId, setTestingId]   = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, string>>({});
  const [sendingSummary,  setSendingSummary]  = useState(false);
  const [summaryResult,   setSummaryResult]   = useState<string | null>(null);
  const [scanningPayment, setScanningPayment] = useState(false);
  const [scanResult,      setScanResult]      = useState<string | null>(null);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [recs, proj, s] = await Promise.all([
        notificationSettingsApi.listRecipients({ include_inactive: showInactive }),
        projectsApi.list(1, 100).then(r => r.items),
        notificationSettingsApi.getQueueStats().catch(() => null),
      ]);
      setRecipients(recs);
      setProjects(proj);
      setStats(s);
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  useEffect(() => { loadAll(); }, [showInactive]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Deactivate "${name}"? They will no longer receive alerts.`)) return;
    await notificationSettingsApi.deleteRecipient(id);
    setRecipients(prev => prev.filter(r => r.id !== id));
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    try {
      const result = await notificationSettingsApi.sendTest(id);
      setTestResult(prev => ({ ...prev, [id]: `Mock sent to ${result.phone}` }));
    } catch {
      setTestResult(prev => ({ ...prev, [id]: "Test failed" }));
    } finally { setTestingId(null); }
  };

  const handleTriggerSummary = async () => {
    setSendingSummary(true);
    setSummaryResult(null);
    try {
      const result = await notificationSettingsApi.triggerDailySummary();
      setSummaryResult(`Sent to ${result.queued} recipient(s) — ${result.sent} sent, ${result.mock_sent} mock, ${result.failed} failed.`);
    } catch {
      setSummaryResult("Failed to trigger summary.");
    } finally {
      setSendingSummary(false);
    }
  };

  const handleScanPaymentDue = async () => {
    setScanningPayment(true);
    setScanResult(null);
    try {
      const result = await notificationSettingsApi.scanPaymentDue();
      setScanResult(
        `Scanned ${result.scanned} invoices — ${result.warnings_queued} due-soon alerts, ${result.overdue_queued} overdue alerts, ${result.already_notified} already notified.`
      );
    } catch {
      setScanResult("Payment due scan failed.");
    } finally {
      setScanningPayment(false);
    }
  };

  const handleSaved = (r: AlertRecipient) => {
    setRecipients(prev => {
      const idx = prev.findIndex(x => x.id === r.id);
      if (idx >= 0) return prev.map(x => x.id === r.id ? r : x);
      return [r, ...prev];
    });
  };

  const projectName = (pid: string | null) =>
    projects.find(p => p.id === pid)?.name ?? "All projects";

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Notification Settings"
        description="Manage WhatsApp alert recipients and category subscriptions."
        actions={
          <Button size="sm" onClick={() => { setEditTarget(null); setShowModal(true); }}>
            <Plus className="w-4 h-4" />
            Add Recipient
          </Button>
        }
      />

      {/* Queue stats banner */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {[
            { label: "Pending",      value: stats.pending,      color: "text-amber-600" },
            { label: "Sent",         value: stats.sent,         color: "text-green-600" },
            { label: "Mock Sent",    value: stats.mock_sent,    color: "text-blue-500" },
            { label: "Failed",       value: stats.failed,       color: "text-destructive" },
            { label: "Acknowledged", value: stats.acknowledged, color: "text-green-600" },
          ].map(s => (
            <div key={s.label} className="bg-card border border-border rounded-xl px-4 py-3">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide">{s.label}</p>
              <p className={`text-xl font-bold tabular-nums ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Info banner */}
      <div className="bg-blue-50 border border-blue-200 dark:bg-blue-950/30 dark:border-blue-800 rounded-xl px-4 py-3 flex items-start gap-2 text-xs text-blue-700 dark:text-blue-300">
        <MessageSquare className="w-4 h-4 shrink-0 mt-0.5" />
        <div>
          <strong>Template-based messages only.</strong> WhatsApp alerts are operational notifications — they never approve requests, create payments, or modify data.
          Set <code className="bg-blue-100 dark:bg-blue-900 px-1 rounded">WHATSAPP_ENABLED=true</code> and{" "}
          <code className="bg-blue-100 dark:bg-blue-900 px-1 rounded">WHATSAPP_ALERT_TEMPLATE_NAME</code> in your environment to send real messages.
          Until then, all messages are stored as <strong>MOCK_SENT</strong>.
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={showInactive} onChange={e => setShowInactive(e.target.checked)} className="accent-primary" />
          Show inactive recipients
        </label>
        <div className="flex items-center gap-2 flex-wrap">
          <Button size="sm" variant="outline" onClick={loadAll}>
            <RefreshCw className="w-3.5 h-3.5 mr-1" />Refresh
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleTriggerSummary}
            disabled={sendingSummary}
            className="border-amber-400 text-amber-700 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-950/30"
          >
            <Clock className="w-3.5 h-3.5 mr-1" />
            {sendingSummary ? "Sending…" : "Send Daily Summary Now"}
          </Button>
          {summaryResult && (
            <span className="text-xs text-muted-foreground">{summaryResult}</span>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={handleScanPaymentDue}
            disabled={scanningPayment}
            className="border-blue-400 text-blue-700 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/30"
          >
            <CreditCard className="w-3.5 h-3.5 mr-1" />
            {scanningPayment ? "Scanning…" : "Scan Payment Due Now"}
          </Button>
          {scanResult && (
            <span className="text-xs text-muted-foreground">{scanResult}</span>
          )}
        </div>
      </div>

      {/* Recipients table */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 rounded-xl" />)}
        </div>
      ) : recipients.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <MessageSquare className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground mb-3">No recipients configured.</p>
          <Button size="sm" onClick={() => { setEditTarget(null); setShowModal(true); }}>
            <Plus className="w-4 h-4 mr-1" />Add First Recipient
          </Button>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Recipient</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Phone</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Scope</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Categories</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {recipients.map(r => (
                <React.Fragment key={r.id}>
                  <tr className={`border-b border-border last:border-0 ${r.is_active ? "hover:bg-muted/30" : "opacity-50"} transition-colors`}>
                    <td className="px-4 py-3">
                      <p className="font-medium">{r.name}</p>
                      {r.label && <p className="text-xs text-muted-foreground">{r.label}</p>}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs hidden sm:table-cell">{r.phone_number}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground hidden md:table-cell">
                      {r.project_id ? (
                        <span className="bg-primary/10 text-primary rounded px-1.5 py-0.5 font-medium text-[10px]">
                          {projectName(r.project_id)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">All projects</span>
                      )}
                    </td>
                    <td className="px-4 py-3"><CategoryPills recipient={r} /></td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      <Badge variant={r.is_active ? "success" : "secondary"}>
                        {r.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1 justify-end">
                        {testResult[r.id] && (
                          <span className="text-[10px] text-green-600">{testResult[r.id]}</span>
                        )}
                        <button
                          onClick={() => handleTest(r.id)}
                          disabled={testingId === r.id || !r.is_active}
                          className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-primary transition-colors disabled:opacity-40"
                          title="Send test message"
                        >
                          {testingId === r.id
                            ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            : <Send className="w-3.5 h-3.5" />}
                        </button>
                        <button
                          onClick={() => { setEditTarget(r); setShowModal(true); }}
                          className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-primary transition-colors"
                          title="Edit recipient"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        {r.is_active && (
                          <button
                            onClick={() => handleDelete(r.id, r.name)}
                            className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                            title="Deactivate"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Last-inbound timestamps (24h window info) */}
      {recipients.some(r => r.last_inbound_at) && (
        <div className="bg-muted/30 rounded-xl px-4 py-3 text-xs text-muted-foreground space-y-1">
          <p className="font-medium">24-hour conversation windows</p>
          {recipients.filter(r => r.last_inbound_at).map(r => (
            <p key={r.id}>
              {r.name}: last inbound {new Date(r.last_inbound_at!).toLocaleString()}
              {" — "}
              {Date.now() - new Date(r.last_inbound_at!).getTime() < 86400000
                ? <span className="text-green-600 font-medium">window open (free-form ok)</span>
                : <span className="text-amber-600">window closed (template required)</span>}
            </p>
          ))}
        </div>
      )}

      <RecipientModal
        open={showModal}
        existing={editTarget}
        projects={projects}
        onClose={() => setShowModal(false)}
        onSaved={handleSaved}
      />
    </div>
  );
}
