/**
 * Milestones — per-lot milestone tracking.
 *
 * Each milestone card shows:
 *   - Status + manual complete button
 *   - Multiple progress photos (upload / delete)
 *   - Material summary (Required / Delivered / Used / Remaining / Shortfall)
 *   - Labour (Job Cards linked to this stage)
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2, Circle, Clock, AlertTriangle, Camera,
  ChevronDown, ChevronUp, Plus, X as XIcon,
  RefreshCw, Package, HardHat, Ban, PlayCircle, History,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { lotsApi, type Lot } from "@/api/lots";
import {
  stagesApi,
  type StageMaster, type ProjectStageStatus, type MilestonePhoto, type StageStatus,
  type MilestoneActivityEntry,
} from "@/api/stages";
import { siteDashboardApi, type MaterialSummaryItem } from "@/api/siteDashboard";
import { jobCardsApi, type JobCard } from "@/api/jobCards";
import { cn } from "@/lib/utils";
import { ROLE_KEY } from "@/lib/constants";
import { formatDate } from "@/lib/format";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, dec = 1): string {
  if (n == null) return "—";
  return n % 1 === 0 ? String(n) : n.toFixed(dec);
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

const STATUS_META: Record<StageStatus, { label: string; icon: React.ReactNode; color: string; bg: string }> = {
  NOT_STARTED:         { label: "Not started",    icon: <Circle className="w-4 h-4" />,          color: "text-muted-foreground", bg: "bg-muted/40" },
  IN_PROGRESS:         { label: "In progress",    icon: <Clock className="w-4 h-4" />,             color: "text-blue-600",         bg: "bg-blue-50 dark:bg-blue-950/30" },
  BLOCKED:             { label: "Blocked",         icon: <Ban className="w-4 h-4" />,               color: "text-destructive",      bg: "bg-destructive/10" },
  AWAITING_INSPECTION: { label: "Awaiting check", icon: <AlertTriangle className="w-4 h-4" />,    color: "text-amber-600",        bg: "bg-amber-50 dark:bg-amber-950/30" },
  COMPLETED:           { label: "Completed",       icon: <CheckCircle2 className="w-4 h-4" />,    color: "text-green-600",        bg: "bg-green-50 dark:bg-green-950/30" },
  CERTIFIED:           { label: "Certified",       icon: <CheckCircle2 className="w-4 h-4" />,    color: "text-emerald-600",      bg: "bg-emerald-50 dark:bg-emerald-950/30" },
};

// ── Lightbox ──────────────────────────────────────────────────────────────────

function Lightbox({ url, onClose }: { url: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/85 backdrop-blur-sm"
      onClick={onClose}
    >
      <button
        className="absolute top-4 right-4 p-2 rounded-full bg-black/40 text-white/80 hover:text-white"
        onClick={onClose}
      >
        <XIcon className="w-5 h-5" />
      </button>
      <img
        src={url}
        alt="Progress photo"
        className="max-h-[90vh] max-w-[90vw] rounded-xl shadow-2xl object-contain"
        onClick={e => e.stopPropagation()}
      />
      <a
        href={url} target="_blank" rel="noopener noreferrer"
        className="absolute bottom-4 text-white/60 hover:text-white text-xs underline"
        onClick={e => e.stopPropagation()}
      >
        Open in new tab
      </a>
    </div>
  );
}

// ── Photo strip ───────────────────────────────────────────────────────────────

function PhotoStrip({
  projectId, statusId, photos, canWrite,
  onRefresh,
}: {
  projectId: string;
  statusId:  string;
  photos:    MilestonePhoto[];
  canWrite:  boolean;
  onRefresh: () => void;
}) {
  const fileRef    = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [lightbox,  setLightbox]  = useState<string | null>(null);
  const [deleting,  setDeleting]  = useState<string | null>(null);

  const upload = async (files: File[]) => {
    setUploading(true);
    try {
      for (const f of files) {
        await stagesApi.uploadPhoto(projectId, statusId, f);
      }
      onRefresh();
    } catch { /* silently show old state */ }
    finally { setUploading(false); }
  };

  const remove = async (id: string) => {
    setDeleting(id);
    try {
      await stagesApi.deletePhoto(projectId, statusId, id);
      onRefresh();
    } catch { /* ignore */ }
    finally { setDeleting(null); }
  };

  return (
    <div className="flex items-start gap-2 flex-wrap mt-3">
      {photos.map(p => (
        <div key={p.id} className="relative group shrink-0">
          <img
            src={p.url}
            alt={p.file_name}
            className="h-20 w-20 rounded-lg object-cover border border-border cursor-zoom-in hover:opacity-85 transition-opacity"
            onClick={() => setLightbox(p.url)}
            onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
          {canWrite && (
            <button
              onClick={() => remove(p.id)}
              disabled={deleting === p.id}
              className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-destructive text-white
                         flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity
                         disabled:opacity-50"
            >
              {deleting === p.id
                ? <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                : <XIcon className="w-2.5 h-2.5" />}
            </button>
          )}
        </div>
      ))}

      {canWrite && (
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className={cn(
            "h-20 w-20 rounded-lg border-2 border-dashed border-border flex flex-col items-center justify-center",
            "hover:border-primary hover:bg-muted/40 transition-colors text-muted-foreground hover:text-primary shrink-0",
            uploading && "opacity-50 pointer-events-none"
          )}
        >
          {uploading
            ? <RefreshCw className="w-5 h-5 animate-spin" />
            : <>
                <Camera className="w-5 h-5 mb-1" />
                <span className="text-[10px] leading-tight text-center">Add photo</span>
              </>}
        </button>
      )}

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        multiple
        className="sr-only"
        onChange={e => {
          const files = Array.from(e.target.files ?? []);
          if (files.length > 0) upload(files);
          e.target.value = "";
        }}
      />

      {lightbox && <Lightbox url={lightbox} onClose={() => setLightbox(null)} />}
    </div>
  );
}

