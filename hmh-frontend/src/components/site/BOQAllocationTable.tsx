/**
 * BOQAllocationTable — Premium BOQ tracking dashboard component.
 *
 * Features:
 *  - KPI summary cards
 *  - Searchable, filterable, sortable table
 *  - Progress bars (used / allocated)
 *  - Status badges with row highlighting
 *  - Material detail drawer
 *  - Pagination (15 rows per page)
 *  - Mobile-responsive card fallback
 *  - CSV / Print export
 */

import { Fragment, useMemo, useState } from "react";
import {
  Search, Download, Printer, ChevronUp, ChevronDown,
  X, FileSpreadsheet, Package, AlertTriangle, CheckCircle2,
  TrendingDown, ChevronLeft, ChevronRight, ArrowUpDown,
  BarChart3, Truck, Minus, Eye, Layers,
} from "lucide-react";
import { type MaterialSummaryItem, type MaterialStatus } from "@/api/siteDashboard";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  items:             MaterialSummaryItem[];
  loading?:          boolean;
  fromSiteTemplate?: boolean;
  hideActions?:      boolean;
  onRecordUsage:     (item: MaterialSummaryItem) => void;
  onReceiveDelivery: (item: MaterialSummaryItem) => void;
  onGenerateLotBoq?: () => void;
}

type SortKey = "description" | "boq_allocated_qty" | "delivered_qty" | "used_qty" | "remaining_qty" | "progress" | "status";
type SortDir = "asc" | "desc";

const STATUS_PRIORITY: Record<MaterialStatus, number> = {
  OVER_BOQ: 0, STOCK_ISSUE: 1, LOW: 2, OK: 3,
};

const STATUS_CONFIG: Record<MaterialStatus, { label: string; badge: string; row: string }> = {
  OK:          { label: "OK",            badge: "bg-green-100 text-green-700 border-green-200 dark:bg-green-950/50 dark:text-green-400 dark:border-green-800",  row: "" },
  LOW:         { label: "LOW REMAINING", badge: "bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-400 dark:border-amber-800",  row: "bg-amber-50/60 dark:bg-amber-950/10" },
  OVER_BOQ:    { label: "OVER BOQ",      badge: "bg-red-100   text-red-700   border-red-200   dark:bg-red-950/50   dark:text-red-400   dark:border-red-800",    row: "bg-red-50/60   dark:bg-red-950/10" },
  STOCK_ISSUE: { label: "STOCK ISSUE",   badge: "bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-950/50 dark:text-orange-400 dark:border-orange-800", row: "bg-orange-50/60 dark:bg-orange-950/10" },
};

const PAGE_SIZE = 15;

// ── Grouping ──────────────────────────────────────────────────────────────────

function getGroupKey(desc: string): string {
  // Use first word (normalized) as the group key
  return desc.trim().toLowerCase().split(/[\s,\/\-]+/)[0] || desc.toLowerCase();
}

function getGroupLabel(key: string): string {
  return key.charAt(0).toUpperCase() + key.slice(1);
}

