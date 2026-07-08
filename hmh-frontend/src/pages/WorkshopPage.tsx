/**
 * WorkshopPage — Office management of vehicle spare parts.
 *
 * Tabs:
 *   Requests  — approve / reject workshop MRs from site staff
 *   Parts     — parts catalog (categories + items) with stock adjustment
 *   Issuances — parts-to-vehicle issuance log + issue parts manually
 *   Suppliers — link suppliers to parts categories
 */

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/hooks/useAuth";
import {
  Wrench, ClipboardList, Package, Building2, CheckCircle2, Ban,
  ChevronRight, Plus, RefreshCw, Trash2, X, Pencil, TrendingDown,
  TrendingUp, AlertTriangle, Clock, Send, Car, History, Mail,
} from "lucide-react";
import {
  workshopApi,
  type WorkshopMR,
  type WorkshopMRStatus,
  type WorkshopItem,
  type WorkshopCategory,
  type WorkshopSupplierLink,
  type WorkshopIssuance,
  type WorkshopIssuanceCreate,
  type WorkshopMREmailLog,
  type WorkshopQuote,
  type WorkshopItemCreate,
  type WorkshopItemUpdate,
  type WorkshopCategoryCreate,
} from "@/api/workshop";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { vehiclesApi, type Vehicle } from "@/api/vehicles";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// ── Shared helpers ────────────────────────────────────────────────────────────

const MR_STATUS_BADGE: Record<string, string> = {
  DRAFT:     "bg-gray-100 text-gray-600 border-gray-200",
  SUBMITTED: "bg-blue-100 text-blue-700 border-blue-200",
  APPROVED:  "bg-green-100 text-green-700 border-green-200",
  REJECTED:  "bg-red-100 text-red-700 border-red-200",
};

const MR_STATUS_LABEL: Record<string, string> = {
  DRAFT:     "Draft",
  SUBMITTED: "Pending",
  APPROVED:  "Approved",
  REJECTED:  "Rejected",
};

const PRIORITY_BADGE: Record<string, string> = {
  LOW:    "bg-gray-100 text-gray-500 border-gray-200",
  NORMAL: "",
  HIGH:   "bg-amber-100 text-amber-700 border-amber-200",
  URGENT: "bg-red-100 text-red-700 border-red-200",
};

function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

// ── Modal shell ───────────────────────────────────────────────────────────────

