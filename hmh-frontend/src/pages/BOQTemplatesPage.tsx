/**
 * BOQ Template manager + lot-clone wizard.
 * Lists reusable templates, lets office users clone to selected lots.
 */
import { useEffect, useState } from "react";
import { Copy, FileSpreadsheet, Check, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import client from "@/api/client";

interface BOQTemplate {
  id: string;
  version_name: string;
  template_name: string | null;
  notes: string | null;
}

interface Lot {
  id: string;
  lot_number: string;
  status: string;
}

interface CloneWizardProps {
  template: BOQTemplate;
  onClose: () => void;
  onDone: () => void;
}

function CloneWizard({ template, onClose, onDone }: CloneWizardProps) {
  const [projects, setProjects] = useState<Array<{ id: string; name: string; code: string }>>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [lots, setLots] = useState<Lot[]>([]);
  const [selectedLots, setSelectedLots] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<"project" | "lots" | "confirm">("project");
  const [cloning, setCloning] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    client.get<{ data: Array<{ id: string; name: string; code: string }> }>("/projects/")
      .then((r) => setProjects(r.data.data || []))
      .catch(() => {});
  }, []);

  const loadLots = async (projectId: string) => {
    setLoading(true);
    try {
      // API returns ApiSuccess<list[LotRead]> → { data: [...] } (plain array, not paginated)
      const r = await client.get<{ data: Lot[] }>(`/projects/${projectId}/lots/`);
      const lots = Array.isArray(r.data.data) ? r.data.data : [];
      setLots(lots);
    } catch {
      setError("Failed to load lots.");
    } finally { setLoading(false); }
  };

  const selectProject = (id: string) => {
    setSelectedProject(id);
    setSelectedLots(new Set());
    loadLots(id);
    setStep("lots");
  };

  const toggleLot = (id: string) => {
    setSelectedLots((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelectedLots(new Set(lots.map((l) => l.id)));
  const clearAll = () => setSelectedLots(new Set());

  const clone = async () => {
    setCloning(true);
    setError("");
    try {
      await client.post("/boq-templates/clone-to-lots", {
        template_boq_id: template.id,
        project_id: selectedProject,
        lot_ids: Array.from(selectedLots),
      });
      setDone(true);
      setTimeout(() => { onDone(); onClose(); }, 1500);
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string; message?: string } } })?.response?.data;
      setError(d?.detail || d?.message || "Clone failed — check Render logs for the full error.");
    } finally { setCloning(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-t-2xl sm:rounded-2xl w-full sm:max-w-lg max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-border shrink-0">
          <div>
            <h2 className="text-base font-semibold">Clone Template to Lots</h2>
            <p className="text-xs text-muted-foreground">{template.template_name || template.version_name}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground">✕</button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {done ? (
            <div className="text-center py-8">
              <Check className="w-10 h-10 text-green-500 mx-auto mb-3" />
              <p className="font-semibold">Cloned to {selectedLots.size} lot{selectedLots.size !== 1 ? "s" : ""}!</p>
            </div>
          ) : step === "project" ? (
            <>
              <p className="text-sm text-muted-foreground">Select the project to clone this template into:</p>
              <div className="space-y-2">
                {projects.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => selectProject(p.id)}
                    className="w-full flex items-center justify-between px-4 py-3 bg-muted/30 hover:bg-muted/60 rounded-xl transition-colors text-left"
                  >
                    <div>
                      <p className="font-medium">{p.name}</p>
                      <p className="text-xs text-muted-foreground">{p.code}</p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  </button>
                ))}
              </div>
            </>
          ) : step === "lots" ? (
            <>
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">{lots.length} lots available</p>
                <div className="flex gap-2">
                  <button onClick={selectAll} className="text-xs text-primary hover:underline">All</button>
                  <button onClick={clearAll} className="text-xs text-muted-foreground hover:underline">None</button>
                </div>
              </div>
              {loading ? (
                <div className="space-y-2">{[1,2,3].map((i) => <Skeleton key={i} className="h-10 rounded-lg" />)}</div>
              ) : (
                <div className="space-y-1.5">
                  {lots.map((lot) => (
                    <button
                      key={lot.id}
                      onClick={() => toggleLot(lot.id)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-left ${
                        selectedLots.has(lot.id) ? "bg-primary/10 border border-primary/30" : "hover:bg-muted/40"
                      }`}
                    >
                      <div className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                        selectedLots.has(lot.id) ? "bg-primary border-primary" : "border-border"
                      }`}>
                        {selectedLots.has(lot.id) && <Check className="w-3 h-3 text-primary-foreground" />}
                      </div>
                      <span className="text-sm font-medium">Lot {lot.lot_number}</span>
                      <Badge variant="outline" className="text-xs ml-auto">{lot.status}</Badge>
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : null}

          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
        </div>

        {step === "lots" && selectedLots.size > 0 && (
          <div className="px-5 pb-5 pt-3 border-t border-border shrink-0">
            <Button onClick={clone} disabled={cloning} className="w-full">
              <Copy className="w-4 h-4 mr-2" />
              {cloning ? "Cloning…" : `Clone to ${selectedLots.size} lot${selectedLots.size !== 1 ? "s" : ""}`}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function BOQTemplatesPage() {
  const [templates, setTemplates] = useState<BOQTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cloneTarget, setCloneTarget] = useState<BOQTemplate | null>(null);

  useEffect(() => {
    client.get<{ data: BOQTemplate[] }>("/boq-templates/")
      .then((r) => setTemplates(r.data.data || []))
      .catch(() => setError("Failed to load BOQ templates."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-xl font-bold">BOQ Templates</h1>
        <p className="text-sm text-muted-foreground">Reusable BOQ templates. Clone to multiple lots at once.</p>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">{error}</div>
      )}

      {loading ? (
        <div className="space-y-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>
      ) : templates.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center">
          <FileSpreadsheet className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No BOQ templates yet.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Mark a BOQ as a template using the BOQ page, then clone it here.
          </p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {templates.map((t, i) => (
            <div
              key={t.id}
              className={`flex items-center gap-4 px-4 py-3 hover:bg-muted/30 transition-colors ${
                i < templates.length - 1 ? "border-b border-border" : ""
              }`}
            >
              <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary/10 shrink-0">
                <FileSpreadsheet className="w-4 h-4 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm">{t.template_name || t.version_name}</p>
                {t.notes && <p className="text-xs text-muted-foreground truncate">{t.notes}</p>}
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setCloneTarget(t)}
              >
                <Copy className="w-3.5 h-3.5 mr-1.5" />
                Clone to Lots
              </Button>
            </div>
          ))}
        </div>
      )}

      {cloneTarget && (
        <CloneWizard
          template={cloneTarget}
          onClose={() => setCloneTarget(null)}
          onDone={() => {}}
        />
      )}
    </div>
  );
}