interface ItemGroup {
  key:   string;
  label: string;
  items: MaterialSummaryItem[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function progressPct(item: MaterialSummaryItem): number {
  return item.boq_allocated_qty > 0
    ? Math.min((item.used_qty / item.boq_allocated_qty) * 100, 999)
    : 0;
}

function progressColor(pct: number): string {
  if (pct > 100) return "bg-red-600";
  if (pct >= 90)  return "bg-orange-500";
  if (pct >= 70)  return "bg-amber-500";
  return "bg-green-500";
}

function fmt(n: number, unit?: string | null): string {
  const s = n % 1 === 0 ? n.toLocaleString("en-ZA") : n.toLocaleString("en-ZA", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return unit ? `${s} ${unit}` : s;
}

function downloadCSV(filename: string, rows: string[][]) {
  const text = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
  const url  = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8;" }));
  const a    = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: MaterialStatus }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-full border whitespace-nowrap", cfg.badge)}>
      {cfg.label}
    </span>
  );
}

function ProgressBar({ item }: { item: MaterialSummaryItem }) {
  const pct    = progressPct(item);
  const barPct = Math.min(pct, 100);
  const color  = progressColor(pct);
  return (
    <div className="min-w-[80px]">
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${barPct}%` }} />
      </div>
      <p className="text-[10px] text-muted-foreground mt-0.5 tabular-nums">
        {fmt(item.used_qty)} / {fmt(item.boq_allocated_qty)} ({pct > 999 ? ">999" : pct.toFixed(0)}%)
      </p>
    </div>
  );
}

function KpiCard({ label, value, icon: Icon, accent, sub = "" }: {
  label: string; value: number | string; icon: React.ElementType;
  accent: string; sub?: string;
}) {
  return (
    <div className={cn("rounded-xl border p-3 flex items-start gap-3", accent)}>
      <div className="p-2 rounded-lg bg-white/10 shrink-0">
        <Icon className="w-4 h-4" />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold tabular-nums leading-tight">{value}</p>
        <p className="text-xs font-medium opacity-80 mt-0.5">{label}</p>
        {sub && <p className="text-[10px] opacity-60 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ── Detail Drawer ─────────────────────────────────────────────────────────────

function DetailDrawer({ item, onClose, onRecordUsage, onReceiveDelivery, hideActions = false }: {
  item: MaterialSummaryItem;
  onClose: () => void;
  onRecordUsage: (item: MaterialSummaryItem) => void;
  onReceiveDelivery: (item: MaterialSummaryItem) => void;
  hideActions?: boolean;
}) {
  const pct       = progressPct(item);
  const variance  = item.boq_allocated_qty > 0
    ? ((item.used_qty - item.boq_allocated_qty) / item.boq_allocated_qty * 100)
    : 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative w-full max-w-sm bg-card border-l border-border shadow-2xl overflow-y-auto flex flex-col animate-fade-in"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 bg-card border-b border-border px-5 py-4 flex items-start justify-between">
          <div className="min-w-0 pr-3">
            <p className="text-xs text-muted-foreground mb-0.5">Material Detail</p>
            <h3 className="font-bold text-base leading-tight">{item.description}</h3>
            <p className="text-xs text-muted-foreground mt-0.5">{item.unit ?? "—"}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Status */}
        <div className="px-5 py-3 border-b border-border flex items-center gap-2">
          <StatusBadge status={item.status} />
          {item.from_site_template && (
            <span className="text-[10px] text-blue-600 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5 font-medium">
              Site template
            </span>
          )}
        </div>

        {/* Metrics grid */}
        <div className="px-5 py-4 grid grid-cols-2 gap-3 border-b border-border">
          {[
            { label: "BOQ Allocated", value: fmt(item.boq_allocated_qty, item.unit), color: "text-foreground" },
            { label: "Delivered",     value: fmt(item.delivered_qty,     item.unit), color: "text-blue-600" },
            { label: "Used",          value: fmt(item.used_qty,          item.unit), color: "text-orange-600" },
            { label: "Remaining",     value: fmt(item.remaining_qty,     item.unit),
              color: item.remaining_qty <= 0 ? "text-red-600" : item.status === "LOW" ? "text-amber-600" : "text-green-600" },
          ].map(m => (
            <div key={m.label} className="bg-muted/40 rounded-xl p-3">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{m.label}</p>
              <p className={cn("text-lg font-bold tabular-nums", m.color)}>{m.value}</p>
            </div>
          ))}
        </div>

        {/* Progress */}
        <div className="px-5 py-4 border-b border-border space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Usage progress</span>
            <span className={cn("font-bold", pct > 100 ? "text-red-600" : pct >= 90 ? "text-orange-600" : "text-muted-foreground")}>
              {pct > 999 ? ">999" : pct.toFixed(1)}%
            </span>
          </div>
          <div className="h-3 bg-muted rounded-full overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all", progressColor(pct))}
              style={{ width: `${Math.min(pct, 100)}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-[10px] text-muted-foreground">
            <span>0</span>
            <span>{fmt(item.boq_allocated_qty, item.unit)}</span>
          </div>
        </div>

        {/* Variance */}
        <div className="px-5 py-4 border-b border-border">
          <p className="text-xs text-muted-foreground mb-2">Variance vs allocation</p>
          <div className="flex items-center gap-2">
            <span className={cn("text-lg font-bold", variance > 0 ? "text-red-600" : variance < 0 ? "text-green-600" : "text-muted-foreground")}>
              {variance > 0 ? "+" : ""}{variance.toFixed(1)}%
            </span>
            <span className="text-xs text-muted-foreground">
              ({variance > 0 ? "over" : variance < 0 ? "under" : "on"} budget)
            </span>
          </div>
        </div>

        {/* Actions */}
        {!hideActions && (
          <div className="px-5 py-4 space-y-2 mt-auto">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Quick actions</p>
            <Button className="w-full" size="sm" onClick={() => { onRecordUsage(item); onClose(); }}>
              <Minus className="w-3.5 h-3.5 mr-1.5" />Record Usage
            </Button>
            <Button variant="outline" className="w-full" size="sm" onClick={() => { onReceiveDelivery(item); onClose(); }}>
              <Truck className="w-3.5 h-3.5 mr-1.5" />Receive Delivery
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── SortHeader helper ─────────────────────────────────────────────────────────

function SortTh({ children, col, sortBy, sortDir, onSort, className = "" }: {
  children: React.ReactNode;
  col: SortKey;
  sortBy: SortKey;
  sortDir: SortDir;
  onSort: (k: SortKey) => void;
  className?: string;
}) {
  const active = sortBy === col;
  return (
    <th
      className={cn("px-3 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide cursor-pointer select-none hover:text-foreground transition-colors", className)}
      onClick={() => onSort(col)}
    >
      <span className="flex items-center gap-1 justify-inherit">
        {children}
        {active
          ? sortDir === "asc" ? <ChevronUp className="w-3 h-3 shrink-0" /> : <ChevronDown className="w-3 h-3 shrink-0" />
          : <ArrowUpDown className="w-3 h-3 shrink-0 opacity-40" />}
      </span>
    </th>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function BOQAllocationTable({
  items, loading = false, fromSiteTemplate = false, hideActions = false,
  onRecordUsage, onReceiveDelivery, onGenerateLotBoq,
}: Props) {
  const [search,         setSearch]         = useState("");
  const [statusFilter,   setStatusFilter]   = useState<MaterialStatus | "ALL">("ALL");
  const [sortBy,         setSortBy]         = useState<SortKey>("status");
  const [sortDir,        setSortDir]        = useState<SortDir>("asc");
  const [page,           setPage]           = useState(1);
  const [drawer,         setDrawer]         = useState<MaterialSummaryItem | null>(null);
  const [groupMode,      setGroupMode]      = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  // ── Filtered + sorted data ──
  const processed = useMemo(() => {
    let list = [...items];

    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(i =>
        i.description.toLowerCase().includes(q) ||
        (i.unit ?? "").toLowerCase().includes(q)
      );
    }

    if (statusFilter !== "ALL") {
      list = list.filter(i => i.status === statusFilter);
    }

    list.sort((a, b) => {
      let cmp = 0;
      if (sortBy === "status") {
        cmp = STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
        if (cmp === 0) cmp = a.description.localeCompare(b.description);
      } else if (sortBy === "description") {
        cmp = a.description.localeCompare(b.description);
      } else if (sortBy === "progress") {
        cmp = progressPct(a) - progressPct(b);
      } else {
        cmp = (a[sortBy] as number) - (b[sortBy] as number);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });

    return list;
  }, [items, search, statusFilter, sortBy, sortDir]);

  // ── Grouped data (when groupMode is active) ──
  const groupedData = useMemo<ItemGroup[] | null>(() => {
    if (!groupMode) return null;
    const groups = new Map<string, ItemGroup>();
    for (const item of processed) {
      const key = getGroupKey(item.description);
      if (!groups.has(key)) {
        groups.set(key, { key, label: getGroupLabel(key), items: [] });
      }
      groups.get(key)!.items.push(item);
    }
    return Array.from(groups.values()).sort((a, b) => a.label.localeCompare(b.label));
  }, [processed, groupMode]);

  const totalPages = Math.max(1, Math.ceil(processed.length / PAGE_SIZE));
  const safePage   = Math.min(page, totalPages);
  const pageItems  = processed.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const handleSort = (col: SortKey) => {
    if (col === sortBy) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortBy(col); setSortDir("asc"); }
    setPage(1);
  };

  // ── KPIs ──
  const kpi = useMemo(() => ({
    total:    items.length,
    remaining: items.filter(i => i.remaining_qty > 0).length,
    overBOQ:  items.filter(i => i.status === "OVER_BOQ").length,
    low:      items.filter(i => i.status === "LOW").length,
    totalAlloc: items.reduce((s, i) => s + i.boq_allocated_qty, 0),
    totalUsed:  items.reduce((s, i) => s + i.used_qty, 0),
  }), [items]);

  // ── Export ──
  const handleExportCSV = () => {
    downloadCSV("boq-allocation.csv", [
      ["Material", "Unit", "BOQ Allocated", "Delivered", "Used", "Remaining", "Over", "Status"],
      ...processed.map(i => [
        i.description, i.unit ?? "", String(i.boq_allocated_qty), String(i.delivered_qty),
        String(i.used_qty), String(i.remaining_qty), String(i.over_qty), i.status,
      ]),
      ["TOTAL", "", String(kpi.totalAlloc.toFixed(1)), "", String(kpi.totalUsed.toFixed(1)), "", "", ""],
    ]);
  };

  // ── Empty state ──
  if (!loading && items.length === 0) {
    return (
      <div className="bg-card border border-dashed border-border rounded-2xl p-12 text-center space-y-3">
        <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mx-auto">
          <BarChart3 className="w-7 h-7 text-muted-foreground" />
        </div>
        <div>
          <p className="text-base font-semibold">No BOQ items</p>
          <p className="text-sm text-muted-foreground mt-0.5">
            No BOQ items found for this lot or site.
          </p>
        </div>
        {onGenerateLotBoq && (
          <Button size="sm" onClick={onGenerateLotBoq} className="mt-2">
            Generate Lot BOQ
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Site template banner ── */}
      {fromSiteTemplate && (
        <div className="flex items-start gap-2.5 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-xl px-4 py-3 text-sm text-blue-700 dark:text-blue-400">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            <strong>Site template:</strong> Showing the site-level BOQ allocation (no lot-specific items yet).
            Go to the BOQ page → Generate Lot BOQs to create editable per-lot copies.
          </span>
        </div>
      )}

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold">BOQ Allocation vs Usage</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Track budgeted quantities against deliveries and actual site consumption in real time.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
              placeholder="Search materials…"
              className="h-8 pl-8 pr-3 text-xs rounded-lg border border-input bg-background focus:outline-none focus:ring-1 focus:ring-primary w-44"
            />
          </div>
          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value as MaterialStatus | "ALL"); setPage(1); }}
            className="h-8 px-2 text-xs rounded-lg border border-input bg-background"
          >
            <option value="ALL">All statuses</option>
            <option value="OK">OK</option>
            <option value="LOW">Low Remaining</option>
            <option value="OVER_BOQ">Over BOQ</option>
            <option value="STOCK_ISSUE">Stock Issue</option>
          </select>
          {/* Group toggle */}
          <Button
            size="sm"
            variant={groupMode ? "default" : "outline"}
            className="h-8 text-xs gap-1.5"
            onClick={() => { setGroupMode(g => !g); setExpandedGroups(new Set()); }}
            title="Group materials by category"
          >
            <Layers className="w-3.5 h-3.5" />Group
          </Button>
          {/* Export */}
          <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={handleExportCSV}>
            <Download className="w-3.5 h-3.5" />CSV
          </Button>
          <Button size="sm" variant="outline" className="h-8 text-xs gap-1.5" onClick={() => window.print()}>
            <Printer className="w-3.5 h-3.5" />Print
          </Button>
        </div>
      </div>

      {/* ── KPI cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KpiCard label="Total BOQ Items"    value={kpi.total}     icon={FileSpreadsheet} accent="bg-blue-600 text-white border-blue-700" />
        <KpiCard label="With Remaining Stock" value={kpi.remaining} icon={CheckCircle2}   accent="bg-green-600 text-white border-green-700" sub={`of ${kpi.total} items`} />
        <KpiCard label="Over BOQ"           value={kpi.overBOQ}   icon={AlertTriangle}   accent={kpi.overBOQ > 0 ? "bg-red-600 text-white border-red-700" : "bg-muted text-muted-foreground border-border"} />
        <KpiCard label="Low Stock Alerts"   value={kpi.low}       icon={TrendingDown}    accent={kpi.low > 0 ? "bg-amber-500 text-white border-amber-600" : "bg-muted text-muted-foreground border-border"} />
      </div>

      {/* ── Table (desktop) ── */}
      <div className="hidden sm:block border border-border rounded-2xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <SortTh col="description" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="text-left">Material</SortTh>
                <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-right">Unit</th>
                <SortTh col="boq_allocated_qty" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="text-right">Allocated</SortTh>
                <SortTh col="delivered_qty"     sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="text-right">Delivered</SortTh>
                <SortTh col="used_qty"          sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="text-right">Used</SortTh>
                <SortTh col="remaining_qty"     sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="text-right">Remaining</SortTh>
                <SortTh col="progress"          sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="text-left min-w-[120px]">Progress</SortTh>
                <SortTh col="status"            sortBy={sortBy} sortDir={sortDir} onSort={handleSort} className="text-center">Status</SortTh>
                {!hideActions && <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {groupedData ? (
                // ── Grouped view ──
                groupedData.map(group => {
                  const isExpanded = expandedGroups.has(group.key);
                  const gAlloc     = group.items.reduce((s, i) => s + i.boq_allocated_qty, 0);
                  const gDelivered = group.items.reduce((s, i) => s + i.delivered_qty,     0);
                  const gUsed      = group.items.reduce((s, i) => s + i.used_qty,          0);
                  const gRemaining = group.items.reduce((s, i) => s + i.remaining_qty,     0);
                  const worstStatus = group.items.reduce<MaterialStatus>(
                    (w, i) => STATUS_PRIORITY[i.status] < STATUS_PRIORITY[w] ? i.status : w,
                    "OK",
                  );
                  const gPct     = gAlloc > 0 ? Math.min((gUsed / gAlloc) * 100, 100) : 0;
                  return (
                    <Fragment key={`grp-${group.key}`}>
                      {/* Group header row */}
                      <tr
                        className="bg-muted/60 border-b border-border cursor-pointer hover:bg-muted/80 transition-colors select-none"
                        onClick={() => setExpandedGroups(prev => {
                          const next = new Set(prev);
                          if (next.has(group.key)) next.delete(group.key); else next.add(group.key);
                          return next;
                        })}
                      >
                        <td className="px-3 py-2.5 font-bold text-sm">
                          <div className="flex items-center gap-2">
                            <ChevronDown className={cn("w-4 h-4 shrink-0 transition-transform text-muted-foreground", !isExpanded && "-rotate-90")} />
                            <span>{group.label}</span>
                            <span className="text-xs font-normal text-muted-foreground">({group.items.length})</span>
                          </div>
                        </td>
                        <td className="px-3 py-2.5 text-right text-muted-foreground text-xs">—</td>
                        <td className="px-3 py-2.5 text-right tabular-nums font-semibold">{fmt(gAlloc)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-blue-600 font-semibold">{fmt(gDelivered)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-orange-600 font-semibold">{fmt(gUsed)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums font-bold">
                          <span className={gRemaining <= 0 ? "text-red-600" : "text-green-600"}>{fmt(gRemaining)}</span>
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="h-1.5 bg-muted rounded-full overflow-hidden min-w-[80px]">
                            <div className={cn("h-full rounded-full", progressColor(gPct))} style={{ width: `${gPct}%` }} />
                          </div>
                        </td>
                        <td className="px-3 py-2.5 text-center"><StatusBadge status={worstStatus} /></td>
                        {!hideActions && <td />}
                      </tr>
                      {/* Expanded child rows */}
                      {isExpanded && group.items.map(item => {
                        const cfg = STATUS_CONFIG[item.status];
                        return (
                          <tr
                            key={`gi-${item.boq_item_id}`}
                            className={cn("group transition-colors hover:bg-muted/40 cursor-pointer", cfg.row)}
                            onClick={() => setDrawer(item)}
                          >
                            <td className="pl-10 pr-3 py-2.5">
                              <p className="font-medium text-sm leading-tight">{item.description}</p>
                              {item.item_id == null && (
                                <p className="text-[10px] text-muted-foreground mt-0.5">No catalog link</p>
                              )}
                            </td>
                            <td className="px-3 py-2.5 text-right text-muted-foreground text-xs">{item.unit ?? "—"}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums font-medium">{fmt(item.boq_allocated_qty)}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-blue-600 font-medium">{fmt(item.delivered_qty)}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-orange-600 font-medium">{fmt(item.used_qty)}</td>
                            <td className="px-3 py-2.5 text-right tabular-nums font-bold">
                              <span className={item.remaining_qty <= 0 ? "text-red-600" : item.status === "LOW" ? "text-amber-600" : "text-green-600"}>
                                {fmt(item.remaining_qty)}
                              </span>
                            </td>
                            <td className="px-3 py-2.5"><ProgressBar item={item} /></td>
                            <td className="px-3 py-2.5 text-center"><StatusBadge status={item.status} /></td>
                            {!hideActions && (
                              <td className="px-3 py-2.5">
                                <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
                                  <button onClick={() => setDrawer(item)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground" title="View details"><Eye className="w-3.5 h-3.5" /></button>
                                  <button onClick={() => onRecordUsage(item)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground" title="Record usage"><Minus className="w-3.5 h-3.5" /></button>
                                  <button onClick={() => onReceiveDelivery(item)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground" title="Receive delivery"><Truck className="w-3.5 h-3.5" /></button>
                                </div>
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </Fragment>
                  );
                })
              ) : (
                // ── Flat view (default) ──
                pageItems.map(item => {
                  const cfg = STATUS_CONFIG[item.status];
                  return (
                    <tr
                      key={item.boq_item_id}
                      className={cn(
                        "group transition-colors hover:bg-muted/40 cursor-pointer",
                        cfg.row,
                      )}
                      onClick={() => setDrawer(item)}
                    >
                      <td className="px-3 py-3">
                        <p className="font-semibold text-sm leading-tight">{item.description}</p>
                        {item.item_id == null && (
                          <p className="text-[10px] text-muted-foreground mt-0.5">No catalog link</p>
                        )}
                      </td>
                      <td className="px-3 py-3 text-right text-muted-foreground text-xs">{item.unit ?? "—"}</td>
                      <td className="px-3 py-3 text-right tabular-nums font-medium">{fmt(item.boq_allocated_qty)}</td>
                      <td className="px-3 py-3 text-right tabular-nums text-blue-600 font-medium">{fmt(item.delivered_qty)}</td>
                      <td className="px-3 py-3 text-right tabular-nums text-orange-600 font-medium">{fmt(item.used_qty)}</td>
                      <td className="px-3 py-3 text-right tabular-nums font-bold">
                        <span className={
                          item.remaining_qty <= 0  ? "text-red-600"
                          : item.status === "LOW"  ? "text-amber-600"
                          : "text-green-600"
                        }>
                          {fmt(item.remaining_qty)}
                        </span>
                      </td>
                      <td className="px-3 py-3"><ProgressBar item={item} /></td>
                      <td className="px-3 py-3 text-center"><StatusBadge status={item.status} /></td>
                      {!hideActions && (
                        <td className="px-3 py-3">
                          <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
                            <button onClick={() => setDrawer(item)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground" title="View details">
                              <Eye className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => onRecordUsage(item)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground" title="Record usage">
                              <Minus className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => onReceiveDelivery(item)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground" title="Receive delivery">
                              <Truck className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
            {/* Summary footer */}
            <tfoot>
              <tr className="bg-muted/40 border-t-2 border-border font-semibold text-sm">
                <td className="px-3 py-3" colSpan={2}>
                  <span className="text-muted-foreground text-xs">
                    {processed.length} item{processed.length !== 1 ? "s" : ""}
                    {search || statusFilter !== "ALL" ? ` (filtered from ${items.length})` : ""}
                  </span>
                </td>
                <td className="px-3 py-3 text-right tabular-nums">{fmt(items.reduce((s, i) => s + i.boq_allocated_qty, 0))}</td>
                <td className="px-3 py-3 text-right tabular-nums text-blue-600">{fmt(items.reduce((s, i) => s + i.delivered_qty, 0))}</td>
                <td className="px-3 py-3 text-right tabular-nums text-orange-600">{fmt(items.reduce((s, i) => s + i.used_qty, 0))}</td>
                <td className="px-3 py-3 text-right tabular-nums text-green-600">{fmt(Math.max(0, items.reduce((s, i) => s + i.remaining_qty, 0)))}</td>
                <td colSpan={hideActions ? 2 : 3} />
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {/* ── Card layout (mobile) ── */}
      <div className="sm:hidden space-y-2">
        {(groupMode ? processed : pageItems).map(item => {
          const cfg = STATUS_CONFIG[item.status];
          return (
            <div
              key={item.boq_item_id}
              className={cn("rounded-xl border border-border p-4 space-y-3 cursor-pointer", cfg.row || "bg-card")}
              onClick={() => setDrawer(item)}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-sm">{item.description}</p>
                  <p className="text-xs text-muted-foreground">{item.unit ?? "—"}</p>
                </div>
                <StatusBadge status={item.status} />
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div><p className="text-muted-foreground">Allocated</p><p className="font-bold tabular-nums">{fmt(item.boq_allocated_qty)}</p></div>
                <div><p className="text-muted-foreground">Used</p><p className="font-bold text-orange-600 tabular-nums">{fmt(item.used_qty)}</p></div>
                <div><p className="text-muted-foreground">Remaining</p>
                  <p className={cn("font-bold tabular-nums", item.remaining_qty <= 0 ? "text-red-600" : "text-green-600")}>
                    {fmt(item.remaining_qty)}
                  </p>
                </div>
              </div>
              <ProgressBar item={item} />
            </div>
          );
        })}
      </div>

      {/* ── Pagination (hidden in group mode) ── */}
      {!groupMode && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, processed.length)} of {processed.length}
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={safePage <= 1}
              className="p-1.5 rounded-lg border border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              const pg = i + Math.max(1, Math.min(safePage - 2, totalPages - 4));
              return (
                <button
                  key={pg}
                  onClick={() => setPage(pg)}
                  className={cn(
                    "w-7 h-7 text-xs rounded-lg border transition-colors",
                    pg === safePage
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border hover:bg-muted",
                  )}
                >
                  {pg}
                </button>
              );
            })}
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={safePage >= totalPages}
              className="p-1.5 rounded-lg border border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* ── Detail Drawer ── */}
      {drawer && (
        <DetailDrawer
          item={drawer}
          onClose={() => setDrawer(null)}
          onRecordUsage={onRecordUsage}
          onReceiveDelivery={onReceiveDelivery}
          hideActions={hideActions}
        />
      )}
    </div>
  );
}
