/**
 * Pending supplier charges — what suppliers have asked for in advance.
 *
 * This sits beside Accounts Payable and is emphatically not part of it. A
 * pro-forma invoice prints the word INVOICE across the top and asks to be
 * paid, but the money is not owed: the liability begins when the supplier
 * issues the tax invoice for goods actually supplied. Counting a pro-forma
 * as a payable overstates what is owed today and doubles it tomorrow.
 *
 * So the number here is never added to the outstanding-invoice figures on
 * the other tabs, and the panel says so in the server's own words rather
 * than leaving a bare total on screen for somebody to add up.
 *
 * Each row answers the questions a person actually has about a request for
 * advance payment: who wants the money, under what reference, how much,
 * against which order, and whether the real invoice has arrived yet.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Ban, CheckCircle2, Clock, FileText, Info, Link2, Wallet,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { StatCard } from "@/components/shared/StatCard";
import {
  PROVISIONAL_STATUS_LABELS,
  provisionalChargesApi,
  type ProvisionalCharge,
  type ProvisionalChargeStatus,
  type ProvisionalSummary,
} from "@/api/provisionalCharges";

const fmtMoney = (n: number) =>
  `R ${n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const fmtDate = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString("en-ZA", {
        day: "numeric", month: "short", year: "numeric",
      })
    : "—";

const STATUS_STYLES: Record<ProvisionalChargeStatus, string> = {
  PENDING:   "bg-amber-50 text-amber-800 border-amber-200",
  INVOICED:  "bg-emerald-50 text-emerald-700 border-emerald-200",
  CANCELLED: "bg-slate-100 text-slate-600 border-slate-300",
};

const STATUS_ICONS: Record<ProvisionalChargeStatus, typeof Clock> = {
  PENDING:   Clock,
  INVOICED:  CheckCircle2,
  CANCELLED: Ban,
};

function StatusBadge({ status }: { status: ProvisionalChargeStatus }) {
  const Icon = STATUS_ICONS[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-semibold whitespace-nowrap",
        STATUS_STYLES[status],
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {PROVISIONAL_STATUS_LABELS[status]}
    </span>
  );
}

// ── Cancel dialog ─────────────────────────────────────────────────────────────
// A reason is required: a charge that simply vanished leaves nobody able to
// say later whether the supplier was refused, paid, or forgotten.

function CancelDialog({
  charge, onClose, onCancelled,
}: {
  charge: ProvisionalCharge;
  onClose: () => void;
  onCancelled: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await provisionalChargesApi.cancel(charge.id, reason.trim());
      onCancelled();
      onClose();
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "The charge was not cancelled.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-background p-5 shadow-lg">
        <h3 className="text-base font-semibold">Withdraw this request</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {charge.supplier_name} · {charge.reference} · {fmtMoney(charge.total_amount)}
        </p>
        <p className="mt-3 text-sm">
          This records that the supplier's request will not be honoured. It does not
          cancel an order and it does not refund anything.
        </p>

        <label className="mt-4 block text-sm font-medium" htmlFor="cancel-reason">
          Why?
        </label>
        <textarea
          id="cancel-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="e.g. Supplier withdrew the offer — no goods to be supplied."
          className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
        />

        {error && (
          <p className="mt-2 text-sm text-destructive">{error}</p>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
            Keep it
          </Button>
          <Button
            size="sm"
            onClick={() => void submit()}
            disabled={busy || reason.trim().length < 3}
          >
            {busy ? "Withdrawing…" : "Withdraw request"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────

interface Props {
  projectId: string;
  /** Bumped by the parent after anything that could change these rows. */
  refreshKey?: number;
}

