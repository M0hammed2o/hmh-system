import { useEffect, useState } from "react";
import { Plus, Droplet, Flame, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { fuelApi, type FuelLog, type FuelType, type FuelUsageType, FUEL_TYPE_LABELS, FUEL_USAGE_LABELS } from "@/api/fuel";
import { vehiclesApi, type Vehicle } from "@/api/vehicles";
import { formatCurrency, formatDate } from "@/lib/format";

// ─── Log Fuel Modal ────────────────────────────────────────────────────────────
function LogFuelModal({
  open,
  onClose,
  projects,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  projects: Project[];
  onSubmit: (projectId: string, data: {
    fuel_type: FuelType;
    usage_type: FuelUsageType;
    litres: number;
    cost_per_litre: string;
    equipment_ref: string;
    fuelled_by: string;
    site_id: string;
    fuel_date: string;
    odometer_reading?: number | null;
    notes: string;
  }) => Promise<void>;
}) {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [sites, setSites] = useState<Site[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [vehicleId, setVehicleId] = useState("");
  const [fuelType, setFuelType] = useState<FuelType>("DIESEL");
  const [usageType, setUsageType] = useState<FuelUsageType>("EQUIPMENT");
  const [litres, setLitres] = useState("");
  const [costPerLitre, setCostPerLitre] = useState("");
  const [equipmentRef, setEquipmentRef] = useState("");
  const [fuelledBy, setFuelledBy] = useState("");
  const [siteId, setSiteId] = useState("");
  const [fuelDate, setFuelDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [odometer, setOdometer] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (projects.length > 0 && !projectId) setProjectId(projects[0].id);
  }, [projects, projectId]);

  useEffect(() => {
    if (!projectId) return;
    sitesApi.list(projectId).then((s) => {
      setSites(s);
      setSiteId(s[0]?.id ?? "");
    }).catch(() => setSites([]));
    // Load all vehicles (not filtered by project) so the Site Hilux and others always appear
    vehiclesApi.list().then(setVehicles).catch(() => setVehicles([]));
  }, [projectId]);

  const handleSubmit = async () => {
    if (!projectId || !litres) return;
    setSaving(true);
    try {
      await onSubmit(projectId, {
        fuel_type: fuelType,
        usage_type: usageType,
        litres: parseFloat(litres),
        cost_per_litre: costPerLitre,
        equipment_ref: equipmentRef || (vehicleId ? vehicles.find(v => v.id === vehicleId)?.registration ?? "" : ""),
        fuelled_by: fuelledBy,
        site_id: siteId,
        fuel_date: fuelDate,
        odometer_reading: odometer ? parseFloat(odometer) : null,
        notes,
        ...(vehicleId ? { vehicle_id: vehicleId } : {}),
      } as Parameters<typeof onSubmit>[1]);
      setLitres(""); setCostPerLitre(""); setEquipmentRef(""); setFuelledBy(""); setNotes("");
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="Log Fuel Usage" onClose={onClose} size="md">
      <div className="p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Project *</label>
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Site</label>
            <select
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— No site —</option>
              {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Vehicle (optional)</label>
            <select
              value={vehicleId}
              onChange={(e) => setVehicleId(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— No vehicle —</option>
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>{v.registration} — {v.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Fuel Type *</label>
            <select
              value={fuelType}
              onChange={(e) => setFuelType(e.target.value as FuelType)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              {(Object.keys(FUEL_TYPE_LABELS) as FuelType[]).map((t) => (
                <option key={t} value={t}>{FUEL_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Usage Type *</label>
            <select
              value={usageType}
              onChange={(e) => setUsageType(e.target.value as FuelUsageType)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              {(Object.keys(FUEL_USAGE_LABELS) as FuelUsageType[]).map((t) => (
                <option key={t} value={t}>{FUEL_USAGE_LABELS[t]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Litres *</label>
            <input
              type="number"
              min="0.1"
              step="0.1"
              value={litres}
              onChange={(e) => setLitres(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="e.g. 50"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Cost per Litre (R)</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={costPerLitre}
              onChange={(e) => setCostPerLitre(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="e.g. 22.50"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Equipment Ref</label>
            <input
              type="text"
              value={equipmentRef}
              onChange={(e) => setEquipmentRef(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="e.g. TLB-001"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Fuelled By</label>
            <input
              type="text"
              value={fuelledBy}
              onChange={(e) => setFuelledBy(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="Person's name"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Date *</label>
            <input
              type="date"
              value={fuelDate}
              onChange={(e) => setFuelDate(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Odometer Reading (km) — optional</label>
          <input
            type="number"
            min="0"
            step="0.1"
            value={odometer}
            onChange={(e) => setOdometer(e.target.value)}
            placeholder="e.g. 45230"
            className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Notes</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
          />
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={handleSubmit} disabled={saving || !projectId || !litres}>
            {saving ? "Saving…" : "Log Fuel"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────────
export default function FuelPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [logs, setLogs] = useState<FuelLog[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loading, setLoading] = useState(false);
  const [showLog, setShowLog] = useState(false);

  useEffect(() => {
    projectsApi
      .list(1, 100)
      .then((res) => {
        setProjects(res.items);
        if (res.items.length > 0) setSelectedProjectId(res.items[0].id);
      })
      .catch(() => {})
      .finally(() => setLoadingProjects(false));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setLoading(true);
    fuelApi
      .list(selectedProjectId)
      .then(setLogs)
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  }, [selectedProjectId]);

  // total_cost: use DB value when available; fall back to litres × cost_per_litre
  // (the DB column is plain nullable — not a GENERATED ALWAYS column — so older
  //  rows may have total_cost=null until they are re-saved via the service fix).
  const lineTotal = (l: { total_cost: number | null; litres: number; cost_per_litre: number | null }) =>
    l.total_cost ?? (l.cost_per_litre != null ? l.litres * l.cost_per_litre : null);

  const totalLitres = logs.reduce((s, l) => s + l.litres, 0);
  const totalCost = logs.reduce((s, l) => s + (lineTotal(l) ?? 0), 0);
  const dieselLitres = logs.filter((l) => l.fuel_type === "DIESEL").reduce((s, l) => s + l.litres, 0);

  const handleLogFuel = async (projectId: string, data: {
    fuel_type: FuelType;
    usage_type: FuelUsageType;
    litres: number;
    cost_per_litre: string;
    equipment_ref: string;
    fuelled_by: string;
    site_id: string;
    fuel_date: string;
    odometer_reading?: number | null;
    notes: string;
  }) => {
    const created = await fuelApi.create(projectId, {
      fuel_type: data.fuel_type,
      usage_type: data.usage_type,
      litres: data.litres,
      cost_per_litre: data.cost_per_litre ? parseFloat(data.cost_per_litre) : null,
      equipment_ref: data.equipment_ref || null,
      fuelled_by: data.fuelled_by || null,
      site_id: data.site_id || null,
      fuel_date: data.fuel_date ? new Date(data.fuel_date).toISOString() : null,
      odometer_reading: data.odometer_reading ?? null,
      notes: data.notes || null,
    });
    if (projectId === selectedProjectId) {
      setLogs((prev) => [created, ...prev]);
    }
  };

  if (loadingProjects) {
    return (
      <div className="space-y-5 animate-fade-in">
        <Skeleton className="h-12 rounded-xl" />
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Fuel Tracking"
        description="Track fuel consumption and costs across projects and equipment."
        actions={
          selectedProjectId ? (
            <Button size="sm" onClick={() => setShowLog(true)}>
              <Plus className="w-4 h-4" />
              Log Fuel
            </Button>
          ) : undefined
        }
      />

      {/* Project selector */}
      <div>
        <label className="text-xs text-muted-foreground block mb-1">Project</label>
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[240px]"
        >
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Total Litres"
          value={`${totalLitres.toLocaleString("en-ZA", { maximumFractionDigits: 1 })} L`}
          icon={Droplet}
          color="bg-primary/10 text-primary"
        />
        <StatCard
          title="Total Fuel Cost"
          value={formatCurrency(totalCost)}
          icon={Flame}
          color="bg-warning/10 text-warning"
        />
        <StatCard
          title="Diesel (L)"
          value={`${dieselLitres.toLocaleString("en-ZA", { maximumFractionDigits: 1 })} L`}
          icon={Droplet}
          color="bg-success/10 text-success"
        />
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 rounded-xl" />)}
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {logs.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">
              No fuel logs for this project.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Type</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Usage</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Equipment</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Litres</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Cost/L</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Total</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Odometer</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Fuelled By</th>
                  <th className="px-4 py-3 w-8" />
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors group">
                    <td className="px-4 py-3 text-xs text-muted-foreground">{formatDate(log.fuel_date)}</td>
                    <td className="px-4 py-3 text-xs font-medium">{FUEL_TYPE_LABELS[log.fuel_type]}</td>
                    <td className="px-4 py-3 text-xs">{FUEL_USAGE_LABELS[log.usage_type]}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{log.equipment_ref ?? "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-medium">
                      {log.litres.toLocaleString("en-ZA", { maximumFractionDigits: 1 })}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-xs text-muted-foreground">
                      {log.cost_per_litre != null ? `R ${log.cost_per_litre.toFixed(4)}` : "—"}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums font-medium">
                      {lineTotal(log) != null ? formatCurrency(lineTotal(log)!) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-xs text-muted-foreground hidden lg:table-cell">
                      {(log as { odometer_reading?: number | null }).odometer_reading != null
                        ? `${(log as { odometer_reading?: number }).odometer_reading?.toLocaleString("en-ZA")} km`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{log.fuelled_by ?? "—"}</td>
                    <td className="px-2 py-3">
                      <button
                        onClick={async () => {
                          if (!window.confirm("Delete this fuel log entry?")) return;
                          try {
                            await fuelApi.delete(log.id);
                            setLogs(prev => prev.filter(l => l.id !== log.id));
                          } catch {
                            alert("Cannot delete fuel log.");
                          }
                        }}
                        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-opacity"
                        title="Delete fuel log"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border bg-muted/30">
                  <td colSpan={4} className="px-4 py-2 text-xs font-medium text-muted-foreground">Totals</td>
                  <td className="px-4 py-2 text-right tabular-nums font-semibold text-xs">
                    {totalLitres.toLocaleString("en-ZA", { maximumFractionDigits: 1 })} L
                  </td>
                  <td />
                  <td className="px-4 py-2 text-right tabular-nums font-semibold text-xs">
                    {formatCurrency(totalCost)}
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          )}
        </div>
      )}

      <LogFuelModal
        open={showLog}
        onClose={() => setShowLog(false)}
        projects={projects}
        onSubmit={handleLogFuel}
      />
    </div>
  );
}
