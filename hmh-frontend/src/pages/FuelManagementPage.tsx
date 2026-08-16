import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, useSearchParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Download, Droplets, Gauge, Plus, RefreshCw, Truck } from "lucide-react";

import { projectsApi, type Project } from "@/api/projects";
import { vehiclesApi, type Vehicle } from "@/api/vehicles";
import {
  fuelManagementApi, type FuelDashboard, type FuelDelivery, type FuelIssue,
  type FuelOrder, type FuelReconciliation, type FuelStorage, type FuelTypeDefinition,
} from "@/api/fuelManagement";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { compressImage } from "@/lib/compressImage";

export type FuelSection = "dashboard" | "orders" | "deliveries" | "issues" | "stock" | "reports";

const tabs: { section: FuelSection; label: string; path: string }[] = [
  { section: "dashboard", label: "Dashboard", path: "/fuel-management" },
  { section: "orders", label: "Orders", path: "/fuel-management/orders" },
  { section: "deliveries", label: "Deliveries", path: "/fuel-management/deliveries" },
  { section: "issues", label: "Issues", path: "/fuel-management/issues" },
  { section: "stock", label: "Stock & Reconciliation", path: "/fuel-management/stock" },
  { section: "reports", label: "Reports", path: "/fuel-management/reports" },
];

const fmt = (value: number | null | undefined) => `${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })} L`;
const statusClass = (status: string) => status.includes("REJECT") || status.includes("CANCEL")
  ? "bg-red-100 text-red-700" : status.includes("DELIVERED") || status === "CLOSED" || status === "VERIFIED" || status === "APPROVED"
  ? "bg-green-100 text-green-700" : status.includes("PENDING") || status === "SUBMITTED"
  ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700";

export default function FuelManagementPage({ section = "dashboard" }: { section?: FuelSection }) {
  const [searchParams] = useSearchParams();
  const linkedOrderId = section === "orders" ? searchParams.get("order") : null;
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [fuelTypes, setFuelTypes] = useState<FuelTypeDefinition[]>([]);
  const [storage, setStorage] = useState<FuelStorage[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [orders, setOrders] = useState<FuelOrder[]>([]);
  const [deliveries, setDeliveries] = useState<FuelDelivery[]>([]);
  const [issues, setIssues] = useState<FuelIssue[]>([]);
  const [reconciliations, setReconciliations] = useState<FuelReconciliation[]>([]);
  const [dashboard, setDashboard] = useState<FuelDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    Promise.all([
      projectsApi.list(1, 100), fuelManagementApi.fuelTypes(),
      linkedOrderId ? fuelManagementApi.order(linkedOrderId).catch(() => null) : Promise.resolve(null),
    ])
      .then(([p, types, linkedOrder]) => {
        setProjects(p.items); setFuelTypes(types);
        if (linkedOrder) {
          setProjectId(linkedOrder.project_id); setOrders([linkedOrder]);
        } else if (p.items.length) setProjectId((current) => current || p.items[0].id);
      }).catch(() => setError("Could not load Fuel Management setup data."));
  }, [linkedOrderId]);

  const reload = useCallback(async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const [stores, allOrders] = await Promise.all([
        fuelManagementApi.storage(projectId), fuelManagementApi.orders(projectId),
      ]);
      setStorage(stores); setOrders(allOrders);
      if (section === "dashboard") setDashboard(await fuelManagementApi.dashboard(projectId));
      if (section === "deliveries") setDeliveries(await fuelManagementApi.deliveries(projectId));
      if (section === "issues") {
        const [rows, fleet] = await Promise.all([fuelManagementApi.issues(projectId), vehiclesApi.list(projectId)]);
        setIssues(rows); setVehicles(fleet);
      }
      if (section === "stock") setReconciliations(await fuelManagementApi.reconciliations(projectId));
    } catch (e: any) {
      setError(e?.response?.data?.message || e?.response?.data?.detail || "Could not load fuel data.");
    } finally { setLoading(false); }
  }, [projectId, section]);

  useEffect(() => { void reload(); }, [reload]);

  const fuelName = (id: string) => fuelTypes.find((x) => x.id === id)?.name || "Fuel";
  const storageName = (id: string | null) => storage.find((x) => x.id === id)?.name || "—";
  const ordered = useMemo(() => orders.filter((x) => ["ORDERED", "PARTIALLY_DELIVERED"].includes(x.status)), [orders]);
  const run = async (action: () => Promise<unknown>) => {
    setError("");
    try { await action(); setShowForm(false); await reload(); }
    catch (e: any) { setError(e?.response?.data?.message || e?.response?.data?.detail || "Action failed."); }
  };

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-5 overflow-x-hidden">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div><h1 className="text-2xl font-bold flex items-center gap-2"><Droplets className="w-6 h-6 text-blue-600" />Fuel Management</h1>
          <p className="text-sm text-muted-foreground mt-1">Orders, deliveries, auditable stock, usage and variance review — separate from BOQ.</p></div>
        <Button variant="outline" size="sm" onClick={() => void reload()} disabled={loading}><RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />Refresh</Button>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
        {tabs.map((tab) => <NavLink key={tab.section} to={tab.path} end={tab.section === "dashboard"}
          className={({ isActive }) => `whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground"}`}>{tab.label}</NavLink>)}
      </div>

      <div className="max-w-md"><Label htmlFor="fuel-project">Project</Label><select id="fuel-project" value={projectId} onChange={(e) => setProjectId(e.target.value)}
        className="mt-1 h-10 w-full rounded-md border bg-background px-3 text-sm"><option value="">Choose a project</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {!projectId ? <Empty text="Choose a project to view fuel records." /> : section === "dashboard" ? <Dashboard data={dashboard} />
        : section === "orders" ? <Orders orders={orders} linkedOrderId={linkedOrderId} fuelName={fuelName} showForm={showForm} setShowForm={setShowForm} projectId={projectId} storage={storage} fuelTypes={fuelTypes} run={run} />
        : section === "deliveries" ? <Deliveries rows={deliveries} ordered={ordered} storage={storage} showForm={showForm} setShowForm={setShowForm} run={run} />
        : section === "issues" ? <Issues rows={issues} storage={storage} vehicles={vehicles} showForm={showForm} setShowForm={setShowForm} projectId={projectId} run={run} />
        : section === "stock" ? <Stock storage={storage} fuelTypes={fuelTypes} rows={reconciliations} showForm={showForm} setShowForm={setShowForm} projectId={projectId} run={run} />
        : <Reports projectId={projectId} run={run} />}
    </div>
  );
}

