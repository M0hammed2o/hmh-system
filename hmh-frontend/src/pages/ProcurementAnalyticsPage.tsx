import { useEffect, useState } from "react";
import {
  BarChart2, TrendingUp, TrendingDown, Package, Truck,
  FileText, CreditCard, AlertCircle, Building2, FolderKanban,
  Clock, CheckCircle, XCircle, DollarSign, Award, Download,
  RefreshCw, Search, ChevronDown, ChevronUp, ArrowUpDown,
} from "lucide-react";
import {
  analyticsApi,
  type ProcurementDashboard,
  type SupplierScore,
  type SupplierSpendRow,
  type ProjectAnalyticsRow,
  type PriceHistoryRow,
  type QuotationComparison,
  type MRForComparison,
  type SavingsRow,
} from "@/api/procurementAnalytics";
import { cn } from "@/lib/utils";

// ── Helpers ──────────────────────────────────────────────────────────────────

const fmt = (v: number) =>
  `R ${v.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const pct = (v: number) => `${v.toFixed(1)}%`;

function ScoreBar({ value, size = "md" }: { value: number; size?: "sm" | "md" }) {
  const color =
    value >= 80 ? "bg-emerald-500" :
    value >= 60 ? "bg-blue-500" :
    value >= 40 ? "bg-amber-500" : "bg-red-500";
  const h = size === "sm" ? "h-1.5" : "h-2";
  return (
    <div className={cn("w-full rounded-full bg-muted overflow-hidden", h)}>
      <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${Math.min(value, 100)}%` }} />
    </div>
  );
}

function ScoreBadge({ value }: { value: number }) {
  const [color, label] =
    value >= 80 ? ["text-emerald-600 bg-emerald-50 border-emerald-200", "Excellent"] :
    value >= 60 ? ["text-blue-600 bg-blue-50 border-blue-200", "Good"] :
    value >= 40 ? ["text-amber-600 bg-amber-50 border-amber-200", "Fair"] :
                  ["text-red-600 bg-red-50 border-red-200", "Poor"];
  return (
    <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full border", color)}>
      {value}/100 · {label}
    </span>
  );
}

function StatCard({
  label, value, sub, icon: Icon, trend,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  trend?: "up" | "down" | "neutral";
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</span>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </div>
      <p className="text-2xl font-bold text-foreground">{value}</p>
      {sub && (
        <p className={cn(
          "text-xs font-medium flex items-center gap-1",
          trend === "up" ? "text-emerald-600" : trend === "down" ? "text-red-500" : "text-muted-foreground",
        )}>
          {trend === "up" && <TrendingUp className="w-3 h-3" />}
          {trend === "down" && <TrendingDown className="w-3 h-3" />}
          {sub}
        </p>
      )}
    </div>
  );
}

// ── Tab types ─────────────────────────────────────────────────────────────────

type Tab = "overview" | "suppliers" | "spend" | "projects" | "prices" | "quotes" | "savings" | "reports";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "overview",   label: "Overview",        icon: BarChart2 },
  { id: "suppliers",  label: "Suppliers",        icon: Building2 },
  { id: "spend",      label: "Spend Analysis",   icon: DollarSign },
  { id: "projects",   label: "Projects",         icon: FolderKanban },
  { id: "prices",     label: "Price History",    icon: TrendingUp },
  { id: "quotes",     label: "Quote Comparison", icon: ArrowUpDown },
  { id: "savings",    label: "Savings",          icon: Award },
  { id: "reports",    label: "Reports",          icon: Download },
];

// ── Overview Tab ─────────────────────────────────────────────────────────────