export function PendingChargesPanel({ projectId, refreshKey = 0 }: Props) {
  const [charges, setCharges] = useState<ProvisionalCharge[]>([]);
  const [summary, setSummary] = useState<ProvisionalSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [cancelling, setCancelling] = useState<ProvisionalCharge | null>(null);

  const load = useCallback(async () => {
    if (!projectId) {
      setLoading(false);
      return;
    }
    try {
      const [rows, totals] = await Promise.all([
        provisionalChargesApi.list(projectId),
        provisionalChargesApi.summary(projectId),
      ]);
      setCharges(rows);
      setSummary(totals);
      setError(null);
    } catch (e: unknown) {
      setError((e as Error)?.message ?? "Could not load pending charges.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load, refreshKey]);

  // Settled and withdrawn requests are kept, because the record of what was
  // asked for is the point — but they are out of the way by default.
  const visible = useMemo(
    () => (showAll ? charges : charges.filter((c) => c.status === "PENDING")),
    [charges, showAll],
  );
  const closedCount = charges.length - charges.filter((c) => c.status === "PENDING").length;

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* What this number is, and what it is not. The server's wording. */}
      <div className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <p>{summary?.meaning}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          title="Requested in advance"
          value={fmtMoney(summary?.pending_total ?? 0)}
          icon={Wallet}
          color="bg-amber-500/10 text-amber-700"
        />
        <StatCard
          title="Open requests"
          value={summary?.pending_count ?? 0}
          icon={Clock}
          color="bg-muted text-foreground"
        />
        <StatCard
          title="Claim to verify"
          value={summary?.payment_evidence_count ?? 0}
          icon={AlertTriangle}
          color="bg-destructive/10 text-destructive"
        />
      </div>

      {closedCount > 0 && (
        <div className="flex items-center justify-end">
          <Button variant="outline" size="sm" onClick={() => setShowAll((v) => !v)}>
            {showAll
              ? "Show open requests only"
              : `Show ${closedCount} settled or withdrawn`}
          </Button>
        </div>
      )}

      {visible.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No pending supplier charges"
          description="Pro-forma invoices imported through Bypass Orders appear here until the supplier's tax invoice arrives."
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-background">
          <table className="w-full min-w-[920px] border-collapse">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2">Supplier</th>
                <th className="px-3 py-2">Reference</th>
                <th className="px-3 py-2 text-right">Amount</th>
                <th className="px-3 py-2">Dated</th>
                <th className="px-3 py-2">Matched order</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Final invoice</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {visible.map((charge) => (
                <tr
                  key={charge.id}
                  className={cn(
                    "border-b border-border/60 align-top",
                    charge.status !== "PENDING" && "opacity-70",
                  )}
                >
                  <td className="px-3 py-3 text-sm font-medium">
                    {charge.supplier_name ?? "—"}
                  </td>
                  <td className="px-3 py-3 font-mono text-sm">{charge.reference}</td>
                  <td className="px-3 py-3 text-right text-sm tabular-nums">
                    {fmtMoney(charge.total_amount)}
                  </td>
                  <td className="px-3 py-3 text-sm text-muted-foreground">
                    {fmtDate(charge.issue_date)}
                  </td>
                  <td className="px-3 py-3 text-sm">
                    {charge.purchase_order_number ? (
                      <span className="inline-flex items-center gap-1 text-sky-700">
                        <Link2 className="h-3.5 w-3.5" />
                        {charge.purchase_order_number}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Not matched</span>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <StatusBadge status={charge.status} />
                    {charge.payment_evidence_detected && (
                      <div className="mt-2 flex gap-1.5 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                        <Wallet className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        <span>{charge.payment_evidence_note}</span>
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 text-sm">
                    {charge.settled_by_invoice_number ? (
                      <span className="font-mono text-emerald-700">
                        {charge.settled_by_invoice_number}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Not yet issued</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right">
                    {charge.status === "PENDING" && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setCancelling(charge)}
                      >
                        Withdraw
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {cancelling && (
        <CancelDialog
          charge={cancelling}
          onClose={() => setCancelling(null)}
          onCancelled={() => void load()}
        />
      )}
    </div>
  );
}