function Dashboard({ data }: { data: FuelDashboard | null }) {
  if (!data) return <Empty text="Loading fuel dashboard…" />;
  const cards = [
    ["Requested", fmt(data.litres_requested), Droplets], ["Approved", fmt(data.litres_approved), CheckCircle2],
    ["Delivered", fmt(data.litres_delivered), Truck], ["Issued", fmt(data.litres_issued), Gauge],
    ["Calculated stock", fmt(data.current_calculated_stock), Droplets], ["Anomalies for review", data.anomalies_for_review, AlertTriangle],
  ] as const;
  return <><div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">{cards.map(([label, value, Icon]) => <div key={label} className="rounded-xl border bg-card p-4"><Icon className="w-5 h-5 text-blue-600" /><p className="text-xs text-muted-foreground mt-3">{label}</p><p className="text-2xl font-bold mt-1">{value}</p></div>)}</div>
    <div className="grid sm:grid-cols-2 gap-3"><div className="rounded-xl border p-4"><p className="font-semibold">Outstanding orders</p><p className="text-3xl font-bold mt-2">{data.outstanding_orders}</p></div><div className="rounded-xl border p-4"><p className="font-semibold">Overdue deliveries</p><p className="text-3xl font-bold mt-2 text-amber-600">{data.overdue_deliveries}</p></div></div></>;
}

