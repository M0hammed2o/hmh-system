/**
 * CreateInvoiceFromSuggestionModal
 *
 * Lets an office/admin user create an Invoice record from a Gmail OCR suggestion.
 * Pre-fills fields from OCR extraction but allows correction before submitting.
 * Preserves original OCR values in the Notes field for audit purposes.
 * NEVER auto-submits — user must confirm each field and click Create.
 */
import { useState, useEffect } from "react";
import { CheckCircle2, AlertTriangle, Info, Sparkles } from "lucide-react";
import { Modal } from "@/components/shared/Modal";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  gmailApi,
  type ReconciliationSuggestion,
} from "@/api/gmail";
import {
  documentAiApi,
  type AIExtractionResult,
  confidenceTier,
  CONF_BADGE,
} from "@/api/documentAi";
import client from "@/api/client";

interface Project {
  id: string;
  name: string;
  code: string;
}

interface Supplier {
  id: string;
  name: string;
  email: string | null;
}

interface Props {
  open:       boolean;
  onClose:    () => void;
  suggestion: ReconciliationSuggestion;
  onCreated:  (invoiceId: string) => void;
}

export function CreateInvoiceFromSuggestionModal({ open, onClose, suggestion, onCreated }: Props) {
  const [projects,    setProjects]    = useState<Project[]>([]);
  const [suppliers,   setSuppliers]   = useState<Supplier[]>([]);
  const [saving,      setSaving]      = useState(false);
  const [error,       setError]       = useState("");
  const [aiResult,    setAIResult]    = useState<AIExtractionResult | null>(null);
  const [aiLoading,   setAILoading]   = useState(false);

  // Editable fields — pre-filled from OCR suggestion
  const [projectId,   setProjectId]   = useState("");
  const [supplierId,  setSupplierId]  = useState("");
  const [invoiceNum,  setInvoiceNum]  = useState(suggestion.invoice_number ?? "");
  const [totalAmount, setTotalAmount] = useState(String(suggestion.total_amount ?? ""));
  const [notes,       setNotes]       = useState("");

  // Track which fields were overridden from OCR values
  const ocrInvoiceNum  = suggestion.invoice_number  ?? "";
  const ocrTotal       = String(suggestion.total_amount ?? "");
  const invoiceChanged = invoiceNum  !== ocrInvoiceNum && ocrInvoiceNum !== "";
  const totalChanged   = totalAmount !== ocrTotal     && ocrTotal       !== "";

  useEffect(() => {
    if (!open) return;
    setError("");
    setAIResult(null);
    setInvoiceNum(suggestion.invoice_number ?? "");
    setTotalAmount(String(suggestion.total_amount ?? ""));
    setNotes("");

    client.get<{ data: { items: Project[] } }>("/projects/", { params: { limit: 100 } })
      .then(r => setProjects(r.data.data?.items ?? []))
      .catch(() => {});

    client.get<{ data: Supplier[] }>("/suppliers/", { params: { include_inactive: false } })
      .then(r => setSuppliers(r.data.data ?? []))
      .catch(() => {});

    // Fetch existing AI extraction result if available (non-blocking)
    if (suggestion.attachment_id) {
      documentAiApi.getAIExtraction(suggestion.attachment_id)
        .then(result => setAIResult(result))
        .catch(() => {}); // 404 is expected when AI hasn't been run yet
    }
  }, [open, suggestion]);

  // Auto-select supplier if OCR matched one by name
  useEffect(() => {
    if (suggestion.supplier_name && suppliers.length > 0) {
      const lower = suggestion.supplier_name.toLowerCase();
      const match = suppliers.find(s => s.name.toLowerCase().includes(lower));
      if (match && !supplierId) setSupplierId(match.id);
    }
  }, [suppliers, suggestion.supplier_name, supplierId]);

  const handleCreate = async () => {
    if (!projectId) { setError("Please select a project."); return; }
    if (!suggestion.attachment_id) { setError("No attachment ID — cannot create invoice."); return; }

    setSaving(true); setError("");

    // Build notes: record original OCR values for any overridden fields
    const auditLines: string[] = [];
    if (invoiceChanged) auditLines.push(`Invoice # overridden from OCR value: "${ocrInvoiceNum}"`);
    if (totalChanged)   auditLines.push(`Total overridden from OCR value: R${ocrTotal}`);
    const finalNotes = [
      notes.trim(),
      `Created from Gmail OCR suggestion (confidence: ${(suggestion.match_confidence * 100).toFixed(0)}%).`,
      ...auditLines,
    ].filter(Boolean).join(" | ");

    try {
      const res = await gmailApi.createInvoiceFromGmail(suggestion.attachment_id, {
        project_id:         projectId,
        supplier_id:        supplierId || null,
        purchase_order_id:  suggestion.matched_po_id ?? null,
        invoice_number:     invoiceNum.trim() || null,
        total_amount:       parseFloat(totalAmount) || 0,
        notes:              finalNotes,
      });
      onCreated(res.invoice_id);
      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to create invoice. Check that the project and supplier are valid.");
    } finally {
      setSaving(false);
    }
  };

  const conf = suggestion.match_confidence;
  const confColor = conf >= 0.75 ? "text-green-600" : conf >= 0.40 ? "text-amber-600" : "text-red-600";
  const confBg    = conf >= 0.75 ? "bg-green-50 border-green-200" : conf >= 0.40 ? "bg-amber-50 border-amber-200" : "bg-red-50 border-red-200";

  return (
    <Modal open={open} onClose={onClose} title="Create Invoice from OCR Suggestion" size="lg">
      <div className="px-6 py-4 space-y-4 text-sm">

        {/* Confidence summary */}
        <div className={cn("flex items-start gap-3 rounded-lg border p-3", confBg)}>
          {conf >= 0.75
            ? <CheckCircle2 className={cn("w-4 h-4 mt-0.5 shrink-0", confColor)} />
            : <AlertTriangle className={cn("w-4 h-4 mt-0.5 shrink-0", confColor)} />
          }
          <div className="min-w-0">
            <p className={cn("font-semibold", confColor)}>
              Match confidence: {(conf * 100).toFixed(0)}%
              {suggestion.matched_po && <span className="ml-2 text-foreground font-normal">→ {suggestion.matched_po}</span>}
            </p>
            {suggestion.issues.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                {suggestion.issues.map((issue, i) => (
                  <li key={i} className="flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full bg-current shrink-0 inline-block" />
                    {issue.replace(/_/g, " ")}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* AI extraction panel */}
        {aiResult ? (
          <div className="rounded-lg border border-border overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 bg-muted/40 border-b border-border">
              <Sparkles className="w-3.5 h-3.5 text-primary shrink-0" />
              <span className="text-xs font-semibold flex-1">AI Extraction Results</span>
              <span className={cn(
                "text-[10px] font-bold px-1.5 py-0.5 rounded border",
                CONF_BADGE[confidenceTier(aiResult.overall_confidence)]
              )}>
                {(aiResult.overall_confidence * 100).toFixed(0)}% overall
              </span>
            </div>
            <div className="divide-y divide-border">
              {(Object.entries(aiResult.header) as [string, { value: string | number | null; confidence: number }][]).map(([key, field]) => {
                const tier = confidenceTier(field.confidence);
                const label = key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
                return (
                  <div key={key} className={cn(
                    "flex items-center justify-between gap-2 px-3 py-1.5 text-xs",
                    tier === "low" && "bg-red-50/50",
                  )}>
                    <span className="text-muted-foreground shrink-0">{label}</span>
                    <div className="flex items-center gap-2">
                      <span className={cn("font-semibold", field.value == null && "text-muted-foreground italic")}>
                        {field.value != null ? String(field.value) : "—"}
                      </span>
                      <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded border", CONF_BADGE[tier])}>
                        {(field.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
            {aiResult.warnings.length > 0 && (
              <div className="px-3 py-2 bg-amber-50 border-t border-border text-xs text-amber-700 space-y-0.5">
                {aiResult.warnings.map((w, i) => (
                  <div key={i} className="flex items-start gap-1.5">
                    <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : suggestion.attachment_id ? (
          <div className="flex items-center gap-2 rounded-lg border border-dashed border-border p-3">
            <Sparkles className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            <span className="text-xs text-muted-foreground flex-1">Run AI extraction for per-field confidence scores</span>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              disabled={aiLoading}
              onClick={async () => {
                setAILoading(true);
                try {
                  const r = await documentAiApi.runAIExtraction(suggestion.attachment_id!);
                  setAIResult(r);
                  // Pre-fill from high-confidence AI values
                  if (r.header.invoice_number.confidence >= 0.5 && r.header.invoice_number.value) {
                    setInvoiceNum(String(r.header.invoice_number.value));
                  }
                  if (r.header.gross_amount.confidence >= 0.5 && r.header.gross_amount.value != null) {
                    setTotalAmount(String(r.header.gross_amount.value));
                  }
                } catch {
                  setError("AI extraction failed. Check that ANTHROPIC_API_KEY is configured.");
                } finally {
                  setAILoading(false);
                }
              }}
            >
              <Sparkles className="w-3 h-3 mr-1" />
              {aiLoading ? "Analysing…" : "AI Extract"}
            </Button>
          </div>
        ) : null}

        {/* Required: Project */}
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">
            Project <span className="text-destructive">*</span>
          </label>
          <select
            value={projectId}
            onChange={e => setProjectId(e.target.value)}
            className="w-full h-9 rounded-md border border-border bg-background px-2 text-sm"
          >
            <option value="">— Select project —</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
            ))}
          </select>
        </div>

        {/* Supplier (pre-matched from OCR name) */}
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Supplier</label>
          <select
            value={supplierId}
            onChange={e => setSupplierId(e.target.value)}
            className="w-full h-9 rounded-md border border-border bg-background px-2 text-sm"
          >
            <option value="">— Not linked —</option>
            {suppliers.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {suggestion.supplier_name && (
            <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
              <Info className="w-3 h-3" />OCR supplier: <span className="italic">{suggestion.supplier_name}</span>
            </p>
          )}
        </div>

        {/* Invoice number */}
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Invoice number</label>
          <input
            value={invoiceNum}
            onChange={e => setInvoiceNum(e.target.value)}
            placeholder="e.g. INV-2024-001"
            className="w-full h-9 rounded-md border border-border bg-background px-2 text-sm"
          />
          {invoiceChanged && (
            <p className="text-xs text-amber-600 mt-0.5 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />Changed from OCR value: <span className="italic font-mono">{ocrInvoiceNum}</span>
            </p>
          )}
        </div>

        {/* Total amount */}
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Total amount (R)</label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={totalAmount}
            onChange={e => setTotalAmount(e.target.value)}
            placeholder="0.00"
            className="w-full h-9 rounded-md border border-border bg-background px-2 text-sm"
          />
          {totalChanged && (
            <p className="text-xs text-amber-600 mt-0.5 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />Changed from OCR value: <span className="italic font-mono">R{ocrTotal}</span>
            </p>
          )}
        </div>

        {/* Linked PO (pre-matched, read-only for reference) */}
        {suggestion.matched_po && (
          <div className="rounded-lg bg-muted/40 border border-border px-3 py-2 text-xs">
            <p className="text-muted-foreground">Matched PO (will be linked automatically)</p>
            <p className="font-semibold mt-0.5 font-mono">{suggestion.matched_po}</p>
          </div>
        )}

        {/* Notes */}
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">Notes (optional)</label>
          <input
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Any additional review notes…"
            className="w-full h-9 rounded-md border border-border bg-background px-2 text-sm"
          />
          <p className="text-xs text-muted-foreground mt-0.5">
            Audit trail (original OCR values, confidence) will be appended automatically.
          </p>
        </div>

        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1 border-t border-border">
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleCreate} disabled={saving || !projectId}>
            <CheckCircle2 className="w-4 h-4 mr-2" />
            {saving ? "Creating…" : "Create Invoice"}
          </Button>
        </div>

        <p className="text-xs text-muted-foreground text-center pb-1">
          This action creates a draft invoice for review. No payment is triggered.
        </p>
      </div>
    </Modal>
  );
}
