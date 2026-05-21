/**
 * BulkPropagateModal — Phase 3D.3
 *
 * Propagates a LotType's default BOQ template to all linked lots.
 *
 * Steps:
 *   configure → preview → result
 *
 * Modes:
 *   SAFE  — skip lots where the BOQ was manually edited (boq_customized_at set)
 *   FORCE — overwrite all lots regardless of customization
 *
 * The user sees exactly which lots will be updated and which will be skipped
 * before confirming.  No silent overwrites.
 */
import { useState } from "react";
import {
  X, Check, AlertTriangle, RefreshCw, ChevronRight, Flag,
  Layers, ShieldCheck, Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  lotTypesApi,
  type LotType,
  type PropagateMode,
  type PropagatePreview,
  type PropagateResult,
} from "@/api/lotTypes";
import { cn } from "@/lib/utils";

interface Props {
  lotType:  LotType;
  onClose:  () => void;
  onDone:   (result: PropagateResult) => void;
}

type Step = "configure" | "preview" | "result";

// ── Step 1: Configure ─────────────────────────────────────────────────────────

function StepConfigure({
  lotType,
  onNext,
  onClose,
}: {
  lotType:  LotType;
  onNext:   (mode: PropagateMode, genMilestones: boolean) => void;
  onClose:  () => void;
}) {
  const [mode,          setMode]         = useState<PropagateMode>("SAFE");
  const [genMilestones, setGenMilestones] = useState(true);

  if (!lotType.default_template_id) {
    return (
      <div className="p-8 text-center space-y-3">
        <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto" />
        <p className="font-semibold">No template set</p>
        <p className="text-sm text-muted-foreground">
          Set a default BOQ template for "{lotType.name}" before propagating.
        </p>
        <Button variant="outline" onClick={onClose}>Close</Button>
      </div>
    );
  }

  return (
    <div className="p-5 space-y-5">
      {/* Summary */}
      <div className="bg-muted/40 rounded-xl p-4 space-y-1">
        <p className="text-sm font-semibold">{lotType.name}</p>
        <p className="text-xs text-muted-foreground flex items-center gap-1">
          <Flag className="w-3 h-3" />
          {lotType.lot_count} lot{lotType.lot_count !== 1 ? "s" : ""} linked
        </p>
        {lotType.default_template_name && (
          <p className="text-xs text-muted-foreground">
            Template: <span className="font-medium text-foreground">{lotType.default_template_name}</span>
          </p>
        )}
      </div>

      {/* Mode selector */}
      <div className="space-y-2">
        <p className="text-sm font-medium">Propagation mode</p>

        {/* SAFE */}
        <label className={cn(
          "flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors",
          mode === "SAFE"
            ? "border-primary bg-primary/5"
            : "border-border hover:bg-muted/30"
        )}>
          <input type="radio" value="SAFE" checked={mode === "SAFE"}
            onChange={() => setMode("SAFE")} className="mt-0.5" />
          <div>
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-green-600" />
              <span className="text-sm font-medium">Safe — preserve customized lots</span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Skips lots where the BOQ was manually edited after the last propagation.
              Recommended for most updates.
            </p>
          </div>
        </label>

        {/* FORCE */}
        <label className={cn(
          "flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors",
          mode === "FORCE"
            ? "border-amber-500 bg-amber-50/60 dark:bg-amber-950/20"
            : "border-border hover:bg-muted/30"
        )}>
          <input type="radio" value="FORCE" checked={mode === "FORCE"}
            onChange={() => setMode("FORCE")} className="mt-0.5" />
          <div>
            <div className="flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-amber-600" />
              <span className="text-sm font-medium">Force — overwrite all lots</span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Replaces the BOQ on ALL linked lots, including those with manual edits.
              Use when the template change is authoritative.
            </p>
          </div>
        </label>
      </div>

      {/* Options */}
      <label className="flex items-start gap-2.5 cursor-pointer">
        <input type="checkbox" checked={genMilestones}
          onChange={e => setGenMilestones(e.target.checked)} className="mt-0.5 rounded" />
        <div>
          <p className="text-sm font-medium flex items-center gap-1.5">
            <Flag className="w-3.5 h-3.5 text-primary" />
            Generate missing milestones
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Creates "Not started" milestone records for stages in the template.
            Existing milestones are kept.
          </p>
        </div>
      </label>

      <div className="flex gap-2 pt-1">
        <Button onClick={() => onNext(mode, genMilestones)} className="flex-1 gap-1.5">
          Preview changes
          <ChevronRight className="w-4 h-4" />
        </Button>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
      </div>
    </div>
  );
}

// ── Step 2: Preview ───────────────────────────────────────────────────────────

