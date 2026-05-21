/**
 * Apply BOQ Template — Phase 3H.
 *
 * 3-step modal: configure → preview → result
 *
 * Modes:
 *   CREATE — only apply to lots that have no existing BOQ (safe default)
 *   SAFE   — skip lots where boq_customized_at IS NOT NULL (user manually edited)
 *   FORCE  — overwrite all lots regardless of customization state
 *
 * All three modes respect freestanding lots (site_id=NULL).
 * No silent changes — user sees exactly which lots will change vs be skipped.
 */
import { useEffect, useState } from "react";
import {
  X, Check, FileSpreadsheet, AlertTriangle,
  RefreshCw, ChevronRight, Flag, ShieldCheck, Zap, Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  boqApi,
  type BOQTemplate,
  type BOQTemplatePreview,
  type BOQTemplatePreviewLot,
  type BOQCloneResult,
  type BOQApplyMode,
} from "@/api/boq";
import client from "@/api/client";
import { cn } from "@/lib/utils";

interface Lot {
  id: string;
  lot_number: string;
  unit_type: string | null;
  site_id: string | null;
  boq_template_id: string | null;
  boq_customized_at?: string | null;
}

interface Props {
  projectId: string;
  onClose:   () => void;
  onApplied: (result: BOQCloneResult) => void;
}

type Step = "configure" | "preview" | "result";

// ── Mode descriptions ─────────────────────────────────────────────────────────

const MODE_INFO: Record<BOQApplyMode, { icon: React.ReactNode; label: string; desc: string; warnColor: boolean }> = {
  CREATE: {
    icon: <Plus className="w-3.5 h-3.5 text-primary" />,
    label: "New lots only",
    desc: "Applies only to lots that have no existing BOQ. Lots with existing BOQs (including customized ones) are skipped.",
    warnColor: false,
  },
  SAFE: {
    icon: <ShieldCheck className="w-3.5 h-3.5 text-green-600" />,
    label: "Safe — preserve customized lots",
    desc: "Updates lots with existing generated BOQs, but skips lots where the BOQ was manually edited. Recommended for most updates.",
    warnColor: false,
  },
  FORCE: {
    icon: <Zap className="w-3.5 h-3.5 text-amber-600" />,
    label: "Force — overwrite all lots",
    desc: "Replaces the BOQ on ALL selected lots, including those with manual edits. Use when the template change is authoritative.",
    warnColor: true,
  },
};

// ── Step 1: Configure ─────────────────────────────────────────────────────────

