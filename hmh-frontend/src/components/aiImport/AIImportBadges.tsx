import {
  AlertTriangle, CheckCircle2, Clock, Copy, Loader2, ScanLine, ShieldAlert, XCircle,
} from "lucide-react";

import {
  STATUS_LABELS,
  confidenceBand,
  type DocumentStatus,
  type MatchStatus,
  type ProcessingOutcome,
} from "@/api/aiImport";

const PILL = "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap";

const STATUS_STYLES: Record<DocumentStatus, string> = {
  UPLOADED:               "bg-muted text-muted-foreground",
  QUEUED:                 "bg-muted text-muted-foreground",
  PROCESSING:             "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  EXTRACTED:              "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  CLASSIFIED:             "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  MATCHING:               "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  AWAITING_REVIEW:        "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  AWAITING_AUTHORISATION: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  READY_TO_POST:          "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400",
  POSTED:                 "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  PARTIALLY_POSTED:       "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  FAILED:                 "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  REJECTED:               "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  DUPLICATE:              "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const icon =
    status === "PROCESSING" ? <Loader2 className="w-3 h-3 animate-spin" /> :
    ["UPLOADED", "QUEUED"].includes(status) ? <Clock className="w-3 h-3" /> :
    ["EXTRACTED", "CLASSIFIED", "MATCHING"].includes(status) ? <ScanLine className="w-3 h-3" /> :
    status === "AWAITING_REVIEW" ? <AlertTriangle className="w-3 h-3" /> :
    status === "AWAITING_AUTHORISATION" ? <ShieldAlert className="w-3 h-3" /> :
    status === "DUPLICATE" ? <Copy className="w-3 h-3" /> :
    ["FAILED", "REJECTED"].includes(status) ? <XCircle className="w-3 h-3" /> :
    <CheckCircle2 className="w-3 h-3" />;

  return <span className={`${PILL} ${STATUS_STYLES[status]}`}>{icon}{STATUS_LABELS[status]}</span>;
}

const OUTCOME_STYLES: Record<ProcessingOutcome, string> = {
  AUTO_ELIGIBLE: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  NEEDS_REVIEW:  "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  BLOCKED:       "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

const OUTCOME_LABELS: Record<ProcessingOutcome, string> = {
  AUTO_ELIGIBLE: "All checks passed",
  NEEDS_REVIEW:  "Needs review",
  BLOCKED:       "Blocked",
};

export function OutcomeBadge({ outcome }: { outcome: ProcessingOutcome | null }) {
  if (!outcome) return null;
  const icon =
    outcome === "AUTO_ELIGIBLE" ? <CheckCircle2 className="w-3 h-3" /> :
    outcome === "BLOCKED" ? <XCircle className="w-3 h-3" /> :
    <AlertTriangle className="w-3 h-3" />;
  return <span className={`${PILL} ${OUTCOME_STYLES[outcome]}`}>{icon}{OUTCOME_LABELS[outcome]}</span>;
}

const MATCH_STYLES: Record<MatchStatus, string> = {
  CONFIRMED: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  PROPOSED:  "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400",
  AMBIGUOUS: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  REJECTED:  "bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
};

const MATCH_LABELS: Record<MatchStatus, string> = {
  CONFIRMED: "Confirmed",
  PROPOSED:  "Suggested",
  AMBIGUOUS: "Needs a choice",
  REJECTED:  "Rejected",
};

export function MatchStatusBadge({ status }: { status: MatchStatus }) {
  return <span className={`${PILL} ${MATCH_STYLES[status]}`}>{MATCH_LABELS[status]}</span>;
}

/**
 * How certain the reader was about one value.
 *
 * Shown on every extracted field so a reviewer knows where to look first,
 * rather than having to re-check everything.
 */
export function ConfidenceDot({ confidence, corrected }: { confidence: number; corrected?: boolean }) {
  if (corrected) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-700 dark:text-green-400">
        <CheckCircle2 className="w-3 h-3" /> corrected
      </span>
    );
  }
  const band = confidenceBand(confidence);
  const colour =
    band === "high" ? "bg-green-500" : band === "medium" ? "bg-amber-500" : "bg-red-500";
  const label =
    band === "high" ? "read clearly" : band === "medium" ? "check this" : "hard to read";
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" title={`${Math.round(confidence * 100)}% confident`}>
      <span className={`w-2 h-2 rounded-full ${colour}`} />
      {label}
    </span>
  );
}
