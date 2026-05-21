/**
 * Apply BOQ Template — 3-step modal.
 *
 * Phase 3C fixes:
 *   1. Uses GET /boq-templates/ (global templates, not project headers)
 *   2. Per-lot selection with status badges
 *   3. Dry-run preview before committing
 *   4. Overwrite confirmation when existing BOQ detected
 *   5. Option to generate milestones from template stages
 *   6. Freestanding lots (site_id=NULL) fully supported
 *   7. Success screen with per-lot detail
 *
 * Steps:
 *   configure → preview → result
 */
import { useEffect, useState } from "react";
import {
  X, Check, FileSpreadsheet, AlertTriangle, RefreshCw,
  ChevronRight, Flag,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  boqApi,
  type BOQTemplate,
  type BOQTemplatePreview,
  type BOQTemplatePreviewLot,
  type BOQCloneResult,
} from "@/api/boq";
import client from "@/api/client";
import { cn } from "@/lib/utils";

interface Lot {
  id: string;
  lot_number: string;
  unit_type: string | null;
  site_id: string | null;
  boq_template_id: string | null;
}

interface Props {
  projectId: string;
  onClose:   () => void;
  onApplied: (result: BOQCloneResult) => void;
}

// ── Step 1: Configure ─────────────────────────────────────────────────────────

