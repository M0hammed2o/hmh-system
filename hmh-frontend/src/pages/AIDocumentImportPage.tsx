/**
 * Bypass Orders — the user-facing name for AI Document Import.
 *
 * The route, API paths, services and database tables keep the ai_import
 * name. Only what staff read is renamed.
 *
 * Upload scanned or photographed procurement paperwork — material requests,
 * purchase orders, delivery notes, invoices — in any mix and any order. The
 * backend reads each one, works out what it is and what it relates to, and
 * puts it in front of a person to confirm before anything is posted.
 *
 * Three views: Upload, the document queue, and the reconciliation dashboard.
 * The detail drawer lives in AIDocumentImportDetail.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Camera, CheckCircle2, Clock, Copy, FileText, Filter,
  Inbox, Loader2, RefreshCw, ScanLine, Upload, XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/shared/Tabs";
import { AIDocumentImportDetail } from "@/components/aiImport/AIDocumentImportDetail";
import { BatchReviewPanel } from "@/components/aiImport/BatchReviewPanel";
import { DocumentStatusBadge, OutcomeBadge } from "@/components/aiImport/AIImportBadges";
import {
  aiImportApi,
  DOCUMENT_TYPE_LABELS,
  IN_FLIGHT_STATUSES,
  type DocumentFilters,
  type DocumentStatus,
  type DocumentType,
  type ImportBatch,
  type ImportDashboard,
  type ImportDocument,
  type ServiceStatus,
} from "@/api/aiImport";
import { projectsApi, type Project } from "@/api/projects";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { companiesApi, type Company } from "@/api/companies";

const POLL_MS = 4000;

const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-ZA", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  }) : "—";

const fmtBytes = (bytes: number) =>
  bytes > 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;

const fmtMoney = (n: number) =>
  `R ${n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// ── Upload panel ──────────────────────────────────────────────────────────────

function UploadPanel({
  projects,
  onUploaded,
}: {
  projects: Project[];
  onUploaded: (batch: ImportBatch) => void;
}) {
  const [projectId, setProjectId] = useState("");
  const [isLegacy, setIsLegacy] = useState(false);
  const [notes, setNotes] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    accepted: number; duplicates: number; rejected: { file_name: string; reason: string }[];
  } | null>(null);

  const fileInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((incoming: FileList | null) => {
    if (!incoming) return;
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const next = [...prev];
      Array.from(incoming).forEach((f) => {
        if (!seen.has(`${f.name}:${f.size}`)) next.push(f);
      });
      return next;
    });
    setResult(null);
    setError(null);
  }, []);

  const submit = async () => {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    setProgress(0);
    try {
      const batch = await aiImportApi.createBatch({
        project_id: projectId || null,
        is_legacy: isLegacy,
        notes: notes.trim() || null,
      });
      const uploaded = await aiImportApi.upload(batch.id, files, {
        isLegacy,
        onProgress: setProgress,
      });
      const duplicates = uploaded.accepted.filter((d) => d.status === "DUPLICATE").length;
      setResult({
        accepted: uploaded.accepted.length,
        duplicates,
        rejected: uploaded.rejected,
      });
      setFiles([]);
      onUploaded(uploaded.batch);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "The upload could not be completed.");
    } finally {
      setBusy(false);
      setProgress(0);
    }
  };

  return (
    <div className="max-w-3xl space-y-5">
      <div className="bg-card border border-border rounded-xl p-5 space-y-4">
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium block mb-1.5">Project (optional)</label>
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="w-full h-9 px-3 rounded-md border border-border bg-background text-sm"
            >
              <option value="">Let the system read it from each document</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground mt-1">
              Only used where a document does not name its own project.
            </p>
          </div>

          <div>
            <label className="text-sm font-medium block mb-1.5">Paperwork age</label>
            <label className="flex items-start gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={isLegacy}
                onChange={(e) => setIsLegacy(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                These are historical documents
                <span className="block text-xs text-muted-foreground">
                  Records created from them are marked as document-backed and need a
                  manager to authorise the import. They are never shown as having gone
                  through the digital approvals.
                </span>
              </span>
            </label>
          </div>
        </div>

        <div>
          <label className="text-sm font-medium block mb-1.5">Note (optional)</label>
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. 2024 Cornubia invoice file, box 3"
            className="w-full h-9 px-3 rounded-md border border-border bg-background text-sm"
          />
        </div>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
        className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
          dragging ? "border-primary bg-primary/5" : "border-border bg-card"
        }`}
      >
        <ScanLine className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
        <p className="font-medium">Drop documents here</p>
        <p className="text-sm text-muted-foreground mt-1">
          PDFs and photos. Mix invoices, delivery notes and orders in one go — you do not
          need to sort or label them.
        </p>
        <div className="flex items-center justify-center gap-2 mt-4">
          <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={busy}>
            <Upload className="w-4 h-4 mr-2" /> Choose files
          </Button>
          <Button variant="outline" onClick={() => cameraInput.current?.click()} disabled={busy}>
            <Camera className="w-4 h-4 mr-2" /> Take a photo
          </Button>
        </div>
        <input
          ref={fileInput} type="file" multiple hidden
          accept="application/pdf,image/jpeg,image/png,image/webp,image/heic,image/heif"
          onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
        />
        <input
          ref={cameraInput} type="file" multiple hidden accept="image/*" capture="environment"
          onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
        />
      </div>

      {files.length > 0 && (
        <div className="bg-card border border-border rounded-xl divide-y divide-border">
          <div className="px-4 py-2.5 flex items-center justify-between">
            <span className="text-sm font-medium">{files.length} file(s) ready</span>
            <button
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setFiles([])}
              disabled={busy}
            >
              Clear all
            </button>
          </div>
          {files.map((f, i) => (
            <div key={`${f.name}-${i}`} className="px-4 py-2.5 flex items-center gap-3 text-sm">
              <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
              <span className="flex-1 truncate">{f.name}</span>
              <span className="text-xs text-muted-foreground">{fmtBytes(f.size)}</span>
              <button
                className="text-muted-foreground hover:text-destructive"
                onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                disabled={busy}
                aria-label={`Remove ${f.name}`}
              >
                <XCircle className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="bg-destructive/10 border border-destructive/30 text-destructive rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {result && (() => {
        // A document only counts as received once its file is stored. When
        // nothing was stored there is nothing to read, and saying so plainly
        // matters more than a tidy banner: an earlier version showed a green
        // tick over "0 document(s) received" and promised background
        // processing, so a failed upload looked like a successful one.
        const nothingStored = result.accepted === 0;
        const someFailed = result.rejected.length > 0;

        return (
          <div
            className={cn(
              "border rounded-xl p-4 space-y-2 text-sm",
              nothingStored && someFailed
                ? "bg-destructive/5 border-destructive/30"
                : someFailed
                  ? "bg-amber-500/5 border-amber-500/30"
                  : "bg-card border-border",
            )}
          >
            {nothingStored && someFailed ? (
              <p className="flex items-center gap-2 font-medium text-destructive">
                <XCircle className="w-4 h-4" />
                Upload failed — nothing was stored, and nothing will be read.
              </p>
            ) : (
              <p className="flex items-center gap-2 font-medium">
                <CheckCircle2 className="w-4 h-4 text-green-600" />
                {result.accepted} document(s) received and queued for reading.
              </p>
            )}

            {result.duplicates > 0 && (
              <p className="text-muted-foreground flex items-center gap-2">
                <Copy className="w-4 h-4" />
                {result.duplicates} were already uploaded before and were not read again.
              </p>
            )}

            {result.rejected.map((r) => (
              <p key={r.file_name} className="text-destructive flex items-start gap-2">
                <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span><strong>{r.file_name}</strong> — {r.reason}</span>
              </p>
            ))}

            {nothingStored && someFailed ? (
              <p className="text-muted-foreground pt-1">
                Nothing reached the Documents tab, so these will not appear in stock
                or on a BOQ. Correct the problem above and upload again, or send this
                message to whoever administers the system.
              </p>
            ) : (
              <p className="text-muted-foreground pt-1">
                Reading happens in the background. Open the Documents tab to follow progress.
              </p>
            )}
          </div>
        );
      })()}

      <Button onClick={submit} disabled={busy || files.length === 0} className="w-full sm:w-auto">
        {busy ? (
          <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Uploading {progress}%</>
        ) : (
          <><Upload className="w-4 h-4 mr-2" /> Import {files.length || ""} document{files.length === 1 ? "" : "s"}</>
        )}
      </Button>
    </div>
  );
}

// ── Document queue ────────────────────────────────────────────────────────────

const STATUS_FILTERS: { value: DocumentStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "AWAITING_REVIEW", label: "Needs review" },
  { value: "AWAITING_AUTHORISATION", label: "Needs authorisation" },
  { value: "READY_TO_POST", label: "Ready to post" },
  { value: "POSTED", label: "Posted" },
  { value: "DUPLICATE", label: "Duplicates" },
  { value: "FAILED", label: "Failed" },
  { value: "REJECTED", label: "Rejected" },
];

function DocumentQueue({
  companies,
  projects,
  suppliers,
  onOpen,
  refreshKey,
  initialFilters,
}: {
  companies: Company[];
  projects: Project[];
  suppliers: Supplier[];
  onOpen: (id: string) => void;
  refreshKey: number;
  initialFilters?: DocumentFilters;
}) {
  const [filters, setFilters] = useState<DocumentFilters>(
    () => ({ page: 1, limit: 25, ...initialFilters }),
  );

  // Arriving from a dashboard queue replaces the current filters.
  useEffect(() => {
    if (initialFilters) setFilters({ page: 1, limit: 25, ...initialFilters });
  }, [initialFilters]);
  const [rows, setRows] = useState<ImportDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const data = await aiImportApi.listDocuments(filters);
      setRows(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setError(null);
    } catch {
      setError("The document list could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { void load(); }, [load, refreshKey]);

  // Poll only while something is still being read.
  const inFlight = useMemo(
    () => rows.some((d) => IN_FLIGHT_STATUSES.includes(d.status)),
    [rows],
  );
  useEffect(() => {
    if (!inFlight) return;
    const timer = setInterval(() => void load(true), POLL_MS);
    return () => clearInterval(timer);
  }, [inFlight, load]);

  const setFilter = (patch: Partial<DocumentFilters>) =>
    setFilters((prev) => ({ ...prev, ...patch, page: 1 }));

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3 text-sm font-medium flex-wrap">
          <Filter className="w-4 h-4" /> Filters
          {filters.reason_code && (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-xs font-medium">
              waiting on: {filters.reason_code.replace(/_/g, " ").toLowerCase()}
              <button
                onClick={() => setFilter({ reason_code: undefined })}
                className="hover:text-amber-950"
                aria-label="Clear the reason filter"
              >
                <XCircle className="w-3.5 h-3.5" />
              </button>
            </span>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <select
            value={filters.company_id ?? ""}
            onChange={(e) => setFilter({ company_id: e.target.value || undefined })}
            className="h-9 px-3 rounded-md border border-border bg-background text-sm"
          >
            <option value="">All companies</option>
            {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>

          <select
            value={filters.project_id ?? ""}
            onChange={(e) => setFilter({ project_id: e.target.value || undefined })}
            className="h-9 px-3 rounded-md border border-border bg-background text-sm"
          >
            <option value="">All projects</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>

          <select
            value={filters.supplier_id ?? ""}
            onChange={(e) => setFilter({ supplier_id: e.target.value || undefined })}
            className="h-9 px-3 rounded-md border border-border bg-background text-sm"
          >
            <option value="">All suppliers</option>
            {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>

          <select
            value={filters.document_type ?? ""}
            onChange={(e) => setFilter({ document_type: (e.target.value || undefined) as DocumentType })}
            className="h-9 px-3 rounded-md border border-border bg-background text-sm"
          >
            <option value="">All document types</option>
            {Object.entries(DOCUMENT_TYPE_LABELS).map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>

          <select
            value={filters.status ?? ""}
            onChange={(e) => setFilter({ status: (e.target.value || undefined) as DocumentStatus })}
            className="h-9 px-3 rounded-md border border-border bg-background text-sm"
          >
            {STATUS_FILTERS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>

          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground shrink-0">From</label>
            <input
              type="date" value={filters.date_from ?? ""}
              onChange={(e) => setFilter({ date_from: e.target.value || undefined })}
              className="h-9 px-2 rounded-md border border-border bg-background text-sm w-full"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground shrink-0">To</label>
            <input
              type="date" value={filters.date_to ?? ""}
              onChange={(e) => setFilter({ date_to: e.target.value || undefined })}
              className="h-9 px-2 rounded-md border border-border bg-background text-sm w-full"
            />
          </div>

          <Button variant="outline" onClick={() => setFilters({ page: 1, limit: 25 })}>
            Clear filters
          </Button>
          <Button variant="outline" onClick={() => void load()}>
            <RefreshCw className="w-4 h-4 mr-2" /> Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/30 text-destructive rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="No documents match these filters"
          description="Import scanned paperwork on the Import Documents tab, or widen the filters."
        />
      ) : (
        <>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="text-left px-4 py-2.5 font-medium">Document</th>
                  <th className="text-left px-4 py-2.5 font-medium">Type</th>
                  <th className="text-left px-4 py-2.5 font-medium">Status</th>
                  <th className="text-left px-4 py-2.5 font-medium hidden lg:table-cell">What needs doing</th>
                  <th className="text-left px-4 py-2.5 font-medium hidden sm:table-cell">Uploaded</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((doc) => {
                  const topReason = doc.outcome_reasons[0];
                  return (
                    <tr key={doc.id} className="hover:bg-muted/30">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <FileText className="w-4 h-4 text-muted-foreground shrink-0" />
                          <div className="min-w-0">
                            <p className="truncate font-medium">{doc.file_name}</p>
                            <p className="text-xs text-muted-foreground">
                              {doc.batch_reference}
                              {doc.is_legacy && " · historical"}
                              {doc.page_count ? ` · ${doc.page_count} page(s)` : ""}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {DOCUMENT_TYPE_LABELS[doc.document_type]}
                        {doc.document_type !== "UNKNOWN" && !doc.document_type_confirmed && (
                          <span className="block text-xs text-muted-foreground">
                            {Math.round(doc.classification_confidence * 100)}% sure
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col items-start gap-1">
                          <DocumentStatusBadge status={doc.status} />
                          {doc.processing_outcome === "BLOCKED" && (
                            <OutcomeBadge outcome={doc.processing_outcome} />
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 hidden lg:table-cell max-w-sm">
                        {topReason ? (
                          <span className="text-xs text-muted-foreground">
                            {topReason.message}
                            {doc.outcome_reasons.length > 1 &&
                              ` (+${doc.outcome_reasons.length - 1} more)`}
                          </span>
                        ) : doc.status === "POSTED" ? (
                          <span className="text-xs text-green-600">Posted — nothing outstanding.</span>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground hidden sm:table-cell whitespace-nowrap">
                        {fmtDate(doc.created_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button size="sm" variant="outline" onClick={() => onOpen(doc.id)}>
                          Open
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {total} document{total === 1 ? "" : "s"}
              {inFlight && (
                <span className="ml-2 inline-flex items-center gap-1 text-xs">
                  <Loader2 className="w-3 h-3 animate-spin" /> some are still being read
                </span>
              )}
            </span>
            <div className="flex items-center gap-2">
              <Button
                size="sm" variant="outline"
                disabled={(filters.page ?? 1) <= 1}
                onClick={() => setFilters((p) => ({ ...p, page: (p.page ?? 1) - 1 }))}
              >
                Previous
              </Button>
              <span className="text-xs text-muted-foreground">
                Page {filters.page ?? 1} of {totalPages}
              </span>
              <Button
                size="sm" variant="outline"
                disabled={(filters.page ?? 1) >= totalPages}
                onClick={() => setFilters((p) => ({ ...p, page: (p.page ?? 1) + 1 }))}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Reconciliation dashboard ──────────────────────────────────────────────────

/** The policy reason behind each queue, so a count can open its worklist. */
const QUEUE_REASON_CODES: Record<string, string> = {
  unmatched_invoices:      "NO_PURCHASE_ORDER",
  missing_purchase_orders: "NO_PURCHASE_ORDER",
  unconfirmed_receipts:    "NO_GOODS_RECEIPT",
  stock_discrepancies:     "QUANTITY_DISCREPANCY",
  invoice_discrepancies:   "PRICE_DISCREPANCY",
  duplicate_documents:     "DUPLICATE_FILE",
  unknown_suppliers:       "UNKNOWN_SUPPLIER",
  unknown_projects:        "UNKNOWN_PROJECT",
  missing_authorisation:   "MISSING_AUTHORISATION",
};

