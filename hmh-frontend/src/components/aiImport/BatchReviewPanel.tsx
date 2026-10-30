/**
 * Batch review — what this upload would do, before it does any of it.
 *
 * A real batch is twenty documents of six different kinds, and the
 * consequences are nothing like uniform: one delivery note moves stock, two
 * tax invoices create a liability, eight purchase orders commit spend, and
 * the quotations and pro-formas create nothing at all. Approving those one
 * drawer at a time gives nobody a view of the whole, which is how a
 * pro-forma ends up paid twice.
 *
 * So this is a manifest. One row per document, each stating its destination,
 * what importing it would do, and whether it needs a person first. Every
 * verdict comes from the server's routing service — nothing here works out a
 * destination for itself, because a screen that does will eventually
 * disagree with what the server actually writes.
 *
 * Corrections are made in place. Classification, supplier and project are the
 * three things the reader can see are wrong at a glance, so they are the
 * three that are editable here rather than four clicks away.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowRight, BadgeCheck, Ban, CheckCircle2, FileWarning,
  Link2, Loader2, RefreshCw, Wallet,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import {
  aiImportApi,
  DOCUMENT_TYPE_LABELS,
  MANIFEST_ACTION_LABELS,
  type BatchManifest,
  type DocumentType,
  type ImportBatch,
  type ManifestAction,
  type ManifestRow,
} from "@/api/aiImport";
import type { Project } from "@/api/projects";
import type { Supplier } from "@/api/suppliers";

const POLL_MS = 5000;

const DOCUMENT_TYPES: DocumentType[] = [
  "MATERIAL_REQUEST",
  "QUOTATION",
  "PURCHASE_ORDER",
  "PRO_FORMA_INVOICE",
  "SUPPLIER_INVOICE",
  "DELIVERY_NOTE",
  "GOODS_RECEIVED_NOTE",
  "SUPPLIER_CREDIT_NOTE",
  "PAYMENT_PROOF",
  "UNKNOWN",
];

const fmtMoney = (raw: string | null) => {
  if (!raw) return "—";
  const n = Number(raw);
  if (!Number.isFinite(n)) return raw;
  return `R ${n.toLocaleString("en-ZA", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
};

// ── Action badge ──────────────────────────────────────────────────────────────
// Colour carries meaning here, so it is never the only carrier: each badge
// also says what it is. A row that is going to create a liability and a row
// that is going to be skipped must not look the same at a glance.

const ACTION_STYLES: Record<ManifestAction, string> = {
  CREATE:         "bg-emerald-50 text-emerald-700 border-emerald-200",
  LINK_EXISTING:  "bg-sky-50 text-sky-700 border-sky-200",
  REVIEW:         "bg-amber-50 text-amber-800 border-amber-200",
  SKIP_DUPLICATE: "bg-slate-100 text-slate-600 border-slate-300",
};

const ACTION_ICONS: Record<ManifestAction, typeof CheckCircle2> = {
  CREATE:         CheckCircle2,
  LINK_EXISTING:  Link2,
  REVIEW:         AlertTriangle,
  SKIP_DUPLICATE: Ban,
};

function ActionBadge({ action }: { action: ManifestAction | null }) {
  if (!action) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Reading…
      </span>
    );
  }
  const Icon = ACTION_ICONS[action];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-semibold",
        ACTION_STYLES[action],
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {MANIFEST_ACTION_LABELS[action]}
    </span>
  );
}

// ── Summary header ────────────────────────────────────────────────────────────

function SummaryBar({ manifest }: { manifest: BatchManifest }) {
  const { summary, rows } = manifest;
  const creating = (summary.by_action.CREATE ?? 0) + (summary.by_action.LINK_EXISTING ?? 0);

  // Named individually rather than as "3 financial documents", because the
  // two consequences are not interchangeable: one is money owed, the other
  // is money asked for.
  const payables = rows.filter(
    (r) => r.routing.destination === "accounts_payable" && r.routing.action !== "SKIP_DUPLICATE",
  ).length;
  const provisional = rows.filter(
    (r) => r.routing.destination === "provisional_charges" && r.routing.action !== "SKIP_DUPLICATE",
  ).length;
  const stock = rows.filter(
    (r) => r.routing.destination === "goods_received" && r.routing.action !== "SKIP_DUPLICATE",
  ).length;

  const tiles = [
    { label: "Will be imported", value: creating, tone: "text-emerald-700" },
    { label: "Need review first", value: summary.needs_review_count, tone: "text-amber-700" },
    { label: "Duplicates, skipped", value: summary.duplicate_count, tone: "text-slate-600" },
    { label: "Create a liability", value: payables, tone: "text-rose-700" },
    { label: "Pending charges", value: provisional, tone: "text-violet-700" },
    { label: "Move stock", value: stock, tone: "text-sky-700" },
  ];

  return (
    <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-lg border border-slate-200 bg-white p-3">
          <div className={cn("text-2xl font-semibold tabular-nums", t.tone)}>{t.value}</div>
          <div className="mt-0.5 text-xs text-slate-500">{t.label}</div>
        </div>
      ))}
    </div>
  );
}

// ── One row ───────────────────────────────────────────────────────────────────

interface RowProps {
  row: ManifestRow;
  projects: Project[];
  suppliers: Supplier[];
  busy: boolean;
  onCorrect: (
    documentId: string,
    patch: { document_type?: DocumentType; supplier_id?: string; project_id?: string },
  ) => void;
  onOpen: (documentId: string) => void;
}

function ManifestRowCard({ row, projects, suppliers, busy, onCorrect, onOpen }: RowProps) {
  const { routing } = row;
  const skipped = routing.action === "SKIP_DUPLICATE";

  return (
    <tr className={cn("border-b border-slate-100 align-top", skipped && "opacity-60")}>
      {/* Document */}
      <td className="px-3 py-3">
        <button
          type="button"
          onClick={() => onOpen(row.document_id)}
          className="text-left text-sm font-medium text-slate-900 hover:text-sky-700 hover:underline"
        >
          {row.file_name}
        </button>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          {row.reference && <span className="font-mono">{row.reference}</span>}
          {!row.document_type_confirmed && row.classification_confidence > 0 && (
            <span title="The classifier's own certainty. Nobody has confirmed it yet.">
              {Math.round(row.classification_confidence * 100)}% confident
            </span>
          )}
          {row.document_type_confirmed && (
            <span className="inline-flex items-center gap-1 text-emerald-700">
              <BadgeCheck className="h-3.5 w-3.5" /> confirmed
            </span>
          )}
        </div>
      </td>

      {/* Type — correctable in place */}
      <td className="px-3 py-3">
        <select
          value={row.document_type}
          disabled={busy}
          onChange={(e) =>
            onCorrect(row.document_id, { document_type: e.target.value as DocumentType })
          }
          className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm disabled:opacity-50"
          aria-label={`Document type for ${row.file_name}`}
        >
          {DOCUMENT_TYPES.map((t) => (
            <option key={t} value={t}>{DOCUMENT_TYPE_LABELS[t]}</option>
          ))}
        </select>
      </td>

      {/* Supplier */}
      <td className="px-3 py-3">
        <select
          value={row.supplier_id ?? ""}
          disabled={busy}
          onChange={(e) => onCorrect(row.document_id, { supplier_id: e.target.value })}
          className={cn(
            "w-full rounded-md border bg-white px-2 py-1.5 text-sm disabled:opacity-50",
            row.supplier_id ? "border-slate-300" : "border-amber-400 bg-amber-50",
          )}
          aria-label={`Supplier for ${row.file_name}`}
        >
          <option value="">
            {row.supplier_name ? `Not linked — read as "${row.supplier_name}"` : "Not linked"}
          </option>
          {suppliers.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      </td>

      {/* Project */}
      <td className="px-3 py-3">
        <select
          value={row.project_id ?? ""}
          disabled={busy}
          onChange={(e) => onCorrect(row.document_id, { project_id: e.target.value })}
          className={cn(
            "w-full rounded-md border bg-white px-2 py-1.5 text-sm disabled:opacity-50",
            row.project_id ? "border-slate-300" : "border-amber-400 bg-amber-50",
          )}
          aria-label={`Project for ${row.file_name}`}
        >
          <option value="">Not set</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </td>

      {/* Amount */}
      <td className="px-3 py-3 text-right text-sm tabular-nums text-slate-800">
        {fmtMoney(row.total_amount)}
      </td>

      {/* Destination and what it would do */}
      <td className="px-3 py-3">
        <div className="text-sm font-medium text-slate-900">
          {routing.destination_label}
        </div>
        <div className="mt-0.5 text-xs text-slate-500">{routing.effect}</div>
        {routing.linked_label && (
          <div className="mt-1 inline-flex items-center gap-1 text-xs text-sky-700">
            <ArrowRight className="h-3 w-3" />
            {routing.linked_label}
          </div>
        )}
      </td>

      {/* Action and the questions attached to it */}
      <td className="px-3 py-3">
        <ActionBadge action={routing.action} />
        <div className="mt-1.5 text-xs text-slate-600">{routing.reason}</div>

        {row.payment_evidence_detected && (
          <div className="mt-2 flex gap-1.5 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
            <Wallet className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{row.payment_evidence_note}</span>
          </div>
        )}

        {routing.review_notes.length > 0 && (
          <ul className="mt-2 space-y-1.5">
            {routing.review_notes.map((note, i) => (
              <li
                key={i}
                className="flex gap-1.5 rounded-md border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700"
              >
                <FileWarning className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                <span>{note}</span>
              </li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────

interface Props {
  projects: Project[];
  suppliers: Supplier[];
  refreshKey: number;
  onOpenDocument: (documentId: string) => void;
}

export function BatchReviewPanel({ projects, suppliers, refreshKey, onOpenDocument }: Props) {
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [manifest, setManifest] = useState<BatchManifest | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyDoc, setBusyDoc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    aiImportApi
      .listBatches()
      .then((list) => {
        if (cancelled) return;
        setBatches(list);
        setBatchId((current) => current ?? list[0]?.id ?? null);
      })
      .catch((e) => !cancelled && setError(e?.message ?? "Could not load batches."));
    return () => { cancelled = true; };
  }, [refreshKey]);

  const load = useCallback(async () => {
    if (!batchId) { setLoading(false); return; }
    try {
      const data = await aiImportApi.getBatchManifest(batchId);
      setManifest(data);
      setError(null);
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Could not load the manifest.");
    } finally {
      setLoading(false);
    }
  }, [batchId]);

  useEffect(() => { setLoading(true); void load(); }, [load, refreshKey]);

  // Keep polling only while something is still being read. A finished batch
  // does not change on its own, and polling it forever is just noise.
  const stillReading = useMemo(
    () => (manifest?.rows ?? []).some((r) => r.routing.action === null),
    [manifest],
  );
  useEffect(() => {
    if (!stillReading) return;
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [stillReading, load]);

  const correct = useCallback(
    async (
      documentId: string,
      patch: { document_type?: DocumentType; supplier_id?: string; project_id?: string },
    ) => {
      setBusyDoc(documentId);
      try {
        await aiImportApi.assignContext(documentId, patch);
        await load();
      } catch (e: unknown) {
        setError((e as Error)?.message ?? "The correction was not saved.");
      } finally {
        setBusyDoc(null);
      }
    },
    [load],
  );

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!batchId || batches.length === 0) {
    return (
      <EmptyState
        icon={FileWarning}
        title="No batches yet"
        description="Upload a batch of paperwork and its import manifest will appear here."
      />
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium text-slate-700" htmlFor="batch-select">
          Batch
        </label>
        <select
          id="batch-select"
          value={batchId}
          onChange={(e) => setBatchId(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm"
        >
          {batches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.reference} — {b.document_count} document{b.document_count === 1 ? "" : "s"}
            </option>
          ))}
        </select>
        <Button variant="outline" size="sm" onClick={() => void load()}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Refresh
        </Button>
        {stillReading && (
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Still reading some documents
          </span>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </div>
      )}

      {manifest && (
        <>
          <SummaryBar manifest={manifest} />

          <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-600">
            Nothing below has been written yet. This is what importing would do. Correct a
            type, supplier or project here and the destination updates with it; approve each
            document from its own screen once the row reads correctly.
          </div>

          <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full min-w-[1100px] border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                  <th className="px-3 py-2">Document</th>
                  <th className="px-3 py-2">Detected type</th>
                  <th className="px-3 py-2">Supplier</th>
                  <th className="px-3 py-2">Project</th>
                  <th className="px-3 py-2 text-right">Amount</th>
                  <th className="px-3 py-2">Destination</th>
                  <th className="px-3 py-2">Proposed action</th>
                </tr>
              </thead>
              <tbody>
                {manifest.rows.map((row) => (
                  <ManifestRowCard
                    key={row.document_id}
                    row={row}
                    projects={projects}
                    suppliers={suppliers}
                    busy={busyDoc === row.document_id}
                    onCorrect={correct}
                    onOpen={onOpenDocument}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