function StepConfigure({
  projectId,
  onNext,
  onClose,
}: {
  projectId: string;
  onNext: (templateId: string, lotIds: string[], overwrite: boolean, milestones: boolean) => void;
  onClose: () => void;
}) {
  const [templates,         setTemplates]         = useState<BOQTemplate[]>([]);
  const [lots,              setLots]              = useState<Lot[]>([]);
  const [selectedTemplate,  setSelectedTemplate]  = useState("");
  const [selectedLotIds,    setSelectedLotIds]    = useState<Set<string>>(new Set());
  const [overwrite,         setOverwrite]         = useState(false);
  const [genMilestones,     setGenMilestones]     = useState(true);
  const [selectAll,         setSelectAll]         = useState(true);
  const [loading,           setLoading]           = useState(true);
  const [error,             setError]             = useState("");

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

  const toggleLot = (id: string) => {
    setSelectedLotIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedLotIds.size === lots.length) {
      setSelectedLotIds(new Set());
      setSelectAll(false);
    } else {
      setSelectedLotIds(new Set(lots.map(l => l.id)));
      setSelectAll(true);
    }
  };

  const lotsNeedingOverwrite = lots.filter(l => selectedLotIds.has(l.id) && l.boq_template_id);

  if (loading) {
    return (
      <div className="p-5 space-y-3">
        {[1, 2, 3].map(i => <Skeleton key={i} className="h-12 rounded-lg" />)}
      </div>
    );
  }

  if (templates.length === 0) {
    return (
      <div className="p-8 text-center space-y-3">
        <FileSpreadsheet className="w-8 h-8 text-muted-foreground mx-auto" />
        <p className="text-sm text-muted-foreground">No BOQ templates found.</p>
        <p className="text-xs text-muted-foreground">
          Open the BOQ page, build or import a BOQ, then mark it as a template.
        </p>
        <Button variant="outline" size="sm" onClick={onClose}>Close</Button>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">
      {error && (
        <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {/* Template picker */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Template to apply</label>
        <select
          value={selectedTemplate}
          onChange={e => setSelectedTemplate(e.target.value)}
          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
        >
          {templates.map(t => (
            <option key={t.id} value={t.id}>
              {t.template_name || t.version_name}
            </option>
          ))}
        </select>
      </div>

      {/* Lot selection */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium">
            Target lots ({selectedLotIds.size} of {lots.length} selected)
          </label>
          <button
            type="button"
            onClick={toggleAll}
            className="text-xs text-primary hover:underline"
          >
            {selectedLotIds.size === lots.length ? "Deselect all" : "Select all"}
          </button>
        </div>

        <div className="border border-border rounded-lg overflow-hidden max-h-52 overflow-y-auto">
          {lots.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">
              No lots in this project.
            </p>
          ) : (
            lots
              .sort((a, b) => a.lot_number.localeCompare(b.lot_number, undefined, { numeric: true }))
              .map((lot, i) => (
                <label
                  key={lot.id}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-muted/40 transition-colors",
                    i < lots.length - 1 && "border-b border-border/50",
                    selectedLotIds.has(lot.id) && "bg-primary/5",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selectedLotIds.has(lot.id)}
                    onChange={() => toggleLot(lot.id)}
                    className="rounded"
                  />
                  <span className="text-sm flex-1 min-w-0">
                    <span className="font-medium">{lot.lot_number}</span>
                    {lot.unit_type && (
                      <span className="text-muted-foreground ml-1.5">· {lot.unit_type}</span>
                    )}
                    {!lot.site_id && (
                      <span className="text-muted-foreground ml-1.5 text-xs">(freestanding)</span>
                    )}
                  </span>
                  {lot.boq_template_id ? (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 shrink-0">
                      Has BOQ
                    </span>
                  ) : (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">
                      Empty
                    </span>
                  )}
                </label>
              ))
          )}
        </div>
      </div>

      {/* Options */}
      <div className="space-y-3 border border-border rounded-lg p-3">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Options</p>

        {lotsNeedingOverwrite.length > 0 && (
          <label className="flex items-start gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={e => setOverwrite(e.target.checked)}
              className="mt-0.5 rounded"
            />
            <div>
              <p className="text-sm font-medium">
                Overwrite existing BOQ
                <span className="ml-1.5 text-xs text-amber-600 font-normal">
                  ({lotsNeedingOverwrite.length} lot{lotsNeedingOverwrite.length !== 1 ? "s" : ""} affected)
                </span>
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Deactivates current items and replaces them with the template.
                Old data is soft-deleted and can be recovered.
              </p>
            </div>
          </label>
        )}

        <label className="flex items-start gap-2.5 cursor-pointer">
          <input
            type="checkbox"
            checked={genMilestones}
            onChange={e => setGenMilestones(e.target.checked)}
            className="mt-0.5 rounded"
          />
          <div>
            <p className="text-sm font-medium flex items-center gap-1.5">
              <Flag className="w-3.5 h-3.5 text-primary" />
              Generate milestones from template stages
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Creates "Not started" milestone records for each stage referenced
              in the template sections. Existing milestone records are preserved.
            </p>
          </div>
        </label>
      </div>

      <div className="flex gap-2 pt-1">
        <Button
          onClick={() => onNext(selectedTemplate, Array.from(selectedLotIds), overwrite, genMilestones)}
          disabled={!selectedTemplate || selectedLotIds.size === 0}
          className="flex-1 gap-1.5"
        >
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
  overwrite,
  genMilestones,
  onApply,
  onBack,
  applying,
}: {
  preview: BOQTemplatePreview;
  overwrite: boolean;
  genMilestones: boolean;
  onApply: () => void;
  onBack: () => void;
  applying: boolean;
}) {
  const creates    = preview.lots.filter(l => l.action === "create").length;
  const overwrites = preview.lots.filter(l => l.action === "overwrite").length;

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-4">
      {/* Summary */}
      <div className="bg-muted/40 rounded-xl p-4 space-y-2">
        <p className="text-sm font-semibold">
          Applying: {preview.template_name}
        </p>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-card rounded-lg py-2">
            <p className="text-xl font-bold">{preview.template_item_count}</p>
            <p className="text-[10px] text-muted-foreground">Items per lot</p>
          </div>
          <div className="bg-card rounded-lg py-2">
            <p className="text-xl font-bold">{preview.template_section_count}</p>
            <p className="text-[10px] text-muted-foreground">Sections</p>
          </div>
          <div className="bg-card rounded-lg py-2">
            <p className="text-xl font-bold">{preview.template_stage_count}</p>
            <p className="text-[10px] text-muted-foreground">Milestones</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground pt-1">
          <span>
            <span className="font-medium text-green-600">{creates}</span> lot(s) — create
          </span>
          {overwrites > 0 && (
            <span>
              <span className="font-medium text-amber-600">{overwrites}</span> lot(s) — overwrite
            </span>
          )}
        </div>
      </div>

      {/* Overwrite warning */}
      {overwrites > 0 && overwrite && (
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 dark:bg-amber-950/20 dark:border-amber-800/50 rounded-xl px-4 py-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">
              Overwriting {overwrites} existing BOQ{overwrites !== 1 ? "s" : ""}
            </p>
            <p className="text-xs text-amber-600 dark:text-amber-500 mt-0.5">
              Existing items will be soft-deleted and replaced. This cannot be undone
              without re-applying or manually restoring items.
            </p>
          </div>
        </div>
      )}

      {/* Per-lot preview */}
      <div className="border border-border rounded-xl overflow-hidden max-h-64 overflow-y-auto">
        <div className="px-3 py-2 bg-muted/30 border-b border-border">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Per-lot detail
          </p>
        </div>
        {preview.lots.map((lot, i) => (
          <LotPreviewRow key={lot.lot_id} lot={lot} genMilestones={genMilestones} overwrite={overwrite}
            isLast={i === preview.lots.length - 1} />
        ))}
      </div>

      <div className="flex gap-2 pt-1">
        <Button onClick={onApply} disabled={applying} className="flex-1 gap-1.5">
          {applying ? (
            <><RefreshCw className="w-4 h-4 animate-spin" />Applying…</>
          ) : (
            <><Check className="w-4 h-4" />Apply to {preview.total_lots} lot{preview.total_lots !== 1 ? "s" : ""}</>
          )}
        </Button>
        <Button variant="outline" onClick={onBack} disabled={applying}>Back</Button>
      </div>
    </div>
  );
}

function LotPreviewRow({
  lot, genMilestones, overwrite, isLast,
}: {
  lot: BOQTemplatePreviewLot;
  genMilestones: boolean;
  overwrite: boolean;
  isLast: boolean;
}) {
  return (
    <div className={cn(
      "flex items-start gap-3 px-3 py-2.5",
      !isLast && "border-b border-border/50",
      lot.action === "overwrite" && "bg-amber-50/50 dark:bg-amber-950/10",
    )}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{lot.lot_number}</span>
          {lot.unit_type && (
            <span className="text-xs text-muted-foreground">· {lot.unit_type}</span>
          )}
          <span className={cn(
            "text-[10px] px-1.5 py-0.5 rounded font-medium",
            lot.action === "create"
              ? "bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-400"
              : "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
          )}>
            {lot.action === "create" ? "Create" : "Overwrite"}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">
          {lot.new_item_count} BOQ items
          {genMilestones && lot.new_milestone_count > 0 && (
            <span className="ml-1.5">
              · {lot.new_milestone_count} milestone{lot.new_milestone_count !== 1 ? "s" : ""}
              {lot.has_existing_milestones ? " (existing kept)" : ""}
            </span>
          )}
          {lot.action === "overwrite" && overwrite && (
            <span className="ml-1.5 text-amber-600">
              · replacing {lot.existing_item_count} existing items
            </span>
          )}
        </p>
      </div>
    </div>
  );
}

// ── Step 3: Result ────────────────────────────────────────────────────────────

function StepResult({
  result,
  onClose,
}: {
  result: BOQCloneResult;
  onClose: () => void;
}) {
  return (
    <div className="p-8 text-center space-y-4">
      <Check className="w-12 h-12 text-green-500 mx-auto" />
      <div>
        <p className="font-semibold text-lg">Template applied!</p>
        <p className="text-sm text-muted-foreground mt-1">
          BOQ applied to <strong>{result.created_count}</strong> lot{result.created_count !== 1 ? "s" : ""}
          {result.milestones_created > 0 && (
            <span> · <strong>{result.milestones_created}</strong> milestone{result.milestones_created !== 1 ? "s" : ""} created</span>
          )}
          {result.deactivated_count > 0 && (
            <span> · <strong>{result.deactivated_count}</strong> old item{result.deactivated_count !== 1 ? "s" : ""} replaced</span>
          )}
          {result.freestanding_master && (
            <span> · project-level master created for freestanding units</span>
          )}
          .
        </p>
      </div>
      <div className="grid grid-cols-3 gap-3 text-center">
        {[
          { label: "Lots updated",       value: result.created_count       },
          { label: "Milestones created", value: result.milestones_created  },
          { label: "Old items replaced", value: result.deactivated_count   },
        ].map(k => (
          <div key={k.label} className="bg-muted/40 rounded-xl py-3 px-2">
            <p className="text-2xl font-bold">{k.value}</p>
            <p className="text-[11px] text-muted-foreground mt-0.5">{k.label}</p>
          </div>
        ))}
      </div>
      <Button onClick={onClose} className="w-full mt-2">Done</Button>
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────

export function ApplyBOQTemplateModal({ projectId, onClose, onApplied }: Props) {
  type Step = "configure" | "preview" | "result";
  const [step,         setStep]         = useState<Step>("configure");
  const [templateId,   setTemplateId]   = useState("");
  const [lotIds,       setLotIds]       = useState<string[]>([]);
  const [overwrite,    setOverwrite]    = useState(false);
  const [genMilestone, setGenMilestone] = useState(true);
  const [preview,      setPreview]      = useState<BOQTemplatePreview | null>(null);
  const [result,       setResult]       = useState<BOQCloneResult | null>(null);
  const [applying,     setApplying]     = useState(false);
  const [error,        setError]        = useState("");

  const handlePreview = async (tmplId: string, ids: string[], ow: boolean, gm: boolean) => {
    setTemplateId(tmplId);
    setLotIds(ids);
    setOverwrite(ow);
    setGenMilestone(gm);
    setError("");
    try {
      const p = await boqApi.previewClone({ template_boq_id: tmplId, project_id: projectId, lot_ids: ids });
      setPreview(p);
      setStep("preview");
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Preview failed. Check that the template has items.");
    }
  };

  const handleApply = async () => {
    if (!preview) return;
    setApplying(true);
    setError("");
    try {
      const r = await boqApi.cloneToLots({
        template_boq_id:     templateId,
        project_id:          projectId,
        lot_ids:             lotIds,
        overwrite,
        generate_milestones: genMilestone,
      });
      setResult(r);
      setStep("result");
      onApplied(r);
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Apply failed — check Render logs for details.");
    } finally {
      setApplying(false);
    }
  };

  const title = { configure: "Apply BOQ Template", preview: "Preview Changes", result: "" }[step];

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-t-2xl sm:rounded-2xl w-full sm:max-w-lg max-h-[92vh] flex flex-col">
        {title && (
          <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border shrink-0">
            <h2 className="text-base font-semibold">{title}</h2>
            <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
          </div>
        )}

        {error && (
          <div className="mx-5 mt-3 bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {step === "configure" && (
          <StepConfigure projectId={projectId} onNext={handlePreview} onClose={onClose} />
        )}
        {step === "preview" && preview && (
          <StepPreview
            preview={preview}
            overwrite={overwrite}
            genMilestones={genMilestone}
            onApply={handleApply}
            onBack={() => setStep("configure")}
            applying={applying}
          />
        )}
        {step === "result" && result && (
          <StepResult result={result} onClose={onClose} />
        )}
      </div>
    </div>
  );
}
