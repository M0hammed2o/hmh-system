/**
 * EmailDraftModal — reusable email compose/send modal.
 *
 * Supports three modes:
 *   "mr"  — MR enquiry email  (POST /material-requests/{id}/prepare-email)
 *   "po"  — PO confirmation   (POST /purchase-orders/{id}/prepare-email)
 *   "free"— free-form (caller provides initial subject/body/to directly)
 *
 * Status lifecycle: DRAFT (queued) → SENT | MANUAL_SENT | FAILED
 */
import { useEffect, useState } from "react";
import { Mail, Send, Check, X, Copy, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/shared/Modal";
import client from "@/api/client";

export type EmailDraftMode = "mr" | "po" | "free";

interface EmailDraftModalProps {
  open:       boolean;
  onClose:    () => void;
  mode:       EmailDraftMode;
  entityId:   string;                // mr_id or po_id (ignored in "free" mode)
  title?:     string;
  // Free-mode initial values (optional)
  initialTo?:      string;
  initialSubject?: string;
  initialBody?:    string;
}

interface DraftState {
  to:      string;
  subject: string;
  body:    string;
  status:  string;
  exists:  boolean;
}

export function EmailDraftModal({
  open, onClose, mode, entityId, title,
  initialTo = "", initialSubject = "", initialBody = "",
}: EmailDraftModalProps) {
  const [draft,     setDraft]     = useState<DraftState | null>(null);
  const [loading,   setLoading]   = useState(false);
  const [saving,    setSaving]    = useState(false);
  const [sending,   setSending]   = useState(false);
  const [marking,   setMarking]   = useState(false);
  const [copied,    setCopied]    = useState(false);
  const [msg,       setMsg]       = useState("");
  const [error,     setError]     = useState("");

  const baseUrl = mode === "mr"
    ? `/material-requests/${entityId}/prepare-email`
    : mode === "po"
    ? `/purchase-orders/${entityId}/prepare-email`
    : null;

  // Load or create draft when modal opens
  useEffect(() => {
    if (!open) return;
    setMsg(""); setError("");

    if (mode === "free") {
      setDraft({ to: initialTo, subject: initialSubject, body: initialBody, status: "DRAFT", exists: false });
      return;
    }

    setLoading(true);
    // Try to GET existing draft first
    client.get<{ data: DraftState & { exists: boolean } }>(baseUrl!)
      .then(r => {
        const d = r.data.data;
        if (d.exists) {
          setDraft({ to: d.to_email as unknown as string ?? (d as unknown as { to: string }).to ?? "",
                     subject: d.subject ?? (d as unknown as { email_subject: string }).email_subject ?? "",
                     body:    d.body_html ?? (d as unknown as { body: string }).body ?? "",
                     status:  d.status,
                     exists:  true });
        } else {
          // Create new draft
          prepareDraft();
        }
      })
      .catch(() => prepareDraft())
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, entityId]);

  const prepareDraft = async () => {
    if (!baseUrl) return;
    setLoading(true);
    try {
      const r = await client.post<{ data: { to_email: string; subject: string; body_html: string; status: string } }>(baseUrl);
      const d = r.data.data;
      setDraft({ to: d.to_email, subject: d.subject, body: d.body_html, status: d.status, exists: true });
    } catch {
      setError("Failed to prepare email draft.");
    } finally { setLoading(false); }
  };

  const saveDraft = async () => {
    if (!draft || !baseUrl) return;
    setSaving(true); setMsg(""); setError("");
    try {
      await client.patch(baseUrl, null, {
        params: { subject: draft.subject, body_html: draft.body, to_email: draft.to },
      });
      setMsg("Draft saved.");
    } catch { setError("Failed to save draft."); }
    finally { setSaving(false); }
  };

  const sendNow = async () => {
    if (!draft) return;
    setSending(true); setMsg(""); setError("");
    try {
      if (baseUrl) {
        // Save latest edits first
        await client.patch(baseUrl, null, {
          params: { subject: draft.subject, body_html: draft.body, to_email: draft.to },
        }).catch(() => {});
      }
      // Send
      const sendUrl = mode === "mr"
        ? `/material-requests/${entityId}/send-email`
        : mode === "po"
        ? `/purchase-orders/${entityId}/send-email`
        : null;
      if (sendUrl) {
        const r = await client.post<{ data: { status: string; sent_to: string } }>(sendUrl);
        const d = r.data.data;
        setMsg(d.status === "sent"
          ? `Email sent to ${d.sent_to ?? draft.to}.`
          : `Email ${d.status} (may be mock mode — body saved in system).`);
        setDraft(prev => prev ? { ...prev, status: d.status } : null);
      } else {
        // Free-mode: just mark as sent manually
        setMsg("Email marked as sent (free mode — use SMTP for real sending).");
        setDraft(prev => prev ? { ...prev, status: "MANUAL_SENT" } : null);
      }
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to send email.");
    } finally { setSending(false); }
  };

  const markSent = async () => {
    setMarking(true); setMsg(""); setError("");
    try {
      const markUrl = mode === "mr"
        ? `/material-requests/${entityId}/mark-sent`
        : mode === "po"
        ? `/purchase-orders/${entityId}/mark-sent`
        : null;
      if (markUrl) {
        await client.post(markUrl);
        setMsg("Marked as manually sent.");
        setDraft(prev => prev ? { ...prev, status: "MANUAL_SENT" } : null);
      }
    } catch { setError("Failed to mark as sent."); }
    finally { setMarking(false); }
  };

  const copyEmail = () => {
    if (!draft) return;
    navigator.clipboard.writeText(
      `To: ${draft.to}\nSubject: ${draft.subject}\n\n${draft.body.replace(/<[^>]+>/g, "")}`
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isSent = draft?.status === "sent" || draft?.status === "MANUAL_SENT";

  return (
    <Modal open={open} onClose={onClose} title={title ?? "Email Draft"} size="lg">
      <div className="p-5 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-8 gap-2 text-sm text-muted-foreground">
            <RefreshCw className="w-4 h-4 animate-spin" />Preparing draft…
          </div>
        ) : draft ? (
          <>
            {isSent && (
              <div className="bg-green-500/10 border border-green-500/30 rounded-lg px-3 py-2 text-xs text-green-700 dark:text-green-400 flex items-center gap-2">
                <Check className="w-3.5 h-3.5 shrink-0" />
                Email status: <strong>{draft.status.replace(/_/g, " ")}</strong>
              </div>
            )}

            {/* To */}
            <div className="space-y-1">
              <Label className="text-xs">To</Label>
              <Input
                value={draft.to}
                onChange={e => setDraft(d => d ? { ...d, to: e.target.value } : null)}
                placeholder="supplier@email.com"
                className="text-sm"
              />
            </div>

            {/* Subject */}
            <div className="space-y-1">
              <Label className="text-xs">Subject</Label>
              <Input
                value={draft.subject}
                onChange={e => setDraft(d => d ? { ...d, subject: e.target.value } : null)}
                className="text-sm"
              />
            </div>

            {/* Body */}
            <div className="space-y-1">
              <Label className="text-xs">Body</Label>
              <textarea
                value={draft.body}
                onChange={e => setDraft(d => d ? { ...d, body: e.target.value } : null)}
                rows={10}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs font-mono resize-y
                           focus:outline-none focus:ring-1 focus:ring-ring"
                placeholder="Email body (HTML or plain text)"
              />
              <p className="text-[10px] text-muted-foreground">HTML is supported. Preview in a browser before sending.</p>
            </div>

            {msg   && <p className="text-xs text-green-600 bg-green-50 border border-green-200 rounded-lg px-3 py-2">{msg}</p>}
            {error && <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}

            {/* Actions */}
            <div className="flex flex-wrap gap-2 pt-1 border-t border-border">
              <Button size="sm" variant="outline" onClick={saveDraft} disabled={saving || isSent} className="text-xs h-8">
                {saving ? <RefreshCw className="w-3 h-3 mr-1 animate-spin" /> : null}
                {saving ? "Saving…" : "Save Draft"}
              </Button>
              <Button size="sm" onClick={sendNow} disabled={sending || isSent} className="text-xs h-8 gap-1">
                <Send className="w-3 h-3" />
                {sending ? "Sending…" : "Send Now"}
              </Button>
              <Button size="sm" variant="outline" onClick={markSent} disabled={marking || isSent} className="text-xs h-8 gap-1">
                <Mail className="w-3 h-3" />
                {marking ? "Marking…" : "Mark as Sent"}
              </Button>
              <Button size="sm" variant="ghost" onClick={copyEmail} className="text-xs h-8 gap-1 ml-auto">
                {copied ? <Check className="w-3 h-3 text-green-600" /> : <Copy className="w-3 h-3" />}
                {copied ? "Copied" : "Copy"}
              </Button>
              <Button size="sm" variant="ghost" onClick={onClose} className="text-xs h-8">
                <X className="w-3 h-3 mr-1" />Close
              </Button>
            </div>
          </>
        ) : (
          <div className="py-6 text-center text-sm text-muted-foreground">
            <p>Could not load email draft.</p>
            <Button size="sm" variant="outline" onClick={prepareDraft} className="mt-3">Retry</Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
