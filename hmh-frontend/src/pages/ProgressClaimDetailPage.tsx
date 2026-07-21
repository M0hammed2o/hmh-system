import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, RefreshCw, Download, AlertCircle, Zap, CheckCircle, ToggleLeft, ToggleRight } from "lucide-react";
import {
  getProgressClaim, generateClaimLines, transitionClaimStatus,
  updateClaimLine, exportClaimPdf,
  ProgressClaim, ClaimLine, ProgressClaimStatus,
} from "@/api/progressClaims";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_COLORS: Record<string, string> = {
  DRAFT:             "bg-slate-100 text-slate-700",
  GENERATED:         "bg-blue-100 text-blue-700",
  UNDER_REVIEW:      "bg-yellow-100 text-yellow-700",
  READY_FOR_PRICING: "bg-orange-100 text-orange-700",
  APPROVED:          "bg-green-100 text-green-700",
  EXPORTED:          "bg-purple-100 text-purple-700",
  CANCELLED:         "bg-red-100 text-red-700",
};

const SOURCE_LABELS: Record<string, string> = {
  STAGE_MILESTONE: "Milestone",
  WORK_DONE:       "Work Done",
  JOB_CARD:        "Job Card",
};

const SOURCE_COLORS: Record<string, string> = {
  STAGE_MILESTONE: "bg-green-50 text-green-700",
  WORK_DONE:       "bg-blue-50 text-blue-700",
  JOB_CARD:        "bg-orange-50 text-orange-700",
};

const NEXT_STATUS: Partial<Record<ProgressClaimStatus, { to: ProgressClaimStatus; label: string }>> = {
  GENERATED:         { to: "UNDER_REVIEW",       label: "Start Review" },
  UNDER_REVIEW:      { to: "READY_FOR_PRICING",  label: "Mark Ready for Pricing" },
  READY_FOR_PRICING: { to: "APPROVED",           label: "Approve Claim" },
  APPROVED:          { to: "EXPORTED",           label: "Mark Exported" },
};