// ── Material summary row ──────────────────────────────────────────────────────

function MaterialSummaryTable({ items, lotSelected }: { items: MaterialSummaryItem[]; lotSelected: boolean }) {
  if (!lotSelected) return (
    <p className="text-xs text-muted-foreground py-2">Select a lot / unit to see the material budget.</p>
  );
  if (items.length === 0) return (
    <p className="text-xs text-muted-foreground py-2">No BOQ items linked to this lot.</p>
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs min-w-[520px]">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left py-1.5 pr-3 text-muted-foreground font-medium">Material</th>
            <th className="text-right py-1.5 px-2 text-muted-foreground font-medium">Required</th>
            <th className="text-right py-1.5 px-2 text-muted-foreground font-medium">Delivered</th>
            <th className="text-right py-1.5 px-2 text-muted-foreground font-medium">Used</th>
            <th className="text-right py-1.5 px-2 text-muted-foreground font-medium">Remaining</th>
            <th className="text-right py-1.5 pl-2 text-muted-foreground font-medium">Shortfall</th>
          </tr>
        </thead>
        <tbody>
          {items.map(item => {
            const shortfall = Math.max(0, item.boq_allocated_qty - item.delivered_qty);
            const isShort = shortfall > 0;
            const isOver  = item.over_qty > 0;
            return (
              <tr key={item.boq_item_id} className="border-b border-border/40 last:border-0">
                <td className="py-1.5 pr-3">
                  <span className={cn("font-medium", isOver && "text-destructive")}>
                    {item.description}
                  </span>
                  {item.unit && <span className="text-muted-foreground ml-1">({item.unit})</span>}
                </td>
                <td className="text-right py-1.5 px-2 tabular-nums">{fmt(item.boq_allocated_qty)}</td>
                <td className="text-right py-1.5 px-2 tabular-nums">{fmt(item.delivered_qty)}</td>
                <td className="text-right py-1.5 px-2 tabular-nums">{fmt(item.used_qty)}</td>
                <td className={cn("text-right py-1.5 px-2 tabular-nums font-medium",
                  item.remaining_qty < 0 ? "text-destructive" : "text-green-600")}>
                  {fmt(item.remaining_qty)}
                </td>
                <td className={cn("text-right py-1.5 pl-2 tabular-nums font-semibold",
                  isShort ? "text-amber-600" : "text-muted-foreground")}>
                  {isShort ? fmt(shortfall) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Milestone card ────────────────────────────────────────────────────────────

// Use JobCard from @/api/jobCards — shorthand for what we display
type JobCardSummary = Pick<JobCard, "id" | "job_card_number" | "work_description" | "worker_name" | "total_amount" | "status">;

interface MilestoneCardProps {
  projectId:   string;
  siteId:      string;
  lotId:       string;
  master:      StageMaster;
  status:      ProjectStageStatus | null;
  photos:      MilestonePhoto[];
  materials:   MaterialSummaryItem[];
  jobCards:    JobCardSummary[];
  canWrite:    boolean;
  lotSelected: boolean;
  index:       number;
  onRefresh:   () => void;
}

function MilestoneCard({
  projectId, siteId, lotId, master, status, photos, materials, jobCards,
  canWrite, lotSelected, index, onRefresh,
}: MilestoneCardProps) {
  const [expanded,       setExpanded]       = useState(false);
  const [starting,       setStarting]       = useState(false);
  const [showComplete,   setShowComplete]   = useState(false);
  const [showBlock,      setShowBlock]      = useState(false);
  const [showActivity,   setShowActivity]   = useState(false);
  const [activity,       setActivity]       = useState<MilestoneActivityEntry[]>([]);
  const [actLoading,     setActLoading]     = useState(false);
  const [progressBusy,   setProgressBusy]   = useState(false);

  const meta   = STATUS_META[status?.status ?? "NOT_STARTED"];
  const isDone = status?.status === "COMPLETED" || status?.status === "CERTIFIED";
  const isBlocked = status?.status === "BLOCKED";

  const startMilestone = async () => {
    setStarting(true);
    try {
      await stagesApi.upsert(projectId, {
        stage_id: master.id,
        site_id:  siteId || null,
        lot_id:   lotId  || null,
        status:   "IN_PROGRESS",
      });
      onRefresh();
    } catch { /* ignore */ }
    finally { setStarting(false); }
  };

  const handleSetProgress = async (pct: number) => {
    if (!status) return;
    setProgressBusy(true);
    try { await stagesApi.setProgress(projectId, status.id, pct); onRefresh(); }
    catch { /* ignore */ }
    finally { setProgressBusy(false); }
  };

  const handleUnblock = async () => {
    if (!status) return;
    try { await stagesApi.unblock(projectId, status.id); onRefresh(); }
    catch { /* ignore */ }
  };

  const toggleActivity = async () => {
    if (!status) return;
    setShowActivity(p => !p);
    if (!showActivity && activity.length === 0) {
      setActLoading(true);
      try { setActivity(await stagesApi.getActivity(projectId, status.id)); }
      catch { /* silent */ }
      finally { setActLoading(false); }
    }
  };

  const totalLabour = jobCards.reduce((s, j) => s + (j.total_amount || 0), 0);

  return (
    <>
    <div className={cn(
      "rounded-2xl border overflow-hidden transition-colors",
      isDone    ? "border-green-200 bg-green-50/40 dark:border-green-900/50 dark:bg-green-950/10"
      : isBlocked ? "border-destructive/30 bg-destructive/5"
      : status?.status === "IN_PROGRESS" || status?.status === "AWAITING_INSPECTION"
                ? "border-blue-200 bg-blue-50/30 dark:border-blue-900/50 dark:bg-blue-950/10"
      : "border-border bg-card"
    )}>
      {/* Card header — always visible */}
      <button
        className="w-full flex items-center gap-4 px-5 py-4 text-left hover:bg-black/[0.02] dark:hover:bg-white/[0.02] transition-colors"
        onClick={() => setExpanded(p => !p)}
      >
        {/* Sequence badge */}
        <span className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0",
          meta.bg, meta.color
        )}>
          {index + 1}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{master.name}</span>
            <span className={cn("flex items-center gap-1 text-xs font-medium", meta.color)}>
              {meta.icon}
              {meta.label}
            </span>
            {photos.length > 0 && (
              <span className="flex items-center gap-1 text-xs text-muted-foreground bg-muted/60 rounded-full px-2 py-0.5">
                <Camera className="w-3 h-3" />
                {photos.length}
              </span>
            )}
          </div>
          {master.description && (
            <p className="text-xs text-muted-foreground mt-0.5">{master.description}</p>
          )}
          {status?.started_at && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Started {fmtDate(status.started_at)}
              {status.completed_at && ` · Completed ${fmtDate(status.completed_at)}`}
              {status.completed_by_name && ` · by ${status.completed_by_name}`}
            </p>
          )}
          {isBlocked && status?.blocked_reason && (
            <p className="text-xs text-destructive mt-0.5 flex items-center gap-1">
              <Ban className="w-3 h-3 shrink-0" />
              {status.blocked_reason}
            </p>
          )}
          {status && !isDone && !isBlocked && (status.progress_pct ?? 0) > 0 && (
            <div className="mt-1 flex items-center gap-2">
              <div className="h-1 bg-muted rounded-full overflow-hidden flex-1 max-w-[100px]">
                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${status.progress_pct}%` }} />
              </div>
              <span className="text-[10px] text-muted-foreground">{status.progress_pct}%</span>
            </div>
          )}
        </div>

        {expanded ? <ChevronUp className="w-4 h-4 text-muted-foreground shrink-0" />
                  : <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />}
      </button>

      {/* Expanded body */}
      {expanded && (
        <div className="px-5 pb-5 space-y-5 border-t border-border/40 pt-4">

          {/* Action buttons */}
          {canWrite && (
            <div className="flex gap-2 flex-wrap">
              {!status && (
                <Button size="sm" variant="outline" onClick={startMilestone} disabled={starting} className="gap-1.5">
                  <Clock className="w-3.5 h-3.5" />
                  {starting ? "Starting…" : "Mark In Progress"}
                </Button>
              )}
              {status && !isDone && !isBlocked && (
                <Button size="sm" onClick={() => setShowComplete(true)}
                        className="gap-1.5 bg-green-600 hover:bg-green-700 text-white">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Mark Complete
                </Button>
              )}
              {status && status.status !== "AWAITING_INSPECTION" && !isDone && !isBlocked && (
                <Button size="sm" variant="outline"
                  onClick={() => stagesApi.upsert(projectId, {
                    stage_id: master.id, site_id: siteId || null, lot_id: lotId || null,
                    status: "AWAITING_INSPECTION",
                  }).then(onRefresh)}
                  className="gap-1.5"
                >
                  <AlertTriangle className="w-3.5 h-3.5" />
                  Awaiting Inspection
                </Button>
              )}
              {status && !isDone && !isBlocked && (
                <Button size="sm" variant="outline" onClick={() => setShowBlock(true)}
                  className="gap-1.5 text-destructive border-destructive/30 hover:bg-destructive/10">
                  <Ban className="w-3.5 h-3.5" />Block
                </Button>
              )}
              {isBlocked && (
                <Button size="sm" variant="outline" onClick={handleUnblock} className="gap-1.5">
                  <PlayCircle className="w-3.5 h-3.5" />Resume
                </Button>
              )}
              {status && (
                <Button size="sm" variant="ghost" onClick={toggleActivity} className="gap-1.5 text-muted-foreground ml-auto">
                  <History className="w-3.5 h-3.5" />Activity
                </Button>
              )}
            </div>
          )}

          {/* Progress slider (for active/in-progress milestones) */}
          {status && !isDone && canWrite && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Progress</span>
                <span className="font-medium text-foreground">{status.progress_pct ?? 0}%</span>
              </div>
              <input
                type="range" min={0} max={100} step={5}
                value={status.progress_pct ?? 0}
                disabled={progressBusy}
                onChange={e => handleSetProgress(parseInt(e.target.value))}
                className="w-full accent-primary cursor-pointer disabled:opacity-50"
              />
              <div className="flex justify-between text-[10px] text-muted-foreground">
                <span>0%</span><span>50%</span><span>100%</span>
              </div>
            </div>
          )}

          {/* Completion info */}
          {isDone && (status?.completion_notes || status?.completed_by_name) && (
            <div className="bg-green-50/60 dark:bg-green-950/20 border border-green-200/50 rounded-xl px-4 py-3 space-y-1">
              {status.completed_by_name && (
                <p className="text-xs text-green-700 dark:text-green-400">
                  Completed by <strong>{status.completed_by_name}</strong>
                  {status.completed_at && ` on ${fmtDate(status.completed_at)}`}
                </p>
              )}
              {status.completion_notes && (
                <p className="text-sm text-green-800 dark:text-green-300 italic">"{status.completion_notes}"</p>
              )}
            </div>
          )}

          {/* Activity feed */}
          {showActivity && (
            <div className="border border-border rounded-xl overflow-hidden">
              <div className="px-4 py-2.5 bg-muted/30 border-b border-border text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center justify-between">
                Activity
                {actLoading && <RefreshCw className="w-3 h-3 animate-spin" />}
              </div>
              <div className="max-h-52 overflow-y-auto">
                {activity.length === 0 && !actLoading ? (
                  <p className="text-xs text-muted-foreground text-center py-4">No activity recorded yet.</p>
                ) : activity.map((a, i) => (
                  <div key={i} className="flex items-start gap-3 px-4 py-2.5 border-b border-border/40 last:border-0">
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium">{a.description}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {a.actor ?? "System"} · {formatDate(a.timestamp)}
                      </p>
                    </div>
                    {a.url && (
                      <a href={a.url} target="_blank" rel="noopener noreferrer">
                        <img src={a.url} alt="photo" className="w-10 h-10 rounded object-cover border border-border shrink-0" />
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Notes */}
          {status?.notes && (() => {
            const noteText = status.notes
              .split(" | ")
              .filter(s => !s.startsWith("evidence:"))
              .join(" | ");
            return noteText ? (
              <p className="text-sm text-muted-foreground italic bg-muted/40 rounded-lg px-3 py-2">
                {noteText}
              </p>
            ) : null;
          })()}

          {/* Progress photos */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
              <Camera className="w-3.5 h-3.5" />
              Progress Photos
            </h4>
            {status ? (
              <PhotoStrip
                projectId={projectId}
                statusId={status.id}
                photos={photos}
                canWrite={canWrite}
                onRefresh={onRefresh}
              />
            ) : (
              <p className="text-xs text-muted-foreground">Start the milestone to upload photos.</p>
            )}
          </div>

          {/* Material summary — lot-level budget shared across all milestones */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1 flex items-center gap-1.5">
              <Package className="w-3.5 h-3.5" />
              Lot Material Budget
            </h4>
            <p className="text-[10px] text-muted-foreground mb-2">
              All materials allocated to this unit — shared across all milestones.
            </p>
            <MaterialSummaryTable items={materials} lotSelected={lotSelected} />
          </div>

          {/* Labour */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
              <HardHat className="w-3.5 h-3.5" />
              Labour
              {jobCards.length > 0 && (
                <span className="ml-1 font-semibold text-foreground">
                  R{totalLabour.toLocaleString("en-ZA", { minimumFractionDigits: 2 })}
                </span>
              )}
            </h4>
            {jobCards.length === 0 ? (
              <p className="text-xs text-muted-foreground">No job cards linked to this milestone.</p>
            ) : (
              <div className="space-y-1">
                {jobCards.map(jc => (
                  <div key={jc.id}
                       className="flex items-center justify-between text-xs py-1.5 border-b border-border/40 last:border-0">
                    <div className="min-w-0">
                      <span className="font-medium">{jc.job_card_number}</span>
                      <span className="text-muted-foreground ml-2 truncate">{jc.work_description}</span>
                      {jc.worker_name && (
                        <span className="text-muted-foreground ml-1">· {jc.worker_name}</span>
                      )}
                    </div>
                    <div className="text-right shrink-0 ml-2">
                      <span className="font-semibold">
                        R{jc.total_amount.toLocaleString("en-ZA", { minimumFractionDigits: 2 })}
                      </span>
                      <span className={cn("ml-2 px-1.5 py-0.5 rounded text-[10px] font-medium",
                        jc.status === "PAID" ? "bg-green-100 text-green-700"
                          : jc.status === "REJECTED" ? "bg-red-100 text-red-700"
                          : "bg-gray-100 text-gray-600")}>
                        {jc.status.replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>

    {/* Completion modal */}
    {showComplete && status && (
      <CompletionModal
        projectId={projectId}
        statusId={status.id}
        stageName={master.name}
        hasPhotos={photos.length > 0}
        onClose={() => setShowComplete(false)}
        onDone={() => { setShowComplete(false); onRefresh(); }}
      />
    )}

    {/* Block modal */}
    {showBlock && status && (
      <BlockModal
        projectId={projectId}
        statusId={status.id}
        stageName={master.name}
        onClose={() => setShowBlock(false)}
        onDone={() => { setShowBlock(false); onRefresh(); }}
      />
    )}
    </>
  );
}

// ── Completion Modal ──────────────────────────────────────────────────────────

function CompletionModal({
  projectId, statusId, stageName, hasPhotos, onClose, onDone,
}: {
  projectId: string; statusId: string; stageName: string;
  hasPhotos: boolean; onClose: () => void; onDone: () => void;
}) {
  const [notes,   setNotes]   = useState("");
  const [name,    setName]    = useState("");
  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState("");

  const submit = async () => {
    setSaving(true); setError("");
    try {
      await stagesApi.complete(projectId, statusId, {
        completion_notes:  notes || undefined,
        completed_by_name: name  || undefined,
      });
      onDone();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Failed to complete milestone.");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base">Complete Milestone</h3>
          <button onClick={onClose}><XIcon className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <p className="text-sm text-muted-foreground">{stageName}</p>

        {!hasPhotos && (
          <div className="flex items-start gap-2 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/50 rounded-xl px-3 py-2.5">
            <Camera className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700 dark:text-amber-400">
              No progress photos uploaded. Consider adding a photo before marking complete.
            </p>
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Completed by</label>
            <input type="text" value={name} onChange={e => setName(e.target.value)} autoFocus
              placeholder="Your name or team"
              className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Completion notes (optional)</label>
            <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3}
              placeholder="Any notes about the completion…"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none" />
          </div>
        </div>

        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

        <div className="flex gap-2 pt-1">
          <Button onClick={submit} disabled={saving} className="flex-1 bg-green-600 hover:bg-green-700">
            {saving ? "Saving…" : "Mark Complete"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Block Modal ───────────────────────────────────────────────────────────────

function BlockModal({
  projectId, statusId, stageName, onClose, onDone,
}: {
  projectId: string; statusId: string; stageName: string;
  onClose: () => void; onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState("");

  const submit = async () => {
    if (!reason.trim()) { setError("A reason is required."); return; }
    setSaving(true); setError("");
    try {
      await stagesApi.block(projectId, statusId, reason.trim());
      onDone();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Failed to block milestone.");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl w-full max-w-sm p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-base flex items-center gap-1.5">
            <Ban className="w-4 h-4 text-destructive" />Block Milestone
          </h3>
          <button onClick={onClose}><XIcon className="w-4 h-4 text-muted-foreground" /></button>
        </div>
        <p className="text-sm text-muted-foreground">{stageName}</p>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Reason for blocking *</label>
          <textarea value={reason} onChange={e => setReason(e.target.value)} rows={3} autoFocus
            placeholder="e.g. Waiting for material delivery, Inspection pending…"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none" />
        </div>
        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex gap-2 pt-1">
          <Button onClick={submit} disabled={saving} className="flex-1 bg-destructive hover:bg-destructive/90">
            {saving ? "Blocking…" : "Mark as Blocked"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MilestonesPage() {
  const canWrite = localStorage.getItem(ROLE_KEY) !== "READ_ONLY";

  const [projects,  setProjects]  = useState<Project[]>([]);
  const [sites,     setSites]     = useState<Site[]>([]);
  const [lots,      setLots]      = useState<Lot[]>([]);
  const [masters,   setMasters]   = useState<StageMaster[]>([]);

  const [projectId, setProjectId] = useState("");
  const [siteId,    setSiteId]    = useState("");
  const [lotId,     setLotId]     = useState("");

  const [statuses,  setStatuses]  = useState<ProjectStageStatus[]>([]);
  const [photos,    setPhotos]    = useState<Record<string, MilestonePhoto[]>>({});
  const [materials, setMaterials] = useState<MaterialSummaryItem[]>([]);
  const [jobCards,  setJobCards]  = useState<Record<string, JobCardSummary[]>>({});
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState("");

  // Load projects + stage masters once
  useEffect(() => {
    projectsApi.list(1, 100, "ACTIVE").then(r => setProjects(r.items)).catch(() => {});
    stagesApi.listMasters().then(setMasters).catch(() => {});
  }, []);

  // Load sites when project changes — auto-select single site for freestanding-lot projects
  useEffect(() => {
    if (!projectId) { setSites([]); setLots([]); return; }
    sitesApi.list(projectId).then(s => {
      setSites(s);
      // Freestanding lot support: if only one site, silently select it
      setSiteId(s.length >= 1 ? s[0].id : "");
    }).catch(() => {});
    lotsApi.list(projectId).then(l => setLots(l)).catch(() => {});
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load lots when site changes
  useEffect(() => {
    if (!siteId) { setLotId(""); return; }
    const siteLots = lots.filter(l => !l.site_id || l.site_id === siteId);
    setLotId(siteLots[0]?.id ?? "");
  }, [siteId, lots]);

  const loadData = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const params: Record<string, string> = {};
      if (siteId) params.site_id = siteId;
      if (lotId)  params.lot_id  = lotId;

      const sts = await stagesApi.listProjectStatuses(projectId, params);
      setStatuses(sts);

      // Load photos for every status that exists
      const photoMap: Record<string, MilestonePhoto[]> = {};
      await Promise.all(sts.map(async s => {
        try {
          photoMap[s.id] = await stagesApi.listPhotos(projectId, s.id);
        } catch { photoMap[s.id] = []; }
      }));
      setPhotos(photoMap);

      // Material summary (needs siteId + lotId)
      if (siteId && lotId) {
        try {
          const mat = await siteDashboardApi.getMaterialSummary(siteId, lotId);
          setMaterials(mat);
        } catch { setMaterials([]); }
      } else {
        setMaterials([]);
      }

      // Job cards per stage — grouped by stage_id (now included in JobCard schema)
      try {
        const jcs = await jobCardsApi.list(
          projectId,
          undefined,               // all statuses
          lotId   || undefined,
          siteId  || undefined,
        );
        const grouped: Record<string, JobCardSummary[]> = {};
        for (const jc of jcs) {
          if (jc.stage_id) {
            if (!grouped[jc.stage_id]) grouped[jc.stage_id] = [];
            grouped[jc.stage_id].push(jc);
          }
        }
        setJobCards(grouped);
      } catch { setJobCards({}); }
    } catch {
      setError("Failed to load milestones.");
    } finally {
      setLoading(false);
    }
  }, [projectId, siteId, lotId]);

  useEffect(() => { loadData(); }, [loadData]);

  // Merge masters with statuses to get full milestone list
  const milestones = masters.map(m => ({
    master: m,
    status: statuses.find(s => s.stage_id === m.id) ?? null,
  }));

  const done    = milestones.filter(m => m.status?.status === "COMPLETED" || m.status?.status === "CERTIFIED").length;
  const active  = milestones.filter(m => m.status?.status === "IN_PROGRESS" || m.status?.status === "AWAITING_INSPECTION").length;
  const pending = milestones.filter(m => !m.status || m.status.status === "NOT_STARTED").length;

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Milestones"
        description="Track construction progress, upload photos, and monitor materials per lot."
      />

      {/* Selectors — hide site when project has only one (freestanding lots) */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={projectId}
          onChange={e => setProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[180px]"
        >
          <option value="">— Select project —</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        {sites.length > 1 && (
          <select
            value={siteId}
            onChange={e => setSiteId(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[160px]"
          >
            <option value="">— Site / Block —</option>
            {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        )}
        <select
          value={lotId}
          onChange={e => setLotId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[160px]"
          disabled={lots.length === 0}
        >
          <option value="">— Select unit / lot —</option>
          {lots
            .filter(l => !siteId || !l.site_id || l.site_id === siteId)
            .sort((a, b) => a.lot_number.localeCompare(b.lot_number, undefined, { numeric: true, sensitivity: "base" }))
            .map(l => (
              <option key={l.id} value={l.id}>
                {l.lot_number}{l.unit_type ? ` · ${l.unit_type}` : ""}
              </option>
            ))
          }
        </select>
        <button
          onClick={loadData}
          disabled={loading}
          className="h-9 w-9 flex items-center justify-center rounded-md border border-input bg-background hover:bg-muted text-muted-foreground disabled:opacity-50 transition-colors"
          title="Refresh"
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {error && (
        <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>
      )}

      {/* Summary KPIs */}
      {!loading && milestones.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Completed", value: done,    color: "text-green-600" },
            { label: "Active",    value: active,  color: "text-blue-600"  },
            { label: "Pending",   value: pending, color: "text-muted-foreground" },
          ].map(k => (
            <div key={k.label} className="bg-card border border-border rounded-xl p-3 text-center">
              <p className={cn("text-2xl font-bold", k.color)}>{k.value}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{k.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Progress bar */}
      {!loading && milestones.length > 0 && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Overall progress</span>
            <span>{done} / {milestones.length} milestones</span>
          </div>
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-green-500 rounded-full transition-all duration-500"
              style={{ width: `${milestones.length > 0 ? (done / milestones.length) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Milestone cards */}
      {loading ? (
        <div className="space-y-3">
          {[1,2,3,4].map(i => <Skeleton key={i} className="h-20 rounded-2xl" />)}
        </div>
      ) : !projectId ? (
        <div className="bg-card border border-border rounded-2xl p-12 text-center text-sm text-muted-foreground">
          Select a project to view milestones.
        </div>
      ) : milestones.length === 0 ? (
        <div className="bg-card border border-border rounded-2xl p-12 text-center space-y-3">
          <p className="text-sm text-muted-foreground">No milestone stages defined yet.</p>
          {canWrite && (
            <Button
              size="sm" variant="outline"
              onClick={() => import("@/api/client").then(m =>
                m.default.post(`/stages/seed`).then(() => stagesApi.listMasters().then(setMasters))
              )}
            >
              <Plus className="w-4 h-4 mr-1.5" />
              Seed default stages
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {milestones.map((m, i) => (
            <MilestoneCard
              key={m.master.id}
              projectId={projectId}
              siteId={siteId}
              lotId={lotId}
              master={m.master}
              status={m.status}
              photos={m.status ? (photos[m.status.id] ?? []) : []}
              materials={materials}
              jobCards={jobCards[m.master.id] ?? []}
              canWrite={canWrite}
              lotSelected={!!lotId}
              index={i}
              onRefresh={loadData}
            />
          ))}
        </div>
      )}
    </div>
  );
}
