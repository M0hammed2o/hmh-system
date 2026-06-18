import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Building2, Edit2, CheckCircle2, XCircle,
  FileText, Download, Trash2, Upload, ChevronDown, ChevronRight,
  Plus, ClipboardList, Package, Truck, Receipt, CreditCard, ExternalLink,
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
  type POChain,
  type SupplierProcurementHistory,
  type StandaloneQuotation,
  type SupplierDocument,
  type SupplierDocType,
} from "@/api/suppliers";
import { attachmentsApi } from "@/api/attachments";
import { gmailApi } from "@/api/gmail";
import {
  quotationsApi,
  type QuotationCreate,
  type QuotationUpdate,
  type QuotationStatus,
  QUOTATION_STATUS_LABELS,
} from "@/api/quotations";

// ─── Document Centre ──────────────────────────────────────────────────────────

const DOC_FILTER_CHIPS: { value: SupplierDocType | "ALL"; label: string }[] = [
  { value: "ALL",            label: "All" },
  { value: "PURCHASE_ORDER", label: "Purchase Orders" },
  { value: "INVOICE",        label: "Invoices" },
  { value: "DELIVERY_NOTE",  label: "Delivery Notes" },
  { value: "QUOTATION",      label: "Quotations" },
  { value: "ATTACHMENT",     label: "Other Documents" },
];

const DOC_TYPE_LABELS: Record<SupplierDocType, string> = {
  PURCHASE_ORDER: "Purchase Order",
  INVOICE:        "Invoice",
  DELIVERY_NOTE:  "Delivery Note",
  QUOTATION:      "Quotation",
  ATTACHMENT:     "Document",
};

const STATUS_COLOURS: Record<string, string> = {
  DRAFT:              "text-yellow-600 bg-yellow-50",
  PENDING:            "text-yellow-600 bg-yellow-50",
  APPROVED:           "text-green-600 bg-green-50",
  RECEIVED:           "text-green-600 bg-green-50",
  PARTIALLY_RECEIVED: "text-blue-600 bg-blue-50",
  REJECTED:           "text-red-600 bg-red-50",
  CANCELLED:          "text-muted-foreground bg-muted",
  PAID:               "text-green-700 bg-green-100",
};

