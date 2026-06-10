import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Building2, Edit2, CheckCircle2, XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import { AttachmentStrip } from "@/components/shared/AttachmentStrip";
import {
  suppliersApi,
  type Supplier,
  type SupplierOutstanding,
  type SupplierUpdate,
  type PricingMethod,
} from "@/api/suppliers";

// ─── Edit Modal ───────────────────────────────────────────────────────────────
function EditSupplierModal({
  open,
  onClose,
  supplier,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  supplier: Supplier;
  onSave: (updated: Supplier) => void;
}) {
  const [name, setName] = useState(supplier.name);
  const [code, setCode] = useState(supplier.code ?? "");
  const [email, setEmail] = useState(supplier.email ?? "");
  const [phone, setPhone] = useState(supplier.phone ?? "");
  const [whatsapp, setWhatsapp] = useState(supplier.whatsapp_number ?? "");
  const [address, setAddress] = useState(supplier.address ?? "");
  const [contactPerson, setContactPerson] = useState(supplier.contact_person ?? "");
  const [paymentTerms, setPaymentTerms] = useState(supplier.payment_terms ?? "");
  const [vatNumber, setVatNumber] = useState(supplier.vat_number ?? "");
  const [notes, setNotes] = useState(supplier.notes ?? "");
  const [vatRegistered, setVatRegistered] = useState(supplier.vat_registered);
  const [pricingMethod, setPricingMethod] = useState<PricingMethod>(supplier.pricing_method);
  const [defaultVatRate, setDefaultVatRate] = useState(String(supplier.default_vat_rate));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setName(supplier.name);
    setCode(supplier.code ?? "");
    setEmail(supplier.email ?? "");
    setPhone(supplier.phone ?? "");
    setWhatsapp(supplier.whatsapp_number ?? "");
    setAddress(supplier.address ?? "");
    setContactPerson(supplier.contact_person ?? "");
    setPaymentTerms(supplier.payment_terms ?? "");
    setVatNumber(supplier.vat_number ?? "");
    setNotes(supplier.notes ?? "");
    setVatRegistered(supplier.vat_registered);
    setPricingMethod(supplier.pricing_method);
    setDefaultVatRate(String(supplier.default_vat_rate));
    setError("");
  }, [open, supplier]);

  // Derived: VAT number is required when registered
  const vatNumberMissing = vatRegistered && !vatNumber.trim();

  const handleSubmit = async () => {
    if (!name.trim() || !email.trim()) return;
    if (vatNumberMissing) return;
    setSaving(true);
    setError("");
    try {
      const updated = await suppliersApi.update(supplier.id, {
        name: name.trim(),
        code: code.trim() || null,
        email: email.trim(),
        phone: phone.trim() || null,
        whatsapp_number: whatsapp.trim() || null,
        address: address.trim() || null,
        contact_person: contactPerson.trim() || null,
        payment_terms: paymentTerms.trim() || null,
        vat_number: vatNumber.trim() || null,
        notes: notes.trim() || null,
        vat_registered: vatRegistered,
        pricing_method: pricingMethod,
        default_vat_rate: parseFloat(defaultVatRate) || 0,
      } as SupplierUpdate);
      onSave(updated);
      onClose();
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          "Failed to save supplier."
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="Edit Supplier" onClose={onClose} size="lg">
      <div className="p-6 space-y-5">
        {/* Basic Information */}
        <div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Basic Information
          </p>
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
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Phone</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                placeholder="+27 XX XXX XXXX"
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
            <div>
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
              <label className="text-xs text-muted-foreground block mb-1">Address</label>
              <input
                type="text"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
          </div>
        </div>

        {/* VAT Configuration */}
        <div className="border-t border-border pt-4">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            VAT Configuration
          </p>
          <div className="grid grid-cols-2 gap-4">
            {/* Toggle first — user decides registration status before entering number */}
            <div className="flex items-center gap-3 pt-1">
              <label className="relative inline-flex items-center cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={vatRegistered}
                  onChange={(e) => setVatRegistered(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-9 h-5 bg-muted peer-checked:bg-primary rounded-full transition-colors" />
                <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4 shadow" />
              </label>
              <span className="text-sm font-medium">
                {vatRegistered ? "VAT Registered" : "Not VAT Registered"}
              </span>
            </div>

            {/* VAT Number — required when registered */}
            <div>
              <label className="text-xs text-muted-foreground block mb-1">
                VAT Number
                {vatRegistered && <span className="text-destructive ml-0.5">*</span>}
              </label>
              <input
                type="text"
                value={vatNumber}
                onChange={(e) => setVatNumber(e.target.value)}
                className={`w-full h-9 rounded-md border bg-background px-3 text-sm transition-colors ${
                  vatNumberMissing
                    ? "border-destructive ring-1 ring-destructive/30 focus:outline-none"
                    : "border-input"
                }`}
                placeholder={vatRegistered ? "Required — e.g. 4123456789" : "e.g. 4123456789"}
              />
              {vatNumberMissing && (
                <p className="text-xs text-destructive mt-1">
                  VAT number is required when the supplier is VAT registered.
                </p>
              )}
            </div>

            <div>
              <label className="text-xs text-muted-foreground block mb-1">Pricing Method</label>
              <select
                value={pricingMethod}
                onChange={(e) => setPricingMethod(e.target.value as PricingMethod)}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="EX_VAT">Ex-VAT (prices exclude VAT)</option>
                <option value="INCL_VAT">Incl. VAT (prices include VAT)</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-muted-foreground block mb-1">Default VAT Rate (%)</label>
              <input
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={defaultVatRate}
                onChange={(e) => setDefaultVatRate(e.target.value)}
                className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
                placeholder="15.00"
              />
            </div>
          </div>
        </div>

        {/* Notes */}
        <div className="border-t border-border pt-4">
          <label className="text-xs text-muted-foreground block mb-1">Notes</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
          />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={saving || !name.trim() || !email.trim() || vatNumberMissing}
          >
            {saving ? "Saving…" : "Save Changes"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Info Row ─────────────────────────────────────────────────────────────────
function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2 py-2 border-b border-border/50 last:border-0">
      <span className="text-xs text-muted-foreground w-36 shrink-0 pt-0.5">{label}</span>
      <span className="text-sm font-medium text-foreground flex-1">{value}</span>
    </div>
  );
}

// ─── Fin Stat ─────────────────────────────────────────────────────────────────
function FinStat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number;
  highlight?: "warning" | "danger";
}) {
  const bgClass =
    highlight === "danger"
      ? "bg-destructive/10"
      : highlight === "warning"
      ? "bg-amber-500/10"
      : "bg-muted/30";
  const textClass =
    highlight === "danger"
      ? "text-destructive"
      : highlight === "warning"
      ? "text-amber-600"
      : "text-foreground";
  const fmt = (n: number) =>
    `R ${n.toLocaleString("en-ZA", { minimumFractionDigits: 2 })}`;

  return (
    <div className={`text-center p-3 rounded-lg ${bgClass}`}>
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className={`text-sm font-bold ${textClass}`}>{fmt(value)}</p>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function SupplierProfilePage() {
  const { supplierId } = useParams<{ supplierId: string }>();
  const navigate = useNavigate();
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [outstanding, setOutstanding] = useState<SupplierOutstanding | null>(null);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);

  useEffect(() => {
    if (!supplierId) return;
    Promise.all([
      suppliersApi.get(supplierId),
      suppliersApi.outstanding(supplierId),
    ])
      .then(([s, o]) => {
        setSupplier(s);
        setOutstanding(o);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [supplierId]);

  if (loading) {
    return (
      <div className="space-y-5 animate-fade-in">
        <Skeleton className="h-14 w-96 rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton className="h-52 rounded-xl" />
          <Skeleton className="h-52 rounded-xl" />
        </div>
        <Skeleton className="h-28 rounded-xl" />
      </div>
    );
  }

  if (!supplier) {
    return (
      <div className="p-12 text-center text-sm text-muted-foreground">Supplier not found.</div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <button
            onClick={() => navigate("/suppliers")}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground mb-3 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Suppliers
          </button>
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <Building2 className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold leading-tight">{supplier.name}</h1>
              <div className="flex items-center flex-wrap gap-2 mt-1">
                {supplier.code && (
                  <span className="font-mono text-xs bg-muted px-2 py-0.5 rounded">
                    {supplier.code}
                  </span>
                )}
                <Badge variant={supplier.is_active ? "success" : "secondary"}>
                  {supplier.is_active ? "Active" : "Inactive"}
                </Badge>
                {supplier.vat_registered && (
                  <Badge variant="outline" className="text-xs font-normal">
                    VAT Registered
                  </Badge>
                )}
              </div>
            </div>
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={() => setEditOpen(true)} className="shrink-0">
          <Edit2 className="w-3.5 h-3.5 mr-1.5" />
          Edit Supplier
        </Button>
      </div>

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Contact Information */}
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-3">Contact Information</h2>
          {supplier.contact_person && (
            <InfoRow label="Contact Person" value={supplier.contact_person} />
          )}
          {supplier.email && (
            <InfoRow
              label="Email"
              value={
                <a href={`mailto:${supplier.email}`} className="text-primary hover:underline">
                  {supplier.email}
                </a>
              }
            />
          )}
          {supplier.phone && (
            <InfoRow
              label="Phone"
              value={
                <a href={`tel:${supplier.phone}`} className="hover:underline">
                  {supplier.phone}
                </a>
              }
            />
          )}
          {supplier.whatsapp_number && (
            <InfoRow label="WhatsApp" value={supplier.whatsapp_number} />
          )}
          {supplier.address && <InfoRow label="Address" value={supplier.address} />}
          {supplier.payment_terms && (
            <InfoRow label="Payment Terms" value={supplier.payment_terms} />
          )}
          {!supplier.contact_person &&
            !supplier.email &&
            !supplier.phone &&
            !supplier.whatsapp_number &&
            !supplier.address &&
            !supplier.payment_terms && (
              <p className="text-xs text-muted-foreground">No contact details on file.</p>
            )}
        </div>

        {/* VAT Configuration */}
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-3">VAT Configuration</h2>
          <InfoRow
            label="VAT Status"
            value={
              <div className="flex items-center gap-1.5">
                {supplier.vat_registered ? (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                    <span>VAT Registered</span>
                  </>
                ) : (
                  <>
                    <XCircle className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="text-muted-foreground">Not VAT Registered</span>
                  </>
                )}
              </div>
            }
          />
          {supplier.vat_number && <InfoRow label="VAT Number" value={supplier.vat_number} />}
          <InfoRow
            label="Pricing Method"
            value={
              <Badge variant="outline" className="font-normal text-xs">
                {supplier.pricing_method === "EX_VAT" ? "Ex-VAT" : "Incl. VAT"}
              </Badge>
            }
          />
          <InfoRow
            label="Default VAT Rate"
            value={`${supplier.default_vat_rate}%`}
          />
        </div>
      </div>

      {/* Financial Summary */}
      {outstanding && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-4">Financial Summary</h2>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <FinStat label="PO Total" value={outstanding.po_total} />
            <FinStat label="Invoiced" value={outstanding.invoice_total} />
            <FinStat label="Paid" value={outstanding.paid_total} />
            <FinStat
              label="Outstanding"
              value={outstanding.outstanding}
              highlight={outstanding.outstanding > 0 ? "warning" : undefined}
            />
            <FinStat
              label="Overdue"
              value={outstanding.overdue_amount}
              highlight={outstanding.overdue_amount > 0 ? "danger" : undefined}
            />
          </div>
        </div>
      )}

      {/* Notes */}
      {supplier.notes && (
        <div className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold mb-2">Notes</h2>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{supplier.notes}</p>
        </div>
      )}

      {/* Documents */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-sm font-semibold mb-4">Documents</h2>
        <AttachmentStrip
          entityType="SUPPLIER"
          entityId={supplier.id}
          attachmentType="QUOTATION"
          showTypeSelector
          compact
        />
      </div>

      {/* Edit Modal */}
      <EditSupplierModal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        supplier={supplier}
        onSave={(updated) => setSupplier(updated)}
      />
    </div>
  );
}
