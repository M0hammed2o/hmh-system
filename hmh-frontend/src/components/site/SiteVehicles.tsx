/**
 * SiteVehicles — vehicle management panel embedded in the site dashboard.
 * Mirrors VehiclesPage but filtered to one site, with:
 *   - Bulk diesel delivery tracking (running countdown balance)
 *   - Fill vehicle from bulk delivery
 *   - Enhanced repair workflow: report → quote → 3-step approval → invoice → close
 *   - Vehicle transfer requests
 */

import { useEffect, useState, useRef } from "react";
import {
  Car, Wrench, Droplet, ClipboardList, Plus, ArrowRightLeft, CheckCircle2, FileText,
  Upload, ChevronDown, ChevronUp, Gauge, Clock,
} from "lucide-react";
import {
  vehiclesApi,
  type Vehicle,
  type VehicleCost,
  type VehicleCostCreate,
  type VehicleCostType,
  type FuelType,
  type RepairJob,
  type RepairJobCreate,
} from "@/api/vehicles";
import { fuelApi, fuelPhotoUrl, type FuelLog } from "@/api/fuel";
import { fuelManagementApi, type FuelIssue } from "@/api/fuelManagement";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Site } from "@/api/sites";

// ── Labels ────────────────────────────────────────────────────────────────────

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