function OverviewTab() {
  const [data, setData] = useState<ProcurementDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ project_id: "", supplier_id: "", date_from: "", date_to: "" });

  const load = async () => {
    setLoading(true);
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== ""));
      const d = await analyticsApi.dashboard(params);
      setData(d);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-6">
      {/* Filters */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1 min-w-[160px]">
          <label className="text-xs font-medium text-muted-foreground">Date From</label>
          <input type="date" value={filters.date_from} onChange={e => setFilters(f => ({ ...f, date_from: e.target.value }))}
            className="border border-border rounded-lg px-3 py-1.5 text-sm bg-background" />
        </div>
        <div className="flex flex-col gap-1 min-w-[160px]">
          <label className="text-xs font-medium text-muted-foreground">Date To</label>
          <input type="date" value={filters.date_to} onChange={e => setFilters(f => ({ ...f, date_to: e.target.value }))}
            className="border border-border rounded-lg px-3 py-1.5 text-sm bg-background" />
        </div>
        <button onClick={load} className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium">
          <RefreshCw className="w-4 h-4" /> Apply
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-card border border-border rounded-xl p-4 h-28 animate-pulse bg-muted/30" />
          ))}
        </div>
      ) : data ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Total Procurement Spend" value={fmt(data.total_spend)} icon={DollarSign} />
            <StatCard label="Spend This Month"        value={fmt(data.spend_this_month)} icon={TrendingUp} />
            <StatCard label="Open Purchase Orders"    value={String(data.open_pos)} icon={Package} />
            <StatCard label="Pending Deliveries"      value={String(data.pending_deliveries)} icon={Truck} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Pending Invoices"        value={String(data.pending_invoices)} icon={FileText} />
            <StatCard label="Pending Reconciliations" value={String(data.pending_reconciliations)} icon={AlertCircle} />
            <StatCard label="Approved Payments"       value={fmt(data.approved_payments)} icon={CheckCircle} />
            <StatCard label="Outstanding Payments"    value={fmt(data.outstanding_payments)} icon={CreditCard}
              sub={data.outstanding_payments > 0 ? "Awaiting payment" : "All settled"} />
          </div>
        </>
      ) : null}
    </div>
  );
}

// ── Suppliers Tab ─────────────────────────────────────────────────────────────

