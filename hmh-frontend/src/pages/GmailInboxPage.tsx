import { useState, useEffect, useCallback } from "react";
import {
  Mail, RefreshCw, FileText, Truck, MessageSquare, HelpCircle,
  CheckCircle2, Clock, AlertTriangle, ChevronRight, Download,
  Zap, XCircle, Minus, Eye, RotateCcw,
} from "lucide-react";
import {
  gmailApi,
  type IncomingEmail, type IncomingEmailAttachment, type DetectedType,
  type ProcessedAttachment, type MatchStatus,
} from "@/api/gmail";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// ── Static maps ───────────────────────────────────────────────────────────────

const TYPE_ICON: Record<DetectedType, React.ElementType> = {
  INVOICE: FileText, DELIVERY_NOTE: Truck, QUOTE: MessageSquare, OTHER: HelpCircle,
};
const TYPE_COLOR: Record<DetectedType, string> = {
  INVOICE:       "text-blue-600 bg-blue-50 border-blue-200",
  DELIVERY_NOTE: "text-green-600 bg-green-50 border-green-200",
  QUOTE:         "text-purple-600 bg-purple-50 border-purple-200",
  OTHER:         "text-gray-500 bg-gray-50 border-gray-200",
};
const TYPE_LABEL: Record<DetectedType, string> = {
  INVOICE: "Invoice", DELIVERY_NOTE: "Delivery Note", QUOTE: "Quote", OTHER: "Other",
};
const STATUS_ICON: Record<string, React.ElementType> = {
  PROCESSED: CheckCircle2, UNPROCESSED: Clock, IGNORED: AlertTriangle,
  PROCESSING_FAILED: XCircle,
};
const STATUS_COLOR: Record<string, string> = {
  PROCESSED:          "text-green-600",
  UNPROCESSED:        "text-amber-600",
  IGNORED:            "text-gray-400",
  PROCESSING_FAILED:  "text-destructive",
};

const MATCH_CONFIG: Record<MatchStatus | string, { label: string; cls: string; icon: React.ElementType }> = {
  MATCHED:      { label: "Matched",         cls: "bg-green-100 text-green-700 border-green-200",   icon: CheckCircle2 },
  MISMATCH:     { label: "Mismatch",        cls: "bg-red-100 text-red-700 border-red-200",          icon: AlertTriangle },
  NOT_FOUND:    { label: "MR not found",    cls: "bg-amber-100 text-amber-700 border-amber-200",    icon: AlertTriangle },
  NO_REFERENCE: { label: "No MR reference", cls: "bg-gray-100 text-gray-600 border-gray-200",       icon: Minus },
};

function shortDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

// ── Extraction result panel ───────────────────────────────────────────────────