function StepConfigure({
  projectId,
  onNext,
  onClose,
}: {
  projectId: string;
  onNext: (templateId: string, lotIds: string[], mode: BOQApplyMode, genMilestones: boolean) => void;
  onClose: () => void;
}) {
  const [templates,        setTemplates]        = useState<BOQTemplate[]>([]);
  const [lots,             setLots]             = useState<Lot[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [selectedLotIds,   setSelectedLotIds]   = useState<Set<string>>(new Set());
  const [mode,             setMode]             = useState<BOQApplyMode>("CREATE");
  const [genMilestones,    setGenMilestones]    = useState(true);
  const [loading,          setLoading]          = useState(true);
  const [error,            setError]            = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      boqApi.listTemplates(),
      client.get<{ data: Lot[] }>(`/projects/${projectId}/lots/`),
    ]).then(([tmpl, lotsRes]) => {
      setTemplates(tmpl);
      if (tmpl.length) setSelectedTemplate(tmpl[0].id);
      const ls = lotsRes.data.data || [];
      setLots(ls);
      setSelectedLotIds(new Set(ls.map(l => l.id)));
    }).catch(() => setError("Failed to load templates or lots."))
      .finally(() => setLoading(false));
  }, [projectId]);

  const toggleLot = (id: string) =>
    setSelectedLotIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const toggleAll = () =>
    setSelectedLotIds(selectedLotIds.size === lots.length ? new Set() : new Set(lots.map(l => l.id)));

  // Count stats for selected lots
  const selectedLots = lots.filter(l => selectedLotIds.has(l.id));
  const withBOQ      = selectedLots.filter(l => l.boq_template_id).length;
  const customized   = selectedLots.filter(l => l.boq_customized_at).length;

  if (loading) return (
    <div className="p-5 space-y-3">
      {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 rounded-lg" />)}
    </div>
  );

  if (templates.length === 0) return (
    <div className="p-8 text-center space-y-3">
      <FileSpreadsheet className="w-8 h-8 text-muted-foreground mx-auto" />
      <p className="text-sm text-muted-foreground">No BOQ templates found.</p>
      <p className="text-xs text-muted-foreground">Build a BOQ in the BOQ page, then mark it as a template.</p>
      <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
    </div>
  );

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">
      {error && <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

      {/* Template picker */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Template</label>
        <select value={selectedTemplate} onChange={e => setSelectedTemplate(e.target.value)}
          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
          {templates.map(t => (
            <option key={t.id} value={t.id}>{t.template_name || t.version_name}</option>
          ))}
        </select>
      </div>

      {/* Mode selector */}
      <div className="space-y-2">
        <p className="text-sm font-medium">Apply mode</p>
        {(Object.entries(MODE_INFO) as [BOQApplyMode, typeof MODE_INFO[BOQApplyMode]][]).map(([m, info]) => (
          <label key={m} className={cn(
            "flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors",
            mode === m
              ? info.warnColor ? "border-amber-400 bg-amber-50/60 dark:bg-amber-950/20"
                               : "border-primary bg-primary/5"
              : "border-border hover:bg-muted/30"
          )}>
            <input type="radio" value={m} checked={mode === m} onChange={() => setMode(m)} className="mt-0.5" />
            <div>
              <div className="flex items-center gap-1.5 text-sm font-medium">
                {info.icon}{info.label}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">{info.desc}</p>
            </div>
          </label>
        ))}
      </div>

      {/* Lot selection */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium">
            Lots ({selectedLotIds.size} of {lots.length} selected)
          </label>
          <button type="button" onClick={toggleAll} className="text-xs text-primary hover:underline">
            {selectedLotIds.size === lots.length ? "Deselect all" : "Select all"}
          </button>
        </div>
        <div className="text-xs text-muted-foreground flex gap-3">
          {withBOQ > 0 && <span className="text-amber-600">{withBOQ} with existing BOQ</span>}
          {customized > 0 && <span className="text-amber-700 font-medium">· {customized} customized</span>}
        </div>
        <div className="border border-border rounded-lg overflow-hidden max-h-52 overflow-y-auto">
          {lots.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">No lots in this project.</p>
          ) : lots
            .sort((a, b) => a.lot_number.localeCompare(b.lot_number, undefined, { numeric: true, sensitivity: "base" }))
            .map((lot, i) => (
              <label key={lot.id} className={cn(
                "flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-muted/40 transition-colors",
                i < lots.length - 1 && "border-b border-border/50",
                selectedLotIds.has(lot.id) && "bg-primary/5",
              )}>
                <input type="checkbox" checked={selectedLotIds.has(lot.id)} onChange={() => toggleLot(lot.id)} className="rounded" />
                <span className="text-sm flex-1 min-w-0">
                  <span className="font-medium font-mono">{lot.lot_number}</span>
                  {lot.unit_type && <span className="text-muted-foreground ml-1.5">· {lot.unit_type}</span>}
                  {!lot.site_id && <span className="text-muted-foreground ml-1 text-xs">(freestanding)</span>}
                </span>
                <div className="flex gap-1 shrink-0">
                  {lot.boq_customized_at && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">customized</span>
                  )}
                  {lot.boq_template_id && !lot.boq_customized_at && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">has BOQ</span>
                  )}
                </div>
              </label>
            ))
          }
        </div>
      </div>

      {/* Milestones option */}
      <label className="flex items-start gap-2.5 cursor-pointer">
        <input type="checkbox" checked={genMilestones} onChange={e => setGenMilestones(e.target.checked)} className="mt-0.5 rounded" />
        <div>
          <p className="text-sm font-medium flex items-center gap-1.5">
            <Flag className="w-3.5 h-3.5 text-primary" />Generate milestones from template stages
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Seeds "Not started" milestone records. Existing milestones are kept.
          </p>
        </div>
      </label>

      <div className="flex gap-2 pt-1">
        <Button
          onClick={() => onNext(selectedTemplate, Array.from(selectedLotIds), mode, genMilestones)}
          disabled={!selectedTemplate || selectedLotIds.size === 0}
          className="flex-1 gap-1.5"
        >
          Preview changes <ChevronRight className="w-4 h-4" />
        </Button>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
      </div>
    </div>
  );
}

