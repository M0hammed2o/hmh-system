/**
 * BOQ Builder — full manual editor for a single BOQ version.
 * Reached from BOQPage when the user clicks "Edit/Build" on a header.
 */
import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft, Plus, Trash2, ChevronDown, ChevronRight,
  Save, Copy, Check, Pencil, X, BookTemplate, AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  boqApi,
  type FullBOQ, type BOQSection, type BOQItem, type ItemType,
} from "@/api/boq";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { cn } from "@/lib/utils";


// ── Delete Section Modal ──────────────────────────────────────────────────────

interface DeleteSectionModalProps {
  sectionName: string;
  isLotBOQ: boolean;
  onConfirm: (scope: "lot" | "site") => void;
  onCancel: () => void;
}

function DeleteSectionModal({ sectionName, isLotBOQ, onConfirm, onCancel }: DeleteSectionModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-background border border-border rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6 space-y-4">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 p-2 rounded-lg bg-destructive/10">
            <AlertTriangle className="w-4 h-4 text-destructive" />
          </div>
          <div>
            <h2 className="font-semibold text-base">Delete section</h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              <span className="font-medium text-foreground">"{sectionName}"</span>
              {" "}and all its items will be permanently removed.
            </p>
          </div>
        </div>

        <div className="space-y-2">
          <Button
            variant="outline"
            className="w-full justify-start text-sm"
            onClick={() => onConfirm("lot")}
          >
            <Trash2 className="w-3.5 h-3.5 mr-2 text-muted-foreground" />
            Delete from this lot only
          </Button>

          {isLotBOQ && (
            <Button
              variant="destructive"
              className="w-full justify-start text-sm"
              onClick={() => onConfirm("site")}
            >
              <Trash2 className="w-3.5 h-3.5 mr-2" />
              Delete from all lots in this site
            </Button>
          )}
        </div>

        <Button variant="ghost" className="w-full text-sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

const TYPE_OPTIONS: ItemType[] = ["MATERIAL", "LABOUR", "PLANT", "SERVICE", "PACKAGE"];

const TYPE_COLOR: Record<ItemType, string> = {
  MATERIAL: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  LABOUR:   "bg-green-500/10 text-green-600 dark:text-green-400",
  PLANT:    "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  SERVICE:  "bg-purple-500/10 text-purple-600 dark:text-purple-400",
  PACKAGE:  "bg-pink-500/10 text-pink-600 dark:text-pink-400",
};

function fmt(n: number | null | undefined) {
  if (n == null) return "—";
  return `R${n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ── BOQ total helpers ─────────────────────────────────────────────────────────
// planned_total may be null (DB-generated column not always returned).
// Compute client-side from planned_quantity × planned_rate instead.

function getQty(item: BOQItem): number | null {
  const v = item.planned_quantity
    ?? (item as Record<string, unknown>).quantity
    ?? (item as Record<string, unknown>).qty;
  return v != null ? Number(v) : null;
}

function getRate(item: BOQItem): number | null {
  const v = item.planned_rate
    ?? (item as Record<string, unknown>).rate
    ?? (item as Record<string, unknown>).unit_rate;
  return v != null ? Number(v) : null;
}

function itemTotalForSum(item: BOQItem): number {
  if (item.planned_total != null) return Number(item.planned_total);
  const q = getQty(item);
  const r = getRate(item);
  if (q == null || r == null) return 0;
  return q * r;
}

function itemTotalDisplay(item: BOQItem): number | null {
  if (item.planned_total != null) return Number(item.planned_total);
  const q = getQty(item);
  const r = getRate(item);
  if (q == null || r == null) return null;
  return q * r;
}
// ─────────────────────────────────────────────────────────────────────────────

// ── Inline item row ───────────────────────────────────────────────────────────

interface ItemRowProps {
  item: BOQItem;
  suppliers: Supplier[];
  onSave: (id: string, patch: Partial<BOQItem>, applyToAllLots?: boolean) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

function ItemRow({ item, suppliers, onSave, onDelete }: ItemRowProps) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    raw_description: item.raw_description,
    unit: item.unit || "",
    planned_quantity: item.planned_quantity?.toString() || "",
    planned_rate: item.planned_rate?.toString() || "",
    item_type: item.item_type,
    specification: item.specification || "",
    notes: item.notes || "",
    supplier_id: item.supplier_id || "",
  });
  const [applyToAll, setApplyToAll] = useState(false);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave(item.id, {
      raw_description: form.raw_description,
      unit: form.unit || null,
      planned_quantity: form.planned_quantity ? parseFloat(form.planned_quantity) : null,
      planned_rate: form.planned_rate ? parseFloat(form.planned_rate) : null,
      item_type: form.item_type,
      specification: form.specification || null,
      notes: form.notes || null,
      supplier_id: form.supplier_id || null,
    }, applyToAll);
    setSaving(false);
    setEditing(false);
    setApplyToAll(false);
  };

  const total = (() => {
    const q = parseFloat(form.planned_quantity || "0");
    const r = parseFloat(form.planned_rate || "0");
    return isNaN(q) || isNaN(r) ? null : q * r;
  })();

  if (editing) {
    return (
      <tr className="bg-primary/5 border-b border-border">
        <td className="px-3 py-2" colSpan={6}>
          <div className="space-y-2">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div className="sm:col-span-2">
                <Input
                  value={form.raw_description}
                  onChange={(e) => setForm({ ...form, raw_description: e.target.value })}
                  placeholder="Description"
                  className="text-sm h-8"
                />
              </div>
              <select
                value={form.item_type}
                onChange={(e) => setForm({ ...form, item_type: e.target.value as ItemType })}
                className="h-8 rounded-md border border-input bg-background px-2 text-sm"
              >
                {TYPE_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
              <Input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} placeholder="Unit" className="text-sm h-8" />
              <Input type="number" value={form.planned_quantity} onChange={(e) => setForm({ ...form, planned_quantity: e.target.value })} placeholder="Qty" className="text-sm h-8" />
              <Input type="number" value={form.planned_rate} onChange={(e) => setForm({ ...form, planned_rate: e.target.value })} placeholder="Rate" className="text-sm h-8" />
              <div className="flex items-center gap-1 text-sm font-medium">
                {total != null ? fmt(total) : "—"}
              </div>
            </div>
            <Input value={form.specification} onChange={(e) => setForm({ ...form, specification: e.target.value })} placeholder="Specification (optional)" className="text-sm h-8" />
            <select
              value={form.supplier_id}
              onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
              className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="">— No supplier —</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {/* Apply-to-all-lots checkbox — only shown when editing a lot-level item */}
            {item.lot_id && (
              <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={applyToAll}
                  onChange={(e) => setApplyToAll(e.target.checked)}
                  className="rounded"
                />
                <span className={applyToAll ? "font-semibold text-primary" : "text-muted-foreground"}>
                  Apply these changes to all lots in this site
                </span>
              </label>
            )}
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSave} disabled={saving} className="h-7 text-xs">
                <Save className="w-3 h-3 mr-1" />{saving ? "Saving…" : applyToAll ? "Save (All Lots)" : "Save"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => { setEditing(false); setApplyToAll(false); }} className="h-7 text-xs">
                <X className="w-3 h-3 mr-1" />Cancel
              </Button>
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-border hover:bg-muted/30 group">
      <td className="px-3 py-2.5 text-sm">
        <span className={cn("text-[10px] font-medium rounded px-1.5 py-0.5 mr-2", TYPE_COLOR[item.item_type])}>
          {item.item_type.slice(0, 3)}
        </span>
        {item.raw_description}
        {item.specification && (
          <span className="block text-xs text-muted-foreground mt-0.5 truncate max-w-[300px]">{item.specification}</span>
        )}
        {item.supplier_id && (() => {
          const sup = suppliers.find(s => s.id === item.supplier_id);
          return sup ? <span className="block text-[10px] text-primary/70 mt-0.5">{sup.name}</span> : null;
        })()}
      </td>
      <td className="px-3 py-2.5 text-sm text-center text-muted-foreground">{item.unit || "—"}</td>
      <td className="px-3 py-2.5 text-sm text-right">{item.planned_quantity ?? "—"}</td>
      <td className="px-3 py-2.5 text-sm text-right">{item.planned_rate != null ? `R${item.planned_rate.toFixed(2)}` : "—"}</td>
      <td className="px-3 py-2.5 text-sm text-right font-medium">{fmt(itemTotalDisplay(item))}</td>
      <td className="px-3 py-2.5 text-right">
        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={() => setEditing(true)} className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground">
            <Pencil className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => onDelete(item.id)} className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── Add item row ──────────────────────────────────────────────────────────────

function AddItemRow({ sectionId, onAdded }: { sectionId: string; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ raw_description: "", unit: "", planned_quantity: "", planned_rate: "", item_type: "MATERIAL" as ItemType });
  const [saving, setSaving] = useState(false);

  const handleAdd = async () => {
    if (!form.raw_description.trim()) return;
    setSaving(true);
    try {
      await boqApi.createItem(sectionId, {
        raw_description: form.raw_description,
        unit: form.unit || null,
        planned_quantity: form.planned_quantity ? parseFloat(form.planned_quantity) : null,
        planned_rate: form.planned_rate ? parseFloat(form.planned_rate) : null,
        item_type: form.item_type,
      });
      setForm({ raw_description: "", unit: "", planned_quantity: "", planned_rate: "", item_type: "MATERIAL" });
      setOpen(false);
      onAdded();
    } finally { setSaving(false); }
  };

  if (!open) {
    return (
      <tr>
        <td colSpan={6} className="px-3 py-2">
          <button onClick={() => setOpen(true)} className="flex items-center gap-1.5 text-xs text-primary hover:underline">
            <Plus className="w-3.5 h-3.5" />Add item
          </button>
        </td>
      </tr>
    );
  }

  return (
    <tr className="bg-muted/20 border-b border-border">
      <td colSpan={6} className="px-3 py-2">
        <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 items-end">
          <div className="col-span-2 sm:col-span-2">
            <Input value={form.raw_description} onChange={(e) => setForm({ ...form, raw_description: e.target.value })} placeholder="Description *" className="h-8 text-sm" autoFocus />
          </div>
          <select value={form.item_type} onChange={(e) => setForm({ ...form, item_type: e.target.value as ItemType })} className="h-8 rounded-md border border-input bg-background px-2 text-sm">
            {TYPE_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <Input value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} placeholder="Unit" className="h-8 text-sm" />
          <Input type="number" value={form.planned_quantity} onChange={(e) => setForm({ ...form, planned_quantity: e.target.value })} placeholder="Qty" className="h-8 text-sm" />
          <Input type="number" value={form.planned_rate} onChange={(e) => setForm({ ...form, planned_rate: e.target.value })} placeholder="Rate" className="h-8 text-sm" />
        </div>
        <div className="flex gap-2 mt-2">
          <Button size="sm" onClick={handleAdd} disabled={saving || !form.raw_description.trim()} className="h-7 text-xs">
            <Check className="w-3 h-3 mr-1" />{saving ? "Adding…" : "Add"}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setOpen(false)} className="h-7 text-xs">Cancel</Button>
        </div>
      </td>
    </tr>
  );
}

// ── Section block ─────────────────────────────────────────────────────────────

interface SectionBlockProps {
  section: BOQSection;
  items: BOQItem[];
  sectionTotal: number;
  headerId: string;
  projectId: string;
  suppliers: Supplier[];
  onRefresh: () => void;
  onDeleteSection: (id: string) => Promise<void>;
}

function SectionBlock({ section, items, sectionTotal, headerId, projectId, suppliers, onRefresh, onDeleteSection }: SectionBlockProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [name, setName] = useState(section.section_name);

  const handleSaveItem = async (id: string, patch: Partial<BOQItem>, applyToAllLots = false) => {
    if (applyToAllLots) {
      const res = await boqApi.applyItemToAllSiteLots(id, patch as Parameters<typeof boqApi.updateItem>[1]);
      const base = `Applied to ${res.updated} item(s) across ${res.lots_affected} lot(s).`;
      if (res.lots_affected === 0) {
        alert(`⚠ ${base}\n\n${res.warning ?? "No peer items were found. Check that lots are assigned to a site."}`);
      } else if (res.warning) {
        alert(`${base}\n\nWarning: ${res.warning}`);
      } else {
        alert(base);
      }
    } else {
      await boqApi.updateItem(id, patch as Parameters<typeof boqApi.updateItem>[1]);
    }
    onRefresh();
  };

  const handleDeleteItem = async (id: string) => {
    if (!confirm("Delete this item?")) return;
    await boqApi.deleteItem(id);
    onRefresh();
  };

  const handleSaveName = async () => {
    if (name.trim() && name.trim() !== section.section_name) {
      await boqApi.updateSection(headerId, section.id, { section_name: name.trim() });
      onRefresh();
    }
    setEditingName(false);
  };

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      {/* Section header */}
      <div className="flex items-center gap-2 px-4 py-3 bg-muted/30 border-b border-border">
        <button onClick={() => setCollapsed(!collapsed)} className="text-muted-foreground hover:text-foreground">
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {editingName ? (
          <div className="flex items-center gap-2 flex-1">
            <Input value={name} onChange={(e) => setName(e.target.value)} className="h-7 text-sm flex-1 max-w-xs" autoFocus />
            <Button size="sm" onClick={handleSaveName} className="h-7 text-xs"><Check className="w-3 h-3" /></Button>
            <Button size="sm" variant="outline" onClick={() => setEditingName(false)} className="h-7 text-xs"><X className="w-3 h-3" /></Button>
          </div>
        ) : (
          <span className="font-semibold text-sm flex-1">{section.section_name}</span>
        )}
        <span className="text-sm font-medium ml-auto">{fmt(sectionTotal)}</span>
        <badge className="text-xs text-muted-foreground ml-2">{items.length} item{items.length !== 1 ? "s" : ""}</badge>
        <button
          onClick={() => onDeleteSection(section.id)}
          className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive ml-1"
          title="Delete section"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Items table */}
      {!collapsed && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/10">
                <th className="text-left px-3 py-2 font-medium text-muted-foreground">Description</th>
                <th className="text-center px-3 py-2 font-medium text-muted-foreground w-16">Unit</th>
                <th className="text-right px-3 py-2 font-medium text-muted-foreground w-20">Qty</th>
                <th className="text-right px-3 py-2 font-medium text-muted-foreground w-24">Rate</th>
                <th className="text-right px-3 py-2 font-medium text-muted-foreground w-28">Total</th>
                <th className="w-16" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <ItemRow key={item.id} item={item} suppliers={suppliers} onSave={handleSaveItem} onDelete={handleDeleteItem} />
              ))}
              <AddItemRow sectionId={section.id} onAdded={onRefresh} />
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BOQBuilderPage() {
  const { projectId, headerId } = useParams<{ projectId: string; headerId: string }>();
  const navigate = useNavigate();
  const [boq, setBOQ] = useState<FullBOQ | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [addingSection, setAddingSection] = useState(false);
  const [newSectionName, setNewSectionName] = useState("");
  const [markingTemplate, setMarkingTemplate] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateDone, setTemplateDone] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [deleteResult, setDeleteResult] = useState<string | null>(null);
  // Detect if this BOQ was cloned to a specific lot (version name contains "— Lot X")
  const lotMatch = boq?.header.version_name.match(/— Lot (\S+)$/);
  const lotNumber = lotMatch ? lotMatch[1] : null;

  const load = useCallback(async () => {
    if (!projectId || !headerId) return;
    setError("");
    try {
      const data = await boqApi.getFullBOQ(projectId, headerId);
      setBOQ(data);
    } catch {
      setError("Failed to load BOQ.");
    } finally {
      setLoading(false);
    }
  }, [projectId, headerId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { suppliersApi.list().then(setSuppliers).catch(() => {}); }, []);

  const handleAddSection = async () => {
    if (!newSectionName.trim() || !headerId) return;
    await boqApi.createSection(headerId, {
      section_name: newSectionName.trim(),
      sequence_order: (boq?.sections.length || 0) + 1,
    });
    setNewSectionName("");
    setAddingSection(false);
    load();
  };

  const handleDeleteSection = (sectionId: string) => {
    const sec = boq?.sections.find(({ section }) => section.id === sectionId);
    if (!sec) return;
    setDeleteResult(null);
    setDeleteTarget({ id: sectionId, name: sec.section.section_name });
  };

  const handleConfirmDelete = async (scope: "lot" | "site") => {
    if (!headerId || !deleteTarget) return;
    try {
      const result = await boqApi.deleteSectionScoped(headerId, deleteTarget.id, scope);
      setDeleteResult(result.message);
    } catch {
      setDeleteResult("Delete failed — please try again.");
    }
    setDeleteTarget(null);
    load();
  };

  const handleMarkTemplate = async () => {
    if (!projectId || !headerId || !templateName.trim()) return;
    await boqApi.markAsTemplate(projectId, headerId, templateName.trim());
    setTemplateDone(true);
    setMarkingTemplate(false);
    load();
  };

  if (loading) {
    return (
      <div className="space-y-4 animate-fade-in">
        <Skeleton className="h-10 w-48 rounded-xl" />
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-32 rounded-xl" />)}
      </div>
    );
  }

  if (error || !boq) {
    return <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 text-sm text-destructive">{error || "BOQ not found."}</div>;
  }

  // Compute totals client-side — API's grand_total/section_total may be 0
  // when the DB-generated planned_total column is null.
  const computedGrandTotal = boq.sections.reduce(
    (sum, { items }) => sum + items.reduce((s, i) => s + itemTotalForSum(i), 0),
    0,
  );

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start gap-3">
        <button onClick={() => navigate(`/boq`)} className="p-2 rounded-lg hover:bg-muted mt-0.5">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1 min-w-0">
          {lotNumber && (
            <p className="text-xs text-muted-foreground mb-0.5">
              Editing BOQ for <span className="font-semibold text-foreground">Lot {lotNumber}</span>
              {" — changes only affect this lot"}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold truncate">{boq.header.version_name}</h1>
            {boq.header.is_template && (
              <Badge variant="secondary" className="text-xs">Template</Badge>
            )}
            {lotNumber && (
              <Badge variant="outline" className="text-xs">Lot-specific</Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            {boq.sections.length} sections · {boq.sections.reduce((sum, s) => sum + s.items.length, 0)} items · Grand total: <span className="font-semibold text-foreground">{fmt(computedGrandTotal)}</span>
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {!boq.header.is_template && (
            <Button size="sm" variant="outline" onClick={() => setMarkingTemplate(true)}>
              <BookTemplate className="w-4 h-4 mr-1" />Make Template
            </Button>
          )}
        </div>
      </div>

      {/* Template done banner */}
      {templateDone && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-xl px-4 py-3 flex items-center justify-between">
          <p className="text-sm text-green-600 dark:text-green-400 font-medium">
            <Check className="w-4 h-4 inline mr-1" />BOQ saved as template. You can now clone it to lots from the <Link to="/boq-templates" className="underline">BOQ Templates</Link> page.
          </p>
          <button onClick={() => setTemplateDone(false)} className="text-muted-foreground hover:text-foreground"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {/* Delete result banner */}
      {deleteResult && (
        <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl px-4 py-3 flex items-center justify-between">
          <p className="text-sm text-orange-700 dark:text-orange-400 font-medium">
            <Trash2 className="w-4 h-4 inline mr-1" />{deleteResult}
          </p>
          <button onClick={() => setDeleteResult(null)} className="text-muted-foreground hover:text-foreground"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {/* Grand total bar */}
      <div className="bg-card border border-border rounded-xl px-5 py-3 flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">Grand Total (Planned)</span>
        <span className="text-2xl font-bold">{fmt(computedGrandTotal)}</span>
      </div>

      {/* Sections */}
      <div className="space-y-3">
        {boq.sections.map(({ section, items }) => {
          const sectionTotal = items.reduce((sum, i) => sum + itemTotalForSum(i), 0);
          return (
            <SectionBlock
              key={section.id}
              section={section}
              items={items}
              sectionTotal={sectionTotal}
              headerId={boq.header.id}
              projectId={boq.header.project_id}
              suppliers={suppliers}
              onRefresh={load}
              onDeleteSection={handleDeleteSection}
            />
          );
        })}
      </div>

      {/* Add section */}
      {addingSection ? (
        <div className="flex gap-2 items-center">
          <Input
            value={newSectionName}
            onChange={(e) => setNewSectionName(e.target.value)}
            placeholder="Section name, e.g. Foundations"
            className="flex-1"
            autoFocus
            onKeyDown={(e) => { if (e.key === "Enter") handleAddSection(); }}
          />
          <Button onClick={handleAddSection} disabled={!newSectionName.trim()}>
            <Check className="w-4 h-4 mr-1" />Add
          </Button>
          <Button variant="outline" onClick={() => { setAddingSection(false); setNewSectionName(""); }}>
            Cancel
          </Button>
        </div>
      ) : (
        <Button variant="outline" onClick={() => setAddingSection(true)} className="w-full">
          <Plus className="w-4 h-4 mr-2" />Add Section
        </Button>
      )}

      {/* Mark as template modal */}
      {markingTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
          <div className="bg-card border border-border rounded-xl w-full max-w-md p-6 space-y-4 animate-fade-in">
            <h2 className="font-semibold text-base">Save as Template</h2>
            <p className="text-sm text-muted-foreground">Give this BOQ a template name so it can be cloned to multiple lots.</p>
            <Input
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="e.g. Standard 2-Bed Unit"
              autoFocus
            />
            <div className="flex gap-2">
              <Button onClick={handleMarkTemplate} disabled={!templateName.trim()} className="flex-1">Save as Template</Button>
              <Button variant="outline" onClick={() => setMarkingTemplate(false)}>Cancel</Button>
            </div>
          </div>
        </div>
      )}

      {/* Delete section modal */}
      {deleteTarget && (
        <DeleteSectionModal
          sectionName={deleteTarget.name}
          isLotBOQ={!!lotNumber}
          onConfirm={handleConfirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
