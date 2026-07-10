import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  RefreshCw, TrendingUp, TrendingDown, Minus,
  ShoppingCart, HardHat, Users, Droplet, Wrench,
  AlertTriangle, ChevronDown, ChevronUp, ArrowLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { formatCurrency } from "@/lib/format";
import {
  costSummaryApi, type ProjectCostSummary,
  EXTRA_TYPE_LABELS, EXTRA_TYPE_COLORS,
} from "@/api/costSummary";

// ── Cost row ──────────────────────────────────────────────────────────────────

function CostRow({
  icon: Icon,
  label,
  amount,
  sub,
  color = "text-foreground",
}: {
  icon: React.ElementType;
  label: string;
  amount: number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-0">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
          <Icon className="w-4 h-4 text-muted-foreground" />
        </div>
        <div>
          <p className="text-sm font-medium">{label}</p>
          {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
        </div>
      </div>
      <p className={`text-sm font-semibold tabular-nums ${color}`}>
        {formatCurrency(amount)}
      </p>
    </div>
  );
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function SpendBar({ budget, actual }: { budget: number; actual: number }) {
  const pct = budget > 0 ? Math.min((actual / budget) * 100, 100) : 0;
  const over = actual > budget;
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Spent</span>
        <span>{pct.toFixed(1)}% of budget</span>
      </div>
      <div className="h-3 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${over ? "bg-destructive" : pct > 85 ? "bg-amber-500" : "bg-success"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── Extra costs panel ─────────────────────────────────────────────────────────

function ExtraPanel({ summary }: { summary: ProjectCostSummary }) {
  const [open, setOpen] = useState(false);
  if (summary.extra_items_total === 0) return null;

  return (
    <div className="bg-card border border-amber-200 dark:border-amber-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-4 hover:bg-amber-50/50 dark:hover:bg-amber-950/20 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-600" />
          <span className="text-sm font-semibold">
            Additional / Breakage Costs
          </span>
          <span className="text-xs bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 rounded-full px-2 py-0.5 font-medium">
            {summary.extra_items_total} item{summary.extra_items_total !== 1 ? "s" : ""}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            Cost captured in Procurement Spend
          </span>
          {open ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-amber-200 dark:border-amber-800 divide-y divide-border">
          {summary.extra_costs.map((group) => (
            <div key={group.type} className="p-4 space-y-2">
              <span className={`text-xs font-semibold px-2 py-1 rounded-full ${EXTRA_TYPE_COLORS[group.type] ?? EXTRA_TYPE_COLORS.OTHER}`}>
                {EXTRA_TYPE_LABELS[group.type] ?? group.type}
              </span>
              <div className="space-y-1 mt-2">
                {group.items.map((item, i) => (
                  <div key={i} className="flex items-start justify-between gap-4 text-xs">
                    <div>
                      <p className="font-medium">{item.description || "—"}</p>
                      {item.notes && <p className="text-muted-foreground">{item.notes}</p>}
                    </div>
                    <span className="text-muted-foreground shrink-0 tabular-nums">
                      {item.quantity} {item.unit ?? ""}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ProjectCostSummaryPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [summary, setSummary] = useState<ProjectCostSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const load = () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    costSummaryApi.get(projectId)
      .then((s) => { setSummary(s); setLastRefresh(new Date()); })
      .catch(() => setError("Failed to load cost summary."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const variance    = summary?.variance ?? 0;
  const variancePct = summary?.variance_pct;
  const overBudget  = variance < 0;

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title={summary ? `${summary.project_name} — Cost Summary` : "Project Cost Summary"}
        description="Live aggregation of all cost sources for this project."
        meta={`Last updated: ${lastRefresh.toLocaleTimeString()}`}
        actions={
          <div className="flex items-center gap-2">
            {projectId && (
              <Link to={`/projects/${projectId}`}>
                <Button size="sm" variant="outline">
                  <ArrowLeft className="w-3.5 h-3.5 mr-1" />Back to Project
                </Button>
              </Link>
            )}
            <Button size="sm" variant="outline" onClick={load} disabled={loading}>
              <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        }
      />

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : summary && (
        <>
          {/* ── Budget vs Actual overview ── */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-card border border-border rounded-xl p-5">
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">BOQ Budget</p>
              <p className="text-2xl font-bold tabular-nums">{formatCurrency(summary.boq_budget)}</p>
              <p className="text-xs text-muted-foreground mt-1">Planned spend from BOQ</p>
            </div>
            <div className="bg-card border border-border rounded-xl p-5">
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Total Actual Spend</p>
              <p className="text-2xl font-bold tabular-nums text-primary">{formatCurrency(summary.total_actual)}</p>
              <p className="text-xs text-muted-foreground mt-1">All cost categories combined</p>
            </div>
            <div className={`rounded-xl p-5 border ${overBudget ? "bg-destructive/5 border-destructive/30" : "bg-success/5 border-success/30"}`}>
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Variance</p>
              <div className="flex items-center gap-1.5">
                {overBudget
                  ? <TrendingUp className="w-5 h-5 text-destructive" />
                  : variance === 0
                    ? <Minus className="w-5 h-5 text-muted-foreground" />
                    : <TrendingDown className="w-5 h-5 text-success" />}
                <p className={`text-2xl font-bold tabular-nums ${overBudget ? "text-destructive" : "text-success"}`}>
                  {formatCurrency(Math.abs(variance))}
                </p>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {overBudget ? "Over budget" : "Under budget"}
                {variancePct != null && ` (${Math.abs(variancePct)}%)`}
              </p>
            </div>
          </div>

          {/* ── Spend bar ── */}
          {summary.boq_budget > 0 && (
            <div className="bg-card border border-border rounded-xl p-5">
              <SpendBar budget={summary.boq_budget} actual={summary.total_actual} />
            </div>
          )}

          {/* ── Cost breakdown ── */}
          <div className="bg-card border border-border rounded-xl p-5">
            <h3 className="text-sm font-semibold mb-1">Cost Breakdown</h3>
            <p className="text-xs text-muted-foreground mb-4">All costs recorded in the system for this project</p>

            <CostRow
              icon={ShoppingCart}
              label="Procurement Spend"
              amount={summary.procurement_spend}
              sub="Supplier payments made (incl. extra/breakage items)"
            />
            <CostRow
              icon={Users}
              label="Subcontractor / Contractor Payments"
              amount={summary.subcontractor_cost}
              sub="Approved work-done claims"
            />
            <CostRow
              icon={HardHat}
              label="Labour (Job Cards)"
              amount={summary.labour_cost}
              sub="Approved daily/piece-rate labour cards"
            />
            <CostRow
              icon={Droplet}
              label="Fuel"
              amount={summary.fuel_cost}
              sub={`${summary.fuel_litres.toLocaleString("en-ZA", { maximumFractionDigits: 1 })} litres on site`}
            />
            <CostRow
              icon={Wrench}
              label="Vehicle Repairs"
              amount={summary.vehicle_repair_cost}
              sub="Repair costs charged to this project"
            />

            {/* Total row */}
            <div className="flex items-center justify-between pt-4 mt-2 border-t border-border">
              <p className="text-sm font-bold">Total Actual</p>
              <p className="text-base font-bold tabular-nums text-primary">{formatCurrency(summary.total_actual)}</p>
            </div>
          </div>

          {/* ── Status badges ── */}
          <div className="flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
            <Badge variant={summary.project_status === "ACTIVE" ? "success" : "secondary"}>
              {summary.project_status}
            </Badge>
            <span>{summary.project_code}</span>
            {summary.extra_items_total > 0 && (
              <span className="flex items-center gap-1 text-amber-600">
                <AlertTriangle className="w-3 h-3" />
                {summary.extra_items_total} extra order{summary.extra_items_total !== 1 ? "s" : ""} (breakage/extras)
              </span>
            )}
            <span className="ml-auto">
              Workshop costs not yet project-linked — tracked separately in Workshop module
            </span>
          </div>

          {/* ── Extra/breakage detail ── */}
          <ExtraPanel summary={summary} />
        </>
      )}
    </div>
  );
}
