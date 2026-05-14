/**
 * Lots generator wizard.
 * Generates lots start_number..end_number with optional BOQ template cloning.
 */
import { useEffect, useState } from "react";
import { Check, X, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import client from "@/api/client";
import { boqApi, type BOQHeader } from "@/api/boq";

interface Site {
  id: string;
  name: string;
}

interface Props {
  projectId: string;
  onClose: () => void;
  onGenerated: (count: number) => void;
}

export function LotsGeneratorModal({ projectId, onClose, onGenerated }: Props) {
  const [sites, setSites] = useState<Site[]>([]);
  const [templates, setTemplates] = useState<BOQHeader[]>([]);
  const [loadingData, setLoadingData] = useState(true);

  const [start, setStart] = useState("1");
  const [end, setEnd] = useState("10");
  const [siteId, setSiteId] = useState("");
  const [unitType, setUnitType] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ created: number; lot_numbers: string[] } | null>(null);

  useEffect(() => {
    Promise.all([
      client.get<{ data: Site[] }>(`/projects/${projectId}/sites/`),
      boqApi.listHeaders(projectId),
    ]).then(([sitesRes, headers]) => {
      setSites(sitesRes.data.data || []);
      setTemplates(headers.filter((h) => h.is_template));
    }).catch(() => {}).finally(() => setLoadingData(false));
  }, [projectId]);

  const startNum = parseInt(start) || 1;
  const endNum = parseInt(end) || 1;
  const count = Math.max(0, endNum - startNum + 1);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (count < 1 || count > 500) return;
    setLoading(true);
    setError("");
    try {
      const body: Record<string, unknown> = {
        start_number: startNum,
        end_number: endNum,
      };
      if (siteId) body.site_id = siteId;
      if (unitType.trim()) body.unit_type = unitType.trim();
      if (templateId) body.boq_template_id = templateId;

      const res = await client.post<{ data: { created: number; lot_numbers: string[] } }>(
        `/projects/${projectId}/lots/generate`,
        body,
      );
      setResult(res.data.data);
      onGenerated(res.data.data.created);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to generate lots.";
      setError(msg);
    } finally { setLoading(false); }
  };

  if (result) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
        <div className="bg-card border border-border rounded-xl w-full max-w-sm p-8 text-center animate-fade-in">
          <Check className="w-10 h-10 text-green-500 mx-auto mb-3" />
          <p className="font-semibold text-lg">{result.created} lot{result.created !== 1 ? "s" : ""} generated!</p>
          {result.lot_numbers.length > 0 && (
            <p className="text-sm text-muted-foreground mt-1">
              Lot {result.lot_numbers[0]} to Lot {result.lot_numbers[result.lot_numbers.length - 1]}
            </p>
          )}
          {templateId && <p className="text-xs text-muted-foreground mt-1">BOQ template cloned to each lot.</p>}
          <Button onClick={onClose} className="mt-5 w-full">Close</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold">Generate Lots</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        {loadingData ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 rounded-lg" />)}
          </div>
        ) : (
          <form onSubmit={handleGenerate} className="space-y-4">
            {/* Range */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Start Number</Label>
                <Input type="number" min="1" value={start} onChange={(e) => setStart(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label>End Number</Label>
                <Input type="number" min={start} value={end} onChange={(e) => setEnd(e.target.value)} required />
              </div>
            </div>

            {count > 0 && (
              <div className="bg-primary/5 border border-primary/20 rounded-lg px-3 py-2 text-sm">
                Will generate <strong>{count}</strong> lot{count !== 1 ? "s" : ""}: Lot {startNum} to Lot {endNum}
              </div>
            )}

            {/* Site */}
            <div className="space-y-2">
              <Label>Assign to Site (optional)</Label>
              <select
                value={siteId}
                onChange={(e) => setSiteId(e.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="">— No site —</option>
                {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>

            {/* Unit type */}
            <div className="space-y-2">
              <Label>Unit Type (optional)</Label>
              <Input
                value={unitType}
                onChange={(e) => setUnitType(e.target.value)}
                placeholder="e.g. 2-Bed, 3-Bed, Duplex"
              />
            </div>

            {/* BOQ template */}
            <div className="space-y-2">
              <Label>BOQ Template (optional)</Label>
              {templates.length === 0 ? (
                <p className="text-xs text-muted-foreground">No templates found. Create a template from the BOQ Builder first.</p>
              ) : (
                <select
                  value={templateId}
                  onChange={(e) => setTemplateId(e.target.value)}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="">— No template —</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>{t.template_name || t.version_name}</option>
                  ))}
                </select>
              )}
              {templateId && (
                <p className="text-xs text-muted-foreground">BOQ will be cloned from the selected template to each new lot.</p>
              )}
            </div>

            {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}

            <div className="flex gap-2 pt-1">
              <Button type="submit" disabled={loading || count < 1 || count > 500} className="flex-1">
                {loading ? "Generating…" : `Generate ${count} Lot${count !== 1 ? "s" : ""}`}
              </Button>
              <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
