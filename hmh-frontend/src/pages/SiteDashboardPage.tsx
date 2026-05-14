import { useState, useEffect, useCallback, useRef } from "react";
import {
  LogOut, RefreshCw, PackagePlus, Truck, Minus,
  ListChecks, Upload, PenLine, AlertTriangle, CheckCircle2,
  Clock, Circle, ChevronRight, Box, Bell, Camera, Image,
} from "lucide-react";
import { siteCaptureApi, type ExtractedItem } from "@/api/siteCapture";
import { siteDashboardApi, type MaterialSummaryItem, type ActivityItem } from "@/api/siteDashboard";
import { BOQAllocationTable } from "@/components/site/BOQAllocationTable";
import { HMHLogo } from "@/components/HMHLogo";
import { TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { lotsApi, type Lot } from "@/api/lots";
import { materialRequestsApi, type MaterialRequest } from "@/api/materialRequests";
import { deliveriesApi, type Delivery } from "@/api/deliveries";
import { stagesApi, type ProjectStageStatus, type StageMaster } from "@/api/stages";
import { alertsApi, type Alert } from "@/api/alerts";
import { stockApi, type StockBalance, type StockLedgerEntry } from "@/api/stock";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { cn } from "@/lib/utils";

// ── Storage keys ──────────────────────────────────────────────────────────────
const SK_PROJECT = "site_project_id";
const SK_SITE    = "site_site_id";
const SK_LOT     = "site_lot_id";

// ── Helpers ───────────────────────────────────────────────────────────────────
const todayStr = () => new Date().toISOString().split("T")[0];

const STAGE_LABEL: Record<string, string> = {
  NOT_STARTED:         "Not Started",
  IN_PROGRESS:         "In Progress",
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
type ModalType = "request" | "delivery" | "usage" | "stage" | null;

export default function SiteDashboardPage() {

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
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [stages,    setStages]    = useState<ProjectStageStatus[]>([]);
  const [alerts,    setAlerts]    = useState<Alert[]>([]);
  const [balances,        setBalances]        = useState<StockBalance[]>([]);
  const [ledger,          setLedger]          = useState<StockLedgerEntry[]>([]);
  const [materialSummary, setMaterialSummary] = useState<MaterialSummaryItem[]>([]);
  const [activity,        setActivity]        = useState<ActivityItem[]>([]);

  const [loading,  setLoading]  = useState(false);
  const [loadErr,  setLoadErr]  = useState("");
  const [modal,    setModal]    = useState<ModalType>(null);

  // ── Persist selection changes ──
  const selectProject = (id: string) => {
    setProjectId(id); localStorage.setItem(SK_PROJECT, id);
    setSiteId(""); localStorage.removeItem(SK_SITE);
    setLotId("");  localStorage.removeItem(SK_LOT);
    setMrs([]); setDeliveries([]); setAlerts([]);
    setBalances([]); setLedger([]); setStages([]);
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
    projectsApi.list(1, 100, "ACTIVE").then(r => setProjects(r.items)).catch(() => {});
    stagesApi.listMasters().then(setStageMasters).catch(() => {});
    suppliersApi.list().then(setSuppliers).catch(() => {});
  }, []);

  // ── Load sites + lots when project changes ──
  useEffect(() => {
    if (!projectId) { setSites([]); setLots([]); return; }
    sitesApi.list(projectId).then(setSites).catch(() => {});
    lotsApi.list(projectId).then(setLots).catch(() => {});
  }, [projectId]);

  // ── Load live data ──
  const loadData = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setLoadErr("");

    const stageParams = lotId  ? { lot_id: lotId }
                      : siteId ? { site_id: siteId }
                      : {};

    Promise.all([
      materialRequestsApi.list(projectId).catch((): MaterialRequest[]    => []),
      deliveriesApi.list(projectId).catch(():    Delivery[]              => []),
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
  }, [projectId, siteId, lotId]);

  useEffect(() => { loadData(); }, [loadData]);

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

  // ── Recent activity ──
  // Legacy computed activity (fallback when API data not yet loaded)
  type LegacyActivity = { id: string; label: string; sub: string; date: string; kind: "del" | "use" | "alert" };
  const legacyActivity: LegacyActivity[] = [
    ...deliveries.slice(0, 8).map(d => ({
      id: d.id, kind: "del" as const,
      label: `Delivery ${d.delivery_number || d.id.slice(0, 8)}`,
      sub: d.delivery_status.replace(/_/g, " "),
      date: d.delivery_date,
    })),
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
        <div className="flex items-center min-w-0">
          <HMHLogo size="sm" />
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
          <Select value={projectId} onChange={selectProject}>
            <option value="">— Select project —</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>

          {projectId && (
            <Select value={siteId} onChange={selectSite} disabled={!projectId}>
              <option value="">— Select site —</option>
              {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          )}

          {siteId && (
            <Select value={lotId} onChange={selectLot}>
              <option value="">— All lots —</option>
              {lots
                .filter(l => !l.site_id || l.site_id === siteId)
                .sort((a, b) => {
                  const na = parseInt(a.lot_number), nb = parseInt(b.lot_number);
                  return isNaN(na) || isNaN(nb) ? a.lot_number.localeCompare(b.lot_number) : na - nb;
                })
                .map(l => (
                  <option key={l.id} value={l.id}>
                    {l.lot_number}{l.unit_type ? ` · ${l.unit_type}` : ""}
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
                <ActionBtn icon={PackagePlus} label="Request Material"   onClick={() => setModal("request")} />
                <ActionBtn icon={Truck}       label="Receive Delivery"   onClick={() => setModal("delivery")} />
                <ActionBtn icon={Minus}       label="Record Usage"       onClick={() => setModal("usage")} />
                <ActionBtn icon={ListChecks}  label="Update Stage"       onClick={() => setModal("stage")} />
              </div>
            </Section>

            {/* ── BOQ Allocation / Usage / Remaining ── */}
            {siteId && lotId && (
              <BOQAllocationTable
                items={materialSummary}
                loading={loading}
                fromSiteTemplate={materialSummary[0]?.from_site_template ?? false}
                onRecordUsage={() => setModal("usage")}
                onReceiveDelivery={() => setModal("delivery")}
              />
            )}

            {/* ── Site Stock (fallback when no lot selected) ── */}
            {siteId && !lotId && matRows.length > 0 && (
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

            {/* ── Stage timeline ── */}
            {siteId && stageRows.length > 0 && (
              <Section title="Stage Timeline">
                <div className="space-y-2">
                  {stageRows.map(s => (
                    <div key={s.id} className="flex items-center gap-3 p-3 bg-card border border-border rounded-xl">
                      <div className="shrink-0">
                        {s.status === "COMPLETED" || s.status === "CERTIFIED"
                          ? <CheckCircle2 className="w-5 h-5 text-green-500" />
                          : s.status === "IN_PROGRESS"
                          ? <Clock className="w-5 h-5 text-blue-500" />
                          : s.status === "AWAITING_INSPECTION"
                          ? <AlertTriangle className="w-5 h-5 text-amber-500" />
                          : <Circle className="w-5 h-5 text-muted-foreground/50" />
                        }
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium truncate">{s.stage_name ?? "Stage"}</p>
                        <p className={cn("text-xs", STAGE_COLOR[s.status] ?? "text-muted-foreground")}>
                          {STAGE_LABEL[s.status] ?? s.status}
                        </p>
                        {s.started_at && (
                          <p className="text-xs text-muted-foreground">
                            Started {shortDate(s.started_at)}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => setModal("stage")}
                        className="shrink-0 p-1 rounded hover:bg-muted"
                        title="Update stage"
                      >
                        <ChevronRight className="w-4 h-4 text-muted-foreground" />
                      </button>
                    </div>
                  ))}
                </div>
              </Section>
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
                      icon:  a.kind === "del"   ? <Truck className="w-4 h-4 text-blue-500 shrink-0" />
                           : a.kind === "use"   ? <Box   className="w-4 h-4 text-purple-500 shrink-0" />
                           :                      <Bell  className="w-4 h-4 text-amber-500 shrink-0" />,
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
          </>
        )}
      </div>

      {/* ── Modals ── */}
      {modal === "request"  && (
        <RequestMaterialModal
          projectId={projectId} siteId={siteId} lotId={lotId}
          suppliers={suppliers}
          onClose={() => setModal(null)} onDone={() => { setModal(null); loadData(); }}
        />
      )}
      {modal === "delivery" && (
        <UnifiedReceiveModal
          projectId={projectId} siteId={siteId} lotId={lotId}
          suppliers={suppliers}
          onClose={() => setModal(null)} onDone={() => { setModal(null); loadData(); }}
        />
      )}
      {modal === "usage" && (
        <RecordUsageModal
          projectId={projectId} siteId={siteId} lotId={lotId}
          balances={balances} materialSummary={materialSummary}
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
      {/* Upload Delivery Note removed — use Receive Delivery for the unified flow */}
      {/* Sign Delivery removed — signing now happens inline in Receive Delivery modal */}
    </div>
  );
}

// ── Request Material ──────────────────────────────────────────────────────────
function RequestMaterialModal({ projectId, siteId, lotId, suppliers, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  suppliers: Supplier[]; onClose: () => void; onDone: () => void;
}) {
  const [desc,       setDesc]       = useState("");
  const [qty,        setQty]        = useState("");
  const [unit,       setUnit]       = useState("bags");
  const [neededBy,   setNeededBy]   = useState("");
  const [notes,      setNotes]      = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId) { setError("Select a project first."); return; }
    setLoading(true); setError("");
    try {
      await materialRequestsApi.create(projectId, {
        site_id:                siteId      || null,
        lot_id:                 lotId       || null,
        preferred_supplier_id:  supplierId  || null,
        needed_by_date:         neededBy    || null,
        notes:                  notes       || null,
        items: [{ description: desc, quantity_requested: parseFloat(qty), unit: unit || null }],
      });
      onDone();
    } catch { setError("Failed to submit. Try again."); }
    finally  { setLoading(false); }
  };

  return (
    <ModalShell title="Request Material" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="rm-desc">Material</Label>
          <Input id="rm-desc" value={desc} onChange={e => setDesc(e.target.value)}
                 required placeholder="e.g. Cement 50kg bags" />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label htmlFor="rm-qty">Quantity</Label>
            <Input id="rm-qty" type="number" min="0.1" step="0.1"
                   value={qty} onChange={e => setQty(e.target.value)} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="rm-unit">Unit</Label>
            <Input id="rm-unit" value={unit} onChange={e => setUnit(e.target.value)} placeholder="bags" />
          </div>
        </div>
        <div className="space-y-1">
          <Label htmlFor="rm-supplier">Preferred supplier (optional)</Label>
          <select id="rm-supplier" value={supplierId} onChange={e => setSupplierId(e.target.value)}
                  className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
            <option value="">— No preference —</option>
            {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="rm-date">Needed by</Label>
          <Input id="rm-date" type="date" min={todayStr()}
                 value={neededBy} onChange={e => setNeededBy(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="rm-notes">Notes</Label>
          <textarea id="rm-notes" rows={2} value={notes} onChange={e => setNotes(e.target.value)}
                    placeholder="Any additional details…"
                    className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none
                               focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? "Submitting…" : "Submit Request"}
        </Button>
      </form>
    </ModalShell>
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
}

const emptyItem = (): DeliveryLineItem => ({
  description: "", unit: "bags",
  quantity_expected: "", quantity_received: "", quantity_rejected: "0", reason: "",
});

function UnifiedReceiveModal({ projectId, siteId, lotId, suppliers, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  suppliers: Supplier[]; onClose: () => void; onDone: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [step,         setStep]         = useState<ReceiveStep>("document");
  const [file,         setFile]         = useState<File | null>(null);
  const [supplierId,   setSupplierId]   = useState("");
  const [dnNum,        setDnNum]        = useState("");
  const [items,        setItems]        = useState<DeliveryLineItem[]>([emptyItem()]);
  const [driverName,   setDriverName]   = useState("");
  const [driverSig,    setDriverSig]    = useState("");
  const [staffName,    setStaffName]    = useState("");
  const [staffSig,     setStaffSig]     = useState("");
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");
  const [warning,      setWarning]      = useState("");
  const [result,       setResult]       = useState<{ delivery_number: string; is_partial: boolean } | null>(null);

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
          if (res.items.length > 0) {
            setItems(res.items.map(i => ({
              description:       i.description || "",
              unit:              i.unit || "bags",
              quantity_expected: String(i.ocr_qty ?? ""),
              quantity_received: String(i.actual_received_qty || i.ocr_qty || ""),
              quantity_rejected: "0",
              reason:            "",
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
      if (lotId) fd.append("lot_id", lotId);
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
            quantity_expected: i.quantity_expected ? parseFloat(i.quantity_expected) : null,
            quantity_received: parseFloat(i.quantity_received || "0"),
            quantity_rejected: parseFloat(i.quantity_rejected || "0"),
            reason:            i.reason || null,
          }))
      ));
      const res = await deliveriesApi.receiveWithDocument(fd);
      setResult({ delivery_number: res.delivery_number, is_partial: res.is_partial });
      setStep("done");
      onDone();
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
            </div>
            <div className="space-y-1">
              <Label htmlFor="u-dn">Delivery Note #</Label>
              <Input id="u-dn" value={dnNum} onChange={e => setDnNum(e.target.value)} placeholder="DN-001" />
            </div>
          </div>

          <div className="space-y-2">
            <Label>Items received <span className="text-destructive">*</span></Label>
            <div className="max-h-48 overflow-y-auto space-y-2">
              {items.map((it, idx) => (
                <div key={idx} className="bg-muted/30 rounded-lg p-2 space-y-1.5">
                  <Input value={it.description} onChange={e => updateItem(idx, "description", e.target.value)}
                         placeholder="Material description" className="h-8 text-sm" />
                  <div className="grid grid-cols-4 gap-1">
                    <Input type="number" placeholder="Ordered" value={it.quantity_expected}
                           onChange={e => updateItem(idx, "quantity_expected", e.target.value)}
                           className="h-7 text-xs" />
                    <Input type="number" placeholder="Received" value={it.quantity_received}
                           onChange={e => updateItem(idx, "quantity_received", e.target.value)}
                           className="h-7 text-xs" />
                    <Input type="number" placeholder="Rejected" value={it.quantity_rejected}
                           onChange={e => updateItem(idx, "quantity_rejected", e.target.value)}
                           className="h-7 text-xs" />
                    <Input placeholder="Unit" value={it.unit}
                           onChange={e => updateItem(idx, "unit", e.target.value)}
                           className="h-7 text-xs" />
                  </div>
                  {(parseFloat(it.quantity_rejected || "0") > 0) && (
                    <Input placeholder="Reason for rejection/shortage"
                           value={it.reason} onChange={e => updateItem(idx, "reason", e.target.value)}
                           className="h-7 text-xs text-amber-700 border-amber-300" />
                  )}
                </div>
              ))}
            </div>
            <button onClick={() => setItems(p => [...p, emptyItem()])}
                    className="text-xs text-primary hover:underline">+ Add item</button>
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
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <CheckCircle2 className="w-12 h-12 text-green-500" />
          <div>
            <p className="font-semibold">{result.delivery_number} recorded.</p>
            {result.is_partial && (
              <p className="text-sm text-amber-600 mt-1">Short delivery detected — alert created.</p>
            )}
          </div>
          <Button className="w-full" onClick={onClose}>Done</Button>
        </div>
      )}
    </ModalShell>
  );
}

// ── Record Usage ──────────────────────────────────────────────────────────────
function RecordUsageModal({ projectId, siteId, lotId, balances, materialSummary, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  balances: StockBalance[]; materialSummary: MaterialSummaryItem[];
  onClose: () => void; onDone: () => void;
}) {
  const evidenceRef = useRef<HTMLInputElement>(null);
  const [itemId,        setItemId]       = useState("");
  const [qty,           setQty]          = useState("");
  const [usedBy,        setUsedBy]       = useState("");
  const [team,          setTeam]         = useState("");
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
        if (overrunReason)      fd.append("overrun_reason",      overrunReason);
        fd.append("evidence_file", evidenceFile);
        await stockApi.recordUsageWithEvidence(projectId, fd);
      } else {
        await stockApi.recordUsage(projectId, {
          site_id:             siteId,
          item_id:             catalogItemId,
          quantity_used:       parseFloat(qty),
          lot_id:              lotId  || null,
          used_by_person_name: usedBy || null,
          used_by_team_name:   team   || null,
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

// ── Update Stage ──────────────────────────────────────────────────────────────
function UpdateStageModal({ projectId, siteId, lotId, stageMasters, stages, onClose, onDone }: {
  projectId: string; siteId: string; lotId: string;
  stageMasters: StageMaster[]; stages: ProjectStageStatus[];
  onClose: () => void; onDone: () => void;
}) {
  const evidenceRef = useRef<HTMLInputElement>(null);
  const [stageId,      setStageId]     = useState("");
  const [status,       setStatus]      = useState("IN_PROGRESS");
  const [notes,        setNotes]       = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [loading,      setLoading]     = useState(false);
  const [error,        setError]       = useState("");

  const STATUS_OPTIONS = [
    "NOT_STARTED", "IN_PROGRESS", "AWAITING_INSPECTION", "COMPLETED", "CERTIFIED",
  ] as const;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!stageId) { setError("Select a stage."); return; }
    setLoading(true); setError("");
    try {
      if (evidenceFile) {
        const fd = new FormData();
        fd.append("stage_id", stageId);
        fd.append("status",   status);
        if (siteId) fd.append("site_id", siteId);
        if (lotId)  fd.append("lot_id",  lotId);
        if (notes)  fd.append("notes",   notes);
        fd.append("evidence_file", evidenceFile);
        await stagesApi.upsertWithEvidence(projectId, fd);
      } else {
        await stagesApi.upsert(projectId, {
          stage_id: stageId,
          site_id:  siteId || null,
          lot_id:   lotId  || null,
          status:   status as ProjectStageStatus["status"],
          notes:    notes  || null,
        });
      }
      onDone();
    } catch { setError("Failed to update. Try again."); }
    finally  { setLoading(false); }
  };

  return (
    <ModalShell title="Update Stage" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div className="space-y-1">
          <Label>Stage</Label>
          <select value={stageId} onChange={e => setStageId(e.target.value)} required
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
        <div className="space-y-1">
          <Label>New status</Label>
          <select value={status} onChange={e => setStatus(e.target.value)}
                  className="w-full h-10 px-3 text-sm rounded-md border border-border bg-background">
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
          </select>
        </div>
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
          {extracted.status === "OCR_NOT_AVAILABLE" && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-700">
              OCR is not available — enter data manually.
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
