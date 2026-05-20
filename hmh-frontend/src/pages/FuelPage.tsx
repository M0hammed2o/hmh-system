import { useEffect, useRef, useState } from "react";
import { Plus, Droplet, Flame, Trash2, Camera, AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";
import { AttachmentStrip } from "@/components/shared/AttachmentStrip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import {
  fuelApi, fuelPhotoUrl,
  type FuelLog, type FuelType, type FuelUsageType,
  FUEL_TYPE_LABELS, FUEL_USAGE_LABELS,
} from "@/api/fuel";
import { vehiclesApi, type Vehicle } from "@/api/vehicles";
import { formatCurrency, formatDate } from "@/lib/format";

// ── Photo upload field ─────────────────────────────────────────────────────────

function PhotoField({ label, onChange }: { label: string; onChange: (f: File | null) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const [name, setName] = useState<string | null>(null);
  return (
    <div>
      <label className="text-xs text-muted-foreground block mb-1">{label}</label>
      <button type="button" onClick={() => ref.current?.click()}
              className={`w-full h-9 rounded-md border px-3 text-sm text-left flex items-center gap-2 transition-colors
                ${name ? "border-green-400 bg-green-50 dark:bg-green-900/20 text-green-700" : "border-input bg-background text-muted-foreground hover:border-primary/50"}`}>
        <Camera className="w-3.5 h-3.5 shrink-0" />
        <span className="truncate">{name ?? "Tap to take / choose photo"}</span>
      </button>
      <input ref={ref} type="file" accept="image/*" capture="environment" className="hidden"
             onChange={e => { const f = e.target.files?.[0] ?? null; setName(f?.name ?? null); onChange(f); }} />
    </div>
  );
}

// ── Log Fuel Modal ─────────────────────────────────────────────────────────────

function LogFuelModal({ open, onClose, projects, onDone }: {
  open: boolean; onClose: () => void; projects: Project[];
  onDone: (log: FuelLog) => void;
}) {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [sites,     setSites]     = useState<Site[]>([]);
  const [vehicles,  setVehicles]  = useState<Vehicle[]>([]);
  const [vehicleId, setVehicleId] = useState("");
  const [fuelType,  setFuelType]  = useState<FuelType>("DIESEL");
  const [usageType, setUsageType] = useState<FuelUsageType>("DELIVERY_VEHICLE");
  const [litres,         setLitres]         = useState("");
  const [costPerLitre,   setCostPerLitre]   = useState("");
  const [equipmentRef,   setEquipmentRef]   = useState("");
  const [fuelledBy,      setFuelledBy]      = useState("");
  const [siteId,         setSiteId]         = useState("");
  const [fuelDate,       setFuelDate]       = useState(() => new Date().toISOString().slice(0, 10));
  const [odometer,       setOdometer]       = useState("");
  const [notes,          setNotes]          = useState("");
  const [photoOdo,       setPhotoOdo]       = useState<File | null>(null);
  const [photoPump,      setPhotoPump]      = useState<File | null>(null);
  const [photoInv,       setPhotoInv]       = useState<File | null>(null);
  const [saving,         setSaving]         = useState(false);
  const [error,          setError]          = useState("");

  useEffect(() => {
    if (projects.length > 0 && !projectId) setProjectId(projects[0].id);
  }, [projects, projectId]);

  useEffect(() => {
    if (!projectId) return;
    sitesApi.list(projectId).then(s => { setSites(s); setSiteId(s[0]?.id ?? ""); }).catch(() => {});
    vehiclesApi.list().then(setVehicles).catch(() => {});
  }, [projectId]);

  const handleSubmit = async () => {
    if (!projectId || !litres) { setError("Project and litres are required."); return; }
    setSaving(true); setError("");
    try {
      const vehicle = vehicles.find(v => v.id === vehicleId);
      const created = await fuelApi.createWithEvidence(projectId, {
        fuel_type:        fuelType,
        usage_type:       usageType,
        litres:           parseFloat(litres),
        cost_per_litre:   costPerLitre ? parseFloat(costPerLitre) : null,
        equipment_ref:    equipmentRef || vehicle?.registration || null,
        fuelled_by:       fuelledBy || null,
        site_id:          siteId || null,
        vehicle_id:       vehicleId || null,
        fuel_date:        fuelDate ? new Date(fuelDate).toISOString() : null,
        odometer_reading: odometer ? parseFloat(odometer) : null,
        notes:            notes || null,
        photo_odometer:   photoOdo,
        photo_pump:       photoPump,
        photo_invoice:    photoInv,
      });
      onDone(created);
      onClose();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail || "Failed to save fuel log.");
    } finally { setSaving(false); }
  };

  return (
    <Modal open={open} title="Log Fuel Usage" onClose={onClose} size="md">
      <div className="p-5 space-y-4 overflow-y-auto max-h-[80vh]">
        {error && <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Project <span className="text-destructive">*</span></label>
            <select value={projectId} onChange={e => setProjectId(e.target.value)}
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm">
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Site</label>
            <select value={siteId} onChange={e => setSiteId(e.target.value)}
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm">
              <option value="">— No site —</option>
              {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Vehicle</label>
            <select value={vehicleId} onChange={e => setVehicleId(e.target.value)}
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm">
              <option value="">— No vehicle —</option>
              {vehicles.map(v => <option key={v.id} value={v.id}>{v.registration} — {v.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Fuel Type <span className="text-destructive">*</span></label>
            <select value={fuelType} onChange={e => setFuelType(e.target.value as FuelType)}
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm">
              {(Object.keys(FUEL_TYPE_LABELS) as FuelType[]).map(t => <option key={t} value={t}>{FUEL_TYPE_LABELS[t]}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Usage Type</label>
            <select value={usageType} onChange={e => setUsageType(e.target.value as FuelUsageType)}
                    className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm">
              {(Object.keys(FUEL_USAGE_LABELS) as FuelUsageType[]).map(t => <option key={t} value={t}>{FUEL_USAGE_LABELS[t]}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Litres <span className="text-destructive">*</span></label>
            <input type="number" min="0.1" step="0.1" value={litres} onChange={e => setLitres(e.target.value)}
                   placeholder="e.g. 50" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Cost per Litre (R)</label>
            <input type="number" min="0" step="0.01" value={costPerLitre} onChange={e => setCostPerLitre(e.target.value)}
                   placeholder="e.g. 22.50" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Odometer (km)</label>
            <input type="number" min="0" step="1" value={odometer} onChange={e => setOdometer(e.target.value)}
                   placeholder="e.g. 45230" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Equipment / Ref</label>
            <input type="text" value={equipmentRef} onChange={e => setEquipmentRef(e.target.value)}
                   placeholder="e.g. TLB-001" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Fuelled By</label>
            <input type="text" value={fuelledBy} onChange={e => setFuelledBy(e.target.value)}
                   placeholder="Name" className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground block mb-1">Date <span className="text-destructive">*</span></label>
            <input type="date" value={fuelDate} onChange={e => setFuelDate(e.target.value)}
                   className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
        </div>

        {/* Evidence photos */}
        <div className="border border-amber-200 bg-amber-50 dark:bg-amber-950/20 rounded-xl p-3 space-y-2.5">
          <p className="text-xs font-semibold text-amber-700 flex items-center gap-1.5">
            <Camera className="w-3.5 h-3.5" />Evidence Photos
          </p>
          <PhotoField label="📷 Odometer / Mileage Photo" onChange={setPhotoOdo} />
          <PhotoField label="⛽ Fuel Pump / Tank Photo"   onChange={setPhotoPump} />
          <PhotoField label="🧾 Invoice / Receipt Slip"   onChange={setPhotoInv} />
        </div>

        <div>
          <label className="text-xs text-muted-foreground block mb-1">Notes</label>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none" />
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

// ── Main Component ─────────────────────────────────────────────────────────────

export default function FuelPage() {
  const [projects,          setProjects]          = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [logs,              setLogs]              = useState<FuelLog[]>([]);
  const [loadingProjects,   setLoadingProjects]   = useState(true);
  const [loading,           setLoading]           = useState(false);
  const [showLog,           setShowLog]           = useState(false);
  const [expandedFuelId,    setExpandedFuelId]    = useState<string | null>(null);

  useEffect(() => {
    projectsApi.list(1, 100)
      .then(res => { setProjects(res.items); if (res.items.length > 0) setSelectedProjectId(res.items[0].id); })
      .catch(() => {})
      .finally(() => setLoadingProjects(false));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setLoading(true);
    fuelApi.list(selectedProjectId).then(setLogs).catch(() => setLogs([])).finally(() => setLoading(false));
  }, [selectedProjectId]);

  const lineTotal = (l: FuelLog) =>
    l.total_cost ?? (l.cost_per_litre != null ? l.litres * l.cost_per_litre : null);

  const totalLitres  = logs.reduce((s, l) => s + l.litres, 0);
  const totalCost    = logs.reduce((s, l) => s + (lineTotal(l) ?? 0), 0);
  const dieselLitres = logs.filter(l => l.fuel_type === "DIESEL").reduce((s, l) => s + l.litres, 0);
  const flaggedCount = logs.filter(l => l.notes?.includes("⚠")).length;

  if (loadingProjects) {
    return (
      <div className="space-y-5 animate-fade-in">
        <Skeleton className="h-12 rounded-xl" />
        <div className="grid grid-cols-3 gap-4">{[1,2,3].map(i => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Fuel Tracking"
        description="Track fuel consumption, costs and evidence across projects."
        actions={
          selectedProjectId ? (
            <Button size="sm" onClick={() => setShowLog(true)}><Plus className="w-4 h-4" />Log Fuel</Button>
          ) : undefined
        }
      />

      <div>
        <label className="text-xs text-muted-foreground block mb-1">Project</label>
        <select value={selectedProjectId} onChange={e => setSelectedProjectId(e.target.value)}
                className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[240px]">
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard title="Total Litres"    value={`${totalLitres.toLocaleString("en-ZA", {maximumFractionDigits:1})} L`} icon={Droplet}        color="bg-primary/10 text-primary" />
        <StatCard title="Total Cost"      value={formatCurrency(totalCost)}                                               icon={Flame}          color="bg-warning/10 text-warning" />
        <StatCard title="Diesel (L)"      value={`${dieselLitres.toLocaleString("en-ZA", {maximumFractionDigits:1})} L`} icon={Droplet}        color="bg-success/10 text-success" />
        <StatCard title="Flagged Entries" value={flaggedCount}                                                            icon={AlertTriangle}  color={flaggedCount > 0 ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground"} />
      </div>

      {loading ? (
        <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-12 rounded-xl" />)}</div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-x-auto">
          {logs.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">No fuel logs for this project.</div>
          ) : (
            <table className="w-full text-sm min-w-[900px]">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-3 py-3 font-medium text-muted-foreground whitespace-nowrap">Date</th>
                  <th className="text-left px-3 py-3 font-medium text-muted-foreground">Type / Usage</th>
                  <th className="text-left px-3 py-3 font-medium text-muted-foreground">Equipment</th>
                  <th className="text-right px-3 py-3 font-medium text-muted-foreground">Litres</th>
                  <th className="text-right px-3 py-3 font-medium text-muted-foreground">Cost/L</th>
                  <th className="text-right px-3 py-3 font-medium text-muted-foreground">Total</th>
                  <th className="text-right px-3 py-3 font-medium text-muted-foreground">Odometer</th>
                  <th className="text-right px-3 py-3 font-medium text-muted-foreground">Distance</th>
                  <th className="text-right px-3 py-3 font-medium text-muted-foreground">km/L</th>
                  <th className="text-right px-3 py-3 font-medium text-muted-foreground">L/100km</th>
                  <th className="text-left px-3 py-3 font-medium text-muted-foreground">Photos</th>
                  <th className="px-3 py-3 w-8 text-muted-foreground font-medium">+</th>
                  <th className="px-3 py-3 w-8" />
                </tr>
              </thead>
              <tbody>
                {logs.map(log => {
                  const flagged = log.notes?.includes("⚠") ?? false;
                  const total   = lineTotal(log);
                  const odoUrl  = fuelPhotoUrl(log.photo_odometer);
                  const pumpUrl = fuelPhotoUrl(log.photo_pump);
                  const invUrl  = fuelPhotoUrl(log.photo_invoice);
                  return (
                    <>
                    <tr key={log.id}
                        className={`border-b ${expandedFuelId === log.id ? "" : "border-border last:border-0"} transition-colors group
                          ${flagged ? "bg-destructive/5 hover:bg-destructive/10" : "hover:bg-muted/30"}`}>
                      <td className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap">{formatDate(log.fuel_date)}</td>
                      <td className="px-3 py-2.5 text-xs">
                        <span className="font-medium">{FUEL_TYPE_LABELS[log.fuel_type]}</span>
                        <span className="block text-muted-foreground text-[10px]">{FUEL_USAGE_LABELS[log.usage_type]}</span>
                      </td>
                      <td className="px-3 py-2.5 text-xs text-muted-foreground">
                        {log.equipment_ref ?? "—"}
                        {log.fuelled_by && <span className="block text-[10px]">{log.fuelled_by}</span>}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums font-medium text-xs">
                        {log.litres.toLocaleString("en-ZA", {maximumFractionDigits:1})}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-xs text-muted-foreground">
                        {log.cost_per_litre != null ? `R${log.cost_per_litre.toFixed(2)}` : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums font-medium text-xs">
                        {total != null ? formatCurrency(total) : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right text-xs text-muted-foreground">
                        {log.odometer_reading != null ? `${log.odometer_reading.toLocaleString("en-ZA")} km` : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right text-xs text-muted-foreground">
                        {log.distance_km != null ? `${log.distance_km.toLocaleString("en-ZA", {maximumFractionDigits:0})} km` : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right text-xs">
                        {log.efficiency_kpl != null ? (
                          <span className={log.efficiency_kpl < 4 ? "text-destructive font-medium" : "text-muted-foreground"}>
                            {log.efficiency_kpl.toFixed(1)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right text-xs">
                        {log.l_per_100km != null ? (
                          <span className={`inline-flex items-center gap-1 justify-end ${log.l_per_100km > 30 ? "text-destructive font-semibold" : "text-muted-foreground"}`}>
                            {flagged && <AlertTriangle className="w-3 h-3" />}
                            {log.l_per_100km.toFixed(1)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex flex-col gap-0.5">
                          {odoUrl  && <a href={odoUrl}  target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-[10px] text-primary hover:underline"><Camera className="w-3 h-3" />Odo</a>}
                          {pumpUrl && <a href={pumpUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-[10px] text-primary hover:underline"><Camera className="w-3 h-3" />Pump</a>}
                          {invUrl  && <a href={invUrl}  target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-[10px] text-primary hover:underline"><Camera className="w-3 h-3" />Slip</a>}
                          {!odoUrl && !pumpUrl && !invUrl && <span className="text-[10px] text-muted-foreground">—</span>}
                        </div>
                      </td>
                      <td className="px-2 py-2.5">
                        <button
                          onClick={() => setExpandedFuelId(prev => prev === log.id ? null : log.id)}
                          className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-primary transition-colors"
                          title="Extra photos"
                        >
                          {expandedFuelId === log.id
                            ? <ChevronUp className="w-3.5 h-3.5" />
                            : <ChevronDown className="w-3.5 h-3.5" />}
                        </button>
                      </td>
                      <td className="px-2 py-2.5">
                        <button
                          onClick={async () => {
                            if (!window.confirm("Delete this fuel log?")) return;
                            try { await fuelApi.delete(log.id); setLogs(p => p.filter(l => l.id !== log.id)); }
                            catch { alert("Cannot delete fuel log."); }
                          }}
                          className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-opacity"
                          title="Delete"
                        ><Trash2 className="w-3.5 h-3.5" /></button>
                      </td>
                    </tr>
                    {expandedFuelId === log.id && (
                      <tr key={`${log.id}-photos`} className="border-b border-border bg-muted/20">
                        <td colSpan={13} className="px-4 py-3">
                          <AttachmentStrip
                            entityType="FUEL_LOG"
                            entityId={log.id}
                            label="Additional Photos"
                            accept="image/*"
                            compact
                          />
                        </td>
                      </tr>
                    )}
                    </>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border bg-muted/30">
                  <td colSpan={3} className="px-3 py-2 text-xs font-medium text-muted-foreground" title="Totals">Totals</td>
                  <td className="px-3 py-2 text-right tabular-nums font-semibold text-xs">
                    {totalLitres.toLocaleString("en-ZA", {maximumFractionDigits:1})} L
                  </td>
                  <td />
                  <td className="px-3 py-2 text-right tabular-nums font-semibold text-xs">{formatCurrency(totalCost)}</td>
                  <td colSpan={6} />
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
        onDone={log => { if (log.project_id === selectedProjectId) setLogs(p => [log, ...p]); }}
      />
    </div>
  );
}
