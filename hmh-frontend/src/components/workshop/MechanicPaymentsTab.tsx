/**
 * Mechanic Payments — what is owed to mechanics, and what has been paid.
 *
 * Recording and reconciling only. Nothing here moves money.
 *
 * Every figure is the server's: the amount payable is derived from the
 * repair, the status from the payments against it. There is no status to
 * set by hand, because a status someone can set is one that disagrees with
 * the money sooner or later.
 */

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, Banknote, Check, History, RefreshCw, Undo2, Wallet, X,
} from "lucide-react";

import {
  mechanicPaymentsApi,
  PAYMENT_STATUS_LABELS,
  type MechanicPaymentFilters,
  type MechanicPaymentOverview,
  type MechanicPaymentStatus,
  type RepairPaymentHistory,
  type RepairPaymentSummary,
} from "@/api/mechanicPayments";
import { companiesApi, type Company } from "@/api/companies";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { HistoryPager } from "@/components/shared/HistoryPager";
import { cn } from "@/lib/utils";

const money = (v: number) =>
  `R${v.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STATUS_STYLES: Record<MechanicPaymentStatus, string> = {
  UNPAID: "bg-destructive/10 text-destructive border-destructive/30",
  PARTIALLY_PAID: "bg-amber-500/10 text-amber-600 border-amber-500/30",
  PAID: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
};

function StatusBadge({ status }: { status: MechanicPaymentStatus }) {
  return (
    <span className={cn("text-xs px-2 py-0.5 rounded-full border", STATUS_STYLES[status])}>
      {PAYMENT_STATUS_LABELS[status]}
    </span>
  );
}

function errorText(err: unknown, fallback: string): string {
  const res = (err as { response?: { data?: { message?: string; detail?: string } } })?.response;
  return res?.data?.message || res?.data?.detail || fallback;
}

export function MechanicPaymentsTab() {
  const [data, setData] = useState<MechanicPaymentOverview | null>(null);
  const [filters, setFilters] = useState<MechanicPaymentFilters>({ page: 1, limit: 25 });
  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openRepair, setOpenRepair] = useState<RepairPaymentSummary | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await mechanicPaymentsApi.overview(filters));
    } catch (err) {
      setError(errorText(err, "Could not load mechanic payments."));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    companiesApi.list().then(setCompanies).catch(() => setCompanies([]));
  }, []);

  const patch = (next: Partial<MechanicPaymentFilters>) =>
    // Any filter change returns to page 1: staying on page 4 of a narrower
    // result set shows an empty screen that looks like "no records".
    setFilters((prev) => ({ ...prev, ...next, page: next.page ?? 1 }));

  const totals = data?.totals;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-xl border border-border p-3">
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <Wallet className="w-3.5 h-3.5" /> Total payable
          </p>
          <p className="text-lg font-semibold">{money(totals?.total_payable ?? 0)}</p>
        </div>
        <div className="rounded-xl border border-border p-3">
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <Check className="w-3.5 h-3.5" /> Recorded payments
          </p>
          <p className="text-lg font-semibold">{money(totals?.total_paid ?? 0)}</p>
        </div>
        <div className="rounded-xl border border-border p-3">
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Outstanding
          </p>
          <p className="text-lg font-semibold">{money(totals?.total_outstanding ?? 0)}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label className="text-xs" htmlFor="mp-filter-mechanic">Mechanic</Label>
          <Input id="mp-filter-mechanic"
            className="h-8 w-44 text-xs"
            placeholder="Workshop name"
            defaultValue={filters.mechanic ?? ""}
            onKeyDown={(e) => {
              if (e.key === "Enter") patch({ mechanic: (e.target as HTMLInputElement).value || undefined });
            }}
            onBlur={(e) => patch({ mechanic: e.target.value || undefined })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs" htmlFor="mp-filter-company">Company</Label>
          <select id="mp-filter-company"
            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
            value={filters.company_id ?? ""}
            onChange={(e) => patch({ company_id: e.target.value || undefined })}
          >
            <option value="">All companies</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs" htmlFor="mp-filter-status">Status</Label>
          <select id="mp-filter-status"
            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
            value={filters.status ?? ""}
            onChange={(e) =>
              patch({ status: (e.target.value || undefined) as MechanicPaymentStatus | undefined })
            }
          >
            <option value="">Any status</option>
            <option value="UNPAID">Unpaid</option>
            <option value="PARTIALLY_PAID">Partially Paid</option>
            <option value="PAID">Paid</option>
          </select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs" htmlFor="mp-filter-from">From</Label>
          <Input id="mp-filter-from" type="date" className="h-8 w-36 text-xs"
                 value={filters.date_from ?? ""}
                 onChange={(e) => patch({ date_from: e.target.value || undefined })} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs" htmlFor="mp-filter-to">To</Label>
          <Input id="mp-filter-to" type="date" className="h-8 w-36 text-xs"
                 value={filters.date_to ?? ""}
                 onChange={(e) => patch({ date_to: e.target.value || undefined })} />
        </div>
        <Button
          size="sm"
          variant={filters.unpaid_only ? "default" : "outline"}
          className="h-8 text-xs"
          onClick={() => patch({ unpaid_only: !filters.unpaid_only })}
        >
          Still owing
        </Button>
        <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => void load()}>
          <RefreshCw className="w-3.5 h-3.5 mr-1" /> Refresh
        </Button>
      </div>

      {error && (
        <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {loading && !data ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No repairs match these filters. Only repairs with a quoted, invoiced
          or recorded cost appear here — there is nothing to pay until one of
          those is captured.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-muted-foreground border-b border-border">
                <th className="text-left font-medium py-2 pr-3">Mechanic</th>
                <th className="text-left font-medium py-2 pr-3">Vehicle</th>
                <th className="text-left font-medium py-2 pr-3">Repair</th>
                <th className="text-left font-medium py-2 pr-3">Date</th>
                <th className="text-right font-medium py-2 pr-3">Payable</th>
                <th className="text-right font-medium py-2 pr-3">Paid</th>
                <th className="text-right font-medium py-2 pr-3">Outstanding</th>
                <th className="text-left font-medium py-2 pr-3">Status</th>
                <th className="text-left font-medium py-2 pr-3">Last paid</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.repair_job_id} className="border-b border-border/50">
                  <td className="py-2 pr-3">{row.mechanic_name || "—"}</td>
                  <td className="py-2 pr-3">
                    <span className="whitespace-nowrap">{row.vehicle_registration || "—"}</span>
                    {row.vehicle_name && (
                      <span className="block text-xs text-muted-foreground">{row.vehicle_name}</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">{row.repair_title}</td>
                  <td className="py-2 pr-3 whitespace-nowrap">{row.repair_date ?? "—"}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {money(row.total_payable)}
                    {/* A balance resting on a quote is not the same as one
                        resting on an invoice. */}
                    <span className="block text-xs text-muted-foreground">
                      from {row.payable_basis}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">{money(row.total_paid)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums font-medium">
                    {money(row.outstanding)}
                  </td>
                  <td className="py-2 pr-3"><StatusBadge status={row.payment_status} /></td>
                  <td className="py-2 pr-3 whitespace-nowrap text-muted-foreground">
                    {row.last_payment_date ?? "—"}
                  </td>
                  <td className="py-2 text-right">
                    <Button size="sm" variant="outline" className="h-7 text-xs"
                            onClick={() => setOpenRepair(row)}>
                      <History className="w-3 h-3 mr-1" /> Payments
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <HistoryPager
            page={data.page}
            limit={data.limit}
            total={data.total}
            totalPages={data.total_pages}
            noun="repair"
            onPageChange={(page) => setFilters((prev) => ({ ...prev, page }))}
            onLimitChange={(limit) => patch({ limit })}
          />
        </div>
      )}

      {openRepair && (
        <RepairPaymentsDrawer
          repair={openRepair}
          onClose={() => setOpenRepair(null)}
          onChanged={() => void load()}
        />
      )}
    </div>
  );
}

/** Payment history for one repair, with the forms to add to it. */
function RepairPaymentsDrawer({
  repair,
  onClose,
  onChanged,
}: {
  repair: RepairPaymentSummary;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [history, setHistory] = useState<RepairPaymentHistory | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const today = new Date().toISOString().split("T")[0];
  const [form, setForm] = useState({
    amount: "",
    payment_date: today,
    payment_method: "",
    payment_reference: "",
    notes: "",
    proof_file_url: "",
  });

  const load = useCallback(async () => {
    try {
      setHistory(await mechanicPaymentsApi.history(repair.repair_job_id));
    } catch (err) {
      setError(errorText(err, "Could not load payment history."));
    }
  }, [repair.repair_job_id]);

  useEffect(() => { void load(); }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const amount = parseFloat(form.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter a payment amount greater than zero.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await mechanicPaymentsApi.record(repair.repair_job_id, {
        amount,
        payment_date: form.payment_date,
        payment_method: form.payment_method || undefined,
        payment_reference: form.payment_reference || undefined,
        notes: form.notes || undefined,
        proof_file_url: form.proof_file_url || undefined,
      });
      setForm({ ...form, amount: "", payment_reference: "", notes: "", proof_file_url: "" });
      await load();
      onChanged();
    } catch (err) {
      // The server explains overpayments and duplicate references precisely.
      setError(errorText(err, "Could not record the payment."));
    } finally {
      setSaving(false);
    }
  };

  const reverse = async (paymentId: string) => {
    const reason = window.prompt("Why is this payment being reversed?");
    if (!reason || !reason.trim()) return;
    setError("");
    try {
      await mechanicPaymentsApi.reverse(paymentId, reason.trim());
      await load();
      onChanged();
    } catch (err) {
      setError(errorText(err, "Could not reverse the payment."));
    }
  };

  const outstanding = history?.outstanding ?? repair.outstanding;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between mb-1">
          <h2 className="text-base font-semibold">{repair.repair_title}</h2>
          <button onClick={onClose} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          {repair.vehicle_registration} · {repair.mechanic_name || "No mechanic recorded"}
        </p>

        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="rounded-lg border border-border p-2.5">
            <p className="text-xs text-muted-foreground">Payable</p>
            <p className="font-semibold">{money(history?.total_payable ?? repair.total_payable)}</p>
          </div>
          <div className="rounded-lg border border-border p-2.5">
            <p className="text-xs text-muted-foreground">Paid</p>
            <p className="font-semibold">{money(history?.total_paid ?? repair.total_paid)}</p>
          </div>
          <div className="rounded-lg border border-border p-2.5">
            <p className="text-xs text-muted-foreground">Outstanding</p>
            <p className="font-semibold">{money(outstanding)}</p>
          </div>
        </div>

        {(history?.other_costs_not_payable_to_mechanic ?? 0) > 0 && (
          <p className="text-xs text-muted-foreground bg-muted/50 border border-border rounded-lg px-3 py-2 mb-3">
            A further {money(history!.other_costs_not_payable_to_mechanic)} of parts,
            tyres or licences is booked against this repair. That is owed to whoever
            supplied it, not to the mechanic, so it is not part of the balance above.
          </p>
        )}

        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2 mb-3">
            {error}
          </p>
        )}

        {outstanding > 0 ? (
          <form onSubmit={submit} className="space-y-3 border border-border rounded-lg p-3 mb-4">
            <p className="text-sm font-medium flex items-center gap-1.5">
              <Banknote className="w-4 h-4" /> Record a payment
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs" htmlFor="mp-amount">Amount (R) *</Label>
                <Input id="mp-amount" type="number" min="0.01" step="0.01" required
                       value={form.amount}
                       onChange={(e) => setForm({ ...form, amount: e.target.value })}
                       placeholder={outstanding.toFixed(2)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs" htmlFor="mp-date">Payment date *</Label>
                <Input id="mp-date" type="date" required value={form.payment_date}
                       onChange={(e) => setForm({ ...form, payment_date: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs" htmlFor="mp-method">Method</Label>
                <Input id="mp-method" value={form.payment_method} placeholder="EFT, cash…"
                       onChange={(e) => setForm({ ...form, payment_method: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs" htmlFor="mp-reference">Reference</Label>
                <Input id="mp-reference" value={form.payment_reference} placeholder="EFT-55012"
                       onChange={(e) => setForm({ ...form, payment_reference: e.target.value })} />
              </div>
              <div className="space-y-1 col-span-2">
                <Label className="text-xs" htmlFor="mp-proof">Proof of payment (link)</Label>
                <Input id="mp-proof" value={form.proof_file_url} placeholder="Link to the remittance or receipt"
                       onChange={(e) => setForm({ ...form, proof_file_url: e.target.value })} />
              </div>
              <div className="space-y-1 col-span-2">
                <Label className="text-xs" htmlFor="mp-notes">Notes</Label>
                <Input id="mp-notes" value={form.notes}
                       onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              </div>
            </div>
            <Button type="submit" size="sm" disabled={saving}>
              {saving ? "Recording…" : "Record payment"}
            </Button>
          </form>
        ) : (
          <p className="text-sm text-emerald-600 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2 mb-4">
            This repair is fully paid. Reverse a payment below if something was recorded in error.
          </p>
        )}

        <p className="text-sm font-medium mb-2">Payment history</p>
        {!history ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : history.payments.length === 0 ? (
          <p className="text-sm text-muted-foreground">No payments recorded yet.</p>
        ) : (
          <div className="space-y-2">
            {history.payments.map((p) => (
              <div
                key={p.id}
                className={cn(
                  "flex items-start justify-between gap-3 border border-border/60 rounded-lg p-2.5 text-sm",
                  p.is_reversed && "opacity-60",
                )}
              >
                <div className="min-w-0">
                  <p className="font-medium">
                    {money(p.amount)}
                    {p.is_reversed && (
                      <span className="ml-2 text-xs text-destructive">reversed</span>
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {p.payment_date}
                    {p.payment_method ? ` · ${p.payment_method}` : ""}
                    {p.payment_reference ? ` · ${p.payment_reference}` : ""}
                  </p>
                  {p.notes && <p className="text-xs text-muted-foreground">{p.notes}</p>}
                  {p.proof_file_url && (
                    <a href={p.proof_file_url} target="_blank" rel="noreferrer"
                       className="text-xs text-primary hover:underline">
                      Proof of payment
                    </a>
                  )}
                  {p.is_reversed && p.reversal_reason && (
                    <p className="text-xs text-destructive">Reversed: {p.reversal_reason}</p>
                  )}
                </div>
                {!p.is_reversed && (
                  <Button size="sm" variant="outline" className="h-7 text-xs shrink-0"
                          onClick={() => void reverse(p.id)}>
                    <Undo2 className="w-3 h-3 mr-1" /> Reverse
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