// ── Step 2: Preview ───────────────────────────────────────────────────────────

function LotPreviewRow({ lot, isLast }: { lot: BOQTemplatePreviewLot; isLast: boolean }) {
  const actionLabel = { create: "Create", overwrite: "Update", skip: "Skip" }[lot.action];
  const actionColor = {
    create:    "bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-400",
    overwrite: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
    skip:      "bg-muted text-muted-foreground",
  }[lot.action];

  return (
    <div className={cn(
      "flex items-center justify-between px-3 py-2.5",
      !isLast && "border-b border-border/50",
      lot.action === "skip" && "bg-muted/20",
    )}>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium font-mono">{lot.lot_number}</span>
          {lot.unit_type && <span className="text-xs text-muted-foreground">· {lot.unit_type}</span>}
          {lot.is_freestanding && <span className="text-xs text-muted-foreground italic">(freestanding)</span>}
          {lot.is_customized && lot.action !== "skip" && (
            <span className="text-[10px] px-1 py-0.5 rounded bg-amber-100 text-amber-700">customized</span>
          )}
        </div>
        {lot.skip_reason && (
          <p className="text-xs text-muted-foreground mt-0.5">{lot.skip_reason}</p>
        )}
        {lot.action !== "skip" && (
          <p className="text-xs text-muted-foreground mt-0.5">
            {lot.new_item_count} items
            {lot.new_milestone_count > 0 && ` · ${lot.new_milestone_count} milestone${lot.new_milestone_count !== 1 ? "s" : ""}`}
            {lot.action === "overwrite" && lot.existing_item_count > 0 && ` · replaces ${lot.existing_item_count} existing`}
          </p>
        )}
      </div>
      <span className={cn("text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ml-2", actionColor)}>
        {actionLabel}
      </span>
    </div>
  );
}

function StepPreview({
  preview,
  onApply,
  onBack,
  applying,
}: {
  preview:  BOQTemplatePreview;
  onApply:  () => void;
  onBack:   () => void;
  applying: boolean;
}) {
  const toApply = preview.lots.filter(l => l.action !== "skip");
  const skipped = preview.lots.filter(l => l.action === "skip");

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-4">
      {/* Summary */}
      <div className="bg-muted/40 rounded-xl p-4 space-y-2">
        <p className="text-sm font-semibold">{preview.template_name}</p>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-card rounded-lg py-2">
            <p className="text-xl font-bold">{preview.template_item_count}</p>
            <p className="text-[10px] text-muted-foreground">Items/lot</p>
          </div>
          <div className="bg-card rounded-lg py-2">
            <p className="text-xl font-bold">{preview.template_stage_count}</p>
            <p className="text-[10px] text-muted-foreground">Milestones</p>
          </div>
          <div className={cn("rounded-lg py-2", toApply.length > 0 ? "bg-green-50 dark:bg-green-950/20" : "bg-muted/40")}>
            <p className={cn("text-xl font-bold", toApply.length > 0 ? "text-green-600" : "text-muted-foreground")}>
              {preview.lots_to_apply}
            </p>
            <p className="text-[10px] text-muted-foreground">Will apply</p>
          </div>
        </div>
        {skipped.length > 0 && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground bg-muted/60 rounded-lg px-3 py-2">
            <AlertTriangle className="w-3 h-3 shrink-0" />
            {skipped.length} lot{skipped.length !== 1 ? "s" : ""} will be skipped
            {preview.mode === "SAFE" && " — customized (use FORCE to override)"}
            {preview.mode === "CREATE" && " — already have BOQ"}
          </div>
        )}
        {toApply.length === 0 && (
          <p className="text-xs text-muted-foreground bg-muted rounded-lg px-3 py-2">
            No lots to update with the current mode. Go back and select SAFE or FORCE.
          </p>
        )}
      </div>

      {/* Per-lot breakdown */}
      <div className="border border-border rounded-xl overflow-hidden max-h-64 overflow-y-auto">
        <div className="px-3 py-2 bg-muted/30 border-b border-border">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Per-lot detail</p>
        </div>
        {preview.lots.map((lot, i) => (
          <LotPreviewRow key={lot.lot_id} lot={lot} isLast={i === preview.lots.length - 1} />
        ))}
      </div>

      <div className="flex gap-2 pt-1">
        <Button onClick={onApply} disabled={applying || toApply.length === 0} className="flex-1 gap-1.5">
          {applying ? (
            <><RefreshCw className="w-4 h-4 animate-spin" />Applying…</>
          ) : (
            <><Check className="w-4 h-4" />Apply to {preview.lots_to_apply} lot{preview.lots_to_apply !== 1 ? "s" : ""}</>
          )}
        </Button>
        <Button variant="outline" onClick={onBack} disabled={applying}>Back</Button>
      </div>
    </div>
  );
}