function ExtractionResult({ result }: { result: ProcessedAttachment }) {
  const match = result.mr_match;
  const mc    = MATCH_CONFIG[match.status] ?? MATCH_CONFIG["NO_REFERENCE"];
  const MatchIcon = mc.icon;
  const f = result.fields;

  return (
    <div className="border border-border rounded-xl overflow-hidden text-xs">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 bg-muted/40 border-b border-border">
        <div className="flex items-center gap-1.5">
          {(() => { const I = TYPE_ICON[result.detected_type] ?? HelpCircle; return <I className="w-3.5 h-3.5 shrink-0" />; })()}
          <span className="font-semibold truncate max-w-[180px]">{result.filename}</span>
        </div>
        <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border", TYPE_COLOR[result.detected_type])}>
          {TYPE_LABEL[result.detected_type]}
        </span>
      </div>

      {/* Extraction status */}
      {result.extraction_status !== "EXTRACTED" && (
        <div className="px-3 py-2 bg-amber-50 border-b border-border text-amber-700">
          Status: <strong>{result.extraction_status.replace("_", " ")}</strong>
          {result.warnings.length > 0 && (
            <span className="ml-1 text-muted-foreground">— {result.warnings[0]}</span>
          )}
        </div>
      )}

      {/* Extracted fields */}
      {(f.invoice_number || f.delivery_note_number || f.supplier_name || f.total_amount != null || f.date) && (
        <div className="px-3 py-2.5 space-y-1 border-b border-border">
          {f.invoice_number      && <FieldRow label="Invoice #"    value={f.invoice_number} />}
          {f.delivery_note_number && <FieldRow label="DN #"         value={f.delivery_note_number} />}
          {f.supplier_name        && <FieldRow label="Supplier"     value={f.supplier_name} />}
          {f.date                 && <FieldRow label="Date"         value={f.date} />}
          {f.total_amount != null && (
            <FieldRow label="Total" value={`R${Number(f.total_amount).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}`} bold />
          )}
        </div>
      )}

      {/* Line items */}
      {result.items.length > 0 && (
        <div className="px-3 py-2.5 border-b border-border space-y-1">
          <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide mb-1">Items</p>
          {result.items.slice(0, 3).map((item, i) => (
            <div key={i} className="flex items-center justify-between gap-2">
              <span className="truncate text-foreground">{item.description}</span>
              <span className="text-muted-foreground shrink-0 tabular-nums">
                {item.quantity != null ? `${item.quantity} ${item.unit ?? ""}` : ""}
              </span>
            </div>
          ))}
          {result.items.length > 3 && (
            <p className="text-muted-foreground">+{result.items.length - 3} more items</p>
          )}
        </div>
      )}

      {/* MR match */}
      <div className="px-3 py-2.5">
        <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wide mb-1.5">MR Match</p>
        <div className={cn("flex items-center gap-2 px-2.5 py-2 rounded-lg border font-medium", mc.cls)}>
          <MatchIcon className="w-3.5 h-3.5 shrink-0" />
          <span>{mc.label}</span>
          {match.mr_number && <span className="ml-auto font-mono">{match.mr_number}</span>}
        </div>
        {match.mismatch_detail && (
          <p className="mt-1 text-destructive">{match.mismatch_detail}</p>
        )}
        {match.mr_status && (
          <p className="mt-0.5 text-muted-foreground">MR status: {match.mr_status}</p>
        )}
      </div>
    </div>
  );
}

