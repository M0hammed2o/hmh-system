import { useState, useEffect, useCallback, useRef, Component } from "react";
import type { ReactNode, ErrorInfo } from "react";
import {
  LogOut, RefreshCw, PackagePlus, Truck, Minus,
  ListChecks, Upload, PenLine, AlertTriangle, CheckCircle2,
  Clock, Circle, ChevronRight, Box, Bell, Camera, Image, X,
  Plus, Trash2, ClipboardList, Flag, Ban, Lock, CalendarClock,
  ShieldOff, Briefcase, RotateCcw, Search, FileSpreadsheet,
  Home, Warehouse, ArrowRightLeft, Wrench,
} from "lucide-react";
import { siteCaptureApi, type ExtractedItem } from "@/api/siteCapture";
import { siteDashboardApi, type MaterialSummaryItem, type ActivityItem } from "@/api/siteDashboard";
import { BOQAllocationTable } from "@/components/site/BOQAllocationTable";
import { ProjectWarehouse } from "@/components/site/ProjectWarehouse";
import { HMHLogo } from "@/components/HMHLogo";
import { TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY, SITE_ROLE_SET } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { lotsApi, type Lot } from "@/api/lots";
import { materialRequestsApi, type MaterialRequest } from "@/api/materialRequests";
import { deliveriesApi, type Delivery } from "@/api/deliveries";
import { stagesApi, type ProjectStageStatus, type StageMaster, type MilestonePhoto } from "@/api/stages";
import { alertsApi, type Alert } from "@/api/alerts";
import { stockApi, type StockBalance, type StockLedgerEntry } from "@/api/stock";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { warehouseApi } from "@/api/warehouse";
import { jobCardsApi, type JobCard } from "@/api/jobCards";
import { getDrafts, removeDraft, type OfflineDraft } from "@/utils/offlineDrafts";
import { procurementApi, type BOQSearchResult } from "@/api/procurement";
import { cn } from "@/lib/utils";

// ── Error boundary — prevents any modal crash from blanking the whole page ────
class ModalErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: ReactNode; fallback?: ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ModalErrorBoundary] render error:", error, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="bg-destructive/10 border border-destructive/30 rounded-xl p-4 text-sm text-destructive space-y-2">
          <p className="font-semibold">Something went wrong inside this modal.</p>
          <p className="text-xs font-mono break-all">{this.state.error.message}</p>
          <p className="text-xs text-muted-foreground">
            Check the browser console for the full stack trace.
            Close and reopen the modal to try again.
          </p>
          {this.props.fallback}
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Storage keys ──────────────────────────────────────────────────────────────
const SK_PROJECT = "site_project_id";
const SK_SITE    = "site_site_id";
const SK_LOT     = "site_lot_id";

// ── Helpers ───────────────────────────────────────────────────────────────────
const todayStr = () => new Date().toISOString().split("T")[0];

const STAGE_LABEL: Record<string, string> = {
  NOT_STARTED:         "Not Started",
  IN_PROGRESS:         "In Progress",
  BLOCKED:             "Blocked",
  AWAITING_INSPECTION: "Awaiting Inspection",
  COMPLETED:           "Completed",
  CERTIFIED:           "Certified",
};

const STAGE_COLOR: Record<string, string> = {
  NOT_STARTED:         "text-muted-foreground",
  IN_PROGRESS:         "text-blue-600",
  AWAITING_INSPECTION: "text-amber-600",
  COMPLETED:           "text-green-600",
  CERTIFIED:           "text-emerald-600",
};

const SEV_BADGE: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-700 border-red-200",
  HIGH:     "bg-orange-100 text-orange-700 border-orange-200",
  MEDIUM:   "bg-amber-100 text-amber-700 border-amber-200",
  LOW:      "bg-gray-100 text-gray-600 border-gray-200",
};

function fmt(n: number | null | undefined, unit = ""): string {
  if (n == null) return "—";
  const s = n % 1 === 0 ? String(n) : n.toFixed(1);
  return unit ? `${s} ${unit}` : s;
}

function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ── Reusable UI atoms ─────────────────────────────────────────────────────────

function Select({ value, onChange, children, disabled = false }: {
  value: string; onChange: (v: string) => void;
  children: React.ReactNode; disabled?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      disabled={disabled}
      className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card text-foreground
                 focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
    >
      {children}
    </select>
  );
}

