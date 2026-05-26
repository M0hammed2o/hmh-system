/**
 * Payment Reports — Phase 3L.
 * Monthly payment summary, supplier breakdown, date range filters.
 * Office-only page. Site users never see this.
 */

import { useEffect, useState } from "react";
import { RefreshCw, CreditCard, TrendingDown, Building2, Calendar, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { projectsApi, type Project } from "@/api/projects";
import { suppliersApi, type Supplier } from "@/api/suppliers";
import { paymentsApi, type PaymentReport } from "@/api/payments";
import { formatCurrency } from "@/lib/format";
import { cn } from "@/lib/utils";
import client from "@/api/client";

export default function PaymentReportsPage() {
  const [projects,    setProjects]    = useState<Project[]>([]);
  const [suppliers,   setSuppliers]   = useState<Supplier[]>([]);
  const [projectId,   setProjectId]   = useState("");
  const [supplierId,  setSupplierId]  = useState("");
  const [fromDate,    setFromDate]    = useState("");
  const [toDate,      setToDate]      = useState("");
  const [report,      setReport]      = useState<PaymentReport | null>(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState("");

  useEffect(() => {
    projectsApi.list(1, 100).then(r => {
      setProjects(r.items);
      if (r.items.length) setProjectId(r.items[0].id);
    }).catch(() => {});
    suppliersApi.list().then(setSuppliers).catch(() => {});
  }, []);

  const [exporting, setExporting] = useState(false);

  const load = async () => {
    if (!projectId) return;
    setLoading(true); setError("");
    try {
      const r = await paymentsApi.getReport(projectId, {
        from_date:   fromDate || undefined,
        to_date:     toDate   || undefined,
        supplier_id: supplierId || undefined,
      });
      setReport(r);
    } catch { setError("Failed to load report."); }
    finally { setLoading(false); }
  };

  const handleExportCSV = async () => {
    if (!projectId) return;
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (fromDate)    params.append("from_date",    fromDate);
      if (toDate)      params.append("to_date",      toDate);
      if (supplierId)  params.append("supplier_id",  supplierId);
      const url = `${client.defaults.baseURL}/projects/${projectId}/payments/export?${params}`;
      const res = await client.get(url, { responseType: "blob" });
      const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `payment_report_${projectId}_${fromDate || "all"}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch { setError("Export failed."); }
    finally { setExporting(false); }
  };

  useEffect(() => { if (projectId) load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Payment Reports"
        description="Monthly payment summary, supplier breakdown, and outstanding balances."
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <p className="text-xs text-muted-foreground mb-1">Project</p>
          <select value={projectId} onChange={e => setProjectId(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[200px]">
            <option value="">— Select project —</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <p className="text-xs text-muted-foreground mb-1">Supplier</p>
          <select value={supplierId} onChange={e => setSupplierId(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[160px]">
            <option value="">— All suppliers —</option>
            {suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <p className="text-xs text-muted-foreground mb-1">From</p>
          <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground mb-1">To</p>
          <input type="date" value={toDate} onChange={e => setToDate(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm" />
        </div>
        <Button onClick={load} disabled={loading || !projectId} size="sm" className="mb-0.5">
          {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : "Run Report"}
        </Button>
        <Button onClick={handleExportCSV} disabled={exporting || !projectId} size="sm" variant="outline" className="mb-0.5">
          <Download className="w-3.5 h-3.5 mr-1" />
          {exporting ? "Exporting…" : "Export CSV"}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : !report ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">
          Select a project and run the report.
        </div>
      ) : (
        <div className="space-y-5">
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div className="bg-card border border-border rounded-xl p-4">
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                <CreditCard className="w-3.5 h-3.5" />Total Paid
              </p>
              <p className="text-2xl font-bold mt-1">{formatCurrency(report.total_paid)}</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-4">
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                <TrendingDown className="w-3.5 h-3.5" />Transactions
              </p>
              <p className="text-2xl font-bold mt-1">{report.payment_count}</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-4">
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                <Building2 className="w-3.5 h-3.5" />Suppliers paid
              </p>
              <p className="text-2xl font-bold mt-1">{report.by_supplier.length}</p>
            </div>
          </div>

          {/* By Month */}
          {report.by_month.length > 0 && (
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center gap-2">
                <Calendar className="w-4 h-4 text-primary" />
                <span className="text-sm font-semibold">By Month</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[320px]">
                  <thead>
                    <tr className="border-b border-border bg-muted/20">
                      <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Month</th>
                      <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Amount</th>
                      <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Transactions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.by_month.map(m => (
                      <tr key={m.month} className="border-b border-border/40 last:border-0 hover:bg-muted/20">
                        <td className="px-4 py-2.5 font-medium">{m.month}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums font-semibold">{formatCurrency(m.total)}</td>
                        <td className="px-4 py-2.5 text-right text-muted-foreground">{m.count}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-border bg-muted/30">
                      <td className="px-4 py-2.5 font-semibold">Total</td>
                      <td className="px-4 py-2.5 text-right font-bold tabular-nums">{formatCurrency(report.total_paid)}</td>
                      <td className="px-4 py-2.5 text-right font-semibold text-muted-foreground">{report.payment_count}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </div>
          )}

          {/* By Supplier */}
          {report.by_supplier.length > 0 && (
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-border bg-muted/30 flex items-center gap-2">
                <Building2 className="w-4 h-4 text-primary" />
                <span className="text-sm font-semibold">By Supplier</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[320px]">
                  <thead>
                    <tr className="border-b border-border bg-muted/20">
                      <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Supplier</th>
                      <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Total Paid</th>
                      <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Payments</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.by_supplier.map(s => (
                      <tr key={s.supplier_id} className="border-b border-border/40 last:border-0 hover:bg-muted/20">
                        <td className="px-4 py-2.5">{s.supplier_name ?? "Unknown"}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums font-semibold">{formatCurrency(s.total)}</td>
                        <td className="px-4 py-2.5 text-right text-muted-foreground">{s.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {report.payment_count === 0 && (
            <div className="bg-card border border-border rounded-xl p-10 text-center text-sm text-muted-foreground">
              No payments found for the selected filters.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