function FieldRow({ label, value, bold = false }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={cn("truncate text-right", bold && "font-semibold text-foreground")}>{value}</span>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function GmailInboxPage() {
  const [emails,     setEmails]     = useState<IncomingEmail[]>([]);
  const [total,      setTotal]      = useState(0);
  const [loading,    setLoading]    = useState(false);
  const [fetching,   setFetching]   = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error,      setError]      = useState("");
  const [notice,     setNotice]     = useState("");
  const [selected,   setSelected]   = useState<IncomingEmail | null>(null);
  const [filter,     setFilter]     = useState<string>("");
  const [extraction, setExtraction] = useState<ProcessedAttachment[] | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const res = await gmailApi.listIncoming({ limit: 60 });
      setEmails(res.items); setTotal(res.total);
    } catch { setError("Failed to load emails."); }
    finally   { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleFetch = async () => {
    setFetching(true); setNotice("");
    try {
      const res = await gmailApi.fetch(20);
      setNotice(res.mock
        ? "IMAP is in mock mode. Set IMAP_ENABLED=true in .env to fetch real emails."
        : `Fetched ${res.fetched} email(s), saved ${res.saved} new.`
      );
      await load();
    } catch { setError("Fetch failed."); }
    finally   { setFetching(false); }
  };

  const handleSelect = async (e: IncomingEmail) => {
    setExtraction(null);
    try { setSelected(await gmailApi.getIncoming(e.id)); }
    catch { setSelected(e); }
  };

  const [refetchingId, setRefetchingId] = useState<string | null>(null);

  /** Open or download an attachment via the authenticated API (preserves auth headers). */
  const handleOpenAttachment = async (attId: string, inline: boolean) => {
    try {
      const { blob, filename } = await gmailApi.getAttachmentBlob(attId, inline);
      const url = URL.createObjectURL(blob);
      if (inline) {
        window.open(url, "_blank", "noopener,noreferrer");
        setTimeout(() => URL.revokeObjectURL(url), 30_000);
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Attachment file is missing. Use Re-fetch to restore it from Gmail.");
    }
  };

  /** Re-fetch a missing attachment from Gmail IMAP. */
  const handleRefetchAttachment = async (att: IncomingEmailAttachment) => {
    setRefetchingId(att.id);
    setError("");
    try {
      await gmailApi.refetchAttachment(att.id);
      // Reload the selected email so file_exists updates
      if (selected) setSelected(await gmailApi.getIncoming(selected.id));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Re-fetch failed. Check that IMAP is enabled and credentials are correct.");
    } finally {
      setRefetchingId(null);
    }
  };

  const handleProcess = async () => {
    if (!selected) return;
    setProcessing(true); setError(""); setExtraction(null);
    try {
      const res = await gmailApi.processEmail(selected.id);
      setExtraction(res.results);
      // Refresh the selected email to get updated status
      const updated = await gmailApi.getIncoming(selected.id);
      setSelected(updated);
      setEmails(prev => prev.map(e => e.id === updated.id ? { ...e, processed_status: updated.processed_status } : e));
    } catch {
      setError("Processing failed. Check backend logs.");
    } finally {
      setProcessing(false);
    }
  };

  const filtered = filter
    ? emails.filter(e => filter === "UNPROCESSED"
        ? e.processed_status === "UNPROCESSED"
        : filter === "PROCESSED"
        ? e.processed_status === "PROCESSED"
        : true)
    : emails;

  const attTypeSummary = (email: IncomingEmail) => {
    if (!email.has_attachments) return null;
    const atts = (email as IncomingEmail & { attachments?: { detected_type: DetectedType }[] }).attachments;
    if (!atts) return "Has attachments";
    return [...new Set(atts.map(a => TYPE_LABEL[a.detected_type]))].join(", ");
  };

  const selAtts = (selected as IncomingEmail & {
    attachments?: { id: string; filename: string; detected_type: DetectedType; content_type: string | null }[]
  })?.attachments;
  const canProcess = selected?.processed_status === "UNPROCESSED" && selected?.has_attachments;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Mail className="w-5 h-5 text-primary" />Procurement Inbox
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Incoming emails from suppliers — invoices, delivery notes, quotes
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={cn("w-4 h-4 mr-1.5", loading && "animate-spin")} />Refresh
          </Button>
          <Button size="sm" onClick={handleFetch} disabled={fetching}>
            <Download className={cn("w-4 h-4 mr-1.5", fetching && "animate-spin")} />
            {fetching ? "Fetching…" : "Fetch New Emails"}
          </Button>
        </div>
      </div>

      {notice && <div className="text-sm bg-primary/10 border border-primary/20 text-primary rounded-lg px-3 py-2">{notice}</div>}
      {error  && <div className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</div>}

      {/* Filter tabs */}
      <div className="flex gap-1 border-b border-border pb-2">
        {["", "UNPROCESSED", "PROCESSED"].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={cn("px-3 py-1 text-sm rounded-md font-medium transition-colors",
              filter === f ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground")}>
            {f === "" ? `All (${total})` : f === "UNPROCESSED" ? "Unprocessed" : "Processed"}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        {/* Email list */}
        <div className="space-y-2">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
              <RefreshCw className="w-4 h-4 animate-spin" />Loading…
            </div>
          )}
          {!loading && filtered.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              <Mail className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">No emails yet.</p>
              <p className="text-xs mt-1">Click "Fetch New Emails" to check the Gmail inbox.</p>
            </div>
          )}
          {filtered.map(email => {
            const SIcon = STATUS_ICON[email.processed_status] ?? Clock;
            return (
              <button key={email.id} onClick={() => handleSelect(email)}
                className={cn("w-full text-left p-3 rounded-xl border transition-colors",
                  selected?.id === email.id ? "border-primary/50 bg-primary/5" : "border-border bg-card hover:bg-muted/50")}>
                <div className="flex items-start gap-2">
                  <SIcon className={cn("w-4 h-4 mt-0.5 shrink-0", STATUS_COLOR[email.processed_status])} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium truncate">{email.from_email}</p>
                      <span className="text-xs text-muted-foreground shrink-0">{shortDate(email.received_at)}</span>
                    </div>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">{email.subject || "(no subject)"}</p>
                    {email.has_attachments && (
                      <div className="flex items-center gap-1 mt-1">
                        <FileText className="w-3 h-3 text-muted-foreground" />
                        <span className="text-xs text-muted-foreground">{attTypeSummary(email) ?? "Attachments"}</span>
                      </div>
                    )}
                    {email.matched_po_number && (
                      <span className="inline-block mt-1 text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded font-medium">
                        {email.matched_po_number}
                      </span>
                    )}
                  </div>
                  <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                </div>
              </button>
            );
          })}
        </div>

        {/* Detail panel */}
        {selected ? (
          <div className="bg-card border border-border rounded-xl p-4 space-y-4">
            {/* Email header */}
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-sm">{selected.from_email}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{selected.subject}</p>
                <p className="text-xs text-muted-foreground">{shortDate(selected.received_at)}</p>
              </div>
              <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium",
                selected.processed_status === "PROCESSED"
                  ? "bg-green-100 text-green-700 border-green-200"
                  : selected.processed_status === "PROCESSING_FAILED"
                  ? "bg-red-100 text-red-700 border-red-200"
                  : "bg-amber-100 text-amber-700 border-amber-200"
              )}>
                {selected.processed_status.replace("_", " ")}
              </span>
            </div>

            {/* ── Process Email button ── */}
            {canProcess && (
              <Button
                className="w-full"
                onClick={handleProcess}
                disabled={processing}
              >
                <Zap className={cn("w-4 h-4 mr-2", processing && "animate-pulse")} />
                {processing ? "Processing…" : "Process Email"}
              </Button>
            )}
            {selected.processed_status !== "UNPROCESSED" && !extraction && (
              <Button variant="outline" className="w-full" size="sm" onClick={handleProcess} disabled={processing}>
                <RefreshCw className={cn("w-3.5 h-3.5 mr-1.5", processing && "animate-spin")} />
                {processing ? "Re-processing…" : "Re-process"}
              </Button>
            )}

            {selected.matched_po_number && (
              <div className="text-xs bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-blue-700">
                Auto-matched: <strong>{selected.matched_po_number}</strong>
              </div>
            )}

            {selected.body_snippet && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-1">Preview</p>
                <p className="text-xs text-foreground bg-muted/40 rounded-lg p-3 whitespace-pre-wrap line-clamp-4">
                  {selected.body_snippet}
                </p>
              </div>
            )}

            {/* Attachments list */}
            {selAtts?.length ? (
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-2">Attachments</p>
                <div className="space-y-1.5">
                  {selAtts.map(att => {
                    const Icon = TYPE_ICON[att.detected_type] ?? HelpCircle;
                    const missing = att.file_exists === false;
                    const refetching = refetchingId === att.id;
                    return (
                      <div key={att.id}
                        className={cn("flex items-center gap-2 p-2 rounded-lg border text-xs",
                          missing ? "border-amber-400/40 bg-amber-500/5" : TYPE_COLOR[att.detected_type])}>
                        <Icon className="w-4 h-4 shrink-0" />
                        <span className="flex-1 truncate font-medium">{att.filename}</span>
                        {missing ? (
                          <span className="shrink-0 text-amber-600 font-semibold mr-1">⚠ Missing</span>
                        ) : (
                          <span className="shrink-0 font-semibold mr-1">{TYPE_LABEL[att.detected_type]}</span>
                        )}
                        {missing ? (
                          /* Re-fetch button — restores file from Gmail IMAP */
                          <button
                            onClick={() => handleRefetchAttachment(att)}
                            disabled={refetching}
                            className="flex items-center gap-1 px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-700 shrink-0"
                            title="Re-fetch attachment file from Gmail"
                          >
                            {refetching
                              ? <RefreshCw className="w-3 h-3 animate-spin" />
                              : <RotateCcw className="w-3 h-3" />}
                            {refetching ? "Re-fetching…" : "Re-fetch"}
                          </button>
                        ) : (
                          <>
                            <button
                              onClick={() => handleOpenAttachment(att.id, true)}
                              className="p-1 rounded hover:bg-black/10 shrink-0"
                              title="View in browser"
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleOpenAttachment(att.id, false)}
                              className="p-1 rounded hover:bg-black/10 shrink-0"
                              title="Download file"
                            >
                              <Download className="w-3.5 h-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : selected.has_attachments ? (
              <p className="text-xs text-muted-foreground">Has attachments (load detail to view)</p>
            ) : (
              <p className="text-xs text-muted-foreground">No attachments</p>
            )}

            {/* ── Extraction results ── */}
            {extraction && extraction.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Extraction Results
                </p>
                {extraction.map(r => (
                  <ExtractionResult key={r.attachment_id} result={r} />
                ))}
              </div>
            )}
            {extraction && extraction.length === 0 && (
              <p className="text-xs text-muted-foreground">No attachments were processed.</p>
            )}
          </div>
        ) : (
          <div className="hidden lg:flex items-center justify-center h-48 bg-muted/20 border border-dashed border-border rounded-xl text-muted-foreground">
            <div className="text-center">
              <Mail className="w-6 h-6 mx-auto mb-1 opacity-40" />
              <p className="text-sm">Select an email to view details</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
