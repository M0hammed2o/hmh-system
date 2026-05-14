/**
 * Apply BOQ Template to existing lots in a project.
 * Clones the selected template into per-lot BOQ records.
 * Only processes lots that don't already have a BOQ template applied.
 */
import { useEffect, useState } from "react";
import { X, Check, FileSpreadsheet, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { boqApi, type BOQHeader } from "@/api/boq";
import client from "@/api/client";

interface Lot {
  id: string;
  lot_number: string;
  boq_template_id: string | null;
}

interface Props {
  projectId: string;
  onClose: () => void;
  onApplied: (count: number) => void;
}

export function ApplyBOQTemplateModal({ projectId, onClose, onApplied }: Props) {
  const [templates, setTemplates] = useState<BOQHeader[]>([]);
  const [lots, setLots] = useState<Lot[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ created: number } | null>(null);

  useEffect(() => {
    Promise.all([
      boqApi.listHeaders(projectId),
      client.get<{ data: Lot[] }>(`/projects/${projectId}/lots/`),
    ]).then(([headers, lotsRes]) => {
      const templateHeaders = headers.filter((h) => h.is_template);
      setTemplates(templateHeaders);
      if (templateHeaders.length) setSelectedTemplate(templateHeaders[0].id);
      setLots(lotsRes.data.data || []);
    }).catch(() => setError("Failed to load data."))
      .finally(() => setLoading(false));
  }, [projectId]);

  const lotsWithoutBOQ = lots.filter((l) => !l.boq_template_id);
  const lotsWithBOQ = lots.filter((l) => l.boq_template_id);
  const targetLots = overwrite ? lots : lotsWithoutBOQ;

  const handleApply = async () => {
    if (!selectedTemplate || targetLots.length === 0) return;
    setApplying(true);
    setError("");
    try {
      const res = await client.post<{ data: { created_count: number } }>(
        "/boq-templates/clone-to-lots",
        {
          template_boq_id: selectedTemplate,
          project_id: projectId,
          lot_ids: targetLots.map((l) => l.id),
        }
      );
      const count = res.data.data?.created_count ?? targetLots.length;
      setResult({ created: count });
      onApplied(count);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
        || "Failed to apply template.";
      setError(msg);
    } finally { setApplying(false); }
  };

  if (result) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
        <div className="bg-card border border-border rounded-xl w-full max-w-sm p-8 text-center animate-fade-in">
          <Check className="w-10 h-10 text-green-500 mx-auto mb-3" />
          <p className="font-semibold text-lg">Template applied!</p>
          <p className="text-sm text-muted-foreground mt-1">
            BOQ cloned to {result.created} lot{result.created !== 1 ? "s" : ""}.
            Each lot now has its own editable BOQ.
          </p>
          <Button onClick={onClose} className="mt-5 w-full">Done</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold">Apply BOQ Template to Lots</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        {loading ? (
          <div className="space-y-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 rounded-lg" />)}</div>
        ) : templates.length === 0 ? (
          <div className="text-center py-6">
            <FileSpreadsheet className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">No BOQ templates found for this project.</p>
            <p className="text-xs text-muted-foreground mt-1">
              Go to the BOQ page, build or import a BOQ, then mark it as a template.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Template to apply</label>
              <select
                value={selectedTemplate}
                onChange={(e) => setSelectedTemplate(e.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.template_name || t.version_name}
                  </option>
                ))}
              </select>
            </div>

            {/* Status summary */}
            <div className="bg-muted/40 rounded-lg p-3 space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Total lots in project</span>
                <span className="font-medium">{lots.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Lots with BOQ already</span>
                <span className="font-medium text-green-600 dark:text-green-400">{lotsWithBOQ.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Lots without BOQ</span>
                <span className="font-medium text-amber-500">{lotsWithoutBOQ.length}</span>
              </div>
            </div>

            {lotsWithBOQ.length > 0 && (
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={overwrite}
                  onChange={(e) => setOverwrite(e.target.checked)}
                  className="mt-0.5 rounded"
                />
                <div>
                  <span className="text-sm">Also apply to lots that already have a BOQ</span>
                  <p className="text-xs text-muted-foreground">This will add a second BOQ to those lots.</p>
                </div>
              </label>
            )}

            {targetLots.length === 0 && (
              <div className="flex items-center gap-2 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
                <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  All lots already have a BOQ. Check the box above to apply anyway.
                </p>
              </div>
            )}

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <div className="flex gap-2 pt-1">
              <Button
                onClick={handleApply}
                disabled={applying || targetLots.length === 0 || !selectedTemplate}
                className="flex-1"
              >
                {applying
                  ? "Applying…"
                  : `Apply to ${targetLots.length} lot${targetLots.length !== 1 ? "s" : ""}`
                }
              </Button>
              <Button variant="outline" onClick={onClose}>Cancel</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
