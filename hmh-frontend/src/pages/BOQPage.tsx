/**
 * BOQ Page — three-level hierarchy: Master Summary → Site BOQ → Lot BOQ
 *
 * Features:
 *  - Project / View-Mode / Site / Lot selectors
 *  - Material / Labour / Plant / Service type breakdown cards
 *  - Variance calculations (actual vs expected)
 *  - Export to CSV and browser-print PDF
 *  - Numerical lot sorting (1,2,3…10 not 1,10,11,2)
 *  - Fallback: if no site-level BOQ exists, derives from lot BOQs
 */

import { useEffect, useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  FileSpreadsheet, TrendingUp, Building2, Package, Users,
  Wrench, ChevronRight, RefreshCw, AlertTriangle, CheckCircle2,
  RotateCcw, ExternalLink, Download, Printer, HardHat,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { lotsApi, type Lot } from "@/api/lots";
import {
  boqApi,
  type ProjectMasterSummary,
  type SiteBOQSummary,
  type SiteBOQItem,
  type LotBOQRow,
} from "@/api/boq";
import { formatCurrency } from "@/lib/format";
import BOQTemplatesInner from "@/pages/BOQTemplatesPage";

// ── Helpers ───────────────────────────────────────────────────────────────────

function siteItemTotal(item: SiteBOQItem): number {
  return item.line_total ?? (Number(item.planned_quantity ?? 0) * Number(item.planned_rate ?? 0));
}

function varianceColor(pct: number): string {
  if (pct > 2)  return "text-destructive";
  if (pct > 0)  return "text-amber-600";
  if (pct < -2) return "text-blue-600";
  return "text-success";
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return formatCurrency(n);
}

// ── CSV Export ────────────────────────────────────────────────────────────────

function downloadCSV(filename: string, rows: string[][]) {
  const text = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([text], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function exportMasterCSV(summary: ProjectMasterSummary, projectName: string) {
  const rows: string[][] = [
    ["HMH Group — Project BOQ Master Summary"],
    ["Project", projectName],
    ["Total Planned", String(summary.total_planned)],
    ["Material Total", String(summary.material_total)],
    ["Labour Total", String(summary.labour_total)],
    ["Plant Total", String(summary.plant_total)],
    [],
    ["Site", "Lots", "Unit Total", "Site Total", "Material", "Labour", "Plant", "Variance %"],
    ...summary.sites.map((s) => [
      s.site_name, String(s.lot_count),
      String(s.unit_total), String(s.site_total),
      String(s.material_total), String(s.labour_total), String(s.plant_total),
      String(s.variance_pct) + "%",
    ]),
  ];
  downloadCSV("boq-master-summary.csv", rows);
}

function exportSiteCSV(summary: SiteBOQSummary, lots: LotBOQRow[]) {
  const rows: string[][] = [
    ["HMH Group — Site BOQ"],
    ["Site", summary.site_name],
    ["Unit Total", String(summary.unit_total)],
    ["Site Total", String(summary.site_total)],
    [],
    ["Section", "Description", "Unit", "Qty", "Rate", "Total", "Type"],
    ...summary.sections.flatMap((sec) =>
      sec.items.map((i) => [
        sec.section_name, i.description, i.unit ?? "", String(i.planned_quantity),
        String(i.planned_rate), String(siteItemTotal(i)), i.item_type,
      ])
    ),
    [],
    ["Lot #", "Total", "Custom", "Material", "Labour", "Plant", "Variance %"],
    ...lots.map((l) => [
      l.lot_number, String(l.lot_total),
      l.has_custom_boq ? "Yes" : "No",
      String(l.material_total), String(l.labour_total), String(l.plant_total),
      String(l.variance_pct) + "%",
    ]),
  ];
  downloadCSV(`boq-site-${summary.site_name.replace(/\s+/g, "-")}.csv`, rows);
}

// ── Print / PDF ───────────────────────────────────────────────────────────────

function triggerPrint() {
  window.print();
}

// ── Atoms ─────────────────────────────────────────────────────────────────────

function Sel({ label, value, onChange, disabled = false, children }: {
  label: string; value: string; onChange: (v: string) => void;
  disabled?: boolean; children: React.ReactNode;
}) {
  return (
    <div>
      <label className="text-xs text-muted-foreground block mb-1">{label}</label>
      <select
        value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}
        className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[200px] disabled:opacity-50"
      >
        {children}
      </select>
    </div>
  );
}

function ViewTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
        active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
      }`}
    >
      {label}
    </button>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-3 bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">
      <AlertTriangle className="w-4 h-4 shrink-0" />{message}
    </div>
  );
}

function TypeCards({ material, labour, plant, service }: {
  material: number; labour: number; plant: number; service: number;
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-xl p-3">
        <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">Material</p>
        <p className="text-base font-bold text-blue-700 dark:text-blue-300 mt-0.5 tabular-nums">{fmt(material)}</p>
      </div>
      <div className="bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 rounded-xl p-3">
        <p className="text-xs text-green-600 dark:text-green-400 font-medium">Labour</p>
        <p className="text-base font-bold text-green-700 dark:text-green-300 mt-0.5 tabular-nums">{fmt(labour)}</p>
      </div>
      <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-3">
        <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">Plant</p>
        <p className="text-base font-bold text-amber-700 dark:text-amber-300 mt-0.5 tabular-nums">{fmt(plant)}</p>
      </div>
      <div className="bg-purple-50 dark:bg-purple-950/30 border border-purple-200 dark:border-purple-800 rounded-xl p-3">
        <p className="text-xs text-purple-600 dark:text-purple-400 font-medium">Service</p>
        <p className="text-base font-bold text-purple-700 dark:text-purple-300 mt-0.5 tabular-nums">{fmt(service)}</p>
      </div>
    </div>
  );
}

function VariancePill({ pct, amount }: { pct: number; amount: number }) {
  if (!pct && !amount) return null;
  const color = varianceColor(pct);
  const sign  = amount >= 0 ? "+" : "";
  return (
    <span className={`text-xs font-medium tabular-nums ${color}`}>
      {sign}{pct.toFixed(1)}% ({sign}{fmt(amount)})
    </span>
  );
}

// ── Site BOQ table ────────────────────────────────────────────────────────────

function SiteBOQTable({ summary }: { summary: SiteBOQSummary }) {
  const grandTotal = summary.sections.reduce((s, sec) => s + sec.section_total, 0);
  if (summary.sections.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-10 text-center text-sm text-muted-foreground">
        No BOQ items for this site.
        {summary.derived_from_lots && (
          <p className="text-xs mt-2 text-amber-600">No site-level items found — showing first lot as representative unit.</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {summary.derived_from_lots && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 text-xs text-amber-700 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>
            Showing lot BOQs as the unit view (no site-level master BOQ found).
            {" "}To create one: go to <strong>BOQ Templates</strong> and apply a template to this project's lots —
            the site-level master will be created automatically.
          </span>
        </div>
      )}
      {summary.sections.map((sec) => (
        <div key={sec.section_id} className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 bg-muted/50 border-b border-border flex items-center justify-between">
            <p className="text-sm font-semibold">{sec.section_name}</p>
            <p className="text-sm font-semibold text-primary">{fmt(sec.section_total)}</p>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">Description</th>
                <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Qty</th>
                <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Unit</th>
                <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Rate (R)</th>
                <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Total</th>
                <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">Type</th>
              </tr>
            </thead>
            <tbody>
              {sec.items.map((item) => {
                const total = siteItemTotal(item);
                return (
                  <tr key={item.id} className="border-b border-border last:border-0 hover:bg-muted/20">
                    <td className="px-4 py-2.5">
                      {item.description}
                      {(item as { supplier_name?: string | null }).supplier_name && (
                        <span className="block text-[10px] text-primary/70 mt-0.5">
                          {(item as { supplier_name?: string | null }).supplier_name}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{item.planned_quantity ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">{item.unit ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{item.planned_rate ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums font-medium">{total > 0 ? fmt(total) : "—"}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{item.item_type}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="bg-muted/30 border-t border-border">
                <td colSpan={4} className="px-4 py-2 text-xs font-semibold text-muted-foreground text-right">Section Total</td>
                <td className="px-4 py-2 text-right font-semibold tabular-nums">{fmt(sec.section_total)}</td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      ))}
      <div className="flex justify-end">
        <div className="bg-card border border-border rounded-xl px-5 py-3 flex items-center gap-6">
          <span className="text-sm font-medium text-muted-foreground">Site Unit Total</span>
          <span className="text-lg font-bold text-primary">{fmt(grandTotal)}</span>
        </div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

type ViewMode = "master" | "site" | "lot" | "templates";

export default function BOQPage() {
  const navigate = useNavigate();

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [viewMode, setViewMode]                   = useState<ViewMode>("master");
  const [selectedSiteId, setSelectedSiteId]       = useState("");
  const [selectedLotId, setSelectedLotId]         = useState("");
  // Phase 3G: freestanding lot mode — true when viewing lots with site_id=null
  const [freestandingMode, setFreestandingMode]   = useState(false);

  const [projects, setProjects] = useState<Project[]>([]);
  const [sites,    setSites]    = useState<Site[]>([]);
  const [lots,     setLots]     = useState<Lot[]>([]);

  const [masterSummary, setMasterSummary] = useState<ProjectMasterSummary | null>(null);
  const [siteSummary,   setSiteSummary]   = useState<SiteBOQSummary | null>(null);
  const [siteLots,      setSiteLots]      = useState<LotBOQRow[]>([]);

  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingMain,     setLoadingMain]     = useState(false);
  const [error,           setError]           = useState("");
  const [resetBusy,       setResetBusy]       = useState(false);

  useEffect(() => {
    projectsApi.list(1, 100)
      .then((res) => { setProjects(res.items); if (res.items.length > 0) setSelectedProjectId(res.items[0].id); })
      .catch(() => setProjects([]))
      .finally(() => setLoadingProjects(false));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) { setSites([]); return; }
    sitesApi.list(selectedProjectId).then(setSites).catch(() => setSites([]));
    lotsApi.list(selectedProjectId).then(setLots).catch(() => setLots([]));
    setSelectedSiteId(""); setSelectedLotId("");
    setMasterSummary(null); setSiteSummary(null); setSiteLots([]);
  }, [selectedProjectId]);

  const loadData = useCallback(() => {
    if (!selectedProjectId) return;
    setError(""); setLoadingMain(true);
    if (viewMode === "master") {
      boqApi.masterSummary(selectedProjectId)
        .then(setMasterSummary)
        .catch(() => setError("Failed to load project summary. Is the backend running?"))
        .finally(() => setLoadingMain(false));
    } else if (viewMode === "site" && selectedSiteId) {
      Promise.all([boqApi.siteBoqSummary(selectedSiteId), boqApi.siteLotBoqs(selectedSiteId)])
        .then(([s, l]) => { setSiteSummary(s); setSiteLots(l); })
        .catch(() => setError("Failed to load site BOQ data."))
        .finally(() => setLoadingMain(false));
    } else if (viewMode === "lot" && selectedSiteId) {
      boqApi.siteLotBoqs(selectedSiteId)
        .then(setSiteLots)
        .catch(() => setError("Failed to load lot data."))
        .finally(() => setLoadingMain(false));
    } else {
      setLoadingMain(false);
    }
  }, [selectedProjectId, viewMode, selectedSiteId]);

  useEffect(() => { loadData(); }, [loadData]);

  const changeMode = (mode: ViewMode) => {
    setViewMode(mode); setError("");
    if (mode !== "lot") setFreestandingMode(false);
    setMasterSummary(null); setSiteSummary(null); setSiteLots([]);
  };

  const navigateToLot = (lot: LotBOQRow) => {
    const headerId = lot.boq_header_ids[0] ?? siteSummary?.boq_header_ids[0] ?? null;
    if (!headerId) { alert("No BOQ header found. Generate lot BOQs from Site BOQ mode first."); return; }
    navigate(`/boq/${selectedProjectId}/${headerId}/build`);
  };

  const handleResetLot = async (lotId: string) => {
    if (!confirm("Reset this lot's BOQ to the site template? Custom changes will be lost.")) return;
    setResetBusy(true);
    try { await boqApi.resetLotToSiteBoq(lotId); loadData(); }
    catch { setError("Reset failed. Make sure a site BOQ exists."); }
    finally { setResetBusy(false); }
  };

  const handleGenerateLotBoqs = async () => {
    if (!selectedSiteId) return;
    try {
      const res = await boqApi.generateSiteLotBoqs(selectedSiteId);
      if (res.used_fallback) {
        // Fallback was used — show a prominent warning, not just a success toast
        setError(
          `⚠ ${res.created} BOQ item(s) generated, but ${res.unassigned_lots} lot(s) ` +
          `had no site assignment and were used as a fallback. ` +
          `Go to the Lots section and assign those lots to this site to prevent them ` +
          `being reused when generating for other sites.`
        );
      } else {
        alert(`Generated ${res.created} BOQ item(s) across ${res.lot_count} lot(s).`);
      }
      loadData();
    } catch (e: unknown) {
      const msg = (e as {response?: {data?: {detail?: string}}})?.response?.data?.detail || "Failed.";
      setError(msg);
    }
  };

  const projectName = projects.find((p) => p.id === selectedProjectId)?.name ?? "Project";
  const siteLotMap  = Object.fromEntries(lots.map((l) => [l.id, l]));

  if (loadingProjects) {
    return (
      <div className="space-y-5 animate-fade-in">
        <Skeleton className="h-12 rounded-xl" />
        <div className="grid grid-cols-3 gap-4">{[1,2,3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in print:space-y-3">
      <PageHeader
        title="Bill of Quantities"
        description="Project → Site → Lot hierarchy."
        actions={
          <div className="flex gap-2 print:hidden">
            {viewMode === "master" && masterSummary && (
              <Button size="sm" variant="outline" onClick={() => exportMasterCSV(masterSummary, projectName)}>
                <Download className="w-3.5 h-3.5 mr-1" />CSV
              </Button>
            )}
            {viewMode === "site" && siteSummary && (
              <Button size="sm" variant="outline" onClick={() => exportSiteCSV(siteSummary, siteLots)}>
                <Download className="w-3.5 h-3.5 mr-1" />CSV
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={triggerPrint}>
              <Printer className="w-3.5 h-3.5 mr-1" />Print
            </Button>
          </div>
        }
      />

      {/* ── Selectors ── */}
      <div className="bg-card border border-border rounded-xl px-4 py-3 space-y-3 print:hidden">
        <div className="flex flex-wrap items-end gap-4">
          <Sel label="Project" value={selectedProjectId} onChange={(v) => { setSelectedProjectId(v); changeMode("master"); }}>
            {projects.length === 0 ? <option disabled>No projects</option>
              : projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Sel>
          <div>
            <p className="text-xs text-muted-foreground mb-1">View Mode</p>
            <div className="flex gap-1 bg-muted/50 p-1 rounded-lg flex-wrap">
              {selectedProjectId && (
                <>
                  <ViewTab label="Master Summary" active={viewMode === "master"} onClick={() => changeMode("master")} />
                  <ViewTab label="Site BOQ"       active={viewMode === "site"}   onClick={() => changeMode("site")} />
                  <ViewTab label="Lot BOQ"        active={viewMode === "lot"}    onClick={() => changeMode("lot")} />
                </>
              )}
              <ViewTab label="Templates" active={viewMode === "templates"} onClick={() => changeMode("templates")} />
            </div>
          </div>
          <button onClick={loadData} disabled={loadingMain} className="p-2 rounded-md hover:bg-muted text-muted-foreground disabled:opacity-50 mt-5" title="Refresh">
            <RefreshCw className={`w-4 h-4 ${loadingMain ? "animate-spin" : ""}`} />
          </button>
        </div>
        {selectedProjectId && viewMode !== "master" && (
          <div className="flex flex-wrap items-end gap-4">
            <Sel label="Site / Block" value={selectedSiteId} onChange={(v) => { setSelectedSiteId(v); setSelectedLotId(""); setFreestandingMode(false); }} disabled={sites.length === 0}>
              <option value="">— Select site —</option>
              {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Sel>
            {viewMode === "lot" && (selectedSiteId || freestandingMode) && (
              <Sel
                label={freestandingMode ? "Lot / Unit" : "Lot"}
                value={selectedLotId}
                onChange={setSelectedLotId}
                disabled={(() => {
                  const avail = freestandingMode
                    ? lots.filter(l => !l.site_id)
                    : lots.filter(l => l.site_id === selectedSiteId);
                  return avail.length === 0;
                })()}
              >
                <option value="">— Select lot —</option>
                {(freestandingMode
                  ? lots.filter(l => !l.site_id)
                  : lots.filter(l => l.site_id === selectedSiteId)
                )
                  .sort((a, b) => a.lot_number.localeCompare(b.lot_number, undefined, { numeric: true, sensitivity: "base" }))
                  .map(l => (
                    <option key={l.id} value={l.id}>
                      {l.lot_number}{l.unit_type ? ` · ${l.unit_type}` : ""}
                    </option>
                  ))}
              </Sel>
            )}
          </div>
        )}
      </div>

      {error && <ErrorBox message={error} />}
      {loadingMain && <div className="space-y-3"><Skeleton className="h-24 rounded-xl" /><Skeleton className="h-48 rounded-xl" /></div>}

      {/* ════ MASTER SUMMARY ════ */}
      {!loadingMain && viewMode === "master" && masterSummary && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard title="Total Planned Value" value={fmt(masterSummary.total_planned)} icon={FileSpreadsheet} color="bg-primary/10 text-primary" />
            <StatCard title="Sites" value={masterSummary.site_count} icon={Building2} color="bg-warning/10 text-warning" />
            <StatCard title="Total Lots / Units" value={masterSummary.total_lot_count} icon={Users} color="bg-success/10 text-success" />
          </div>

          <TypeCards
            material={masterSummary.material_total}
            labour={masterSummary.labour_total}
            plant={masterSummary.plant_total}
            service={masterSummary.service_total}
          />

          <div>
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              {masterSummary.sites.every((s: { site_id: string | null }) => !s.site_id)
                ? "Lots / Units"
                : "Sites & Groupings"}
            </h2>
            {masterSummary.sites.length === 0 ? (
              <div className="bg-card border border-border rounded-xl p-10 text-center text-sm text-muted-foreground">
                No BOQ data yet. Create a BOQ template and apply it to lots.
              </div>
            ) : (
              <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
                <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto] gap-3 px-4 py-2.5 bg-muted/40 text-xs font-semibold text-muted-foreground uppercase">
                  <span>Group</span><span className="text-center">Lots</span>
                  <span className="text-right">Unit Total</span><span className="text-right">Total</span>
                  <span className="text-right">Variance</span><span />
                </div>
                {masterSummary.sites.map((site: { site_id: string | null; site_name: string; lot_count: number; has_boq: boolean; unit_total: number; site_total: number; variance_pct: number | null; variance_amount: number | null; is_freestanding?: boolean }) => (
                  <div key={site.site_id ?? "__freestanding__"} className="grid grid-cols-[1fr_auto_auto_auto_auto_auto] gap-3 px-4 py-3 bg-card items-center hover:bg-muted/20">
                    <div>
                      <p className="text-sm font-medium flex items-center gap-1.5">
                        {site.site_name}
                        {site.is_freestanding && (
                          <span className="text-xs text-muted-foreground font-normal italic">(freestanding)</span>
                        )}
                      </p>
                      {!site.has_boq && <p className="text-xs text-amber-600 mt-0.5">No BOQ yet</p>}
                    </div>
                    <span className="text-sm text-center tabular-nums font-medium">{site.lot_count}</span>
                    <span className="text-sm text-right tabular-nums">{site.has_boq ? fmt(site.unit_total) : "—"}</span>
                    <span className="text-sm text-right tabular-nums font-semibold text-primary">{site.has_boq ? fmt(site.site_total) : "—"}</span>
                    <div className="text-right"><VariancePill pct={site.variance_pct} amount={site.variance_amount} /></div>
                    {site.is_freestanding || !site.site_id ? (
                      <Button size="sm" variant="outline" onClick={() => {
                        setFreestandingMode(true);
                        setSelectedSiteId("");
                        changeMode("lot");
                      }}>
                        View Lots <ChevronRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => {
                        setFreestandingMode(false);
                        setSelectedSiteId(site.site_id!);
                        changeMode("site");
                      }}>
                        View Site <ChevronRight className="w-3.5 h-3.5 ml-1" />
                      </Button>
                    )}
                  </div>
                ))}
                <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto] gap-3 px-4 py-3 bg-muted/30 items-center">
                  <span className="text-sm font-semibold">Total</span>
                  <span className="text-sm text-center font-semibold">{masterSummary.total_lot_count}</span>
                  <span /><span className="text-sm text-right font-bold text-primary tabular-nums">{fmt(masterSummary.total_planned)}</span>
                  <span /><span />
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ════ SITE BOQ ════ */}
      {!loadingMain && viewMode === "site" && (
        <>
          {!selectedSiteId ? (
            <div className="bg-card border border-border rounded-xl p-10 text-center text-sm text-muted-foreground">Select a site above.</div>
          ) : siteSummary ? (
            <div className="space-y-5">
              <div className="bg-card border border-border rounded-xl px-5 py-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs text-muted-foreground">Site BOQ</p>
                  <h2 className="text-lg font-bold">{siteSummary.site_name}</h2>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    {siteSummary.lot_count} lots · {siteSummary.item_count} items ·
                    Unit: <span className="font-semibold text-foreground">{fmt(siteSummary.unit_total)}</span> ·
                    Site: <span className="font-semibold text-foreground">{fmt(siteSummary.site_total)}</span>
                    {siteSummary.variance_pct !== 0 && (
                      <> · <VariancePill pct={siteSummary.variance_pct} amount={siteSummary.variance_amount} /></>
                    )}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={handleGenerateLotBoqs}>
                    <Package className="w-3.5 h-3.5 mr-1" />Generate Lot BOQs
                  </Button>
                  {siteSummary.boq_header_ids.length > 0 && (
                    <Button size="sm" onClick={() => navigate(`/boq/${selectedProjectId}/${siteSummary.boq_header_ids[0]}/build`)}>
                      <Wrench className="w-3.5 h-3.5 mr-1" />Edit Site BOQ
                    </Button>
                  )}
                </div>
              </div>

              <TypeCards material={siteSummary.material_total} labour={siteSummary.labour_total} plant={siteSummary.plant_total} service={siteSummary.service_total} />

              <SiteBOQTable summary={siteSummary} />

              <div>
                <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Lots / Units</h2>
                {siteLots.length === 0 ? (
                  <div className="bg-card border border-border rounded-xl p-8 text-center text-sm text-muted-foreground">No lots found.</div>
                ) : (
                  <div className="border border-border rounded-xl overflow-hidden">
                    <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] gap-2 px-4 py-2.5 bg-muted/40 text-xs font-semibold text-muted-foreground uppercase">
                      <span>Lot</span><span className="text-right">Total</span><span className="text-right">Material</span>
                      <span className="text-right">Labour</span><span className="text-center">Custom</span>
                      <span className="text-right">Variance</span><span />
                    </div>
                    {siteLots.map((lot) => (
                      <div key={lot.lot_id} className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] gap-2 px-4 py-2.5 bg-card border-t border-border items-center hover:bg-muted/20">
                        <span className="text-sm font-medium">{lot.lot_number}</span>
                        <span className="text-sm text-right tabular-nums font-medium">{lot.has_lot_boq ? fmt(lot.lot_total) : "—"}</span>
                        <span className="text-sm text-right tabular-nums text-muted-foreground">{fmt(lot.material_total)}</span>
                        <span className="text-sm text-right tabular-nums text-muted-foreground">{fmt(lot.labour_total)}</span>
                        <div className="flex justify-center">
                          {lot.has_custom_boq
                            ? <Badge variant="outline" className="text-xs text-amber-600 border-amber-300">Custom</Badge>
                            : lot.has_lot_boq ? <CheckCircle2 className="w-4 h-4 text-success" /> : <span className="text-xs text-muted-foreground">—</span>}
                        </div>
                        <div className="text-right"><VariancePill pct={lot.variance_pct} amount={lot.variance_amount} /></div>
                        <Button size="sm" variant="outline" className="h-7 text-xs"
                          onClick={() => { setSelectedLotId(lot.lot_id); changeMode("lot"); }}>
                          Edit
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : !error && (
            <div className="bg-card border border-border rounded-xl p-10 text-center text-sm text-muted-foreground">Select a site to load its BOQ.</div>
          )}
        </>
      )}

      {/* ════ LOT BOQ ════ */}
      {!loadingMain && viewMode === "lot" && (
        <>
          {!selectedSiteId ? (
            <div className="bg-card border border-border rounded-xl p-10 text-center text-sm text-muted-foreground">Select a site first.</div>
          ) : !selectedLotId ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground px-1">Select a lot from the dropdown, or click one below.</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {siteLots.map((lot) => (
                  <button key={lot.lot_id} onClick={() => setSelectedLotId(lot.lot_id)}
                    className="bg-card border border-border rounded-xl p-4 text-left hover:border-primary/40 hover:bg-primary/5 transition-colors">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-semibold text-sm">{lot.lot_number}</span>
                      {lot.has_custom_boq && <Badge variant="outline" className="text-xs text-amber-600 border-amber-300">Custom</Badge>}
                    </div>
                    <p className="text-sm text-primary font-medium">{lot.has_lot_boq ? fmt(lot.lot_total) : "No BOQ yet"}</p>
                    <div className="flex gap-3 mt-1.5 text-xs text-muted-foreground">
                      <span>Mat: {fmt(lot.material_total)}</span>
                      <span>Lab: {fmt(lot.labour_total)}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : (() => {
            const lotRow  = siteLots.find((l) => l.lot_id === selectedLotId);
            const lotMeta = siteLotMap[selectedLotId];
            const headerId = lotRow?.boq_header_ids[0] ?? siteSummary?.boq_header_ids[0] ?? null;
            return (
              <div className="space-y-4">
                <div className="bg-card border border-border rounded-xl px-5 py-4 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant="outline" className="text-xs">Lot-specific</Badge>
                      {lotRow?.has_custom_boq && <Badge variant="outline" className="text-xs text-amber-600 border-amber-300">Custom changes</Badge>}
                    </div>
                    <h2 className="text-lg font-bold">Lot {lotMeta?.lot_number ?? selectedLotId.slice(0, 8)}</h2>
                    {lotRow && (
                      <p className="text-sm text-muted-foreground mt-0.5">
                        {lotRow.item_count} items · {fmt(lotRow.lot_total)}
                        {lotRow.variance_pct !== 0 && <> · <VariancePill pct={lotRow.variance_pct} amount={lotRow.variance_amount} /></>}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" disabled={resetBusy} onClick={() => handleResetLot(selectedLotId)}>
                      <RotateCcw className={`w-3.5 h-3.5 mr-1 ${resetBusy ? "animate-spin" : ""}`} />Reset to Site BOQ
                    </Button>
                    <Button size="sm" disabled={!headerId}
                      onClick={() => headerId && navigate(`/boq/${selectedProjectId}/${headerId}/build`)}>
                      <ExternalLink className="w-3.5 h-3.5 mr-1" />Edit in Builder
                    </Button>
                  </div>
                </div>

                {lotRow && <TypeCards material={lotRow.material_total} labour={lotRow.labour_total} plant={lotRow.plant_total} service={lotRow.service_total} />}

                {lotRow && !lotRow.has_lot_boq && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800 flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                    This lot has no dedicated BOQ yet.
                    Apply a template from the <strong>BOQ Templates</strong> page to populate all lots,
                    or switch to <strong>Site BOQ</strong> mode and click <strong>Generate Lot BOQs</strong>.
                  </div>
                )}

                {headerId && lotRow?.has_lot_boq && (
                  <div className="bg-card border border-border rounded-xl px-5 py-4 flex items-center gap-4">
                    <FileSpreadsheet className="w-5 h-5 text-primary shrink-0" />
                    <div className="flex-1">
                      <p className="font-medium text-sm">{lotRow.item_count} BOQ items · {fmt(lotRow.lot_total)}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">Click <strong>Edit in Builder</strong> to edit all line items.</p>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => navigate(`/boq/${selectedProjectId}/${headerId}/build`)}>
                      <Wrench className="w-3.5 h-3.5 mr-1" />Open Builder
                    </Button>
                  </div>
                )}
              </div>
            );
          })()}
        </>
      )}

      {/* ════ TEMPLATES ════ */}
      {viewMode === "templates" && <BOQTemplatesInner />}

      {!selectedProjectId && !loadingProjects && viewMode !== "templates" && (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">Select a project to get started.</div>
      )}
    </div>
  );
}
