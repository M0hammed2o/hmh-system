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
import { useEffect, useRef, useState } from "react";
import { Mail, Send, Check, X, Copy, RefreshCw, Paperclip, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/shared/Modal";
import client from "@/api/client";
import { gmailApi } from "@/api/gmail";

const ALLOWED_EXTS = [".pdf", ".jpg", ".jpeg", ".png", ".gif", ".xls", ".xlsx", ".csv"];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

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
  const [files,     setFiles]     = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
        // Free-mode: use compose-send endpoint (supports real SMTP + attachments)
        const d = await gmailApi.composeSend(draft.to, draft.subject, draft.body, files);
        const attNote = files.length > 0 ? ` (${d.attachment_count} attachment${d.attachment_count !== 1 ? "s" : ""})` : "";
        setMsg(d.status === "SENT"
          ? `Email sent to ${draft.to}${attNote}.`
          : `Email ${d.status}${attNote} (SMTP not configured — body recorded only).`);
        setDraft(prev => prev ? { ...prev, status: d.status === "SENT" ? "sent" : "MOCK_SENT" } : null);
        setFiles([]);
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

            {/* File attachments — free mode only */}
            {mode === "free" && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Label className="text-xs">Attachments</Label>
                  <span className="text-[10px] text-muted-foreground">(PDF, JPEG, PNG, GIF, XLS, XLSX, CSV — max 10 MB each)</span>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.jpg,.jpeg,.png,.gif,.xls,.xlsx,.csv"
                  className="hidden"
                  onChange={e => {
                    const selected = Array.from(e.target.files ?? []);
                    const valid = selected.filter(f => {
                      const ext = "." + f.name.split(".").pop()!.toLowerCase();
                      return ALLOWED_EXTS.includes(ext) && f.size <= MAX_FILE_SIZE;
                    });
                    const rejected = selected.length - valid.length;
                    if (rejected > 0) setError(`${rejected} file(s) rejected (type or size limit).`);
                    setFiles(prev => {
                      const combined = [...prev, ...valid];
                      return combined.slice(0, 5);
                    });
                    e.target.value = "";
                  }}
                />
                <div className="flex flex-wrap gap-1.5">
                  {files.map((f, i) => (
                    <div key={i} className="flex items-center gap-1 bg-muted/60 border border-border rounded px-2 py-1 text-xs">
                      <Paperclip className="w-3 h-3 text-muted-foreground shrink-0" />
                      <span className="max-w-[120px] truncate">{f.name}</span>
                      <span className="text-muted-foreground">({(f.size / 1024).toFixed(0)} KB)</span>
                      <button onClick={() => setFiles(prev => prev.filter((_, j) => j !== i))}
                        className="ml-1 text-muted-foreground hover:text-destructive">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                  {files.length < 5 && (
                    <Button size="sm" variant="outline" type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="text-xs h-7 px-2 gap-1">
                      <Paperclip className="w-3 h-3" />
                      Add file
                    </Button>
                  )}
                </div>
              </div>
            )}

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
