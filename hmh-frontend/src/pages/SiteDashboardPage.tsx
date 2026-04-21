import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Truck, Package, ClipboardList, Droplet, AlertTriangle,
  RefreshCw, CheckCircle2, Plus, Trash2, Upload, X, LogOut,
} from "lucide-react";
import { TOKEN_KEY, REFRESH_TOKEN_KEY } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/shared/Modal";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { deliveriesApi, type Delivery, type DeliveryItemCreate } from "@/api/deliveries";
import { stockApi, type StockBalance, type StockLedgerEntry, type UsageLogCreate } from "@/api/stock";
import { purchaseOrdersApi, type PurchaseOrder } from "@/api/purchaseOrders";
import { materialRequestsApi } from "@/api/materialRequests";
import { fuelApi, type FuelType, type FuelUsageType, FUEL_TYPE_LABELS, FUEL_USAGE_LABELS } from "@/api/fuel";
import { attachmentsApi } from "@/api/attachments";
import { formatDateTime } from "@/lib/format";

// ─── Shared input style ────────────────────────────────────────────────────────
const inp = "w-full h-11 rounded-lg border border-input bg-background px-3 text-sm";
const tinp = "w-full h-9 rounded-md border border-input bg-background px-2 text-xs";

// ─── Proof upload helper ───────────────────────────────────────────────────────
function ProofPicker({
  file,
  onChange,
}: {
  file: File | null;
  onChange: (f: File | null) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div>
      <label className="text-xs text-muted-foreground block mb-1">Proof photo / file (optional)</label>
      {file ? (
        <div className="flex items-center gap-2 bg-muted/50 rounded-lg px-3 py-2">
          <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
          <span className="text-xs flex-1 truncate">{file.name}</span>
          <button onClick={() => onChange(null)} className="text-muted-foreground hover:text-destructive shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => ref.current?.click()}
          className="flex items-center gap-2 w-full h-11 rounded-lg border border-dashed border-input bg-muted/20 px-3 text-sm text-muted-foreground hover:bg-muted/40 transition-colors"
        >
          <Upload className="w-4 h-4 shrink-0" />
          Tap to attach photo or file
        </button>
      )}
      <input
        ref={ref}
        type="file"
        accept="image/*,application/pdf"
        capture="environment"
        className="hidden"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}

// ─── Receive Delivery Modal ────────────────────────────────────────────────────
interface DraftDeliveryItem {
  description: string;
  qty_received: string;
  qty_expected: string;
  unit: string;
}
const emptyDeliveryItem = (): DraftDeliveryItem => ({
  description: "", qty_received: "", qty_expected: "", unit: "",
});

function ReceiveDeliveryModal({
  open, onClose, projectId, siteId, suppliers, purchaseOrders,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  siteId: string;
  suppliers: Supplier[];
  purchaseOrders: PurchaseOrder[];
  onDone: (d: Delivery) => void;
}) {
  const [supplierId, setSupplierId] = useState(suppliers[0]?.id ?? "");
  const [poId, setPoId] = useState("");
  const [deliveryNum, setDeliveryNum] = useState("");
  const [supplierDN, setSupplierDN] = useState("");
  const [deliveryDate, setDeliveryDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [comments, setComments] = useState("");
  const [items, setItems] = useState<DraftDeliveryItem[]>([emptyDeliveryItem()]);
  const [proof, setProof] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (suppliers.length > 0 && !supplierId) setSupplierId(suppliers[0].id);
  }, [suppliers, supplierId]);

  const updateItem = (idx: number, field: keyof DraftDeliveryItem, val: string) =>
    setItems((prev) => prev.map((it, i) => i === idx ? { ...it, [field]: val } : it));

  const removeItem = (idx: number) =>
    setItems((prev) => prev.filter((_, i) => i !== idx));

  const handleSubmit = async () => {
    if (!supplierId || !siteId) { setError("Select supplier and ensure site is set."); return; }
    const validItems = items.filter((i) => i.description.trim() && i.qty_received);
    if (validItems.length === 0) { setError("Add at least one item."); return; }
    setError(""); setSaving(true);
    try {
      const deliveryItems: DeliveryItemCreate[] = validItems.map((i) => ({
        description: i.description.trim(),
        quantity_received: parseFloat(i.qty_received),
        quantity_expected: i.qty_expected ? parseFloat(i.qty_expected) : null,
        unit: i.unit.trim() || null,
      }));
      const created = await deliveriesApi.create(projectId, {
        supplier_id: supplierId,
        site_id: siteId,
        purchase_order_id: poId || null,
        delivery_number: deliveryNum.trim() || null,
        supplier_delivery_note_number: supplierDN.trim() || null,
        delivery_date: new Date(deliveryDate).toISOString(),
        comments: comments.trim() || null,
        items: deliveryItems,
      });
      if (proof) {
        try {
          await attachmentsApi.upload(proof, "DELIVERY", created.id, "DELIVERY_NOTE");
        } catch {
          // proof upload failure is non-fatal
        }
      }
      onDone(created);
      setSupplierId(suppliers[0]?.id ?? ""); setPoId(""); setDeliveryNum("");
      setSupplierDN(""); setComments(""); setItems([emptyDeliveryItem()]); setProof(null);
      onClose();
    } catch {
      setError("Failed to record delivery. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="Receive Delivery" onClose={onClose} size="md">
      <div className="p-5 space-y-4">
        {error && (
          <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Supplier *</label>
            <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)} className={inp}>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Linked PO</label>
            <select value={poId} onChange={(e) => setPoId(e.target.value)} className={inp}>
              <option value="">— None —</option>
              {purchaseOrders.map((po) => (
                <option key={po.id} value={po.id}>{po.po_number}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Delivery #</label>
            <input type="text" value={deliveryNum} onChange={(e) => setDeliveryNum(e.target.value)}
              className={inp} placeholder="DEL-001" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Date *</label>
            <input type="date" value={deliveryDate} onChange={(e) => setDeliveryDate(e.target.value)} className={inp} />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground block mb-1">Supplier DN #</label>
            <input type="text" value={supplierDN} onChange={(e) => setSupplierDN(e.target.value)} className={inp} />
          </div>
        </div>

        {/* Line items */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold">Items Received *</p>
            <button onClick={() => setItems((p) => [...p, emptyDeliveryItem()])}
              className="flex items-center gap-1 text-xs text-primary">
              <Plus className="w-3.5 h-3.5" /> Add row
            </button>
          </div>
          <div className="space-y-2">
            {items.map((item, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <input type="text" value={item.description}
                  onChange={(e) => updateItem(idx, "description", e.target.value)}
                  placeholder="Description" className={`${tinp} flex-1`} />
                <input type="number" value={item.qty_received}
                  onChange={(e) => updateItem(idx, "qty_received", e.target.value)}
                  placeholder="Rcv" className={`${tinp} w-16`} />
                <input type="number" value={item.qty_expected}
                  onChange={(e) => updateItem(idx, "qty_expected", e.target.value)}
                  placeholder="Exp" className={`${tinp} w-16`} />
                <input type="text" value={item.unit}
                  onChange={(e) => updateItem(idx, "unit", e.target.value)}
                  placeholder="Unit" className={`${tinp} w-14`} />
                {items.length > 1 && (
                  <button onClick={() => removeItem(idx)} className="text-muted-foreground hover:text-destructive shrink-0">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Rcv = received qty · Exp = expected qty</p>
        </div>

        <div>
          <label className="text-xs text-muted-foreground block mb-1">Comments</label>
          <textarea value={comments} onChange={(e) => setComments(e.target.value)} rows={2}
            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm resize-none" />
        </div>

        <ProofPicker file={proof} onChange={setProof} />

        <Button className="w-full h-12 text-base" onClick={handleSubmit} disabled={saving}>
          {saving ? "Recording…" : "Record Delivery"}
        </Button>
      </div>
    </Modal>
  );
}

// ─── Record Usage Modal ────────────────────────────────────────────────────────
function RecordUsageModal({
  open, onClose, projectId, siteId, balances, onDone,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  siteId: string;
  balances: StockBalance[];
  onDone: () => void;
}) {
  const siteBalances = balances.filter((b) => b.site_id === siteId && b.balance > 0);
  const [itemId, setItemId] = useState(siteBalances[0]?.item_id ?? "");
  const [qty, setQty] = useState("");
  const [usedBy, setUsedBy] = useState("");
  const [usageDate, setUsageDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [comments, setComments] = useState("");
  const [proof, setProof] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setItemId(siteBalances[0]?.item_id ?? "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, open]);

  const selected = siteBalances.find((b) => b.item_id === itemId);

  const handleSubmit = async () => {
    if (!itemId || !qty) { setError("Select an item and enter quantity."); return; }
    setError(""); setSaving(true);
    try {
      const body: UsageLogCreate = {
        site_id: siteId,
        item_id: itemId,
        quantity_used: parseFloat(qty),
        used_by_person_name: usedBy.trim() || null,
        usage_date: new Date(usageDate).toISOString(),
        comments: comments.trim() || null,
      };
      const usageLog = await stockApi.recordUsage(projectId, body);
      if (proof) {
        try {
          await attachmentsApi.upload(proof, "USAGE_LOG", usageLog.id, "PROOF");
        } catch {
          // non-fatal
        }
      }
      onDone();
      setQty(""); setUsedBy(""); setComments(""); setProof(null);
      onClose();
    } catch {
      setError("Failed to record usage. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="Record Material Usage" onClose={onClose} size="sm">
      <div className="p-5 space-y-4">
        {error && (
          <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div>
          <label className="text-xs text-muted-foreground block mb-1">Material *</label>
          <select value={itemId} onChange={(e) => setItemId(e.target.value)} className={inp}>
            <option value="">— Select material —</option>
            {siteBalances.map((b) => (
              <option key={b.item_id} value={b.item_id}>
                {b.item_name ?? b.item_id.slice(0, 8)} ({b.balance} {b.item_unit ?? ""})
              </option>
            ))}
          </select>
          {selected && (
            <p className="text-xs text-muted-foreground mt-1">
              Balance: <span className={`font-semibold ${selected.balance < 10 ? "text-warning" : "text-success"}`}>
                {selected.balance} {selected.item_unit ?? ""}
              </span>
            </p>
          )}
          {siteBalances.length === 0 && (
            <p className="text-xs text-warning mt-1">No stock available for this site.</p>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Quantity Used *</label>
            <input type="number" min="0.01" step="any" value={qty}
              onChange={(e) => setQty(e.target.value)} className={inp} placeholder="e.g. 10" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Date *</label>
            <input type="date" value={usageDate} onChange={(e) => setUsageDate(e.target.value)} className={inp} />
          </div>
        </div>

        <div>
          <label className="text-xs text-muted-foreground block mb-1">Used By</label>
          <input type="text" value={usedBy} onChange={(e) => setUsedBy(e.target.value)}
            className={inp} placeholder="Person or team name" />
        </div>

        <div>
          <label className="text-xs text-muted-foreground block mb-1">Comments</label>
          <textarea value={comments} onChange={(e) => setComments(e.target.value)} rows={2}
            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm resize-none" />
        </div>

        <ProofPicker file={proof} onChange={setProof} />

        <Button className="w-full h-12 text-base" onClick={handleSubmit}
          disabled={saving || !itemId || !qty}>
          {saving ? "Recording…" : "Record Usage"}
        </Button>
      </div>
    </Modal>
  );
}

// ─── Request Material Modal ────────────────────────────────────────────────────
interface DraftMRItem { description: string; qty: string; unit: string; notes: string; }
const emptyMRItem = (): DraftMRItem => ({ description: "", qty: "", unit: "", notes: "" });

function RequestMaterialModal({
  open, onClose, projectId, siteId, onDone,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  siteId: string;
  onDone: () => void;
}) {
  const [items, setItems] = useState<DraftMRItem[]>([emptyMRItem()]);
  const [neededBy, setNeededBy] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const updateItem = (idx: number, field: keyof DraftMRItem, val: string) =>
    setItems((prev) => prev.map((it, i) => i === idx ? { ...it, [field]: val } : it));

  const removeItem = (idx: number) =>
    setItems((prev) => prev.filter((_, i) => i !== idx));

  const handleSubmit = async () => {
    const validItems = items.filter((i) => i.description.trim() && i.qty);
    if (validItems.length === 0) { setError("Add at least one item with description and quantity."); return; }
    setError(""); setSaving(true);
    try {
      await materialRequestsApi.create(projectId, {
        site_id: siteId || null,
        needed_by_date: neededBy ? new Date(neededBy).toISOString() : null,
        notes: notes.trim() || null,
        items: validItems.map((i) => ({
          description: i.description.trim(),
          quantity_requested: parseFloat(i.qty),
          unit: i.unit.trim() || null,
          notes: i.notes.trim() || null,
        })),
      });
      setDone(true);
      setTimeout(() => {
        setDone(false);
        setItems([emptyMRItem()]); setNeededBy(""); setNotes("");
        onDone();
        onClose();
      }, 1200);
    } catch {
      setError("Failed to submit request. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="Request Material" onClose={onClose} size="md">
      <div className="p-5 space-y-4">
        {done && (
          <div className="flex items-center gap-2 bg-success/10 border border-success/20 text-success rounded-lg px-3 py-3">
            <CheckCircle2 className="w-5 h-5 shrink-0" />
            <span className="text-sm font-medium">Request submitted successfully!</span>
          </div>
        )}
        {error && (
          <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold">Items Needed *</p>
            <button onClick={() => setItems((p) => [...p, emptyMRItem()])}
              className="flex items-center gap-1 text-xs text-primary">
              <Plus className="w-3.5 h-3.5" /> Add item
            </button>
          </div>
          <div className="space-y-2">
            {items.map((item, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <input type="text" value={item.description}
                  onChange={(e) => updateItem(idx, "description", e.target.value)}
                  placeholder="Material description *" className={`${tinp} flex-1`} />
                <input type="number" value={item.qty}
                  onChange={(e) => updateItem(idx, "qty", e.target.value)}
                  placeholder="Qty *" className={`${tinp} w-16`} />
                <input type="text" value={item.unit}
                  onChange={(e) => updateItem(idx, "unit", e.target.value)}
                  placeholder="Unit" className={`${tinp} w-16`} />
                {items.length > 1 && (
                  <button onClick={() => removeItem(idx)}
                    className="text-muted-foreground hover:text-destructive shrink-0">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Needed By</label>
            <input type="date" value={neededBy} onChange={(e) => setNeededBy(e.target.value)} className={inp} />
          </div>
        </div>

        <div>
          <label className="text-xs text-muted-foreground block mb-1">Notes / Urgency</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm resize-none"
            placeholder="e.g. URGENT — production stalled without this" />
        </div>

        <Button className="w-full h-12 text-base" onClick={handleSubmit} disabled={saving || done}>
          {saving ? "Submitting…" : "Submit Request"}
        </Button>
      </div>
    </Modal>
  );
}

// ─── Log Fuel Modal ────────────────────────────────────────────────────────────
function LogFuelModal({
  open, onClose, projectId, siteId, onDone,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  siteId: string;
  onDone: () => void;
}) {
  const [fuelType, setFuelType] = useState<FuelType>("DIESEL");
  const [usageType, setUsageType] = useState<FuelUsageType>("EQUIPMENT");
  const [litres, setLitres] = useState("");
  const [costPerLitre, setCostPerLitre] = useState("");
  const [equipmentRef, setEquipmentRef] = useState("");
  const [fuelledBy, setFuelledBy] = useState("");
  const [fuelDate, setFuelDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const handleSubmit = async () => {
    if (!litres) { setError("Enter litres."); return; }
    setError(""); setSaving(true);
    try {
      await fuelApi.create(projectId, {
        fuel_type: fuelType,
        usage_type: usageType,
        litres: parseFloat(litres),
        cost_per_litre: costPerLitre ? parseFloat(costPerLitre) : null,
        equipment_ref: equipmentRef.trim() || null,
        fuelled_by: fuelledBy.trim() || null,
        site_id: siteId || null,
        fuel_date: new Date(fuelDate).toISOString(),
        notes: notes.trim() || null,
      });
      setDone(true);
      setTimeout(() => {
        setDone(false);
        setLitres(""); setCostPerLitre(""); setEquipmentRef("");
        setFuelledBy(""); setNotes("");
        onDone();
        onClose();
      }, 1200);
    } catch {
      setError("Failed to log fuel. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="Log Fuel" onClose={onClose} size="sm">
      <div className="p-5 space-y-4">
        {done && (
          <div className="flex items-center gap-2 bg-success/10 border border-success/20 text-success rounded-lg px-3 py-3">
            <CheckCircle2 className="w-5 h-5 shrink-0" />
            <span className="text-sm font-medium">Fuel logged!</span>
          </div>
        )}
        {error && (
          <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Fuel Type</label>
            <select value={fuelType} onChange={(e) => setFuelType(e.target.value as FuelType)} className={inp}>
              {(Object.keys(FUEL_TYPE_LABELS) as FuelType[]).map((t) => (
                <option key={t} value={t}>{FUEL_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Usage Type</label>
            <select value={usageType} onChange={(e) => setUsageType(e.target.value as FuelUsageType)} className={inp}>
              {(Object.keys(FUEL_USAGE_LABELS) as FuelUsageType[]).map((t) => (
                <option key={t} value={t}>{FUEL_USAGE_LABELS[t]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Litres *</label>
            <input type="number" min="0.1" step="0.1" value={litres}
              onChange={(e) => setLitres(e.target.value)} className={inp} placeholder="e.g. 50" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Cost / Litre (R)</label>
            <input type="number" min="0" step="0.01" value={costPerLitre}
              onChange={(e) => setCostPerLitre(e.target.value)} className={inp} placeholder="e.g. 22.50" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Equipment Ref</label>
            <input type="text" value={equipmentRef} onChange={(e) => setEquipmentRef(e.target.value)}
              className={inp} placeholder="TLB-001" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Fuelled By</label>
            <input type="text" value={fuelledBy} onChange={(e) => setFuelledBy(e.target.value)}
              className={inp} placeholder="Name" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Date</label>
            <input type="date" value={fuelDate} onChange={(e) => setFuelDate(e.target.value)} className={inp} />
          </div>
        </div>

        <div>
          <label className="text-xs text-muted-foreground block mb-1">Notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2}
            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm resize-none" />
        </div>

        <Button className="w-full h-12 text-base" onClick={handleSubmit} disabled={saving || done || !litres}>
          {saving ? "Logging…" : "Log Fuel"}
        </Button>
      </div>
    </Modal>
  );
}

// ─── Action Card ───────────────────────────────────────────────────────────────
function ActionCard({
  icon: Icon, label, sublabel, color, onClick,
}: {
  icon: React.ElementType;
  label: string;
  sublabel: string;
  color: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex flex-col items-center justify-center gap-3 p-5 bg-card border border-border rounded-2xl hover:bg-muted/50 active:scale-95 transition-all text-center min-h-[130px] w-full touch-manipulation"
    >
      <div className={`flex items-center justify-center w-14 h-14 rounded-2xl ${color}`}>
        <Icon className="w-7 h-7" />
      </div>
      <div>
        <p className="text-sm font-semibold leading-tight">{label}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5 leading-tight">{sublabel}</p>
      </div>
    </button>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────────
const LAST_PROJECT_KEY = "site_dashboard_project";
const LAST_SITE_KEY = "site_dashboard_site";

export default function SiteDashboardPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [projectId, setProjectId] = useState(() => localStorage.getItem(LAST_PROJECT_KEY) ?? "");
  const [siteId, setSiteId] = useState(() => localStorage.getItem(LAST_SITE_KEY) ?? "");
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [balances, setBalances] = useState<StockBalance[]>([]);
  const [recentDeliveries, setRecentDeliveries] = useState<Delivery[]>([]);
  const [recentUsage, setRecentUsage] = useState<StockLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [modal, setModal] = useState<"delivery" | "usage" | "request" | "fuel" | null>(null);

  const today = new Date().toLocaleDateString("en-ZA", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(LAST_PROJECT_KEY);
    localStorage.removeItem(LAST_SITE_KEY);
    navigate("/site-login", { replace: true });
  };

  // Load projects + suppliers on mount
  useEffect(() => {
    Promise.all([projectsApi.list(1, 100), suppliersApi.list()])
      .then(([projRes, suppRes]) => {
        setProjects(projRes.items);
        setSuppliers(suppRes);
        if (projRes.items.length > 0 && !projectId) {
          setProjectId(projRes.items[0].id);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load sites when project changes
  useEffect(() => {
    if (!projectId) return;
    localStorage.setItem(LAST_PROJECT_KEY, projectId);
    sitesApi.list(projectId).then((s) => {
      setSites(s);
      if (s.length > 0 && (!siteId || !s.find((x) => x.id === siteId))) {
        setSiteId(s[0].id);
      }
    }).catch(() => setSites([]));
    purchaseOrdersApi.list(projectId)
      .then((pos) => setPurchaseOrders(pos.filter((p) => ["APPROVED", "SENT"].includes(p.status))))
      .catch(() => setPurchaseOrders([]));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Persist site selection
  useEffect(() => {
    if (siteId) localStorage.setItem(LAST_SITE_KEY, siteId);
  }, [siteId]);

  const loadSiteData = useCallback(async (pid: string, sid: string) => {
    if (!pid || !sid) return;
    try {
      const [bal, deliveries, ledger] = await Promise.all([
        stockApi.getBalances(pid, sid),
        deliveriesApi.list(pid),
        stockApi.getLedger(pid, { site_id: sid, limit: 20 }),
      ]);
      setBalances(bal);
      setRecentDeliveries(
        deliveries
          .filter((d) => d.site_id === sid)
          .sort((a, b) => new Date(b.delivery_date).getTime() - new Date(a.delivery_date).getTime())
          .slice(0, 3)
      );
      setRecentUsage(
        ledger
          .filter((e) => e.movement_type === "USAGE")
          .slice(0, 3)
      );
    } catch {
      // silently fail — offline resilience
    }
  }, []);

  useEffect(() => {
    loadSiteData(projectId, siteId);
  }, [projectId, siteId, loadSiteData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadSiteData(projectId, siteId);
    setRefreshing(false);
  };

  const lowStockItems = balances.filter((b) => b.balance <= 10);
  const currentProject = projects.find((p) => p.id === projectId);
  const currentSite = sites.find((s) => s.id === siteId);

  const supplierMap = Object.fromEntries(suppliers.map((s) => [s.id, s.name]));

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <RefreshCw className="w-6 h-6 animate-spin" />
          <p className="text-sm">Loading site dashboard…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background pb-8">
      {/* ── Header ── */}
      <div className="bg-card border-b border-border px-4 pt-5 pb-4 sticky top-0 z-10">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold leading-tight">Site Dashboard</h1>
              <span className="text-[10px] font-semibold bg-warning/15 text-warning px-2 py-0.5 rounded-full uppercase tracking-wide">
                Site
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">{today}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground bg-muted/50 px-3 py-2 rounded-lg active:scale-95 transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-destructive bg-muted/50 px-3 py-2 rounded-lg active:scale-95 transition-all"
              title="Sign out"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Project + Site selectors */}
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="text-[10px] text-muted-foreground block mb-1 uppercase tracking-wide">Project</label>
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className="w-full h-10 rounded-lg border border-input bg-background px-3 text-sm font-medium"
            >
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="flex-1">
            <label className="text-[10px] text-muted-foreground block mb-1 uppercase tracking-wide">Site</label>
            <select
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              className="w-full h-10 rounded-lg border border-input bg-background px-3 text-sm font-medium"
            >
              {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
        </div>

        {currentProject && currentSite && (
          <p className="text-[11px] text-muted-foreground mt-2 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-success inline-block" />
            {currentProject.name} → {currentSite.name}
          </p>
        )}
      </div>

      <div className="px-4 pt-5 space-y-6 max-w-lg mx-auto">
        {/* ── Low stock alert banner ── */}
        {lowStockItems.length > 0 && (
          <div className="bg-warning/10 border border-warning/30 rounded-xl px-4 py-3 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-warning">Low Stock Alert</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {lowStockItems.length} item{lowStockItems.length > 1 ? "s" : ""} running low on this site
              </p>
            </div>
          </div>
        )}

        {/* ── 4 Action Cards ── */}
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Quick Actions</p>
          <div className="grid grid-cols-2 gap-3">
            <ActionCard
              icon={Truck}
              label="Receive Delivery"
              sublabel="Record incoming materials"
              color="bg-primary/15 text-primary"
              onClick={() => setModal("delivery")}
            />
            <ActionCard
              icon={Package}
              label="Record Usage"
              sublabel="Log material consumption"
              color="bg-success/15 text-success"
              onClick={() => setModal("usage")}
            />
            <ActionCard
              icon={ClipboardList}
              label="Request Material"
              sublabel="Submit stock request"
              color="bg-warning/15 text-warning"
              onClick={() => setModal("request")}
            />
            <ActionCard
              icon={Droplet}
              label="Log Fuel"
              sublabel="Record fuel usage"
              color="bg-blue-500/15 text-blue-500"
              onClick={() => setModal("fuel")}
            />
          </div>
        </div>

        {/* ── Low stock items list ── */}
        {lowStockItems.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Low Stock Items</p>
            <div className="bg-card border border-border rounded-xl divide-y divide-border overflow-hidden">
              {lowStockItems.slice(0, 5).map((b) => (
                <div key={`${b.item_id}-${b.site_id}`} className="flex items-center justify-between px-4 py-3">
                  <p className="text-sm font-medium truncate">{b.item_name ?? b.item_id.slice(0, 8)}</p>
                  <span className={`text-sm font-bold ml-2 shrink-0 ${b.balance <= 0 ? "text-destructive" : "text-warning"}`}>
                    {b.balance} {b.item_unit ?? ""}
                  </span>
                </div>
              ))}
              {lowStockItems.length > 5 && (
                <div className="px-4 py-2 text-xs text-muted-foreground text-center">
                  +{lowStockItems.length - 5} more items low
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Recent Deliveries ── */}
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Recent Deliveries</p>
          {recentDeliveries.length === 0 ? (
            <div className="bg-card border border-border rounded-xl px-4 py-6 text-center text-sm text-muted-foreground">
              No deliveries recorded yet for this site.
            </div>
          ) : (
            <div className="bg-card border border-border rounded-xl divide-y divide-border overflow-hidden">
              {recentDeliveries.map((d) => (
                <div key={d.id} className="flex items-start justify-between px-4 py-3 gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">
                      {supplierMap[d.supplier_id] ?? "Unknown supplier"}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {d.delivery_number ?? d.id.slice(0, 8)} · {d.items.length} item{d.items.length !== 1 ? "s" : ""}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <Badge variant={
                      d.delivery_status === "MATCHED" ? "success" :
                      d.delivery_status === "DISPUTED" ? "destructive" : "secondary"
                    }>
                      {d.delivery_status}
                    </Badge>
                    <p className="text-[10px] text-muted-foreground mt-1">{formatDateTime(d.delivery_date)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── Recent Usage ── */}
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Recent Usage</p>
          {recentUsage.length === 0 ? (
            <div className="bg-card border border-border rounded-xl px-4 py-6 text-center text-sm text-muted-foreground">
              No usage recorded yet for this site.
            </div>
          ) : (
            <div className="bg-card border border-border rounded-xl divide-y divide-border overflow-hidden">
              {recentUsage.map((e) => (
                <div key={e.id} className="flex items-start justify-between px-4 py-3 gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium font-mono truncate">{e.item_id.slice(0, 8)}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{formatDateTime(e.movement_date)}</p>
                  </div>
                  <p className="text-sm font-bold text-destructive shrink-0">
                    −{e.quantity_out.toLocaleString("en-ZA")} {e.unit ?? ""}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Modals ── */}
      {projectId && siteId && (
        <>
          <ReceiveDeliveryModal
            open={modal === "delivery"}
            onClose={() => setModal(null)}
            projectId={projectId}
            siteId={siteId}
            suppliers={suppliers}
            purchaseOrders={purchaseOrders}
            onDone={(d) => {
              setRecentDeliveries((prev) => [d, ...prev].slice(0, 3));
            }}
          />
          <RecordUsageModal
            open={modal === "usage"}
            onClose={() => setModal(null)}
            projectId={projectId}
            siteId={siteId}
            balances={balances}
            onDone={() => loadSiteData(projectId, siteId)}
          />
          <RequestMaterialModal
            open={modal === "request"}
            onClose={() => setModal(null)}
            projectId={projectId}
            siteId={siteId}
            onDone={() => {}}
          />
          <LogFuelModal
            open={modal === "fuel"}
            onClose={() => setModal(null)}
            projectId={projectId}
            siteId={siteId}
            onDone={() => {}}
          />
        </>
      )}
    </div>
  );
}
