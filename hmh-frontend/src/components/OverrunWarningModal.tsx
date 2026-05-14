/**
 * Overrun warning modal — shown when a stock issue exceeds lot BOQ allocation.
 *
 * Props:
 *   warning — the detail object from the 422 response (detail.overrun === true)
 *   onConfirm(reason) — called when user submits a reason
 *   onCancel — called if user cancels
 *
 * Usage:
 *   const [overrun, setOverrun] = useState(null)
 *   // in catch block after stock issue returns 422:
 *   if (err.response?.data?.detail?.overrun) setOverrun(err.response.data.detail)
 *   // render:
 *   {overrun && <OverrunWarningModal warning={overrun} onConfirm={...} onCancel={() => setOverrun(null)} />}
 */
import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

export interface OverrunDetail {
  overrun: true;
  lot_number: string;
  item_name: string;
  item_unit: string | null;
  allocated_quantity: number;
  already_used: number;
  new_issue_quantity: number;
  new_total: number;
  over_amount: number;
}

interface Props {
  warning: OverrunDetail;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
  loading?: boolean;
}

export function OverrunWarningModal({ warning, onConfirm, onCancel, loading }: Props) {
  const [reason, setReason] = useState("");
  const unit = warning.item_unit || "";

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) return;
    onConfirm(reason.trim());
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-foreground/60">
      <div className="bg-card border border-destructive/40 rounded-2xl w-full max-w-sm p-6 animate-fade-in">
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-destructive/10 shrink-0">
            <AlertTriangle className="w-5 h-5 text-destructive" />
          </div>
          <div>
            <h2 className="text-base font-bold text-destructive">Allocation Exceeded</h2>
            <p className="text-xs text-muted-foreground">Lot {warning.lot_number} — {warning.item_name}</p>
          </div>
        </div>

        {/* Stats */}
        <div className="bg-destructive/5 border border-destructive/20 rounded-xl p-4 space-y-2 mb-4">
          {[
            { label: "Planned allocation", value: `${warning.allocated_quantity} ${unit}` },
            { label: "Already issued", value: `${warning.already_used} ${unit}` },
            { label: "New issue amount", value: `${warning.new_issue_quantity} ${unit}` },
            { label: "New total", value: `${warning.new_total} ${unit}`, bold: true },
          ].map(({ label, value, bold }) => (
            <div key={label} className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{label}</span>
              <span className={bold ? "font-bold" : "font-medium"}>{value}</span>
            </div>
          ))}
          <div className="flex items-center justify-between text-sm border-t border-destructive/20 pt-2 mt-1">
            <span className="text-destructive font-medium">Over by</span>
            <span className="text-destructive font-bold">{warning.over_amount} {unit}</span>
          </div>
        </div>

        {/* Reason form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label className="text-sm font-medium">
              Reason for overuse <span className="text-destructive">*</span>
            </Label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Slab correction required extra cement due to level issues"
              required
              rows={3}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <p className="text-xs text-muted-foreground">This reason will be saved to the audit log and an alert will be sent to management.</p>
          </div>

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="destructive"
              disabled={!reason.trim() || loading}
              className="flex-1"
            >
              {loading ? "Submitting…" : "Confirm & Proceed"}
            </Button>
            <Button type="button" variant="outline" onClick={onCancel} disabled={loading}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