function Orders({ orders, linkedOrderId, fuelName, showForm, setShowForm, projectId, storage, fuelTypes, run }: any) {
  const [form, setForm] = useState({ fuel_type_id: "", storage_location_id: "", requested_litres: "", delivery_location: "", expected_delivery_date: "", purpose: "" });
  useEffect(() => { if (!form.fuel_type_id && fuelTypes[0]) setForm((x) => ({ ...x, fuel_type_id: fuelTypes[0].id })); }, [fuelTypes, form.fuel_type_id]);
  const transition = (order: FuelOrder, action: any) => {
    const reason = ["reject", "cancel"].includes(action) ? window.prompt("Reason") : undefined;
    const override_reason = action === "approve" && order.feasibility_status === "OVERRIDE_REQUIRED" ? window.prompt("Authorised feasibility override reason") : undefined;
    const supplier_reference = action === "mark-ordered" ? window.prompt("Supplier reference") : undefined;
    if (["reject", "cancel"].includes(action) && !reason || action === "mark-ordered" && !supplier_reference || action === "approve" && order.feasibility_status === "OVERRIDE_REQUIRED" && !override_reason) return;
    void run(() => fuelManagementApi.transitionOrder(order.id, action, { reason, override_reason, supplier_reference }));
  };
  return <Section title="Fuel Orders" action={<Button onClick={() => setShowForm(!showForm)}><Plus className="w-4 h-4" />New request</Button>}>
    {showForm && <FormCard><div className="grid sm:grid-cols-2 gap-3"><Field label="Fuel type"><select value={form.fuel_type_id} onChange={(e) => setForm({ ...form, fuel_type_id: e.target.value })} className="input"><option value="">Choose</option>{fuelTypes.map((x: FuelTypeDefinition) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
      <Field label="Destination storage"><select value={form.storage_location_id} onChange={(e) => setForm({ ...form, storage_location_id: e.target.value })} className="input"><option value="">Choose</option>{storage.filter((x: FuelStorage) => x.fuel_type_id === form.fuel_type_id).map((x: FuelStorage) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field>
      <Field label="Requested litres"><Input type="number" min="0.01" value={form.requested_litres} onChange={(e) => setForm({ ...form, requested_litres: e.target.value })} /></Field><Field label="Expected delivery"><Input type="date" value={form.expected_delivery_date} onChange={(e) => setForm({ ...form, expected_delivery_date: e.target.value })} /></Field>
      <Field label="Delivery location"><Input value={form.delivery_location} onChange={(e) => setForm({ ...form, delivery_location: e.target.value })} /></Field><Field label="Purpose / notes"><Input value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} /></Field></div>
      <Button onClick={() => void run(() => fuelManagementApi.createOrder(projectId, { ...form, requested_litres: Number(form.requested_litres), expected_delivery_date: form.expected_delivery_date || null, storage_location_id: form.storage_location_id || null }))}>Save draft</Button></FormCard>}
    <CardList empty="No fuel orders yet.">{orders.map((o: FuelOrder) => <article key={o.id} data-testid={`fuel-order-${o.id}`} className={`rounded-xl border p-4 space-y-3 ${linkedOrderId === o.id ? "ring-2 ring-primary" : ""}`}><div className="flex flex-wrap justify-between gap-2"><div><p className="font-semibold">{o.order_number}</p><p className="text-sm text-muted-foreground">{fuelName(o.fuel_type_id)} · {fmt(o.requested_litres)} · delivered {fmt(o.delivered_litres)}</p><p className="text-xs text-muted-foreground">Requested by {o.requester_name || "User"} · next: {o.next_approver || "complete"}</p>{o.feasibility_message && <p className="mt-1 text-sm text-amber-700">Review flag: {o.feasibility_message}</p>}</div><Badge className={statusClass(o.status)}>{o.status.replaceAll("_", " ")}</Badge></div>
      <details className="text-sm" open={linkedOrderId === o.id || undefined}><summary className="cursor-pointer text-primary">Details and approval history</summary><div className="mt-2 space-y-1"><p>Intended use: {o.intended_use || o.purpose || "—"}</p><p>Destination: {o.destination_type?.replaceAll("_", " ") || "—"} {o.equipment_reference || ""}</p><ol className="border-l pl-3">{o.history?.map(h => <li key={h.id}>{new Date(h.created_at).toLocaleString()} — {h.to_status} by {h.actor_name || "User"}{h.reason ? `: ${h.reason}` : ""}</li>)}</ol></div></details>
      <div className="flex flex-wrap gap-2">{o.status === "DRAFT" && <Button size="sm" onClick={() => transition(o, "submit")}>Submit</Button>}{o.status === "SUBMITTED" && <><Button size="sm" onClick={() => transition(o, "approve")}>Approve</Button><Button size="sm" variant="outline" onClick={() => transition(o, "reject")}>Reject</Button></>}{o.status === "APPROVED" && <Button size="sm" onClick={() => transition(o, "mark-ordered")}>Mark ordered</Button>}{o.status === "DELIVERED" && <Button size="sm" onClick={() => transition(o, "close")}>Close</Button>}</div></article>)}</CardList>
  </Section>;
}

function Deliveries({ rows, ordered, storage, showForm, setShowForm, run }: any) {
  const [form, setForm] = useState({ order_id: "", storage_location_id: "", delivered_litres: "", delivery_note_number: "", opening_reading: "", closing_reading: "", tanker_registration: "", driver_details: "" });
  return <Section title="Fuel Deliveries" action={<Button onClick={() => setShowForm(!showForm)}><Plus className="w-4 h-4" />Record delivery</Button>}>
    {showForm && <FormCard><div className="grid sm:grid-cols-2 gap-3"><Field label="Ordered request"><select className="input" value={form.order_id} onChange={(e) => { const order = ordered.find((x: FuelOrder) => x.id === e.target.value); setForm({ ...form, order_id: e.target.value, storage_location_id: order?.storage_location_id || "" }); }}><option value="">Choose</option>{ordered.map((x: FuelOrder) => <option key={x.id} value={x.id}>{x.order_number} · outstanding {fmt(x.requested_litres - x.delivered_litres)}</option>)}</select></Field>
      <Field label="Destination tank"><select className="input" value={form.storage_location_id} onChange={(e) => setForm({ ...form, storage_location_id: e.target.value })}><option value="">Choose</option>{storage.map((x: FuelStorage) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field><Field label="Delivered litres"><Input type="number" value={form.delivered_litres} onChange={(e) => setForm({ ...form, delivered_litres: e.target.value })} /></Field><Field label="Delivery note number"><Input value={form.delivery_note_number} onChange={(e) => setForm({ ...form, delivery_note_number: e.target.value })} /></Field><Field label="Opening meter"><Input type="number" value={form.opening_reading} onChange={(e) => setForm({ ...form, opening_reading: e.target.value })} /></Field><Field label="Closing meter"><Input type="number" value={form.closing_reading} onChange={(e) => setForm({ ...form, closing_reading: e.target.value })} /></Field><Field label="Tanker registration"><Input value={form.tanker_registration} onChange={(e) => setForm({ ...form, tanker_registration: e.target.value })} /></Field><Field label="Driver details"><Input value={form.driver_details} onChange={(e) => setForm({ ...form, driver_details: e.target.value })} /></Field></div>
      <Button onClick={() => void run(() => fuelManagementApi.recordDelivery(form.order_id, { ...form, delivered_at: new Date().toISOString(), delivered_litres: Number(form.delivered_litres), storage_location_id: form.storage_location_id, opening_reading: form.opening_reading ? Number(form.opening_reading) : null, closing_reading: form.closing_reading ? Number(form.closing_reading) : null }))}>Record pending delivery</Button></FormCard>}
    <CardList empty="No deliveries recorded.">{rows.map((d: FuelDelivery) => <article key={d.id} className="rounded-xl border p-4"><div className="flex flex-wrap justify-between gap-2"><div><p className="font-semibold">{d.delivery_note_number || "Delivery"}</p><p className="text-sm text-muted-foreground">{fmt(d.confirmed_litres || d.litres_delivered)} · {storage.find((s: FuelStorage) => s.id === d.storage_location_id)?.name || "Storage"} · variance {fmt(d.variance_litres)}</p></div><Badge className={statusClass(d.verification_status)}>{d.verification_status}</Badge></div>{d.verification_status === "PENDING" && <div className="flex gap-2 mt-3"><Button size="sm" onClick={() => void run(() => fuelManagementApi.verifyDelivery(d.id))}>Verify</Button><Button size="sm" variant="outline" onClick={() => void run(() => fuelManagementApi.verifyDelivery(d.id, false))}>Reject</Button></div>}</article>)}</CardList>
  </Section>;
}

function Issues({ rows, storage, vehicles, showForm, setShowForm, projectId, run }: any) {
  const [form, setForm] = useState({ storage_location_id: "", fuel_type_id: "", destination_type: "VEHICLE", vehicle_id: "", equipment_reference: "", litres: "", odometer_reading: "", hour_meter_reading: "", received_by: "", purpose: "" });
  const [files, setFiles] = useState<Record<string, File | null>>({ asset_photo: null, pump_photo: null, odometer_photo: null, hour_meter_photo: null });
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const chooseStorage = (id: string) => { const store = storage.find((x: FuelStorage) => x.id === id); setForm({ ...form, storage_location_id: id, fuel_type_id: store?.fuel_type_id || "" }); };
  const saveCapture = async (key: string, file: File | null) => {
    const next = file ? await compressImage(file) : null;
    setFiles((current) => ({ ...current, [key]: next }));
  };
  const submit = async () => {
    if (uploading) return;
    setUploading(true); setProgress(0);
    try {
      await run(() => fuelManagementApi.createIssueWithEvidence(projectId, {
        ...form, litres: Number(form.litres), vehicle_id: form.vehicle_id || null,
        equipment_reference: form.equipment_reference || null,
        odometer_reading: form.odometer_reading ? Number(form.odometer_reading) : null,
        hour_meter_reading: form.hour_meter_reading ? Number(form.hour_meter_reading) : null,
        reading_source: "PHOTOGRAPH_VERIFIED",
      }, files, setProgress));
    } finally { setUploading(false); }
  };
  return <Section title="Fuel Issues" action={<Button onClick={() => setShowForm(!showForm)}><Plus className="w-4 h-4" />Issue fuel</Button>}>
    {showForm && <FormCard><div className="grid sm:grid-cols-2 gap-3"><Field label="Source storage"><select className="input" value={form.storage_location_id} onChange={(e) => chooseStorage(e.target.value)}><option value="">Choose</option>{storage.map((x: FuelStorage) => <option key={x.id} value={x.id}>{x.name} · {fmt(x.calculated_balance_litres)}</option>)}</select></Field><Field label="Destination type"><select className="input" value={form.destination_type} onChange={(e) => setForm({ ...form, destination_type: e.target.value, vehicle_id: "", equipment_reference: "" })}><option value="VEHICLE">Vehicle</option><option value="PLANT">Plant</option><option value="GENERATOR">Generator</option><option value="STORAGE_TANK">Storage tank</option><option value="OTHER_EQUIPMENT">Other equipment</option></select></Field>
      {form.destination_type === "VEHICLE" ? <Field label="Vehicle"><select className="input" value={form.vehicle_id} onChange={(e) => setForm({ ...form, vehicle_id: e.target.value })}><option value="">Choose</option>{vehicles.map((v: Vehicle) => <option key={v.id} value={v.id}>{v.registration} · {v.name}</option>)}</select></Field> : <Field label="Equipment / generator reference"><Input value={form.equipment_reference} onChange={(e) => setForm({ ...form, equipment_reference: e.target.value })} /></Field>}
      <Field label="Litres issued"><Input type="number" min="0.01" value={form.litres} onChange={(e) => setForm({ ...form, litres: e.target.value })} /></Field>{form.destination_type === "VEHICLE" ? <Field label="Odometer (km)"><Input type="number" value={form.odometer_reading} onChange={(e) => setForm({ ...form, odometer_reading: e.target.value })} /></Field> : <Field label="Hour meter"><Input type="number" value={form.hour_meter_reading} onChange={(e) => setForm({ ...form, hour_meter_reading: e.target.value })} /></Field>}<Field label="Received by / operator"><Input value={form.received_by} onChange={(e) => setForm({ ...form, received_by: e.target.value })} /></Field><Field label="Purpose"><Input value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} /></Field></div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <CameraCapture label="Vehicle / equipment" file={files.asset_photo} onChange={(f) => void saveCapture("asset_photo", f)} required />
        <CameraCapture label="Pump / dispenser" file={files.pump_photo} onChange={(f) => void saveCapture("pump_photo", f)} required />
        {form.destination_type === "VEHICLE" ? <CameraCapture label="Odometer" file={files.odometer_photo} onChange={(f) => void saveCapture("odometer_photo", f)} required /> : <CameraCapture label="Hour meter" file={files.hour_meter_photo} onChange={(f) => void saveCapture("hour_meter_photo", f)} required />}
      </div>
      {uploading && <div className="space-y-1"><div className="h-2 rounded bg-muted overflow-hidden"><div className="h-full bg-primary" style={{ width: `${progress}%` }} /></div><p className="text-xs text-muted-foreground">Uploading {progress}% — keep this page open.</p></div>}
      <Button disabled={uploading} onClick={() => void submit()}>{uploading ? "Uploading evidence…" : progress > 0 ? "Retry fuel issue" : "Record fuel issue"}</Button></FormCard>}
    <CardList empty="No fuel issues recorded.">{rows.map((i: FuelIssue) => <article key={i.id} className={`rounded-xl border p-4 ${i.anomaly_flag ? "border-amber-300 bg-amber-50/50" : ""}`}><div className="flex flex-wrap justify-between gap-2"><div><p className="font-semibold">{i.issue_number}</p><p className="text-sm text-muted-foreground">{i.destination_type.replaceAll("_", " ")} · {i.vehicle_id ? vehicles.find((v: Vehicle) => v.id === i.vehicle_id)?.registration : i.equipment_reference} · {fmt(i.litres)}</p>{i.anomaly_reason && <p className="text-sm text-amber-700 mt-1">Review flag: {i.anomaly_reason}</p>}</div>{i.is_reversed ? <Badge variant="outline">REVERSED</Badge> : <Badge className={i.anomaly_flag ? "bg-amber-100 text-amber-700" : "bg-green-100 text-green-700"}>{i.anomaly_flag ? "REVIEW" : "RECORDED"}</Badge>}</div></article>)}</CardList>
  </Section>;
}

function CameraCapture({ label, file, onChange, required = false }: { label: string; file: File | null; onChange: (file: File | null) => void; required?: boolean }) {
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file); setPreview(url); return () => URL.revokeObjectURL(url);
  }, [file]);
  return <div className="rounded-lg border p-2 space-y-2">
    <p className="text-xs font-medium">{label}{required ? " *" : ""}</p>
    {preview ? <img src={preview} alt={`${label} preview`} className="h-28 w-full rounded object-cover" /> : <div className="h-28 rounded bg-muted flex items-center justify-center text-xs text-muted-foreground">No photo</div>}
    <div className="flex gap-2"><label className="cursor-pointer rounded border px-2 py-1 text-xs">{file ? "Retake" : "Capture"}<input className="sr-only" type="file" accept="image/*" capture="environment" onChange={(e) => onChange(e.target.files?.[0] || null)} /></label>{file && <button type="button" className="text-xs text-destructive" onClick={() => onChange(null)}>Remove</button>}</div>
  </div>;
}

function Stock({ storage, fuelTypes, rows, showForm, setShowForm, projectId, run }: any) {
  const [mode, setMode] = useState<"reconcile" | "storage">("reconcile");
  const [rec, setRec] = useState({ storage_location_id: "", physical_balance_litres: "", explanation: "" });
  const [store, setStore] = useState({ name: "", fuel_type_id: "", capacity_litres: "", low_stock_threshold_litres: "", opening_stock_litres: "" });
  useEffect(() => {
    if (!store.fuel_type_id && fuelTypes[0]) {
      setStore((current) => ({ ...current, fuel_type_id: fuelTypes[0].id }));
    }
  }, [fuelTypes, store.fuel_type_id]);
  return <Section title="Fuel Stock & Reconciliation" action={<div className="flex gap-2"><Button variant="outline" onClick={() => { setMode("storage"); setShowForm(true); }}>New storage</Button><Button onClick={() => { setMode("reconcile"); setShowForm(true); }}>Reconcile</Button></div>}>
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">{storage.map((s: FuelStorage) => <div key={s.id} className="rounded-xl border p-4"><p className="font-semibold">{s.name}</p><p className="text-3xl font-bold mt-3">{fmt(s.calculated_balance_litres)}</p><p className="text-xs text-muted-foreground mt-1">Capacity {s.capacity_litres ? fmt(s.capacity_litres) : "not set"}</p>{s.low_stock_threshold_litres != null && s.calculated_balance_litres <= s.low_stock_threshold_litres && <p className="text-sm text-amber-700 mt-2 flex gap-1"><AlertTriangle className="w-4 h-4" />Below threshold</p>}</div>)}</div>
    {showForm && mode === "reconcile" && <FormCard><div className="grid sm:grid-cols-2 gap-3"><Field label="Storage location"><select className="input" value={rec.storage_location_id} onChange={(e) => setRec({ ...rec, storage_location_id: e.target.value })}><option value="">Choose</option>{storage.map((x: FuelStorage) => <option key={x.id} value={x.id}>{x.name} · calculated {fmt(x.calculated_balance_litres)}</option>)}</select></Field><Field label="Physical reading (litres)"><Input type="number" value={rec.physical_balance_litres} onChange={(e) => setRec({ ...rec, physical_balance_litres: e.target.value })} /></Field><Field label="Explanation"><Input value={rec.explanation} onChange={(e) => setRec({ ...rec, explanation: e.target.value })} /></Field></div><Button onClick={() => void run(() => fuelManagementApi.reconcile(projectId, { ...rec, physical_balance_litres: Number(rec.physical_balance_litres), reconciliation_date: new Date().toISOString() }))}>Complete reconciliation</Button></FormCard>}
    {showForm && mode === "storage" && <FormCard><div className="grid sm:grid-cols-2 gap-3"><Field label="Storage name"><Input value={store.name} onChange={(e) => setStore({ ...store, name: e.target.value })} /></Field><Field label="Fuel type"><select className="input" value={store.fuel_type_id} onChange={(e) => setStore({ ...store, fuel_type_id: e.target.value })}><option value="">Choose</option>{fuelTypes.map((x: FuelTypeDefinition) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></Field><Field label="Capacity (litres)"><Input type="number" value={store.capacity_litres} onChange={(e) => setStore({ ...store, capacity_litres: e.target.value })} /></Field><Field label="Low-stock threshold"><Input type="number" value={store.low_stock_threshold_litres} onChange={(e) => setStore({ ...store, low_stock_threshold_litres: e.target.value })} /></Field><Field label="Opening stock"><Input type="number" value={store.opening_stock_litres} onChange={(e) => setStore({ ...store, opening_stock_litres: e.target.value })} /></Field></div><Button onClick={() => void run(() => fuelManagementApi.createStorage(projectId, { ...store, capacity_litres: store.capacity_litres ? Number(store.capacity_litres) : null, low_stock_threshold_litres: store.low_stock_threshold_litres ? Number(store.low_stock_threshold_litres) : null, opening_stock_litres: Number(store.opening_stock_litres || 0) }))}>Create storage</Button></FormCard>}
    <CardList empty="No reconciliations recorded.">{rows.map((r: FuelReconciliation) => <article key={r.id} className="rounded-xl border p-4"><div className="flex flex-wrap justify-between gap-2"><div><p className="font-semibold">{r.reconciliation_number}</p><p className="text-sm text-muted-foreground">Calculated {fmt(r.calculated_balance_litres)} · physical {fmt(r.physical_balance_litres)} · variance {fmt(r.variance_litres)}</p><p className="text-sm mt-1">{r.explanation}</p></div><Badge className={statusClass(r.status)}>{r.status.replaceAll("_", " ")}</Badge></div></article>)}</CardList>
  </Section>;
}

function Reports({ projectId, run }: any) {
  return <Section title="Fuel Reports"><div className="grid sm:grid-cols-2 gap-4"><Report title="Fuel order register" text="Requested, delivered and outstanding quantities by order." onClick={() => run(() => fuelManagementApi.downloadReport(projectId, "orders"))} /><Report title="Fuel usage register" text="Vehicle and equipment issues, consumption metrics and review flags." onClick={() => run(() => fuelManagementApi.downloadReport(projectId, "usage"))} /></div><div className="rounded-xl border bg-muted/30 p-4 text-sm text-muted-foreground">All exports are generated server-side and respect the same project access and Fuel Management permissions as the on-screen data.</div></Section>;
}

function Report({ title, text, onClick }: { title: string; text: string; onClick: () => void }) { return <div className="rounded-xl border p-5"><Download className="w-6 h-6 text-blue-600" /><h3 className="font-semibold mt-3">{title}</h3><p className="text-sm text-muted-foreground mt-1 mb-4">{text}</p><Button variant="outline" onClick={onClick}><Download className="w-4 h-4" />Download CSV</Button></div>; }
function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) { return <section className="space-y-4"><div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2"><h2 className="text-xl font-semibold">{title}</h2>{action}</div>{children}</section>; }
function FormCard({ children }: { children: React.ReactNode }) { return <div className="rounded-xl border bg-muted/20 p-4 space-y-4">{children}</div>; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="min-w-0"><Label className="mb-1 block">{label}</Label>{children}</div>; }
function CardList({ empty, children }: { empty: string; children: React.ReactNode }) { return <div className="grid gap-3">{Array.isArray(children) && children.length === 0 ? <Empty text={empty} /> : children}</div>; }
function Empty({ text }: { text: string }) { return <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">{text}</div>; }
