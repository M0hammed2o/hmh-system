/**
 * Document detail drawer.
 *
 * The original scan on the left, what the system read on the right, so a
 * reviewer can check one against the other without switching windows.
 * Values can be corrected in place; every correction is recorded with its
 * previous value before it is applied.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle, CheckCircle2, ExternalLink, FileText, Link2, Loader2,
  RefreshCw, Save, ShieldAlert, X, XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ConfidenceDot, DocumentStatusBadge, MatchStatusBadge, OutcomeBadge,
} from "@/components/aiImport/AIImportBadges";
import { ManualLinkPanel } from "@/components/aiImport/ManualLinkPanel";
import {
  aiImportApi,
  DOCUMENT_TYPE_LABELS,
  fieldLabel,
  IN_FLIGHT_STATUSES,
  type DocumentType,
  type ImportDocumentDetail,
  type DocumentPipeline,
} from "@/api/aiImport";
import type { Project } from "@/api/projects";
import type { Supplier } from "@/api/suppliers";

const POLL_MS = 4000;

const DESTINATIONS = [
  { value: "SITE_STORE", label: "Project warehouse (received on site)" },
  { value: "MAIN_WAREHOUSE", label: "Project warehouse (via main warehouse)" },
  { value: "PICKUP", label: "Collected" },
];

const fmtValue = (v: unknown): string => {
  if (v === null || v === undefined || v === "") return "";
  return String(v);
};

// ── Field row ─────────────────────────────────────────────────────────────────

function FieldRow({
  name,
  value,
  page,
  confidence,
  corrected,
  draft,
  onDraft,
  disabled,
}: {
  name: string;
  value: unknown;
  page: number | null;
  confidence: number;
  corrected: boolean;
  draft: string | undefined;
  onDraft: (value: string) => void;
  disabled: boolean;
}) {
  const current = draft !== undefined ? draft : fmtValue(value);
  const dirty = draft !== undefined && draft !== fmtValue(value);
  const unresolved = fmtValue(value) === "" && !dirty;

  return (
    <div className="grid grid-cols-[minmax(0,9rem)_1fr] gap-3 items-start py-2 border-b border-border last:border-0">
      <div className="pt-1.5">
        <p className="text-xs font-medium">{fieldLabel(name)}</p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <ConfidenceDot confidence={confidence} corrected={corrected} />
          {page !== null && <span className="text-xs text-muted-foreground">p.{page}</span>}
        </div>
      </div>
      <div>
        <input
          value={current}
          disabled={disabled}
          placeholder={unresolved ? "Not found on the document" : ""}
          onChange={(e) => onDraft(e.target.value)}
          className={`w-full h-8 px-2 rounded-md border bg-background text-sm ${
            dirty ? "border-primary ring-1 ring-primary/30"
              : unresolved ? "border-dashed border-amber-400"
              : "border-border"
          }`}
        />
      </div>
    </div>
  );
}

// ── Detail drawer ─────────────────────────────────────────────────────────────


/**
 * What has actually happened to this document, in plain words.
 *
 * Posting a delivery note writes a goods receipt into the PROJECT
 * WAREHOUSE. Putting those materials against a BOQ lot is a separate,
 * deliberate step — nobody should guess which lot consumed which bag of
 * cement. Until this banner existed, a correctly posted delivery that was
 * simply awaiting allocation looked like a lost one.
 */
function PipelineBanner({ pipeline }: { pipeline: DocumentPipeline }) {
  const awaiting = pipeline.stage === "IN_PROJECT_WAREHOUSE"
    || pipeline.stage === "PARTIALLY_ALLOCATED";
  const bad = pipeline.stage === "FAILED" || pipeline.stage === "REJECTED";
  const done = pipeline.stage === "ALLOCATED_TO_LOT";

  return (
    <div
      className={
        "mt-2 rounded-lg border px-3 py-2 text-sm " +
        (bad
          ? "border-destructive/30 bg-destructive/5 text-destructive"
          : awaiting
            ? "border-amber-500/30 bg-amber-500/5"
            : done
              ? "border-emerald-500/30 bg-emerald-500/5"
              : "border-border bg-muted/40")
      }
    >
      <p className="font-medium">{pipeline.label}</p>
      <p className="text-muted-foreground">{pipeline.detail}</p>

      {pipeline.receiving.received_qty > 0 && (
        <p className="text-xs text-muted-foreground mt-1 tabular-nums">
          received {pipeline.receiving.received_qty.toLocaleString()}
          {" · "}allocated to a lot {pipeline.receiving.allocated_qty.toLocaleString()}
          {" · "}still in the warehouse {pipeline.receiving.awaiting_allocation_qty.toLocaleString()}
        </p>
      )}

      {pipeline.next_action && (
        <p className="mt-1.5 flex items-center gap-1.5">
          <span className="text-muted-foreground">Next:</span>
          <span>{pipeline.next_action}</span>
          {awaiting && (
            // The existing warehouse workflow, with its allocation and
            // overrun safeguards — not a second path around them.
            <a href="/project-warehouse" className="text-primary hover:underline">
              Open Project Warehouse
            </a>
          )}
        </p>
      )}
    </div>
  );
}

