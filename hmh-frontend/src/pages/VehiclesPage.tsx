import { useEffect, useState } from "react";
import { Plus, Car, Wrench, Fuel, Trash2, Droplet, AlertTriangle, Pencil } from "lucide-react";
import { fuelApi, fuelPhotoUrl, type FuelLog, FUEL_TYPE_LABELS } from "@/api/fuel";
import { formatCurrency } from "@/lib/format";
import { vehiclesApi, type Vehicle, type VehicleCost, type VehicleCreate, type VehicleCostCreate, type VehicleType, type VehicleCostType, type FuelType } from "@/api/vehicles";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi } from "@/api/sites";
import type { Site } from "@/api/sites";

const vehicleTypeLabels: Record<VehicleType, string> = {
  BAKKIE: "Bakkie", TRUCK: "Truck", TLB: "TLB", EXCAVATOR: "Excavator",
  CRANE: "Crane", VAN: "Van", OTHER: "Other",
};

const costTypeLabels: Record<VehicleCostType, string> = {
  FUEL: "Fuel", TYRE: "Tyre", REPAIR: "Repair", SERVICE: "Service",
  LICENCE: "Licence", INSURANCE: "Insurance", OTHER: "Other",
};

const fuelTypeLabels: Record<FuelType, string> = {
  DIESEL: "Diesel", PETROL: "Petrol", PARAFFIN: "Paraffin", OTHER: "Other",
};

const costTypeOptions: VehicleCostType[] = ["FUEL", "TYRE", "REPAIR", "SERVICE", "LICENCE", "INSURANCE", "OTHER"];
const vehicleTypeOptions: VehicleType[] = ["BAKKIE", "TRUCK", "TLB", "EXCAVATOR", "CRANE", "VAN", "OTHER"];
const fuelTypeOptions: FuelType[] = ["DIESEL", "PETROL", "PARAFFIN", "OTHER"];

function VehicleFormFields({
  form,
  onChange,
}: {
  form: VehicleCreate;
  onChange: (patch: Partial<VehicleCreate>) => void;
}) {
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label>Registration *</Label>
          <Input value={form.registration} onChange={(e) => onChange({ registration: e.target.value })} placeholder="e.g. CA 123-456" required />
        </div>
        <div className="space-y-2">
          <Label>Display Name *</Label>
          <Input value={form.name} onChange={(e) => onChange({ name: e.target.value })} placeholder="e.g. Site Hilux" required />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label>Type</Label>
          <select
            value={form.vehicle_type ?? "BAKKIE"}
            onChange={(e) => onChange({ vehicle_type: e.target.value as VehicleType })}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            {vehicleTypeOptions.map((t) => <option key={t} value={t}>{vehicleTypeLabels[t]}</option>)}
          </select>
        </div>
        <div className="space-y-2">
          <Label>Status</Label>
          <select
            value={form.status ?? "ACTIVE"}
            onChange={(e) => onChange({ status: e.target.value as VehicleCreate["status"] })}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="ACTIVE">Active</option>
            <option value="MAINTENANCE">Maintenance</option>
            <option value="RETIRED">Retired</option>
          </select>
        </div>
      </div>
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide pt-1">Identification</p>
      <div className="space-y-2">
        <Label>VIN Number</Label>
        <Input value={form.vin_number ?? ""} onChange={(e) => onChange({ vin_number: e.target.value || undefined })} placeholder="e.g. AHTFZ29G003012345" maxLength={20} />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-2">
          <Label>Make</Label>
          <Input value={form.make ?? ""} onChange={(e) => onChange({ make: e.target.value || undefined })} placeholder="Toyota" />
        </div>
        <div className="space-y-2">
          <Label>Model</Label>
          <Input value={form.model ?? ""} onChange={(e) => onChange({ model: e.target.value || undefined })} placeholder="Hilux" />
        </div>
        <div className="space-y-2">
          <Label>Year</Label>
          <Input type="number" min="1990" max="2099" value={form.year ?? ""} onChange={(e) => onChange({ year: e.target.value ? parseInt(e.target.value) : undefined })} placeholder="2022" />
        </div>
      </div>
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide pt-1">Fuel &amp; Consumption</p>
      <div className="grid grid-cols-3 gap-3">
        <div className="space-y-2">
          <Label>Fuel Type</Label>
          <select
            value={form.fuel_type ?? ""}
            onChange={(e) => onChange({ fuel_type: (e.target.value as FuelType) || undefined })}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">— None —</option>
            {fuelTypeOptions.map((f) => <option key={f} value={f}>{fuelTypeLabels[f]}</option>)}
          </select>
        </div>
        <div className="space-y-2">
          <Label>Tank (L)</Label>
          <Input type="number" min="0" step="0.5" value={form.tank_capacity_l ?? ""} onChange={(e) => onChange({ tank_capacity_l: e.target.value ? parseFloat(e.target.value) : undefined })} placeholder="80" />
        </div>
        <div className="space-y-2">
          <Label>L/100km</Label>
          <Input type="number" min="0" step="0.1" value={form.fuel_consumption_per_100km ?? ""} onChange={(e) => onChange({ fuel_consumption_per_100km: e.target.value ? parseFloat(e.target.value) : undefined })} placeholder="12.5" />
        </div>
      </div>
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide pt-1">Odometer &amp; Service</p>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label>Current Odometer (km)</Label>
          <Input type="number" min="0" step="1" value={form.current_odometer_km ?? ""} onChange={(e) => onChange({ current_odometer_km: e.target.value ? parseFloat(e.target.value) : undefined })} placeholder="45000" />
        </div>
        <div className="space-y-2">
          <Label>Service Interval (km)</Label>
          <Input type="number" min="0" step="500" value={form.service_interval_km ?? ""} onChange={(e) => onChange({ service_interval_km: e.target.value ? parseInt(e.target.value) : undefined })} placeholder="10000" />
        </div>
      </div>
    </>
  );
}

function AddVehicleModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState<VehicleCreate>({ registration: "", name: "", vehicle_type: "BAKKIE", status: "ACTIVE" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await vehiclesApi.create(form);
      onCreated();
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to add vehicle.";
      setError(msg);
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 bg-foreground/40 overflow-y-auto">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg p-6 animate-fade-in my-6">
        <h2 className="text-base font-semibold mb-5">Add Vehicle</h2>
        <form onSubmit={submit} className="space-y-3">
          <VehicleFormFields form={form} onChange={(patch) => setForm((prev) => ({ ...prev, ...patch }))} />
          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">{loading ? "Adding…" : "Add Vehicle"}</Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EditVehicleModal({ vehicle, onClose, onSaved }: { vehicle: Vehicle; onClose: () => void; onSaved: (v: Vehicle) => void }) {
  const [form, setForm] = useState<VehicleCreate>({
    registration: vehicle.registration,
    name: vehicle.name,
    vehicle_type: vehicle.vehicle_type,
    status: vehicle.status,
    vin_number: vehicle.vin_number ?? undefined,
    make: vehicle.make ?? undefined,
    model: vehicle.model ?? undefined,
    year: vehicle.year ?? undefined,
    fuel_type: vehicle.fuel_type ?? undefined,
    tank_capacity_l: vehicle.tank_capacity_l ?? undefined,
    fuel_consumption_per_100km: vehicle.fuel_consumption_per_100km ?? undefined,
    current_odometer_km: vehicle.current_odometer_km ?? undefined,
    service_interval_km: vehicle.service_interval_km ?? undefined,
    last_service_date: vehicle.last_service_date ?? undefined,
    next_service_date: vehicle.next_service_date ?? undefined,
    notes: vehicle.notes ?? undefined,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const updated = await vehiclesApi.update(vehicle.id, form);
      onSaved(updated);
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to update vehicle.";
      setError(msg);
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 bg-foreground/40 overflow-y-auto">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg p-6 animate-fade-in my-6">
        <h2 className="text-base font-semibold mb-1">Edit Vehicle</h2>
        <p className="text-sm text-muted-foreground mb-5">{vehicle.registration}</p>
        <form onSubmit={submit} className="space-y-3">
          <VehicleFormFields form={form} onChange={(patch) => setForm((prev) => ({ ...prev, ...patch }))} />
          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">{loading ? "Saving…" : "Save Changes"}</Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function LogCostModal({ vehicle, onClose, onLogged }: { vehicle: Vehicle; onClose: () => void; onLogged: () => void }) {
  const today = new Date().toISOString().split("T")[0];
  const [form, setForm] = useState<VehicleCostCreate>({ cost_type: "FUEL", amount: 0, cost_date: today });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [sites, setSites] = useState<Site[]>([]);

  useEffect(() => {
    projectsApi.list(1, 100).then(r => setProjects(r.items)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!form.project_id) { setSites([]); return; }
    sitesApi.list(form.project_id as string).then(setSites).catch(() => setSites([]));
  }, [form.project_id]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await vehiclesApi.logCost(vehicle.id, form);
      onLogged();
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to log cost.";
      setError(msg);
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-1">Log Cost</h2>
        <p className="text-sm text-muted-foreground mb-5">{vehicle.name} ({vehicle.registration})</p>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label>Cost Type</Label>
            <select
              value={form.cost_type}
              onChange={(e) => setForm({ ...form, cost_type: e.target.value as VehicleCostType })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {costTypeOptions.map((t) => <option key={t} value={t}>{costTypeLabels[t]}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Project (optional)</Label>
              <select
                value={(form.project_id as string) ?? ""}
                onChange={(e) => setForm({ ...form, project_id: e.target.value as unknown as typeof form.project_id || undefined, site_id: undefined })}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="">— None —</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Site (optional)</Label>
              <select
                value={(form.site_id as string) ?? ""}
                onChange={(e) => setForm({ ...form, site_id: e.target.value as unknown as typeof form.site_id || undefined })}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                disabled={sites.length === 0}
              >
                <option value="">— None —</option>
                {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          </div>
          <div className="space-y-2">
            <Label>Amount (R)</Label>
            <Input type="number" min="0" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: parseFloat(e.target.value) || 0 })} required />
          </div>
          <div className="space-y-2">
            <Label>Description</Label>
            <Input value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Brief description" />
          </div>
          <div className="space-y-2">
            <Label>Date</Label>
            <Input type="date" value={form.cost_date} onChange={(e) => setForm({ ...form, cost_date: e.target.value })} required />
          </div>
          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">{loading ? "Logging…" : "Log Cost"}</Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function VehiclesPage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [costs, setCosts] = useState<Record<string, VehicleCost[]>>({});
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [logCostFor, setLogCostFor] = useState<Vehicle | null>(null);
  const [editVehicle, setEditVehicle] = useState<Vehicle | null>(null);
  const [expanded,      setExpanded]      = useState<string | null>(null);
  const [error,         setError]         = useState("");
  const [fuelLogs,      setFuelLogs]      = useState<Record<string, FuelLog[]>>({});
  const [activeTab,     setActiveTab]     = useState<Record<string, "costs" | "fuel" | "details">>({});

  const loadVehicles = () => {
    setLoading(true);
    vehiclesApi.list()
      .then(setVehicles)
      .catch(() => setError("Failed to load vehicles."))
      .finally(() => setLoading(false));
  };

  const loadCosts = async (vehicleId: string) => {
    const data = await vehiclesApi.listCosts(vehicleId);
    setCosts((prev) => ({ ...prev, [vehicleId]: data }));
  };

  const loadFuelLogs = async (vehicleId: string) => {
    // Find a project from the vehicle's assigned_project_id or load all
    const vehicle = vehicles.find(v => v.id === vehicleId);
    const projId  = vehicle?.assigned_project_id;
    if (!projId) {
      // Try to get logs across all projects by fetching project list first
      try {
        const { projectsApi: api } = await import("@/api/projects");
        const projects = await api.list(1, 100).then(r => r.items);
        const allLogs: FuelLog[] = [];
        await Promise.all(
          projects.map(p =>
            fuelApi.listByVehicle(p.id, vehicleId)
              .then(logs => allLogs.push(...logs))
              .catch(() => {})
          )
        );
        allLogs.sort((a, b) => new Date(b.fuel_date).getTime() - new Date(a.fuel_date).getTime());
        setFuelLogs(prev => ({ ...prev, [vehicleId]: allLogs }));
      } catch { setFuelLogs(prev => ({ ...prev, [vehicleId]: [] })); }
      return;
    }
    const logs = await fuelApi.listByVehicle(projId, vehicleId).catch(() => []);
    setFuelLogs(prev => ({ ...prev, [vehicleId]: logs }));
  };

  const toggleExpand = (id: string) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    loadCosts(id);
    loadFuelLogs(id);
    if (!activeTab[id]) setActiveTab(prev => ({ ...prev, [id]: "details" }));
  };

  useEffect(() => { loadVehicles(); }, []);

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Vehicles</h1>
          {!loading && <p className="text-sm text-muted-foreground">{vehicles.length} vehicles</p>}
        </div>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="w-4 h-4" />
          Add Vehicle
        </Button>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">{error}</div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
        </div>
      ) : vehicles.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center">
          <Car className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No vehicles registered yet.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {vehicles.map((v) => (
            <div key={v.id} className="bg-card border border-border rounded-xl overflow-hidden">
              <div
                className="flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
                onClick={() => toggleExpand(v.id)}
              >
                <div className={cn(
                  "flex items-center justify-center w-10 h-10 rounded-xl shrink-0",
                  v.status === "MAINTENANCE" ? "bg-amber-500/10" : "bg-blue-500/10"
                )}>
                  <Car className={cn("w-5 h-5", v.status === "MAINTENANCE" ? "text-amber-500" : "text-blue-500")} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-semibold">{v.name}</p>
                    {v.status === "MAINTENANCE" && <Badge variant="secondary" className="text-xs">Maintenance</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground">{v.registration} · {vehicleTypeLabels[v.vehicle_type]}</p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={(e) => { e.stopPropagation(); setEditVehicle(v); }}
                  className="shrink-0"
                  title="Edit vehicle"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={(e) => { e.stopPropagation(); setLogCostFor(v); }}
                  className="shrink-0"
                >
                  <Wrench className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline ml-1">Log Cost</span>
                </Button>
                <button
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (!window.confirm(`Delete vehicle "${v.registration}"?\n\nBlocked if it has cost records. Set to RETIRED status instead for vehicles in active use.`)) return;
                    try {
                      await vehiclesApi.delete(v.id);
                      setVehicles(prev => prev.filter(x => x.id !== v.id));
                    } catch (err: unknown) {
                      alert((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Cannot delete vehicle.");
                    }
                  }}
                  className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive shrink-0"
                  title="Delete vehicle"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>

              {expanded === v.id && (
                <div className="border-t border-border bg-muted/20">
                  {/* Tab switcher */}
                  <div className="flex border-b border-border/50">
                    {(["details", "costs", "fuel"] as const).map(tab => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(prev => ({ ...prev, [v.id]: tab }))}
                        className={`px-4 py-2 text-xs font-medium transition-colors flex items-center gap-1.5
                          ${(activeTab[v.id] ?? "details") === tab
                            ? "border-b-2 border-primary text-primary"
                            : "text-muted-foreground hover:text-foreground"}`}
                      >
                        {tab === "details" ? <Car className="w-3 h-3" /> : tab === "costs" ? <Wrench className="w-3 h-3" /> : <Droplet className="w-3 h-3" />}
                        {tab === "details" ? "Details" : tab === "costs" ? `Costs (${costs[v.id]?.length ?? 0})` : `Fuel (${fuelLogs[v.id]?.length ?? 0})`}
                      </button>
                    ))}
                  </div>

                  {/* Details tab */}
                  {(activeTab[v.id] ?? "details") === "details" && (
                    <div className="px-4 py-3">
                      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                        {(v.make || v.model || v.year) && (
                          <div className="col-span-2 pb-1 border-b border-border/40 mb-1">
                            <span className="text-muted-foreground">Vehicle: </span>
                            <span className="font-medium">{[v.year, v.make, v.model].filter(Boolean).join(" ")}</span>
                          </div>
                        )}
                        {v.vin_number && (
                          <div className="col-span-2"><span className="text-muted-foreground">VIN: </span><span className="font-medium font-mono">{v.vin_number}</span></div>
                        )}
                        {v.fuel_type && (
                          <div><span className="text-muted-foreground">Fuel type: </span><span className="font-medium">{fuelTypeLabels[v.fuel_type]}</span></div>
                        )}
                        {v.tank_capacity_l != null && (
                          <div><span className="text-muted-foreground">Tank: </span><span className="font-medium">{v.tank_capacity_l} L</span></div>
                        )}
                        {v.fuel_consumption_per_100km != null && (
                          <div>
                            <span className="text-muted-foreground">Consumption: </span>
                            <span className="font-medium">{v.fuel_consumption_per_100km} L/100km</span>
                            {v.tank_capacity_l && (
                              <span className="text-muted-foreground"> (~{Math.round(v.tank_capacity_l * 100 / v.fuel_consumption_per_100km)} km range)</span>
                            )}
                          </div>
                        )}
                        {v.current_odometer_km != null && (
                          <div><span className="text-muted-foreground">Odometer: </span><span className="font-medium">{v.current_odometer_km.toLocaleString()} km</span></div>
                        )}
                        {v.service_interval_km != null && (
                          <div><span className="text-muted-foreground">Service every: </span><span className="font-medium">{v.service_interval_km.toLocaleString()} km</span></div>
                        )}
                        {v.last_service_date && (
                          <div><span className="text-muted-foreground">Last service: </span><span className="font-medium">{formatDate(v.last_service_date)}</span></div>
                        )}
                        {v.next_service_date && (
                          <div><span className="text-muted-foreground">Next service: </span><span className="font-medium">{formatDate(v.next_service_date)}</span></div>
                        )}
                        {!v.vin_number && !v.make && !v.model && !v.year && !v.fuel_type && !v.tank_capacity_l && !v.current_odometer_km && (
                          <p className="col-span-2 text-muted-foreground">No additional details recorded. Click the edit button to add vehicle specs.</p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Costs tab */}
                  {(activeTab[v.id] ?? "details") === "costs" && costs[v.id] && (
                    <div className="px-4 py-3 space-y-2">
                      {costs[v.id].length > 0 && (
                        <div className="flex gap-4 text-xs text-muted-foreground pb-1 border-b border-border/50">
                          <span>Total: <strong className="text-foreground">R{costs[v.id].reduce((s, c) => s + c.amount, 0).toLocaleString()}</strong></span>
                          <span>{costs[v.id].length} entries</span>
                        </div>
                      )}
                      {costs[v.id].length === 0 ? (
                        <p className="text-xs text-muted-foreground">No costs logged yet.</p>
                      ) : (
                        costs[v.id].slice(0, 10).map(cost => (
                          <div key={cost.id} className="flex items-center justify-between text-sm">
                            <div className="flex items-center gap-2">
                              {cost.cost_type === "FUEL" ? <Fuel className="w-3.5 h-3.5 text-muted-foreground" /> : <Wrench className="w-3.5 h-3.5 text-muted-foreground" />}
                              <span className="text-muted-foreground text-xs">{costTypeLabels[cost.cost_type]}</span>
                              {cost.description && <span className="text-xs text-muted-foreground">— {cost.description}</span>}
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="font-medium text-xs">R{cost.amount.toLocaleString()}</span>
                              <span className="text-xs text-muted-foreground">{cost.cost_date}</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {/* Fuel logs tab */}
                  {(activeTab[v.id] ?? "details") === "fuel" && (
                    <div className="px-4 py-3 space-y-2">
                      {!fuelLogs[v.id] ? (
                        <p className="text-xs text-muted-foreground">Loading fuel logs…</p>
                      ) : fuelLogs[v.id].length === 0 ? (
                        <p className="text-xs text-muted-foreground">No fuel logs for this vehicle.</p>
                      ) : (
                        <>
                          <div className="flex gap-4 text-xs text-muted-foreground pb-1 border-b border-border/50">
                            <span>Total: <strong className="text-foreground">{fuelLogs[v.id].reduce((s, l) => s + l.litres, 0).toFixed(1)} L</strong></span>
                            <span>Cost: <strong className="text-foreground">{formatCurrency(fuelLogs[v.id].reduce((s, l) => s + (l.total_cost ?? (l.cost_per_litre ? l.litres * l.cost_per_litre : 0)), 0))}</strong></span>
                            <span>{fuelLogs[v.id].length} entries</span>
                          </div>
                          {fuelLogs[v.id].slice(0, 10).map(log => {
                            const flagged = log.notes?.includes("⚠") ?? false;
                            const odoUrl  = fuelPhotoUrl(log.photo_odometer);
                            return (
                              <div key={log.id} className={`flex items-start justify-between text-xs rounded-lg px-2 py-1.5 ${flagged ? "bg-destructive/5" : ""}`}>
                                <div className="space-y-0.5">
                                  <div className="flex items-center gap-2">
                                    <Droplet className="w-3 h-3 text-muted-foreground" />
                                    <span className="font-medium">{log.litres.toFixed(1)} L {FUEL_TYPE_LABELS[log.fuel_type]}</span>
                                    {flagged && <AlertTriangle className="w-3 h-3 text-destructive" title="Unusual consumption" />}
                                  </div>
                                  <div className="text-muted-foreground pl-5 flex flex-wrap gap-2">
                                    {log.odometer_reading != null && <span>📍 {log.odometer_reading.toLocaleString()} km</span>}
                                    {log.distance_km      != null && <span>↔ {log.distance_km.toFixed(0)} km</span>}
                                    {log.efficiency_kpl   != null && <span>⛽ {log.efficiency_kpl.toFixed(1)} km/L</span>}
                                    {log.l_per_100km      != null && <span className={log.l_per_100km > 30 ? "text-destructive font-medium" : ""}>{log.l_per_100km.toFixed(1)} L/100km</span>}
                                    {odoUrl && <a href={odoUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">📷 Odo photo</a>}
                                  </div>
                                </div>
                                <div className="text-right shrink-0 ml-3">
                                  <p className="font-medium">{log.total_cost != null ? formatCurrency(log.total_cost) : "—"}</p>
                                  <p className="text-muted-foreground">{new Date(log.fuel_date).toLocaleDateString("en-ZA")}</p>
                                </div>
                              </div>
                            );
                          })}
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showAdd && (
        <AddVehicleModal
          onClose={() => setShowAdd(false)}
          onCreated={loadVehicles}
        />
      )}

      {editVehicle && (
        <EditVehicleModal
          vehicle={editVehicle}
          onClose={() => setEditVehicle(null)}
          onSaved={(updated) => {
            setVehicles(prev => prev.map(v => v.id === updated.id ? updated : v));
            setEditVehicle(null);
          }}
        />
      )}

      {logCostFor && (
        <LogCostModal
          vehicle={logCostFor}
          onClose={() => setLogCostFor(null)}
          onLogged={() => {
            loadCosts(logCostFor.id);
            if (expanded !== logCostFor.id) setExpanded(logCostFor.id);
          }}
        />
      )}
    </div>
  );
}
