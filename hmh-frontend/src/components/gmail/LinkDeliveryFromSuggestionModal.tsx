/**
 * LinkDeliveryFromSuggestionModal
 *
 * Lets an office/admin user link a DELIVERY_NOTE Gmail attachment to an
 * existing Delivery record.  Requires the user to select a project first
 * (deliveries are project-scoped), then choose from the deliveries in that
 * project.  NEVER auto-links — user must confirm the target and click Link.
 */
import { useState, useEffect } from "react";
import { Truck, AlertTriangle, Info } from "lucide-react";
import { Modal } from "@/components/shared/Modal";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { gmailApi, type ReconciliationSuggestion } from "@/api/gmail";
import { deliveriesApi, type Delivery } from "@/api/deliveries";
import client from "@/api/client";

interface Project {
  id: string;
  name: string;
  code: string;
}

interface Props {
  open:       boolean;
  onClose:    () => void;
  suggestion: ReconciliationSuggestion;
  onLinked:   (deliveryId: string) => void;
}

export function LinkDeliveryFromSuggestionModal({ open, onClose, suggestion, onLinked }: Props) {
  const [projects,    setProjects]    = useState<Project[]>([]);
  const [deliveries,  setDeliveries]  = useState<Delivery[]>([]);
  const [projectId,   setProjectId]   = useState("");
  const [deliveryId,  setDeliveryId]  = useState("");
  const [loadingDels, setLoadingDels] = useState(false);
  const [saving,      setSaving]      = useState(false);
  const [error,       setError]       = useState("");

  useEffect(() => {
    if (!open) return;
    setError("");
    setProjectId("");
    setDeliveryId("");
    setDeliveries([]);

    client.get<{ data: { items: Project[] } }>("/projects/", { params: { limit: 100 } })
      .then(r => setProjects(r.data.data?.items ?? []))
      .catch(() => {});
  }, [open]);

  // Fetch deliveries when project changes
  useEffect(() => {
    if (!projectId) { setDeliveries([]); setDeliveryId(""); return; }
    setLoadingDels(true);
    setDeliveryId("");
    deliveriesApi.list(projectId)
      .then(items => setDeliveries(items))
      .catch(() => setDeliveries([]))
      .finally(() => setLoadingDels(false));
  }, [projectId]);

  const handleLink = async () => {
    if (!deliveryId)            { setError("Please select a delivery."); return; }
    if (!suggestion.attachment_id) { setError("No attachment ID — cannot link."); return; }

    setSaving(true); setError("");
    try {
      const res = await gmailApi.linkDeliveryFromGmail(suggestion.attachment_id, deliveryId);
      onLinked(res.delivery_id);
      onClose();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to link delivery note. Check that the delivery exists.");
    } finally {
      setSaving(false);
    }
  };

  const selectedDelivery = deliveries.find(d => d.id === deliveryId);

  return (
    <Modal open={open} onClose={onClose} title="Link Delivery Note from OCR" size="lg">
      <div className="px-6 py-4 space-y-4 text-sm">

        {/* OCR context */}
        <div className="rounded-lg bg-blue-50 border border-blue-200 px-3 py-2.5 text-xs space-y-1">
          <p className="font-semibold text-blue-800">Delivery note from: <span className="font-mono">{suggestion.filename}</span></p>
          {suggestion.delivery_note_number && (
            <p className="text-blue-700 flex items-center gap-1">
              <Info className="w-3 h-3" />
              OCR delivery note #: <span className="italic font-mono ml-1">{suggestion.delivery_note_number}</span>
            </p>
          )}
          {suggestion.supplier_name && (
            <p className="text-blue-700 flex items-center gap-1">
              <Info className="w-3 h-3" />
              OCR supplier: <span className="italic ml-1">{suggestion.supplier_name}</span>
            </p>
          )}
          {suggestion.matched_po && (
            <p className="text-blue-700 flex items-center gap-1">
              <Info className="w-3 h-3" />
              Matched PO: <span className="font-mono font-semibold ml-1">{suggestion.matched_po}</span>
            </p>
          )}
        </div>

        {/* Project selector */}
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

        {/* Delivery selector */}
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">
            Delivery <span className="text-destructive">*</span>
          </label>
          <select
            value={deliveryId}
            onChange={e => setDeliveryId(e.target.value)}
            disabled={!projectId || loadingDels}
            className={cn(
              "w-full h-9 rounded-md border border-border bg-background px-2 text-sm",
              (!projectId || loadingDels) && "opacity-50",
            )}
          >
            <option value="">
              {!projectId ? "— Select a project first —" : loadingDels ? "Loading…" : deliveries.length === 0 ? "— No deliveries in this project —" : "— Select delivery —"}
            </option>
            {deliveries.map(d => (
              <option key={d.id} value={d.id}>
                {d.delivery_number ?? d.id.slice(0, 8)} — {d.delivery_date?.slice(0, 10) ?? "?"} {d.supplier_delivery_note_number ? `(DN: ${d.supplier_delivery_note_number})` : ""}
              </option>
            ))}
          </select>
        </div>

        {/* Preview of selected delivery */}
        {selectedDelivery && (
          <div className="rounded-lg bg-muted/40 border border-border px-3 py-2 text-xs space-y-0.5">
            <p className="text-muted-foreground text-[10px] uppercase font-semibold tracking-wide">Selected delivery</p>
            <p className="font-semibold">{selectedDelivery.delivery_number ?? "—"}</p>
            <p className="text-muted-foreground">Date: {selectedDelivery.delivery_date?.slice(0, 10) ?? "—"}</p>
            {selectedDelivery.delivery_note_image_url && (
              <p className="flex items-center gap-1 text-amber-600">
                <AlertTriangle className="w-3 h-3" />
                This delivery already has a note image attached — linking will replace it.
              </p>
            )}
          </div>
        )}

        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1 border-t border-border">
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleLink} disabled={saving || !deliveryId}>
            <Truck className="w-4 h-4 mr-2" />
            {saving ? "Linking…" : "Link Delivery Note"}
          </Button>
        </div>

        <p className="text-xs text-muted-foreground text-center pb-1">
          This links the Gmail attachment as the delivery note image. No new delivery is created.
        </p>
      </div>
    </Modal>
  );
}