const QUEUE_LABELS: Record<string, string> = {
  unmatched_invoices:     "Invoices with no purchase order",
  missing_purchase_orders: "Missing purchase orders",
  unconfirmed_receipts:   "Deliveries not confirmed",
  stock_discrepancies:    "Stock discrepancies",
  invoice_discrepancies:  "Invoice discrepancies",
  duplicate_documents:    "Duplicates detected",
  unknown_suppliers:      "Unknown suppliers",
  unknown_projects:       "Unknown projects",
  missing_authorisation:  "Missing authorisation",
};

function DashboardPanel({
  projects,
  refreshKey,
  onOpenQueue,
}: {
  projects: Project[];
  refreshKey: number;
  onOpenQueue: (reasonCode: string, projectId?: string) => void;
}) {
  const [projectId, setProjectId] = useState("");
  const [data, setData] = useState<ImportDashboard | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    aiImportApi
      .dashboard(projectId ? { project_id: projectId } : {})
      .then((d) => { if (active) setData(d); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId, refreshKey]);

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
      </div>
    );
  }
  if (!data) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="The dashboard could not be loaded"
        description="Refresh the page, or check that the backend is reachable."
      />
    );
  }

  const t = data.totals;

  return (
    <div className="space-y-5">
      <select
        value={projectId}
        onChange={(e) => setProjectId(e.target.value)}
        className="h-9 px-3 rounded-md border border-border bg-background text-sm"
      >
        <option value="">All projects</option>
        {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Uploaded" value={t.uploaded} icon={Inbox} color="bg-blue-100 text-blue-700" />
        <StatCard
          title="Identified" value={t.classified} icon={ScanLine}
          color="bg-indigo-100 text-indigo-700"
          sub={`${t.in_progress} still being read`}
        />
        <StatCard
          title="Needs review" value={t.awaiting_review + t.awaiting_authorisation}
          icon={AlertTriangle} color="bg-amber-100 text-amber-700"
          sub={t.awaiting_authorisation ? `${t.awaiting_authorisation} need authorisation` : undefined}
        />
        <StatCard
          title="Posted" value={t.posted} icon={CheckCircle2}
          color="bg-green-100 text-green-700"
          sub={`${t.posted_transactions} transaction(s) created`}
        />
        <StatCard title="Ready to post" value={t.ready_to_post} icon={Clock} color="bg-sky-100 text-sky-700" />
        <StatCard title="Duplicates" value={t.duplicates} icon={Copy} color="bg-slate-100 text-slate-700" />
        <StatCard
          title="Failed" value={t.failed} icon={XCircle} color="bg-red-100 text-red-700"
          sub={t.failed_jobs ? `${t.failed_jobs} failed job(s)` : undefined}
        />
        <StatCard
          title="Awaiting authorisation"
          value={fmtMoney(data.amounts_awaiting_authorisation)}
          icon={FileText} color="bg-purple-100 text-purple-700"
          sub="Invoice value not yet posted"
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="bg-card border border-border rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3">What is holding documents up</h3>
          <div className="space-y-2">
            {Object.entries(QUEUE_LABELS).map(([key, label]) => {
              const count = data.queues[key] ?? 0;
              const code = QUEUE_REASON_CODES[key];
              return (
                <button
                  key={key}
                  type="button"
                  disabled={!count || !code}
                  onClick={() => onOpenQueue(code, projectId || undefined)}
                  className={`w-full flex items-center justify-between text-sm rounded-md px-2 -mx-2 py-1 text-left transition-colors ${
                    count && code ? "hover:bg-muted cursor-pointer" : "cursor-default"
                  }`}
                  title={count && code ? `Show the ${count} document(s) waiting on this` : undefined}
                >
                  <span className="text-muted-foreground">{label}</span>
                  <span className={`font-semibold ${count ? "" : "text-muted-foreground"}`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-5">
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-3">By document type</h3>
            {Object.keys(data.by_document_type).length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing uploaded yet.</p>
            ) : (
              <div className="space-y-2">
                {Object.entries(data.by_document_type).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">
                      {DOCUMENT_TYPE_LABELS[type as DocumentType] ?? type}
                    </span>
                    <span className="font-semibold">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-3">AI usage</h3>
            {!data.ai_usage.provider_configured && (
              <p className="text-sm text-amber-700 bg-amber-50 dark:bg-amber-900/20 rounded-md px-3 py-2 mb-3">
                No AI provider is configured. Documents are still stored and tracked, but they
                are read by the basic text parser only and all need checking by hand.
              </p>
            )}
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Model</span>
                <span className="font-mono text-xs">{data.ai_usage.model}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Tokens read / written</span>
                <span className="font-semibold">
                  {data.ai_usage.input_tokens.toLocaleString()} / {data.ai_usage.output_tokens.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Cost so far</span>
                <span className="font-semibold">${data.ai_usage.cost_usd.toFixed(4)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {t.incomplete_postings > 0 && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-300 rounded-xl px-4 py-3 text-sm">
          <p className="font-medium text-amber-900 dark:text-amber-200">
            {t.incomplete_postings} posting(s) did not finish.
          </p>
          <p className="text-amber-800 dark:text-amber-300 mt-1">
            A posting attempt was interrupted. Nothing was duplicated — retries are blocked —
            but someone should check in the destination module whether the record exists.
            Details are on the operations health endpoint.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AIDocumentImportPage() {
  const [tab, setTab] = useState("upload");
  const [projects, setProjects] = useState<Project[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [queueFilters, setQueueFilters] = useState<DocumentFilters | undefined>();
  const [service, setService] = useState<ServiceStatus | null>(null);

  useEffect(() => {
    void projectsApi.list(1, 200).then((r) => setProjects(r.items ?? [])).catch(() => setProjects([]));
    void suppliersApi.list().then(setSuppliers).catch(() => setSuppliers([]));
    void companiesApi.list().then(setCompanies).catch(() => setCompanies([]));
    void aiImportApi.serviceStatus().then(setService).catch(() => setService(null));
  }, []);

  const bump = () => setRefreshKey((k) => k + 1);

  return (
    <div className="p-4 sm:p-6 max-w-[1400px] mx-auto">
      <PageHeader
        title="Bypass Orders"
        description="Upload material requests, purchase orders, delivery notes and supplier invoices. AI will automatically identify, extract and reconcile the documents with the correct project and records."
        actions={
          <Button variant="outline" onClick={bump}>
            <RefreshCw className="w-4 h-4 mr-2" /> Refresh
          </Button>
        }
      />

      {service && (!service.enabled || !service.extraction_available || !service.private_storage_configured) && (
        <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <p className="font-medium">
            {!service.enabled
              ? "Bypass Orders is switched off"
              : "Bypass Orders is running with reduced capability"}
          </p>
          <ul className="mt-1 list-disc pl-5 space-y-0.5">
            {!service.enabled && (
              <li>Uploading is disabled for this environment. Existing documents remain viewable.</li>
            )}
            {service.enabled && !service.extraction_available && (
              <li>
                No AI provider is configured, so documents are stored, de-duplicated and queued for
                review, but their contents are not read. Fields will come back empty — that is the
                missing configuration, not a bad scan.
              </li>
            )}
            {service.enabled && !service.private_storage_configured && (
              <li>Private document storage is not configured, so uploads may be refused.</li>
            )}
          </ul>
        </div>
      )}

      <Tabs
        tabs={[
          { key: "upload", label: "Import Documents" },
          // Between upload and the per-document queue, because that is where
          // it belongs in the work: see what the whole batch would do, fix
          // what is wrong, then go document by document.
          { key: "review", label: "Batch Review" },
          { key: "documents", label: "Documents" },
          { key: "dashboard", label: "Reconciliation" },
        ]}
        active={tab}
        onChange={setTab}
      />

      <div className="mt-5">
        {tab === "upload" && (
          <UploadPanel
            projects={projects}
            onUploaded={() => { bump(); setTab("review"); }}
          />
        )}
        {tab === "review" && (
          <BatchReviewPanel
            projects={projects}
            suppliers={suppliers}
            refreshKey={refreshKey}
            onOpenDocument={setOpenId}
          />
        )}
        {tab === "documents" && (
          <DocumentQueue
            companies={companies}
            projects={projects}
            suppliers={suppliers}
            onOpen={setOpenId}
            refreshKey={refreshKey}
            initialFilters={queueFilters}
          />
        )}
        {tab === "dashboard" && (
          <DashboardPanel
            projects={projects}
            refreshKey={refreshKey}
            onOpenQueue={(reasonCode, projectId) => {
              setQueueFilters({ reason_code: reasonCode, project_id: projectId });
              setTab("documents");
            }}
          />
        )}
      </div>

      {openId && (
        <AIDocumentImportDetail
          documentId={openId}
          projects={projects}
          suppliers={suppliers}
          onClose={() => setOpenId(null)}
          onChanged={bump}
        />
      )}
    </div>
  );
}
