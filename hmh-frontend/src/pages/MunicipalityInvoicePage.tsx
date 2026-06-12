/**
 * Municipality Invoice — manual capture + Excel download.
 * No auto-send. No auto-approve. The office lady controls everything.
 */

import { useEffect, useState, useCallback } from "react";
import {
  Plus, Download, Trash2, Edit2, X, ChevronDown, ChevronUp,
  FileSpreadsheet, CheckCircle, RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { muniInvoiceApi, type MuniInvoice, type MuniInvoiceItem } from "@/api/municipalityInvoice";
import { projectsApi, type Project } from "@/api/projects";
import { cn } from "@/lib/utils";
import client from "@/api/client";

const fmt = (n: number | null | undefined) =>
  n == null ? "—" : `R${Number(n).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STATUS_COLOR: Record<string, string> = {
  DRAFT:      "bg-muted text-muted-foreground",
  FINALISED:  "bg-green-100 text-green-700",
};

// ── Empty line item ───────────────────────────────────────────────────────────

const emptyItem = (): MuniInvoiceItem => ({
  sort_order:  0,
  line_number: null,
  description: "",
  quantity:    null,
  unit_price:  null,
  total:       null,
  disc_pct:    null,
  comments:    null,
});

// ── Invoice form (create + edit) ──────────────────────────────────────────────

type InvoiceFormData = {
  cert_number:         string;
  invoice_number:      string;
  invoice_date:        string;
  client_name:         string;
  client_vat_no:       string;
  client_address:      string;
  company_email:       string;
  project_description: string;
  contract_reference:  string;
  previously_paid:     string;
  vat_rate:            string;
  notes:               string;
  bank_name:           string;
  account_number:      string;
  branch_name:         string;
  branch_code:         string;
  items:               MuniInvoiceItem[];
};

const defaultForm = (): InvoiceFormData => ({
  cert_number:         "",
  invoice_number:      "",
  invoice_date:        new Date().toISOString().slice(0, 10),
  client_name:         "Ethekweni Municipality",
  client_vat_no:       "",
  client_address:      "PO BOX 828,Durban\n4001",
  company_email:       "",
  project_description: "",
  contract_reference:  "",
  previously_paid:     "0",
  vat_rate:            "15",
  notes:               "",
  bank_name:           "FIRST NATIONAL BANK",
  account_number:      "",
  branch_name:         "",
  branch_code:         "",
  items:               [emptyItem()],
});

function fromInvoice(inv: MuniInvoice): InvoiceFormData {
  return {
    cert_number:         inv.cert_number         || "",
    invoice_number:      inv.invoice_number       || "",
    invoice_date:        inv.invoice_date         || new Date().toISOString().slice(0, 10),
    client_name:         inv.client_name          || "Ethekweni Municipality",
    client_vat_no:       inv.client_vat_no        || "",
    client_address:      inv.client_address       || "",
    company_email:       inv.company_email        || "",
    project_description: inv.project_description  || "",
    contract_reference:  inv.contract_reference   || "",
    previously_paid:     String(inv.previously_paid ?? 0),
    vat_rate:            String(inv.vat_rate       ?? 15),
    notes:               inv.notes                || "",
    bank_name:           inv.bank_name            || "",
    account_number:      inv.account_number       || "",
    branch_name:         inv.branch_name          || "",
    branch_code:         inv.branch_code          || "",
    items:               inv.items.length ? inv.items : [emptyItem()],
  };
}

// ── Item row editor ───────────────────────────────────────────────────────────

function ItemRow({
  item, idx, onChange, onRemove,
}: {
  item: MuniInvoiceItem;
  idx: number;
  onChange: (idx: number, field: keyof MuniInvoiceItem, val: unknown) => void;
  onRemove: (idx: number) => void;
}) {
  const lineTotal =
    item.quantity != null && item.unit_price != null
      ? item.quantity * item.unit_price
      : item.total;

  return (
    <tr className="border-b border-border hover:bg-muted/10">
      <td className="px-2 py-1.5 w-10">
        <input
          value={item.line_number ?? ""}
          onChange={e => onChange(idx, "line_number", e.target.value || null)}
          className="w-full h-7 rounded border border-input bg-background px-1.5 text-xs text-center"
          placeholder="#"
        />
      </td>
      <td className="px-2 py-1.5">
        <input
          value={item.description}
          onChange={e => onChange(idx, "description", e.target.value)}
          className="w-full h-7 rounded border border-input bg-background px-2 text-xs"
          placeholder="Description"
        />
      </td>
      <td className="px-2 py-1.5 w-20">
        <input
          type="number" step="0.001"
          value={item.quantity ?? ""}
          onChange={e => onChange(idx, "quantity", e.target.value === "" ? null : parseFloat(e.target.value))}
          className="w-full h-7 rounded border border-input bg-background px-1.5 text-xs text-right"
          placeholder="0"
        />
      </td>
      <td className="px-2 py-1.5 w-28">
        <input
          type="number" step="0.01"
          value={item.unit_price ?? ""}
          onChange={e => onChange(idx, "unit_price", e.target.value === "" ? null : parseFloat(e.target.value))}
          className="w-full h-7 rounded border border-input bg-background px-1.5 text-xs text-right"
          placeholder="0.00"
        />
      </td>
      <td className="px-2 py-1.5 w-28 text-right text-xs font-medium text-muted-foreground">
        {lineTotal != null ? fmt(lineTotal) : "—"}
      </td>
      <td className="px-2 py-1.5 w-24">
        <input
          value={item.comments ?? ""}
          onChange={e => onChange(idx, "comments", e.target.value || null)}
          className="w-full h-7 rounded border border-input bg-background px-1.5 text-xs"
          placeholder="Notes"
        />
      </td>
      <td className="px-2 py-1.5 w-8 text-center">
        <button onClick={() => onRemove(idx)} className="text-muted-foreground hover:text-destructive">
          <X className="w-3.5 h-3.5" />
        </button>
      </td>
    </tr>
  );
}

// ── Invoice form modal ────────────────────────────────────────────────────────

function InvoiceFormModal({
  projectId, editInvoice, onClose, onSaved,
}: {
  projectId: string;
  editInvoice: MuniInvoice | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<InvoiceFormData>(
    editInvoice ? fromInvoice(editInvoice) : defaultForm()
  );
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const f = <K extends keyof InvoiceFormData>(field: K, val: InvoiceFormData[K]) =>
    setForm(prev => ({ ...prev, [field]: val }));

  const updateItem = (idx: number, field: keyof MuniInvoiceItem, val: unknown) => {
    setForm(prev => {
      const items = [...prev.items];
      items[idx] = { ...items[idx], [field]: val } as MuniInvoiceItem;
      // Auto-compute total from qty × price
      const it = items[idx];
      if (it.quantity != null && it.unit_price != null) {
        items[idx] = { ...items[idx], total: parseFloat((it.quantity * it.unit_price).toFixed(2)) };
      }
      return { ...prev, items };
    });
  };

  const addItem = () =>
    setForm(prev => ({
      ...prev,
      items: [...prev.items, { ...emptyItem(), sort_order: prev.items.length }],
    }));

  const removeItem = (idx: number) =>
    setForm(prev => ({ ...prev, items: prev.items.filter((_, i) => i !== idx) }));

  // Live totals preview
  const previewSubtotal = form.items.reduce((s, it) => {
    const t = it.total ?? (it.quantity != null && it.unit_price != null ? it.quantity * it.unit_price : 0);
    return s + (t || 0);
  }, 0);
  const prevPaid = parseFloat(form.previously_paid || "0") || 0;
  const net = Math.max(0, previewSubtotal - prevPaid);
  const vatRate = parseFloat(form.vat_rate || "15") || 15;
  const previewVat = net * vatRate / 100;
  const previewDue = net + previewVat;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true); setError("");
    try {
      const payload = {
        cert_number:         form.cert_number         || null,
        invoice_number:      form.invoice_number       || undefined,
        invoice_date:        form.invoice_date,
        client_name:         form.client_name,
        client_vat_no:       form.client_vat_no        || null,
        client_address:      form.client_address       || null,
        company_email:       form.company_email        || null,
        project_description: form.project_description  || null,
        contract_reference:  form.contract_reference   || null,
        previously_paid:     parseFloat(form.previously_paid || "0") || 0,
        vat_rate:            parseFloat(form.vat_rate  || "15") || 15,
        notes:               form.notes                || null,
        bank_name:           form.bank_name            || null,
        account_number:      form.account_number       || null,
        branch_name:         form.branch_name          || null,
        branch_code:         form.branch_code          || null,
        items: form.items.map((it, i) => ({
          ...it,
          sort_order: i,
          total: it.total ?? (it.quantity != null && it.unit_price != null
            ? parseFloat((it.quantity * it.unit_price).toFixed(2)) : null),
        })),
      };
      if (editInvoice) {
        await muniInvoiceApi.update(editInvoice.id, payload);
      } else {
        await muniInvoiceApi.create(projectId, payload);
      }
      onSaved(); onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string; detail?: string } } })
        ?.response?.data?.message
        || (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Save failed.";
      setError(msg);
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-3">
      <div className="bg-card border border-border rounded-2xl w-full max-w-4xl max-h-[95vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border shrink-0">
          <h2 className="text-base font-semibold flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4" />
            {editInvoice ? "Edit Invoice" : "New Municipality Invoice"}
          </h2>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <form onSubmit={save} className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* ── Invoice header ── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Cert Number</label>
              <input value={form.cert_number}
                onChange={e => f("cert_number", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                placeholder="26"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Invoice Number</label>
              <input value={form.invoice_number}
                onChange={e => f("invoice_number", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                placeholder="Auto-generated"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Invoice Date *</label>
              <input type="date" required value={form.invoice_date}
                onChange={e => f("invoice_date", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Company Email</label>
              <input type="email" value={form.company_email}
                onChange={e => f("company_email", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                placeholder="you@company.co.za"
              />
            </div>
          </div>

          {/* ── Client ── */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Client Name *</label>
              <input required value={form.client_name}
                onChange={e => f("client_name", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Client VAT No</label>
              <input value={form.client_vat_no}
                onChange={e => f("client_vat_no", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                placeholder="4880193505"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Client Address</label>
              <textarea rows={2} value={form.client_address}
                onChange={e => f("client_address", e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm resize-none"
                placeholder="PO BOX 828,Durban"
              />
            </div>
          </div>

          {/* ── Contract ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Project Description</label>
              <input value={form.project_description}
                onChange={e => f("project_description", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                placeholder="Kwalinda Rural Housing Project"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Contract Reference</label>
              <input value={form.contract_reference}
                onChange={e => f("contract_reference", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                placeholder="Contract 1H-42037"
              />
            </div>
          </div>

          {/* ── Line items ── */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium">Line Items</label>
              <Button type="button" size="sm" variant="outline" onClick={addItem}>
                <Plus className="w-3.5 h-3.5 mr-1" />Add Row
              </Button>
            </div>
            <div className="overflow-x-auto border border-border rounded-lg">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/40 text-xs text-muted-foreground">
                    <th className="px-2 py-2 text-left w-10">#</th>
                    <th className="px-2 py-2 text-left">Description</th>
                    <th className="px-2 py-2 text-right w-20">Qty</th>
                    <th className="px-2 py-2 text-right w-28">Unit Price</th>
                    <th className="px-2 py-2 text-right w-28">Total</th>
                    <th className="px-2 py-2 text-left w-24">Notes</th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody>
                  {form.items.map((item, idx) => (
                    <ItemRow
                      key={idx}
                      item={item}
                      idx={idx}
                      onChange={updateItem}
                      onRemove={removeItem}
                    />
                  ))}
                  {form.items.length === 0 && (
                    <tr>
                      <td colSpan={7} className="text-center text-xs text-muted-foreground py-4">
                        No items yet — click Add Row
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Totals preview ── */}
          <div className="bg-muted/30 border border-border rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Previously Paid (R)</label>
              <input type="number" step="0.01" min="0"
                value={form.previously_paid}
                onChange={e => f("previously_paid", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-right"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">VAT Rate (%)</label>
              <input type="number" step="0.01" min="0"
                value={form.vat_rate}
                onChange={e => f("vat_rate", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-right"
              />
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Sub Total</p>
              <p className="font-bold text-sm">{fmt(previewSubtotal)}</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Now Due</p>
              <p className="font-bold text-base text-primary">{fmt(previewDue)}</p>
            </div>
          </div>

          {/* ── Notes ── */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Invoice Notes</label>
            <textarea rows={2} value={form.notes}
              onChange={e => f("notes", e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
              placeholder="In this invoice we are claiming for…"
            />
          </div>

          {/* ── Banking details ── */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="space-y-1 col-span-2 md:col-span-1">
              <label className="text-xs font-medium text-muted-foreground">Bank Name</label>
              <input value={form.bank_name}
                onChange={e => f("bank_name", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                placeholder="FIRST NATIONAL BANK"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Account No</label>
              <input value={form.account_number}
                onChange={e => f("account_number", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Branch</label>
              <input value={form.branch_name}
                onChange={e => f("branch_name", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Branch Code</label>
              <input value={form.branch_code}
                onChange={e => f("branch_code", e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </div>
          </div>

          {error && (
            <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </form>

        <div className="flex gap-2 px-5 py-4 border-t border-border shrink-0">
          <Button variant="outline" onClick={onClose} disabled={loading} className="flex-1">Cancel</Button>
          <Button disabled={loading} className="flex-1" onClick={e => {
            const form_el = (e.target as HTMLButtonElement).closest("div")?.previousElementSibling?.querySelector("form");
            form_el?.requestSubmit();
          }}>
            {loading ? "Saving…" : editInvoice ? "Save Changes" : "Create Invoice"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Invoice card ──────────────────────────────────────────────────────────────

function InvoiceCard({
  inv, onEdit, onDelete, onDownload, onFinalise,
}: {
  inv: MuniInvoice;
  onEdit: (inv: MuniInvoice) => void;
  onDelete: (inv: MuniInvoice) => void;
  onDownload: (inv: MuniInvoice) => void;
  onFinalise: (inv: MuniInvoice) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-border rounded-xl bg-card overflow-hidden">
      <div className="p-4 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs text-muted-foreground">{inv.invoice_number}</span>
            {inv.cert_number && (
              <span className="text-xs text-muted-foreground">Cert {inv.cert_number}</span>
            )}
            <span className={cn("text-[11px] font-semibold px-2 py-0.5 rounded-full",
              STATUS_COLOR[inv.status] || "bg-muted text-muted-foreground")}>
              {inv.status}
            </span>
          </div>
          <p className="text-sm font-medium mt-0.5">{inv.client_name}</p>
          {inv.project_description && (
            <p className="text-xs text-muted-foreground truncate">{inv.project_description}</p>
          )}
          <p className="text-xs text-muted-foreground mt-0.5">
            {inv.invoice_date} · {inv.items.length} line{inv.items.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="font-bold text-base">{fmt(inv.total_due)}</p>
          <p className="text-xs text-muted-foreground">incl. VAT</p>
        </div>
      </div>

      {/* Actions row */}
      <div className="flex items-center gap-1.5 px-4 pb-3 flex-wrap">
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1"
          onClick={() => onDownload(inv)}>
          <Download className="w-3 h-3" />Excel
        </Button>
        {inv.status === "DRAFT" && (
          <>
            <Button size="sm" variant="outline" className="h-7 text-xs gap-1"
              onClick={() => onEdit(inv)}>
              <Edit2 className="w-3 h-3" />Edit
            </Button>
            <Button size="sm" variant="outline" className="h-7 text-xs gap-1 text-green-700 hover:bg-green-50"
              onClick={() => onFinalise(inv)}>
              <CheckCircle className="w-3 h-3" />Finalise
            </Button>
            <Button size="sm" variant="outline" className="h-7 text-xs gap-1 text-destructive hover:bg-destructive/10"
              onClick={() => onDelete(inv)}>
              <Trash2 className="w-3 h-3" />Delete
            </Button>
          </>
        )}
        <button className="ml-auto text-muted-foreground hover:text-foreground"
          onClick={() => setExpanded(v => !v)}>
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {/* Expanded items */}
      {expanded && inv.items.length > 0 && (
        <div className="border-t border-border overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-muted/30 text-muted-foreground">
                <th className="px-3 py-1.5 text-left w-8">#</th>
                <th className="px-3 py-1.5 text-left">Description</th>
                <th className="px-3 py-1.5 text-right w-16">Qty</th>
                <th className="px-3 py-1.5 text-right w-24">Unit Price</th>
                <th className="px-3 py-1.5 text-right w-24">Total</th>
              </tr>
            </thead>
            <tbody>
              {inv.items.map((item, i) => (
                <tr key={i} className="border-t border-border/50">
                  <td className="px-3 py-1.5 text-muted-foreground">{item.line_number || i + 1}</td>
                  <td className="px-3 py-1.5">{item.description}</td>
                  <td className="px-3 py-1.5 text-right">{item.quantity ?? "—"}</td>
                  <td className="px-3 py-1.5 text-right">{fmt(item.unit_price)}</td>
                  <td className="px-3 py-1.5 text-right font-medium">{fmt(item.total)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-border bg-muted/20 font-semibold">
                <td colSpan={4} className="px-3 py-2 text-right text-muted-foreground">Sub Total</td>
                <td className="px-3 py-2 text-right">{fmt(inv.subtotal)}</td>
              </tr>
              {inv.previously_paid != null && inv.previously_paid > 0 && (
                <tr className="bg-muted/10">
                  <td colSpan={4} className="px-3 py-1 text-right text-muted-foreground">Less Previously Paid</td>
                  <td className="px-3 py-1 text-right text-destructive">({fmt(inv.previously_paid)})</td>
                </tr>
              )}
              <tr className="bg-muted/10">
                <td colSpan={4} className="px-3 py-1 text-right text-muted-foreground">VAT @ {inv.vat_rate}%</td>
                <td className="px-3 py-1 text-right">{fmt(inv.vat_amount)}</td>
              </tr>
              <tr className="bg-muted/20 font-bold text-base">
                <td colSpan={4} className="px-3 py-2 text-right">Now Due</td>
                <td className="px-3 py-2 text-right text-primary">{fmt(inv.total_due)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MunicipalityInvoicePage() {
  const [projects,  setProjects]  = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [invoices,  setInvoices]  = useState<MuniInvoice[]>([]);
  const [loading,   setLoading]   = useState(false);
  const [showForm,  setShowForm]  = useState(false);
  const [editInv,   setEditInv]   = useState<MuniInvoice | null>(null);
  const [filterStatus, setFilterStatus] = useState("");

  useEffect(() => {
    projectsApi.list().then(setProjects).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    if (!projectId) { setInvoices([]); return; }
    setLoading(true);
    try {
      const data = await muniInvoiceApi.list(projectId, filterStatus || undefined);
      setInvoices(data);
    } finally { setLoading(false); }
  }, [projectId, filterStatus]);

  useEffect(() => { load(); }, [load]);

  const handleDownload = async (inv: MuniInvoice) => {
    try {
      const res = await client.get(muniInvoiceApi.exportExcel(inv.id), { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a   = document.createElement("a");
      a.href    = url;
      a.download = `Invoice_${inv.invoice_number}_Cert${inv.cert_number || "NA"}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch { alert("Download failed."); }
  };

  const handleDelete = async (inv: MuniInvoice) => {
    if (!confirm(`Delete invoice ${inv.invoice_number}?`)) return;
    try {
      await muniInvoiceApi.delete(inv.id);
      await load();
    } catch { alert("Delete failed."); }
  };

  const handleFinalise = async (inv: MuniInvoice) => {
    if (!confirm(`Finalise invoice ${inv.invoice_number}? You will not be able to edit it afterwards.`)) return;
    try {
      await muniInvoiceApi.update(inv.id, { status: "FINALISED" } as Partial<MuniInvoice>);
      await load();
    } catch { alert("Finalise failed."); }
  };

  const totalDue = invoices.reduce((s, i) => s + i.total_due, 0);

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5" />
            Municipality Invoices
          </h1>
          <p className="text-sm text-muted-foreground">
            Manual invoice capture — download as Excel, send yourself
          </p>
        </div>
        <Button size="sm" onClick={() => { setEditInv(null); setShowForm(true); }} disabled={!projectId}>
          <Plus className="w-4 h-4 mr-1" />New Invoice
        </Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <select value={projectId} onChange={e => setProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm flex-1 min-w-[180px]">
          <option value="">— Select project —</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm">
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="FINALISED">Finalised</option>
        </select>
        <Button variant="ghost" size="sm" onClick={load} disabled={loading || !projectId}>
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </Button>
      </div>

      {/* Summary strip */}
      {invoices.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Total Invoices", value: invoices.length.toString() },
            { label: "Draft",          value: invoices.filter(i => i.status === "DRAFT").length.toString() },
            { label: "Total Due",      value: fmt(totalDue) },
          ].map(({ label, value }) => (
            <div key={label} className="border border-border rounded-xl p-3 bg-card text-center">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="font-bold text-sm">{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* List */}
      {!projectId ? (
        <div className="text-center py-12 text-muted-foreground text-sm">
          Select a project to view invoices.
        </div>
      ) : loading ? (
        <div className="space-y-3">
          {[1, 2].map(i => <Skeleton key={i} className="h-28 rounded-xl" />)}
        </div>
      ) : invoices.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground text-sm">
          No invoices yet. Click New Invoice to create one.
        </div>
      ) : (
        <div className="space-y-3">
          {invoices.map(inv => (
            <InvoiceCard
              key={inv.id}
              inv={inv}
              onEdit={inv => { setEditInv(inv); setShowForm(true); }}
              onDelete={handleDelete}
              onDownload={handleDownload}
              onFinalise={handleFinalise}
            />
          ))}
        </div>
      )}

      {showForm && projectId && (
        <InvoiceFormModal
          projectId={projectId}
          editInvoice={editInv}
          onClose={() => { setShowForm(false); setEditInv(null); }}
          onSaved={load}
        />
      )}
    </div>
  );
}
