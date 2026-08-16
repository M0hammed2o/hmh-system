import { useEffect, useState } from "react";
import { Plus, Car, Wrench, Fuel, Trash2, Droplet, AlertTriangle, Pencil, ClipboardList, MapPin, History } from "lucide-react";
import { fuelApi, fuelPhotoUrl, type FuelLog } from "@/api/fuel";
import { fuelManagementApi, type FuelIssue } from "@/api/fuelManagement";
import { formatCurrency } from "@/lib/format";
import {
  vehiclesApi,
  type Vehicle,
  type VehicleCost,
  type VehicleCreate,
  type VehicleCostCreate,
  type VehicleType,
  type VehicleCostType,
  type FuelType,
  type RepairJob,
  type RepairJobCreate,
} from "@/api/vehicles";
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
import { workshopApi, type WorkshopIssuance } from "@/api/workshop";

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

// ── Fuel history: merge canonical FuelIssue (Fuel Management) with legacy
// FuelLog into one timeline, clearly labelled by source. A road vehicle
// shows L/100km; an hour-based vehicle (uses_hours) shows L/hour — never both.
interface FuelTimelineEntry {
  key: string;
  source: "issue" | "legacy";
  date: string;
  litres: number;
  odometer: number | null;
  hours: number | null;
  consumption: string | null;
  anomaly: boolean;
  anomalyReason: string | null;
  cost: number | null;
  photoUrl: string | null;
  evidenceCount: number;
  reversed: boolean;
}

function buildFuelTimeline(vehicle: Vehicle, logs: FuelLog[], issues: FuelIssue[]): FuelTimelineEntry[] {
  const fromIssues: FuelTimelineEntry[] = issues.map(i => ({
    key: `issue-${i.id}`, source: "issue", date: i.issued_at, litres: i.litres,
    odometer: i.odometer_reading, hours: i.hour_meter_reading,
    consumption: vehicle.uses_hours
      ? (i.litres_per_hour != null ? `${i.litres_per_hour.toFixed(2)} L/hr` : null)
      : (i.litres_per_100km != null ? `${i.litres_per_100km.toFixed(1)} L/100km` : null),
    anomaly: i.anomaly_flag, anomalyReason: i.anomaly_reason, cost: i.total_cost,
    photoUrl: null, evidenceCount: i.evidence?.length ?? 0, reversed: i.is_reversed,
  }));
  const fromLogs: FuelTimelineEntry[] = logs.map(l => ({
    key: `log-${l.id}`, source: "legacy", date: l.fuel_date, litres: l.litres,
    odometer: l.odometer_reading, hours: l.hours_reading,
    consumption: vehicle.uses_hours
      ? (l.fuel_per_hour != null ? `${l.fuel_per_hour.toFixed(2)} L/hr` : null)
      : (l.l_per_100km != null ? `${l.l_per_100km.toFixed(1)} L/100km` : null),
    anomaly: false, anomalyReason: null, cost: l.total_cost,
    photoUrl: fuelPhotoUrl(l.photo_odometer), evidenceCount: 0, reversed: false,
  }));
  return [...fromIssues, ...fromLogs].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
}

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
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2"><Label>L/hour (machines)</Label><Input type="number" min="0" step="0.1" value={form.fuel_consumption_per_hour ?? ""} onChange={(e) => onChange({ fuel_consumption_per_hour: e.target.value ? Number(e.target.value) : undefined })} /></div>
        <div className="space-y-2"><Label>Allowed variance (%)</Label><Input type="number" min="0" step="1" value={form.fuel_tolerance_pct ?? 20} onChange={(e) => onChange({ fuel_tolerance_pct: Number(e.target.value) })} /></div>
        <div className="space-y-2"><Label>Minimum refill interval (hours)</Label><Input type="number" min="0" step="0.5" value={form.fuel_minimum_issue_interval_hours ?? 0} onChange={(e) => onChange({ fuel_minimum_issue_interval_hours: Number(e.target.value) })} /></div>
        <div className="space-y-2"><Label>Tracker provider</Label><Input value={form.tracker_provider ?? ""} onChange={(e) => onChange({ tracker_provider: e.target.value || undefined })} /></div>
        <div className="space-y-2"><Label>Tracker external ID</Label><Input value={form.tracker_external_id ?? ""} onChange={(e) => onChange({ tracker_external_id: e.target.value || undefined })} /></div>
        <div className="flex flex-col justify-end gap-2 pb-2">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.hour_meter_required ?? false} onChange={(e) => onChange({ hour_meter_required: e.target.checked })} /> Hour meter required</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.fuel_override_required ?? false} onChange={(e) => onChange({ fuel_override_required: e.target.checked })} /> Manager override outside limits</label>
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
    fuel_consumption_per_hour: vehicle.fuel_consumption_per_hour ?? undefined,
    fuel_tolerance_pct: vehicle.fuel_tolerance_pct,
    fuel_minimum_issue_interval_hours: vehicle.fuel_minimum_issue_interval_hours,
    fuel_override_required: vehicle.fuel_override_required,
    hour_meter_required: vehicle.hour_meter_required,
    tracker_provider: vehicle.tracker_provider ?? undefined,
    tracker_external_id: vehicle.tracker_external_id ?? undefined,
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