function SuppliersTab() {
  const [data, setData] = useState<SupplierScore[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    analyticsApi.allSupplierScores().then(d => { setData(d); setLoading(false); });
  }, []);

  const filtered = data.filter(s =>
    !search || s.supplier_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search supplier…"
            className="w-full pl-9 pr-3 py-2 border border-border rounded-lg text-sm bg-background" />
        </div>
        <span className="text-sm text-muted-foreground">{filtered.length} suppliers</span>
      </div>

      {loading ? (
        <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-16 rounded-xl bg-muted/30 animate-pulse" />
        ))}</div>
      ) : (
        <div className="space-y-2">
          {filtered.map(s => (
            <div key={s.supplier_id} className="bg-card border border-border rounded-xl overflow-hidden">
              <button
                className="w-full flex items-center gap-4 px-5 py-4 hover:bg-muted/30 transition-colors text-left"
                onClick={() => setExpanded(expanded === s.supplier_id ? null : s.supplier_id)}
              >
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <Building2 className="w-5 h-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm text-foreground truncate">{s.supplier_name}</p>
                  <p className="text-xs text-muted-foreground">{s.supplier_code || "No code"} · {fmt(s.stats.total_spend)} spend</p>
                </div>
                <div className="flex items-center gap-4 shrink-0">
                  <div className="w-32 hidden md:block">
                    <ScoreBar value={s.score} />
                    <p className="text-xs text-muted-foreground mt-0.5 text-right">{s.score}/100</p>
                  </div>
                  <ScoreBadge value={s.score} />
                  {expanded === s.supplier_id ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                </div>
              </button>

              {expanded === s.supplier_id && (
                <div className="border-t border-border px-5 py-4 bg-muted/10">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div className="text-center">
                      <p className="text-2xl font-bold text-foreground">{s.stats.total_pos}</p>
                      <p className="text-xs text-muted-foreground">Purchase Orders</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-foreground">{s.stats.total_deliveries}</p>
                      <p className="text-xs text-muted-foreground">Deliveries</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-foreground">{s.stats.total_invoices}</p>
                      <p className="text-xs text-muted-foreground">Invoices</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-foreground">{s.stats.open_issues}</p>
                      <p className="text-xs text-muted-foreground">Open Issues</p>
                    </div>
                  </div>

                  <div className="space-y-3">
                    {[
                      { label: "Delivery Reliability",       value: s.metrics.delivery_reliability },
                      { label: "Reconciliation Match Rate",   value: s.metrics.reconciliation_match_rate },
                      { label: "Quote Acceptance Rate",       value: s.metrics.quote_acceptance_rate },
                      { label: "Delivery Speed Score",        value: s.metrics.delivery_speed_score },
                    ].map(m => (
                      <div key={m.label} className="flex items-center gap-3">
                        <span className="text-xs text-muted-foreground w-44 shrink-0">{m.label}</span>
                        <div className="flex-1"><ScoreBar value={m.value} size="sm" /></div>
                        <span className="text-xs font-semibold text-foreground w-12 text-right">{pct(m.value)}</span>
                      </div>
                    ))}
                    {s.metrics.avg_delivery_days !== null && (
                      <p className="text-xs text-muted-foreground flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        Avg delivery time: <strong>{s.metrics.avg_delivery_days} days</strong>
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="text-center text-sm text-muted-foreground py-10">No suppliers found.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Spend Analysis Tab ────────────────────────────────────────────────────────

function SpendTab() {
  const [data, setData] = useState<SupplierSpendRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    analyticsApi.supplierSpend(10).then(d => { setData(d.top_suppliers); setLoading(false); });
  }, []);

  const maxSpend = data[0]?.total_spend || 1;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-foreground">Top 10 Suppliers by Spend</h3>

      {loading ? (
        <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-16 rounded-xl bg-muted/30 animate-pulse" />
        ))}</div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">#</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Supplier</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Total Spend</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">This Year</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">This Month</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">POs</th>
                <th className="px-4 py-3 text-xs font-semibold text-muted-foreground w-40">Share</th>
                <th className="px-4 py-3 w-8" />
              </tr>
            </thead>
            <tbody>
              {data.map((s, idx) => (
                <>
                  <tr key={s.supplier_id} className="border-b border-border hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 text-xs text-muted-foreground">{idx + 1}</td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-foreground">{s.supplier_name}</p>
                      <p className="text-xs text-muted-foreground">{s.supplier_code || "—"}</p>
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-foreground">{fmt(s.total_spend)}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground">{fmt(s.spend_this_year)}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground">{fmt(s.spend_this_month)}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground">{s.po_count}</td>
                    <td className="px-4 py-3">
                      <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
                        <div className="h-full rounded-full bg-primary"
                          style={{ width: `${(s.total_spend / maxSpend) * 100}%` }} />
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => setExpanded(expanded === s.supplier_id ? null : s.supplier_id)}
                        className="text-muted-foreground hover:text-foreground transition-colors">
                        {expanded === s.supplier_id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                    </td>
                  </tr>
                  {expanded === s.supplier_id && s.spend_per_project.length > 0 && (
                    <tr key={`${s.supplier_id}-detail`} className="bg-muted/10 border-b border-border">
                      <td colSpan={8} className="px-8 py-3">
                        <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">Spend by Project</p>
                        <div className="space-y-1.5">
                          {s.spend_per_project.map(p => (
                            <div key={p.project_id} className="flex items-center gap-3">
                              <span className="text-xs text-foreground w-48 truncate">{p.project_name}</span>
                              <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                                <div className="h-full rounded-full bg-blue-400"
                                  style={{ width: `${(p.spend / s.total_spend) * 100}%` }} />
                              </div>
                              <span className="text-xs text-muted-foreground w-32 text-right">{fmt(p.spend)}</span>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Projects Tab ──────────────────────────────────────────────────────────────

function ProjectsTab() {
  const [data, setData] = useState<ProjectAnalyticsRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    analyticsApi.projectAnalytics().then(d => { setData(d); setLoading(false); });
  }, []);

  return (
    <div className="space-y-4">
      {loading ? (
        <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 rounded-xl bg-muted/30 animate-pulse" />
        ))}</div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Project</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">BOQ Budget</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Total Spend</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Variance</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Open POs</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Pending Deliveries</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Pending Invoices</th>
              </tr>
            </thead>
            <tbody>
              {data.map(p => (
                <tr key={p.project_id} className="border-b border-border hover:bg-muted/20 transition-colors">
                  <td className="px-4 py-3">
                    <p className="font-medium text-foreground">{p.project_name}</p>
                    <p className="text-xs text-muted-foreground">{p.project_code} · {p.project_status}</p>
                  </td>
                  <td className="px-4 py-3 text-right text-muted-foreground">
                    {p.boq_budget > 0 ? fmt(p.boq_budget) : <span className="text-muted-foreground/50">No BOQ</span>}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-foreground">{fmt(p.total_spend)}</td>
                  <td className={cn("px-4 py-3 text-right font-semibold",
                    p.budget_variance >= 0 ? "text-emerald-600" : "text-red-500")}>
                    {p.boq_budget > 0 ? (
                      <span>{p.budget_variance >= 0 ? "+" : ""}{fmt(p.budget_variance)}</span>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={cn("font-semibold", p.open_pos > 0 ? "text-amber-600" : "text-emerald-600")}>
                      {p.open_pos}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={cn("font-semibold", p.outstanding_deliveries > 0 ? "text-amber-600" : "text-emerald-600")}>
                      {p.outstanding_deliveries}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className={cn("font-semibold", p.outstanding_invoices > 0 ? "text-amber-600" : "text-emerald-600")}>
                      {p.outstanding_invoices}
                    </span>
                  </td>
                </tr>
              ))}
              {data.length === 0 && (
                <tr><td colSpan={7} className="text-center py-10 text-sm text-muted-foreground">No project data.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Price History Tab ─────────────────────────────────────────────────────────

function PricesTab() {
  const [data, setData] = useState<PriceHistoryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [searched, setSearched] = useState(false);

  const load = async () => {
    if (!search.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const rows = await analyticsApi.priceHistory({ search: search.trim(), limit: 200 });
      setData(rows);
    } finally {
      setLoading(false);
    }
  };

  const maxRate = data.reduce((m, r) => Math.max(m, r.rate), 0) || 1;

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-4">
        <p className="text-sm text-muted-foreground mb-3">
          Search for any material or item to view historical procurement prices across all POs.
        </p>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input value={search} onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === "Enter" && load()}
              placeholder="e.g. Cement 50kg, Bricks, Reinforcement…"
              className="w-full pl-9 pr-3 py-2 border border-border rounded-lg text-sm bg-background" />
          </div>
          <button onClick={load} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium">
            <Search className="w-4 h-4" /> Search
          </button>
        </div>
      </div>

      {loading && <div className="h-40 rounded-xl bg-muted/30 animate-pulse" />}

      {!loading && searched && data.length > 0 && (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border">
            <p className="text-sm font-semibold text-foreground">{data.length} price records for "{search}"</p>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="text-left px-4 py-2 text-xs font-semibold text-muted-foreground">Description</th>
                <th className="text-right px-4 py-2 text-xs font-semibold text-muted-foreground">Rate</th>
                <th className="text-center px-4 py-2 text-xs font-semibold text-muted-foreground">Unit</th>
                <th className="text-right px-4 py-2 text-xs font-semibold text-muted-foreground">Qty</th>
                <th className="text-left px-4 py-2 text-xs font-semibold text-muted-foreground">Supplier</th>
                <th className="text-left px-4 py-2 text-xs font-semibold text-muted-foreground">PO#</th>
                <th className="text-left px-4 py-2 text-xs font-semibold text-muted-foreground">Date</th>
                <th className="px-4 py-2 w-28 text-xs font-semibold text-muted-foreground">Rate Trend</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r, i) => (
                <tr key={i} className="border-b border-border hover:bg-muted/20">
                  <td className="px-4 py-2 max-w-xs truncate text-foreground">{r.description}</td>
                  <td className="px-4 py-2 text-right font-semibold text-foreground">{fmt(r.rate)}</td>
                  <td className="px-4 py-2 text-center text-muted-foreground">{r.unit || "—"}</td>
                  <td className="px-4 py-2 text-right text-muted-foreground">{r.quantity_ordered}</td>
                  <td className="px-4 py-2 text-muted-foreground truncate max-w-[120px]">{r.supplier_name || "—"}</td>
                  <td className="px-4 py-2 text-muted-foreground text-xs">{r.po_number}</td>
                  <td className="px-4 py-2 text-muted-foreground text-xs">{r.po_date || "—"}</td>
                  <td className="px-4 py-2">
                    <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                      <div className="h-full rounded-full bg-primary/60"
                        style={{ width: `${(r.rate / maxRate) * 100}%` }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && searched && data.length === 0 && (
        <p className="text-center text-sm text-muted-foreground py-10">No price records found for "{search}".</p>
      )}
    </div>
  );
}

// ── Quote Comparison Tab ──────────────────────────────────────────────────────

function QuotesTab() {
  const [mrs, setMrs] = useState<MRForComparison[]>([]);
  const [selectedMr, setSelectedMr] = useState<string>("");
  const [comparison, setComparison] = useState<QuotationComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingComp, setLoadingComp] = useState(false);

  useEffect(() => {
    analyticsApi.mrsWithMultipleQuotes().then(d => { setMrs(d); setLoading(false); });
  }, []);

  const loadComparison = async (mrId: string) => {
    setSelectedMr(mrId);
    setLoadingComp(true);
    try {
      const d = await analyticsApi.quotationComparison(mrId);
      setComparison(d);
    } finally {
      setLoadingComp(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-card border border-border rounded-xl p-4">
        <p className="text-sm text-muted-foreground mb-3">
          Select a Material Request with multiple quotations to compare supplier prices side-by-side.
        </p>
        {loading ? (
          <div className="h-10 rounded-lg bg-muted/30 animate-pulse w-64" />
        ) : mrs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No MRs with multiple quotations found.</p>
        ) : (
          <select value={selectedMr} onChange={e => loadComparison(e.target.value)}
            className="border border-border rounded-lg px-3 py-2 text-sm bg-background min-w-[280px]">
            <option value="">— Select Material Request —</option>
            {mrs.map(m => (
              <option key={m.material_request_id} value={m.material_request_id}>
                {m.mr_number} ({m.quote_count} quotes)
              </option>
            ))}
          </select>
        )}
      </div>

      {loadingComp && <div className="h-40 rounded-xl bg-muted/30 animate-pulse" />}

      {!loadingComp && comparison && (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <div>
              <p className="font-semibold text-foreground">MR: {comparison.mr_number}</p>
              <p className="text-xs text-muted-foreground">{comparison.quotation_count} quotations compared</p>
            </div>
            {comparison.lowest_amount !== null && (
              <div className="text-right">
                <p className="text-xs text-muted-foreground">Lowest Quote</p>
                <p className="font-bold text-emerald-600">{fmt(comparison.lowest_amount)}</p>
              </div>
            )}
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground">Supplier</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Quote #</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Date</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Net Amount</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">VAT ({comparison.quotes[0]?.vat_rate ?? 15}%)</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Total</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Status</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-muted-foreground">Lowest</th>
              </tr>
            </thead>
            <tbody>
              {comparison.quotes.map(q => (
                <tr key={q.quotation_id}
                  className={cn("border-b border-border hover:bg-muted/20 transition-colors",
                    q.is_lowest && "bg-emerald-50/50")}>
                  <td className="px-5 py-3 font-medium text-foreground">{q.supplier_name}</td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{q.quote_number}</td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">{q.quote_date || "—"}</td>
                  <td className="px-4 py-3 text-right text-foreground">{fmt(q.net_amount)}</td>
                  <td className="px-4 py-3 text-right text-muted-foreground">{fmt(q.vat_amount)}</td>
                  <td className={cn("px-4 py-3 text-right font-semibold",
                    q.is_lowest ? "text-emerald-600" : "text-foreground")}>
                    {fmt(q.gross_amount)}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-muted-foreground">{q.status}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    {q.is_lowest && (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                        <CheckCircle className="w-3 h-3" /> Lowest
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-5 py-3 text-xs text-muted-foreground bg-muted/20 border-t border-border">
            No automatic approval — all quotation selections require manual procurement approval.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Savings Tab ───────────────────────────────────────────────────────────────

function SavingsTab() {
  const [data, setData] = useState<SavingsRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    analyticsApi.savingsReport().then(d => { setData(d); setLoading(false); });
  }, []);

  const totalBudget = data.reduce((s, r) => s + r.boq_budget, 0);
  const totalSpend  = data.reduce((s, r) => s + r.actual_spend, 0);
  const totalSaving = totalBudget - totalSpend;

  return (
    <div className="space-y-4">
      {!loading && data.length > 0 && totalBudget > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="Total BOQ Budget"  value={fmt(totalBudget)} icon={FileText} />
          <StatCard label="Total Actual Spend" value={fmt(totalSpend)} icon={DollarSign} />
          <StatCard label="Total Variance"
            value={fmt(Math.abs(totalSaving))}
            sub={totalSaving >= 0 ? "Under budget" : "Over budget"}
            icon={totalSaving >= 0 ? TrendingDown : TrendingUp}
            trend={totalSaving >= 0 ? "up" : "down"} />
        </div>
      )}

      {loading ? (
        <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 rounded-xl bg-muted/30 animate-pulse" />
        ))}</div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground">Project</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">BOQ Budget</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Actual Spend</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Variance</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-muted-foreground">Variance %</th>
                <th className="text-center px-4 py-3 text-xs font-semibold text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map(s => (
                <tr key={s.project_id} className="border-b border-border hover:bg-muted/20">
                  <td className="px-4 py-3">
                    <p className="font-medium text-foreground">{s.project_name}</p>
                    <p className="text-xs text-muted-foreground">{s.project_code}</p>
                  </td>
                  <td className="px-4 py-3 text-right text-muted-foreground">
                    {s.has_boq ? fmt(s.boq_budget) : <span className="text-muted-foreground/40">No BOQ</span>}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-foreground">{fmt(s.actual_spend)}</td>
                  <td className={cn("px-4 py-3 text-right font-semibold",
                    !s.has_boq ? "text-muted-foreground/40" :
                    s.variance >= 0 ? "text-emerald-600" : "text-red-500")}>
                    {s.has_boq ? `${s.variance >= 0 ? "+" : ""}${fmt(s.variance)}` : "—"}
                  </td>
                  <td className={cn("px-4 py-3 text-right font-semibold",
                    !s.has_boq ? "text-muted-foreground/40" :
                    s.variance_pct >= 0 ? "text-emerald-600" : "text-red-500")}>
                    {s.has_boq ? `${s.variance_pct >= 0 ? "+" : ""}${s.variance_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {s.has_boq ? (
                      <span className={cn(
                        "text-xs font-semibold px-2 py-0.5 rounded-full border",
                        s.status === "under_budget"
                          ? "text-emerald-600 bg-emerald-50 border-emerald-200"
                          : "text-red-600 bg-red-50 border-red-200",
                      )}>
                        {s.status === "under_budget" ? "Under Budget" : "Over Budget"}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground/40">No BOQ</span>
                    )}
                  </td>
                </tr>
              ))}
              {data.length === 0 && (
                <tr><td colSpan={6} className="text-center py-10 text-sm text-muted-foreground">No project data.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Reports Tab ───────────────────────────────────────────────────────────────

function ReportCard({
  title, description, excelPath, pdfPath,
}: {
  title: string;
  description: string;
  excelPath: string;
  pdfPath: string;
}) {
  const base = import.meta.env.VITE_API_URL || "";
  return (
    <div className="bg-card border border-border rounded-xl p-5 flex items-start gap-4">
      <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
        <FileText className="w-5 h-5 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-sm text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
      <div className="flex gap-2 shrink-0">
        <a href={`${base}/api/v1${excelPath}`} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 transition-colors">
          <Download className="w-3.5 h-3.5" /> Excel
        </a>
        <a href={`${base}/api/v1${pdfPath}`} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600 text-white text-xs font-medium hover:bg-red-700 transition-colors">
          <Download className="w-3.5 h-3.5" /> PDF
        </a>
      </div>
    </div>
  );
}

function ReportsTab() {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Download management reports in Excel (.xlsx) or PDF format.
        Reports reflect live data at the time of download.
      </p>
      <ReportCard
        title="Supplier Spend Report"
        description="Top 10 suppliers by total procurement spend with monthly/yearly breakdown."
        excelPath="/procurement-analytics/reports/supplier-spend/excel"
        pdfPath="/procurement-analytics/reports/supplier-spend/pdf"
      />
      <ReportCard
        title="Outstanding Orders Report"
        description="All projects showing open POs, pending deliveries, spend vs BOQ budget."
        excelPath="/procurement-analytics/reports/outstanding-orders/excel"
        pdfPath="/procurement-analytics/reports/outstanding-orders/pdf"
      />
      <ReportCard
        title="Procurement Savings Report"
        description="BOQ budget vs actual procurement spend per project with variance analysis."
        excelPath="/procurement-analytics/reports/savings/excel"
        pdfPath="/procurement-analytics/reports/savings/pdf"
      />
      <ReportCard
        title="Reconciliation Report"
        description="Full reconciliation register showing status, PO, invoice and match results."
        excelPath="/procurement-analytics/reports/reconciliation/excel"
        pdfPath="/procurement-analytics/reports/reconciliation/pdf"
      />
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ProcurementAnalyticsPage() {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <BarChart2 className="w-5 h-5 text-primary" />
            Procurement Analytics
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Management visibility into spend, supplier performance, and procurement health
          </p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-muted/30 rounded-xl p-1 flex-wrap">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
              tab === t.id
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground hover:bg-background/50",
            )}>
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {tab === "overview"   && <OverviewTab />}
        {tab === "suppliers"  && <SuppliersTab />}
        {tab === "spend"      && <SpendTab />}
        {tab === "projects"   && <ProjectsTab />}
        {tab === "prices"     && <PricesTab />}
        {tab === "quotes"     && <QuotesTab />}
        {tab === "savings"    && <SavingsTab />}
        {tab === "reports"    && <ReportsTab />}
      </div>
    </div>
  );
}