function StatCard({ label, value, accent = false, sub = "" }: {
  label: string; value: number; accent?: boolean; sub?: string;
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-3">
      <p className="text-xs text-muted-foreground mb-0.5">{label}</p>
      <p className={cn("text-2xl font-bold", accent && value > 0 ? "text-amber-600" : "")}>{value}</p>
      {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}

function ActionBtn({ icon: Icon, label, onClick }: {
  icon: React.ElementType; label: string; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center justify-center gap-1.5 p-3 rounded-xl border border-border
                 bg-muted/40 hover:bg-muted text-foreground text-xs font-medium transition-colors"
    >
      <Icon className="w-5 h-5" />
      <span className="text-center leading-tight">{label}</span>
    </button>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">{title}</h2>
      {children}
    </section>
  );
}

function ModalShell({ title, onClose, children }: {
  title: string; onClose: () => void; children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end sm:items-center justify-center">
      <div className="w-full sm:max-w-md bg-card rounded-t-2xl sm:rounded-2xl shadow-xl max-h-[92vh] overflow-y-auto">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border sticky top-0 bg-card z-10">
          <h3 className="font-semibold text-sm">{title}</h3>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-muted text-muted-foreground"
          >
            ✕
          </button>
        </div>
        <div className="p-4 space-y-4">{children}</div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
type ModalType = "request" | "delivery" | "usage" | "stage" | "jobcard" | "add_warehouse" | "warehouse_transfer" | null;

// Virtual sentinel used for the view-only Global Main Warehouse option
const MAIN_WAREHOUSE_SENTINEL = "__main_warehouse__";

export default function SiteDashboardPage() {

  // ── Role check ──
  const userRole   = localStorage.getItem(ROLE_KEY) ?? "";
  const isViewOnly = userRole === "SITE_MANAGER_VIEW";
  const isSiteUser = userRole === "SITE_STAFF" || userRole === "SITE_MANAGER" || userRole === "SITE_MANAGER_VIEW";

  // ── Selection (persisted) ──
  const [projectId, setProjectId] = useState(localStorage.getItem(SK_PROJECT) || "");
  const [siteId,    setSiteId]    = useState(localStorage.getItem(SK_SITE)    || "");
  const [lotId,     setLotId]     = useState(localStorage.getItem(SK_LOT)     || "");

  // ── Reference data ──
  const [projects,     setProjects]     = useState<Project[]>([]);
  const [sites,        setSites]        = useState<Site[]>([]);
  const [lots,         setLots]         = useState<Lot[]>([]);
  const [suppliers,    setSuppliers]    = useState<Supplier[]>([]);
  const [stageMasters, setStageMasters] = useState<StageMaster[]>([]);

  // ── Live data ──
  const [mrs,       setMrs]       = useState<MaterialRequest[]>([]);
  const [siteRequests, setSiteRequests] = useState<MaterialRequest[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [stages,    setStages]    = useState<ProjectStageStatus[]>([]);
  const [alerts,    setAlerts]    = useState<Alert[]>([]);
  const [balances,        setBalances]        = useState<StockBalance[]>([]);
  const [ledger,          setLedger]          = useState<StockLedgerEntry[]>([]);
  const [materialSummary, setMaterialSummary] = useState<MaterialSummaryItem[]>([]);
  const [activity,        setActivity]        = useState<ActivityItem[]>([]);

  const [jobCards,          setJobCards]          = useState<JobCard[]>([]);
  const [stagePhotos,       setStagePhotos]       = useState<MilestonePhoto[]>([]);
  const [pwMaterialSummary, setPwMaterialSummary] = useState<MaterialSummaryItem[]>([]);
  const [pwMainStock,       setPwMainStock]       = useState<import("@/api/warehouse").WarehouseStockItem[]>([]);
  const [offlineDrafts, setOfflineDrafts] = useState<OfflineDraft[]>(getDrafts);
  const [discardConfirm, setDiscardConfirm] = useState(false);
  const [syncingDrafts, setSyncingDrafts] = useState(false);

  const [loading,  setLoading]  = useState(false);
  const [loadErr,  setLoadErr]  = useState("");
  const [modal,    setModal]    = useState<ModalType>(null);

  // ── Persist selection changes ──
  const selectProject = (id: string) => {
    setProjectId(id); localStorage.setItem(SK_PROJECT, id);
    setSiteId(""); localStorage.removeItem(SK_SITE);
    setLotId("");  localStorage.removeItem(SK_LOT);
    setMrs([]); setDeliveries([]); setAlerts([]);
    setBalances([]); setLedger([]); setStages([]); setJobCards([]);
  };
  const selectSite = (id: string) => {
    setSiteId(id); localStorage.setItem(SK_SITE, id);
    setLotId(""); localStorage.removeItem(SK_LOT);
  };
  const selectLot = (id: string) => {
    setLotId(id); localStorage.setItem(SK_LOT, id);
  };

  // ── Load reference data once ──
  useEffect(() => {
    projectsApi.list(1, 100).then(r => {
      setProjects(r.items);
      const validIds = new Set(r.items.map((p: Project) => p.id));

      // Wipe stale localStorage selection if the stored project is no longer accessible
      if (projectId && !validIds.has(projectId)) {
        setProjectId(""); setSiteId(""); setLotId("");
        localStorage.removeItem(SK_PROJECT);
        localStorage.removeItem(SK_SITE);
        localStorage.removeItem(SK_LOT);
        if (isSiteUser && r.items.length === 1) {
          setProjectId(r.items[0].id);
          localStorage.setItem(SK_PROJECT, r.items[0].id);
        }
        return;
      }

      // Auto-select the only accessible project on first visit
      if (isSiteUser && r.items.length === 1 && !projectId) {
        setProjectId(r.items[0].id);
        localStorage.setItem(SK_PROJECT, r.items[0].id);
      }
    }).catch(() => {});
    stagesApi.listMasters().then(setStageMasters).catch(() => {});
    suppliersApi.list().then(setSuppliers).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load sites + lots when project changes ──
  useEffect(() => {
    if (!projectId) { setSites([]); setLots([]); return; }
    sitesApi.list(projectId).then(s => {
      setSites(s);
      // Freestanding lot support: if project has exactly one site, auto-select it
      if (s.length === 1 && !siteId) {
        setSiteId(s[0].id);
        localStorage.setItem(SK_SITE, s[0].id);
      }
    }).catch(() => {});
    lotsApi.list(projectId).then(setLots).catch(() => {});
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Derived: is the selected site the Project Warehouse? ──
  const isWarehouse = !!siteId && !!sites.find(s => s.id === siteId && s.site_type === "warehouse");

  // ── Load live data ──
  const loadData = useCallback(() => {
    if (!projectId) return;

    // Main Warehouse sentinel: only fetch global stock, skip all project APIs
    if (projectId === MAIN_WAREHOUSE_SENTINEL) {
      warehouseApi.getGlobalStock()
        .then(setPwMainStock).catch(() => setPwMainStock([]));
      return;
    }

    setLoading(true);
    setLoadErr("");

    const stageParams = lotId  ? { lot_id: lotId }
                      : siteId ? { site_id: siteId }
                      : {};

    Promise.all([
      materialRequestsApi.list(projectId).catch((): MaterialRequest[]    => []),
      deliveriesApi.list(projectId, siteId || undefined).catch((): Delivery[] => []),
      alertsApi.list({ project_id: projectId, limit: 50 }).catch((): Alert[] => []),
      siteId
        ? stockApi.getBalances(projectId, siteId).catch((): StockBalance[] => [])
        : Promise.resolve([] as StockBalance[]),
      siteId
        ? stockApi.getLedger(projectId, { site_id: siteId, limit: 40 }).catch((): StockLedgerEntry[] => [])
        : Promise.resolve([] as StockLedgerEntry[]),
      Object.keys(stageParams).length
        ? stagesApi.listProjectStatuses(projectId, stageParams).catch((): ProjectStageStatus[] => [])
        : Promise.resolve([] as ProjectStageStatus[]),
    ]).then(([m, d, a, b, l, s]) => {
      setMrs(m);
      setDeliveries(d);
      setAlerts(a);
      setBalances(b);
      setLedger(l);
      setStages(s);
    }).catch(() => setLoadErr("Failed to load site data. Pull down to retry."))
      .finally(() => setLoading(false));

    // Material summary + activity (lot-specific, best-effort)
    if (siteId && lotId) {
      siteDashboardApi.getMaterialSummary(siteId, lotId)
        .then(setMaterialSummary).catch(() => setMaterialSummary([]));
      siteDashboardApi.getActivity(siteId, lotId)
        .then(setActivity).catch(() => setActivity([]));
    } else {
      setMaterialSummary([]);
      setActivity([]);
    }

    // Site-specific request history
    if (siteId) {
      materialRequestsApi.list(projectId, { site_id: siteId })
        .then(setSiteRequests).catch(() => setSiteRequests([]));
    } else {
      setSiteRequests([]);
    }

    // Job cards (best-effort, site-filtered when site selected)
    if (siteId) {
      jobCardsApi.list(projectId, undefined, undefined, siteId)
        .then(setJobCards).catch(() => setJobCards([]));
    } else {
      jobCardsApi.list(projectId)
        .then(jcs => setJobCards(jcs.slice(0, 20))).catch(() => setJobCards([]));
    }

    // Project Warehouse material summary (only when a warehouse site is selected)
    const _isWarehouse = !!siteId && !!sites.find(s => s.id === siteId && s.site_type === "warehouse");
    if (_isWarehouse) {
      warehouseApi.getWarehouseMaterialSummary(projectId)
        .then(setPwMaterialSummary).catch(() => setPwMaterialSummary([]));
    } else {
      setPwMaterialSummary([]);
    }

    // Global Main Warehouse view-only
    if (projectId === MAIN_WAREHOUSE_SENTINEL) {
      warehouseApi.getGlobalStock()
        .then(setPwMainStock).catch(() => setPwMainStock([]));
    } else {
      setPwMainStock([]);
    }
  }, [projectId, siteId, lotId, sites]);

  useEffect(() => { loadData(); }, [loadData]);

  // ── Load stage photos whenever stages change ──
  useEffect(() => {
    if (!projectId || stages.length === 0) { setStagePhotos([]); return; }
    Promise.all(stages.map(s => stagesApi.listPhotos(projectId, s.id).catch(() => [])))
      .then(results => setStagePhotos(results.flat()))
      .catch(() => setStagePhotos([]));
  }, [stages, projectId]);

  // ── Sync offline drafts ──
  const syncDrafts = async () => {
    if (offlineDrafts.length === 0) return;
    setSyncingDrafts(true);
    const { removeDraft: _remove } = await import("@/utils/offlineDrafts");
    const remaining: OfflineDraft[] = [];
    for (const draft of offlineDrafts) {
      try {
        if (draft.type === "material_request") {
          const { items, neededBy, notes } = draft.payload as {
            items: Array<{ desc: string; qty: string; unit: string }>;
            neededBy: string; notes: string;
          };
          const mr = await materialRequestsApi.create(draft.projectId, {
            site_id: draft.siteId || null,
            lot_id:  draft.lotId  || null,
            delivery_destination: "SITE_STORE",
            needed_by_date: neededBy || null,
            notes:          notes    || null,
            items: items.map(r => ({
              description:        r.desc.trim(),
              requested_quantity: parseFloat(r.qty),
              unit:               r.unit.trim() || null,
            })),
          });
          await materialRequestsApi.submit(mr.id);
          _remove(draft.id);
        } else {
          remaining.push(draft);
        }
      } catch {
        remaining.push(draft);
      }
    }
    setOfflineDrafts(getDrafts());
    setSyncingDrafts(false);
    if (remaining.length < offlineDrafts.length) loadData();
  };

  // ── Computed summary ──
  const openMRs      = mrs.filter(m => m.status === "DRAFT" || m.status === "SUBMITTED").length;
  const partialDels  = deliveries.filter(d => d.delivery_status === "PARTIALLY_RECEIVED").length;
  const activeStages = stages.filter(s => s.status === "IN_PROGRESS").length;
  const openAlerts   = alerts.filter(a => a.status === "OPEN");
  const criticalOpen = openAlerts.filter(a => a.severity === "CRITICAL" || a.severity === "HIGH");

  // ── Lot materials (stock balances filtered by lot) ──
  const matRows = lotId
    ? balances.filter(b => b.lot_id === lotId)
    : siteId ? balances : [];

  // ── Stage timeline ──
  const stageRows = [...stages]
    .filter(s => !lotId || s.lot_id === lotId)
    .sort((a, b) => (a.sequence_order ?? 99) - (b.sequence_order ?? 99));

  // ── Recent activity (usage + alerts only — deliveries have their own section) ──
  type LegacyActivity = { id: string; label: string; sub: string; date: string; kind: "use" | "alert" };
  const legacyActivity: LegacyActivity[] = [
    ...ledger.filter(e => e.movement_type === "USAGE").slice(0, 8).map(e => ({
      id: e.id, kind: "use" as const,
      label: "Usage recorded",
      sub: fmt(e.quantity_out, e.unit || ""),
      date: e.movement_date,
    })),
    ...openAlerts.slice(0, 5).map(a => ({
      id: a.id, kind: "alert" as const,
      label: a.title,
      sub: a.severity,
      date: a.created_at,
    })),
  ].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
   .slice(0, 15);

  // ── Logout ──
  const handleLogout = () => {
    [TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY].forEach(k => localStorage.removeItem(k));
    window.location.href = "/site-login";
  };

  // ─────────────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-background pb-10">

      {/* Header */}
      <header className="sticky top-0 z-30 bg-card/90 backdrop-blur border-b border-border px-4 py-3
                          flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <HMHLogo size="sm" />
          {isViewOnly && (
            <span className="flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-md
                             bg-amber-100 text-amber-800 border border-amber-200 shrink-0">
              <ShieldOff className="w-2.5 h-2.5" />
              View Only
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 rounded-md hover:bg-muted text-muted-foreground disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
          </button>
          <button
            onClick={handleLogout}
            className="p-2 rounded-md hover:bg-muted text-muted-foreground"
            title="Log out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </header>

      <div className="px-4 pt-4 space-y-5 max-w-2xl mx-auto">

        {/* ── Selectors ── */}
        <div className="space-y-2">
          {/* Project: locked for site users with only 1 project */}
          {isSiteUser && projects.length <= 1 && projectId ? (
            <div className="w-full h-10 px-3 flex items-center text-sm rounded-lg border border-border bg-muted/40 text-foreground font-medium">
              {projects.find(p => p.id === projectId)?.name ?? "Project"}
            </div>
          ) : (
            <Select value={projectId} onChange={selectProject}>
              <option value="">— Select project —</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              <option value={MAIN_WAREHOUSE_SENTINEL}>🏭 Main Warehouse (view only)</option>
            </Select>
          )}

          {/* Location: sites including Project Warehouse */}
          {projectId && sites.length > 0 && (
            <Select value={siteId} onChange={selectSite} disabled={!projectId}>
              <option value="">— Select location —</option>
              {sites.map(s => (
                <option key={s.id} value={s.id}>
                  {s.site_type === "warehouse" ? `🏭 ${s.name}` : s.name}
                </option>
              ))}
            </Select>
          )}

          {/* Lot: hidden when Project Warehouse is selected */}
          {siteId && !isWarehouse && (
            <Select value={lotId} onChange={selectLot}>
              <option value="">— All units —</option>
              {lots
                .filter(l => !l.site_id || l.site_id === siteId)
                .sort((a, b) => {
                  const na = parseInt(a.lot_number), nb = parseInt(b.lot_number);
                  if (!isNaN(na) && !isNaN(nb)) return na - nb;
                  return a.lot_number.localeCompare(b.lot_number, undefined, { numeric: true, sensitivity: "base" });
                })
                .map(l => (
                  <option key={l.id} value={l.id}>
                    {l.lot_number}{l.unit_type ? ` · ${l.unit_type}` : ""}{l.block_number ? ` (Block ${l.block_number})` : ""}
                  </option>
                ))}
            </Select>
          )}
        </div>

        {!projectId && (
          <p className="text-center text-sm text-muted-foreground py-8">
            Select a project to begin.
          </p>
        )}

        {loadErr && (
          <div className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {loadErr}
          </div>
        )}

        {/* ── Offline draft queue banner ── */}
        {offlineDrafts.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5 space-y-2">
            <div className="flex items-center gap-3">
              <Upload className="w-4 h-4 text-amber-600 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-amber-800">
                  {offlineDrafts.length} offline draft{offlineDrafts.length > 1 ? "s" : ""} pending
                </p>
                <p className="text-xs text-amber-700">Saved while offline — sync or discard.</p>
              </div>
            </div>
            {discardConfirm ? (
              <div className="flex items-center gap-2">
                <p className="text-xs text-amber-800 flex-1">Discard all drafts? This cannot be undone.</p>
                <button
                  onClick={() => {
                    offlineDrafts.forEach(d => removeDraft(d.id));
                    setOfflineDrafts([]);
                    setDiscardConfirm(false);
                  }}
                  className="text-xs font-semibold text-red-700 px-2 py-1 bg-red-50 border border-red-200 rounded-md"
                >
                  Yes, discard
                </button>
                <button
                  onClick={() => setDiscardConfirm(false)}
                  className="text-xs font-medium text-amber-800 px-2 py-1 bg-white border border-amber-200 rounded-md"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={syncDrafts}
                  disabled={syncingDrafts}
                  className="flex items-center gap-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-60 px-3 py-1.5 rounded-lg transition-colors"
                >
                  <RotateCcw className={cn("w-3.5 h-3.5", syncingDrafts && "animate-spin")} />
                  {syncingDrafts ? "Syncing…" : "Sync Now"}
                </button>
                <button
                  onClick={() => setDiscardConfirm(true)}
                  className="text-xs font-medium text-amber-800 px-3 py-1.5 bg-white border border-amber-200 rounded-lg"
                >
                  Discard
                </button>
              </div>
            )}
          </div>
        )}

        {projectId && (
          <>
            {/* ── Today summary ── */}
            <Section title="Today">
              <div className="grid grid-cols-2 gap-2">
                <StatCard label="Open Requests"      value={openMRs}      accent={openMRs > 0} />
                <StatCard label="Partial Deliveries" value={partialDels}   accent={partialDels > 0} />
                <StatCard label="Stages Active"      value={activeStages} />
                <StatCard
                  label="Active Alerts"
                  value={openAlerts.length}
                  accent={openAlerts.length > 0}
                  sub={criticalOpen.length > 0 ? `${criticalOpen.length} critical/high` : ""}
                />
              </div>
            </Section>

            {/* Lot BOQ KPI cards are now rendered inside BOQAllocationTable */}

            {/* ── Critical/high alert banner ── */}
            {criticalOpen.length > 0 && (
              <Section title="Urgent Alerts">
                <div className="space-y-2">
                  {criticalOpen.slice(0, 3).map(a => (
                    <div key={a.id} className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl p-3">
                      <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-semibold text-red-700 truncate">{a.title}</p>
                        <p className="text-xs text-red-600 line-clamp-2 mt-0.5">{a.message}</p>
                      </div>
                      <span className={cn("text-xs px-1.5 py-0.5 rounded border shrink-0 font-medium", SEV_BADGE[a.severity])}>
                        {a.severity}
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* ── Quick actions ── */}
            <Section title="Quick Actions">
              <div className="grid grid-cols-3 gap-2">
                {/* Site / lot actions — hide when in warehouse mode or when a lot is selected */}
                {!isViewOnly && !isWarehouse && !lotId && <ActionBtn icon={PackagePlus} label="Request Materials" onClick={() => setModal("request")} />}
                {!isViewOnly && !isWarehouse && !lotId && <ActionBtn icon={Truck}       label="Receive Delivery"  onClick={() => setModal("delivery")} />}
                {!isViewOnly && !isWarehouse && <ActionBtn icon={Home}       label="Record Usage"     onClick={() => setModal("usage")} />}
                {!isViewOnly && !isWarehouse && <ActionBtn icon={ListChecks} label="Update Milestone" onClick={() => setModal("stage")} />}
                {!isViewOnly && siteId && !isWarehouse && <ActionBtn icon={Briefcase} label="Log Job Card" onClick={() => setModal("jobcard")} />}
                {!isWarehouse && (
                  <ActionBtn
                    icon={Flag}
                    label="View Milestones"
                    onClick={() => {
                      document.getElementById("milestones-section")?.scrollIntoView({ behavior: "smooth" });
                    }}
                  />
                )}
                {!isWarehouse && projectId && projectId !== MAIN_WAREHOUSE_SENTINEL && (
                  <ActionBtn
                    icon={FileSpreadsheet}
                    label="Invoices"
                    onClick={() => {
                      window.location.href = `/municipality-invoices?projectId=${projectId}`;
                    }}
                  />
                )}
                {/* Warehouse actions */}
                {!isViewOnly && isWarehouse && (
                  <ActionBtn icon={PackagePlus} label="Add to Warehouse" onClick={() => setModal("add_warehouse")} />
                )}
                {!isViewOnly && isWarehouse && (
                  <ActionBtn icon={ArrowRightLeft} label="Project Transfer" onClick={() => setModal("warehouse_transfer")} />
                )}
              </div>
              {isViewOnly && (
                <p className="text-xs text-muted-foreground mt-2 text-center">
                  View-only mode — write actions are disabled.
                </p>
              )}
            </Section>

            {/* ── Project Warehouse: BOQ Allocation (materials then tools) ── */}
            {isWarehouse && siteId && projectId && (
              <>
                <BOQAllocationTable
                  items={pwMaterialSummary.filter(i => !i.description.toLowerCase().startsWith("tool:"))}
                  loading={loading}
                  hideActions={true}
                  onRecordUsage={() => {}}
                  onReceiveDelivery={() => {}}
                />
                {/* Tools section at the bottom */}
                {pwMaterialSummary.filter(i => i.description.toLowerCase().startsWith("tool:")).length > 0 && (
                  <Section title="Tools">
                    <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
                      <div className="grid grid-cols-4 gap-2 px-3 py-2 bg-muted/50 text-xs font-medium text-muted-foreground">
                        <span className="col-span-2 flex items-center gap-1.5"><Wrench className="w-3.5 h-3.5" />Tool</span>
                        <span className="text-right">Allocated</span>
                        <span className="text-right">Remaining</span>
                      </div>
                      {pwMaterialSummary.filter(i => i.description.toLowerCase().startsWith("tool:")).map(row => (
                        <div key={row.boq_item_id} className="grid grid-cols-4 gap-2 px-3 py-2.5 bg-card items-center">
                          <div className="col-span-2 min-w-0">
                            <p className="text-sm font-medium truncate">{row.description.replace(/^tool:\s*/i, "")}</p>
                            <p className="text-xs text-muted-foreground">{row.unit ?? "—"}</p>
                          </div>
                          <p className="text-sm text-right font-mono">{row.boq_allocated_qty}</p>
                          <p className={cn("text-sm text-right font-mono font-semibold",
                            row.remaining_qty <= 0 ? "text-red-600" : row.status === "LOW" ? "text-amber-600" : "text-green-600"
                          )}>{row.remaining_qty}</p>
                        </div>
                      ))}
                    </div>
                  </Section>
                )}
              </>
            )}

            {/* ── Main Warehouse view-only ── */}
            {projectId === MAIN_WAREHOUSE_SENTINEL && (
              <Section title="Main Warehouse — Stock On Hand">
                {pwMainStock.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-6">No stock in the Main Warehouse.</p>
                ) : (
                  <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
                    <div className="grid grid-cols-3 gap-2 px-3 py-2 bg-muted/50 text-xs font-medium text-muted-foreground">
                      <span className="col-span-2">Item</span>
                      <span className="text-right">On Hand</span>
                    </div>
                    {pwMainStock.map(row => (
                      <div key={row.item_id} className="grid grid-cols-3 gap-2 px-3 py-2.5 bg-card items-center">
                        <div className="col-span-2 min-w-0">
                          <p className="text-sm font-medium truncate">{row.item_name}</p>
                          <p className="text-xs text-muted-foreground">{row.unit ?? "—"}</p>
                        </div>
                        <p className="text-sm text-right font-mono font-semibold">{row.on_hand}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Section>
            )}

            {/* ── BOQ Allocation / Usage / Remaining (site lots only) ── */}
            {!isWarehouse && siteId && lotId && (
              <BOQAllocationTable
                items={materialSummary}
                loading={loading}
                fromSiteTemplate={materialSummary[0]?.from_site_template ?? false}
                onRecordUsage={() => setModal("usage")}
                onReceiveDelivery={() => setModal("delivery")}
              />
            )}

            {/* ── Site Stock (fallback when no lot selected, non-warehouse) ── */}
            {!isWarehouse && siteId && !lotId && matRows.length > 0 && (
              <Section title="Site Stock">
                <div className="space-y-2">
                  {matRows.map(b => {
                    const isOver = b.balance < 0;
                    const isLow  = b.balance > 0 && b.balance <= 5;
                    const isZero = b.balance === 0;
                    return (
                      <div key={`${b.item_id}-${b.lot_id ?? "site"}`}
                        className={cn("flex items-center justify-between p-3 rounded-xl border",
                          isOver ? "bg-red-50 border-red-200" : isZero ? "bg-amber-50 border-amber-200" : isLow ? "bg-orange-50 border-orange-200" : "bg-card border-border"
                        )}>
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{b.item_name ?? "Unknown"}</p>
                          <p className="text-xs text-muted-foreground">{isOver ? "Over-issued" : isZero ? "Out of stock" : isLow ? "Low stock" : "Available"}</p>
                        </div>
                        <div className="text-right shrink-0 ml-3">
                          <p className={cn("text-xl font-bold", isOver ? "text-red-600" : isZero || isLow ? "text-amber-600" : "text-green-600")}>
                            {fmt(b.balance, b.item_unit ?? "")}
                          </p>
                          {isOver && <p className="text-xs font-semibold text-red-600">⚠ Over BOQ</p>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Section>
            )}

            {/* ── My Requests — view status of submitted requests ── */}
            {siteId && (
              <SiteRequestHistory requests={siteRequests} />
            )}

            {/* ── Milestones / Stage timeline (site lots only) ── */}
            {!isWarehouse && siteId && stageMasters.length > 0 && (
              <section id="milestones-section">
              <Section title="Milestones">
                <div className="space-y-2">
                  {stageMasters.map(m => {
                    const s = stageRows.find(r => r.stage_id === m.id);
                    const status   = s?.status ?? "NOT_STARTED";
                    const progress = s?.progress_pct ?? 0;
                    return (
                    <div key={m.id} className="flex items-center gap-3 p-3 bg-card border border-border rounded-xl">
                      <div className="shrink-0">
                        {status === "COMPLETED" || status === "CERTIFIED"
                          ? <CheckCircle2 className="w-5 h-5 text-green-500" />
                          : status === "IN_PROGRESS"
                          ? <Clock className="w-5 h-5 text-blue-500" />
                          : status === "AWAITING_INSPECTION"
                          ? <AlertTriangle className="w-5 h-5 text-amber-500" />
                          : <Circle className="w-5 h-5 text-muted-foreground/50" />
                        }
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{m.name}</p>
                        <p className={cn("text-xs", STAGE_COLOR[status] ?? "text-muted-foreground")}>
                          {STAGE_LABEL[status] ?? status}
                          {status === "IN_PROGRESS" && progress > 0 && ` · ${progress}%`}
                        </p>
                        {s?.started_at && (
                          <p className="text-xs text-muted-foreground">
                            Started {shortDate(s.started_at)}
                          </p>
                        )}
                        {status === "IN_PROGRESS" && progress > 0 && (
                          <div className="mt-1.5 h-1.5 w-full bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-500 rounded-full transition-all"
                              style={{ width: `${progress}%` }}
                            />
                          </div>
                        )}
                      </div>
                      {!isViewOnly && (
                        <button
                          onClick={() => setModal("stage")}
                          className="shrink-0 p-1 rounded hover:bg-muted"
                          title="Update stage"
                        >
                          <ChevronRight className="w-4 h-4 text-muted-foreground" />
                        </button>
                      )}
                    </div>
                  ); })}
                </div>
              </Section>
              </section>
            )}

            {/* ── Recent activity ── */}
            <Section title="Recent Activity">
              {(() => {
                // Use API activity when lot is selected, otherwise legacy computed list
                const items = (lotId && activity.length > 0)
                  ? activity.map(a => ({
                      key:   a.title + (a.date ?? ""),
                      icon:  a.type === "delivery" ? <Truck className="w-4 h-4 text-blue-500 shrink-0" />
                           : a.type === "usage"    ? <Box   className="w-4 h-4 text-purple-500 shrink-0" />
                           : a.type === "stage"    ? <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                           :                         <Bell  className="w-4 h-4 text-amber-500 shrink-0" />,
                      label: a.title,
                      sub:   a.status ?? "",
                      date:  a.date ?? "",
                    }))
                  : legacyActivity.map(a => ({
                      key:   a.id,
                      icon:  a.kind === "use" ? <Box  className="w-4 h-4 text-purple-500 shrink-0" />
                                              : <Bell className="w-4 h-4 text-amber-500 shrink-0" />,
                      label: a.label,
                      sub:   a.sub,
                      date:  a.date,
                    }));
                if (items.length === 0) return (
                  <div className="text-sm text-muted-foreground bg-muted/40 rounded-xl p-4 text-center">No recent activity.</div>
                );
                return (
                  <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
                    {items.map(a => (
                      <div key={a.key} className="flex items-center gap-3 px-3 py-2.5 bg-card">
                        {a.icon}
                        <div className="min-w-0 flex-1">
                          <p className="text-sm truncate">{a.label}</p>
                          {a.sub && <p className="text-xs text-muted-foreground">{a.sub}</p>}
                        </div>
                        <span className="text-xs text-muted-foreground shrink-0">{shortDate(a.date)}</span>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </Section>

            {/* ── Delivery History ── */}
            {deliveries.length > 0 && (
              <Section title="Delivery History">
                <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
                  {deliveries.slice(0, 10).map(d => (
                    <div key={d.id} className="flex items-center gap-3 px-3 py-2.5 bg-card">
                      <Truck className="w-4 h-4 text-blue-500 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">
                          {d.delivery_number || `DEL-${d.id.slice(0, 8)}`}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {d.delivery_status.replace(/_/g, " ")}
                          {(d.driver_name ?? (d.ocr_raw_data as { driver_name?: string } | null)?.driver_name) && (
                            <span> · Driver: {d.driver_name ?? (d.ocr_raw_data as { driver_name?: string } | null)?.driver_name}</span>
                          )}
                          {d.receiver_name && <span> · Recv: {d.receiver_name}</span>}
                        </p>
                      </div>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {shortDate(d.delivery_date)}
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* ── Job Cards (site lots only) ── */}
            {!isWarehouse && jobCards.length > 0 && (
              <Section title="Job Cards">
                <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
                  {jobCards.slice(0, 10).map(jc => (
                    <div key={jc.id} className="flex items-center gap-3 px-3 py-2.5 bg-card">
                      <ClipboardList className="w-4 h-4 text-purple-500 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{jc.work_description}</p>
                        <p className="text-xs text-muted-foreground">
                          {jc.job_card_number} · {jc.status.replace(/_/g, " ")}
                        </p>
                      </div>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {jc.work_date ? shortDate(jc.work_date) : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* ── Photo / Evidence Gallery (site lots only) ── */}
            {!isWarehouse && stagePhotos.length > 0 && (
              <Section title="Evidence Photos">
                <div className="grid grid-cols-3 gap-2">
                  {stagePhotos.slice(0, 12).map(p => (
                    <a key={p.id} href={p.url} target="_blank" rel="noopener noreferrer"
                       className="aspect-square rounded-lg overflow-hidden bg-muted border border-border block">
                      <img src={p.url} alt={p.file_name}
                           className="w-full h-full object-cover"
                           onError={e => { (e.target as HTMLImageElement).style.display = "none"; }} />
                    </a>
                  ))}
                </div>
              </Section>
            )}

          </>
        )}
      </div>

      {/* ── Modals ── */}
      {modal === "request"  && (
        <RequestMaterialModal
          projectId={projectId} siteId={siteId} lotId={lotId}
          onClose={() => setModal(null)} onDone={() => { setModal(null); loadData(); }}
        />
      )}
      {modal === "delivery" && (
        <UnifiedReceiveModal
          projectId={projectId} siteId={siteId} lotId={lotId}
          suppliers={suppliers}
          materialSummary={materialSummary}
          onClose={() => setModal(null)} onDone={() => { setModal(null); loadData(); }}
        />
      )}
      {modal === "usage" && (
        <RecordUsageModal
          projectId={projectId} siteId={siteId} lotId={lotId}
          balances={balances} materialSummary={materialSummary}
          stageMasters={stageMasters} stages={stages}
          onClose={() => setModal(null)} onDone={() => { setModal(null); loadData(); }}
        />
      )}
      {modal === "stage" && (
        <UpdateStageModal
          projectId={projectId} siteId={siteId} lotId={lotId}
          stageMasters={stageMasters} stages={stages}
          onClose={() => setModal(null)} onDone={() => { setModal(null); loadData(); }}
        />
      )}
      {modal === "jobcard" && (
        <CreateJobCardModal
          projectId={projectId} siteId={siteId} lotId={lotId}
          onClose={() => setModal(null)} onDone={() => { setModal(null); loadData(); }}
        />
      )}
      {modal === "add_warehouse" && (
        <AddToWarehouseModal
          projectId={projectId}
          boqItems={pwMaterialSummary}
          onClose={() => setModal(null)}
          onDone={() => { setModal(null); loadData(); }}
        />
      )}
      {modal === "warehouse_transfer" && (
        <ProjectToProjectTransferModal
          fromProjectId={projectId}
          projects={projects}
          warehouseStock={[]}
          onClose={() => setModal(null)}
          onDone={() => { setModal(null); loadData(); }}
        />
      )}
      {/* Upload Delivery Note removed — use Receive Delivery for the unified flow */}
      {/* Sign Delivery removed — signing now happens inline in Receive Delivery modal */}
    </div>
  );
}

// ── Request Material (BOQ-driven) ─────────────────────────────────────────────
interface CartItem {
  key:            string;
  mode:           "boq" | "custom";
  boq_item_id:    string | null;
  description:    string;
  qty:            string;
  unit:           string;
  supplier_id?:   string;
  supplier_name?: string;
  planned_qty?:   number;
}

function RequestMaterialModal({ projectId, siteId, lotId, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  onClose: () => void; onDone: () => void;
}) {
  const [cart,         setCart]         = useState<CartItem[]>([]);
  const [search,       setSearch]       = useState("");
  const [results,      setResults]      = useState<BOQSearchResult[]>([]);
  const [searching,    setSearching]    = useState(false);
  const [neededBy,     setNeededBy]     = useState("");
  const [notes,        setNotes]        = useState("");
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");
  const [savedOffline, setSavedOffline] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout>>();

  // Debounced BOQ search
  useEffect(() => {
    clearTimeout(searchTimer.current);
    const q = search.trim();
    if (!q) { setResults([]); return; }
    searchTimer.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await procurementApi.searchBOQItems(projectId, q);
        setResults(res.filter(r => !cart.some(c => c.boq_item_id === r.id)));
      } catch { setResults([]); }
      finally { setSearching(false); }
    }, 300);
    return () => clearTimeout(searchTimer.current);
  }, [search, projectId, cart]);

  const addBOQItem = (item: BOQSearchResult) => {
    setCart(prev => [...prev, {
      key:           item.id,
      mode:          "boq",
      boq_item_id:   item.id,
      description:   item.description,
      qty:           "",
      unit:          item.unit ?? "",
      supplier_id:   item.preferred_supplier_id ?? undefined,
      supplier_name: item.supplier_name ?? undefined,
      planned_qty:   item.planned_quantity ?? undefined,
    }]);
    setSearch("");
    setResults([]);
  };

  const addCustom = () => setCart(prev => [...prev, {
    key: `custom-${Date.now()}`,
    mode: "custom", boq_item_id: null,
    description: "", qty: "", unit: "",
  }]);

  const updateCart = (i: number, field: keyof CartItem, val: string) =>
    setCart(prev => prev.map((row, idx) => idx === i ? { ...row, [field]: val } : row));

  const removeCart = (i: number) => setCart(prev => prev.filter((_, idx) => idx !== i));

  const validItems = cart.filter(c => c.description.trim() && parseFloat(c.qty) > 0);

  const submit = async () => {
    if (validItems.length === 0) { setError("Add at least one item with a name and quantity."); return; }
    if (!projectId) { setError("No project selected."); return; }
    setLoading(true); setError("");
    try {
      const supplierFromBOQ = cart.find(c => c.mode === "boq" && c.supplier_id)?.supplier_id;
      const mr = await materialRequestsApi.create(projectId, {
        site_id:               siteId  || null,
        lot_id:                lotId   || null,
        delivery_destination:  "SITE_STORE",
        needed_by_date:        neededBy || null,
        notes:                 notes    || null,
        preferred_supplier_id: supplierFromBOQ ?? null,
        items: validItems.map(c => ({
          description:          c.description.trim(),
          quantity_requested:   parseFloat(c.qty),
          unit:                 c.unit.trim() || null,
          boq_item_id:          c.boq_item_id,
          preferred_supplier_id: c.supplier_id || null,
          notes:                c.mode === "custom" ? "Outside BOQ — one-time purchase" : null,
        })),
      });
      await materialRequestsApi.submit(mr.id);
      onDone();
    } catch (err: unknown) {
      const isOffline = !navigator.onLine || (err as { code?: string })?.code === "ERR_NETWORK";
      if (isOffline) {
        const { saveDraft } = await import("@/utils/offlineDrafts");
        saveDraft({
          type: "material_request", projectId, siteId, lotId,
          payload: {
            items: validItems.map(c => ({ desc: c.description, qty: c.qty, unit: c.unit })),
            neededBy, notes,
          },
        });
        setSavedOffline(true);
      } else {
        setError("Failed to submit request. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell title="Request Materials" onClose={onClose}>
      {savedOffline ? (
        <div className="space-y-4 py-2">
          <div className="flex flex-col items-center gap-2 text-center">
            <Upload className="w-8 h-8 text-amber-500" />
            <p className="font-semibold text-sm">Saved offline</p>
            <p className="text-xs text-muted-foreground">
              Your request was saved locally and will be sent when you are back online.
            </p>
          </div>
          <Button className="w-full" onClick={onClose}>Close</Button>
        </div>
      ) : (
        <div className="space-y-3">

          {/* ── BOQ Search ─────────────────────────────────────────── */}
          <div className="space-y-1">
            <Label className="text-xs font-medium">Search BOQ Materials</Label>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Type material name (e.g. Cement, Door…)"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-8"
                autoFocus
              />
            </div>

            {results.length > 0 && (
              <div className="border border-border rounded-lg divide-y bg-background shadow-sm max-h-40 overflow-y-auto">
                {results.map(r => (
                  <button
                    type="button" key={r.id}
                    onClick={() => addBOQItem(r)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-muted flex items-center justify-between"
                  >
                    <div className="min-w-0">
                      <span className="font-medium">{r.description}</span>
                      {r.supplier_name && (
                        <span className="text-xs text-muted-foreground ml-2">· {r.supplier_name}</span>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground ml-2 shrink-0">
                      {r.planned_quantity != null ? `${r.planned_quantity} ` : ""}{r.unit ?? ""}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {search.trim() && !searching && results.length === 0 && (
              <p className="text-xs text-muted-foreground px-1">
                No BOQ items match — use "Add one-time purchase" below.
              </p>
            )}
          </div>

          {/* ── Cart ───────────────────────────────────────────────── */}
          {cart.length > 0 && (
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">
                Items to request ({cart.length})
              </Label>
              {cart.map((item, i) => (
                <div key={item.key}
                  className="flex gap-2 items-start bg-muted/30 rounded-lg px-2.5 py-2">
                  <div className="flex-1 min-w-0 space-y-1">
                    {item.mode === "custom" ? (
                      <Input
                        placeholder="Item description"
                        value={item.description}
                        onChange={e => updateCart(i, "description", e.target.value)}
                        className="h-7 text-xs"
                        autoFocus={item.description === ""}
                      />
                    ) : (
                      <p className="text-xs font-medium truncate">{item.description}</p>
                    )}
                    <div className="flex flex-wrap gap-1.5 items-center">
                      <Input
                        type="number" min="0.001" step="any"
                        placeholder="Qty"
                        value={item.qty}
                        onChange={e => updateCart(i, "qty", e.target.value)}
                        className="h-7 text-xs w-20"
                      />
                      {item.mode === "custom" ? (
                        <Input
                          placeholder="unit"
                          value={item.unit}
                          onChange={e => updateCart(i, "unit", e.target.value)}
                          className="h-7 text-xs w-16"
                        />
                      ) : (
                        <span className="text-xs text-muted-foreground">{item.unit}</span>
                      )}
                      {item.mode === "boq" && item.planned_qty != null && (
                        <span className="text-[10px] text-green-700 bg-green-50 border border-green-200 rounded px-1.5 py-0.5">
                          BOQ: {item.planned_qty}
                        </span>
                      )}
                      {item.mode === "boq" && item.supplier_name && (
                        <span className="text-[10px] text-blue-700 bg-blue-50 border border-blue-200 rounded px-1.5 py-0.5 truncate max-w-[100px]">
                          {item.supplier_name}
                        </span>
                      )}
                      {item.mode === "custom" && (
                        <span className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5">
                          One-time
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeCart(i)}
                    className="mt-0.5 p-1 text-muted-foreground hover:text-destructive rounded transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* ── Add custom item ─────────────────────────────────────── */}
          <button
            type="button"
            onClick={addCustom}
            className="flex items-center gap-1.5 text-xs text-amber-600 hover:text-amber-700 font-medium
                       px-2 py-1.5 rounded-md hover:bg-amber-50 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add one-time purchase (not in BOQ)
          </button>

          <div className="h-px bg-border" />

          {/* ── Date + notes ────────────────────────────────────────── */}
          <div className="space-y-1">
            <Label htmlFor="rm-date" className="text-xs">Needed by (optional)</Label>
            <Input id="rm-date" type="date" min={todayStr()}
                   value={neededBy} onChange={e => setNeededBy(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="rm-notes" className="text-xs">Notes (optional)</Label>
            <textarea
              id="rm-notes" rows={2}
              value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="Any extra details for the office…"
              className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none
                         focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div className="text-xs text-muted-foreground bg-muted/40 rounded-lg px-3 py-2">
            Destination: <strong>Project Warehouse</strong> — office will arrange delivery or transfer.
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          <Button
            onClick={submit}
            disabled={loading || validItems.length === 0}
            className="w-full"
          >
            {loading
              ? "Submitting…"
              : validItems.length === 0
                ? "Search and add items above"
                : `Submit Request (${validItems.length} item${validItems.length !== 1 ? "s" : ""})`}
          </Button>
        </div>
      )}
    </ModalShell>
  );
}

// ── Site Request History ──────────────────────────────────────────────────────

const STATUS_BADGE: Record<string, string> = {
  DRAFT:             "bg-gray-100 text-gray-600 border-gray-200",
  SUBMITTED:         "bg-blue-100 text-blue-700 border-blue-200",
  PENDING_APPROVAL:  "bg-amber-100 text-amber-700 border-amber-200",
  APPROVED:          "bg-green-100 text-green-700 border-green-200",
  REJECTED:          "bg-red-100 text-red-700 border-red-200",
  CONVERTED_TO_PO:   "bg-purple-100 text-purple-700 border-purple-200",
};

const STATUS_LABEL: Record<string, string> = {
  DRAFT:             "Draft",
  SUBMITTED:         "Submitted",
  PENDING_APPROVAL:  "Pending",
  APPROVED:          "Approved",
  REJECTED:          "Rejected",
  CONVERTED_TO_PO:   "Ordered",
};

function SiteRequestHistory({ requests }: { requests: MaterialRequest[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showAll,  setShowAll]  = useState(false);

  if (requests.length === 0) return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <ClipboardList className="w-4 h-4 text-primary" />
        <span className="font-semibold text-sm">My Requests</span>
      </div>
      <div className="bg-card border border-border rounded-xl p-6 text-center">
        <ClipboardList className="w-7 h-7 text-muted-foreground mx-auto mb-2" />
        <p className="text-sm text-muted-foreground">No requests submitted yet.</p>
      </div>
    </div>
  );

  const displayed = showAll ? requests : requests.slice(0, 5);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ClipboardList className="w-4 h-4 text-primary" />
          <span className="font-semibold text-sm">My Requests</span>
          <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
            {requests.length}
          </span>
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {displayed.map((mr, i) => {
          const isExpanded = expanded === mr.id;
          const badge = STATUS_BADGE[mr.status] ?? "bg-gray-100 text-gray-600 border-gray-200";
          const label = STATUS_LABEL[mr.status] ?? mr.status;
          return (
            <div
              key={mr.id}
              className={cn("border-b border-border last:border-0", i > 0 && "")}
            >
              <button
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors text-left"
                onClick={() => setExpanded(isExpanded ? null : mr.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{mr.request_number}</span>
                    <span className={cn("text-xs px-1.5 py-0.5 rounded border font-medium", badge)}>
                      {label}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {mr.items.length} item{mr.items.length !== 1 ? "s" : ""}
                    {" · "}{new Date(mr.requested_date || mr.created_at).toLocaleDateString("en-ZA")}
                    {mr.needed_by_date && ` · Needed by ${new Date(mr.needed_by_date).toLocaleDateString("en-ZA")}`}
                  </p>
                </div>
                <ChevronRight className={cn("w-4 h-4 text-muted-foreground shrink-0 transition-transform", isExpanded && "rotate-90")} />
              </button>

              {isExpanded && (
                <div className="px-4 pb-3 space-y-2 border-t border-border/50 pt-2 bg-muted/20">
                  {mr.items.map((item, j) => (
                    <div key={item.id ?? j} className="flex items-start justify-between text-sm">
                      <span className="text-foreground truncate flex-1">{item.description}</span>
                      <span className="text-muted-foreground shrink-0 ml-2 text-xs">
                        {item.requested_quantity ?? item.quantity_requested ?? "—"} {item.unit ?? ""}
                      </span>
                    </div>
                  ))}
                  {mr.notes && (
                    <p className="text-xs text-muted-foreground italic mt-1">{mr.notes}</p>
                  )}
                  {mr.rejection_reason && (
                    <p className="text-xs text-red-600 bg-red-50 rounded px-2 py-1">
                      Rejected: {mr.rejection_reason}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {requests.length > 5 && (
        <button
          onClick={() => setShowAll(p => !p)}
          className="text-xs text-primary hover:text-primary/80 font-medium w-full text-center py-1"
        >
          {showAll ? "Show less" : `Show all ${requests.length} requests`}
        </button>
      )}
    </div>
  );
}

// ── Canvas Signature Pad ──────────────────────────────────────────────────────
function SignaturePad({ label, value, onChange, required = false }: {
  label: string; value: string; onChange: (v: string) => void; required?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing   = useRef(false);

  const toPos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const c = canvasRef.current!;
    const r = c.getBoundingClientRect();
    return {
      x: (e.clientX - r.left) * (c.width  / r.width),
      y: (e.clientY - r.top)  * (c.height / r.height),
    };
  };

  const onDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    const ctx = canvasRef.current!.getContext("2d")!;
    const p = toPos(e);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    ctx.lineTo(p.x + 0.1, p.y);
    ctx.strokeStyle = "#111827";
    ctx.lineWidth   = 2.5;
    ctx.lineCap     = "round";
    ctx.lineJoin    = "round";
    ctx.stroke();
  };

  const onMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const ctx = canvasRef.current!.getContext("2d")!;
    const p = toPos(e);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
  };

  const onUp = () => {
    if (!drawing.current) return;
    drawing.current = false;
    onChange(canvasRef.current!.toDataURL("image/png"));
  };

  const clear = () => {
    const c = canvasRef.current!;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
    onChange("");
  };

  // Sync clear when parent clears value
  useEffect(() => {
    if (!value && canvasRef.current) {
      canvasRef.current.getContext("2d")!.clearRect(
        0, 0, canvasRef.current.width, canvasRef.current.height
      );
    }
  }, [value]);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <Label className="text-xs">
          {label}{required && <span className="text-destructive ml-0.5">*</span>}
        </Label>
        {value && (
          <button type="button" onClick={clear}
                  className="text-[10px] text-muted-foreground hover:text-destructive transition-colors">
            Clear
          </button>
        )}
      </div>
      <div className="relative border-2 border-dashed border-border rounded-xl bg-white dark:bg-slate-950 overflow-hidden"
           style={{ touchAction: "none" }}>
        <canvas
          ref={canvasRef}
          width={420} height={110}
          className="w-full block cursor-crosshair"
          style={{ touchAction: "none" }}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerLeave={onUp}
        />
        {!value && (
          <p className="absolute inset-0 flex items-center justify-center text-xs text-gray-300 dark:text-gray-700 pointer-events-none select-none">
            Sign here with finger or mouse
          </p>
        )}
      </div>
    </div>
  );
}

// ── Unified Receive Delivery (3-step: document → details/items → sign) ────────
type ReceiveStep = "document" | "details" | "sign" | "done";

interface DeliveryLineItem {
  description:       string;
  unit:              string;
  quantity_expected: string;
  quantity_received: string;
  quantity_rejected: string;
  reason:            string;
  item_id:           string;    // catalog item UUID — empty string = not linked
  boq_item_id:       string;    // BOQ item UUID — empty string = not linked
}

const emptyItem = (): DeliveryLineItem => ({
  description: "", unit: "bags",
  quantity_expected: "", quantity_received: "", quantity_rejected: "0", reason: "",
  item_id: "", boq_item_id: "",
});

// ── BOQ item picker — extracted component so it is never rendered as an IIFE ─
function BOQPickerPanel({
  materialSummary, addedBOQIds, boqSearch, setBoqSearch, onSelect, onClose,
}: {
  materialSummary: MaterialSummaryItem[];
  addedBOQIds:     Set<string>;
  boqSearch:       string;
  setBoqSearch:    (s: string) => void;
  onSelect:        (item: DeliveryLineItem) => void;
  onClose:         () => void;
}) {
  // Safe lower-case — never call .toLowerCase() on null/undefined
  const safeLC = (s: string | null | undefined) => (s ?? "").toLowerCase();
  const searchLC = safeLC(boqSearch);

  const available = materialSummary.filter(m => {
    const id = String(m.boq_item_id ?? "");
    if (!id) return false;
    if (addedBOQIds.has(id)) return false;
    return safeLC(m.description).includes(searchLC);
  });

  return (
    <div className="border border-green-300 rounded-xl bg-green-50 dark:bg-green-950/20 p-3 space-y-2">
      <p className="text-xs font-semibold text-green-800">Select BOQ item that arrived:</p>
      <input
        type="text"
        placeholder="Search BOQ items…"
        value={boqSearch}
        onChange={e => setBoqSearch(e.target.value)}
        className="w-full h-7 rounded border border-border bg-background px-2 text-xs"
        autoFocus
      />
      <div className="max-h-36 overflow-y-auto space-y-0.5">
        {available.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-2">
            {addedBOQIds.size > 0
              ? "All matching BOQ items have been added."
              : "No BOQ items found. Generate lot BOQs from the BOQ page first."}
          </p>
        ) : available.map(m => {
          const desc     = String(m.description   ?? "");
          const unit     = String(m.unit          ?? "");
          const boqId    = String(m.boq_item_id   ?? "");
          const itemId   = String(m.item_id       ?? "");
          const allocQty = typeof m.boq_allocated_qty === "number" ? m.boq_allocated_qty : 0;
          return (
            <button
              key={boqId || desc}
              type="button"
              onClick={() => onSelect({
                description:       desc,
                unit:              unit,
                quantity_expected: allocQty > 0 ? String(allocQty) : "",
                quantity_received: "",
                quantity_rejected: "0",
                reason:            "",
                item_id:           itemId,
                boq_item_id:       boqId,
              })}
              className="w-full text-left px-2 py-1.5 rounded text-xs hover:bg-green-100 dark:hover:bg-green-900/30 flex items-center justify-between"
            >
              <span className="font-medium">{desc || "—"}</span>
              <span className="text-[10px] text-green-600 ml-2 shrink-0">
                {allocQty} {unit} BOQ{itemId ? " ✓" : " ⚠"}
              </span>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        onClick={onClose}
        className="text-xs text-muted-foreground hover:text-foreground"
      >
        ✕ Close picker
      </button>
    </div>
  );
}


function UnifiedReceiveModal({ projectId, siteId, lotId, suppliers, materialSummary, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  suppliers: Supplier[]; materialSummary: MaterialSummaryItem[];
  onClose: () => void; onDone: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [step,         setStep]         = useState<ReceiveStep>("document");
  const [file,         setFile]         = useState<File | null>(null);
  const [supplierId,   setSupplierId]   = useState("");
  const [poId,         setPoId]         = useState("");
  const [dnNum,        setDnNum]        = useState("");

  // Load POs for the project (APPROVED or SENT) so user can link the delivery.
  // Also carries lot_id so the modal can load BOQ items when no lot is pre-selected.
  const [projectPOs, setProjectPOs] = useState<Array<{ id: string; po_number: string; status: string; lot_id: string | null }>>([]);
  useEffect(() => {
    if (!projectId) return;
    import("@/api/client").then(m =>
      m.default.get<{ data: Array<{ id: string; po_number: string; status: string; lot_id: string | null }> }>(
        `/projects/${projectId}/purchase-orders/`
      )
    ).then(r => {
      const all = r.data.data || [];
      setProjectPOs(all.filter(p => ["APPROVED", "SENT", "PARTIALLY_RECEIVED"].includes(p.status)));
    }).catch(() => {});
  }, [projectId]);

  // BOQ summary fallback: project-warehouse aggregate when no lot context is active.
  // When a specific lot is pre-selected (materialSummary already loaded), this is a no-op.
  const [poBOQSummary, setPoBOQSummary] = useState<MaterialSummaryItem[]>([]);
  useEffect(() => {
    if (materialSummary.length > 0) { setPoBOQSummary([]); return; }
    if (!projectId) { setPoBOQSummary([]); return; }
    const po = poId ? projectPOs.find(p => p.id === poId) : null;
    if (po?.lot_id) {
      // PO is linked to a specific lot — load that lot's BOQ
      import("@/api/siteDashboard").then(m =>
        m.siteDashboardApi.getMaterialSummary(siteId, po.lot_id!)
      ).then(setPoBOQSummary).catch(() => setPoBOQSummary([]));
    } else {
      // No lot context — aggregate BOQ from all lots in the project (warehouse level)
      import("@/api/siteDashboard").then(m =>
        m.siteDashboardApi.getProjectWarehouseMaterialSummary(projectId)
      ).then(setPoBOQSummary).catch(() => setPoBOQSummary([]));
    }
  }, [poId, projectId, projectPOs, materialSummary.length, siteId]);

  // Effective BOQ summary: prefer parent-provided, fall back to PO-derived
  const effectiveMaterialSummary = materialSummary.length > 0 ? materialSummary : poBOQSummary;

  // Items always start empty — user adds only what actually arrived.
  const [items, setItems] = useState<DeliveryLineItem[]>([]);

  // When the BOQ summary loads (async, after PO is auto-selected from OCR), try to
  // link any unlinked OCR-extracted items to their matching BOQ item by description.
  // This turns "⚠ No catalog link" into "✓ BOQ item — stock will update" automatically.
  useEffect(() => {
    if (effectiveMaterialSummary.length === 0) return;
    setItems(prev => {
      const unlinked = prev.filter(i => !i.boq_item_id);
      if (unlinked.length === 0) return prev; // nothing to do — skip re-render
      return prev.map(item => {
        if (item.boq_item_id) return item;
        const norm = item.description.toLowerCase().trim();
        if (!norm) return item;
        const match = effectiveMaterialSummary.find(m => {
          const mNorm = m.description.toLowerCase().trim();
          return mNorm === norm || mNorm.includes(norm) || norm.includes(mNorm);
        });
        if (!match) return item;
        return {
          ...item,
          boq_item_id: match.boq_item_id,
          item_id:     match.item_id ?? "",
          unit:        item.unit || match.unit || "",
        };
      });
    });
  }, [effectiveMaterialSummary]);

  // BOQ picker state
  const [showBOQPicker,    setShowBOQPicker]    = useState(false);
  const [boqSearch,        setBoqSearch]        = useState("");

  // Non-BOQ picker state
  const [showNonBOQPicker, setShowNonBOQPicker] = useState(false);
  const [nonBOQForm,       setNonBOQForm]       = useState({ description: "", unit: "", item_id: "" });

  const [driverName,   setDriverName]   = useState("");
  const [driverSig,    setDriverSig]    = useState("");
  const [staffName,    setStaffName]    = useState("");
  const [staffSig,     setStaffSig]     = useState("");
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");
  const [warning,      setWarning]      = useState("");
  const [result,       setResult]       = useState<{
    delivery_number:      string;
    is_partial:           boolean;
    unlinked_count?:      number;
    stock_updated_count?: number;
    unlinked_items?: Array<{ description: string; quantity_received: number; unit: string | null }>;
  } | null>(null);

  // Catalog items — always loaded so Non-BOQ picker works whether or not a lot is selected
  const [catalogItems, setCatalogItems] = useState<Array<{ id: string; name: string; default_unit: string | null }>>([]);
  useEffect(() => {
    import("@/api/client").then(m =>
      m.default.get<{ data: Array<{ id: string; name: string; default_unit: string | null }> }>("/items/")
    ).then(r => setCatalogItems(r.data.data || [])).catch(() => {});
  }, []);

  // BOQ items already added (by boq_item_id) so the picker can hide them
  const addedBOQIds = new Set(items.map(i => i.boq_item_id).filter(Boolean));

  // ── Step 1: optional document upload + try extraction ──────────────────────
  const handleDocument = async () => {
    setError(""); setWarning("");
    if (file) {
      setLoading(true);
      try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("site_id", siteId);
        fd.append("supplier_name", "");
        const res = await siteCaptureApi.uploadDeliveryNote(fd);
        const f = res.extracted_fields;
        if (res.status === "EXTRACTED" || res.status === "NEEDS_REVIEW") {
          if (f.delivery_note_number) setDnNum(f.delivery_note_number);
          // Auto-select PO from extracted po_number
          if (f.po_number) {
            const norm = f.po_number.toLowerCase();
            const matched = projectPOs.find(p =>
              p.po_number.toLowerCase().includes(norm) || norm.includes(p.po_number.toLowerCase())
            );
            if (matched) setPoId(matched.id);
          }
          // Auto-select supplier from extracted supplier_name
          if (f.supplier_name && !supplierId) {
            const norm = f.supplier_name.toLowerCase().trim();
            const matched = suppliers.find(s =>
              s.name.toLowerCase().trim().includes(norm) || norm.includes(s.name.toLowerCase().trim())
            );
            if (matched) setSupplierId(matched.id);
          }
          if (res.items.length > 0) {
            // OCR-extracted items have no catalog/BOQ link — user must add via
            // "Add BOQ Item" or "Add Non-BOQ Item" for stock to update.
            // We show them so the user can see what OCR found, but they're
            // treated the same as manually-added unlinked items.
            setItems(res.items.map(i => ({
              description:       i.description || "",
              unit:              i.unit || "",
              quantity_expected: String(i.ocr_qty ?? ""),
              quantity_received: String(i.actual_received_qty || i.ocr_qty || ""),
              quantity_rejected: "0",
              reason:            "",
              item_id:           "",
              boq_item_id:       "",
            })));
          }
        } else {
          setWarning("Could not read the document automatically. Please enter details below.");
        }
      } catch { setWarning("Extraction unavailable — enter details manually."); }
      finally { setLoading(false); }
    }
    setStep("details");
  };

  const updateItem = (idx: number, field: keyof DeliveryLineItem, val: string) =>
    setItems(prev => prev.map((it, i) => i === idx ? { ...it, [field]: val } : it));

  // ── Step 3: submit to backend ──────────────────────────────────────────────
  const handleSubmit = async () => {
    if (!supplierId) { setError("Select a supplier."); return; }
    if (!staffName.trim() || !staffSig) { setError("Receiver name and signature are required."); return; }
    setLoading(true); setError("");
    try {
      const fd = new FormData();
      fd.append("project_id", projectId);
      fd.append("site_id",    siteId);
      fd.append("supplier_id", supplierId);
      fd.append("delivery_note_number", dnNum);
      if (lotId) { fd.append("lot_id", lotId); fd.append("destination", "LOT"); }
      else         fd.append("destination", "SITE_STORE");
      if (poId)  fd.append("purchase_order_id", poId);
      fd.append("receiver_name",    staffName);
      fd.append("receiver_signature", staffSig);
      if (driverName) fd.append("driver_name",      driverName);
      if (driverSig)  fd.append("driver_signature", driverSig);
      if (file)       fd.append("delivery_note_file", file);
      fd.append("items_json", JSON.stringify(
        items
          .filter(i => i.description.trim())
          .map(i => ({
            description:       i.description,
            unit:              i.unit,
            // item_id is included so the backend can write StockLedger entries.
            // Blank/undefined means the item is not catalog-linked — backend tracks
            // this and returns it in unlinked_items.
            item_id:           i.item_id || undefined,
            boq_item_id:       i.boq_item_id || undefined,
            quantity_expected: i.quantity_expected ? parseFloat(i.quantity_expected) : null,
            quantity_received: parseFloat(i.quantity_received || "0"),
            quantity_rejected: parseFloat(i.quantity_rejected || "0"),
            reason:            i.reason || null,
          }))
      ));
      const res = await deliveriesApi.receiveWithDocument(fd);
      setResult({
        delivery_number: res.delivery_number,
        is_partial:      res.is_partial,
        unlinked_count:  res.unlinked_count,
        unlinked_items:  res.unlinked_items,
        stock_updated_count: res.stock_updated_count,
      });
      setStep("done");
      // NOTE: do NOT call onDone() here — the user must see the done screen
      // (which shows unlinked-item warnings) before the modal closes.
      // onDone() is called by the Done button below.
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || "Failed to record delivery. Try again.");
    } finally { setLoading(false); }
  };

  const titles: Record<ReceiveStep, string> = {
    document: "Receive Delivery — Step 1 of 3: Document",
    details:  "Receive Delivery — Step 2 of 3: Details & Items",
    sign:     "Receive Delivery — Step 3 of 3: Signatures",
    done:     "Delivery Recorded",
  };

  return (
    <ModalShell title={titles[step]} onClose={onClose}>
      <ModalErrorBoundary>
      {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2 mb-3">{error}</p>}

      {/* ── STEP 1: Document upload ── */}
      {step === "document" && (
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Upload a photo or PDF of the delivery note (optional — you can skip and enter manually).
          </p>
          <div
            onClick={() => fileRef.current?.click()}
            className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-border rounded-xl p-6 cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-colors"
          >
            {file
              ? <p className="text-sm font-medium text-primary">{file.name}</p>
              : <>
                  <Camera className="w-6 h-6 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Photo from camera or choose file</p>
                </>
            }
            <input
              ref={fileRef} type="file" className="sr-only"
              accept="image/*,.pdf" capture="environment"
              onChange={e => { setFile(e.target.files?.[0] ?? null); setError(""); }}
            />
          </div>
          {/* Vision AI extraction — shown only when a file is selected */}
          {file && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-xs text-blue-700 space-y-1">
              <p className="font-medium flex items-center gap-1">✨ AI Extraction available</p>
              <p>Click "Extract with AI" to auto-fill delivery fields. You can edit everything before saving.</p>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs border-blue-300 text-blue-700 hover:bg-blue-100 mt-1"
                disabled={loading}
                onClick={async () => {
                  setLoading(true); setError("");
                  try {
                    const { visionApi } = await import("@/api/vision");
                    const result = await visionApi.extract(file, "delivery_note");
                    if (result.status === "OCR_NOT_AVAILABLE" || result.status === "OCR_FAILED") {
                      setWarning(result.status === "OCR_FAILED"
                        ? "Google Vision configured but returned no text — check credentials. Entering manually."
                        : "AI Vision not configured — entering manually.");
                    } else {
                      const p = result.preview as {
                        delivery_note_number?: string | null;
                        po_number?:            string | null;
                        supplier_name?:        string | null;
                        items?: Array<{ description: string | null; quantity: number | null; unit: string | null }>;
                      };
                      if (p.delivery_note_number) setDnNum(p.delivery_note_number);
                      // Auto-select matching PO from extracted po_number
                      if (p.po_number) {
                        const norm = p.po_number.toLowerCase();
                        const matched = projectPOs.find(po =>
                          po.po_number.toLowerCase().includes(norm) || norm.includes(po.po_number.toLowerCase())
                        );
                        if (matched) setPoId(matched.id);
                      }
                      // Auto-select matching supplier from extracted supplier_name
                      if (p.supplier_name && !supplierId) {
                        const norm = p.supplier_name.toLowerCase().trim();
                        const matched = suppliers.find(s =>
                          s.name.toLowerCase().trim().includes(norm) || norm.includes(s.name.toLowerCase().trim())
                        );
                        if (matched) setSupplierId(matched.id);
                      }
                      if (p.items && p.items.length > 0) {
                        setItems(p.items.map(i => ({
                          description:       String(i.description ?? ""),
                          unit:              String(i.unit ?? ""),
                          quantity_expected: String(i.quantity ?? ""),
                          quantity_received: "",
                          quantity_rejected: "0",
                          reason:            "",
                          item_id:           "",
                          boq_item_id:       "",
                        })));
                      }
                      setWarning(result.status === "NEEDS_REVIEW"
                        ? "Partial extraction — please review and correct all fields."
                        : "Fields extracted — review before submitting.");
                    }
                    setStep("details");
                  } catch {
                    setWarning("Extraction failed — entering manually.");
                    setStep("details");
                  } finally { setLoading(false); }
                }}
              >
                {loading ? "Extracting…" : "✨ Extract with AI"}
              </Button>
            </div>
          )}

          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={onClose}>Cancel</Button>
            <Button className="flex-1" onClick={handleDocument} disabled={loading}>
              {loading ? "Extracting…" : file ? "Next →" : "Skip (Enter manually)"}
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 2: Details + items ── */}
      {step === "details" && (
        <div className="space-y-4">
          {warning && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-700">
              {warning}
            </div>
          )}
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Supplier <span className="text-destructive">*</span></Label>
              <select value={supplierId} onChange={e => setSupplierId(e.target.value)}
                      className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
                <option value="">— Select supplier —</option>
                {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              {/* Multi-supplier warning — shown when BOQ items have different suppliers */}
              {(() => {
                const boqSuppliers = items
                  .filter(i => i.boq_item_id)
                  .map(i => effectiveMaterialSummary.find(m => String(m.boq_item_id) === i.boq_item_id)?.supplier_name)
                  .filter((n): n is string => !!n);
                const uniqueSuppliers = [...new Set(boqSuppliers)];
                if (uniqueSuppliers.length > 1) {
                  return (
                    <p className="text-xs text-amber-600 mt-1">
                      ⚠ Items have different BOQ suppliers: {uniqueSuppliers.join(", ")}.
                      Consider splitting into separate delivery notes per supplier.
                    </p>
                  );
                }
                if (uniqueSuppliers.length === 1 && !supplierId) {
                  return (
                    <p className="text-xs text-primary mt-1">
                      BOQ supplier suggestion: <strong>{uniqueSuppliers[0]}</strong>
                    </p>
                  );
                }
                return null;
              })()}
            </div>
            <div className="space-y-1">
              <Label htmlFor="u-dn">Delivery Note #</Label>
              <Input id="u-dn" value={dnNum} onChange={e => setDnNum(e.target.value)} placeholder="DN-001" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="u-po">Link to Purchase Order (PO)</Label>
              <select
                id="u-po"
                value={poId}
                onChange={e => setPoId(e.target.value)}
                className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background"
              >
                <option value="">— No PO (will create alert) —</option>
                {projectPOs.map(p => (
                  <option key={p.id} value={p.id}>{p.po_number} · {p.status}</option>
                ))}
              </select>
              {!poId && (
                <p className="text-[10px] text-amber-600">
                  ⚠ Delivery without PO will create a "Delivery Without PO" alert.
                </p>
              )}
            </div>
          </div>

          {/* ── Items received ──────────────────────────────────────────────── */}
          <div className="space-y-2">
            <Label>Items received <span className="text-destructive">*</span></Label>

            {/* ── Added items list ── */}
            {items.length > 0 && (
              <div className="max-h-56 overflow-y-auto space-y-2">
                {items.map((it, idx) => {
                  // Defensive: treat any non-empty string as truthy; guard against null/undefined
                  const isBoq     = !!(it.boq_item_id);
                  const isCatalog = !!(it.item_id);
                  const rowCls = isBoq
                    ? "bg-green-50 dark:bg-green-950/20 border-green-200"
                    : isCatalog
                    ? "bg-blue-50 dark:bg-blue-950/20 border-blue-200"
                    : "bg-amber-50 dark:bg-amber-950/20 border-amber-200";
                  const tagCls  = isBoq ? "text-green-700" : isCatalog ? "text-blue-700" : "text-amber-700";
                  const tagText = isBoq
                    ? "✓ BOQ item — stock will update"
                    : isCatalog
                    ? "✓ Non-BOQ, catalog linked — stock will update"
                    : "⚠ No catalog link — stock will NOT update";

                  // Safe numeric parse — never crash on empty/invalid
                  const rejectedQty = parseFloat(String(it.quantity_rejected || "0")) || 0;

                  return (
                    <div key={idx} className={`rounded-lg p-2.5 space-y-1.5 border ${rowCls}`}>
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium truncate">{String(it.description || "—")}</p>
                          <p className={`text-[10px] ${tagCls}`}>{tagText}</p>
                        </div>
                        <button
                          onClick={() => setItems(p => p.filter((_, i) => i !== idx))}
                          className="shrink-0 text-muted-foreground hover:text-destructive"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      {/* Qty inputs — always show Received + Rejected; show BOQ qty only for BOQ items */}
                      <div className="flex gap-1">
                        {isBoq && (
                          <Input type="number" placeholder="BOQ qty"
                                 value={String(it.quantity_expected ?? "")}
                                 onChange={e => updateItem(idx, "quantity_expected", e.target.value)}
                                 className="h-7 text-xs w-20 shrink-0" title="BOQ allocated quantity" />
                        )}
                        <Input type="number" placeholder="Received *"
                               value={String(it.quantity_received ?? "")}
                               onChange={e => updateItem(idx, "quantity_received", e.target.value)}
                               className="h-7 text-xs flex-1" />
                        <Input type="number" placeholder="Rej."
                               value={String(it.quantity_rejected ?? "0")}
                               onChange={e => updateItem(idx, "quantity_rejected", e.target.value)}
                               className="h-7 text-xs w-16 shrink-0" />
                        <Input placeholder="Unit"
                               value={String(it.unit ?? "")}
                               onChange={e => updateItem(idx, "unit", e.target.value)}
                               className="h-7 text-xs w-16 shrink-0" />
                      </div>
                      {rejectedQty > 0 && (
                        <Input placeholder="Reason for rejection"
                               value={String(it.reason ?? "")}
                               onChange={e => updateItem(idx, "reason", e.target.value)}
                               className="h-7 text-xs text-amber-700 border-amber-300" />
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {items.length === 0 && !showBOQPicker && !showNonBOQPicker && (
              <p className="text-xs text-muted-foreground bg-muted/40 rounded-lg px-3 py-3 text-center">
                No items added yet. Use the buttons below to add what arrived.
              </p>
            )}

            {/* ── Picker buttons ── */}
            {!showBOQPicker && !showNonBOQPicker && (
              <div className="flex gap-2">
                {effectiveMaterialSummary.length > 0 && (
                  <button
                    onClick={() => setShowBOQPicker(true)}
                    className="flex-1 py-2 rounded-lg border border-green-300 bg-green-50 text-xs font-medium text-green-700 hover:bg-green-100 transition-colors"
                  >
                    + Add BOQ Item
                  </button>
                )}
                <button
                  onClick={() => setShowNonBOQPicker(true)}
                  className="flex-1 py-2 rounded-lg border border-blue-300 bg-blue-50 text-xs font-medium text-blue-700 hover:bg-blue-100 transition-colors"
                >
                  + Add Non-BOQ Item
                </button>
              </div>
            )}

            {/* ── BOQ picker panel ── */}
            {showBOQPicker && <BOQPickerPanel
              materialSummary={effectiveMaterialSummary}
              addedBOQIds={addedBOQIds}
              boqSearch={boqSearch}
              setBoqSearch={setBoqSearch}
              onSelect={(newItem) => {
                setItems(p => [...p, newItem]);
                setBoqSearch("");
                // Auto-populate supplier from the BOQ item if not yet set
                const boqEntry = effectiveMaterialSummary.find(m => String(m.boq_item_id) === newItem.boq_item_id);
                if (boqEntry?.supplier_id && !supplierId) {
                  setSupplierId(boqEntry.supplier_id);
                }
              }}
              onClose={() => { setShowBOQPicker(false); setBoqSearch(""); }}
            />}

            {/* ── Non-BOQ picker panel ── */}
            {showNonBOQPicker && (
              <div className="border border-blue-300 rounded-xl bg-blue-50 dark:bg-blue-950/20 p-3 space-y-2">
                <p className="text-xs font-semibold text-blue-800">
                  Add non-BOQ item (consumables, extras, tools):
                </p>
                <Input
                  placeholder="Description *"
                  value={nonBOQForm.description}
                  onChange={e => setNonBOQForm(f => ({ ...f, description: e.target.value }))}
                  className="h-8 text-sm"
                  autoFocus
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="Unit (e.g. pcs, kg)"
                    value={nonBOQForm.unit}
                    onChange={e => setNonBOQForm(f => ({ ...f, unit: e.target.value }))}
                    className="h-7 text-xs"
                  />
                  <select
                    value={nonBOQForm.item_id}
                    onChange={e => setNonBOQForm(f => ({ ...f, item_id: e.target.value }))}
                    className={`h-7 rounded border px-1 text-[10px] bg-background ${
                      nonBOQForm.item_id ? "border-green-400 text-green-700" : "border-amber-300 text-amber-700"
                    }`}
                  >
                    <option value="">⚠ No catalog — stock won't update</option>
                    {catalogItems.map(ci => (
                      <option key={ci.id} value={ci.id}>
                        {ci.name}{ci.default_unit ? ` (${ci.default_unit})` : ""}
                      </option>
                    ))}
                  </select>
                </div>
                {!nonBOQForm.item_id && (
                  <p className="text-[10px] text-amber-700">
                    Link to a catalog item for stock tracking. Leave blank only for non-tracked consumables.
                  </p>
                )}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={!nonBOQForm.description.trim()}
                    onClick={() => {
                      const ci = catalogItems.find(c => c.id === nonBOQForm.item_id);
                      setItems(p => [...p, {
                        description:       nonBOQForm.description.trim(),
                        unit:              nonBOQForm.unit || (ci?.default_unit ?? ""),
                        quantity_expected: "",
                        quantity_received: "",
                        quantity_rejected: "0",
                        reason:            "",
                        item_id:           nonBOQForm.item_id,
                        boq_item_id:       "",
                      }]);
                      setNonBOQForm({ description: "", unit: "", item_id: "" });
                      setShowNonBOQPicker(false);
                    }}
                    className="h-7 text-xs"
                  >
                    Add Item
                  </Button>
                  <Button
                    size="sm" variant="outline"
                    onClick={() => { setShowNonBOQPicker(false); setNonBOQForm({ description: "", unit: "", item_id: "" }); }}
                    className="h-7 text-xs"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>

          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={() => setStep("document")}>← Back</Button>
            <Button className="flex-1" onClick={() => { setError(""); setStep("sign"); }}
                    disabled={!supplierId || items.every(i => !i.description.trim())}>
              Next →
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 3: Signatures ── */}
      {step === "sign" && (
        <div className="space-y-4">
          <div className="space-y-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Driver / Supplier Rep</p>
            <Input placeholder="Driver full name (optional)" value={driverName}
                   onChange={e => setDriverName(e.target.value)} className="h-9" />
            {driverName && (
              <SignaturePad label="Driver signature (optional)" value={driverSig} onChange={setDriverSig} />
            )}
          </div>
          <div className="space-y-3 border-t border-border pt-4">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Site Receiver</p>
            <Input placeholder="Receiver full name *" value={staffName}
                   onChange={e => setStaffName(e.target.value)} required className="h-9" />
            <SignaturePad label="Receiver signature *" value={staffSig} onChange={setStaffSig} required />
            <p className="text-[10px] text-muted-foreground">
              Timestamp: {new Date().toLocaleString()} (auto-captured on submit)
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={() => setStep("details")}>← Back</Button>
            <Button className="flex-1" onClick={handleSubmit}
                    disabled={loading || !staffName.trim() || !staffSig}>
              {loading ? "Recording…" : "Record Delivery"}
            </Button>
          </div>
        </div>
      )}

      {/* ── DONE ── */}
      {step === "done" && result && (
        <div className="flex flex-col gap-4 py-4">
          <div className="flex flex-col items-center gap-2 text-center">
            <CheckCircle2 className="w-12 h-12 text-green-500" />
            <p className="font-semibold">{result.delivery_number} recorded.</p>
            {result.is_partial && (
              <p className="text-sm text-amber-600">Short delivery detected — alert created.</p>
            )}
            {(result.stock_updated_count ?? 0) > 0 && (
              <p className="text-xs text-green-600">
                ✓ {result.stock_updated_count} item{result.stock_updated_count !== 1 ? "s" : ""} updated stock balance.
              </p>
            )}
          </div>

          {/* Unlinked items warning — stock was not updated for these lines */}
          {(result.unlinked_count ?? 0) > 0 && (
            <div className="bg-amber-50 border border-amber-300 rounded-xl p-3 space-y-2">
              <p className="text-xs font-semibold text-amber-800 flex items-center gap-1.5">
                <span>⚠</span>
                {result.unlinked_count} item{result.unlinked_count !== 1 ? "s" : ""} not linked to catalog — stock NOT updated
              </p>
              <p className="text-xs text-amber-700">
                These items have no catalog link so their stock balances could not be updated.
                An office admin must link them in the Deliveries page.
              </p>
              <div className="space-y-0.5">
                {result.unlinked_items?.map((item, i) => (
                  <p key={i} className="text-xs text-amber-800 font-medium">
                    • {item.description} — {item.quantity_received} {item.unit ?? ""}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Done — calls onDone which refreshes the dashboard and closes the modal */}
          <Button className="w-full" onClick={onDone}>Done</Button>
        </div>
      )}
      </ModalErrorBoundary>
    </ModalShell>
  );
}

// ── Record Usage ──────────────────────────────────────────────────────────────
function RecordUsageModal({ projectId, siteId, lotId, balances, materialSummary, stageMasters, stages, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  balances: StockBalance[]; materialSummary: MaterialSummaryItem[];
  stageMasters: StageMaster[]; stages: ProjectStageStatus[];
  onClose: () => void; onDone: () => void;
}) {
  const evidenceRef = useRef<HTMLInputElement>(null);
  const [itemId,        setItemId]       = useState("");
  const [qty,           setQty]          = useState("");
  const [usedBy,        setUsedBy]       = useState("");
  const [team,          setTeam]         = useState("");
  const [stageId,       setStageId]      = useState("");
  const [overrunReason, setOverrunReason] = useState("");
  const [evidenceFile,  setEvidenceFile] = useState<File | null>(null);
  const [loading,       setLoading]      = useState(false);
  const [error,         setError]        = useState("");

  // Prefer materialSummary (BOQ-aware) when available, fallback to balances
  // itemId holds boq_item_id when using materialSummary, item_id when using balances
  const boqItems  = materialSummary.length > 0 ? materialSummary : null;
  // Find selected by boq_item_id (materialSummary mode) OR item_id (balances mode)
  const selected  = boqItems?.find(i => i.boq_item_id === itemId);
  const isOverBOQ = selected ? parseFloat(qty || "0") > selected.remaining_qty : false;

  const available = boqItems
    ? boqItems
    : balances.filter(b => (lotId ? b.lot_id === lotId : true) && b.balance > 0);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!itemId) { setError("Select a material."); return; }
    if (!siteId) { setError("Select a site first."); return; }
    if (isOverBOQ && !overrunReason.trim()) { setError("Provide a reason for exceeding the BOQ allocation."); return; }

    // For BOQ items, resolve the catalog item_id (required by stockApi)
    const catalogItemId = selected?.item_id ?? itemId;
    if (boqItems && !selected?.item_id) {
      setError("This material is not linked to the catalog. Ask admin to link the BOQ item to a catalog item before recording usage.");
      return;
    }

    setLoading(true); setError("");
    try {
      if (evidenceFile) {
        const fd = new FormData();
        fd.append("project_id",          projectId);
        fd.append("site_id",             siteId);
        fd.append("item_id",             catalogItemId);
        fd.append("quantity_used",       String(parseFloat(qty)));
        if (lotId)              fd.append("lot_id",              lotId);
        if (usedBy)             fd.append("used_by_person_name", usedBy);
        if (team)               fd.append("used_by_team_name",   team);
        if (stageId)            fd.append("stage_id",            stageId);
        if (overrunReason)      fd.append("overrun_reason",      overrunReason);
        fd.append("evidence_file", evidenceFile);
        await stockApi.recordUsageWithEvidence(projectId, fd);
      } else {
        await stockApi.recordUsage(projectId, {
          site_id:             siteId,
          item_id:             catalogItemId,
          quantity_used:       parseFloat(qty),
          lot_id:              lotId   || null,
          stage_id:            stageId || null,
          used_by_person_name: usedBy  || null,
          used_by_team_name:   team    || null,
          usage_date:          new Date().toISOString(),
        }, overrunReason || undefined);
      }
      onDone();
    } catch { setError("Failed to record usage. Try again."); }
    finally  { setLoading(false); }
  };

  return (
    <ModalShell title="Record Usage" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div className="space-y-1">
          <Label>Material</Label>
          <select value={itemId} onChange={e => setItemId(e.target.value)} required
                  className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
            <option value="">— Select material —</option>
            {boqItems
              ? boqItems.map(i => (
                  // value = boq_item_id so we can look up item_id on submit
                  <option key={i.boq_item_id} value={i.boq_item_id}
                          disabled={!i.item_id}
                          title={!i.item_id ? "Not linked to catalog — contact admin" : undefined}>
                    {i.description}{!i.item_id ? " (no catalog link)" : ""} · {i.remaining_qty.toFixed(1)} {i.unit ?? ""} remaining
                  </option>
                ))
              : (available as StockBalance[]).map(b => (
                  <option key={b.item_id} value={b.item_id}>
                    {b.item_name ?? b.item_id} · {fmt(b.balance, b.item_unit ?? "")} left
                  </option>
                ))
            }
            {available.length === 0 && <option disabled>No BOQ materials for this lot</option>}
          </select>
          {/* BOQ info for selected item */}
          {selected && (
            <div className="bg-muted/40 rounded-lg px-3 py-2 text-xs space-y-0.5">
              <div className="flex justify-between"><span className="text-muted-foreground">BOQ Allocated</span><span className="font-medium">{selected.boq_allocated_qty} {selected.unit ?? ""}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Already Used</span><span className="font-medium">{selected.used_qty} {selected.unit ?? ""}</span></div>
              <div className="flex justify-between"><span className={selected.remaining_qty <= 0 ? "text-destructive font-semibold" : "text-muted-foreground"}>Remaining</span>
                <span className={cn("font-semibold", selected.remaining_qty <= 0 ? "text-destructive" : "text-green-600")}>{selected.remaining_qty} {selected.unit ?? ""}</span>
              </div>
            </div>
          )}
        </div>
        {isOverBOQ && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-700">
            ⚠ Quantity exceeds BOQ allocation. A reason is required.
          </div>
        )}
        <div className="space-y-1">
          <Label htmlFor="us-qty">Quantity used</Label>
          <Input id="us-qty" type="number" min="0.1" step="0.1"
                 value={qty} onChange={e => setQty(e.target.value)} required />
        </div>
        {isOverBOQ && (
          <div className="space-y-1">
            <Label htmlFor="us-reason" className="text-amber-600">Over-BOQ reason (required)</Label>
            <Input id="us-reason" value={overrunReason} onChange={e => setOverrunReason(e.target.value)}
                   placeholder="e.g. Approved rework by site manager" />
          </div>
        )}
        <div className="space-y-1">
          <Label htmlFor="us-by">Used by (name)</Label>
          <Input id="us-by" value={usedBy} onChange={e => setUsedBy(e.target.value)} placeholder="John Dlamini" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="us-team">Team</Label>
          <Input id="us-team" value={team} onChange={e => setTeam(e.target.value)} placeholder="Foundation crew" />
        </div>
        {stageMasters.length > 0 && (
          <div className="space-y-1">
            <Label htmlFor="us-stage">Milestone (optional)</Label>
            <select id="us-stage" value={stageId} onChange={e => setStageId(e.target.value)}
                    className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
              <option value="">— No milestone —</option>
              {stageMasters.map(m => {
                const s = stages.find(st => st.stage_id === m.id);
                return (
                  <option key={m.id} value={m.id}>
                    {m.name}{s ? ` · ${STAGE_LABEL[s.status] ?? s.status}` : ""}
                  </option>
                );
              })}
            </select>
          </div>
        )}

        {/* Optional evidence photo */}
        <div className="space-y-1">
          <Label className="text-xs">Evidence Photo (optional)</Label>
          <div
            onClick={() => evidenceRef.current?.click()}
            className="flex items-center gap-2 border-2 border-dashed border-border rounded-xl p-3 cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-colors"
          >
            <Image className="w-5 h-5 text-muted-foreground shrink-0" />
            <span className="text-xs text-muted-foreground truncate">
              {evidenceFile ? evidenceFile.name : "Tap to add photo evidence"}
            </span>
            <input
              ref={evidenceRef} type="file" className="sr-only"
              accept="image/*" capture="environment"
              onChange={e => setEvidenceFile(e.target.files?.[0] ?? null)}
            />
          </div>
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Recording…" : "Record Usage"}
        </Button>
      </form>
    </ModalShell>
  );
}

// ── Add to Warehouse (BOQ-linked) ────────────────────────────────────────────
function AddToWarehouseModal({ projectId, boqItems, onClose, onDone }: {
  projectId: string;
  boqItems: MaterialSummaryItem[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [mode,     setMode]     = useState<"boq" | "adhoc">("boq");
  const [boqItemId, setBoqItemId] = useState("");
  const [name,     setName]     = useState("");
  const [qty,      setQty]      = useState("");
  const [unit,     setUnit]     = useState("");
  const [notes,    setNotes]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const selected = boqItems.find(i => i.boq_item_id === boqItemId);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "boq" && !boqItemId) { setError("Select a BOQ item."); return; }
    if (mode === "adhoc" && !name.trim()) { setError("Enter a material name."); return; }
    const quantity = parseFloat(qty);
    if (!qty || isNaN(quantity) || quantity <= 0) { setError("Enter a valid quantity."); return; }

    setLoading(true); setError("");
    try {
      if (mode === "boq" && selected) {
        await warehouseApi.addProjectMaterial(projectId, {
          name:     selected.description,
          quantity,
          unit:     (selected.unit ?? unit) || undefined,
          notes:    notes || undefined,
        });
      } else {
        await warehouseApi.addProjectMaterial(projectId, {
          name:     name.trim(),
          quantity,
          unit:     unit || undefined,
          notes:    notes || undefined,
        });
      }
      onDone();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Failed to add material. Try again.");
    } finally { setLoading(false); }
  };

  return (
    <ModalShell title="Add to Warehouse" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        {/* Mode toggle */}
        <div className="flex gap-2">
          <button type="button"
            className={cn("flex-1 py-2 text-xs font-semibold rounded-lg border transition-colors",
              mode === "boq" ? "bg-primary text-primary-foreground border-primary" : "bg-background border-border hover:bg-muted")}
            onClick={() => setMode("boq")}>
            From BOQ
          </button>
          <button type="button"
            className={cn("flex-1 py-2 text-xs font-semibold rounded-lg border transition-colors",
              mode === "adhoc" ? "bg-primary text-primary-foreground border-primary" : "bg-background border-border hover:bg-muted")}
            onClick={() => setMode("adhoc")}>
            Ad-hoc
          </button>
        </div>

        {mode === "boq" ? (
          <div className="space-y-1">
            <Label>BOQ Item</Label>
            <select value={boqItemId} onChange={e => {
                setBoqItemId(e.target.value);
                const it = boqItems.find(i => i.boq_item_id === e.target.value);
                if (it) setUnit(it.unit ?? "");
              }}
              className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
              <option value="">— Select BOQ item —</option>
              {boqItems.map(i => (
                <option key={i.boq_item_id} value={i.boq_item_id ?? ""}>
                  {i.description} · {i.boq_allocated_qty} {i.unit ?? ""}
                </option>
              ))}
            </select>
            {selected && (
              <div className="bg-muted/40 rounded-lg px-3 py-2 text-xs space-y-0.5">
                <div className="flex justify-between"><span className="text-muted-foreground">BOQ Allocated</span><span className="font-medium">{selected.boq_allocated_qty} {selected.unit ?? ""}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Already Delivered</span><span className="font-medium">{selected.delivered_qty} {selected.unit ?? ""}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Remaining</span>
                  <span className={cn("font-semibold", selected.remaining_qty <= 0 ? "text-destructive" : "text-green-600")}>{selected.remaining_qty} {selected.unit ?? ""}</span>
                </div>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="space-y-1">
              <Label>Material Name</Label>
              <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Cement 32.5N" required />
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input value={unit} onChange={e => setUnit(e.target.value)} placeholder="e.g. bags, m³" />
            </div>
          </>
        )}

        <div className="space-y-1">
          <Label htmlFor="aw-qty">Quantity received</Label>
          <Input id="aw-qty" type="number" min="0.01" step="0.01"
                 value={qty} onChange={e => setQty(e.target.value)} required />
        </div>
        <div className="space-y-1">
          <Label htmlFor="aw-notes">Notes (optional)</Label>
          <Input id="aw-notes" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Supplier ref, batch no, etc." />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Adding…" : "Add to Warehouse"}
        </Button>
      </form>
    </ModalShell>
  );
}

// ── Project-to-Project Transfer ───────────────────────────────────────────────
function ProjectToProjectTransferModal({ fromProjectId, projects, onClose, onDone }: {
  fromProjectId: string;
  projects: Project[];
  warehouseStock: import("@/api/warehouse").WarehouseStockItem[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [toProjectId,  setToProjectId]  = useState("");
  const [stock,        setStock]        = useState<import("@/api/warehouse").WarehouseStockItem[]>([]);
  const [loadingStock, setLoadingStock] = useState(false);
  const [itemId,       setItemId]       = useState("");
  const [qty,          setQty]          = useState("");
  const [notes,        setNotes]        = useState("");
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");

  // Load source warehouse stock
  useEffect(() => {
    if (!fromProjectId) return;
    setLoadingStock(true);
    warehouseApi.getMainStock(fromProjectId)
      .then(setStock).catch(() => setStock([])).finally(() => setLoadingStock(false));
  }, [fromProjectId]);

  const selected = stock.find(s => s.item_id === itemId);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!toProjectId) { setError("Select a destination project."); return; }
    if (!itemId)      { setError("Select an item."); return; }
    const quantity = parseFloat(qty);
    if (!qty || isNaN(quantity) || quantity <= 0) { setError("Enter a valid quantity."); return; }
    if (selected && quantity > selected.on_hand) {
      setError(`Only ${selected.on_hand} ${selected.unit ?? ""} available.`);
      return;
    }

    setLoading(true); setError("");
    try {
      await warehouseApi.transferToProject(fromProjectId, toProjectId, itemId, quantity, notes || undefined);
      onDone();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Transfer failed. Try again.");
    } finally { setLoading(false); }
  };

  const otherProjects = projects.filter(p => p.id !== fromProjectId);

  return (
    <ModalShell title="Project Warehouse Transfer" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Transfer stock from this project's warehouse to another project's warehouse.
        </p>

        <div className="space-y-1">
          <Label>Destination Project</Label>
          <select value={toProjectId} onChange={e => setToProjectId(e.target.value)} required
                  className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
            <option value="">— Select project —</option>
            {otherProjects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>

        <div className="space-y-1">
          <Label>Item</Label>
          {loadingStock ? (
            <p className="text-xs text-muted-foreground py-2">Loading stock…</p>
          ) : stock.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No stock in this warehouse.</p>
          ) : (
            <select value={itemId} onChange={e => setItemId(e.target.value)} required
                    className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
              <option value="">— Select item —</option>
              {stock.map(s => (
                <option key={s.item_id} value={s.item_id}>
                  {s.item_name} · {s.on_hand} {s.unit ?? ""} available
                </option>
              ))}
            </select>
          )}
        </div>

        {selected && (
          <div className="bg-muted/40 rounded-lg px-3 py-2 text-xs">
            <div className="flex justify-between"><span className="text-muted-foreground">Available</span>
              <span className="font-semibold text-green-600">{selected.on_hand} {selected.unit ?? ""}</span>
            </div>
          </div>
        )}

        <div className="space-y-1">
          <Label htmlFor="pt-qty">Quantity to transfer</Label>
          <Input id="pt-qty" type="number" min="0.01" step="0.01"
                 value={qty} onChange={e => setQty(e.target.value)} required />
        </div>
        <div className="space-y-1">
          <Label htmlFor="pt-notes">Notes (optional)</Label>
          <Input id="pt-notes" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Reason for transfer" />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={loading || stock.length === 0}>
          {loading ? "Transferring…" : "Transfer Stock"}
        </Button>
      </form>
    </ModalShell>
  );
}

// ── Update Stage ──────────────────────────────────────────────────────────────
function UpdateStageModal({ projectId, siteId, lotId, stageMasters, stages, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  stageMasters: StageMaster[]; stages: ProjectStageStatus[];
  onClose: () => void; onDone: () => void;
}) {
  const evidenceRef = useRef<HTMLInputElement>(null);
  const userRole = localStorage.getItem(ROLE_KEY) ?? "";
  const isSiteStaff = userRole === "SITE_STAFF";

  const [stageId,        setStageId]        = useState("");
  const [status,         setStatus]         = useState("IN_PROGRESS");
  const [notes,          setNotes]          = useState("");
  const [blockedReason,  setBlockedReason]  = useState("");
  const [progressPct,    setProgressPct]    = useState(0);
  const [plannedDate,    setPlannedDate]    = useState("");
  const [completionNotes, setCompletionNotes] = useState("");
  const [evidenceFile,   setEvidenceFile]   = useState<File | null>(null);
  const [loading,        setLoading]        = useState(false);
  const [error,          setError]          = useState("");

  const STATUS_OPTIONS = [
    "NOT_STARTED", "IN_PROGRESS", "BLOCKED", "AWAITING_INSPECTION", "COMPLETED", "CERTIFIED",
  ] as const;

  // When stage selection changes, pre-fill from existing data
  const currentStage = stages.find(s => s.stage_id === stageId);
  const isCompletedLock = isSiteStaff && (
    currentStage?.status === "COMPLETED" || currentStage?.status === "CERTIFIED"
  );

  const handleStageChange = (id: string) => {
    setStageId(id);
    const s = stages.find(st => st.stage_id === id);
    if (s) {
      setStatus(s.status);
      setProgressPct(s.progress_pct ?? 0);
      setPlannedDate(s.planned_completion_date ?? "");
      setBlockedReason(s.blocked_reason ?? "");
    } else {
      setStatus("IN_PROGRESS");
      setProgressPct(0);
      setPlannedDate("");
      setBlockedReason("");
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!stageId) { setError("Select a stage."); return; }
    if (status === "BLOCKED" && !blockedReason.trim()) {
      setError("A reason is required when blocking a milestone.");
      return;
    }
    setLoading(true); setError("");
    try {
      if (evidenceFile) {
        const fd = new FormData();
        fd.append("stage_id", stageId);
        fd.append("status",   status);
        if (siteId) fd.append("site_id", siteId);
        if (lotId)  fd.append("lot_id",  lotId);
        if (notes)  fd.append("notes",   notes);
        if (status === "BLOCKED" && blockedReason.trim()) fd.append("blocked_reason", blockedReason.trim());
        if (status === "IN_PROGRESS") fd.append("progress_pct", String(progressPct));
        if (plannedDate) fd.append("planned_completion_date", plannedDate);
        if (status === "COMPLETED" && completionNotes) fd.append("completion_notes", completionNotes);
        fd.append("evidence_file", evidenceFile);
        await stagesApi.upsertWithEvidence(projectId, fd);
      } else {
        await stagesApi.upsert(projectId, {
          stage_id:               stageId,
          site_id:                siteId || null,
          lot_id:                 lotId  || null,
          status:                 status as ProjectStageStatus["status"],
          notes:                  notes  || null,
          blocked_reason:         status === "BLOCKED" ? blockedReason.trim() : null,
          progress_pct:           status === "IN_PROGRESS" ? progressPct : undefined,
          planned_completion_date: plannedDate || null,
          completion_notes:       status === "COMPLETED" ? (completionNotes || null) : undefined,
        });
      }
      onDone();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to update. Try again.");
    }
    finally  { setLoading(false); }
  };

  return (
    <ModalShell title="Update Stage" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        {/* Stage selector */}
        <div className="space-y-1">
          <Label>Stage</Label>
          <select value={stageId} onChange={e => handleStageChange(e.target.value)} required
                  className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
            <option value="">— Select stage —</option>
            {stageMasters.map(m => {
              const cur = stages.find(s => s.stage_id === m.id);
              return (
                <option key={m.id} value={m.id}>
                  {m.name}{cur ? ` — ${STAGE_LABEL[cur.status] ?? cur.status}` : ""}
                </option>
              );
            })}
          </select>
        </div>

        {/* Edit-lock for site staff on completed milestones */}
        {isCompletedLock ? (
          <div className="flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-800/50 dark:bg-amber-950/20 px-4 py-3">
            <Lock className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="text-xs text-amber-800 dark:text-amber-300">
              <p className="font-semibold">Milestone completed — locked</p>
              <p className="mt-0.5 text-amber-700 dark:text-amber-400">
                Contact office or admin to reopen this milestone.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Status selector */}
            <div className="space-y-1">
              <Label>New status</Label>
              <select value={status} onChange={e => setStatus(e.target.value)}
                      className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
                {STATUS_OPTIONS.map(s => <option key={s} value={s}>{STAGE_LABEL[s] ?? s}</option>)}
              </select>
            </div>

            {/* BLOCKED — reason required */}
            {status === "BLOCKED" && (
              <div className="space-y-1">
                <Label className="flex items-center gap-1.5 text-destructive">
                  <Ban className="w-3.5 h-3.5" />Block reason *
                </Label>
                <textarea
                  rows={2} value={blockedReason} onChange={e => setBlockedReason(e.target.value)}
                  placeholder="e.g. Waiting for material delivery…"
                  className="w-full px-3 py-2 text-sm rounded-md border border-destructive/50 bg-background resize-none
                             focus:outline-none focus:ring-1 focus:ring-destructive"
                />
              </div>
            )}

            {/* IN_PROGRESS — progress slider */}
            {status === "IN_PROGRESS" && (
              <div className="space-y-1">
                <Label className="flex items-center justify-between">
                  <span>Progress</span>
                  <span className="font-semibold text-foreground">{progressPct}%</span>
                </Label>
                <input
                  type="range" min={0} max={100} step={5}
                  value={progressPct}
                  onChange={e => setProgressPct(parseInt(e.target.value))}
                  className="w-full accent-primary cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-muted-foreground">
                  <span>0%</span><span>50%</span><span>100%</span>
                </div>
              </div>
            )}

            {/* COMPLETED — completion notes */}
            {status === "COMPLETED" && (
              <div className="space-y-1">
                <Label>Completion notes (optional)</Label>
                <textarea rows={2} value={completionNotes} onChange={e => setCompletionNotes(e.target.value)}
                  placeholder="Any notes about the completion…"
                  className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none
                             focus:outline-none focus:ring-1 focus:ring-primary" />
              </div>
            )}

            {/* Planned completion date — always shown */}
            <div className="space-y-1">
              <Label className="flex items-center gap-1.5">
                <CalendarClock className="w-3.5 h-3.5 text-muted-foreground" />
                Planned completion date
              </Label>
              <input
                type="date" value={plannedDate} onChange={e => setPlannedDate(e.target.value)}
                className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background
                           focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            {/* Notes */}
            <div className="space-y-1">
              <Label htmlFor="st-notes">Notes</Label>
              <textarea id="st-notes" rows={2} value={notes} onChange={e => setNotes(e.target.value)}
                        placeholder="Any notes about this stage…"
                        className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none
                                   focus:outline-none focus:ring-1 focus:ring-primary" />
            </div>

            {/* Progress photo */}
            <div className="space-y-1">
              <Label className="text-xs">Progress Photo (optional)</Label>
              <div
                onClick={() => evidenceRef.current?.click()}
                className="flex items-center gap-2 border-2 border-dashed border-border rounded-xl p-3 cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-colors"
              >
                <Camera className="w-5 h-5 text-muted-foreground shrink-0" />
                <span className="text-xs text-muted-foreground truncate">
                  {evidenceFile ? evidenceFile.name : "Tap to add progress photo"}
                </span>
                <input
                  ref={evidenceRef} type="file" className="sr-only"
                  accept="image/*" capture="environment"
                  onChange={e => setEvidenceFile(e.target.files?.[0] ?? null)}
                />
              </div>
            </div>

            {error && <p className="text-xs text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Updating…" : "Update Stage"}
            </Button>
          </>
        )}
      </form>
    </ModalShell>
  );
}

// ── Upload Delivery Note — real multi-step flow ───────────────────────────────
type UploadStep = "upload" | "correct" | "sign" | "done";

function DeliveryNoteUploadModal({ projectId, siteId, lotId, suppliers, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  suppliers: Supplier[]; onClose: () => void; onDone: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [step,         setStep]         = useState<UploadStep>("upload");
  const [file,         setFile]         = useState<File | null>(null);
  const [verificationId, setVerifId]   = useState("");
  const [extracted,    setExtracted]    = useState<import("@/api/siteCapture").DeliveryNoteUploadResult | null>(null);
  const [items,        setItems]        = useState<ExtractedItem[]>([]);
  const [dnNumber,     setDnNumber]     = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [signature,    setSignature]    = useState("");
  const [signedBy,     setSignedBy]     = useState("");
  const [result,       setResult]       = useState<{ status: string } | null>(null);
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");

  // ── Step 1: Upload ──
  const handleUpload = async () => {
    if (!file || !siteId) { setError("Select a file and ensure a site is selected."); return; }
    setLoading(true); setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("site_id", siteId);
      if (lotId)         fd.append("lot_id", lotId);
      if (supplierName)  fd.append("supplier_name", supplierName);
      const res = await siteCaptureApi.uploadDeliveryNote(fd);
      setVerifId(res.id);
      setExtracted(res);
      setDnNumber(res.extracted_fields.delivery_note_number ?? "");
      setSupplierName(res.extracted_fields.supplier_name ?? supplierName);
      // Default items from extraction, or one empty row
      setItems(
        res.items.length > 0 ? res.items
        : [{ description: "", unit: "", ocr_qty: null, actual_received_qty: 0, accepted_qty: 0, rejected_qty: 0, mismatch_reason: null }]
      );
      setStep("correct");
    } catch (e: unknown) {
      const msg = (e as {response?: {data?: {detail?: string}}})?.response?.data?.detail;
      setError(msg || "Upload failed. Check connection and try again.");
    }
    finally   { setLoading(false); }
  };

  // ── Step 2: Correct ──
  const handleCorrect = async () => {
    if (!verificationId) return;
    setLoading(true); setError("");
    try {
      await siteCaptureApi.correctDeliveryNote(verificationId, {
        supplier_name:        supplierName || null,
        delivery_note_number: dnNumber || null,
        items,
      });
      setStep("sign");
    } catch (e: unknown) {
      const msg = (e as {response?: {data?: {detail?: string}}})?.response?.data?.detail;
      setError(msg || "Could not save corrections. Try again.");
    }
    finally   { setLoading(false); }
  };

  // ── Step 3: Sign + Verify ──
  const handleSign = async () => {
    if (!verificationId) return;
    setLoading(true); setError("");
    try {
      // Save signature first (text or initials are acceptable as MVP)
      await siteCaptureApi.saveSignature(verificationId, signature || signedBy || "Signed", signedBy);
      // Then verify quantities
      const res = await siteCaptureApi.verify(verificationId);
      setResult(res);
      setStep("done");
      onDone();
    } catch (e: unknown) {
      const msg = (e as {response?: {data?: {detail?: string}}})?.response?.data?.detail;
      setError(msg || "Could not complete verification. Check that all fields are filled.");
    }
    finally   { setLoading(false); }
  };

  const updateItem = (idx: number, field: keyof ExtractedItem, value: string | number | null) => {
    setItems((prev) => prev.map((it, i) => i === idx ? { ...it, [field]: value } : it));
  };

  const titles: Record<UploadStep, string> = {
    upload:  "Upload Delivery Note",
    correct: "Correct Extracted Data",
    sign:    "Sign & Verify",
    done:    "Verification Complete",
  };

  return (
    <ModalShell title={titles[step]} onClose={onClose}>
      {error && <p className="text-xs text-destructive bg-destructive/10 rounded px-3 py-2 mb-2">{error}</p>}

      {/* ── Step 1: Upload ── */}
      {step === "upload" && (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Upload a photo or PDF of the delivery note. The system will extract key fields automatically.
          </p>
          <div className="space-y-1">
            <Label>File (photo / PDF)</Label>
            <div
              onClick={() => fileRef.current?.click()}
              className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-border rounded-xl p-6 cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-colors"
            >
              {file
                ? <p className="text-sm font-medium text-primary">{file.name}</p>
                : <>
                    <Camera className="w-6 h-6 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">Tap to take photo or choose file</p>
                  </>
              }
              <input
                ref={fileRef} type="file" className="sr-only"
                accept="image/*,.pdf" capture="environment"
                onChange={(e) => { setFile(e.target.files?.[0] ?? null); setError(""); }}
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="dn-supplier">Supplier (optional)</Label>
            <select id="dn-supplier" value={supplierName} onChange={(e) => setSupplierName(e.target.value)}
              className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
              <option value="">— Select supplier —</option>
              {suppliers.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
            </select>
          </div>
          <Button className="w-full" onClick={handleUpload} disabled={loading || !file}>
            {loading ? "Uploading…" : "Upload & Extract"}
          </Button>
          <Button variant="outline" className="w-full" onClick={onClose}>Cancel</Button>
        </div>
      )}

      {/* ── Step 2: Correct ── */}
      {step === "correct" && extracted && (
        <div className="space-y-3">
          {(extracted.status === "OCR_NOT_AVAILABLE" || extracted.status === "OCR_FAILED") && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-700">
              {extracted.status === "OCR_FAILED"
                ? "Google Vision configured but returned no text — verify GOOGLE_CREDENTIALS_JSON on Render. Enter data manually."
                : "OCR is not available — enter data manually."}
            </div>
          )}
          {extracted.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-600">{w}</p>
          ))}
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label htmlFor="dn-num">Delivery Note #</Label>
              <Input id="dn-num" value={dnNumber} onChange={(e) => setDnNumber(e.target.value)} placeholder="DN-001" className="h-8 text-sm" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="dn-sup">Supplier</Label>
              <Input id="dn-sup" value={supplierName} onChange={(e) => setSupplierName(e.target.value)} placeholder="Supplier name" className="h-8 text-sm" />
            </div>
          </div>

          <div>
            <Label className="mb-1 block">Items received</Label>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {items.map((it, idx) => (
                <div key={idx} className="grid grid-cols-[1fr_auto_auto_auto] gap-1.5 items-center bg-muted/30 rounded-lg p-2">
                  <Input value={it.description} onChange={(e) => updateItem(idx, "description", e.target.value)}
                    placeholder="Description" className="h-7 text-xs" />
                  <div className="text-center">
                    <p className="text-[10px] text-muted-foreground mb-0.5">OCR Qty</p>
                    <p className="text-xs font-medium tabular-nums">{it.ocr_qty ?? "—"}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-muted-foreground mb-0.5">Received</p>
                    <Input type="number" min="0" step="0.1" value={it.actual_received_qty}
                      onChange={(e) => { const v = parseFloat(e.target.value)||0; updateItem(idx,"actual_received_qty",v); updateItem(idx,"accepted_qty",v); }}
                      className="h-7 text-xs w-16 text-right" />
                  </div>
                  <div>
                    <p className="text-[10px] text-muted-foreground mb-0.5">Rejected</p>
                    <Input type="number" min="0" step="0.1" value={it.rejected_qty}
                      onChange={(e) => updateItem(idx,"rejected_qty",parseFloat(e.target.value)||0)}
                      className="h-7 text-xs w-16 text-right" />
                  </div>
                </div>
              ))}
            </div>
            <button onClick={() => setItems((p) => [...p, { description:"",unit:"",ocr_qty:null,actual_received_qty:0,accepted_qty:0,rejected_qty:0,mismatch_reason:null }])}
              className="mt-2 text-xs text-primary hover:underline">+ Add item</button>
          </div>

          <Button className="w-full" onClick={handleCorrect} disabled={loading}>
            {loading ? "Saving…" : "Save Corrections → Sign"}
          </Button>
          <Button variant="outline" className="w-full" onClick={() => setStep("upload")}>Back</Button>
        </div>
      )}

      {/* ── Step 3: Sign ── */}
      {step === "sign" && (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Sign below to confirm you received and verified this delivery.
          </p>
          <div className="space-y-1">
            <Label htmlFor="sig-by">Received by (name)</Label>
            <Input id="sig-by" value={signedBy} onChange={(e) => setSignedBy(e.target.value)} placeholder="Your full name" className="h-10" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sig-text">Signature text / initials</Label>
            <Input id="sig-text" value={signature} onChange={(e) => setSignature(e.target.value)} placeholder="e.g. J. Smith" className="h-10 font-mono text-lg" />
            <p className="text-xs text-muted-foreground">Digital signature pad coming soon. Text initials accepted.</p>
          </div>
          <Button className="w-full" onClick={handleSign} disabled={loading || (!signature && !signedBy)}>
            {loading ? "Verifying…" : "Sign & Verify Delivery"}
          </Button>
          <Button variant="outline" className="w-full" onClick={() => setStep("correct")}>Back</Button>
        </div>
      )}

      {/* ── Step 4: Done ── */}
      {step === "done" && result && (
        <div className="flex flex-col items-center gap-4 py-4 text-center">
          {result.status === "VERIFIED"
            ? <><CheckCircle2 className="w-12 h-12 text-success" /><p className="text-sm font-semibold text-success">Delivery Verified</p></>
            : <><AlertTriangle className="w-12 h-12 text-amber-500" /><p className="text-sm font-semibold text-amber-600">Mismatch Detected — Alert Created</p></>
          }
          <p className="text-xs text-muted-foreground">
            The delivery verification record has been saved. It will appear in recent deliveries.
          </p>
          <Button className="w-full" onClick={onClose}>Done</Button>
        </div>
      )}
    </ModalShell>
  );
}

// ── Sign Delivery ─────────────────────────────────────────────────────────────
function SignDeliveryModal({ deliveries, onClose, onDone }: {
  deliveries: Delivery[]; onClose: () => void; onDone: () => void;
}) {
  const [deliveryId, setDeliveryId] = useState("");
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");
  const [done,       setDone]       = useState(false);

  const candidates = deliveries
    .filter(d => d.delivery_status !== "CANCELLED")
    .slice(0, 10);

  const confirm = async () => {
    if (!deliveryId) { setError("Select a delivery."); return; }
    setLoading(true); setError("");
    try {
      await deliveriesApi.update(deliveryId, { delivery_status: "RECEIVED" });
      setDone(true);
      onDone();
    } catch { setError("Failed to update. Try again."); }
    finally  { setLoading(false); }
  };

  if (done) {
    return (
      <ModalShell title="Sign Delivery" onClose={onClose}>
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <CheckCircle2 className="w-12 h-12 text-green-500" />
          <p className="text-sm font-semibold">Delivery marked as received.</p>
          <Button className="w-full" onClick={onClose}>Done</Button>
        </div>
      </ModalShell>
    );
  }

  return (
    <ModalShell title="Sign / Verify Delivery" onClose={onClose}>
      <p className="text-xs text-muted-foreground">
        Select a delivery to mark it as received and verified. Digital signature
        capture is coming in the next update.
      </p>
      <div className="space-y-1">
        <Label>Delivery</Label>
        <select value={deliveryId} onChange={e => setDeliveryId(e.target.value)}
                className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
          <option value="">— Select delivery —</option>
          {candidates.map(d => (
            <option key={d.id} value={d.id}>
              {d.delivery_number ?? d.id.slice(0, 8)} · {shortDate(d.delivery_date)} ·{" "}
              {d.delivery_status.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <Button className="w-full" onClick={confirm} disabled={loading || !deliveryId}>
        {loading ? "Verifying…" : "Mark as Verified"}
      </Button>
      <Button variant="outline" className="w-full mt-2" onClick={onClose}>Cancel</Button>
    </ModalShell>
  );
}

// ── Create Job Card ───────────────────────────────────────────────────────────
const WORK_TYPES = [
  { value: "DAILY_LABOUR",  label: "Daily Labour" },
  { value: "CONTRACT",      label: "Contract" },
  { value: "SUBCONTRACTOR", label: "Subcontractor" },
  { value: "OVERTIME",      label: "Overtime" },
] as const;

function CreateJobCardModal({ projectId, siteId, lotId, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  onClose: () => void; onDone: () => void;
}) {
  const [description, setDescription] = useState("");
  const [workType,    setWorkType]    = useState<string>("DAILY_LABOUR");
  const [workerName,  setWorkerName]  = useState("");
  const [teamName,    setTeamName]    = useState("");
  const [quantity,    setQuantity]    = useState("1");
  const [unit,        setUnit]        = useState("");
  const [rate,        setRate]        = useState("");
  const [workDate,    setWorkDate]    = useState(todayStr());
  const [notes,       setNotes]       = useState("");
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim()) { setError("Work description is required."); return; }
    if (!rate || parseFloat(rate) <= 0) { setError("Rate must be greater than 0."); return; }
    if (!siteId) { setError("A site must be selected."); return; }
    setLoading(true); setError("");
    try {
      const jc = await jobCardsApi.create(projectId, {
        site_id:          siteId,
        lot_id:           lotId || undefined,
        work_description: description.trim(),
        work_type:        workType as "DAILY_LABOUR" | "CONTRACT" | "SUBCONTRACTOR" | "OVERTIME",
        worker_name:      workerName.trim() || undefined,
        team_name:        teamName.trim()   || undefined,
        quantity:         parseFloat(quantity) || 1,
        unit:             unit.trim()          || undefined,
        rate:             parseFloat(rate),
        work_date:        workDate || undefined,
        notes:            notes.trim()         || undefined,
      });
      await jobCardsApi.submit(jc.id);
      onDone();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to create job card. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell title="Log Job Card" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="jc-desc">Work description *</Label>
          <textarea
            id="jc-desc" rows={2} required
            value={description} onChange={e => setDescription(e.target.value)}
            placeholder="e.g. Foundation excavation for Block A"
            className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none
                       focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label htmlFor="jc-type">Work type</Label>
            <select id="jc-type" value={workType} onChange={e => setWorkType(e.target.value)}
                    className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
              {WORK_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="jc-date">Work date</Label>
            <Input id="jc-date" type="date" value={workDate} onChange={e => setWorkDate(e.target.value)} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label htmlFor="jc-worker">Worker name</Label>
            <Input id="jc-worker" value={workerName} onChange={e => setWorkerName(e.target.value)} placeholder="John Dlamini" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="jc-team">Team</Label>
            <Input id="jc-team" value={teamName} onChange={e => setTeamName(e.target.value)} placeholder="Foundation crew" />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-1">
            <Label htmlFor="jc-qty">Quantity</Label>
            <Input id="jc-qty" type="number" min="0.01" step="any" value={quantity} onChange={e => setQuantity(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="jc-unit">Unit</Label>
            <Input id="jc-unit" value={unit} onChange={e => setUnit(e.target.value)} placeholder="m², days…" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="jc-rate">Rate (R) *</Label>
            <Input id="jc-rate" type="number" min="0.01" step="any" required value={rate} onChange={e => setRate(e.target.value)} placeholder="0.00" />
          </div>
        </div>

        {quantity && rate && parseFloat(quantity) > 0 && parseFloat(rate) > 0 && (
          <p className="text-xs text-muted-foreground bg-muted/40 rounded px-2 py-1">
            Total: <strong>R {(parseFloat(quantity) * parseFloat(rate)).toFixed(2)}</strong>
          </p>
        )}

        <div className="space-y-1">
          <Label htmlFor="jc-notes">Notes (optional)</Label>
          <textarea
            id="jc-notes" rows={2}
            value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="Any additional details…"
            className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none
                       focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Submitting…" : "Submit Job Card"}
        </Button>
      </form>
    </ModalShell>
  );
}