function NewRepairJobModal({
  vehicle,
  onClose,
  onCreated,
}: {
  vehicle: Vehicle;
  onClose: () => void;
  onCreated: (job: RepairJob) => void;
}) {
  const today = new Date().toISOString().split("T")[0];
  const [form, setForm] = useState<RepairJobCreate>({ title: "", date_opened: today });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) { setError("Title is required."); return; }
    setLoading(true);
    setError("");
    try {
      const job = await vehiclesApi.createRepair(vehicle.id, form);
      onCreated(job);
      onClose();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to create repair job.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-1">New Repair Job</h2>
        <p className="text-sm text-muted-foreground mb-5">{vehicle.name} ({vehicle.registration})</p>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-2">
            <Label>Title *</Label>
            <Input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="e.g. Engine oil leak repair"
              required
            />
          </div>
          <div className="space-y-2">
            <Label>Workshop / Supplier</Label>
            <Input
              value={form.workshop_name || ""}
              onChange={(e) => setForm({ ...form, workshop_name: e.target.value || undefined })}
              placeholder="e.g. ABC Auto Repairs"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label>Date Opened</Label>
              <Input
                type="date"
                value={form.date_opened}
                onChange={(e) => setForm({ ...form, date_opened: e.target.value })}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Odometer (km)</Label>
              <Input
                type="number"
                min="0"
                value={form.odometer_at_repair ?? ""}
                onChange={(e) => setForm({ ...form, odometer_at_repair: e.target.value ? parseFloat(e.target.value) : undefined })}
                placeholder="45000"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Description</Label>
            <Input
              value={form.description || ""}
              onChange={(e) => setForm({ ...form, description: e.target.value || undefined })}
              placeholder="Brief description of the issue"
            />
          </div>
          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">{loading ? "Creating…" : "Create Job"}</Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function LogRepairCostModal({
  job,
  onClose,
  onLogged,
}: {
  job: RepairJob;
  onClose: () => void;
  onLogged: () => void;
}) {
  const today = new Date().toISOString().split("T")[0];
  const [form, setForm] = useState<VehicleCostCreate>({ cost_type: "REPAIR", amount: 0, cost_date: today });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await vehiclesApi.logRepairCost(job.id, form);
      onLogged();
      onClose();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to log cost.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-1">Log Repair Cost</h2>
        <p className="text-sm text-muted-foreground mb-5">{job.title}</p>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-2">
            <Label>Cost Type</Label>
            <select
              value={form.cost_type}
              onChange={(e) => setForm({ ...form, cost_type: e.target.value as VehicleCostType })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="REPAIR">Repair (Labour)</option>
              <option value="SERVICE">Service</option>
              <option value="TYRE">Tyre</option>
              <option value="OTHER">Other</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label>Amount (R)</Label>
            <Input
              type="number"
              min="0"
              step="0.01"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: parseFloat(e.target.value) || 0 })}
              required
            />
          </div>
          <div className="space-y-2">
            <Label>Description</Label>
            <Input
              value={form.description || ""}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="e.g. Labour charge, parts, etc."
            />
          </div>
          <div className="space-y-2">
            <Label>Date</Label>
            <Input
              type="date"
              value={form.cost_date}
              onChange={(e) => setForm({ ...form, cost_date: e.target.value })}
              required
            />
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

