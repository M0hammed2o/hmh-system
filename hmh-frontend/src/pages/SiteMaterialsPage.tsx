/**
 * Site Materials — per-material stock status for a selected lot.
 * Shows: BOQ Allocated | Delivered | Used | Remaining | Variance (over-BOQ)
 * Data from: GET /site-dashboard/{site_id}/lots/{lot_id}/material-summary
 */
import { useEffect, useState, useCallback } from "react";
import { AlertTriangle, CheckCircle2, Package, RefreshCw } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import client from "@/api/client";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Project { id: string; name: string; }
interface Site    { id: string; name: string; }
interface Lot     { id: string; lot_number: string; unit_type: string | null; site_id: string | null; }

interface MaterialRow {
  boq_item_id:       string;
  item_id:           string | null;
  description:       string;
  unit:              string | null;
  boq_allocated_qty: number;
  delivered_qty:     number;
  used_qty:          number;
  remaining_qty:     number;
  over_qty:          number;
  status:            "OK" | "LOW" | "OVER_BOQ" | "STOCK_ISSUE";
  from_site_template: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number, unit?: string | null) {
  const s = n % 1 === 0 ? String(n) : n.toFixed(2);
  return unit ? `${s} ${unit}` : s;
}

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  OK:          { label: "OK",          cls: "bg-green-100 text-green-700"   },
  LOW:         { label: "Low Stock",   cls: "bg-amber-100 text-amber-700"   },
  OVER_BOQ:    { label: "Over BOQ",    cls: "bg-red-100 text-red-700"       },
  STOCK_ISSUE: { label: "Stock Issue", cls: "bg-orange-100 text-orange-700" },
};

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SiteMaterialsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [sites,    setSites]    = useState<Site[]>([]);
  const [lots,     setLots]     = useState<Lot[]>([]);

  const [projectId, setProjectId] = useState("");
  const [siteId,    setSiteId]    = useState("");
  const [lotId,     setLotId]     = useState("");

  const [materials, setMaterials] = useState<MaterialRow[]>([]);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState("");

  // Load projects on mount
  useEffect(() => {
    client.get<{ data: { items?: Project[]; total?: number } | Project[] }>("/projects/", {
      params: { status: "ACTIVE", limit: 50 },
    }).then(r => {
      const raw = r.data.data;
      const list: Project[] = Array.isArray(raw) ? raw : (raw as { items?: Project[] }).items ?? [];
      setProjects(list);
      if (list.length > 0) setProjectId(list[0].id);
    }).catch(() => {});
  }, []);

  // Load sites when project changes
  useEffect(() => {
    if (!projectId) { setSites([]); setSiteId(""); return; }
    client.get<{ data: Site[] }>(`/projects/${projectId}/sites/`)
      .then(r => {
        const list = r.data.data || [];
        setSites(list);
        setSiteId(list[0]?.id ?? "");
      })
      .catch(() => setSites([]));
  }, [projectId]);

  // Load lots when site changes
  useEffect(() => {
    if (!projectId) { setLots([]); setLotId(""); return; }
    client.get<{ data: Lot[] | { items?: Lot[] } }>(`/projects/${projectId}/lots/`, {
      params: { limit: 200 },
    }).then(r => {
      const raw = r.data.data;
      const all: Lot[] = Array.isArray(raw) ? raw : (raw as { items?: Lot[] }).items ?? [];
      // Filter to lots belonging to the selected site (or unassigned)
      const filtered = siteId
        ? all.filter(l => l.site_id === siteId || l.site_id === null)
        : all;
      setLots(filtered);
      setLotId(filtered[0]?.id ?? "");
    }).catch(() => setLots([]));
  }, [projectId, siteId]);

  // Load material summary when lot changes
  const loadMaterials = useCallback(() => {
    if (!siteId || !lotId) { setMaterials([]); return; }
    setLoading(true);
    setError("");
    client.get<{ data: MaterialRow[] }>(`/site-dashboard/${siteId}/lots/${lotId}/material-summary`)
      .then(r => setMaterials(r.data.data || []))
      .catch(() => setError("Failed to load material data."))
      .finally(() => setLoading(false));
  }, [siteId, lotId]);

  useEffect(() => { loadMaterials(); }, [loadMaterials]);

  // ── Computed ────────────────────────────────────────────────────────────────
  const overCount  = materials.filter(m => m.status === "OVER_BOQ").length;
  const lowCount   = materials.filter(m => m.status === "LOW").length;
  const totalAlloc = materials.reduce((s, m) => s + m.boq_allocated_qty, 0);
  const totalDel   = materials.reduce((s, m) => s + m.delivered_qty,     0);
  const totalUsed  = materials.reduce((s, m) => s + m.used_qty,           0);

  const selectedLot = lots.find(l => l.id === lotId);

  return (
    <div className="space-y-4 animate-fade-in">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold">Site Materials</h1>
          <p className="text-sm text-muted-foreground">
            BOQ allocation vs delivered vs used per material.
          </p>
        </div>
        <button
          onClick={loadMaterials}
          disabled={loading}
          className="p-2 rounded-lg hover:bg-muted text-muted-foreground disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {/* ── Selectors ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Project</label>
          <select
            value={projectId}
            onChange={e => setProjectId(e.target.value)}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Site</label>
          <select
            value={siteId}
            onChange={e => setSiteId(e.target.value)}
            disabled={!projectId}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50"
          >
            <option value="">— All sites —</option>
            {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Lot</label>
          <select
            value={lotId}
            onChange={e => setLotId(e.target.value)}
            disabled={!siteId || lots.length === 0}
            className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50"
          >
            <option value="">— Select lot —</option>
            {lots.map(l => (
              <option key={l.id} value={l.id}>
                Lot {l.lot_number}{l.unit_type ? ` · ${l.unit_type}` : ""}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Summary cards ── */}
      {!loading && materials.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-card border border-border rounded-xl p-3">
            <p className="text-xs text-muted-foreground">Materials</p>
            <p className="text-xl font-bold">{materials.length}</p>
          </div>
          <div className={cn("bg-card border rounded-xl p-3", overCount > 0 ? "border-red-300 bg-red-50 dark:bg-red-950/20" : "border-border")}>
            <p className={cn("text-xs", overCount > 0 ? "text-red-600" : "text-muted-foreground")}>Over BOQ</p>
            <p className={cn("text-xl font-bold", overCount > 0 ? "text-red-600" : "")}>{overCount}</p>
          </div>
          <div className={cn("bg-card border rounded-xl p-3", lowCount > 0 ? "border-amber-300 bg-amber-50 dark:bg-amber-950/20" : "border-border")}>
            <p className={cn("text-xs", lowCount > 0 ? "text-amber-600" : "text-muted-foreground")}>Low Stock</p>
            <p className={cn("text-xl font-bold", lowCount > 0 ? "text-amber-600" : "")}>{lowCount}</p>
          </div>
          <div className="bg-card border border-border rounded-xl p-3">
            <p className="text-xs text-muted-foreground">Delivered (total)</p>
            <p className="text-xl font-bold">{fmt(totalDel)}</p>
          </div>
        </div>
      )}

      {/* ── Template notice ── */}
      {materials.length > 0 && materials[0].from_site_template && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 text-xs text-amber-700 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          No lot-specific BOQ found — showing site template. Generate lot BOQs first for accurate tracking.
        </div>
      )}

      {/* ── Error ── */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* ── Table ── */}
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-12 rounded-xl" />)}
        </div>
      ) : !lotId ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <Package className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">Select a project, site, and lot to view material data.</p>
        </div>
      ) : materials.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <Package className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No BOQ items for this lot.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Go to BOQ → Site view → Generate Lot BOQs to create allocations.
          </p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 bg-muted/50 border-b border-border">
            <p className="text-sm font-semibold">
              Lot {selectedLot?.lot_number ?? ""}
              {selectedLot?.unit_type ? ` · ${selectedLot.unit_type}` : ""}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Material</th>
                  <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">BOQ Allocated</th>
                  <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">Delivered</th>
                  <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">Used</th>
                  <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">Remaining</th>
                  <th className="text-right px-3 py-2.5 font-medium text-muted-foreground">Variance</th>
                  <th className="text-center px-3 py-2.5 font-medium text-muted-foreground">Status</th>
                </tr>
              </thead>
              <tbody>
                {materials.map((m) => {
                  const cfg = STATUS_BADGE[m.status] ?? STATUS_BADGE.OK;
                  const isOver = m.status === "OVER_BOQ";
                  return (
                    <tr
                      key={m.boq_item_id}
                      className={cn(
                        "border-b border-border/50 last:border-0 transition-colors",
                        isOver ? "bg-red-50/50 dark:bg-red-950/10 hover:bg-red-50 dark:hover:bg-red-950/20"
                               : "hover:bg-muted/20",
                      )}
                    >
                      <td className="px-4 py-2.5">
                        <span className="font-medium">{m.description}</span>
                        {!m.item_id && (
                          <span className="ml-1.5 text-[10px] bg-muted text-muted-foreground rounded px-1">
                            no catalog link
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
                        {fmt(m.boq_allocated_qty, m.unit)}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {m.delivered_qty > 0
                          ? <span className="text-blue-600 dark:text-blue-400 font-medium">{fmt(m.delivered_qty, m.unit)}</span>
                          : <span className="text-muted-foreground">—</span>
                        }
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {m.used_qty > 0
                          ? <span className="font-medium">{fmt(m.used_qty, m.unit)}</span>
                          : <span className="text-muted-foreground">—</span>
                        }
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums font-semibold">
                        <span className={cn(
                          m.remaining_qty <= 0 ? "text-red-600" :
                          m.remaining_qty < m.boq_allocated_qty * 0.15 ? "text-amber-600" :
                          "text-green-600 dark:text-green-400",
                        )}>
                          {fmt(m.remaining_qty, m.unit)}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">
                        {m.over_qty > 0
                          ? <span className="text-red-600 font-semibold">+{fmt(m.over_qty, m.unit)}</span>
                          : <span className="text-muted-foreground">—</span>
                        }
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <span className={cn("text-xs font-medium rounded-full px-2 py-0.5", cfg.cls)}>
                          {cfg.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="bg-muted/30 border-t border-border">
                  <td className="px-4 py-2 text-xs font-semibold text-muted-foreground">Totals</td>
                  <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums">{fmt(totalAlloc)}</td>
                  <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-blue-600 dark:text-blue-400">{fmt(totalDel)}</td>
                  <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums">{fmt(totalUsed)}</td>
                  <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums">{fmt(Math.max(0, totalAlloc - totalUsed))}</td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