export function AIDocumentImportDetail({
  documentId,
  projects,
  suppliers,
  onClose,
  onChanged,
}: {
  documentId: string;
  projects: Project[];
  suppliers: Supplier[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const [doc, setDoc] = useState<ImportDocumentDetail | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [destination, setDestination] = useState("SITE_STORE");
  const [authNote, setAuthNote] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const fileUrlFor = useRef<string | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const data = await aiImportApi.getDocument(documentId);
      setDoc(data);
      setError(null);
    } catch {
      setError("This document could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => { void load(); }, [load]);

  // The signed URL is short-lived, so fetch it once per document on open.
  useEffect(() => {
    if (!doc || fileUrlFor.current === doc.id) return;
    fileUrlFor.current = doc.id;
    aiImportApi.getFileUrl(doc.id)
      .then((r) => setFileUrl(r.url))
      .catch(() => setFileUrl(null));
  }, [doc]);

  // Follow progress while the backend is still working on it.
  useEffect(() => {
    if (!doc || !IN_FLIGHT_STATUSES.includes(doc.status)) return;
    const timer = setInterval(() => void load(true), POLL_MS);
    return () => clearInterval(timer);
  }, [doc, load]);

  const run = async (action: () => Promise<unknown>, message?: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      await load(true);
      onChanged();
      if (message) setNotice(message);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      if (typeof detail === "string") {
        setError(detail);
      } else if (detail && typeof detail === "object" && "message" in detail) {
        setError(String((detail as { message: string }).message));
      } else {
        setError("That action could not be completed.");
      }
    } finally {
      setBusy(false);
    }
  };

  const saveCorrections = () => {
    if (!doc?.extraction) return;
    const changes = Object.entries(drafts)
      .filter(([path, value]) => {
        const original = fmtValue(doc.extraction?.fields[path]?.value);
        return value !== original;
      })
      .map(([path, value]) => ({
        field_path: path,
        value: value === "" ? null : value,
      }));
    if (!changes.length) return;
    void run(
      () => aiImportApi.correct(doc.id, changes).then(() => setDrafts({})),
      `${changes.length} correction(s) saved.`,
    );
  };

  const dirtyCount = doc?.extraction
    ? Object.entries(drafts).filter(
        ([p, v]) => v !== fmtValue(doc.extraction?.fields[p]?.value),
      ).length
    : 0;

  const blocking = doc?.outcome_reasons.filter((r) => r.severity === "BLOCKED") ?? [];
  const reviewItems = doc?.outcome_reasons.filter((r) => r.severity === "NEEDS_REVIEW") ?? [];
  const isReceipt = doc?.document_type === "DELIVERY_NOTE" || doc?.document_type === "GOODS_RECEIVED_NOTE";
  const terminal = doc ? ["POSTED", "REJECTED", "DUPLICATE"].includes(doc.status) : false;

  return (
    <div className="fixed inset-0 z-50 bg-foreground/40 flex justify-end">
      <div className="bg-background w-full max-w-6xl h-full overflow-y-auto shadow-xl">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-background border-b border-border px-5 py-3 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
              <h3 className="font-semibold truncate">{doc?.file_name ?? "Document"}</h3>
              {doc && <DocumentStatusBadge status={doc.status} />}
              {doc?.pipeline && <PipelineBanner pipeline={doc.pipeline} />}
              {doc && <OutcomeBadge outcome={doc.processing_outcome} />}
              {doc?.is_legacy && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">
                  historical
                </span>
              )}
            </div>
            {doc && (
              <p className="text-xs text-muted-foreground mt-0.5">
                {DOCUMENT_TYPE_LABELS[doc.document_type]} · {doc.batch_reference}
                {doc.extraction && ` · read by ${doc.extraction.provider} (${doc.extraction.extraction_mode})`}
              </p>
            )}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-md hover:bg-muted shrink-0" aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading ? (
          <div className="p-5 space-y-3">
            <Skeleton className="h-64 w-full rounded-xl" />
            <Skeleton className="h-40 w-full rounded-xl" />
          </div>
        ) : !doc ? (
          <div className="p-5 text-sm text-destructive">{error ?? "Not found."}</div>
        ) : (
          <div className="p-5 space-y-5">
            {error && (
              <div className="bg-destructive/10 border border-destructive/30 text-destructive rounded-lg px-4 py-3 text-sm">
                {error}
              </div>
            )}
            {notice && (
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-300 text-green-800 dark:text-green-300 rounded-lg px-4 py-3 text-sm">
                {notice}
              </div>
            )}

            {/* What needs doing */}
            {(blocking.length > 0 || reviewItems.length > 0) && (
              <div className="space-y-2">
                {blocking.length > 0 && (
                  <div className="bg-destructive/10 border border-destructive/30 rounded-xl p-4">
                    <p className="font-medium text-sm flex items-center gap-2 text-destructive">
                      <XCircle className="w-4 h-4" />
                      This document cannot be posted
                    </p>
                    <ul className="mt-2 space-y-1 text-sm text-destructive/90">
                      {blocking.map((r, i) => <li key={i}>• {r.message}</li>)}
                    </ul>
                  </div>
                )}
                {reviewItems.length > 0 && (
                  <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-300 rounded-xl p-4">
                    <p className="font-medium text-sm flex items-center gap-2 text-amber-900 dark:text-amber-200">
                      <AlertTriangle className="w-4 h-4" />
                      Check these before posting
                    </p>
                    <ul className="mt-2 space-y-1 text-sm text-amber-800 dark:text-amber-300">
                      {reviewItems.map((r, i) => <li key={i}>• {r.message}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {doc.failure_reason && (
              <div className="bg-destructive/10 border border-destructive/30 rounded-xl p-4 text-sm">
                <p className="font-medium text-destructive">Processing problem</p>
                <p className="mt-1 text-destructive/90">{doc.failure_reason}</p>
                {doc.job?.last_error && (
                  <p className="mt-1 text-xs font-mono text-destructive/70">{doc.job.last_error}</p>
                )}
              </div>
            )}

            {/* Side by side */}
            <div className="grid gap-5 lg:grid-cols-2">
              {/* Original */}
              <div className="bg-card border border-border rounded-xl overflow-hidden flex flex-col">
                <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
                  <span className="text-sm font-medium">Original document</span>
                  {fileUrl && (
                    <a
                      href={fileUrl} target="_blank" rel="noreferrer"
                      className="text-xs text-primary inline-flex items-center gap-1 hover:underline"
                    >
                      Open full size <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
                <div className="flex-1 min-h-[28rem] bg-muted/40">
                  {!fileUrl ? (
                    <div className="h-full flex items-center justify-center text-sm text-muted-foreground p-6 text-center">
                      The original could not be loaded from storage.
                    </div>
                  ) : doc.mime_type === "application/pdf" ? (
                    <iframe src={fileUrl} title={doc.file_name} className="w-full h-full min-h-[28rem]" />
                  ) : (
                    <img src={fileUrl} alt={doc.file_name} className="w-full h-auto" />
                  )}
                </div>
              </div>

              {/* Extracted */}
              <div className="bg-card border border-border rounded-xl">
                <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
                  <span className="text-sm font-medium">What the system read</span>
                  {doc.extraction && (
                    <span className="text-xs text-muted-foreground">
                      {Math.round(doc.extraction.overall_confidence * 100)}% overall
                    </span>
                  )}
                </div>

                {!doc.extraction ? (
                  <div className="p-6 text-sm text-muted-foreground text-center">
                    {IN_FLIGHT_STATUSES.includes(doc.status)
                      ? "Still reading this document…"
                      : "Nothing has been read from this document yet."}
                  </div>
                ) : (
                  <div className="p-4">
                    <div className="max-h-[22rem] overflow-y-auto pr-1">
                      {Object.entries(doc.extraction.fields).length === 0 ? (
                        <p className="text-sm text-muted-foreground">No fields were read.</p>
                      ) : (
                        Object.entries(doc.extraction.fields).map(([name, f]) => (
                          <FieldRow
                            key={name}
                            name={name}
                            value={f.value}
                            page={f.page}
                            confidence={f.confidence}
                            corrected={f.corrected}
                            draft={drafts[name]}
                            disabled={busy || terminal}
                            onDraft={(v) => setDrafts((d) => ({ ...d, [name]: v }))}
                          />
                        ))
                      )}
                    </div>

                    {dirtyCount > 0 && (
                      <div className="pt-3 mt-2 border-t border-border flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">
                          {dirtyCount} unsaved change(s)
                        </span>
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => setDrafts({})} disabled={busy}>
                            Discard
                          </Button>
                          <Button size="sm" onClick={saveCorrections} disabled={busy}>
                            <Save className="w-4 h-4 mr-1.5" /> Save corrections
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Arithmetic */}
            {doc.extraction && doc.extraction.arithmetic_checks.length > 0 && (
              <div className="bg-card border border-border rounded-xl p-4">
                <h4 className="text-sm font-semibold mb-2">Arithmetic check</h4>
                <p className="text-xs text-muted-foreground mb-3">
                  Recalculated here from the figures above, not taken from the document.
                </p>
                <div className="space-y-1.5">
                  {doc.extraction.arithmetic_checks.map((c, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      {c.passed
                        ? <CheckCircle2 className="w-4 h-4 text-green-600 mt-0.5 shrink-0" />
                        : <XCircle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />}
                      <span className={c.passed ? "text-muted-foreground" : "text-destructive"}>
                        {c.message ?? `${fieldLabel(c.name)} adds up.`}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Line items */}
            {doc.extraction && doc.extraction.line_items.length > 0 && (
              <div className="bg-card border border-border rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 border-b border-border text-sm font-medium">
                  Line items
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
                      <tr>
                        <th className="text-left px-4 py-2 font-medium">Description</th>
                        <th className="text-right px-4 py-2 font-medium">Qty</th>
                        <th className="text-left px-4 py-2 font-medium">Unit</th>
                        <th className="text-right px-4 py-2 font-medium">Price</th>
                        <th className="text-right px-4 py-2 font-medium">Total</th>
                        <th className="text-left px-4 py-2 font-medium">Catalogue item</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {doc.extraction.line_items.map((item, i) => {
                        const match = doc.line_item_matches.find((m) => m.index === i);
                        return (
                          <tr key={i}>
                            <td className="px-4 py-2">{item.description ?? "—"}</td>
                            <td className="px-4 py-2 text-right">{item.quantity ?? "—"}</td>
                            <td className="px-4 py-2">{item.unit ?? "—"}</td>
                            <td className="px-4 py-2 text-right">{item.unit_price ?? "—"}</td>
                            <td className="px-4 py-2 text-right">{item.line_total ?? "—"}</td>
                            <td className="px-4 py-2">
                              {match?.item_name ? (
                                <span className="text-xs">
                                  {match.item_name}
                                  {!match.unit_convertible && match.unit && (
                                    <span className="block text-amber-600">
                                      unit not comparable with {match.item_unit}
                                    </span>
                                  )}
                                </span>
                              ) : (
                                <span className="text-xs text-amber-600">not matched</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Matches */}
            <div className="bg-card border border-border rounded-xl p-4">
              <h4 className="text-sm font-semibold mb-3">What this document relates to</h4>
              {doc.matches.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nothing was matched yet. Set the project and supplier below to help.
                </p>
              ) : (
                <div className="space-y-2">
                  {doc.matches.map((m) => (
                    <div key={m.id} className="border border-border rounded-lg px-3 py-2.5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium flex items-center gap-2 flex-wrap">
                            <Link2 className="w-3.5 h-3.5 text-muted-foreground" />
                            {fieldLabel(m.target_type)}: {m.target_label ?? "—"}
                            <MatchStatusBadge status={m.status} />
                          </p>
                          {m.explanation && (
                            <p className="text-xs text-muted-foreground mt-1">{m.explanation}</p>
                          )}
                        </div>
                        {m.status === "PROPOSED" && !terminal && (
                          <div className="flex gap-1.5 shrink-0">
                            <Button
                              size="sm" variant="outline" disabled={busy}
                              onClick={() => void run(() => aiImportApi.decideMatch(doc.id, m.id, true), "Match confirmed.")}
                            >
                              Confirm
                            </Button>
                            <Button
                              size="sm" variant="outline" disabled={busy}
                              onClick={() => void run(() => aiImportApi.decideMatch(doc.id, m.id, false), "Match rejected.")}
                            >
                              Reject
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Manual linking — for when the engine found no order or request */}
            {!terminal && (
              <ManualLinkPanel
                doc={doc}
                suppliers={suppliers}
                disabled={busy}
                onLinked={(updated) => {
                  setDoc(updated);
                  onChanged();
                  setNotice("Record linked.");
                }}
              />
            )}

            {/* Context */}
            {!terminal && (
              <div className="bg-card border border-border rounded-xl p-4">
                <h4 className="text-sm font-semibold mb-3">Set the details by hand</h4>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Project</label>
                    <select
                      value={doc.project_id ?? ""}
                      disabled={busy}
                      onChange={(e) => void run(
                        () => aiImportApi.assignContext(doc.id, { project_id: e.target.value || null }),
                        "Project set.",
                      )}
                      className="w-full h-9 px-2 rounded-md border border-border bg-background text-sm"
                    >
                      <option value="">Not set</option>
                      {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Supplier</label>
                    <select
                      value={doc.supplier_id ?? ""}
                      disabled={busy}
                      onChange={(e) => void run(
                        () => aiImportApi.assignContext(doc.id, { supplier_id: e.target.value || null }),
                        "Supplier set.",
                      )}
                      className="w-full h-9 px-2 rounded-md border border-border bg-background text-sm"
                    >
                      <option value="">Not set</option>
                      {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground block mb-1">Document type</label>
                    <select
                      value={doc.document_type}
                      disabled={busy}
                      onChange={(e) => void run(
                        () => aiImportApi.assignContext(doc.id, { document_type: e.target.value as DocumentType }),
                        "Document type set.",
                      )}
                      className="w-full h-9 px-2 rounded-md border border-border bg-background text-sm"
                    >
                      {Object.entries(DOCUMENT_TYPE_LABELS).map(([v, label]) => (
                        <option key={v} value={v}>{label}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* Legacy authorisation */}
            {doc.is_legacy && !doc.authorised_by && !terminal && (
              <div className="bg-purple-50 dark:bg-purple-900/20 border border-purple-300 rounded-xl p-4">
                <p className="text-sm font-medium flex items-center gap-2 text-purple-900 dark:text-purple-200">
                  <ShieldAlert className="w-4 h-4" /> Historical document — authorisation needed
                </p>
                <p className="text-xs text-purple-800 dark:text-purple-300 mt-1">
                  This paperwork was created outside the system. Authorising it records that you
                  vouch for the paper trail. The record created from it will say so — it will not
                  be shown as having gone through the digital approvals.
                </p>
                <div className="flex gap-2 mt-3">
                  <input
                    value={authNote}
                    onChange={(e) => setAuthNote(e.target.value)}
                    placeholder="Where is the signed original kept?"
                    className="flex-1 h-9 px-3 rounded-md border border-border bg-background text-sm"
                  />
                  <Button
                    disabled={busy || authNote.trim().length < 3}
                    onClick={() => void run(
                      () => aiImportApi.authoriseLegacy(doc.id, authNote.trim()),
                      "Legacy import authorised.",
                    )}
                  >
                    Authorise
                  </Button>
                </div>
              </div>
            )}

            {/* Postings */}
            {doc.postings.length > 0 && (
              <div className="bg-card border border-border rounded-xl p-4">
                <h4 className="text-sm font-semibold mb-2">Records created</h4>
                <div className="space-y-1.5">
                  {doc.postings.map((p) => (
                    <div key={p.id} className="flex items-center gap-2 text-sm">
                      {p.complete
                        ? <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0" />
                        : <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />}
                      <span>
                        {fieldLabel(p.entity_type)}{" "}
                        <strong>{p.entity_label ?? "—"}</strong>
                        {!p.complete && " — attempt did not finish, verify in that module"}
                        {p.reversed_at && " (reversed)"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Related documents */}
            {doc.related_documents.length > 0 && (
              <div className="bg-card border border-border rounded-xl p-4">
                <h4 className="text-sm font-semibold mb-2">Related uploads</h4>
                <div className="space-y-1.5">
                  {doc.related_documents.slice(0, 8).map((r) => (
                    <div key={r.id} className="flex items-center gap-2 text-sm">
                      <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                      <span className="truncate">{r.file_name}</span>
                      <span className="text-xs text-muted-foreground">
                        {DOCUMENT_TYPE_LABELS[r.document_type]}
                        {r.shared_links.length > 0 && ` · shares ${r.shared_links.join(", ")}`}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Corrections log */}
            {doc.corrections.length > 0 && (
              <div className="bg-card border border-border rounded-xl p-4">
                <h4 className="text-sm font-semibold mb-2">Corrections made</h4>
                <div className="space-y-1 text-xs text-muted-foreground">
                  {doc.corrections.map((c, i) => (
                    <p key={i}>
                      <strong>{fieldLabel(c.field_path)}</strong>: “{c.before_value ?? "empty"}”
                      → “{c.after_value ?? "empty"}”
                      {c.reason && ` — ${c.reason}`}
                    </p>
                  ))}
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="sticky bottom-0 bg-background border-t border-border pt-4 pb-2 -mx-5 px-5">
              {isReceipt && !terminal && (
                <div className="mb-3">
                  <label className="text-xs text-muted-foreground block mb-1">
                    Where the goods were received
                  </label>
                  <select
                    value={destination}
                    onChange={(e) => setDestination(e.target.value)}
                    className="w-full sm:w-96 h-9 px-2 rounded-md border border-border bg-background text-sm"
                  >
                    {DESTINATIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                  </select>
                  <p className="text-xs text-muted-foreground mt-1">
                    Stock goes into this project's warehouse. Issue it to a lot afterwards
                    from the warehouse screen.
                  </p>
                </div>
              )}

              {showReject && (
                <div className="mb-3 flex gap-2">
                  <input
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Why is this document being rejected?"
                    className="flex-1 h-9 px-3 rounded-md border border-border bg-background text-sm"
                  />
                  <Button
                    variant="outline" disabled={busy || rejectReason.trim().length < 3}
                    onClick={() => void run(
                      () => aiImportApi.reject(doc.id, rejectReason.trim()),
                      "Document rejected.",
                    )}
                  >
                    Confirm rejection
                  </Button>
                  <Button variant="outline" onClick={() => setShowReject(false)}>Cancel</Button>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                {!terminal && (
                  <>
                    <Button
                      disabled={busy || blocking.length > 0}
                      onClick={() => void run(
                        () => aiImportApi.post(doc.id, {
                          destination: isReceipt ? destination : undefined,
                          confirm_override: doc.processing_outcome !== "AUTO_ELIGIBLE",
                        }),
                        "Posted.",
                      )}
                      title={blocking.length > 0 ? "Blocked items must be resolved first" : undefined}
                    >
                      {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
                      {doc.processing_outcome === "AUTO_ELIGIBLE"
                        ? "Post this document"
                        : "Post anyway (on my authority)"}
                    </Button>

                    <Button
                      variant="outline" disabled={busy}
                      onClick={() => void run(() => aiImportApi.retry(doc.id), "Queued for re-reading.")}
                    >
                      <RefreshCw className="w-4 h-4 mr-2" /> Read again
                    </Button>

                    <Button variant="outline" disabled={busy} onClick={() => setShowReject((v) => !v)}>
                      <XCircle className="w-4 h-4 mr-2" /> Reject
                    </Button>
                  </>
                )}

                {terminal && (
                  <p className="text-sm text-muted-foreground">
                    This document is {doc.status.toLowerCase().replace(/_/g, " ")} and can no
                    longer be changed.
                    {doc.rejection_reason && ` Reason: ${doc.rejection_reason}`}
                  </p>
                )}

                <div className="flex-1" />
                <Button variant="outline" onClick={onClose}>Close</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