function AssignVehicleModal({ vehicle, onClose, onSaved }: { vehicle: Vehicle; onClose: () => void; onSaved: (v: Vehicle) => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(vehicle.assigned_project_id ?? "");
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setProjectsLoading(true);
    projectsApi.list(1, 100)
      .then(r => setProjects(r.items))
      .catch(() => setError("Could not load projects. Please close and try again."))
      .finally(() => setProjectsLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      let warehouseSiteId: string | null = null;
      if (projectId) {
        const sites = await sitesApi.list(projectId).catch(() => [] as Site[]);
        const warehouse = sites.find(s => s.site_type === "warehouse");
        warehouseSiteId = warehouse?.id ?? null;
      }
      const updated = await vehiclesApi.update(vehicle.id, {
        assigned_project_id: projectId || null,
        assigned_site_id: warehouseSiteId,
      });
      onSaved(updated);
      onClose();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to save.");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-1">Assign to Project</h2>
        <p className="text-sm text-muted-foreground mb-5">{vehicle.name} ({vehicle.registration})</p>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Project {projectsLoading && <span className="text-muted-foreground text-xs">(loading…)</span>}</Label>
            <select
              value={projectId}
              onChange={e => setProjectId(e.target.value)}
              disabled={projectsLoading}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50"
            >
              <option value="">— Unassigned —</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <p className="text-xs text-muted-foreground">Vehicle will be placed in the project warehouse. Site staff can request transfers from there.</p>
          {error && <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button onClick={save} disabled={saving || projectsLoading} className="flex-1">
              {saving ? "Saving…" : "Save Assignment"}
            </Button>
            <Button variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function VehiclesPage() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [costs, setCosts] = useState<Record<string, VehicleCost[]>>({});
  const [repairs, setRepairs] = useState<Record<string, RepairJob[]>>({});
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [logCostFor, setLogCostFor] = useState<Vehicle | null>(null);
  const [editVehicle, setEditVehicle] = useState<Vehicle | null>(null);
  const [assignFor, setAssignFor] = useState<Vehicle | null>(null);
  const [newRepairFor, setNewRepairFor] = useState<Vehicle | null>(null);
  const [logRepairCostFor, setLogRepairCostFor] = useState<{ vehicle: Vehicle; job: RepairJob } | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [fuelLogs, setFuelLogs] = useState<Record<string, FuelLog[]>>({});
  const [fuelIssues, setFuelIssues] = useState<Record<string, FuelIssue[]>>({});
  const [partsHistory, setPartsHistory] = useState<Record<string, WorkshopIssuance[]>>({});
  const [activeTab, setActiveTab] = useState<Record<string, "costs" | "fuel" | "details" | "repairs" | "parts">>({});
  const [projectNames, setProjectNames] = useState<Record<string, string>>({});

  const loadVehicles = () => {
    setLoading(true);
    Promise.all([
      vehiclesApi.list(),
      projectsApi.list(1, 100).then(r => r.items).catch(() => [] as Project[]),
    ]).then(([vs, projects]) => {
      setVehicles(vs);
      const map: Record<string, string> = {};
      projects.forEach(p => { map[p.id] = p.name; });
      setProjectNames(map);
    }).catch(() => setError("Failed to load vehicles."))
      .finally(() => setLoading(false));
  };

  const loadCosts = async (vehicleId: string) => {
    const data = await vehiclesApi.listCosts(vehicleId);
    setCosts((prev) => ({ ...prev, [vehicleId]: data }));
  };

  const loadRepairs = async (vehicleId: string) => {
    const data = await vehiclesApi.listRepairs(vehicleId);
    setRepairs((prev) => ({ ...prev, [vehicleId]: data }));
  };

  const loadFuelLogs = async (vehicleId: string) => {
    const vehicle = vehicles.find(v => v.id === vehicleId);
    const projId  = vehicle?.assigned_project_id;
    if (!projId) {
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

  // Canonical fills (Fuel Management) — the FuelLog above is legacy/frozen
  // once a project cuts over; both are shown together, clearly labelled,
  // so fill history never appears to silently stop.
  const loadFuelIssues = async (vehicleId: string) => {
    const vehicle = vehicles.find(v => v.id === vehicleId);
    const projId  = vehicle?.assigned_project_id;
    if (!projId) {
      try {
        const projects = await projectsApi.list(1, 100).then(r => r.items);
        const allIssues: FuelIssue[] = [];
        await Promise.all(
          projects.map(p =>
            fuelManagementApi.issues(p.id, { vehicle_id: vehicleId })
              .then(issues => allIssues.push(...issues))
              .catch(() => {})
          )
        );
        allIssues.sort((a, b) => new Date(b.issued_at).getTime() - new Date(a.issued_at).getTime());
        setFuelIssues(prev => ({ ...prev, [vehicleId]: allIssues }));
      } catch { setFuelIssues(prev => ({ ...prev, [vehicleId]: [] })); }
      return;
    }
    const issues = await fuelManagementApi.issues(projId, { vehicle_id: vehicleId }).catch(() => []);
    setFuelIssues(prev => ({ ...prev, [vehicleId]: issues }));
  };

  const loadPartsHistory = async (vehicleId: string) => {
    const data = await workshopApi.listIssuances({ vehicle_id: vehicleId }).catch(() => []);
    setPartsHistory(prev => ({ ...prev, [vehicleId]: data.sort((a, b) => new Date(b.issued_at).getTime() - new Date(a.issued_at).getTime()) }));
  };

  const toggleExpand = (id: string) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    loadCosts(id);
    loadFuelLogs(id);
    loadFuelIssues(id);
    loadRepairs(id);
    loadPartsHistory(id);
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
                  <p className="text-xs text-muted-foreground">
                    {v.registration} · {vehicleTypeLabels[v.vehicle_type]}
                    {v.assigned_site_id
                      ? <span className="ml-1 text-blue-600"> · {projectNames[v.assigned_project_id ?? ""] ?? "Project"} Warehouse</span>
                      : v.assigned_project_id
                      ? <span className="ml-1 text-amber-500"> · {projectNames[v.assigned_project_id] ?? "Project"} (no warehouse)</span>
                      : <span className="ml-1 text-muted-foreground/60"> · Unassigned</span>}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={(e) => { e.stopPropagation(); setAssignFor(v); }}
                  className="shrink-0 text-xs gap-1"
                  title="Assign to project / site"
                >
                  <MapPin className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">{v.assigned_site_id ? "Reassign" : v.assigned_project_id ? "Move" : "Assign"}</span>
                </Button>
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
                  <div className="flex border-b border-border/50 overflow-x-auto">
                    {(["details", "costs", "fuel", "repairs", "parts"] as const).map(tab => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(prev => ({ ...prev, [v.id]: tab }))}
                        className={`px-4 py-2 text-xs font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap
                          ${(activeTab[v.id] ?? "details") === tab
                            ? "border-b-2 border-primary text-primary"
                            : "text-muted-foreground hover:text-foreground"}`}
                      >
                        {tab === "details"  ? <Car className="w-3 h-3" />
                         : tab === "costs"  ? <Wrench className="w-3 h-3" />
                         : tab === "fuel"   ? <Droplet className="w-3 h-3" />
                         : tab === "repairs" ? <ClipboardList className="w-3 h-3" />
                         : <History className="w-3 h-3" />}
                        {tab === "details"  ? "Details"
                         : tab === "costs"  ? `Costs (${costs[v.id]?.length ?? 0})`
                         : tab === "fuel"   ? `Fuel (${(fuelLogs[v.id]?.length ?? 0) + (fuelIssues[v.id]?.length ?? 0)})`
                         : tab === "repairs" ? `Repairs (${repairs[v.id]?.length ?? 0})`
                         : `Parts (${partsHistory[v.id]?.length ?? 0})`}
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
                        <div className="col-span-2 border-t border-border/40 pt-2 mt-1">
                          <div className="flex items-center justify-between">
                            <div>
                              <span className="text-muted-foreground">Assignment: </span>
                              <span className="font-medium">
                                {v.assigned_site_id
                                  ? `${projectNames[v.assigned_project_id ?? ""] ?? "Project"} Warehouse`
                                  : v.assigned_project_id
                                  ? `${projectNames[v.assigned_project_id] ?? "Project"} (no warehouse found)`
                                  : "Unassigned (fleet pool)"}
                              </span>
                            </div>
                            <button
                              onClick={() => setAssignFor(v)}
                              className="text-xs text-primary hover:underline flex items-center gap-1"
                            >
                              <MapPin className="w-3 h-3" /> Change
                            </button>
                          </div>
                        </div>
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
                      {!fuelLogs[v.id] || !fuelIssues[v.id] ? (
                        <p className="text-xs text-muted-foreground">Loading fuel history…</p>
                      ) : (() => {
                        const timeline = buildFuelTimeline(v, fuelLogs[v.id], fuelIssues[v.id]);
                        if (timeline.length === 0) {
                          return <p className="text-xs text-muted-foreground">No fuel fills recorded for this vehicle.</p>;
                        }
                        const totalLitres = timeline.reduce((s, e) => s + e.litres, 0);
                        const totalCost = timeline.reduce((s, e) => s + (e.cost ?? 0), 0);
                        const latestIssue = fuelIssues[v.id].find(i => !i.is_reversed);
                        return (
                          <>
                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground pb-1 border-b border-border/50">
                              <span>Total: <strong className="text-foreground">{totalLitres.toFixed(1)} L</strong></span>
                              <span>Cost: <strong className="text-foreground">{formatCurrency(totalCost)}</strong></span>
                              <span>{timeline.length} entries</span>
                              {latestIssue?.estimated_remaining_litres != null && (
                                <span>Est. remaining: <strong className="text-foreground">{latestIssue.estimated_remaining_litres.toFixed(1)} L</strong></span>
                              )}
                            </div>
                            {timeline.slice(0, 10).map(entry => (
                              <div key={entry.key} className={cn(
                                "flex items-start justify-between text-xs rounded-lg px-2 py-1.5",
                                entry.anomaly && "bg-destructive/5",
                                entry.reversed && "opacity-50",
                              )}>
                                <div className="space-y-0.5">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <Droplet className="w-3 h-3 text-muted-foreground" />
                                    <span className="font-medium">{entry.litres.toFixed(1)} L</span>
                                    {entry.source === "legacy" && (
                                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">Legacy</Badge>
                                    )}
                                    {entry.reversed && (
                                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">Reversed</Badge>
                                    )}
                                    {entry.anomaly && <AlertTriangle className="w-3 h-3 text-destructive" title="Review required" />}
                                  </div>
                                  <div className="text-muted-foreground pl-5 flex flex-wrap gap-2">
                                    {v.uses_hours
                                      ? entry.hours != null && <span>⏱ {entry.hours.toLocaleString()} hrs</span>
                                      : entry.odometer != null && <span>📍 {entry.odometer.toLocaleString()} km</span>}
                                    {entry.consumption && (
                                      <span className={entry.anomaly ? "text-destructive font-medium" : ""}>{entry.consumption}</span>
                                    )}
                                    {entry.evidenceCount > 0 && <span>📎 {entry.evidenceCount} evidence file(s)</span>}
                                    {entry.photoUrl && <a href={entry.photoUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">📷 Photo</a>}
                                  </div>
                                  {entry.anomaly && entry.anomalyReason && (
                                    <p className="text-destructive pl-5">{entry.anomalyReason}</p>
                                  )}
                                </div>
                                <div className="text-right shrink-0 ml-3">
                                  <p className="font-medium">{entry.cost != null ? formatCurrency(entry.cost) : "—"}</p>
                                  <p className="text-muted-foreground">{new Date(entry.date).toLocaleDateString("en-ZA")}</p>
                                </div>
                              </div>
                            ))}
                          </>
                        );
                      })()}
                    </div>
                  )}

                  {/* Parts history tab */}
                  {(activeTab[v.id] ?? "details") === "parts" && (
                    <div className="px-4 py-3 space-y-2">
                      {!partsHistory[v.id] ? (
                        <p className="text-xs text-muted-foreground">Loading…</p>
                      ) : partsHistory[v.id].length === 0 ? (
                        <p className="text-xs text-muted-foreground">No spare parts have been issued to this vehicle yet.</p>
                      ) : (
                        <>
                          <div className="flex gap-4 text-xs text-muted-foreground pb-1 border-b border-border/50">
                            <span>
                              Total issued: <strong className="text-foreground">
                                {partsHistory[v.id].reduce((s, i) => s + i.quantity_issued, 0).toLocaleString()}
                              </strong> units
                            </span>
                            <span>
                              {new Set(partsHistory[v.id].map(i => i.item_id)).size} part type(s)
                            </span>
                            <span>{partsHistory[v.id].length} issuance(s)</span>
                          </div>
                          <div className="space-y-1">
                            {partsHistory[v.id].map(iss => (
                              <div key={iss.id} className="flex items-center justify-between text-xs gap-3">
                                <div className="flex items-center gap-2 min-w-0">
                                  <History className="w-3 h-3 text-muted-foreground shrink-0" />
                                  <div className="min-w-0">
                                    <p className="font-medium truncate">
                                      {iss.item?.name ?? iss.item_id.slice(0, 8)}
                                    </p>
                                    {iss.item?.part_number && (
                                      <p className="text-muted-foreground">#{iss.item.part_number}</p>
                                    )}
                                  </div>
                                </div>
                                <div className="shrink-0 text-right space-y-0.5">
                                  <p className="font-semibold tabular-nums">
                                    {iss.quantity_issued % 1 === 0 ? iss.quantity_issued : iss.quantity_issued.toFixed(2)}
                                    {" "}<span className="font-normal text-muted-foreground">{iss.item?.unit ?? ""}</span>
                                  </p>
                                  <p className="text-muted-foreground">
                                    {new Date(iss.issued_at).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })}
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </>
                      )}
                    </div>
                  )}

                  {/* Repairs tab */}
                  {(activeTab[v.id] ?? "details") === "repairs" && (
                    <div className="px-4 py-3 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">
                          {repairs[v.id]?.length ?? 0} repair job(s)
                        </span>
                        <Button size="sm" variant="outline" onClick={() => setNewRepairFor(v)}>
                          <Plus className="w-3.5 h-3.5" />
                          New Repair Job
                        </Button>
                      </div>
                      {!repairs[v.id] ? (
                        <p className="text-xs text-muted-foreground">Loading…</p>
                      ) : repairs[v.id].length === 0 ? (
                        <p className="text-xs text-muted-foreground">No repair jobs logged yet. Click "New Repair Job" to get started.</p>
                      ) : (
                        <div className="space-y-3">
                          {repairs[v.id].map(job => (
                            <div key={job.id} className="border border-border/60 rounded-lg p-3 space-y-2">
                              <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <p className="text-sm font-medium">{job.title}</p>
                                  {job.description && <p className="text-xs text-muted-foreground">{job.description}</p>}
                                </div>
                                <Badge
                                  variant="secondary"
                                  className={cn(
                                    "text-xs shrink-0",
                                    job.status === "OPEN"
                                      ? "bg-amber-500/10 text-amber-600"
                                      : "bg-green-500/10 text-green-600"
                                  )}
                                >
                                  {job.status}
                                </Badge>
                              </div>
                              <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
                                <span>Opened: <strong className="text-foreground">{formatDate(job.date_opened)}</strong></span>
                                {job.workshop_name && (
                                  <span>Workshop: <strong className="text-foreground">{job.workshop_name}</strong></span>
                                )}
                                {job.odometer_at_repair != null && (
                                  <span>Odometer: <strong className="text-foreground">{job.odometer_at_repair.toLocaleString()} km</strong></span>
                                )}
                                {job.date_closed && (
                                  <span>Closed: <strong className="text-foreground">{formatDate(job.date_closed)}</strong></span>
                                )}
                              </div>
                              {job.labour_costs.length > 0 && (
                                <div className="bg-muted/30 rounded p-2 space-y-1">
                                  {job.labour_costs.map(c => (
                                    <div key={c.id} className="flex items-center justify-between text-xs">
                                      <span className="text-muted-foreground">
                                        {costTypeLabels[c.cost_type]}{c.description ? ` — ${c.description}` : ""}
                                        <span className="ml-2 text-muted-foreground/60">{c.cost_date}</span>
                                      </span>
                                      <span className="font-medium">R{c.amount.toLocaleString()}</span>
                                    </div>
                                  ))}
                                  <div className="border-t border-border/50 pt-1 flex justify-between text-xs font-semibold">
                                    <span>Total</span>
                                    <span>R{job.total_labour_cost.toLocaleString()}</span>
                                  </div>
                                </div>
                              )}
                              {job.mr_count > 0 && (
                                <p className="text-xs text-muted-foreground">
                                  {job.mr_count} material request{job.mr_count !== 1 ? "s" : ""} linked
                                </p>
                              )}
                              <div className="flex gap-2 pt-0.5">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="text-xs h-7 px-2.5"
                                  onClick={() => setLogRepairCostFor({ vehicle: v, job })}
                                >
                                  <Plus className="w-3 h-3 mr-1" /> Add Cost
                                </Button>
                                {job.status === "OPEN" && (
                                  <button
                                    onClick={async () => {
                                      if (!window.confirm("Close this repair job?")) return;
                                      try {
                                        const updated = await vehiclesApi.updateRepair(job.id, {
                                          status: "CLOSED",
                                          date_closed: new Date().toISOString().split("T")[0],
                                        });
                                        setRepairs(prev => ({
                                          ...prev,
                                          [v.id]: (prev[v.id] ?? []).map(j => j.id === job.id ? updated : j),
                                        }));
                                      } catch {
                                        alert("Failed to close repair job.");
                                      }
                                    }}
                                    className="text-xs px-2.5 h-7 rounded-md border border-border hover:bg-green-500/10 hover:text-green-600 hover:border-green-500/30 transition-colors"
                                  >
                                    ✓ Close Job
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
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

      {assignFor && (
        <AssignVehicleModal
          vehicle={assignFor}
          onClose={() => setAssignFor(null)}
          onSaved={(updated) => {
            setVehicles(prev => prev.map(x => x.id === updated.id ? updated : x));
            setAssignFor(null);
          }}
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

      {newRepairFor && (
        <NewRepairJobModal
          vehicle={newRepairFor}
          onClose={() => setNewRepairFor(null)}
          onCreated={(job) => {
            setRepairs(prev => ({
              ...prev,
              [newRepairFor.id]: [job, ...(prev[newRepairFor.id] ?? [])],
            }));
          }}
        />
      )}

      {logRepairCostFor && (
        <LogRepairCostModal
          job={logRepairCostFor.job}
          onClose={() => setLogRepairCostFor(null)}
          onLogged={() => loadRepairs(logRepairCostFor.vehicle.id)}
        />
      )}
    </div>
  );
}
