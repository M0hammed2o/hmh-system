/**
 * Sites bulk-create modal.
 * Usage: <SitesBulkCreateModal projectId="..." onClose={() => {}} onCreated={() => reload()} />
 */
import { useState } from "react";
import { Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import client from "@/api/client";

interface Props {
  projectId: string;
  onClose: () => void;
  onCreated: (count: number) => void;
}

export function SitesBulkCreateModal({ projectId, onClose, onCreated }: Props) {
  const [prefix, setPrefix] = useState("Site");
  const [count, setCount] = useState("3");
  const [siteType, setSiteType] = useState("construction_site");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(0);

  const preview = Array.from({ length: Math.min(parseInt(count) || 0, 5) }, (_, i) => `${prefix.trim()} ${i + 1}`);
  const countNum = parseInt(count) || 0;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prefix.trim() || countNum < 1 || countNum > 50) return;
    setLoading(true);
    setError("");
    try {
      const res = await client.post<{ data: unknown[] }>(
        `/projects/${projectId}/sites/bulk`,
        { prefix: prefix.trim(), count: countNum, site_type: siteType },
      );
      const created = Array.isArray(res.data.data) ? res.data.data.length : countNum;
      setDone(created);
      onCreated(created);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to create sites.";
      setError(msg);
    } finally { setLoading(false); }
  };

  if (done > 0) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
        <div className="bg-card border border-border rounded-xl w-full max-w-sm p-8 text-center animate-fade-in">
          <Check className="w-10 h-10 text-green-500 mx-auto mb-3" />
          <p className="font-semibold text-lg">{done} site{done !== 1 ? "s" : ""} created!</p>
          <Button onClick={onClose} className="mt-5 w-full">Close</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold">Create Multiple Sites</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>
        <form onSubmit={handleCreate} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Name Prefix</Label>
              <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} placeholder="e.g. Site" required />
            </div>
            <div className="space-y-2">
              <Label>Number of Sites</Label>
              <Input
                type="number" min="1" max="50"
                value={count}
                onChange={(e) => setCount(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Site Type</Label>
            <Input value={siteType} onChange={(e) => setSiteType(e.target.value)} placeholder="construction_site" />
          </div>

          {/* Preview */}
          {preview.length > 0 && (
            <div className="bg-muted/40 rounded-lg p-3">
              <p className="text-xs font-medium text-muted-foreground mb-2">Preview:</p>
              <div className="flex flex-wrap gap-1.5">
                {preview.map((name) => (
                  <span key={name} className="text-xs bg-background border border-border rounded px-2 py-0.5">{name}</span>
                ))}
                {countNum > 5 && <span className="text-xs text-muted-foreground">… and {countNum - 5} more</span>}
              </div>
            </div>
          )}

          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}

          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading || countNum < 1 || !prefix.trim()} className="flex-1">
              {loading ? "Creating…" : `Create ${countNum || ""} Site${countNum !== 1 ? "s" : ""}`}
            </Button>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