export default function ProgressClaimDetailPage() {
  const { claimId } = useParams<{ claimId: string }>();
  const navigate = useNavigate();

  const [claim, setClaim] = useState<ProgressClaim | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const fetchClaim = useCallback(() => {
    if (!claimId) return;
    setLoading(true);
    setLoadError(null);
    getProgressClaim(claimId)
      .then(setClaim)
      .catch(() => setLoadError("Failed to load claim."))
      .finally(() => setLoading(false));
  }, [claimId]);

  useEffect(() => { fetchClaim(); }, [fetchClaim]);

  const handleGenerate = async () => {
    if (!claimId) return;
    setGenerating(true);
    setActionError(null);
    try {
      await generateClaimLines(claimId, { overwrite_existing: false });
      fetchClaim();
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || "Failed to generate lines.");
    } finally {
      setGenerating(false);
    }
  };

  const handleTransition = async (newStatus: ProgressClaimStatus) => {
    if (!claimId) return;
    setTransitioning(true);
    setActionError(null);
    try {
      const updated = await transitionClaimStatus(claimId, newStatus);
      setClaim(updated);
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || "Transition failed.");
    } finally {
      setTransitioning(false);
    }
  };

  const handleToggleLine = async (lineId: string, newIncluded: boolean) => {
    if (!claimId) return;
    setTogglingId(lineId);
    try {
      await updateClaimLine(claimId, lineId, { is_included: newIncluded });
      setClaim((prev) =>
        prev
          ? { ...prev, lines: prev.lines.map((l) => l.id === lineId ? { ...l, is_included: newIncluded } : l) }
          : prev
      );
    } catch {
      // leave as-is; next refresh will correct
    } finally {
      setTogglingId(null);
    }
  };

  const handleExportPdf = async () => {
    if (!claimId || !claim) return;
    setActionError(null);
    try {
      const blob = await exportClaimPdf(claimId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${claim.claim_number}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || "PDF export failed.");
    }
  };

  if (loading) {
    return (
      <div className="p-6 max-w-5xl mx-auto space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (loadError || !claim) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Back
        </Button>
        <div className="mt-6 text-center text-destructive">{loadError || "Claim not found."}</div>
      </div>
    );
  }

  const nextStep = NEXT_STATUS[claim.status];
  const includedCount = claim.lines.filter((l) => l.is_included).length;
  const isEditable = !["APPROVED", "EXPORTED", "CANCELLED"].includes(claim.status);
  const isActionBusy = generating || transitioning;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start gap-4 mb-6">
        <Button variant="ghost" size="sm" onClick={() => navigate("/progress-claims")}>
          <ArrowLeft className="w-4 h-4 mr-1" /> Back
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-xl font-bold">{claim.claim_number}</h1>
            <Badge className={STATUS_COLORS[claim.status] || ""}>{claim.status.replace(/_/g, " ")}</Badge>
          </div>
          <p className="text-sm font-medium">{claim.claim_title}</p>
          <p className="text-xs text-muted-foreground">
            {claim.municipality_name} • Period: {claim.period_start} → {claim.period_end}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchClaim}>
            <RefreshCw className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={handleExportPdf}>
            <Download className="w-4 h-4 mr-1" /> Export PDF
          </Button>
          {isEditable && (
            <Button size="sm" variant="outline" onClick={handleGenerate} disabled={isActionBusy}>
              <Zap className="w-4 h-4 mr-1" />
              {generating ? "Generating..." : "Generate Lines"}
            </Button>
          )}
          {nextStep && (
            <Button size="sm" onClick={() => handleTransition(nextStep.to)} disabled={isActionBusy}>
              <CheckCircle className="w-4 h-4 mr-1" />
              {transitioning ? "Processing..." : nextStep.label}
            </Button>
          )}
        </div>
      </div>

      {/* Generation summary */}
      {claim.generation_summary && (
        <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg p-3 mb-4 text-sm text-blue-800 dark:text-blue-200">
          <strong>Last generation:</strong>{" "}
          {(claim.generation_summary as any).milestone_lines ?? 0} milestones,{" "}
          {(claim.generation_summary as any).work_done_lines ?? 0} work done,{" "}
          {(claim.generation_summary as any).job_card_lines ?? 0} job cards
          {((claim.generation_summary as any).skipped_duplicates ?? 0) > 0 &&
            ` (${(claim.generation_summary as any).skipped_duplicates} duplicates skipped)`}
        </div>
      )}

      {/* No-pricing notice */}
      <div className="flex items-start gap-2 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg p-3 mb-4 text-sm text-amber-800 dark:text-amber-200">
        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          This claim contains <strong>work evidence only</strong> — no monetary amounts.
          Pricing is added manually after the claim reaches <em>Ready for Pricing</em> status.
        </span>
      </div>

      {actionError && (
        <div className="bg-destructive/10 border border-destructive/30 text-destructive rounded-lg px-4 py-2 mb-4 text-sm">
          {actionError}
        </div>
      )}

      {/* Lines */}
      <div className="bg-card border rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b bg-muted/30 flex items-center justify-between">
          <h2 className="font-semibold text-sm">Claim Lines</h2>
          <span className="text-xs text-muted-foreground">{includedCount} / {claim.lines.length} included</span>
        </div>

        {claim.lines.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground text-sm">
            No lines yet. Click <strong>Generate Lines</strong> to pull from operational data.
          </div>
        ) : (
          <div className="divide-y">
            {claim.lines.map((line, idx) => (
              <LineRow
                key={line.id}
                line={line}
                index={idx + 1}
                isEditable={isEditable}
                toggling={togglingId === line.id}
                onToggle={(v) => handleToggleLine(line.id, v)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LineRow({
  line, index, isEditable, toggling, onToggle,
}: {
  line: ClaimLine;
  index: number;
  isEditable: boolean;
  toggling: boolean;
  onToggle: (v: boolean) => void;
}) {
  return (
    <div className={`flex items-start gap-3 px-4 py-3 ${!line.is_included ? "opacity-50" : ""}`}>
      <span className="text-xs text-muted-foreground w-5 shrink-0 mt-1">{index}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
          <Badge className={`text-[10px] px-1.5 py-0 ${SOURCE_COLORS[line.source_type] || ""}`}>
            {SOURCE_LABELS[line.source_type] || line.source_type}
          </Badge>
          {line.lot_number && <span className="text-[10px] text-muted-foreground">Lot {line.lot_number}</span>}
          {line.stage_name && <span className="text-[10px] text-muted-foreground">{line.stage_name}</span>}
        </div>
        <p className="text-sm">{line.description}</p>
        <div className="flex gap-3 mt-1 text-xs text-muted-foreground">
          {line.work_date && <span>Date: {line.work_date}</span>}
          {line.quantity && <span>{line.quantity} {line.unit}</span>}
          {line.progress_pct != null && <span>{line.progress_pct}% progress</span>}
        </div>
      </div>
      {isEditable && (
        <button
          onClick={() => !toggling && onToggle(!line.is_included)}
          disabled={toggling}
          className="shrink-0 text-muted-foreground hover:text-primary transition-colors disabled:opacity-40"
          title={line.is_included ? "Exclude this line" : "Include this line"}
        >
          {line.is_included
            ? <ToggleRight className="w-5 h-5 text-primary" />
            : <ToggleLeft className="w-5 h-5" />}
        </button>
      )}
    </div>
  );
}
