/**
 * IssueToLotPanel — issues stock from warehouse/site into a specific lot.
 * Runs BOQ allocation check on the backend. If over budget, shows overrun popup.
 */
import { useEffect, useState } from "react";
import { AlertTriangle, Check, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { stockApi, type StockBalance } from "@/api/stock";
import { OverrunWarningModal, type OverrunDetail } from "@/components/OverrunWarningModal";
import { cn } from "@/lib/utils";
import client from "@/api/client";

interface Site { id: string; name: string; }
interface Lot  { id: string; lot_number: string; site_id: string | null; }

interface Props {
  projectId: string;
  sites: Site[];
  balances: StockBalance[];
  onIssued: () => void;
}

export function IssueToLotPanel({ projectId, sites, balances, onIssued }: Props) {
  const [fromSiteId, setFromSiteId] = useState(sites[0]?.id || "");
  const [lots, setLots] = useState<Lot[]>([]);
  const [lotId, setLotId] = useState("");
  const [itemId, setItemId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [overrun, setOverrun] = useState<OverrunDetail | null>(null);

  // Load lots for this project
  useEffect(() => {
    if (!projectId) return;
    client.get<{ data: Lot[] }>(`/projects/${projectId}/lots/`)
      .then((r) => {
        setLots(r.data.data || []);
        if (r.data.data?.length) setLotId(r.data.data[0].id);
      })
      .catch(() => {});
  }, [projectId]);

  const siteBalances = balances.filter((b) => b.site_id === fromSiteId && b.balance > 0);
  useEffect(() => {
    setItemId(siteBalances[0]?.item_id || "");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromSiteId]);

  const selectedBalance = siteBalances.find((b) => b.item_id === itemId);
  const selectedLot = lots.find((l) => l.id === lotId);
  const qty = parseFloat(quantity) || 0;

  const doIssue = async (overrunReason?: string) => {
    if (!fromSiteId || !lotId || !itemId || qty <= 0) return;
    setLoading(true); setError(""); setSuccess("");
    try {
      await stockApi.issueToLot({
        project_id: projectId,
        from_site_id: fromSiteId,
        lot_id: lotId,
        item_id: itemId,
        quantity: qty,
        notes: notes || undefined,
        overrun_reason: overrunReason,
      });
      setSuccess(`${qty} ${selectedBalance?.item_unit || "units"} issued to Lot ${selectedLot?.lot_number}`);
      setQuantity(""); setNotes(""); setOverrun(null);
      onIssued();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { overrun?: boolean } & OverrunDetail } } })?.response?.data?.detail;
      if (detail?.overrun) {
        setOverrun(detail as OverrunDetail);
      } else {
        const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Issue failed.";
        setError(msg);
      }
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3">
        <p className="text-sm font-medium text-blue-600 dark:text-blue-400">Issue Stock to Lot</p>
        <p className="text-xs text-blue-600/80 dark:text-blue-400/80 mt-0.5">
          The system checks the lot's BOQ allocation before issuing. If the quantity exceeds the allocation, you must provide a reason.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>From (warehouse / site store)</Label>
          <select
            value={fromSiteId}
            onChange={(e) => setFromSiteId(e.target.value)}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label>To Lot</Label>
          <select
            value={lotId}
            onChange={(e) => setLotId(e.target.value)}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            {lots.map((l) => <option key={l.id} value={l.id}>Lot {l.lot_number}</option>)}
          </select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>Item</Label>
        <select
          value={itemId}
          onChange={(e) => setItemId(e.target.value)}
          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
        >
          {siteBalances.length === 0 ? (
            <option disabled>No stock at this site</option>
          ) : (
            siteBalances.map((b) => (
              <option key={b.item_id} value={b.item_id}>
                {b.item_name || b.item_id.slice(0, 8)} — {b.balance} {b.item_unit || ""} available
              </option>
            ))
          )}
        </select>
        {selectedBalance && (
          <p className="text-xs text-muted-foreground">
            Available at {sites.find((s) => s.id === fromSiteId)?.name}: {" "}
            <strong>{selectedBalance.balance} {selectedBalance.item_unit || "units"}</strong>
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Quantity to Issue</Label>
          <Input
            type="number"
            min="0.01"
            step="any"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="e.g. 5"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Notes (optional)</Label>
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Reason or reference" />
        </div>
      </div>

      {/* Preview */}
      {fromSiteId && lotId && itemId && qty > 0 && (
        <div className="flex items-center gap-3 bg-muted/40 rounded-xl px-4 py-3 text-sm">
          <span className="font-medium">{qty} {selectedBalance?.item_unit || "units"} {selectedBalance?.item_name || "item"}</span>
          <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0" />
          <span>Lot {selectedLot?.lot_number}</span>
        </div>
      )}

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />{error}
        </div>
      )}
      {success && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-xl px-4 py-3 text-sm text-green-600 dark:text-green-400 flex items-center gap-2">
          <Check className="w-4 h-4 shrink-0" />{success}
        </div>
      )}

      <Button
        onClick={() => doIssue()}
        disabled={loading || !fromSiteId || !lotId || !itemId || qty <= 0}
        className="w-full"
      >
        {loading ? "Issuing…" : "Issue to Lot"}
      </Button>

      {overrun && (
        <OverrunWarningModal
          warning={overrun}
          loading={loading}
          onConfirm={(reason) => doIssue(reason)}
          onCancel={() => setOverrun(null)}
        />
      )}
    </div>
  );
}