const REPAIR_STATUS_LABELS: Record<string, { label: string; color: string }> = {
  OPEN:             { label: "Issue Reported",    color: "bg-amber-500/10 text-amber-600" },
  QUOTE_SUBMITTED:  { label: "Quote Submitted",   color: "bg-blue-500/10 text-blue-600" },
  QUOTE_APPROVED_1: { label: "Approved (1/3)",    color: "bg-indigo-500/10 text-indigo-600" },
  QUOTE_APPROVED_2: { label: "Approved (2/3)",    color: "bg-violet-500/10 text-violet-600" },
  APPROVED:         { label: "Fully Approved",    color: "bg-green-500/10 text-green-600" },
  INVOICE_UPLOADED: { label: "Invoice Uploaded",  color: "bg-teal-500/10 text-teal-600" },
  CLOSED:           { label: "Closed",            color: "bg-muted text-muted-foreground" },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const today = () => new Date().toISOString().split("T")[0];

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


// ── Repair workflow modals ────────────────────────────────────────────────────

function SubmitQuoteModal({ job, onClose, onSubmitted }: { job: RepairJob; onClose: () => void; onSubmitted: (j: RepairJob) => void }) {
  const [amount, setAmount] = useState("");
  const [workshop, setWorkshop] = useState(job.workshop_name ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || parseFloat(amount) <= 0) { setError("Enter quote amount."); return; }
    setLoading(true);
    try {
      const updated = await vehiclesApi.submitRepairQuote(job.id, parseFloat(amount), workshop || undefined, file);
      onSubmitted(updated);
      onClose();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to submit quote.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-1">Submit Quote</h2>
        <p className="text-sm text-muted-foreground mb-4">{job.title}</p>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-2">
            <Label>Workshop / Supplier</Label>
            <Input value={workshop} onChange={e => setWorkshop(e.target.value)} placeholder="e.g. ABC Auto Repairs" />
          </div>
          <div className="space-y-2">
            <Label>Quote Amount (R) *</Label>
            <Input type="number" min="0" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} placeholder="5000.00" required />
          </div>
          <div className="space-y-2">
            <Label>Quote Document (PDF/image)</Label>
            <input ref={fileRef} type="file" accept=".pdf,image/*" className="hidden" onChange={e => setFile(e.target.files?.[0] ?? null)} />
            <Button type="button" variant="outline" className="w-full" onClick={() => fileRef.current?.click()}>
              <Upload className="w-3.5 h-3.5 mr-1" />
              {file ? file.name : "Upload Quote File"}
            </Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">{loading ? "Submitting…" : "Submit Quote"}</Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function UploadInvoiceModal({ job, onClose, onUploaded }: { job: RepairJob; onClose: () => void; onUploaded: (j: RepairJob) => void }) {
  const [amount, setAmount] = useState(job.quote_amount != null ? String(job.quote_amount) : "");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || parseFloat(amount) <= 0) { setError("Enter invoice amount."); return; }
    setLoading(true);
    try {
      const updated = await vehiclesApi.uploadRepairInvoice(job.id, parseFloat(amount), file);
      onUploaded(updated);
      onClose();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to upload invoice.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-1">Upload Invoice</h2>
        <p className="text-sm text-muted-foreground mb-4">{job.title}</p>
        {job.quote_amount && <p className="text-xs text-muted-foreground mb-3">Quote amount: <strong>{formatCurrency(job.quote_amount)}</strong></p>}
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-2">
            <Label>Final Invoice Amount (R) *</Label>
            <Input type="number" min="0" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} required />
          </div>
          <div className="space-y-2">
            <Label>Invoice Document (PDF/image)</Label>
            <input ref={fileRef} type="file" accept=".pdf,image/*" className="hidden" onChange={e => setFile(e.target.files?.[0] ?? null)} />
            <Button type="button" variant="outline" className="w-full" onClick={() => fileRef.current?.click()}>
              <Upload className="w-3.5 h-3.5 mr-1" />
              {file ? file.name : "Upload Invoice File"}
            </Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">{loading ? "Uploading…" : "Upload Invoice"}</Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function RequestTransferModal({ vehicle, siteId, sites, onClose, onRequested }: { vehicle: Vehicle; siteId: string; sites: Site[]; onClose: () => void; onRequested: () => void }) {
  const [toSiteId, setToSiteId] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const otherSites = sites.filter(s => s.id !== siteId);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!toSiteId) { setError("Select destination site."); return; }
    setLoading(true);
    try {
      await vehiclesApi.requestTransfer(vehicle.id, toSiteId, reason || undefined);
      onRequested();
      onClose();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to submit request.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-1">Request Vehicle Transfer</h2>
        <p className="text-sm text-muted-foreground mb-4">{vehicle.name} ({vehicle.registration})</p>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-2">
            <Label>Transfer To *</Label>
            <select
              value={toSiteId}
              onChange={e => setToSiteId(e.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              required
            >
              <option value="">— Select site —</option>
              {otherSites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <Label>Reason</Label>
            <Input value={reason} onChange={e => setReason(e.target.value)} placeholder="Why is the vehicle needed there?" />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={loading} className="flex-1">{loading ? "Requesting…" : "Submit Request"}</Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Repair job card (enhanced with workflow) ─────────────────────────────────

function RepairJobCard({
  job,
  vehicle,
  isViewOnly,
  onUpdated,
}: {
  job: RepairJob;
  vehicle: Vehicle;
  isViewOnly: boolean;
  onUpdated: (j: RepairJob) => void;
}) {
  const [showQuote, setShowQuote] = useState(false);
  const [showInvoice, setShowInvoice] = useState(false);
  const [approving, setApproving] = useState(false);
  const [closing, setClosing] = useState(false);

  const statusInfo = REPAIR_STATUS_LABELS[job.status] ?? { label: job.status, color: "bg-muted text-muted-foreground" };

  const canSubmitQuote = !isViewOnly && (job.status === "OPEN" || job.status === "QUOTE_SUBMITTED");
  const canApprove = !isViewOnly && ["QUOTE_SUBMITTED", "QUOTE_APPROVED_1", "QUOTE_APPROVED_2"].includes(job.status);
  const canUploadInvoice = !isViewOnly && job.status === "APPROVED";
  const canClose = !isViewOnly && (job.status === "INVOICE_UPLOADED" || job.status === "APPROVED" || job.status === "OPEN");

  const handleApprove = async () => {
    if (!window.confirm("Approve this repair quote? (advance to next approval stage)")) return;
    setApproving(true);
    try {
      const updated = await vehiclesApi.approveRepairQuote(job.id);
      onUpdated(updated);
    } catch { alert("Approval failed."); }
    finally { setApproving(false); }
  };

  const handleClose = async () => {
    if (!window.confirm("Close this repair job?")) return;
    setClosing(true);
    try {
      const updated = await vehiclesApi.updateRepair(job.id, {
        status: "CLOSED",
        date_closed: new Date().toISOString().split("T")[0],
      });
      onUpdated(updated);
    } catch { alert("Failed to close repair job."); }
    finally { setClosing(false); }
  };

  return (
    <div className="border border-border/60 rounded-lg p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{job.title}</p>
          {job.description && <p className="text-xs text-muted-foreground">{job.description}</p>}
        </div>
        <Badge variant="secondary" className={cn("text-xs shrink-0", statusInfo.color)}>
          {statusInfo.label}
        </Badge>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
        <span>Opened: <strong className="text-foreground">{formatDate(job.date_opened)}</strong></span>
        {job.workshop_name && <span>Workshop: <strong className="text-foreground">{job.workshop_name}</strong></span>}
        {job.date_closed && <span>Closed: <strong className="text-foreground">{formatDate(job.date_closed)}</strong></span>}
      </div>

      {/* Quote info */}
      {job.quote_amount != null && (
        <div className="bg-blue-500/5 border border-blue-500/20 rounded-md p-2 text-xs space-y-0.5">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Quote:</span>
            <strong>{formatCurrency(job.quote_amount)}</strong>
          </div>
          {job.approval_stage > 0 && (
            <div className="flex items-center gap-1 text-muted-foreground">
              <CheckCircle2 className="w-3 h-3 text-green-500" />
              <span>Approvals: {job.approval_stage}/3</span>
            </div>
          )}
          {job.quote_file_url && (
            <a href={job.quote_file_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-primary hover:underline">
              <FileText className="w-3 h-3" /> View Quote
            </a>
          )}
        </div>
      )}

      {/* Invoice info */}
      {job.invoice_amount != null && (
        <div className="bg-teal-500/5 border border-teal-500/20 rounded-md p-2 text-xs space-y-0.5">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Invoice:</span>
            <strong>{formatCurrency(job.invoice_amount)}</strong>
          </div>
          {job.invoice_file_url && (
            <a href={job.invoice_file_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-primary hover:underline">
              <FileText className="w-3 h-3" /> View Invoice
            </a>
          )}
        </div>
      )}

      {/* Labour costs */}
      {job.labour_costs.length > 0 && (
        <div className="bg-muted/30 rounded p-2 space-y-1">
          {job.labour_costs.map(c => (
            <div key={c.id} className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{c.description || costTypeLabels[c.cost_type]}</span>
              <span className="font-medium">{formatCurrency(c.amount)}</span>
            </div>
          ))}
          <div className="border-t border-border/50 pt-1 flex justify-between text-xs font-semibold">
            <span>Total labour</span>
            <span>{formatCurrency(job.total_labour_cost)}</span>
          </div>
        </div>
      )}

      {/* Actions */}
      {job.status !== "CLOSED" && (
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {canSubmitQuote && (
            <Button size="sm" variant="outline" className="text-xs h-7 px-2.5" onClick={() => setShowQuote(true)}>
              <FileText className="w-3 h-3 mr-1" /> {job.quote_amount ? "Update Quote" : "Submit Quote"}
            </Button>
          )}
          {canApprove && (
            <Button size="sm" variant="outline" className="text-xs h-7 px-2.5 text-green-600 border-green-500/30 hover:bg-green-500/10" onClick={handleApprove} disabled={approving}>
              <CheckCircle2 className="w-3 h-3 mr-1" /> Approve ({job.approval_stage + 1}/3)
            </Button>
          )}
          {canUploadInvoice && (
            <Button size="sm" variant="outline" className="text-xs h-7 px-2.5" onClick={() => setShowInvoice(true)}>
              <Upload className="w-3 h-3 mr-1" /> Upload Invoice
            </Button>
          )}
          {canClose && (
            <button
              onClick={handleClose}
              disabled={closing}
              className="text-xs px-2.5 h-7 rounded-md border border-border hover:bg-green-500/10 hover:text-green-600 hover:border-green-500/30 transition-colors"
            >
              ✓ Close Job
            </button>
          )}
        </div>
      )}

      {showQuote && <SubmitQuoteModal job={job} onClose={() => setShowQuote(false)} onSubmitted={j => { onUpdated(j); setShowQuote(false); }} />}
      {showInvoice && <UploadInvoiceModal job={job} onClose={() => setShowInvoice(false)} onUploaded={j => { onUpdated(j); setShowInvoice(false); }} />}
    </div>
  );
}


// ── Main component ────────────────────────────────────────────────────────────

interface SiteVehiclesProps {
  siteId: string;
  projectId: string | null;
  sites: Site[];
  isViewOnly?: boolean;
}

export function SiteVehicles({ siteId, projectId, sites, isViewOnly = false }: SiteVehiclesProps) {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [costs, setCosts] = useState<Record<string, VehicleCost[]>>({});
  const [repairs, setRepairs] = useState<Record<string, RepairJob[]>>({});
  const [fuelLogs, setFuelLogs] = useState<Record<string, FuelLog[]>>({});
  const [fuelIssues, setFuelIssues] = useState<Record<string, FuelIssue[]>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Record<string, "details" | "costs" | "fuel" | "repairs">>({});
  const [error, setError] = useState("");
  const [newRepairFor, setNewRepairFor] = useState<Vehicle | null>(null);
  const [transferFor, setTransferFor] = useState<Vehicle | null>(null);
  const [logCostFor, setLogCostFor] = useState<Vehicle | null>(null);
  const loadVehicles = () => {
    setLoading(true);
    vehiclesApi.list(undefined, siteId)
      .then(setVehicles)
      .catch(() => setError("Failed to load vehicles."))
      .finally(() => setLoading(false));
  };

  const loadCosts = async (vehicleId: string) => {
    const data = await vehiclesApi.listCosts(vehicleId).catch(() => []);
    setCosts(prev => ({ ...prev, [vehicleId]: data }));
  };

  const loadRepairs = async (vehicleId: string) => {
    const data = await vehiclesApi.listRepairs(vehicleId).catch(() => []);
    setRepairs(prev => ({ ...prev, [vehicleId]: data }));
  };

  const loadFuelLogs = async (vehicleId: string) => {
    if (!projectId) { setFuelLogs(prev => ({ ...prev, [vehicleId]: [] })); return; }
    const logs = await fuelApi.list(projectId, { site_id: siteId }).catch(() => []);
    const vLogs = logs.filter(l => l.vehicle_id === vehicleId);
    setFuelLogs(prev => ({ ...prev, [vehicleId]: vLogs }));
  };

  // Canonical fills (Fuel Management) — the FuelLog above is legacy/frozen
  // once a project cuts over; both are shown together, clearly labelled,
  // so fill history never appears to silently stop.
  const loadFuelIssues = async (vehicleId: string) => {
    if (!projectId) { setFuelIssues(prev => ({ ...prev, [vehicleId]: [] })); return; }
    const issues = await fuelManagementApi.issues(projectId, { vehicle_id: vehicleId }).catch(() => []);
    setFuelIssues(prev => ({ ...prev, [vehicleId]: issues }));
  };

  const toggleExpand = (id: string) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    loadCosts(id);
    loadRepairs(id);
    loadFuelLogs(id);
    loadFuelIssues(id);
    if (!activeTab[id]) setActiveTab(prev => ({ ...prev, [id]: "details" }));
  };

  useEffect(() => { loadVehicles(); }, [siteId]);

  return (
    <div className="space-y-3 animate-fade-in">
      {/* Vehicle list header */}
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Site Vehicles ({loading ? "…" : vehicles.length})
        </p>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">{error}</div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 rounded-xl" />)}
        </div>
      ) : vehicles.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-8 text-center">
          <Car className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No vehicles assigned to this site.</p>
          <p className="text-xs text-muted-foreground mt-1">The office can assign vehicles from the Vehicles page.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {vehicles.map(v => (
            <div key={v.id} className="bg-card border border-border rounded-xl overflow-hidden">
              {/* Vehicle row */}
              <div
                className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
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
                    <p className="font-semibold text-sm">{v.name}</p>
                    {v.status === "MAINTENANCE" && <Badge variant="secondary" className="text-xs bg-amber-500/10 text-amber-600">Maintenance</Badge>}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{v.registration} · {vehicleTypeLabels[v.vehicle_type]}</span>
                    {v.uses_hours && v.current_hours_reading != null && (
                      <span className="flex items-center gap-0.5">
                        <Clock className="w-3 h-3" /> {v.current_hours_reading.toLocaleString()} hrs
                      </span>
                    )}
                    {!v.uses_hours && v.current_odometer_km != null && (
                      <span className="flex items-center gap-0.5">
                        <Gauge className="w-3 h-3" /> {v.current_odometer_km.toLocaleString()} km
                      </span>
                    )}
                  </div>
                </div>
                {!isViewOnly && (
                  <Button
                    size="sm" variant="outline"
                    className="shrink-0 text-xs"
                    onClick={e => { e.stopPropagation(); setTransferFor(v); }}
                    title="Request transfer to another site"
                  >
                    <ArrowRightLeft className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>

              {/* Expanded panel */}
              {expanded === v.id && (
                <div className="border-t border-border bg-muted/20">
                  {/* Tabs */}
                  <div className="flex border-b border-border/50">
                    {(["details", "costs", "fuel", "repairs"] as const).map(tab => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(prev => ({ ...prev, [v.id]: tab }))}
                        className={cn(
                          "px-4 py-2 text-xs font-medium transition-colors flex items-center gap-1.5",
                          (activeTab[v.id] ?? "details") === tab
                            ? "border-b-2 border-primary text-primary"
                            : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        {tab === "details" ? <Car className="w-3 h-3" />
                          : tab === "costs" ? <Wrench className="w-3 h-3" />
                          : tab === "fuel" ? <Droplet className="w-3 h-3" />
                          : <ClipboardList className="w-3 h-3" />}
                        {tab === "details" ? "Details"
                          : tab === "costs" ? `Costs (${costs[v.id]?.length ?? 0})`
                          : tab === "fuel" ? `Fuel (${(fuelLogs[v.id]?.length ?? 0) + (fuelIssues[v.id]?.length ?? 0)})`
                          : `Repairs (${repairs[v.id]?.length ?? 0})`}
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
                        {v.vin_number && <div className="col-span-2"><span className="text-muted-foreground">VIN: </span><span className="font-medium font-mono">{v.vin_number}</span></div>}
                        {v.fuel_type && <div><span className="text-muted-foreground">Fuel: </span><span className="font-medium">{fuelTypeLabels[v.fuel_type]}</span></div>}
                        {v.tank_capacity_l != null && <div><span className="text-muted-foreground">Tank: </span><span className="font-medium">{v.tank_capacity_l} L</span></div>}
                        {v.uses_hours ? (
                          v.current_hours_reading != null && <div className="col-span-2">
                            <span className="text-muted-foreground">Hours: </span>
                            <span className="font-medium">{v.current_hours_reading.toLocaleString()} hrs</span>
                          </div>
                        ) : (
                          v.current_odometer_km != null && <div>
                            <span className="text-muted-foreground">Odometer: </span>
                            <span className="font-medium">{v.current_odometer_km.toLocaleString()} km</span>
                          </div>
                        )}
                        {v.last_service_date && <div><span className="text-muted-foreground">Last service: </span><span className="font-medium">{formatDate(v.last_service_date)}</span></div>}
                        {v.next_service_date && <div><span className="text-muted-foreground">Next service: </span><span className="font-medium">{formatDate(v.next_service_date)}</span></div>}
                      </div>
                    </div>
                  )}

                  {/* Costs tab */}
                  {(activeTab[v.id] ?? "details") === "costs" && (
                    <div className="px-4 py-3 space-y-2">
                      {!isViewOnly && (
                        <div className="flex justify-end">
                          <Button size="sm" variant="outline" onClick={() => setLogCostFor(v)}>
                            <Plus className="w-3.5 h-3.5 mr-1" /> Log Cost
                          </Button>
                        </div>
                      )}
                      {costs[v.id]?.length === 0 ? (
                        <p className="text-xs text-muted-foreground">No costs logged yet.</p>
                      ) : costs[v.id]?.length > 0 ? (
                        <>
                          <div className="flex gap-4 text-xs text-muted-foreground pb-1 border-b border-border/50">
                            <span>Total: <strong className="text-foreground">{formatCurrency(costs[v.id].reduce((s, c) => s + c.amount, 0))}</strong></span>
                          </div>
                          {costs[v.id].slice(0, 10).map(cost => (
                            <div key={cost.id} className="flex items-center justify-between text-xs">
                              <div className="flex items-center gap-2">
                                <Wrench className="w-3.5 h-3.5 text-muted-foreground" />
                                <span className="text-muted-foreground">{costTypeLabels[cost.cost_type]}</span>
                                {cost.description && <span>— {cost.description}</span>}
                              </div>
                              <div className="flex items-center gap-3">
                                <span className="font-medium">{formatCurrency(cost.amount)}</span>
                                <span className="text-muted-foreground">{cost.cost_date}</span>
                              </div>
                            </div>
                          ))}
                        </>
                      ) : null}
                    </div>
                  )}

                  {/* Fuel tab */}
                  {(activeTab[v.id] ?? "details") === "fuel" && (
                    <div className="px-4 py-3 space-y-2">
                      {!fuelLogs[v.id] || !fuelIssues[v.id] ? (
                        <p className="text-xs text-muted-foreground">Loading…</p>
                      ) : (() => {
                        const timeline = buildFuelTimeline(v, fuelLogs[v.id], fuelIssues[v.id]);
                        if (timeline.length === 0) {
                          return <p className="text-xs text-muted-foreground">No fuel fills recorded for this vehicle at this site.</p>;
                        }
                        const totalLitres = timeline.reduce((s, e) => s + e.litres, 0);
                        const latest = timeline[0];
                        const latestIssue = fuelIssues[v.id].find(i => !i.is_reversed);
                        return (
                          <>
                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground pb-1 border-b border-border/50">
                              <span>Total: <strong className="text-foreground">{totalLitres.toFixed(1)} L</strong></span>
                              <span>{timeline.length} entries</span>
                              <span>Latest: <strong className="text-foreground">{new Date(latest.date).toLocaleDateString("en-ZA")}</strong></span>
                              {latestIssue?.estimated_remaining_litres != null && (
                                <span>Est. remaining: <strong className="text-foreground">{latestIssue.estimated_remaining_litres.toFixed(1)} L</strong></span>
                              )}
                            </div>
                            {timeline.slice(0, 10).map(entry => (
                              <div key={entry.key} className={cn(
                                "flex items-start justify-between text-xs rounded-lg px-2 py-1.5",
                                entry.anomaly && "bg-amber-500/5",
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
                                    {entry.anomaly && (
                                      <Badge className="text-[10px] px-1.5 py-0 bg-amber-500/15 text-amber-700 border-amber-500/30">Review required</Badge>
                                    )}
                                  </div>
                                  <div className="text-muted-foreground pl-5 flex flex-wrap gap-2">
                                    {v.uses_hours
                                      ? entry.hours != null && <span>⏱ {entry.hours.toLocaleString()} hrs</span>
                                      : entry.odometer != null && <span>📍 {entry.odometer.toLocaleString()} km</span>}
                                    {entry.consumption && <span>{entry.consumption}</span>}
                                    {entry.evidenceCount > 0 && <span>📎 {entry.evidenceCount} evidence file(s)</span>}
                                    {entry.photoUrl && <a href={entry.photoUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">📷 Photo</a>}
                                  </div>
                                  {entry.anomaly && entry.anomalyReason && (
                                    <p className="text-amber-700 pl-5">{entry.anomalyReason}</p>
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

                  {/* Repairs tab */}
                  {(activeTab[v.id] ?? "details") === "repairs" && (
                    <div className="px-4 py-3 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">{repairs[v.id]?.length ?? 0} repair job(s)</span>
                        {!isViewOnly && (
                          <Button size="sm" variant="outline" onClick={() => setNewRepairFor(v)}>
                            <Plus className="w-3.5 h-3.5 mr-1" /> Report Issue
                          </Button>
                        )}
                      </div>
                      {!repairs[v.id] ? (
                        <p className="text-xs text-muted-foreground">Loading…</p>
                      ) : repairs[v.id].length === 0 ? (
                        <p className="text-xs text-muted-foreground">No repair jobs yet.</p>
                      ) : (
                        <div className="space-y-3">
                          {repairs[v.id].map(job => (
                            <RepairJobCard
                              key={job.id}
                              job={job}
                              vehicle={v}
                              isViewOnly={isViewOnly}
                              onUpdated={updated => {
                                setRepairs(prev => ({
                                  ...prev,
                                  [v.id]: (prev[v.id] ?? []).map(j => j.id === updated.id ? updated : j),
                                }));
                              }}
                            />
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

      {/* New repair job modal */}
      {newRepairFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
          <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
            <h2 className="text-base font-semibold mb-1">Report Repair Issue</h2>
            <p className="text-sm text-muted-foreground mb-4">{newRepairFor.name} ({newRepairFor.registration})</p>
            <NewRepairJobForm
              vehicle={newRepairFor}
              onClose={() => setNewRepairFor(null)}
              onCreated={job => {
                setRepairs(prev => ({
                  ...prev,
                  [newRepairFor.id]: [job, ...(prev[newRepairFor.id] ?? [])],
                }));
                setNewRepairFor(null);
                // Auto-open repairs tab
                setExpanded(newRepairFor.id);
                setActiveTab(prev => ({ ...prev, [newRepairFor.id]: "repairs" }));
              }}
            />
          </div>
        </div>
      )}

      {/* Transfer request modal */}
      {transferFor && (
        <RequestTransferModal
          vehicle={transferFor}
          siteId={siteId}
          sites={sites}
          onClose={() => setTransferFor(null)}
          onRequested={() => { setTransferFor(null); }}
        />
      )}

      {/* Log cost modal (standalone) */}
      {logCostFor && (
        <LogCostModal
          vehicle={logCostFor}
          onClose={() => setLogCostFor(null)}
          onLogged={() => {
            loadCosts(logCostFor.id);
            setLogCostFor(null);
          }}
        />
      )}

    </div>
  );
}

// ── Small modals reused from VehiclesPage pattern ─────────────────────────────

function NewRepairJobForm({ vehicle, onClose, onCreated }: { vehicle: Vehicle; onClose: () => void; onCreated: (j: RepairJob) => void }) {
  const [form, setForm] = useState<RepairJobCreate>({ title: "", date_opened: new Date().toISOString().split("T")[0] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) { setError("Title required."); return; }
    setLoading(true);
    try {
      const job = await vehiclesApi.createRepair(vehicle.id, form);
      onCreated(job);
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed.");
    } finally { setLoading(false); }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="space-y-2">
        <Label>Issue Title *</Label>
        <Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="e.g. Engine oil leak" required />
      </div>
      <div className="space-y-2">
        <Label>Workshop</Label>
        <Input value={form.workshop_name ?? ""} onChange={e => setForm({ ...form, workshop_name: e.target.value || undefined })} placeholder="e.g. ABC Auto" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label>Date Opened</Label>
          <Input type="date" value={form.date_opened} onChange={e => setForm({ ...form, date_opened: e.target.value })} />
        </div>
        <div className="space-y-2">
          <Label>{vehicle.uses_hours ? "Hours Reading" : "Odometer (km)"}</Label>
          <Input type="number" min="0" value={form.odometer_at_repair ?? ""} onChange={e => setForm({ ...form, odometer_at_repair: e.target.value ? parseFloat(e.target.value) : undefined })} />
        </div>
      </div>
      <div className="space-y-2">
        <Label>Description</Label>
        <Input value={form.description ?? ""} onChange={e => setForm({ ...form, description: e.target.value || undefined })} placeholder="Brief description of the issue" />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-2 pt-1">
        <Button type="submit" disabled={loading} className="flex-1">{loading ? "Creating…" : "Create Job"}</Button>
        <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
      </div>
    </form>
  );
}

function LogCostModal({ vehicle, onClose, onLogged }: { vehicle: Vehicle; onClose: () => void; onLogged: () => void }) {
  const t = new Date().toISOString().split("T")[0];
  const [form, setForm] = useState<VehicleCostCreate>({ cost_type: "FUEL", amount: 0, cost_date: t });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await vehiclesApi.logCost(vehicle.id, form);
      onLogged();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed.");
    } finally { setLoading(false); }
  };

  const costTypeOptions: VehicleCostType[] = ["FUEL", "TYRE", "REPAIR", "SERVICE", "LICENCE", "INSURANCE", "OTHER"];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 animate-fade-in">
        <h2 className="text-base font-semibold mb-1">Log Cost</h2>
        <p className="text-sm text-muted-foreground mb-4">{vehicle.name} ({vehicle.registration})</p>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-2">
            <Label>Cost Type</Label>
            <select value={form.cost_type} onChange={e => setForm({ ...form, cost_type: e.target.value as VehicleCostType })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
              {costTypeOptions.map(t => <option key={t} value={t}>{costTypeLabels[t]}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <Label>Amount (R)</Label>
            <Input type="number" min="0" step="0.01" value={form.amount} onChange={e => setForm({ ...form, amount: parseFloat(e.target.value) || 0 })} required />
          </div>
          <div className="space-y-2">
            <Label>Description</Label>
            <Input value={form.description ?? ""} onChange={e => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="space-y-2">
            <Label>Date</Label>
            <Input type="date" value={form.cost_date} onChange={e => setForm({ ...form, cost_date: e.target.value })} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex gap-2">
            <Button type="submit" disabled={loading} className="flex-1">{loading ? "Logging…" : "Log Cost"}</Button>
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