function SupplierDocRow({
  doc,
  onDeleteAttachment,
  onPreview,
  onDownloadGmail,
}: {
  doc: SupplierDocument;
  onDeleteAttachment: (id: string) => void;
  onPreview: (doc: SupplierDocument) => void;
  onDownloadGmail?: (attId: string) => void;
}) {
  const typeLabel = DOC_TYPE_LABELS[doc.doc_type] ?? doc.doc_type;
  const statusColour = doc.status ? (STATUS_COLOURS[doc.status] ?? "text-muted-foreground bg-muted") : "";
  const dateStr = doc.date
    ? new Date(doc.date).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })
    : "—";
  const fmt = (n: number) => `R ${n.toLocaleString("en-ZA", { minimumFractionDigits: 2 })}`;

  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors group">
      <div className="shrink-0 w-9 h-9 rounded-lg bg-muted flex items-center justify-center overflow-hidden">
        {doc.is_attachment && doc.is_image && doc.file_url ? (
          <img src={doc.file_url} alt="" className="w-9 h-9 object-cover" />
        ) : (
          <FileText className="w-4 h-4 text-muted-foreground" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate leading-tight">{doc.title}</div>
        {doc.caption && (
          <p className="text-xs text-muted-foreground truncate mt-0.5">{doc.caption}</p>
        )}
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          <Badge variant="outline" className="text-xs font-normal py-0 px-1.5 h-4">
            {typeLabel}
          </Badge>
          {doc.status && (
            <span className={`text-xs px-1.5 py-0 rounded font-medium ${statusColour}`}>
              {doc.status.replace(/_/g, " ")}
            </span>
          )}
          {doc.amount != null && (
            <span className="text-xs font-medium text-foreground">{fmt(doc.amount)}</span>
          )}
          {doc.file_size_display && (
            <span className="text-xs text-muted-foreground">{doc.file_size_display}</span>
          )}
          <span className="text-xs text-muted-foreground">{dateStr}</span>
          {doc.uploaded_by_name && (
            <span className="text-xs text-muted-foreground">· {doc.uploaded_by_name}</span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        {doc.gmail_attachment_id ? (
          <button
            onClick={() => onDownloadGmail?.(doc.gmail_attachment_id!)}
            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="View / Download from email"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
        ) : doc.file_url ? (
          <a
            href={doc.file_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={doc.is_image ? (e) => { e.preventDefault(); onPreview(doc); } : undefined}
            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Open / Download"
          >
            <Download className="w-3.5 h-3.5" />
          </a>
        ) : doc.detail_path ? (
          <a
            href={doc.detail_path}
            className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="View record"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        ) : null}
        {doc.is_attachment && !doc.gmail_attachment_id && (
          <button
            onClick={() => onDeleteAttachment(doc.doc_id)}
            className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
            title="Delete"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

function SupplierDocCentre({ supplierId }: { supplierId: string }) {
  const [docs, setDocs] = useState<SupplierDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeType, setActiveType] = useState<SupplierDocType | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [preview, setPreview] = useState<SupplierDocument | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocs = () => {
    setLoading(true);
    suppliersApi.documents(supplierId)
      .then(setDocs)
      .catch(() => setDocs([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadDocs(); }, [supplierId]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = docs.filter((d) => {
    const matchesType = activeType === "ALL" || d.doc_type === activeType;
    const q = search.toLowerCase();
    const matchesSearch =
      !q ||
      (d.title || "").toLowerCase().includes(q) ||
      (d.ref_number || "").toLowerCase().includes(q) ||
      (d.caption ?? "").toLowerCase().includes(q);
    return matchesType && matchesSearch;
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
      await attachmentsApi.upload(file, "SUPPLIER", supplierId, "INVOICE_COPY");
      loadDocs();
    } catch {
      setUploadError("Upload failed. Please try again.");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleDeleteAttachment = async (id: string) => {
    if (!window.confirm("Delete this document?")) return;
    try {
      await attachmentsApi.delete(id);
      setDocs((prev) => prev.filter((d) => d.doc_id !== id));
    } catch {
      // silent
    }
  };

  const handleDownloadGmail = async (attId: string) => {
    try {
      const { blob, filename } = await gmailApi.getAttachmentBlob(attId, true);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch {
      // ignore — file may be missing from disk
    }
  };

  const countFor = (type: SupplierDocType) =>
    docs.filter((d) => d.doc_type === type).length;

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
              <span className="ml-1 opacity-70">({countFor(chip.value as SupplierDocType)})</span>
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
          placeholder="Search by title, reference, or caption…"
          className="h-8 flex-1 min-w-48 rounded-md border border-input bg-background px-3 text-xs"
        />
        <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
          <Upload className="w-3.5 h-3.5 mr-1.5" />
          {uploading ? "Uploading…" : "Upload Document"}
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
            : "No documents yet. Purchase orders, invoices, and deliveries will appear here automatically."}
        </div>
      ) : (
        <div className="divide-y divide-border border border-border rounded-lg overflow-hidden">
          {filtered.map((doc) => (
            <SupplierDocRow
              key={doc.doc_id}
              doc={doc}
              onDeleteAttachment={handleDeleteAttachment}
              onPreview={setPreview}
              onDownloadGmail={handleDownloadGmail}
            />
          ))}
        </div>
      )}

      {/* Image lightbox */}
      {preview?.file_url && (
        <Modal open={!!preview} onClose={() => setPreview(null)} title={preview.title} size="lg">
          <div className="p-4 flex flex-col items-center gap-3">
            <img
              src={preview.file_url}
              alt={preview.title}
              className="max-w-full max-h-[65vh] object-contain rounded"
            />
            <a
              href={preview.file_url}
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

// ─── Procurement History ──────────────────────────────────────────────────────

const fmt = (n: number) =>
  `R ${n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const fmtDate = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })
    : "—";

function QuotationStatusBadge({ status }: { status: string }) {
  const variants: Record<string, string> = {
    DRAFT:    "bg-muted text-muted-foreground",
    SENT:     "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    RECEIVED: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
    APPROVED: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    REJECTED: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    EXPIRED:  "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
  };
  const label = QUOTATION_STATUS_LABELS[status as QuotationStatus] ?? status;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${variants[status] ?? "bg-muted text-muted-foreground"}`}>
      {label}
    </span>
  );
}

function PoStatusBadge({ status }: { status: string }) {
  const labelMap: Record<string, string> = {
    DRAFT: "Draft", SUBMITTED: "Submitted", PENDING_APPROVAL: "Pending Approval",
    APPROVED: "Approved", REJECTED: "Rejected", SENT: "Sent",
    SUPPLIER_CONFIRMED: "Confirmed", ORDERED: "Ordered",
    PARTIALLY_RECEIVED: "Partially Delivered", RECEIVED: "Delivered",
    INVOICED: "Invoiced", PARTIALLY_PAID: "Partially Paid",
    PAID: "Paid", CANCELLED: "Cancelled", CLOSED: "Closed",
  };
  const colorMap: Record<string, string> = {
    DRAFT: "secondary", SUBMITTED: "outline", APPROVED: "outline",
    SENT: "outline", SUPPLIER_CONFIRMED: "outline", ORDERED: "outline",
    PARTIALLY_RECEIVED: "warning", RECEIVED: "success",
    INVOICED: "outline", PAID: "success", CANCELLED: "destructive",
  };
  return (
    <Badge variant={(colorMap[status] as any) ?? "secondary"} className="text-xs">
      {labelMap[status] ?? status}
    </Badge>
  );
}

function ChainStep({
  icon: Icon,
  label,
  present,
  status,
  detail,
}: {
  icon: React.ElementType;
  label: string;
  present: boolean;
  status?: string | null;
  detail?: string | null;
}) {
  const doneStatuses = new Set(["APPROVED", "RECEIVED", "PAID", "SUPPLIER_CONFIRMED", "MATCHED", "CLOSED"]);
  const activeStatuses = new Set(["SENT", "PARTIALLY_RECEIVED", "INVOICED", "PARTIALLY_PAID", "ORDERED"]);
  const badStatuses = new Set(["CANCELLED", "REJECTED", "EXPIRED"]);

  let dotColor = "bg-muted text-muted-foreground";
  let textColor = "text-muted-foreground";
  if (!present) {
    dotColor = "bg-muted/50 text-muted-foreground/50";
    textColor = "text-muted-foreground/50";
  } else if (status && badStatuses.has(status)) {
    dotColor = "bg-destructive/20 text-destructive";
    textColor = "text-destructive";
  } else if (status && doneStatuses.has(status)) {
    dotColor = "bg-success/20 text-success";
    textColor = "text-foreground";
  } else if (status && activeStatuses.has(status)) {
    dotColor = "bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400";
    textColor = "text-foreground";
  } else if (present) {
    dotColor = "bg-primary/10 text-primary";
    textColor = "text-foreground";
  }

  return (
    <div className="flex items-start gap-2 min-w-0">
      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${dotColor}`}>
        <Icon className="w-3.5 h-3.5" />
      </div>
      <div className="min-w-0">
        <p className={`text-xs font-medium ${textColor}`}>{label}</p>
        {detail && present && (
          <p className="text-xs text-muted-foreground truncate max-w-[120px]">{detail}</p>
        )}
        {!present && (
          <p className="text-xs text-muted-foreground/50">Not recorded</p>
        )}
      </div>
    </div>
  );
}

function POChainCard({
  po,
  supplierId,
  onRefresh,
}: {
  po: POChain;
  supplierId: string;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const cs = po.chain_status;

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      {/* Summary row */}
      <button
        onClick={() => setExpanded((p) => !p)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold font-mono">{po.po_number}</span>
            <PoStatusBadge status={po.status} />
            {po.quotation && (
              <span className="text-xs text-muted-foreground">· Q: {po.quotation.quote_number}</span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            <span className="text-xs text-muted-foreground">{fmtDate(po.po_date)}</span>
            <span className="text-xs font-medium">{fmt(po.total_amount)}</span>
            {po.invoices.length > 0 && (
              <span className="text-xs text-muted-foreground">
                · Paid: {fmt(cs.total_paid)} / {fmt(cs.total_invoiced)}
              </span>
            )}
          </div>
        </div>

        {/* Mini chain indicators */}
        <div className="hidden sm:flex items-center gap-1 shrink-0">
          {[
            { ok: cs.has_mr, label: "MR" },
            { ok: cs.has_quotation, label: "Q" },
            { ok: true, label: "PO" },
            { ok: cs.has_delivery, label: "Del" },
            { ok: cs.has_invoice, label: "Inv" },
            { ok: cs.is_fully_paid, label: "Paid" },
          ].map((step) => (
            <span
              key={step.label}
              className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                step.ok
                  ? "bg-success/15 text-success"
                  : "bg-muted text-muted-foreground/50"
              }`}
            >
              {step.label}
            </span>
          ))}
        </div>

        {expanded ? (
          <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
        )}
      </button>

      {/* Expanded chain */}
      {expanded && (
        <div className="border-t border-border bg-muted/20 px-4 py-4 space-y-4">
          {/* Chain steps */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
            <ChainStep
              icon={ClipboardList}
              label="Order Note / MR"
              present={cs.has_mr}
              detail={cs.has_mr ? "Linked" : undefined}
            />
            <ChainStep
              icon={FileText}
              label="Quotation"
              present={cs.has_quotation}
              status={cs.quotation_status}
              detail={po.quotation?.quote_number}
            />
            <ChainStep
              icon={Package}
              label="Purchase Order"
              present={true}
              status={cs.po_status}
              detail={po.po_number}
            />
            <ChainStep
              icon={Truck}
              label="Delivery"
              present={cs.has_delivery}
              status={cs.delivery_status}
              detail={cs.has_delivery ? `${po.deliveries.length} delivery${po.deliveries.length !== 1 ? "ies" : ""}` : undefined}
            />
            <ChainStep
              icon={Receipt}
              label="Invoice"
              present={cs.has_invoice}
              status={cs.invoice_status}
              detail={cs.has_invoice ? po.invoices[0].invoice_number : undefined}
            />
            <ChainStep
              icon={CreditCard}
              label="Payment"
              present={cs.is_fully_paid}
              status={cs.is_fully_paid ? "PAID" : cs.has_invoice && cs.total_paid > 0 ? "PARTIALLY_PAID" : undefined}
              detail={cs.total_paid > 0 ? fmt(cs.total_paid) : undefined}
            />
          </div>

          {/* Deliveries detail */}
          {po.deliveries.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Deliveries
              </p>
              <div className="space-y-1">
                {po.deliveries.map((d) => (
                  <div key={d.delivery_id} className="flex items-center gap-3 text-xs">
                    <span className="font-mono text-muted-foreground">{d.delivery_number}</span>
                    <span className="text-muted-foreground">{fmtDate(d.delivery_date)}</span>
                    {d.status && <Badge variant="outline" className="text-xs py-0 h-4">{d.status}</Badge>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Invoices detail */}
          {po.invoices.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Invoices
              </p>
              <div className="space-y-1">
                {po.invoices.map((inv) => (
                  <div key={inv.invoice_id} className="flex items-center gap-3 text-xs flex-wrap">
                    <span className="font-mono font-medium">{inv.invoice_number}</span>
                    <span className="text-muted-foreground">{fmt(inv.total_amount)}</span>
                    <span className={inv.balance_due > 0 ? "text-amber-600" : "text-success"}>
                      {inv.balance_due > 0 ? `Owing: ${fmt(inv.balance_due)}` : "Paid"}
                    </span>
                    {inv.due_date && (
                      <span className="text-muted-foreground">Due: {fmtDate(inv.due_date)}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* PO amounts */}
          <div className="flex items-center gap-4 pt-1 border-t border-border/50 text-xs text-muted-foreground flex-wrap">
            <span>Net: {fmt(po.subtotal_amount)}</span>
            <span>VAT: {fmt(po.vat_amount)}</span>
            <span className="font-medium text-foreground">Total: {fmt(po.total_amount)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function QuotationModal({
  open,
  onClose,
  supplierId,
  existing,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  supplierId: string;
  existing: StandaloneQuotation | null;
  onSave: () => void;
}) {
  const [quoteNumber, setQuoteNumber] = useState(existing?.quote_number ?? "");
  const [status, setStatus] = useState<QuotationStatus>((existing?.status as QuotationStatus) ?? "DRAFT");
  const [quoteDate, setQuoteDate] = useState(existing?.quote_date ?? "");
  const [expiryDate, setExpiryDate] = useState(existing?.expiry_date ?? "");
  const [vatRate, setVatRate] = useState(String(existing?.vat_rate_used ?? 15));
  const [netAmount, setNetAmount] = useState(String(existing?.net_amount ?? 0));
  const [vatAmount, setVatAmount] = useState(String(existing?.vat_amount ?? 0));
  const [grossAmount, setGrossAmount] = useState(String(existing?.gross_amount ?? 0));
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setQuoteNumber(existing?.quote_number ?? "");
    setStatus((existing?.status as QuotationStatus) ?? "DRAFT");
    setQuoteDate(existing?.quote_date ?? "");
    setExpiryDate(existing?.expiry_date ?? "");
    setVatRate(String(existing?.vat_rate_used ?? 15));
    setNetAmount(String(existing?.net_amount ?? 0));
    setVatAmount(String(existing?.vat_amount ?? 0));
    setGrossAmount(String(existing?.gross_amount ?? 0));
    setNotes(existing?.notes ?? "");
    setError("");
  }, [open, existing]);

  const handleNetChange = (val: string) => {
    setNetAmount(val);
    const net = parseFloat(val) || 0;
    const rate = parseFloat(vatRate) || 0;
    const vat = parseFloat((net * rate / 100).toFixed(2));
    setVatAmount(String(vat));
    setGrossAmount(String(parseFloat((net + vat).toFixed(2))));
  };

  const handleSubmit = async () => {
    if (!quoteNumber.trim()) { setError("Quote number is required."); return; }
    setSaving(true);
    setError("");
    try {
      const payload = {
        quote_number: quoteNumber.trim(),
        supplier_id: supplierId,
        status,
        quote_date: quoteDate || null,
        expiry_date: expiryDate || null,
        net_amount: parseFloat(netAmount) || 0,
        vat_amount: parseFloat(vatAmount) || 0,
        gross_amount: parseFloat(grossAmount) || 0,
        vat_rate_used: parseFloat(vatRate) || 15,
        notes: notes.trim() || null,
      };
      if (existing) {
        await quotationsApi.update(existing.quotation_id, payload as QuotationUpdate);
      } else {
        await quotationsApi.create(payload as QuotationCreate);
      }
      onSave();
      onClose();
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          "Failed to save quotation."
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={existing ? "Edit Quotation" : "New Quotation"}
      size="md"
    >
      <div className="p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground block mb-1">Quote Number *</label>
            <input
              type="text"
              value={quoteNumber}
              onChange={(e) => setQuoteNumber(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm font-mono"
              placeholder="e.g. Q-2026-001"
              disabled={!!existing}
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as QuotationStatus)}
              className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm"
            >
              {(["DRAFT", "SENT", "RECEIVED", "APPROVED", "REJECTED", "EXPIRED"] as QuotationStatus[]).map((s) => (
                <option key={s} value={s}>{QUOTATION_STATUS_LABELS[s]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">VAT Rate (%)</label>
            <input
              type="number"
              value={vatRate}
              onChange={(e) => setVatRate(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="15"
              min="0"
              max="100"
              step="0.01"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Quote Date</label>
            <input
              type="date"
              value={quoteDate}
              onChange={(e) => setQuoteDate(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Expiry Date</label>
            <input
              type="date"
              value={expiryDate}
              onChange={(e) => setExpiryDate(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">Net Amount (excl. VAT)</label>
            <input
              type="number"
              value={netAmount}
              onChange={(e) => handleNetChange(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="0.00"
              min="0"
              step="0.01"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1">VAT Amount</label>
            <input
              type="number"
              value={vatAmount}
              onChange={(e) => setVatAmount(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              placeholder="0.00"
              min="0"
              step="0.01"
            />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-muted-foreground block mb-1">Gross Amount (incl. VAT)</label>
            <input
              type="number"
              value={grossAmount}
              onChange={(e) => setGrossAmount(e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm font-semibold"
              placeholder="0.00"
              min="0"
              step="0.01"
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
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={handleSubmit} disabled={saving || !quoteNumber.trim()}>
            {saving ? "Saving…" : existing ? "Save Changes" : "Create Quotation"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function ProcurementHistoryTab({ supplierId }: { supplierId: string }) {
  const [history, setHistory] = useState<SupplierProcurementHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [showQuotationModal, setShowQuotationModal] = useState(false);
  const [editQuotation, setEditQuotation] = useState<StandaloneQuotation | null>(null);
  const [poFilter, setPoFilter] = useState("");

  const load = () => {
    setLoading(true);
    suppliersApi
      .procurementHistory(supplierId)
      .then(setHistory)
      .catch(() => setHistory(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [supplierId]);

  const filteredPos = (history?.purchase_orders ?? []).filter(
    (po) =>
      !poFilter ||
      po.po_number.toLowerCase().includes(poFilter.toLowerCase()) ||
      (po.quotation?.quote_number ?? "").toLowerCase().includes(poFilter.toLowerCase())
  );

  const handleDeleteQuotation = async (id: string) => {
    if (!window.confirm("Delete this quotation?")) return;
    try {
      await quotationsApi.delete(id);
      load();
    } catch {
      /* silent */
    }
  };

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Purchase Orders */}
      <div>
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h3 className="text-sm font-semibold">Purchase Orders</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {history?.po_count ?? 0} total — click a row to expand the full procurement chain.
            </p>
          </div>
          <input
            type="text"
            value={poFilter}
            onChange={(e) => setPoFilter(e.target.value)}
            placeholder="Filter by PO or quote number…"
            className="h-8 rounded-md border border-input bg-background px-3 text-xs w-48"
          />
        </div>

        {filteredPos.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground border border-dashed border-border rounded-xl">
            {poFilter ? "No purchase orders match your filter." : "No purchase orders for this supplier yet."}
          </div>
        ) : (
          <div className="space-y-2">
            {filteredPos.map((po) => (
              <POChainCard key={po.po_id} po={po} supplierId={supplierId} onRefresh={load} />
            ))}
          </div>
        )}
      </div>

      {/* Standalone Quotations */}
      <div>
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h3 className="text-sm font-semibold">Quotations</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Standalone supplier quotations not yet converted to a Purchase Order.
            </p>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => { setEditQuotation(null); setShowQuotationModal(true); }}
          >
            <Plus className="w-3.5 h-3.5 mr-1.5" />
            New Quotation
          </Button>
        </div>

        {(history?.standalone_quotations ?? []).length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground border border-dashed border-border rounded-xl">
            No standalone quotations. Use the button above to record a supplier quotation.
          </div>
        ) : (
          <div className="divide-y divide-border border border-border rounded-xl overflow-hidden">
            {(history?.standalone_quotations ?? []).map((q) => (
              <div key={q.quotation_id} className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-mono font-semibold">{q.quote_number}</span>
                    <QuotationStatusBadge status={q.status} />
                    {q.expiry_date && new Date(q.expiry_date) < new Date() && q.status !== "EXPIRED" && (
                      <span className="text-xs text-amber-600">⚠ Expired</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                    {q.quote_date && (
                      <span className="text-xs text-muted-foreground">Date: {fmtDate(q.quote_date)}</span>
                    )}
                    {q.expiry_date && (
                      <span className="text-xs text-muted-foreground">Expires: {fmtDate(q.expiry_date)}</span>
                    )}
                    <span className="text-xs font-medium">{fmt(q.gross_amount)}</span>
                    <span className="text-xs text-muted-foreground">VAT @ {q.vat_rate_used}%</span>
                  </div>
                  {q.notes && (
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{q.notes}</p>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => { setEditQuotation(q); setShowQuotationModal(true); }}
                    className="text-xs text-primary hover:underline px-1.5 py-1"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDeleteQuotation(q.quotation_id)}
                    className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <QuotationModal
        open={showQuotationModal}
        onClose={() => setShowQuotationModal(false)}
        supplierId={supplierId}
        existing={editQuotation}
        onSave={load}
      />
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
  const [activeTab, setActiveTab] = useState<"documents" | "history">("documents");

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

      {/* Tabs: Documents | Procurement History */}
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="flex border-b border-border">
          <button
            onClick={() => setActiveTab("documents")}
            className={`px-5 py-3 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === "documents"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Document Centre
          </button>
          <button
            onClick={() => setActiveTab("history")}
            className={`px-5 py-3 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === "history"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Procurement History
          </button>
        </div>
        <div className="p-5">
          {activeTab === "documents" ? (
            <SupplierDocCentre supplierId={supplier.id} />
          ) : (
            <ProcurementHistoryTab supplierId={supplier.id} />
          )}
        </div>
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