function StepPreview({
  preview,
  mode,
  onApply,
  onBack,
  applying,
}: {
  preview:  PropagatePreview;
  mode:     PropagateMode;
  onApply:  () => void;
  onBack:   () => void;
  applying: boolean;
}) {
  const propagate = preview.lots.filter(l => l.action === "propagate");
  const skipped   = preview.lots.filter(l => l.action === "skip");

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-4">
      {/* Summary */}
      <div className="bg-muted/40 rounded-xl p-4 space-y-2">
        <p className="text-sm font-semibold">{preview.template_name ?? "Template"}</p>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-card rounded-lg py-2">
            <p className="text-xl font-bold">{preview.items_per_lot}</p>
            <p className="text-[10px] text-muted-foreground">Items/lot</p>
          </div>
          <div className="bg-card rounded-lg py-2">
            <p className="text-xl font-bold">{preview.stages_per_lot}</p>
            <p className="text-[10px] text-muted-foreground">Milestones</p>
          </div>
          <div className="bg-card rounded-lg py-2">
            <p className="text-xl font-bold text-green-600">{preview.lots_to_propagate}</p>
            <p className="text-[10px] text-muted-foreground">Will update</p>
          </div>
        </div>
        {preview.lots_skipped > 0 && (
          <div className="flex items-center gap-2 text-xs text-amber-600 bg-amber-50 dark:bg-amber-950/20 rounded-lg px-3 py-2">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            {preview.lots_skipped} customized lot{preview.lots_skipped !== 1 ? "s" : ""} will be skipped ({mode === "SAFE" ? "use FORCE to override" : "—"})
          </div>
        )}
        {preview.lots_to_propagate === 0 && (
          <div className="text-xs text-muted-foreground bg-muted rounded-lg px-3 py-2">
            No lots to update. Go back and switch to FORCE mode if needed.
          </div>
        )}
      </div>

      {/* Per-lot list */}
      <div className="border border-border rounded-xl overflow-hidden max-h-64 overflow-y-auto">
        <div className="px-3 py-2 bg-muted/30 border-b border-border">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Per-lot detail
          </p>
        </div>
        {preview.lots.map((lot, i) => (
          <div key={lot.lot_id}
            className={cn(
              "flex items-center justify-between px-3 py-2.5",
              i < preview.lots.length - 1 && "border-b border-border/50",
              lot.action === "skip" && "bg-muted/20",
            )}>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium font-mono">{lot.lot_number}</span>
                {lot.unit_type && <span className="text-xs text-muted-foreground">· {lot.unit_type}</span>}
                {!lot.site_id && <span className="text-xs text-muted-foreground">(freestanding)</span>}
              </div>
            </div>
            <span className={cn(
              "text-xs px-1.5 py-0.5 rounded font-medium shrink-0",
              lot.action === "propagate"
                ? "bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-400"
                : "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
            )}>
              {lot.action === "propagate" ? "Update" : "Skip"}
            </span>
          </div>
        ))}
      </div>

      <div className="flex gap-2 pt-1">
        <Button
          onClick={onApply}
          disabled={applying || preview.lots_to_propagate === 0}
          className="flex-1 gap-1.5"
        >
          {applying ? (
            <><RefreshCw className="w-4 h-4 animate-spin" />Propagating…</>
          ) : (
            <><Check className="w-4 h-4" />Apply to {preview.lots_to_propagate} lot{preview.lots_to_propagate !== 1 ? "s" : ""}</>
          )}
        </Button>
        <Button variant="outline" onClick={onBack} disabled={applying}>Back</Button>
      </div>
    </div>
  );
}

// ── Step 3: Result ────────────────────────────────────────────────────────────

function StepResult({ result, onClose }: { result: PropagateResult; onClose: () => void }) {
  return (
    <div className="p-8 text-center space-y-4">
      <Check className="w-12 h-12 text-green-500 mx-auto" />
      <div>
        <p className="font-semibold text-lg">Propagation complete</p>
        <p className="text-sm text-muted-foreground mt-1">{result.message}</p>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Lots updated",       value: result.propagated        },
          { label: "Milestones seeded",  value: result.milestones_created },
          { label: "Lots skipped",       value: result.skipped           },
        ].map(k => (
          <div key={k.label} className="bg-muted/40 rounded-xl py-3">
            <p className="text-2xl font-bold">{k.value}</p>
            <p className="text-[11px] text-muted-foreground mt-0.5">{k.label}</p>
          </div>
        ))}
      </div>
      <Button onClick={onClose} className="w-full">Done</Button>
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────

export function BulkPropagateModal({ lotType, onClose, onDone }: Props) {
  const [step,    setStep]    = useState<Step>("configure");
  const [mode,    setMode]    = useState<PropagateMode>("SAFE");
  const [genMs,   setGenMs]   = useState(true);
  const [preview, setPreview] = useState<PropagatePreview | null>(null);
  const [result,  setResult]  = useState<PropagateResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const handlePreview = async (m: PropagateMode, gm: boolean) => {
    setMode(m); setGenMs(gm); setLoading(true); setError("");
    try {
      const p = await lotTypesApi.previewPropagate(lotType.id, m);
      setPreview(p);
      setStep("preview");
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Preview failed.");
    } finally { setLoading(false); }
  };

  const handleApply = async () => {
    if (!preview) return;
    setLoading(true); setError("");
    try {
      const r = await lotTypesApi.propagate(lotType.id, mode, undefined, genMs);
      setResult(r);
      setStep("result");
      onDone(r);
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Propagation failed.");
    } finally { setLoading(false); }
  };

  const titles: Record<Step, string> = {
    configure: `Propagate — ${lotType.name}`,
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
          <div className="mx-5 mt-3 bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading && step === "configure" ? (
          <div className="p-5 space-y-3">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 rounded-lg" />)}
          </div>
        ) : step === "configure" ? (
          <StepConfigure lotType={lotType} onNext={handlePreview} onClose={onClose} />
        ) : step === "preview" && preview ? (
          <StepPreview preview={preview} mode={mode} onApply={handleApply}
            onBack={() => setStep("configure")} applying={loading} />
        ) : step === "result" && result ? (
          <StepResult result={result} onClose={onClose} />
        ) : null}
      </div>
    </div>
  );
}