// ── Step 3: Result ────────────────────────────────────────────────────────────

function StepResult({ result, onClose }: { result: BOQCloneResult; onClose: () => void }) {
  return (
    <div className="p-8 text-center space-y-4">
      <Check className="w-12 h-12 text-green-500 mx-auto" />
      <div>
        <p className="font-semibold text-lg">Template applied!</p>
        <p className="text-sm text-muted-foreground mt-1">
          Mode: <span className="font-medium">{result.mode}</span>
        </p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        {[
          { label: "Lots updated",     value: result.created_count },
          { label: "Milestones seeded",value: result.milestones_created },
          { label: "Items replaced",   value: result.deactivated_count },
          { label: "Lots skipped",     value: result.skipped_count || 0 },
        ].map(k => (
          <div key={k.label} className="bg-muted/40 rounded-xl py-3">
            <p className="text-2xl font-bold">{k.value}</p>
            <p className="text-[11px] text-muted-foreground mt-0.5">{k.label}</p>
          </div>
        ))}
      </div>
      {result.freestanding_master && (
        <p className="text-xs text-muted-foreground bg-muted/40 rounded-lg px-3 py-2">
          Project-level master created for freestanding lots.
        </p>
      )}
      <Button onClick={onClose} className="w-full mt-2">Done</Button>
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────

export function ApplyBOQTemplateModal({ projectId, onClose, onApplied }: Props) {
  type StepT = "configure" | "preview" | "result";
  const [step,     setStep]     = useState<StepT>("configure");
  const [tmplId,   setTmplId]   = useState("");
  const [lotIds,   setLotIds]   = useState<string[]>([]);
  const [mode,     setMode]     = useState<BOQApplyMode>("CREATE");
  const [genMs,    setGenMs]    = useState(true);
  const [preview,  setPreview]  = useState<BOQTemplatePreview | null>(null);
  const [result,   setResult]   = useState<BOQCloneResult | null>(null);
  const [applying, setApplying] = useState(false);
  const [error,    setError]    = useState("");

  const handlePreview = async (tId: string, ids: string[], m: BOQApplyMode, gm: boolean) => {
    setTmplId(tId); setLotIds(ids); setMode(m); setGenMs(gm); setError("");
    try {
      const p = await boqApi.previewClone({ template_boq_id: tId, project_id: projectId, lot_ids: ids, mode: m });
      setPreview(p);
      setStep("preview");
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Preview failed.");
    }
  };

  const handleApply = async () => {
    if (!preview) return;
    setApplying(true); setError("");
    try {
      const r = await boqApi.cloneToLots({
        template_boq_id:    tmplId,
        project_id:         projectId,
        lot_ids:            lotIds,
        mode,
        generate_milestones: genMs,
      });
      setResult(r);
      setStep("result");
      onApplied(r);
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Apply failed. Check logs.");
    } finally { setApplying(false); }
  };

  const titles: Record<StepT, string> = {
    configure: "Apply BOQ Template",
    preview:   "Preview Changes",
    result:    "",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-t-2xl sm:rounded-2xl w-full sm:max-w-lg max-h-[92vh] flex flex-col">
        {titles[step] && (
          <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border shrink-0">
            <h2 className="text-base font-semibold">{titles[step]}</h2>
            <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
          </div>
        )}
        {error && (
          <div className="mx-5 mt-3 bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2 text-sm text-destructive shrink-0">
            {error}
          </div>
        )}
        {step === "configure" && <StepConfigure projectId={projectId} onNext={handlePreview} onClose={onClose} />}
        {step === "preview"   && preview && <StepPreview preview={preview} onApply={handleApply} onBack={() => setStep("configure")} applying={applying} />}
        {step === "result"    && result  && <StepResult result={result} onClose={onClose} />}
      </div>
    </div>
  );
}
