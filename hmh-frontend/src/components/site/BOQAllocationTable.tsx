/**
 * BOQAllocationTable — BOQ tracking dashboard grouped by section (milestone).
 *
 * Columns: Description | Supplier | Qty | Unit | Rate | Total | Received | Used | Remaining | Type
 * Sections are collapsed/expanded like the main BOQ page.
 */

import { useMemo, useState } from "react";
import {
  Search, Download, Printer, ChevronDown, ChevronRight,
  X, FileSpreadsheet, AlertTriangle, CheckCircle2,
  TrendingDown, Eye, Minus, Truck, BarChart3, Package,
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

const STATUS_PRIORITY: Record<MaterialStatus, number> = {
  OVER_BOQ: 0, STOCK_ISSUE: 1, LOW: 2, OK: 3,
};

const STATUS_CONFIG: Record<MaterialStatus, { label: string; badge: string; row: string }> = {
  OK:          { label: "OK",            badge: "bg-green-100 text-green-700 border-green-200",  row: "" },
  LOW:         { label: "LOW",           badge: "bg-amber-100 text-amber-700 border-amber-200",  row: "bg-amber-50/40" },
  OVER_BOQ:    { label: "OVER BOQ",      badge: "bg-red-100   text-red-700   border-red-200",    row: "bg-red-50/40" },
  STOCK_ISSUE: { label: "STOCK ISSUE",   badge: "bg-orange-100 text-orange-700 border-orange-200", row: "bg-orange-50/40" },
};

const TYPE_BADGE: Record<string, string> = {
  MATERIAL: "bg-blue-100 text-blue-700",
  LABOUR:   "bg-purple-100 text-purple-700",
  PLANT:    "bg-amber-100 text-amber-700",
  SERVICE:  "bg-green-100 text-green-700",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number, unit?: string | null): string {
  if (n === 0 && unit === undefined) return "—";
  const s = n % 1 === 0
    ? n.toLocaleString("en-ZA")
    : n.toLocaleString("en-ZA", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
  return unit ? `${s} ${unit}` : s;
}

function fmtMoney(n: number | null | undefined): string {
  if (n == null || n === 0) return "—";
  return `R ${n.toLocaleString("en-ZA", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function fmtQty(n: number | null | undefined, unit?: string | null): string {
  if (n == null) return "—";
  return n % 1 === 0
    ? n.toLocaleString("en-ZA")
    : n.toLocaleString("en-ZA", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

function downloadCSV(filename: string, rows: string[][]) {
  const text = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
  const url  = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8;" }));
  const a    = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

interface Section {
  name:  string;
  order: number;
  items: MaterialSummaryItem[];
}

function buildSections(items: MaterialSummaryItem[]): Section[] {
  const map = new Map<string, Section>();
  for (const item of items) {
    const name  = item.section_name ?? "Other";
    const order = item.section_order ?? 999;
    if (!map.has(name)) map.set(name, { name, order, items: [] });
    map.get(name)!.items.push(item);
  }
  return Array.from(map.values()).sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: MaterialStatus }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded border whitespace-nowrap", cfg.badge)}>
      {cfg.label}
    </span>
  );
}

function KpiCard({ label, value, icon: Icon, accent, sub = "" }: {
  label: string; value: number | string; icon: React.ElementType; accent: string; sub?: string;
}) {
  return (
    <div className={cn("rounded-xl border p-3 flex items-start gap-3", accent)}>
      <div className="p-2 rounded-lg bg-white/10 shrink-0"><Icon className="w-4 h-4" /></div>
      <div className="min-w-0">
        <p className="text-2xl font-bold tabular-nums leading-tight">{value}</p>
        <p className="text-xs font-medium opacity-80 mt-0.5">{label}</p>
        {sub && <p className="text-[10px] opacity-60 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

function DetailDrawer({ item, onClose, onRecordUsage, onReceiveDelivery, hideActions = false }: {
  item: MaterialSummaryItem;
  onClose: () => void;
  onRecordUsage: (item: MaterialSummaryItem) => void;
  onReceiveDelivery: (item: MaterialSummaryItem) => void;
  hideActions?: boolean;
}) {
  const pct = item.boq_allocated_qty > 0
    ? Math.min((item.used_qty / item.boq_allocated_qty) * 100, 999)
    : 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div
        className="relative w-full max-w-sm bg-card border-l border-border shadow-2xl overflow-y-auto flex flex-col animate-fade-in"
        onClick={e => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 bg-card border-b border-border px-5 py-4 flex items-start justify-between">
          <div className="min-w-0 pr-3">
            <p className="text-xs text-muted-foreground mb-0.5">
              {item.section_name ?? "Material Detail"}
            </p>
            <h3 className="font-bold text-base leading-tight">{item.description}</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {item.supplier_name ?? ""} {item.unit ? `· ${item.unit}` : ""}
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-3 border-b border-border flex items-center gap-2">
          <StatusBadge status={item.status} />
          {item.item_type && (
            <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded", TYPE_BADGE[item.item_type] ?? "bg-muted text-muted-foreground")}>
              {item.item_type}
            </span>
          )}
        </div>

        <div className="px-5 py-4 grid grid-cols-2 gap-3 border-b border-border">
          {[
            { label: "BOQ Qty",   value: fmtQty(item.boq_allocated_qty, item.unit), color: "text-foreground" },
            { label: "Rate",      value: fmtMoney(item.planned_rate),                color: "text-foreground" },
            { label: "Total",     value: fmtMoney(item.planned_total),               color: "text-foreground" },
            { label: "Received",  value: fmtQty(item.delivered_qty, item.unit),      color: "text-blue-600" },
            { label: "Used",      value: fmtQty(item.used_qty, item.unit),           color: "text-orange-600" },
            { label: "Remaining", value: fmtQty(item.remaining_qty, item.unit),
              color: item.remaining_qty <= 0 ? "text-red-600" : item.status === "LOW" ? "text-amber-600" : "text-green-600" },
          ].map(m => (
            <div key={m.label} className="bg-muted/40 rounded-xl p-3">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{m.label}</p>
              <p className={cn("text-lg font-bold tabular-nums", m.color)}>{m.value}</p>
            </div>
          ))}
        </div>

        <div className="px-5 py-4 border-b border-border space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Usage progress</span>
            <span className={cn("font-bold", pct > 100 ? "text-red-600" : pct >= 90 ? "text-orange-600" : "text-muted-foreground")}>
              {pct > 999 ? ">999" : pct.toFixed(1)}%
            </span>
          </div>
          <div className="h-3 bg-muted rounded-full overflow-hidden">
            <div
              className={cn("h-full rounded-full transition-all", pct > 100 ? "bg-red-600" : pct >= 90 ? "bg-orange-500" : pct >= 70 ? "bg-amber-500" : "bg-green-500")}
              style={{ width: `${Math.min(pct, 100)}%` }}
            />
          </div>
        </div>

        {!hideActions && (
          <div className="px-5 py-4 space-y-2 mt-auto">
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

// ── Section Row ───────────────────────────────────────────────────────────────

function SectionGroup({
  section, expanded, onToggle, hideActions, onRecordUsage, onReceiveDelivery, onDetail,
}: {
  section:           Section;
  expanded:          boolean;
  onToggle:          () => void;
  hideActions:       boolean;
  onRecordUsage:     (item: MaterialSummaryItem) => void;
  onReceiveDelivery: (item: MaterialSummaryItem) => void;
  onDetail:          (item: MaterialSummaryItem) => void;
}) {
  const totalQty      = section.items.reduce((s, i) => s + i.boq_allocated_qty, 0);
  const totalReceived = section.items.reduce((s, i) => s + i.delivered_qty,     0);
  const totalUsed     = section.items.reduce((s, i) => s + i.used_qty,          0);
  const totalRemaining= section.items.reduce((s, i) => s + i.remaining_qty,     0);
  const totalValue    = section.items.reduce((s, i) => s + (i.planned_total ?? 0), 0);
  const worstStatus   = section.items.reduce<MaterialStatus>(
    (w, i) => STATUS_PRIORITY[i.status] < STATUS_PRIORITY[w] ? i.status : w, "OK"
  );

  return (
    <>
      {/* Section header */}
      <tr
        className="bg-muted/60 cursor-pointer hover:bg-muted/80 transition-colors select-none border-b border-border"
        onClick={onToggle}
      >
        <td className="px-3 py-2.5" colSpan={2}>
          <div className="flex items-center gap-2">
            {expanded
              ? <ChevronDown className="w-4 h-4 shrink-0 text-muted-foreground" />
              : <ChevronRight className="w-4 h-4 shrink-0 text-muted-foreground" />}
            <span className="font-bold text-sm">{section.name}</span>
            <span className="text-xs text-muted-foreground font-normal">
              ({section.items.length} item{section.items.length !== 1 ? "s" : ""})
            </span>
          </div>
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums font-semibold text-sm">{fmtQty(totalQty)}</td>
        <td className="px-3 py-2.5 text-muted-foreground text-xs text-right">—</td>
        <td className="px-3 py-2.5 text-right tabular-nums font-semibold text-sm">{fmtMoney(totalValue)}</td>
        <td className="px-3 py-2.5 text-right tabular-nums text-blue-600 font-semibold text-sm">{totalReceived > 0 ? fmtQty(totalReceived) : "—"}</td>
        <td className="px-3 py-2.5 text-right tabular-nums text-orange-600 font-semibold text-sm">{totalUsed > 0 ? fmtQty(totalUsed) : "—"}</td>
        <td className="px-3 py-2.5 text-right">
          <span className={cn("font-bold tabular-nums text-sm", totalRemaining <= 0 && totalQty > 0 ? "text-red-600" : "text-foreground")}>
            {totalRemaining > 0 ? fmtQty(totalRemaining) : "—"}
          </span>
        </td>
        <td className="px-3 py-2.5 text-center">
          <StatusBadge status={worstStatus} />
        </td>
        {!hideActions && <td />}
      </tr>

      {/* Item rows */}
      {expanded && section.items.map(item => {
        const cfg = STATUS_CONFIG[item.status];
        return (
          <tr
            key={item.boq_item_id}
            className={cn("group hover:bg-muted/30 transition-colors cursor-pointer border-b border-border/50", cfg.row)}
            onClick={() => onDetail(item)}
          >
            <td className="pl-9 pr-3 py-2.5">
              <p className="text-sm leading-tight font-medium">{item.description}</p>
              {item.supplier_name && (
                <p className="text-[11px] text-muted-foreground mt-0.5">{item.supplier_name}</p>
              )}
            </td>
            <td className="px-3 py-2.5 text-xs text-muted-foreground text-right whitespace-nowrap">{item.unit ?? "—"}</td>
            <td className="px-3 py-2.5 text-right tabular-nums text-sm">{fmtQty(item.boq_allocated_qty)}</td>
            <td className="px-3 py-2.5 text-right tabular-nums text-sm text-muted-foreground">{fmtMoney(item.planned_rate)}</td>
            <td className="px-3 py-2.5 text-right tabular-nums text-sm">{fmtMoney(item.planned_total)}</td>
            <td className="px-3 py-2.5 text-right tabular-nums text-sm text-blue-600">
              {item.delivered_qty > 0 ? fmtQty(item.delivered_qty) : "—"}
            </td>
            <td className="px-3 py-2.5 text-right tabular-nums text-sm text-orange-600">
              {item.used_qty > 0 ? fmtQty(item.used_qty) : "—"}
            </td>
            <td className="px-3 py-2.5 text-right tabular-nums text-sm">
              <span className={cn("font-semibold",
                item.remaining_qty <= 0 && item.boq_allocated_qty > 0 ? "text-red-600"
                : item.status === "LOW" ? "text-amber-600"
                : item.used_qty > 0 ? "text-green-600"
                : "text-muted-foreground"
              )}>
                {item.remaining_qty > 0 ? fmtQty(item.remaining_qty) : "—"}
              </span>
            </td>
            <td className="px-3 py-2.5 text-center">
              <span className={cn("text-[10px] font-semibold px-1.5 py-0.5 rounded", TYPE_BADGE[item.item_type] ?? "bg-muted text-muted-foreground")}>
                {item.item_type ?? "MATERIAL"}
              </span>
            </td>
            {!hideActions && (
              <td className="px-3 py-2.5">
                <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
                  <button onClick={() => onDetail(item)} className="p-1.5 rounded hover:bg-muted text-muted-foreground" title="Details"><Eye className="w-3.5 h-3.5" /></button>
                  <button onClick={() => onRecordUsage(item)} className="p-1.5 rounded hover:bg-muted text-muted-foreground" title="Record usage"><Minus className="w-3.5 h-3.5" /></button>
                  <button onClick={() => onReceiveDelivery(item)} className="p-1.5 rounded hover:bg-muted text-muted-foreground" title="Receive delivery"><Truck className="w-3.5 h-3.5" /></button>
                </div>
              </td>
            )}
          </tr>
        );
      })}
    </>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function BOQAllocationTable({
  items, loading = false, fromSiteTemplate = false, hideActions = false,
  onRecordUsage, onReceiveDelivery, onGenerateLotBoq,
}: Props) {
  const [search,         setSearch]         = useState("");
  const [drawer,         setDrawer]         = useState<MaterialSummaryItem | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [allExpanded,    setAllExpanded]    = useState(true);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.toLowerCase();
    return items.filter(i =>
      i.description.toLowerCase().includes(q) ||
      (i.supplier_name ?? "").toLowerCase().includes(q) ||
      (i.section_name ?? "").toLowerCase().includes(q)
    );
  }, [items, search]);

  const sections = useMemo(() => buildSections(filtered), [filtered]);

  const hasSections = items.some(i => i.section_name);

  // Initialise all sections expanded when first loaded
  const sectionNames = useMemo(() => new Set(sections.map(s => s.name)), [sections]);
  const effectiveExpanded = allExpanded
    ? sectionNames
    : expandedGroups;

  const toggleSection = (name: string) => {
    if (allExpanded) {
      // Switch from "all expanded" mode to explicit mode
      const next = new Set(sectionNames);
      next.delete(name);
      setExpandedGroups(next);
      setAllExpanded(false);
    } else {
      setExpandedGroups(prev => {
        const next = new Set(prev);
        if (next.has(name)) next.delete(name); else next.add(name);
        return next;
      });
    }
  };

  const kpi = useMemo(() => ({
    total:    items.length,
    overBOQ:  items.filter(i => i.status === "OVER_BOQ").length,
    low:      items.filter(i => i.status === "LOW").length,
    stockIssue: items.filter(i => i.status === "STOCK_ISSUE").length,
    totalValue: items.reduce((s, i) => s + (i.planned_total ?? 0), 0),
  }), [items]);

  const handleExportCSV = () => {
    downloadCSV("boq-allocation.csv", [
      ["Section", "Description", "Supplier", "Qty", "Unit", "Rate(R)", "Total(R)", "Received", "Used", "Remaining", "Type", "Status"],
      ...items.map(i => [
        i.section_name ?? "",
        i.description,
        i.supplier_name ?? "",
        String(i.boq_allocated_qty),
        i.unit ?? "",
        String(i.planned_rate ?? ""),
        String(i.planned_total ?? ""),
        String(i.delivered_qty),
        String(i.used_qty),
        String(i.remaining_qty),
        i.item_type ?? "MATERIAL",
        i.status,
      ]),
    ]);
  };

  if (!loading && items.length === 0) {
    return (
      <div className="bg-card border border-dashed border-border rounded-2xl p-12 text-center space-y-3">
        <div className="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mx-auto">
          <BarChart3 className="w-7 h-7 text-muted-foreground" />
        </div>
        <div>
          <p className="text-base font-semibold">No BOQ items</p>
          <p className="text-sm text-muted-foreground mt-0.5">No BOQ items found for this lot or site.</p>
        </div>
        {onGenerateLotBoq && (
          <Button size="sm" onClick={onGenerateLotBoq} className="mt-2">Generate Lot BOQ</Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {fromSiteTemplate && (
        <div className="flex items-start gap-2.5 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 rounded-xl px-4 py-3 text-sm text-blue-700">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            <strong>Site template:</strong> Showing the site-level BOQ. Go to BOQ → Generate Lot BOQs to create editable per-lot copies.
          </span>
        </div>
      )}

      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold">BOQ Allocation vs Usage</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Budgeted quantities vs deliveries and site consumption, grouped by milestone.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search materials…"
              className="h-8 pl-8 pr-3 text-xs rounded-lg border border-input bg-background focus:outline-none focus:ring-1 focus:ring-primary w-44"
            />
          </div>
          {hasSections && (
            <Button
              size="sm"
              variant="outline"
              className="h-8 text-xs gap-1.5"
              onClick={() => {
                if (allExpanded) {
                  setExpandedGroups(new Set());
                  setAllExpanded(false);
                } else {
                  setAllExpanded(true);
                  setExpandedGroups(new Set());
                }
              }}
            >
              {allExpanded ? "Collapse All" : "Expand All"}
            </Button>
          )}
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
        <KpiCard label="BOQ Items"     value={kpi.total}     icon={FileSpreadsheet} accent="bg-blue-600 text-white border-blue-700" />
        <KpiCard label="Total Value"   value={fmtMoney(kpi.totalValue)} icon={Package} accent="bg-slate-700 text-white border-slate-800" />
        <KpiCard label="Over BOQ"      value={kpi.overBOQ}   icon={AlertTriangle}   accent={kpi.overBOQ > 0 ? "bg-red-600 text-white border-red-700" : "bg-muted text-muted-foreground border-border"} />
        <KpiCard label="Low / Issues"  value={kpi.low + kpi.stockIssue} icon={TrendingDown} accent={(kpi.low + kpi.stockIssue) > 0 ? "bg-amber-500 text-white border-amber-600" : "bg-muted text-muted-foreground border-border"} />
      </div>

      {/* ── Table (desktop) ── */}
      <div className="hidden sm:block border border-border rounded-2xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-left">Description</th>
                <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-right">Unit</th>
                <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-right">Qty</th>
                <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-right">Rate (R)</th>
                <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-right">Total</th>
                <th className="px-3 py-3 text-xs font-semibold text-blue-600/80 text-right">Received</th>
                <th className="px-3 py-3 text-xs font-semibold text-orange-600/80 text-right">Used</th>
                <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-right">Remaining</th>
                <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-center">Type</th>
                {!hideActions && <th className="px-3 py-3 text-xs font-semibold text-muted-foreground text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {hasSections ? (
                sections.map(section => (
                  <SectionGroup
                    key={section.name}
                    section={section}
                    expanded={effectiveExpanded.has(section.name)}
                    onToggle={() => toggleSection(section.name)}
                    hideActions={hideActions}
                    onRecordUsage={onRecordUsage}
                    onReceiveDelivery={onReceiveDelivery}
                    onDetail={setDrawer}
                  />
                ))
              ) : (
                // Flat view when no section info available
                filtered.map(item => {
                  const cfg = STATUS_CONFIG[item.status];
                  return (
                    <tr
                      key={item.boq_item_id}
                      className={cn("group hover:bg-muted/30 transition-colors cursor-pointer", cfg.row)}
                      onClick={() => setDrawer(item)}
                    >
                      <td className="px-3 py-3">
                        <p className="font-medium text-sm">{item.description}</p>
                        {item.supplier_name && <p className="text-[11px] text-muted-foreground mt-0.5">{item.supplier_name}</p>}
                      </td>
                      <td className="px-3 py-3 text-right text-xs text-muted-foreground">{item.unit ?? "—"}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{fmtQty(item.boq_allocated_qty)}</td>
                      <td className="px-3 py-3 text-right tabular-nums text-muted-foreground">{fmtMoney(item.planned_rate)}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{fmtMoney(item.planned_total)}</td>
                      <td className="px-3 py-3 text-right tabular-nums text-blue-600">{item.delivered_qty > 0 ? fmtQty(item.delivered_qty) : "—"}</td>
                      <td className="px-3 py-3 text-right tabular-nums text-orange-600">{item.used_qty > 0 ? fmtQty(item.used_qty) : "—"}</td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        <span className={cn("font-semibold",
                          item.remaining_qty <= 0 && item.boq_allocated_qty > 0 ? "text-red-600"
                          : item.status === "LOW" ? "text-amber-600"
                          : "text-muted-foreground"
                        )}>
                          {item.remaining_qty > 0 ? fmtQty(item.remaining_qty) : "—"}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <span className={cn("text-[10px] font-semibold px-1.5 py-0.5 rounded", TYPE_BADGE[item.item_type] ?? "bg-muted text-muted-foreground")}>
                          {item.item_type ?? "MATERIAL"}
                        </span>
                      </td>
                      {!hideActions && (
                        <td className="px-3 py-3">
                          <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
                            <button onClick={() => setDrawer(item)} className="p-1.5 rounded hover:bg-muted text-muted-foreground"><Eye className="w-3.5 h-3.5" /></button>
                            <button onClick={() => onRecordUsage(item)} className="p-1.5 rounded hover:bg-muted text-muted-foreground"><Minus className="w-3.5 h-3.5" /></button>
                            <button onClick={() => onReceiveDelivery(item)} className="p-1.5 rounded hover:bg-muted text-muted-foreground"><Truck className="w-3.5 h-3.5" /></button>
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
            {/* Footer totals */}
            <tfoot>
              <tr className="bg-muted/40 border-t-2 border-border font-semibold text-sm">
                <td className="px-3 py-3 text-xs text-muted-foreground" colSpan={2}>
                  {items.length} item{items.length !== 1 ? "s" : ""}
                  {search ? ` (filtered from ${items.length})` : ""}
                </td>
                <td className="px-3 py-3 text-right tabular-nums">{fmtQty(items.reduce((s, i) => s + i.boq_allocated_qty, 0))}</td>
                <td />
                <td className="px-3 py-3 text-right tabular-nums">{fmtMoney(kpi.totalValue)}</td>
                <td className="px-3 py-3 text-right tabular-nums text-blue-600">
                  {items.reduce((s, i) => s + i.delivered_qty, 0) > 0 ? fmtQty(items.reduce((s, i) => s + i.delivered_qty, 0)) : "—"}
                </td>
                <td className="px-3 py-3 text-right tabular-nums text-orange-600">
                  {items.reduce((s, i) => s + i.used_qty, 0) > 0 ? fmtQty(items.reduce((s, i) => s + i.used_qty, 0)) : "—"}
                </td>
                <td className="px-3 py-3 text-right tabular-nums text-green-600">
                  {items.reduce((s, i) => s + i.remaining_qty, 0) > 0 ? fmtQty(items.reduce((s, i) => s + i.remaining_qty, 0)) : "—"}
                </td>
                <td colSpan={hideActions ? 1 : 2} />
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {/* ── Mobile card layout ── */}
      <div className="sm:hidden space-y-4">
        {sections.map(section => (
          <div key={section.name}>
            <button
              className="w-full flex items-center gap-2 px-3 py-2 bg-muted/50 rounded-lg text-sm font-bold mb-2"
              onClick={() => toggleSection(section.name)}
            >
              {effectiveExpanded.has(section.name)
                ? <ChevronDown className="w-4 h-4 text-muted-foreground" />
                : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
              {section.name}
              <span className="text-xs font-normal text-muted-foreground ml-1">({section.items.length})</span>
            </button>
            {effectiveExpanded.has(section.name) && (
              <div className="space-y-2 pl-2">
                {section.items.map(item => {
                  const cfg = STATUS_CONFIG[item.status];
                  return (
                    <div
                      key={item.boq_item_id}
                      className={cn("rounded-xl border border-border p-3 space-y-2 cursor-pointer", cfg.row || "bg-card")}
                      onClick={() => setDrawer(item)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="font-semibold text-sm">{item.description}</p>
                          {item.supplier_name && <p className="text-[11px] text-muted-foreground">{item.supplier_name}</p>}
                        </div>
                        <StatusBadge status={item.status} />
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div><p className="text-muted-foreground">Qty</p><p className="font-bold">{fmtQty(item.boq_allocated_qty)} {item.unit ?? ""}</p></div>
                        <div><p className="text-muted-foreground">Received</p><p className="font-bold text-blue-600">{item.delivered_qty > 0 ? fmtQty(item.delivered_qty) : "—"}</p></div>
                        <div><p className="text-muted-foreground">Used</p><p className="font-bold text-orange-600">{item.used_qty > 0 ? fmtQty(item.used_qty) : "—"}</p></div>
                      </div>
                      {(item.planned_rate ?? 0) > 0 && (
                        <div className="flex gap-4 text-xs text-muted-foreground">
                          <span>Rate: <strong className="text-foreground">{fmtMoney(item.planned_rate)}</strong></span>
                          <span>Total: <strong className="text-foreground">{fmtMoney(item.planned_total)}</strong></span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

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
