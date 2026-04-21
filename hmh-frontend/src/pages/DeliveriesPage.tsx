import { useEffect, useState } from "react";
import { Plus, Truck, CheckCircle2, AlertCircle, Package, Trash2, RefreshCw, Paperclip, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { deliveriesApi, type Delivery, type DeliveryItemCreate } from "@/api/deliveries";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { purchaseOrdersApi, type PurchaseOrder } from "@/api/purchaseOrders";
import { attachmentsApi, type Attachment } from "@/api/attachments";
import { formatDateTime } from "@/lib/format";

const deliveryStatusVariant: Record<string, "success" | "default" | "destructive" | "secondary"> = {
  MATCHED: "success",
  RECEIVED: "default",
  DISPUTED: "destructive",
  PENDING: "secondary",
};

const deliveryStatusLabel: Record<string, string> = {
  MATCHED: "Matched",
  RECEIVED: "Received",
  DISPUTED: "Disputed",
  PENDING: "Pending",
};

// ─── Record Delivery Modal ─────────────────────────────────────────────────────
interface DraftItem {
  description: string;
  quantity_received: string;
  quantity_expected: string;
  unit: string;
}

const emptyItem = (): DraftItem => ({ description: "", quantity_received: "", quantity_expected: "", unit: "" });

function RecordDeliveryModal({
  open,
  onClose,
  projects,
  suppliers,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  projects: Project[];
  suppliers: Supplier[];
  onSubmit: (projectId: string, data: {
    supplier_id: string;
    site_id: string;
    purchase_order_id: string;
    delivery_number: string;
    supplier_dn: string;
    delivery_date: string;
    comments: string;
    items: DraftItem[];
  }) => Promise<void>;
}) {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [sites, setSites] = useState<Site[]>([]);
  const [siteId, setSiteId] = useState("");
  const [supplierId, setSupplierId] = useState(suppliers[0]?.id ?? "");
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [poId, setPoId] = useState("");
  const [deliveryNumber, setDeliveryNumber] = useState("");
  const [supplierDN, setSupplierDN] = useState("");
  const [deliveryDate, setDeliveryDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [comments, setComments] = useState("");
  const [items, setItems] = useState<DraftItem[]>([emptyItem()]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (projects.length > 0 && !projectId) setProjectId(projects[0].id);
  }, [projects, projectId]);

  useEffect(() => {
    if (suppliers.length > 0 && !supplierId) setSupplierId(suppliers[0].id);
  }, [suppliers, supplierId]);

  useEffect(() => {
    if (!projectId) return;
    sitesApi.list(projectId).then((s) => {
      setSites(s);
      setSiteId(s[0]?.id ?? "");
    }).catch(() => setSites([]));
    purchaseOrdersApi.list(projectId).then((pos) => {
      setPurchaseOrders(pos.filter((p) => ["APPROVED", "SENT"].includes(p.status)));
    }).catch(() => setPurchaseOrders([]));
  }, [projectId]);

  const updateItem = (idx: number, field: keyof DraftItem, val: string) => {
    setItems((prev) => prev.map((it, i) => i === idx ? { ...it, [field]: val } : it));
  };

  const removeItem = (idx: number) => {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = async () => {
    if (!projectId || !supplierId || !siteId) return;
    const validItems = items.filter((it) => it.description.trim() && it.quantity_received);
    if (validItems.length === 0) return;
    setSaving(true);
    try {
      await onSubmit(projectId, {
        supplier_id: supplierId,
        site_id: siteId,
        purchase_order_id: poId,
        delivery_number: deliveryNumber,
        supplier_dn: supplierDN,
        delivery_date: deliveryDate,
        comments,
        items: validItems,
      });
      setDeliveryNumber(""); setSupplierDN(""); setComments(""); setPoId("");
      setItems([emptyItem()]);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="Record Delivery" onClose={onClose} size="lg">
      <div className="p-6 space-y-5">
        {/* Header fields */}
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
            <label className="text-xs text-muted-foreground block mb-1">Site *</label>
            <select
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— Select site —</option>
              {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Supplier *</label>
            <select
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Linked PO (optional)</label>
            <select
              value={poId}
              onChange={(e) => setPoId(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— No PO —</option>
              {purchaseOrders.map((po) => (
                <option key={po.id} value={po.id}>{po.po_number}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Delivery Number</label>
            <input
              type="text"
              value={deliveryNumber}
              onChange={(e) => setDeliveryNumber(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="e.g. DEL-2024-001"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Supplier Delivery Note #</label>
            <input
              type="text"
              value={supplierDN}
              onChange={(e) => setSupplierDN(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Delivery Date *</label>
            <input
              type="date"
              value={deliveryDate}
              onChange={(e) => setDeliveryDate(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Comments</label>
            <input
              type="text"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
        </div>

        {/* Line items */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-medium">Line Items *</p>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => setItems((prev) => [...prev, emptyItem()])}
            >
              <Plus className="w-3 h-3 mr-1" />
              Add Row
            </Button>
          </div>
          <div className="border border-border rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-3 py-2 font-medium">Description *</th>
                  <th className="text-right px-3 py-2 font-medium w-24">Received *</th>
                  <th className="text-right px-3 py-2 font-medium w-24">Expected</th>
                  <th className="text-right px-3 py-2 font-medium w-20">Unit</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => (
                  <tr key={idx} className="border-t border-border/50">
                    <td className="px-3 py-1.5">
                      <input
                        type="text"
                        value={item.description}
                        onChange={(e) => updateItem(idx, "description", e.target.value)}
                        placeholder="Material description"
                        className="w-full h-7 rounded border border-input bg-background px-2 text-xs"
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <input
                        type="number"
                        min="0"
                        step="any"
                        value={item.quantity_received}
                        onChange={(e) => updateItem(idx, "quantity_received", e.target.value)}
                        className="w-full h-7 rounded border border-input bg-background px-2 text-xs text-right"
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <input
                        type="number"
                        min="0"
                        step="any"
                        value={item.quantity_expected}
                        onChange={(e) => updateItem(idx, "quantity_expected", e.target.value)}
                        className="w-full h-7 rounded border border-input bg-background px-2 text-xs text-right"
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <input
                        type="text"
                        value={item.unit}
                        onChange={(e) => updateItem(idx, "unit", e.target.value)}
                        placeholder="e.g. m³"
                        className="w-full h-7 rounded border border-input bg-background px-2 text-xs"
                      />
                    </td>
                    <td className="px-2">
                      {items.length > 1 && (
                        <button
                          onClick={() => removeItem(idx)}
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={saving || !projectId || !supplierId || !siteId || items.every((i) => !i.description.trim() || !i.quantity_received)}
          >
            {saving ? "Recording…" : "Record Delivery"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────────
export default function DeliveriesPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [selectedDelivery, setSelectedDelivery] = useState<Delivery | null>(null);
  const [deliveryAttachments, setDeliveryAttachments] = useState<Attachment[]>([]);
  const [loadingAttachments, setLoadingAttachments] = useState(false);
  const [showRecord, setShowRecord] = useState(false);

  useEffect(() => {
    Promise.all([projectsApi.list(1, 100), suppliersApi.list()])
      .then(([projRes, suppRes]) => {
        setProjects(projRes.items);
        setSuppliers(suppRes);
        if (projRes.items.length > 0) setSelectedProjectId(projRes.items[0].id);
      })
      .catch(() => {})
      .finally(() => setLoadingProjects(false));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setLoading(true);
    deliveriesApi
      .list(selectedProjectId)
      .then(setDeliveries)
      .catch(() => setDeliveries([]))
      .finally(() => setLoading(false));
  }, [selectedProjectId]);

  // Fetch attachments when a delivery is opened
  useEffect(() => {
    if (!selectedDelivery) { setDeliveryAttachments([]); return; }
    setLoadingAttachments(true);
    attachmentsApi
      .listByEntity("DELIVERY", selectedDelivery.id)
      .then(setDeliveryAttachments)
      .catch(() => setDeliveryAttachments([]))
      .finally(() => setLoadingAttachments(false));
  }, [selectedDelivery]);

  const refreshDeliveries = async () => {
    if (!selectedProjectId) return;
    setRefreshing(true);
    deliveriesApi
      .list(selectedProjectId)
      .then(setDeliveries)
      .catch(() => {})
      .finally(() => setRefreshing(false));
  };

  const supplierMap = Object.fromEntries(suppliers.map((s) => [s.id, s.name]));

  const matchedCount = deliveries.filter((d) => d.delivery_status === "MATCHED").length;
  const receivedCount = deliveries.filter((d) => d.delivery_status === "RECEIVED").length;
  const noPOCount = deliveries.filter((d) => !d.purchase_order_id).length;

  const handleRecord = async (
    projectId: string,
    data: {
      supplier_id: string;
      site_id: string;
      purchase_order_id: string;
      delivery_number: string;
      supplier_dn: string;
      delivery_date: string;
      comments: string;
      items: { description: string; quantity_received: string; quantity_expected: string; unit: string }[];
    }
  ) => {
    const deliveryItems: DeliveryItemCreate[] = data.items
      .filter((i) => i.description.trim() && i.quantity_received)
      .map((i) => ({
        description: i.description.trim(),
        quantity_received: parseFloat(i.quantity_received),
        quantity_expected: i.quantity_expected ? parseFloat(i.quantity_expected) : null,
        unit: i.unit.trim() || null,
      }));

    const created = await deliveriesApi.create(projectId, {
      supplier_id: data.supplier_id,
      site_id: data.site_id,
      purchase_order_id: data.purchase_order_id || null,
      delivery_number: data.delivery_number || null,
      supplier_delivery_note_number: data.supplier_dn || null,
      delivery_date: data.delivery_date ? new Date(data.delivery_date).toISOString() : null,
      comments: data.comments || null,
      items: deliveryItems,
    });
    if (projectId === selectedProjectId) {
      setDeliveries((prev) => [created, ...prev]);
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
        title="Deliveries"
        description="Record and verify incoming material deliveries on site."
        meta={`${deliveries.length} deliveries`}
        actions={
          selectedProjectId ? (
            <Button size="sm" onClick={() => setShowRecord(true)}>
              <Plus className="w-4 h-4" />
              Record Delivery
            </Button>
          ) : undefined
        }
      />

      {/* Project selector + refresh */}
      <div className="flex items-end gap-3">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Project</label>
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[240px]"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={refreshDeliveries}
          disabled={refreshing}
          title="Refresh deliveries"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard title="Matched to PO" value={matchedCount} icon={CheckCircle2} color="bg-success/10 text-success" />
        <StatCard title="Received (Unmatched)" value={receivedCount} icon={Package} color="bg-primary/10 text-primary" />
        <StatCard title="Without PO" value={noPOCount} icon={AlertCircle} color="bg-warning/10 text-warning" />
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {deliveries.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">
              No deliveries for this project.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Delivery #</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Supplier</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Linked PO</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                  <th className="text-right px-4 py-3 font-medium text-muted-foreground">Items</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {deliveries.map((del) => (
                  <tr key={del.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-mono font-medium text-xs">
                      {del.delivery_number ?? <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {supplierMap[del.supplier_id] ?? del.supplier_id.slice(0, 8)}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {del.purchase_order_id ? (
                        <span className="font-mono text-primary">{del.purchase_order_id.slice(0, 8)}</span>
                      ) : (
                        <span className="text-warning font-medium">No PO</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={deliveryStatusVariant[del.delivery_status] ?? "secondary"}>
                        {deliveryStatusLabel[del.delivery_status] ?? del.delivery_status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{del.items.length}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(del.delivery_date)}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setSelectedDelivery(del)}
                        className="text-xs text-primary hover:underline"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Detail Modal */}
      {selectedDelivery && (
        <Modal
          open
          title={`Delivery ${selectedDelivery.delivery_number ?? selectedDelivery.id.slice(0, 8)}`}
          onClose={() => setSelectedDelivery(null)}
          size="md"
        >
          <div className="p-6 space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-xs text-muted-foreground">Delivery Number</p>
                <p className="font-mono font-medium mt-0.5">
                  {selectedDelivery.delivery_number ?? "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Status</p>
                <div className="mt-1">
                  <Badge variant={deliveryStatusVariant[selectedDelivery.delivery_status] ?? "secondary"}>
                    {deliveryStatusLabel[selectedDelivery.delivery_status] ?? selectedDelivery.delivery_status}
                  </Badge>
                </div>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Supplier</p>
                <p className="font-medium mt-0.5">
                  {supplierMap[selectedDelivery.supplier_id] ?? selectedDelivery.supplier_id.slice(0, 8)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Date</p>
                <p className="mt-0.5">{formatDateTime(selectedDelivery.delivery_date)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Supplier DN</p>
                <p className="font-mono mt-0.5">{selectedDelivery.supplier_delivery_note_number ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Linked PO</p>
                <p className="font-mono mt-0.5">{selectedDelivery.purchase_order_id ?? "None"}</p>
              </div>
            </div>

            {selectedDelivery.items.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">Line Items</p>
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border bg-muted/50">
                        <th className="text-left px-3 py-2 font-medium">Description</th>
                        <th className="text-right px-3 py-2 font-medium">Expected</th>
                        <th className="text-right px-3 py-2 font-medium">Received</th>
                        <th className="text-right px-3 py-2 font-medium">Unit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedDelivery.items.map((item) => {
                        const hasDiscrepancy =
                          item.quantity_expected != null &&
                          item.quantity_received !== item.quantity_expected;
                        return (
                          <tr key={item.id} className="border-t border-border/50">
                            <td className="px-3 py-2">{item.description}</td>
                            <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                              {item.quantity_expected ?? "—"}
                            </td>
                            <td className={`px-3 py-2 text-right tabular-nums font-medium ${hasDiscrepancy ? "text-warning" : ""}`}>
                              {item.quantity_received}
                            </td>
                            <td className="px-3 py-2 text-right text-muted-foreground">{item.unit ?? "—"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {selectedDelivery.comments && (
              <div className="bg-muted/50 rounded-lg p-3">
                <p className="text-xs text-muted-foreground mb-1">Comments</p>
                <p>{selectedDelivery.comments}</p>
              </div>
            )}
            {!selectedDelivery.purchase_order_id && (
              <div className="bg-warning/10 border border-warning/20 rounded-lg p-3 text-warning text-xs flex items-start gap-2">
                <Truck className="w-4 h-4 shrink-0 mt-0.5" />
                This delivery was received without a linked purchase order.
              </div>
            )}

            {/* Attachments */}
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5">
                <Paperclip className="w-3.5 h-3.5" />
                Proof / Attachments
              </p>
              {loadingAttachments ? (
                <p className="text-xs text-muted-foreground">Loading…</p>
              ) : deliveryAttachments.length === 0 ? (
                <p className="text-xs text-muted-foreground">No attachments for this delivery.</p>
              ) : (
                <div className="space-y-1.5">
                  {deliveryAttachments.map((att) => (
                    <div key={att.id} className="flex items-center gap-2 bg-muted/40 rounded-lg px-3 py-2">
                      {att.is_image ? (
                        <img
                          src={`/api/v1/attachments/${att.id}/download`}
                          alt={att.file_name}
                          className="w-10 h-10 object-cover rounded border border-border shrink-0"
                        />
                      ) : (
                        <div className="w-10 h-10 flex items-center justify-center bg-muted rounded border border-border shrink-0">
                          <Paperclip className="w-4 h-4 text-muted-foreground" />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium truncate">{att.file_name}</p>
                        <p className="text-[10px] text-muted-foreground">{att.file_size_display}</p>
                      </div>
                      <a
                        href={`/api/v1/attachments/${att.id}/download`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:text-primary/80 shrink-0"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </Modal>
      )}

      <RecordDeliveryModal
        open={showRecord}
        onClose={() => setShowRecord(false)}
        projects={projects}
        suppliers={suppliers}
        onSubmit={handleRecord}
      />
    </div>
  );
}