function Modal({ title, onClose, children, wide = false }: {
  title: string; onClose: () => void; children: React.ReactNode; wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className={cn(
        "bg-card rounded-2xl shadow-xl w-full max-h-[90vh] overflow-y-auto",
        wide ? "max-w-2xl" : "max-w-md"
      )}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-border sticky top-0 bg-card z-10">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5 space-y-4">{children}</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 1 — Workshop MR Requests
// ─────────────────────────────────────────────────────────────────────────────

function RejectModal({ mr, onClose, onRejected }: {
  mr: WorkshopMR; onClose: () => void; onRejected: (mr: WorkshopMR) => void;
}) {
  const [reason,  setReason]  = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const submit = async () => {
    setLoading(true);
    setError("");
    try {
      const updated = await workshopApi.rejectMR(mr.id, reason.trim() || undefined);
      onRejected(updated);
    } catch {
      setError("Failed to reject MR.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={`Reject ${mr.mr_number}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Vehicle: <strong className="text-foreground">{mr.vehicle?.registration ?? mr.vehicle_id}</strong>
          {" · "}{mr.vehicle?.name}
        </p>
        <div className="space-y-1.5">
          <Label>Reason for rejection (optional)</Label>
          <textarea
            rows={3}
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder="Explain why the request is being rejected…"
            className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button variant="destructive" className="flex-1" onClick={submit} disabled={loading}>
            {loading ? "Rejecting…" : "Reject MR"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

const VOTES_REQUIRED = 3;

const EMAIL_STATUS_STYLE: Record<string, string> = {
  SENT:      "bg-green-50 text-green-700 border-green-200",
  MOCK_SENT: "bg-blue-50 text-blue-700 border-blue-200",
  FAILED:    "bg-red-50 text-red-700 border-red-200",
};

function EmailStatusPanel({
  logs, onSend, sending,
}: {
  logs: WorkshopMREmailLog[];
  onSend: (forceResend: boolean) => void;
  sending: boolean;
}) {
  const hasSent = logs.some(l => l.status === "SENT" || l.status === "MOCK_SENT");

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Supplier Quote Request</p>
        <Button
          size="sm"
          variant={hasSent ? "outline" : "default"}
          disabled={sending}
          onClick={() => onSend(hasSent)}
          className="h-7 text-xs px-3 gap-1.5"
        >
          <Mail className="w-3.5 h-3.5" />
          {sending ? "Sending…" : hasSent ? "Resend to Suppliers" : "Send to Suppliers"}
        </Button>
      </div>

      {logs.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Not sent yet. Click "Send to Suppliers" to email linked suppliers for a quote.
        </p>
      ) : (
        <div className="space-y-1.5">
          {logs.map(log => (
            <div key={log.id} className={cn(
              "flex items-center justify-between text-xs px-3 py-2 rounded-lg border",
              EMAIL_STATUS_STYLE[log.status] ?? "bg-muted text-muted-foreground border-border"
            )}>
              <div className="flex items-center gap-2 min-w-0">
                <Mail className="w-3.5 h-3.5 shrink-0" />
                <div className="min-w-0">
                  <p className="font-medium truncate">
                    {log.supplier?.name ?? log.sent_to_email}
                  </p>
                  <p className="text-[11px] opacity-75 truncate">
                    {log.sent_to_email}
                  </p>
                </div>
              </div>
              <div className="text-right shrink-0 ml-3">
                <p className="font-semibold">{log.status}</p>
                {log.sent_at && (
                  <p className="text-[11px] opacity-75">
                    {new Date(log.sent_at).toLocaleDateString("en-ZA", { day: "numeric", month: "short" })}
                  </p>
                )}
                {log.error_message && (
                  <p className="text-[11px] text-red-600 max-w-[160px] truncate" title={log.error_message}>
                    {log.error_message}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function VoteProgress({ mr, userId }: { mr: WorkshopMR; userId: string | undefined }) {
  const nonOverride = mr.approvals.filter(a => !a.is_override);
  const hasVoted = userId ? nonOverride.some(a => a.approved_by === userId) : false;
  const pct = Math.min((nonOverride.length / VOTES_REQUIRED) * 100, 100);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground font-medium">Approval votes</span>
        <span className={cn("font-semibold", nonOverride.length >= VOTES_REQUIRED ? "text-green-600" : "text-amber-600")}>
          {nonOverride.length} / {VOTES_REQUIRED}
        </span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", nonOverride.length >= VOTES_REQUIRED ? "bg-green-500" : "bg-amber-400")}
          style={{ width: `${pct}%` }}
        />
      </div>
      {nonOverride.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {nonOverride.map(a => (
            <span key={a.id} className="text-xs px-2 py-0.5 bg-green-50 text-green-700 border border-green-200 rounded-full flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" />
              {a.voter?.full_name ?? "Office user"}
            </span>
          ))}
        </div>
      )}
      {hasVoted && (
        <p className="text-xs text-muted-foreground">You have already voted on this request.</p>
      )}
    </div>
  );
}

const QUOTE_STATUS_STYLE: Record<string, string> = {
  PENDING:  "bg-amber-50 text-amber-700 border-amber-200",
  APPROVED: "bg-green-50 text-green-700 border-green-200",
  REJECTED: "bg-red-50 text-red-700 border-red-200",
};

function UploadQuoteModal({
  mr,
  onClose,
  onUploaded,
}: {
  mr: WorkshopMR;
  onClose: () => void;
  onUploaded: (updatedMr: WorkshopMR) => void;
}) {
  const supplierOptions = mr.email_logs
    .filter(l => l.supplier)
    .map(l => l.supplier!)
    .filter((s, i, arr) => arr.findIndex(x => x.id === s.id) === i);

  const [supplierId, setSupplierId] = useState(supplierOptions[0]?.id ?? "");
  const [supplierName, setSupplierName] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("ZAR");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const useCustomSupplier = supplierId === "__custom__" || supplierOptions.length === 0;

  const submit = async () => {
    setLoading(true);
    setError("");
    try {
      const resolvedSupplierId = (!useCustomSupplier && supplierId) ? supplierId : null;
      const resolvedSupplierName = useCustomSupplier ? supplierName.trim() : null;

      let q = await workshopApi.createQuote({
        workshop_mr_id: mr.id,
        supplier_id: resolvedSupplierId,
        supplier_name: resolvedSupplierName,
        total_amount: amount ? parseFloat(amount) : null,
        currency,
        notes: notes.trim() || null,
      });

      if (file) {
        q = await workshopApi.uploadQuoteFile(q.id, file);
      }

      const updated = await workshopApi.getMR(mr.id);
      onUploaded(updated);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to upload quote.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="Upload Supplier Quote" onClose={onClose}>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>Supplier</Label>
          {supplierOptions.length > 0 ? (
            <select
              value={supplierId}
              onChange={e => setSupplierId(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
            >
              {supplierOptions.map(s => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
              <option value="__custom__">Other supplier…</option>
            </select>
          ) : null}
          {useCustomSupplier && (
            <Input
              placeholder="Supplier name"
              value={supplierName}
              onChange={e => setSupplierName(e.target.value)}
            />
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Total Amount</Label>
            <Input
              type="number"
              min="0"
              step="0.01"
              placeholder="0.00"
              value={amount}
              onChange={e => setAmount(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Currency</Label>
            <select
              value={currency}
              onChange={e => setCurrency(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
            >
              <option>ZAR</option>
              <option>USD</option>
              <option>EUR</option>
            </select>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Quote Document (PDF)</Label>
          <input
            type="file"
            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
            onChange={e => setFile(e.target.files?.[0] ?? null)}
            className="w-full text-sm text-muted-foreground file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-input file:text-sm file:font-medium file:bg-muted file:text-foreground hover:file:bg-muted/70 cursor-pointer"
          />
        </div>

        <div className="space-y-1.5">
          <Label>Notes (optional)</Label>
          <textarea
            rows={2}
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Any additional notes…"
            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm resize-none"
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex gap-2 pt-1">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>
            {loading ? "Uploading…" : "Submit Quote"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function QuoteVoteProgress({ quote, userId }: { quote: WorkshopQuote; userId: string | undefined }) {
  const nonOverride = quote.approvals.filter(a => !a.is_override);
  const pct = Math.min((nonOverride.length / VOTES_REQUIRED) * 100, 100);
  return (
    <div className="space-y-1.5 mt-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">Approval votes</span>
        <span className={cn("font-semibold", nonOverride.length >= VOTES_REQUIRED ? "text-green-600" : "text-amber-600")}>
          {nonOverride.length}/{VOTES_REQUIRED}
        </span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full", nonOverride.length >= VOTES_REQUIRED ? "bg-green-500" : "bg-amber-400")}
          style={{ width: `${pct}%` }}
        />
      </div>
      {nonOverride.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {nonOverride.map(a => (
            <span key={a.id} className="text-[11px] px-1.5 py-0.5 bg-green-50 text-green-700 border border-green-200 rounded-full">
              {a.voter?.full_name ?? "Office user"}
            </span>
          ))}
        </div>
      )}
      {userId && nonOverride.some(a => a.approved_by === userId) && (
        <p className="text-[11px] text-muted-foreground">You have already voted on this quote.</p>
      )}
    </div>
  );
}

function QuoteSectionPanel({
  mr,
  userId,
  isAdmin,
  onMrUpdated,
}: {
  mr: WorkshopMR;
  userId: string | undefined;
  isAdmin: boolean;
  onMrUpdated: (updated: WorkshopMR) => void;
}) {
  const [showUpload, setShowUpload] = useState(false);
  const [acting, setActing] = useState<string | null>(null);

  const handleVote = async (q: WorkshopQuote) => {
    setActing(q.id);
    try {
      await workshopApi.castQuoteVote(q.id);
      const updated = await workshopApi.getMR(mr.id);
      onMrUpdated(updated);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail ?? "Failed to cast vote.");
    } finally {
      setActing(null);
    }
  };

  const handleApprove = async (q: WorkshopQuote) => {
    if (!window.confirm(`Override and approve this quote from ${q.supplier?.name ?? q.supplier_name ?? "supplier"}?`)) return;
    setActing(q.id);
    try {
      await workshopApi.approveQuote(q.id);
      const updated = await workshopApi.getMR(mr.id);
      onMrUpdated(updated);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail ?? "Failed to approve quote.");
    } finally {
      setActing(null);
    }
  };

  const handleReject = async (q: WorkshopQuote) => {
    const reason = window.prompt("Reason for rejection (optional):");
    if (reason === null) return;
    setActing(q.id);
    try {
      await workshopApi.rejectQuote(q.id, reason || undefined);
      const updated = await workshopApi.getMR(mr.id);
      onMrUpdated(updated);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail ?? "Failed to reject quote.");
    } finally {
      setActing(null);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          Supplier Quotes {mr.quotes.length > 0 && `(${mr.quotes.length})`}
        </p>
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs px-3 gap-1.5"
          onClick={() => setShowUpload(true)}
        >
          <Plus className="w-3.5 h-3.5" />
          Upload Quote
        </Button>
      </div>

      {mr.quotes.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No quotes yet. Upload a quote received from a supplier.
        </p>
      ) : (
        <div className="space-y-2">
          {mr.quotes.map(q => {
            const supplierLabel = q.supplier?.name ?? q.supplier_name ?? "Unknown supplier";
            const hasVoted = userId ? q.approvals.some(a => a.approved_by === userId) : false;
            return (
              <div key={q.id} className="border border-border rounded-xl p-3 space-y-2 bg-muted/20">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{supplierLabel}</p>
                    {q.total_amount != null && (
                      <p className="text-xs text-muted-foreground">
                        {q.currency} {q.total_amount.toLocaleString("en-ZA", { minimumFractionDigits: 2 })}
                      </p>
                    )}
                  </div>
                  <span className={cn(
                    "shrink-0 text-xs px-2 py-0.5 rounded-full border font-medium",
                    QUOTE_STATUS_STYLE[q.status] ?? "bg-muted text-muted-foreground border-border"
                  )}>
                    {q.status}
                  </span>
                </div>

                {q.quote_file_url && (
                  <a
                    href={q.quote_file_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                  >
                    <ClipboardList className="w-3.5 h-3.5" />
                    View Quote Document
                  </a>
                )}

                {q.notes && <p className="text-xs text-muted-foreground italic">{q.notes}</p>}

                {q.rejection_reason && (
                  <p className="text-xs text-destructive bg-destructive/10 rounded px-2 py-1">
                    Rejected: {q.rejection_reason}
                  </p>
                )}

                {q.status === "PENDING" && (
                  <>
                    <QuoteVoteProgress quote={q} userId={userId} />
                    <div className="flex gap-2 pt-1">
                      <Button
                        size="sm"
                        className="flex-1 h-7 text-xs"
                        disabled={acting === q.id || hasVoted}
                        onClick={() => handleVote(q)}
                      >
                        <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                        {acting === q.id ? "Voting…" : hasVoted ? "Already Voted" : "Approve Vote"}
                      </Button>
                      {isAdmin && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs text-primary border-primary hover:bg-primary/10"
                          disabled={acting === q.id}
                          onClick={() => handleApprove(q)}
                        >
                          Override
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs border-destructive text-destructive hover:bg-destructive/10"
                        disabled={acting === q.id}
                        onClick={() => handleReject(q)}
                      >
                        Reject
                      </Button>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      {showUpload && (
        <UploadQuoteModal
          mr={mr}
          onClose={() => setShowUpload(false)}
          onUploaded={updated => {
            onMrUpdated(updated);
            setShowUpload(false);
          }}
        />
      )}
    </div>
  );
}

function MRRequestsTab() {
  const { user, role } = useAuth();
  const [mrs,       setMrs]       = useState<WorkshopMR[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState("");
  const [filter,    setFilter]    = useState<WorkshopMRStatus | "ALL">("ALL");
  const [expanded,  setExpanded]  = useState<string | null>(null);
  const [acting,    setActing]    = useState<string | null>(null);
  const [sending,   setSending]   = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<WorkshopMR | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    workshopApi.listMRs()
      .then(data => setMrs(data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())))
      .catch(() => setError("Failed to load workshop requests."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const displayed = filter === "ALL" ? mrs : mrs.filter(m => m.status === filter);

  const handleVote = async (mr: WorkshopMR) => {
    setActing(mr.id);
    try {
      const updated = await workshopApi.castVote(mr.id);
      setMrs(prev => prev.map(m => m.id === updated.id ? updated : m));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail ?? "Failed to cast vote.");
    } finally {
      setActing(null);
    }
  };

  const handleSend = async (mr: WorkshopMR, forceResend: boolean) => {
    setSending(mr.id);
    try {
      const logs = await workshopApi.sendToSuppliers(mr.id, forceResend);
      setMrs(prev => prev.map(m => m.id === mr.id ? { ...m, email_logs: logs } : m));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail ?? "Failed to send emails.");
    } finally {
      setSending(null);
    }
  };

  const handleAdminApprove = async (mr: WorkshopMR) => {
    if (!window.confirm(`Override the 3-vote requirement and approve ${mr.mr_number} directly?`)) return;
    setActing(mr.id);
    try {
      const updated = await workshopApi.approveMR(mr.id);
      setMrs(prev => prev.map(m => m.id === updated.id ? updated : m));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail ?? "Failed to approve MR.");
    } finally {
      setActing(null);
    }
  };

  const pending = mrs.filter(m => m.status === "SUBMITTED").length;
  const isAdmin = role === "OWNER" || role === "OFFICE_ADMIN";

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3">
        {(["ALL", "SUBMITTED", "APPROVED", "REJECTED"] as const).map(s => {
          const count = s === "ALL" ? mrs.length : mrs.filter(m => m.status === s).length;
          return (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={cn(
                "rounded-xl border p-3 text-left transition-colors",
                filter === s ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted/40"
              )}
            >
              <p className="text-xs text-muted-foreground">{s === "ALL" ? "All MRs" : MR_STATUS_LABEL[s]}</p>
              <p className={cn("text-2xl font-bold mt-0.5",
                s === "SUBMITTED" && count > 0 ? "text-amber-600" : ""
              )}>{count}</p>
            </button>
          );
        })}
      </div>

      {pending > 0 && (
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span><strong>{pending}</strong> workshop request{pending !== 1 ? "s" : ""} awaiting approval ({VOTES_REQUIRED} votes required).</span>
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{displayed.length} request{displayed.length !== 1 ? "s" : ""}</p>
        <button onClick={load} disabled={loading} className="p-2 rounded-lg hover:bg-muted text-muted-foreground disabled:opacity-50">
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <div className="py-12 text-center text-muted-foreground text-sm">Loading…</div>
      ) : displayed.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground text-sm border border-border rounded-2xl">
          No workshop requests{filter !== "ALL" ? ` with status "${MR_STATUS_LABEL[filter]}"` : ""}.
        </div>
      ) : (
        <div className="bg-card border border-border rounded-2xl overflow-hidden divide-y divide-border">
          {displayed.map(mr => {
            const isOpen = expanded === mr.id;
            const nonOverrideVotes = mr.approvals.filter(a => !a.is_override);
            const hasVoted = user ? nonOverrideVotes.some(a => a.approved_by === user.id) : false;

            return (
              <div key={mr.id}>
                <button
                  className="w-full flex items-center gap-3 px-5 py-4 hover:bg-muted/30 text-left transition-colors"
                  onClick={() => setExpanded(isOpen ? null : mr.id)}
                >
                  <div className="shrink-0">
                    {mr.status === "APPROVED"  ? <CheckCircle2 className="w-5 h-5 text-green-500" /> :
                     mr.status === "SUBMITTED" ? <Clock        className="w-5 h-5 text-amber-500" /> :
                     mr.status === "REJECTED"  ? <Ban          className="w-5 h-5 text-red-500"   /> :
                                                 <Wrench       className="w-5 h-5 text-muted-foreground" />}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm">{mr.mr_number}</span>
                      <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium", MR_STATUS_BADGE[mr.status])}>
                        {MR_STATUS_LABEL[mr.status]}
                      </span>
                      {mr.status === "SUBMITTED" && (
                        <span className={cn(
                          "text-xs px-2 py-0.5 rounded-full border font-medium",
                          nonOverrideVotes.length >= VOTES_REQUIRED
                            ? "bg-green-100 text-green-700 border-green-200"
                            : "bg-amber-100 text-amber-700 border-amber-200"
                        )}>
                          {nonOverrideVotes.length}/{VOTES_REQUIRED} votes
                        </span>
                      )}
                      {mr.priority !== "NORMAL" && (
                        <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium", PRIORITY_BADGE[mr.priority])}>
                          {mr.priority}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-0.5 truncate">{mr.reason}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {mr.vehicle?.registration ?? "—"} {mr.vehicle?.name ? `· ${mr.vehicle.name}` : ""}
                      {mr.site?.name ? ` · ${mr.site.name}` : ""}
                      {" · "}{mr.lines.length} part{mr.lines.length !== 1 ? "s" : ""}
                      {" · "}{shortDate(mr.created_at)}
                    </p>
                  </div>

                  <ChevronRight className={cn("w-4 h-4 text-muted-foreground shrink-0 transition-transform", isOpen && "rotate-90")} />
                </button>

                {isOpen && (
                  <div className="px-5 pb-5 pt-3 bg-muted/20 border-t border-border/50 space-y-4">
                    {/* Vehicle + site */}
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <p className="text-xs text-muted-foreground mb-0.5">Vehicle</p>
                        <p className="font-medium">{mr.vehicle?.registration ?? mr.vehicle_id.slice(0, 8)}</p>
                        {mr.vehicle?.name && <p className="text-xs text-muted-foreground">{mr.vehicle.name}</p>}
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-0.5">Site</p>
                        <p className="font-medium">{mr.site?.name ?? mr.site_id.slice(0, 8)}</p>
                        {mr.site?.site_type && <p className="text-xs text-muted-foreground capitalize">{mr.site.site_type.replace(/_/g, " ")}</p>}
                      </div>
                    </div>

                    {/* Parts table */}
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Parts Requested</p>
                      <div className="border border-border rounded-xl overflow-hidden divide-y divide-border">
                        <div className="grid grid-cols-[1fr_auto] gap-2 px-3 py-2 bg-muted/50 text-xs font-medium text-muted-foreground">
                          <span>Part</span><span className="text-right">Qty</span>
                        </div>
                        {mr.lines.map((line, i) => (
                          <div key={line.id ?? i} className="grid grid-cols-[1fr_auto] gap-2 px-3 py-2.5 bg-card items-start">
                            <div>
                              <p className="text-sm font-medium">{line.item?.name ?? "Unknown"}</p>
                              {line.item?.part_number && <p className="text-xs text-muted-foreground">#{line.item.part_number}</p>}
                              {line.remarks && <p className="text-xs text-muted-foreground italic">{line.remarks}</p>}
                            </div>
                            <p className="text-sm font-semibold tabular-nums text-right shrink-0">
                              {line.quantity_requested} {line.item?.unit ?? ""}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Notes / dates */}
                    {(mr.notes || mr.needed_by_date) && (
                      <div className="text-sm space-y-1">
                        {mr.needed_by_date && (
                          <p className="text-muted-foreground">Needed by: <span className="font-medium text-foreground">{shortDate(mr.needed_by_date)}</span></p>
                        )}
                        {mr.notes && <p className="text-muted-foreground italic">{mr.notes}</p>}
                      </div>
                    )}

                    {/* Rejection reason */}
                    {mr.rejection_reason && (
                      <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                        Rejected: {mr.rejection_reason}
                      </p>
                    )}

                    {/* Approval info + email panel + quotes */}
                    {mr.status === "APPROVED" && (
                      <div className="space-y-4">
                        <p className="text-sm text-green-700 bg-green-50 rounded-lg px-3 py-2 flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4" />
                          Approved {mr.approved_at ? shortDate(mr.approved_at) : ""}
                        </p>
                        <EmailStatusPanel
                          logs={mr.email_logs}
                          sending={sending === mr.id}
                          onSend={forceResend => handleSend(mr, forceResend)}
                        />
                        <div className="border-t border-border pt-3">
                          <QuoteSectionPanel
                            mr={mr}
                            userId={user?.id}
                            isAdmin={isAdmin}
                            onMrUpdated={updated => setMrs(prev => prev.map(m => m.id === updated.id ? updated : m))}
                          />
                        </div>
                      </div>
                    )}

                    {/* Vote progress */}
                    {mr.status === "SUBMITTED" && (
                      <VoteProgress mr={mr} userId={user?.id} />
                    )}

                    {/* Actions */}
                    {mr.status === "SUBMITTED" && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        <Button
                          className="flex-1"
                          disabled={acting === mr.id || hasVoted}
                          onClick={() => handleVote(mr)}
                          title={hasVoted ? "You have already voted" : ""}
                        >
                          <CheckCircle2 className="w-4 h-4 mr-1.5" />
                          {acting === mr.id ? "Voting…" : hasVoted ? "Already Voted" : "Cast Vote"}
                        </Button>
                        {isAdmin && (
                          <Button
                            variant="outline"
                            className="text-primary border-primary hover:bg-primary/10"
                            disabled={acting === mr.id}
                            onClick={() => handleAdminApprove(mr)}
                            title="Override — approve without 3 votes"
                          >
                            Override Approve
                          </Button>
                        )}
                        <Button
                          variant="outline"
                          className="flex-1 border-destructive text-destructive hover:bg-destructive/10"
                          disabled={acting === mr.id}
                          onClick={() => setRejectTarget(mr)}
                        >
                          Reject
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {rejectTarget && (
        <RejectModal
          mr={rejectTarget}
          onClose={() => setRejectTarget(null)}
          onRejected={updated => {
            setMrs(prev => prev.map(m => m.id === updated.id ? updated : m));
            setRejectTarget(null);
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 2 — Parts Catalog
// ─────────────────────────────────────────────────────────────────────────────

function StockAdjustModal({ item, onClose, onAdjusted }: {
  item: WorkshopItem; onClose: () => void; onAdjusted: (newQty: number) => void;
}) {
  const [delta,   setDelta]   = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const submit = async () => {
    const d = parseFloat(delta);
    if (isNaN(d) || d === 0) { setError("Enter a non-zero quantity."); return; }
    setLoading(true);
    setError("");
    try {
      const result = await workshopApi.adjustStock(item.id, d);
      onAdjusted(result.quantity_on_hand);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Adjustment failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={`Adjust Stock — ${item.name}`} onClose={onClose}>
      <div className="space-y-3">
        <div className="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3">
          <p className="text-xs text-muted-foreground">Current stock</p>
          <p className="text-2xl font-bold">{item.quantity_on_hand} <span className="text-sm font-normal text-muted-foreground">{item.unit}</span></p>
          {item.reorder_level != null && item.quantity_on_hand <= item.reorder_level && (
            <p className="text-xs text-amber-600 mt-0.5 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> Below reorder level ({item.reorder_level})
            </p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label>Quantity to add or remove</Label>
          <p className="text-xs text-muted-foreground">Enter a positive number to add stock, negative to remove.</p>
          <div className="flex gap-2">
            <button type="button" onClick={() => setDelta(d => String(Math.abs(parseFloat(d) || 0)))}
              className="px-3 py-2 rounded-lg border border-border bg-green-50 text-green-700 text-sm font-medium hover:bg-green-100">
              <TrendingUp className="w-4 h-4" />
            </button>
            <Input
              type="number"
              step="any"
              placeholder="e.g. 10 or -3"
              value={delta}
              onChange={e => setDelta(e.target.value)}
              className="flex-1"
              autoFocus
            />
            <button type="button" onClick={() => setDelta(d => String(-Math.abs(parseFloat(d) || 0)))}
              className="px-3 py-2 rounded-lg border border-border bg-red-50 text-red-700 text-sm font-medium hover:bg-red-100">
              <TrendingDown className="w-4 h-4" />
            </button>
          </div>
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>
            {loading ? "Saving…" : "Apply Adjustment"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function AddItemModal({
  categories,
  editItem,
  onClose,
  onSaved,
}: {
  categories: WorkshopCategory[];
  editItem: WorkshopItem | null;
  onClose: () => void;
  onSaved: (item: WorkshopItem) => void;
}) {
  const [form, setForm] = useState<WorkshopItemCreate>({
    category_id: editItem?.category_id ?? (categories[0]?.id ?? ""),
    name: editItem?.name ?? "",
    part_number: editItem?.part_number ?? "",
    unit: editItem?.unit ?? "each",
    description: editItem?.description ?? "",
    reorder_level: editItem?.reorder_level ?? null,
  });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const patch = (p: Partial<WorkshopItemCreate>) => setForm(prev => ({ ...prev, ...p }));

  const submit = async () => {
    if (!form.name.trim()) { setError("Name is required."); return; }
    if (!form.category_id) { setError("Select a category."); return; }
    setLoading(true);
    setError("");
    try {
      let saved: WorkshopItem;
      if (editItem) {
        const body: WorkshopItemUpdate = {
          name:         form.name.trim(),
          part_number:  form.part_number || null,
          unit:         form.unit,
          description:  form.description || null,
          reorder_level: form.reorder_level,
        };
        saved = await workshopApi.updateItem(editItem.id, body);
      } else {
        saved = await workshopApi.createItem({ ...form, name: form.name.trim() });
      }
      onSaved(saved);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to save item.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={editItem ? `Edit — ${editItem.name}` : "Add Part"} onClose={onClose}>
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label>Category *</Label>
          <select
            value={form.category_id}
            onChange={e => patch({ category_id: e.target.value })}
            disabled={!!editItem}
            className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-60"
          >
            <option value="">— Select —</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>Part name *</Label>
          <Input value={form.name} onChange={e => patch({ name: e.target.value })} placeholder="e.g. 235/65 R17 Tyre" autoFocus />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Part number</Label>
            <Input value={form.part_number ?? ""} onChange={e => patch({ part_number: e.target.value })} placeholder="OEM / supplier ref" />
          </div>
          <div className="space-y-1.5">
            <Label>Unit</Label>
            <Input value={form.unit} onChange={e => patch({ unit: e.target.value })} placeholder="each, litre, kg…" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label>Reorder level</Label>
          <Input
            type="number" min="0" step="any"
            value={form.reorder_level ?? ""}
            onChange={e => patch({ reorder_level: e.target.value ? parseFloat(e.target.value) : null })}
            placeholder="Alert when stock falls below…"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Description (optional)</Label>
          <textarea
            rows={2}
            value={form.description ?? ""}
            onChange={e => patch({ description: e.target.value })}
            placeholder="Specifications, notes…"
            className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>
            {loading ? "Saving…" : editItem ? "Save Changes" : "Add Part"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function AddCategoryModal({ onClose, onSaved }: {
  onClose: () => void; onSaved: (cat: WorkshopCategory) => void;
}) {
  const [form, setForm] = useState<WorkshopCategoryCreate>({ name: "", description: "" });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const submit = async () => {
    if (!form.name.trim()) { setError("Name is required."); return; }
    setLoading(true);
    setError("");
    try {
      const cat = await workshopApi.createCategory({ name: form.name.trim(), description: form.description || null });
      onSaved(cat);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to create category.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="New Category" onClose={onClose}>
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label>Category name *</Label>
          <Input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Tyres, Engine Oil, Filters" autoFocus />
        </div>
        <div className="space-y-1.5">
          <Label>Description</Label>
          <Input value={form.description ?? ""} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} placeholder="Optional" />
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>{loading ? "Saving…" : "Add Category"}</Button>
        </div>
      </div>
    </Modal>
  );
}

function PartsTab() {
  const [items,      setItems]      = useState<WorkshopItem[]>([]);
  const [categories, setCategories] = useState<WorkshopCategory[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [catFilter,  setCatFilter]  = useState("");
  const [activeOnly, setActiveOnly] = useState(true);

  const [adjustTarget, setAdjustTarget] = useState<WorkshopItem | null>(null);
  const [editTarget,   setEditTarget]   = useState<WorkshopItem | null>(null);
  const [showAddItem,  setShowAddItem]  = useState(false);
  const [showAddCat,   setShowAddCat]   = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      workshopApi.listItems(catFilter || undefined),
      workshopApi.listCategories(),
    ]).then(([items, cats]) => {
      setItems(items);
      setCategories(cats);
    }).finally(() => setLoading(false));
  }, [catFilter]);

  useEffect(() => { load(); }, [load]);

  const displayed = activeOnly ? items.filter(i => i.is_active) : items;

  const totalValue = displayed.reduce((s, i) => s + i.quantity_on_hand, 0);
  const lowStock   = displayed.filter(i => i.reorder_level != null && i.quantity_on_hand <= i.reorder_level);

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-card border border-border rounded-xl p-3">
          <p className="text-xs text-muted-foreground">Total Parts</p>
          <p className="text-2xl font-bold mt-0.5">{displayed.length}</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-3">
          <p className="text-xs text-muted-foreground">Categories</p>
          <p className="text-2xl font-bold mt-0.5">{categories.length}</p>
        </div>
        <div className={cn("border rounded-xl p-3", lowStock.length > 0 ? "bg-amber-50 border-amber-200" : "bg-card border-border")}>
          <p className="text-xs text-muted-foreground">Low Stock</p>
          <p className={cn("text-2xl font-bold mt-0.5", lowStock.length > 0 ? "text-amber-600" : "")}>{lowStock.length}</p>
        </div>
      </div>

      {/* Filters + actions */}
      <div className="flex flex-wrap gap-2 items-center justify-between">
        <div className="flex gap-2">
          <select
            value={catFilter}
            onChange={e => setCatFilter(e.target.value)}
            className="h-9 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none"
          >
            <option value="">All categories</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={e => setActiveOnly(e.target.checked)}
              className="rounded"
            />
            Active only
          </label>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowAddCat(true)}>
            <Plus className="w-3.5 h-3.5 mr-1" />Category
          </Button>
          <Button size="sm" onClick={() => setShowAddItem(true)}>
            <Plus className="w-3.5 h-3.5 mr-1" />Add Part
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="py-12 text-center text-muted-foreground text-sm">Loading…</div>
      ) : displayed.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground text-sm border border-border rounded-2xl">
          No parts in catalog. Add a category first, then add parts.
        </div>
      ) : (
        <div className="bg-card border border-border rounded-2xl overflow-hidden">
          <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-2 px-5 py-3 bg-muted/50 text-xs font-medium text-muted-foreground border-b border-border">
            <span>Part</span>
            <span className="text-right">Stock</span>
            <span className="text-right">Reorder</span>
            <span />
            <span />
          </div>
          <div className="divide-y divide-border">
            {displayed.map(item => {
              const isLow = item.reorder_level != null && item.quantity_on_hand <= item.reorder_level;
              const catName = item.category_name ?? categories.find(c => c.id === item.category_id)?.name;
              return (
                <div key={item.id} className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-2 px-5 py-3 items-center">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium truncate">{item.name}</p>
                      {!item.is_active && <Badge variant="outline" className="text-xs shrink-0">Inactive</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {catName && <span>{catName} · </span>}
                      {item.part_number && <span>#{item.part_number} · </span>}
                      {item.unit}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className={cn("text-sm font-semibold tabular-nums", isLow ? "text-amber-600" : item.quantity_on_hand === 0 ? "text-destructive" : "text-green-600")}>
                      {item.quantity_on_hand}
                    </p>
                    {isLow && <AlertTriangle className="w-3 h-3 text-amber-500 ml-auto" />}
                  </div>
                  <p className="text-xs text-muted-foreground text-right">
                    {item.reorder_level ?? "—"}
                  </p>
                  <button
                    onClick={() => setAdjustTarget(item)}
                    className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    title="Adjust stock"
                  >
                    <Package className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setEditTarget(item)}
                    className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                    title="Edit item"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {adjustTarget && (
        <StockAdjustModal
          item={adjustTarget}
          onClose={() => setAdjustTarget(null)}
          onAdjusted={newQty => {
            setItems(prev => prev.map(i => i.id === adjustTarget.id ? { ...i, quantity_on_hand: newQty } : i));
            setAdjustTarget(null);
          }}
        />
      )}

      {(showAddItem || editTarget) && (
        <AddItemModal
          categories={categories}
          editItem={editTarget}
          onClose={() => { setShowAddItem(false); setEditTarget(null); }}
          onSaved={saved => {
            setItems(prev => {
              const idx = prev.findIndex(i => i.id === saved.id);
              if (idx >= 0) { const n = [...prev]; n[idx] = saved; return n; }
              return [saved, ...prev];
            });
            setShowAddItem(false);
            setEditTarget(null);
          }}
        />
      )}

      {showAddCat && (
        <AddCategoryModal
          onClose={() => setShowAddCat(false)}
          onSaved={cat => { setCategories(prev => [...prev, cat]); setShowAddCat(false); }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 3 — Supplier Links
// ─────────────────────────────────────────────────────────────────────────────

function AddSupplierLinkModal({ categories, suppliers, onClose, onSaved }: {
  categories: WorkshopCategory[];
  suppliers: Supplier[];
  onClose: () => void;
  onSaved: (link: WorkshopSupplierLink) => void;
}) {
  const [catId,     setCatId]     = useState(categories[0]?.id ?? "");
  const [suppId,    setSuppId]    = useState("");
  const [preferred, setPreferred] = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState("");

  const submit = async () => {
    if (!catId || !suppId) { setError("Select both category and supplier."); return; }
    setLoading(true);
    setError("");
    try {
      const link = await workshopApi.createSupplierLink({ category_id: catId, supplier_id: suppId, is_preferred: preferred });
      onSaved(link);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to create link.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="Link Supplier to Category" onClose={onClose}>
      <div className="space-y-3">
        <div className="space-y-1.5">
          <Label>Parts category *</Label>
          <select value={catId} onChange={e => setCatId(e.target.value)}
            className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary">
            <option value="">— Select —</option>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>Supplier *</Label>
          <select value={suppId} onChange={e => setSuppId(e.target.value)}
            className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary">
            <option value="">— Select —</option>
            {suppliers.filter(s => s.is_active).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={preferred} onChange={e => setPreferred(e.target.checked)} className="rounded" />
          Mark as preferred supplier for this category
        </label>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>{loading ? "Saving…" : "Link Supplier"}</Button>
        </div>
      </div>
    </Modal>
  );
}

function SuppliersTab() {
  const [links,      setLinks]      = useState<WorkshopSupplierLink[]>([]);
  const [categories, setCategories] = useState<WorkshopCategory[]>([]);
  const [suppliers,  setSuppliers]  = useState<Supplier[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [showAdd,    setShowAdd]    = useState(false);
  const [deleting,   setDeleting]   = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      workshopApi.listSupplierLinks(),
      workshopApi.listCategories(),
      suppliersApi.list(),
    ]).then(([l, c, s]) => {
      setLinks(l);
      setCategories(c);
      setSuppliers(s);
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (linkId: string) => {
    setDeleting(linkId);
    try {
      await workshopApi.deleteSupplierLink(linkId);
      setLinks(prev => prev.filter(l => l.id !== linkId));
    } catch {
      alert("Failed to remove supplier link.");
    } finally {
      setDeleting(null);
    }
  };

  // Group by category
  const grouped = categories.map(cat => ({
    cat,
    links: links.filter(l => l.category_id === cat.id),
  })).filter(g => g.links.length > 0);

  const orphans = links.filter(l => !categories.some(c => c.id === l.category_id));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{links.length} supplier link{links.length !== 1 ? "s" : ""} across {grouped.length} categor{grouped.length !== 1 ? "ies" : "y"}</p>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="w-3.5 h-3.5 mr-1" /> Link Supplier
        </Button>
      </div>

      {loading ? (
        <div className="py-12 text-center text-muted-foreground text-sm">Loading…</div>
      ) : links.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground text-sm border border-border rounded-2xl">
          No supplier links yet. Link suppliers to parts categories so site staff can select them on MRs.
        </div>
      ) : (
        <div className="space-y-3">
          {grouped.map(({ cat, links: catLinks }) => (
            <div key={cat.id} className="bg-card border border-border rounded-2xl overflow-hidden">
              <div className="px-4 py-3 bg-muted/40 border-b border-border">
                <p className="font-semibold text-sm">{cat.name}</p>
                {cat.description && <p className="text-xs text-muted-foreground mt-0.5">{cat.description}</p>}
              </div>
              <div className="divide-y divide-border">
                {catLinks.map(link => {
                  const suppName = link.supplier?.name ?? suppliers.find(s => s.id === link.supplier_id)?.name ?? link.supplier_id.slice(0, 8);
                  const suppEmail = link.supplier?.email ?? suppliers.find(s => s.id === link.supplier_id)?.email;
                  return (
                    <div key={link.id} className="flex items-center gap-3 px-4 py-3">
                      <Building2 className="w-4 h-4 text-muted-foreground shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">{suppName}</p>
                        {suppEmail && <p className="text-xs text-muted-foreground">{suppEmail}</p>}
                      </div>
                      {link.is_preferred && (
                        <Badge variant="outline" className="text-xs border-green-200 text-green-700 bg-green-50">Preferred</Badge>
                      )}
                      <button
                        onClick={() => handleDelete(link.id)}
                        disabled={deleting === link.id}
                        className="p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
                        title="Remove link"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

          {orphans.length > 0 && (
            <div className="bg-card border border-dashed border-border rounded-2xl p-4">
              <p className="text-xs text-muted-foreground mb-2">Links with no matching category (stale):</p>
              {orphans.map(l => (
                <div key={l.id} className="flex items-center justify-between py-1">
                  <p className="text-sm">{l.supplier?.name ?? l.supplier_id.slice(0, 8)}</p>
                  <button onClick={() => handleDelete(l.id)} disabled={deleting === l.id}
                    className="p-1.5 text-muted-foreground hover:text-destructive">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {showAdd && (
        <AddSupplierLinkModal
          categories={categories}
          suppliers={suppliers}
          onClose={() => setShowAdd(false)}
          onSaved={link => { setLinks(prev => [...prev, link]); setShowAdd(false); }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB 3 — Issuances
// ─────────────────────────────────────────────────────────────────────────────

function IssuePartsModal({ items, vehicles, mrs, onClose, onIssued }: {
  items: WorkshopItem[];
  vehicles: Vehicle[];
  mrs: WorkshopMR[];
  onClose: () => void;
  onIssued: (r: WorkshopIssuance) => void;
}) {
  const [form, setForm] = useState<WorkshopIssuanceCreate>({
    item_id: "",
    vehicle_id: "",
    workshop_mr_id: null,
    quantity_issued: 1,
    notes: "",
  });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const patch = (p: Partial<WorkshopIssuanceCreate>) => setForm(f => ({ ...f, ...p }));

  const selectedItem = items.find(i => i.id === form.item_id);
  const overStock = selectedItem != null && form.quantity_issued > selectedItem.quantity_on_hand;

  const submit = async () => {
    if (!form.item_id)    { setError("Select a part."); return; }
    if (!form.vehicle_id) { setError("Select a vehicle."); return; }
    if (form.quantity_issued <= 0) { setError("Quantity must be greater than zero."); return; }
    setLoading(true);
    setError("");
    try {
      const result = await workshopApi.issueParts({
        item_id: form.item_id,
        vehicle_id: form.vehicle_id,
        workshop_mr_id: form.workshop_mr_id || null,
        quantity_issued: form.quantity_issued,
        notes: form.notes || null,
      });
      onIssued(result);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to issue parts.");
    } finally {
      setLoading(false);
    }
  };

  const approvedMrs = mrs.filter(m => m.status === "APPROVED");

  return (
    <Modal title="Issue Parts" onClose={onClose} wide>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>Part *</Label>
          <select
            value={form.item_id}
            onChange={e => patch({ item_id: e.target.value })}
            className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">— Select part —</option>
            {items.map(i => (
              <option key={i.id} value={i.id}>
                {i.name}{i.part_number ? ` (#${i.part_number})` : ""} — {i.quantity_on_hand} {i.unit} in stock
              </option>
            ))}
          </select>
          {selectedItem && (
            <p className={cn("text-xs mt-1", selectedItem.quantity_on_hand === 0 ? "text-destructive" : "text-muted-foreground")}>
              Current stock: <strong>{selectedItem.quantity_on_hand} {selectedItem.unit}</strong>
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label>Vehicle *</Label>
          <select
            value={form.vehicle_id}
            onChange={e => patch({ vehicle_id: e.target.value })}
            className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">— Select vehicle —</option>
            {vehicles.map(v => (
              <option key={v.id} value={v.id}>{v.registration} — {v.name}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <Label>Quantity *</Label>
          <Input
            type="number" min="0.001" step="any"
            value={form.quantity_issued}
            onChange={e => patch({ quantity_issued: parseFloat(e.target.value) || 0 })}
          />
          {overStock && (
            <p className="text-xs text-amber-600 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> Exceeds current stock ({selectedItem?.quantity_on_hand ?? 0} {selectedItem?.unit})
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <Label>Link to approved MR (optional)</Label>
          <select
            value={form.workshop_mr_id ?? ""}
            onChange={e => patch({ workshop_mr_id: e.target.value || null })}
            className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">— None —</option>
            {approvedMrs.map(m => (
              <option key={m.id} value={m.id}>
                {m.mr_number} · {m.vehicle?.registration ?? "?"} · {m.reason.slice(0, 40)}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <Label>Notes (optional)</Label>
          <textarea
            rows={2}
            value={form.notes ?? ""}
            onChange={e => patch({ notes: e.target.value })}
            placeholder="Any additional notes…"
            className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button className="flex-1" onClick={submit} disabled={loading}>
            <Send className="w-4 h-4 mr-1.5" />{loading ? "Issuing…" : "Issue Parts"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function IssuancesTab() {
  const [issuances, setIssuances] = useState<WorkshopIssuance[]>([]);
  const [items,     setItems]     = useState<WorkshopItem[]>([]);
  const [vehicles,  setVehicles]  = useState<Vehicle[]>([]);
  const [mrs,       setMrs]       = useState<WorkshopMR[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState("");

  const [vehicleFilter, setVehicleFilter] = useState("");
  const [itemFilter,    setItemFilter]    = useState("");
  const [showIssue,     setShowIssue]     = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    Promise.all([
      workshopApi.listIssuances(),
      workshopApi.listItems(),
      vehiclesApi.list(),
      workshopApi.listMRs(),
    ]).then(([iss, its, vehs, ms]) => {
      setIssuances(iss.sort((a, b) => new Date(b.issued_at).getTime() - new Date(a.issued_at).getTime()));
      setItems(its);
      setVehicles(vehs);
      setMrs(ms);
    }).catch(() => setError("Failed to load issuances."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const displayed = issuances.filter(i => {
    if (vehicleFilter && i.vehicle_id !== vehicleFilter) return false;
    if (itemFilter    && i.item_id    !== itemFilter)    return false;
    return true;
  });

  const uniqueVehicles = new Set(issuances.map(i => i.vehicle_id)).size;
  const uniqueItems    = new Set(issuances.map(i => i.item_id)).size;
  const totalQty       = issuances.reduce((s, i) => s + i.quantity_issued, 0);

  const linkedMrNumber = (mrId: string | null) => {
    if (!mrId) return null;
    return mrs.find(m => m.id === mrId)?.mr_number ?? mrId.slice(0, 8);
  };

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-card border border-border rounded-xl p-3">
          <p className="text-xs text-muted-foreground">Total Issuances</p>
          <p className="text-2xl font-bold mt-0.5">{issuances.length}</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-3">
          <p className="text-xs text-muted-foreground">Vehicles Served</p>
          <p className="text-2xl font-bold mt-0.5">{uniqueVehicles}</p>
        </div>
        <div className="bg-card border border-border rounded-xl p-3">
          <p className="text-xs text-muted-foreground">Total Qty Issued</p>
          <p className="text-2xl font-bold mt-0.5">{totalQty % 1 === 0 ? totalQty : totalQty.toFixed(2)}</p>
          <p className="text-xs text-muted-foreground">{uniqueItems} part type{uniqueItems !== 1 ? "s" : ""}</p>
        </div>
      </div>

      {/* Filters + action */}
      <div className="flex flex-wrap gap-2 items-center justify-between">
        <div className="flex gap-2">
          <select
            value={vehicleFilter}
            onChange={e => setVehicleFilter(e.target.value)}
            className="h-9 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none"
          >
            <option value="">All vehicles</option>
            {vehicles.map(v => <option key={v.id} value={v.id}>{v.registration} — {v.name}</option>)}
          </select>
          <select
            value={itemFilter}
            onChange={e => setItemFilter(e.target.value)}
            className="h-9 px-3 text-sm rounded-lg border border-border bg-card focus:outline-none"
          >
            <option value="">All parts</option>
            {items.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
        </div>
        <Button size="sm" onClick={() => setShowIssue(true)}>
          <Send className="w-3.5 h-3.5 mr-1" /> Issue Parts
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <div className="py-12 text-center text-muted-foreground text-sm">Loading…</div>
      ) : displayed.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground text-sm border border-border rounded-2xl">
          {issuances.length === 0
            ? "No parts have been issued yet. Use \"Issue Parts\" to record an issuance."
            : "No issuances match the current filters."}
        </div>
      ) : (
        <div className="bg-card border border-border rounded-2xl overflow-hidden">
          <div className="grid grid-cols-[auto_1fr_1fr_auto_auto_auto] gap-3 px-5 py-3 bg-muted/50 text-xs font-medium text-muted-foreground border-b border-border">
            <span>Date</span>
            <span>Part</span>
            <span>Vehicle</span>
            <span className="text-right">Qty</span>
            <span>MR</span>
            <span>Notes</span>
          </div>
          <div className="divide-y divide-border">
            {displayed.map(iss => {
              const mrNum = linkedMrNumber(iss.workshop_mr_id);
              return (
                <div key={iss.id} className="grid grid-cols-[auto_1fr_1fr_auto_auto_auto] gap-3 px-5 py-3 items-center">
                  <p className="text-xs text-muted-foreground whitespace-nowrap">{shortDate(iss.issued_at)}</p>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">
                      {iss.item?.name ?? items.find(i => i.id === iss.item_id)?.name ?? iss.item_id.slice(0, 8)}
                    </p>
                    {iss.item?.part_number && (
                      <p className="text-xs text-muted-foreground">#{iss.item.part_number}</p>
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">
                      {iss.vehicle?.registration ?? vehicles.find(v => v.id === iss.vehicle_id)?.registration ?? "—"}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {iss.vehicle?.name ?? vehicles.find(v => v.id === iss.vehicle_id)?.name ?? ""}
                    </p>
                  </div>
                  <p className="text-sm font-semibold tabular-nums text-right">
                    {iss.quantity_issued % 1 === 0 ? iss.quantity_issued : iss.quantity_issued.toFixed(2)}
                    {" "}<span className="text-xs font-normal text-muted-foreground">{iss.item?.unit ?? ""}</span>
                  </p>
                  {mrNum ? (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 whitespace-nowrap">{mrNum}</span>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                  <p className="text-xs text-muted-foreground truncate max-w-[120px]" title={iss.notes ?? ""}>
                    {iss.notes || "—"}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {showIssue && (
        <IssuePartsModal
          items={items}
          vehicles={vehicles}
          mrs={mrs}
          onClose={() => setShowIssue(false)}
          onIssued={r => {
            setIssuances(prev => [r, ...prev]);
            setShowIssue(false);
            // Refresh item stock levels
            workshopApi.listItems().then(setItems);
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

type Tab = "requests" | "parts" | "issuances" | "suppliers";

const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: "requests",  label: "Requests",  icon: ClipboardList },
  { key: "parts",     label: "Parts",     icon: Package      },
  { key: "issuances", label: "Issuances", icon: History      },
  { key: "suppliers", label: "Suppliers", icon: Building2    },
];

export default function WorkshopPage() {
  const [tab, setTab] = useState<Tab>("requests");

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
          <Wrench className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Workshop</h1>
          <p className="text-sm text-muted-foreground">Vehicle spare parts management</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px",
              tab === t.key
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "requests"  && <MRRequestsTab />}
      {tab === "parts"     && <PartsTab />}
      {tab === "issuances" && <IssuancesTab />}
      {tab === "suppliers" && <SuppliersTab />}
    </div>
  );
}
