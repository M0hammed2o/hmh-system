import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Building2, CheckCircle2, XCircle, Trash2, ChevronDown, ChevronUp, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { AttachmentStrip } from "@/components/shared/AttachmentStrip";
import { suppliersApi, type Supplier, type SupplierCreate, type SupplierUpdate } from "@/api/suppliers";

// ─── Supplier Form Modal ──────────────────────────────────────────────────────
function SupplierModal({
  open,
  onClose,
  existing,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  existing: Supplier | null;
  onSave: (data: SupplierCreate | SupplierUpdate, id?: string) => Promise<void>;
}) {
  const [name, setName] = useState(existing?.name ?? "");
  const [code, setCode] = useState(existing?.code ?? "");
  const [email, setEmail] = useState(existing?.email ?? "");
  const [phone, setPhone] = useState(existing?.phone ?? "");
  const [whatsapp, setWhatsapp] = useState(existing?.whatsapp_number ?? "");
  const [address, setAddress] = useState(existing?.address ?? "");
  const [contactPerson, setContactPerson] = useState(existing?.contact_person ?? "");
  const [paymentTerms, setPaymentTerms] = useState(existing?.payment_terms ?? "");
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(existing?.name ?? "");
    setCode(existing?.code ?? "");
    setEmail(existing?.email ?? "");
    setPhone(existing?.phone ?? "");
    setWhatsapp(existing?.whatsapp_number ?? "");
    setAddress(existing?.address ?? "");
    setContactPerson(existing?.contact_person ?? "");
    setPaymentTerms(existing?.payment_terms ?? "");
    setNotes(existing?.notes ?? "");
  }, [existing, open]);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    if (!email.trim()) { alert("Email is required for suppliers."); return; }
    if (!phone.trim()) { alert("Phone number is required for suppliers."); return; }
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        code: code.trim() || null,
        email: email.trim(),
        phone: phone.trim() || null,
        whatsapp_number: whatsapp.trim() || null,
        address: address.trim() || null,
        contact_person: contactPerson.trim() || null,
        payment_terms: paymentTerms.trim() || null,
        notes: notes.trim() || null,
      };
      await onSave(payload, existing?.id);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title={existing ? "Edit Supplier" : "New Supplier"} onClose={onClose} size="md">
      <div className="p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground block mb-1">Supplier Name *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="e.g. Buildmart SA"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Code</label>
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="e.g. BM001"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Contact Person</label>
            <input
              type="text"
              value={contactPerson}
              onChange={(e) => setContactPerson(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Email *</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="supplier@example.com"
              required
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Phone *</label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="+27 XX XXX XXXX"
              required
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">WhatsApp Number</label>
            <input
              type="tel"
              value={whatsapp}
              onChange={(e) => setWhatsapp(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="+27 XX XXX XXXX"
            />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground block mb-1">Address</label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground block mb-1">Payment Terms</label>
            <input
              type="text"
              value={paymentTerms}
              onChange={(e) => setPaymentTerms(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="e.g. 30 days EOM"
            />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground block mb-1">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={handleSubmit} disabled={saving || !name.trim() || !email.trim() || !phone.trim()}>
            {saving ? "Saving…" : existing ? "Save Changes" : "Create Supplier"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────────
export default function SuppliersPage() {
  const navigate = useNavigate();
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<Supplier | null>(null);
  const [search, setSearch] = useState("");
  const [expandedDocs, setExpandedDocs] = useState<string | null>(null);

  useEffect(() => {
    suppliersApi
      .list(true) // include inactive
      .then(setSuppliers)
      .catch(() => setSuppliers([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = suppliers.filter(
    (s) =>
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      (s.code ?? "").toLowerCase().includes(search.toLowerCase()) ||
      (s.contact_person ?? "").toLowerCase().includes(search.toLowerCase())
  );

  const activeCount = suppliers.filter((s) => s.is_active).length;

  const handleSave = async (data: SupplierCreate | SupplierUpdate, id?: string) => {
    if (id) {
      const updated = await suppliersApi.update(id, data as SupplierUpdate);
      setSuppliers((prev) => prev.map((s) => (s.id === id ? updated : s)));
    } else {
      const created = await suppliersApi.create(data as SupplierCreate);
      setSuppliers((prev) => [created, ...prev]);
    }
  };

  const handleToggleActive = async (supplier: Supplier) => {
    const updated = await suppliersApi.update(supplier.id, { is_active: !supplier.is_active });
    setSuppliers((prev) => prev.map((s) => (s.id === supplier.id ? updated : s)));
  };

  const toggleDocs = (id: string) => {
    setExpandedDocs((prev) => (prev === id ? null : id));
  };

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Suppliers"
        description="Manage supplier records for purchase orders and deliveries."
        actions={
          <Button size="sm" onClick={() => { setEditTarget(null); setShowModal(true); }}>
            <Plus className="w-4 h-4" />
            New Supplier
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard title="Total Suppliers" value={suppliers.length} icon={Building2} color="bg-primary/10 text-primary" />
        <StatCard title="Active" value={activeCount} icon={CheckCircle2} color="bg-success/10 text-success" />
        <StatCard title="Inactive" value={suppliers.length - activeCount} icon={XCircle} color="bg-muted-foreground/10 text-muted-foreground" />
      </div>

      {/* Search */}
      <div>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, code or contact..."
          className="h-9 rounded-md border border-input bg-background px-3 text-sm w-full max-w-sm"
        />
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {filtered.length === 0 ? (
            <div className="p-12 text-center text-sm text-muted-foreground">No suppliers found.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Code</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Contact</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Email</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Phone</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Terms</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <React.Fragment key={s.id}>
                    <tr className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-4 py-3 font-mono text-xs">{s.code ?? "—"}</td>
                      <td className="px-4 py-3 font-medium">
                        <button
                          onClick={() => navigate(`/suppliers/${s.id}`)}
                          className="text-primary hover:underline text-left"
                        >
                          {s.name}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{s.contact_person ?? "—"}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{s.email ?? "—"}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{s.phone ?? "—"}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{s.payment_terms ?? "—"}</td>
                      <td className="px-4 py-3">
                        <Badge variant={s.is_active ? "success" : "secondary"}>
                          {s.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleDocs(s.id)}
                            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                            title="Supplier documents"
                          >
                            <Paperclip className="w-3 h-3" />
                            Docs
                            {expandedDocs === s.id ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                          </button>
                          <button
                            onClick={() => { setEditTarget(s); setShowModal(true); }}
                            className="text-xs text-primary hover:underline"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleToggleActive(s)}
                            className="text-xs text-muted-foreground hover:text-foreground"
                          >
                            {s.is_active ? "Deactivate" : "Activate"}
                          </button>
                          {s.is_active && (
                            <button
                              onClick={async () => {
                                if (!window.confirm(`Delete supplier "${s.name}"?\n\nThis will deactivate the supplier. All historical records are preserved.`)) return;
                                try {
                                  await suppliersApi.delete(s.id);
                                  setSuppliers(prev => prev.filter(x => x.id !== s.id));
                                } catch (err: unknown) {
                                  alert((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Cannot delete supplier.");
                                }
                              }}
                              className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                              title="Delete supplier"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                    {expandedDocs === s.id && (
                      <tr className="bg-muted/20 border-b border-border">
                        <td colSpan={8} className="px-6 py-4">
                          <p className="text-xs font-medium text-muted-foreground mb-3">
                            Supplier Documents — {s.name}
                          </p>
                          <AttachmentStrip
                            entityType="SUPPLIER"
                            entityId={s.id}
                            attachmentType="QUOTATION"
                            showTypeSelector
                            compact
                          />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <SupplierModal
        open={showModal}
        onClose={() => setShowModal(false)}
        existing={editTarget}
        onSave={handleSave}
      />
    </div>
  );
}
