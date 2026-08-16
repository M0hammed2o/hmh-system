import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fuelManagementApi, type FuelEquipmentProfile, type FuelOrder, type FuelStorage, type FuelTypeDefinition } from "@/api/fuelManagement";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { vehiclesApi, type Vehicle } from "@/api/vehicles";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function SiteFuelRequestPage() {
  const [projects, setProjects] = useState<Project[]>([]); const [sites, setSites] = useState<Site[]>([]);
  const [types, setTypes] = useState<FuelTypeDefinition[]>([]); const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [storage, setStorage] = useState<FuelStorage[]>([]); const [profiles, setProfiles] = useState<FuelEquipmentProfile[]>([]);
  const [mine, setMine] = useState<FuelOrder[]>([]); const [error, setError] = useState(""); const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ project_id: "", site_id: "", fuel_type_id: "", requested_litres: "", intended_use: "", expected_delivery_date: "", destination_type: "VEHICLE", vehicle_id: "", storage_location_id: "", equipment_reference: "", notes: "" });
  useEffect(() => { Promise.all([projectsApi.list(1, 100), fuelManagementApi.fuelTypes()]).then(([p, f]) => { setProjects(p.items); setTypes(f); setForm(x => ({ ...x, project_id: p.items[0]?.id || "", fuel_type_id: f[0]?.id || "" })); }); }, []);
  useEffect(() => { if (!form.project_id) return; Promise.all([sitesApi.list(form.project_id), vehiclesApi.list(form.project_id), fuelManagementApi.storage(form.project_id), fuelManagementApi.equipmentProfiles(form.project_id), fuelManagementApi.orders(form.project_id, true)]).then(([s, v, stores, equipment, o]) => { setSites(s); setVehicles(v); setStorage(stores); setProfiles(equipment); setMine(o); setForm(x => ({ ...x, site_id: s.some(y => y.id === x.site_id) ? x.site_id : s[0]?.id || "", vehicle_id: "", storage_location_id: "", equipment_reference: "" })); }).catch(() => setError("Could not load your site fuel requests.")); }, [form.project_id]);
  const submit = async () => {
    if (saving) return; setSaving(true); setError("");
    try {
      const site = sites.find(x => x.id === form.site_id);
      await fuelManagementApi.submitRequest(form.project_id, { ...form, requested_litres: Number(form.requested_litres), expected_delivery_date: form.expected_delivery_date || null, delivery_location: site?.name || "Site", vehicle_id: form.vehicle_id || null, storage_location_id: form.storage_location_id || null, equipment_reference: form.equipment_reference || null, purpose: form.intended_use });
      setMine(await fuelManagementApi.orders(form.project_id, true)); setForm(x => ({ ...x, requested_litres: "", intended_use: "", notes: "" }));
    } catch (e: unknown) { setError((e as { response?: { data?: { detail?: string } } }).response?.data?.detail || "Could not submit the request."); }
    finally { setSaving(false); }
  };
  const selectedTypeName = types.find(x => x.id === form.fuel_type_id)?.name;
  const balanceStorage = storage.filter(x => x.fuel_type_id === form.fuel_type_id && (!x.site_id || x.site_id === form.site_id));
  return <main className="mx-auto min-h-screen max-w-2xl space-y-5 bg-background p-4">
    <div><Link to="/site" className="text-sm text-primary">← Site dashboard</Link><h1 className="mt-2 text-2xl font-bold">Request fuel</h1><p className="text-sm text-muted-foreground">Submit to the office and track every approval step.</p></div>
    {error && <p className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {form.site_id && <section className="space-y-2 rounded-xl border p-4" aria-label="Fuel balance">
      <h2 className="text-sm font-semibold">Fuel balance</h2>
      {balanceStorage.length === 0 ? (
        <p className="text-sm text-amber-700">No fuel storage location has been configured for {selectedTypeName ?? "this fuel type"} at this site yet. Contact the office before requesting fuel here.</p>
      ) : balanceStorage.map(s => (
        <div key={s.id} className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium">Estimated fuel remaining</p>
            <p className="text-xs text-muted-foreground truncate">{s.name} · {selectedTypeName}</p>
          </div>
          <p className="shrink-0 text-xl font-bold">{s.calculated_balance_litres.toFixed(0)} L</p>
        </div>
      ))}
    </section>}
    <section className="space-y-3 rounded-xl border p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Project"><select className="input" value={form.project_id} onChange={e => setForm({ ...form, project_id: e.target.value })}>{projects.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        <Field label="Site"><select className="input" value={form.site_id} onChange={e => setForm({ ...form, site_id: e.target.value })}>{sites.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        <Field label="Fuel type"><select className="input" value={form.fuel_type_id} onChange={e => setForm({ ...form, fuel_type_id: e.target.value })}>{types.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
        <Field label="Litres"><Input inputMode="decimal" type="number" min="0.01" value={form.requested_litres} onChange={e => setForm({ ...form, requested_litres: e.target.value })} /></Field>
        <Field label="Intended use"><Input value={form.intended_use} onChange={e => setForm({ ...form, intended_use: e.target.value })} /></Field>
        <Field label="Required date"><Input type="date" value={form.expected_delivery_date} onChange={e => setForm({ ...form, expected_delivery_date: e.target.value })} /></Field>
        <Field label="Destination"><select className="input" value={form.destination_type} onChange={e => setForm({ ...form, destination_type: e.target.value, vehicle_id: "", storage_location_id: "", equipment_reference: "" })}><option value="VEHICLE">Vehicle</option><option value="SITE_STORAGE">Site storage</option><option value="PLANT">Plant</option><option value="GENERATOR">Generator</option><option value="OTHER_EQUIPMENT">Other equipment</option></select></Field>
        {form.destination_type === "VEHICLE" ? <Field label="Vehicle"><select className="input" value={form.vehicle_id} onChange={e => setForm({ ...form, vehicle_id: e.target.value })}><option value="">Choose vehicle</option>{vehicles.map(x => <option key={x.id} value={x.id}>{x.registration} · {x.name}</option>)}</select></Field> : form.destination_type === "SITE_STORAGE" ? <Field label="Site storage"><select className="input" value={form.storage_location_id} onChange={e => setForm({ ...form, storage_location_id: e.target.value })}><option value="">Choose storage</option>{storage.filter(x => x.fuel_type_id === form.fuel_type_id).map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field> : <Field label="Equipment profile"><select className="input" value={form.equipment_reference} onChange={e => setForm({ ...form, equipment_reference: e.target.value })}><option value="">Choose equipment</option>{profiles.filter(x => x.destination_type === form.destination_type).map(x => <option key={x.id} value={x.equipment_reference}>{x.equipment_reference}</option>)}</select></Field>}
      </div>
      <Field label="Notes"><textarea className="input min-h-20 py-2" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></Field>
      <Button className="w-full" disabled={saving || !form.site_id || !form.requested_litres || !form.intended_use || !form.expected_delivery_date || (form.destination_type === "VEHICLE" ? !form.vehicle_id : form.destination_type === "SITE_STORAGE" ? !form.storage_location_id : !form.equipment_reference)} onClick={() => void submit()}>{saving ? "Submitting…" : "Submit fuel request"}</Button>
    </section>
    <section className="space-y-3"><h2 className="text-lg font-semibold">My requests</h2>{mine.length === 0 ? <p className="rounded border border-dashed p-6 text-center text-sm text-muted-foreground">No fuel requests yet.</p> : mine.map(order => <details key={order.id} className="rounded-xl border p-4"><summary className="cursor-pointer font-medium">{order.order_number} · {order.requested_litres} L · {order.status.replaceAll("_", " ")}</summary><div className="mt-3 space-y-1 text-sm"><p>Next step: {order.next_approver || "Complete"}</p><p>Required: {order.expected_delivery_date || "Not specified"}</p>{order.feasibility_message && <p className="text-amber-700">Review: {order.feasibility_message}</p>}<ol className="mt-2 border-l pl-3">{order.history?.map(h => <li key={h.id}>{new Date(h.created_at).toLocaleString()} — {h.to_status} by {h.actor_name || "User"}{h.reason ? `: ${h.reason}` : ""}</li>)}</ol></div></details>)}</section>
  </main>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div><Label className="mb-1 block">{label}</Label>{children}</div>; }
