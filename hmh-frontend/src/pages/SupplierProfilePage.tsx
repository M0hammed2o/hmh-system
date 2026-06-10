import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Building2, Edit2, CheckCircle2, XCircle,
  FileText, Download, Trash2, Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import {
  suppliersApi,
  type Supplier,
  type SupplierOutstanding,
  type SupplierUpdate,
  type PricingMethod,
} from "@/api/suppliers";
import {
  attachmentsApi,
  type Attachment,
  type AttachmentType,
  ATTACHMENT_TYPE_LABELS,
} from "@/api/attachments";

// ─── Document Centre ──────────────────────────────────────────────────────────

const SUPPLIER_DOC_TYPES: { value: AttachmentType; label: string }[] = [
  { value: "ORDER_NOTE",    label: "Order Note" },
  { value: "QUOTATION",     label: "Quotation" },
  { value: "PO_DOCUMENT",   label: "Purchase Order" },
  { value: "DELIVERY_NOTE", label: "Delivery Note" },
  { value: "INVOICE_COPY",  label: "Invoice" },
  { value: "CREDIT_NOTE",   label: "Credit Note" },
];

const DOC_FILTER_CHIPS: { value: AttachmentType | "ALL"; label: string }[] = [
  { value: "ALL",           label: "All" },
  { value: "ORDER_NOTE",    label: "Order Notes" },
  { value: "QUOTATION",     label: "Quotations" },
  { value: "PO_DOCUMENT",   label: "Purchase Orders" },
  { value: "DELIVERY_NOTE", label: "Delivery Notes" },
  { value: "INVOICE_COPY",  label: "Invoices" },
  { value: "CREDIT_NOTE",   label: "Credit Notes" },
];

function DocRow({
  doc,
  onOpen,
  onDelete,
}: {
  doc: Attachment;
  onOpen: (d: Attachment) => void;
  onDelete: (id: string) => void;
}) {
  const typeLabel = ATTACHMENT_TYPE_LABELS[doc.attachment_type] ?? doc.attachment_type;
  const date = new Date(doc.uploaded_at).toLocaleDateString("en-ZA", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors group">
      <div className="shrink-0 w-9 h-9 rounded-lg bg-muted flex items-center justify-center overflow-hidden">
        {doc.is_image ? (
          <img src={doc.download_url} alt="" className="w-9 h-9 object-cover" />
        ) : (
          <FileText className="w-4 h-4 text-muted-foreground" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <button
          onClick={() => onOpen(doc)}
          className="text-sm font-medium hover:text-primary truncate block w-full text-left leading-tight"
        >
          {doc.file_name}
        </button>
        {doc.caption && (
          <p className="text-xs text-muted-foreground truncate mt-0.5">{doc.caption}</p>
        )}
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <Badge variant="outline" className="text-xs font-normal py-0 px-1.5 h-4">
            {typeLabel}
          </Badge>
          <span className="text-xs text-muted-foreground">{doc.file_size_display}</span>
          <span className="text-xs text-muted-foreground">{date}</span>
          {doc.uploaded_by_name && (
            <span className="text-xs text-muted-foreground">· {doc.uploaded_by_name}</span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <a
          href={doc.download_url}
          target="_blank"
          rel="noopener noreferrer"
          className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          title="Open / Download"
        >
          <Download className="w-3.5 h-3.5" />
        </a>
        <button
          onClick={() => onDelete(doc.id)}
          className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
          title="Delete"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

function SupplierDocCentre({ supplierId }: { supplierId: string }) {
  const [docs, setDocs] = useState<Attachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeType, setActiveType] = useState<AttachmentType | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [uploadType, setUploadType] = useState<AttachmentType>("QUOTATION");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [preview, setPreview] = useState<Attachment | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    attachmentsApi
      .listByEntity("SUPPLIER", supplierId)
      .then(setDocs)
      .catch(() => setDocs([]))
      .finally(() => setLoading(false));
  }, [supplierId]);

  const filtered = docs.filter((d) => {
    const matchesType = activeType === "ALL" || d.attachment_type === activeType;
    const q = search.toLowerCase();
    const matchesSearch =
      !q ||
      d.file_name.toLowerCase().includes(q) ||
      (d.caption ?? "").toLowerCase().includes(q);
    return matchesType && matchesSearch && d.is_active;
  });

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setUploadError("File exceeds 5 MB limit.");
      e.target.value = "";
      return;
    }
    setUploadError("");
    setUploading(true);
    try {
      const att = await attachmentsApi.upload(file, "SUPPLIER", supplierId, uploadType);
      setDocs((prev) => [att, ...prev]);
    } catch {
      setUploadError("Upload failed. Please try again.");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("Delete this document?")) return;
    try {
      await attachmentsApi.delete(id);
      setDocs((prev) => prev.filter((d) => d.id !== id));
    } catch {
      // silent — item may already be gone
    }
  };

  const handleOpen = (doc: Attachment) => {
    if (doc.is_image) {
      setPreview(doc);
    } else {
      window.open(doc.download_url, "_blank", "noopener,noreferrer");
    }
  };

  const countFor = (type: AttachmentType) =>
    docs.filter((d) => d.is_active && d.attachment_type === type).length;

  return (
    <div className="space-y-4">
      {/* Category chips */}
      <div className="flex gap-1.5 flex-wrap">
        {DOC_FILTER_CHIPS.map((chip) => (
          <button
            key={chip.value}
            onClick={() => setActiveType(chip.value)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
              activeType === chip.value
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
            }`}
          >
            {chip.label}
            {chip.value !== "ALL" && (
              <span className="ml-1 opacity-70">({countFor(chip.value as AttachmentType)})</span>
            )}
          </button>
        ))}
      </div>

      {/* Search + upload row */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by filename or caption…"
          className="h-8 flex-1 min-w-48 rounded-md border border-input bg-background px-3 text-xs"
        />
        <select
          value={uploadType}
          onChange={(e) => setUploadType(e.target.value as AttachmentType)}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs"
        >
          {SUPPLIER_DOC_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
          <Upload className="w-3.5 h-3.5 mr-1.5" />
          {uploading ? "Uploading…" : "Upload"}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.heic,.doc,.docx,.xls,.xlsx"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>

      {uploadError && <p className="text-xs text-destructive">{uploadError}</p>}

      {/* Document list */}
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-10 text-center text-sm text-muted-foreground border border-dashed border-border rounded-lg">
          {search || activeType !== "ALL"
            ? "No documents match your filter."
            : "No documents uploaded yet. Use the upload button to add documents."}
        </div>
      ) : (
        <div className="divide-y divide-border border border-border rounded-lg overflow-hidden">
          {filtered.map((doc) => (
            <DocRow key={doc.id} doc={doc} onOpen={handleOpen} onDelete={handleDelete} />
          ))}
        </div>
      )}

      {/* Image lightbox */}
      {preview && (
        <Modal open={!!preview} onClose={() => setPreview(null)} title={preview.file_name} size="lg">
          <div className="p-4 flex flex-col items-center gap-3">
            <img
              src={preview.download_url}
              alt={preview.file_name}
              className="max-w-full max-h-[65vh] object-contain rounded"
            />
            <a
              href={preview.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary hover:underline flex items-center gap-1"
            >
              <Download className="w-3 h-3" />
              Open full size
            </a>
          </div>
        </Modal>
      )}
    </div>
  );
}

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
        <h2 className="text-sm font-semibold mb-4">Document Centre</h2>
        <SupplierDocCentre supplierId={supplier.id} />
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
