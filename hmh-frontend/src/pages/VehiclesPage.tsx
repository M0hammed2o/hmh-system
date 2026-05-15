import { useEffect, useState } from "react";
import { Plus, Car, Wrench, Fuel, MoreHorizontal, Trash2 } from "lucide-react";
import { vehiclesApi, type Vehicle, type VehicleCost, type VehicleCreate, type VehicleCostCreate, type VehicleType, type VehicleCostType } from "@/api/vehicles";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const vehicleTypeLabels: Record<VehicleType, string> = {
  BAKKIE: "Bakkie", TRUCK: "Truck", TLB: "TLB", EXCAVATOR: "Excavator",
  CRANE: "Crane", VAN: "Van", OTHER: "Other",
};

const costTypeLabels: Record<VehicleCostType, string> = {
  FUEL: "Fuel", TYRE: "Tyre", REPAIR: "Repair", SERVICE: "Service",
  LICENCE: "Licence", INSURANCE: "Insurance", OTHER: "Other",
};

const costTypeOptions: VehicleCostType[] = ["FUEL", "TYRE", "REPAIR", "SERVICE", "LICENCE", "INSURANCE", "OTHER"];
const vehicleTypeOptions: VehicleType[] = ["BAKKIE", "TRUCK", "TLB", "EXCAVATOR", "CRANE", "VAN", "OTHER"];

function AddVehicleModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState<VehicleCreate>({ registration: "", name: "", vehicle_type: "BAKKIE" });
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-5">Add Vehicle</h2>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label>Registration</Label>
            <Input value={form.registration} onChange={(e) => setForm({ ...form, registration: e.target.value })} placeholder="e.g. CA 123-456" required />
          </div>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Site Hilux" required />
          </div>
          <div className="space-y-2">
            <Label>Type</Label>
            <select
              value={form.vehicle_type}
              onChange={(e) => setForm({ ...form, vehicle_type: e.target.value as VehicleType })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {vehicleTypeOptions.map((t) => <option key={t} value={t}>{vehicleTypeLabels[t]}</option>)}
            </select>
          </div>
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

function LogCostModal({ vehicle, onClose, onLogged }: { vehicle: Vehicle; onClose: () => void; onLogged: () => void }) {
  const today = new Date().toISOString().split("T")[0];
  const [form, setForm] = useState<VehicleCostCreate>({ cost_type: "FUEL", amount: 0, cost_date: today });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState("");

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

  const toggleExpand = (id: string) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    loadCosts(id);
  };

  useEffect(() => { loadVehicles(); }, []);

  const totalMonthCost = Object.values(costs).flat().reduce((sum, c) => sum + c.amount, 0);

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

              {expanded === v.id && costs[v.id] && (
                <div className="border-t border-border px-4 py-3 bg-muted/20 space-y-2">
                  {/* Cost summary */}
                  {costs[v.id].length > 0 && (
                    <div className="flex gap-4 text-xs text-muted-foreground pb-1 border-b border-border/50">
                      <span>Total cost: <strong className="text-foreground">R{costs[v.id].reduce((s, c) => s + c.amount, 0).toLocaleString()}</strong></span>
                      <span>Entries: <strong className="text-foreground">{costs[v.id].length}</strong></span>
                    </div>
                  )}
                  {costs[v.id].length === 0 ? (
                    <p className="text-xs text-muted-foreground">No costs logged yet.</p>
                  ) : (
                    costs[v.id].slice(0, 10).map((cost) => (
                      <div key={cost.id} className="flex items-center justify-between text-sm">
                        <div className="flex items-center gap-2">
                          {cost.cost_type === "FUEL" ? <Fuel className="w-3.5 h-3.5 text-muted-foreground" /> : <Wrench className="w-3.5 h-3.5 text-muted-foreground" />}
                          <span className="text-muted-foreground">{costTypeLabels[cost.cost_type]}</span>
                          {cost.description && <span className="text-xs text-muted-foreground">— {cost.description}</span>}
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="font-medium">R{cost.amount.toLocaleString()}</span>
                          <span className="text-xs text-muted-foreground">{cost.cost_date}</span>
                        </div>
                      </div>
                    ))
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
