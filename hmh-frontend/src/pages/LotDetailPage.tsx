/**
 * Lot detail page — per-lot BOQ allocation vs actual usage.
 * Has "Edit BOQ" button that navigates to the BOQ Builder for this specific lot.
 */
import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft, AlertTriangle, Package, ChevronDown, ChevronUp,
  Pencil, PlusCircle, BookTemplate,
} from "lucide-react";
import { boqApi, type LotBOQSummary, type LotBOQSummaryItem, type ItemType } from "@/api/boq";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const TYPE_COLOR: Record<ItemType, string> = {
  MATERIAL: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  LABOUR:   "bg-green-500/10 text-green-600 dark:text-green-400",
  PLANT:    "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  SERVICE:  "bg-purple-500/10 text-purple-600 dark:text-purple-400",
  PACKAGE:  "bg-pink-500/10 text-pink-600 dark:text-pink-400",
};

function fmt(n: number) {
  return `R${n.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function AllocationRow({ item }: { item: LotBOQSummaryItem }) {
  const pct = item.allocated_quantity > 0
    ? Math.min(100, (item.used_quantity / item.allocated_quantity) * 100)
    : 0;

  return (
    <div className="space-y-1.5 py-3 border-b border-border last:border-0">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn(
              "text-[10px] font-medium rounded px-1.5 py-0.5 shrink-0",
              TYPE_COLOR[item.item_type as ItemType] || "bg-muted text-muted-foreground"
            )}>
              {item.item_type.slice(0, 3)}
            </span>
            <p className="text-sm font-medium truncate">{item.description}</p>
          </div>
          {item.item_name && item.item_name !== item.description && (
            <p className="text-xs text-muted-foreground mt-0.5 ml-8">{item.item_name}</p>
          )}
        </div>
        {item.is_over ? (
          <Badge variant="destructive" className="text-xs shrink-0">
            Over by {item.over_quantity.toFixed(1)} {item.unit || ""}
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground shrink-0">
            {item.remaining_quantity.toFixed(1)} {item.unit || ""} left
          </span>
        )}
      </div>

      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            item.is_over ? "bg-destructive" : pct >= 90 ? "bg-amber-500" : "bg-green-500"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="grid grid-cols-4 gap-2 text-xs">
        <div>
          <p className="text-muted-foreground">Allocated</p>
          <p className="font-medium">{item.allocated_quantity} {item.unit || ""}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Used</p>
          <p className={cn("font-medium", item.is_over ? "text-destructive" : "")}>
            {item.used_quantity} {item.unit || ""}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Planned</p>
          <p className="font-medium">{fmt(item.planned_total)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Used Cost</p>
          <p className="font-medium">{fmt(item.used_cost)}</p>
        </div>
      </div>
    </div>
  );
}

export default function LotDetailPage() {
  const { lotId } = useParams<{ lotId: string }>();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<LotBOQSummary | null>(null);
  const [headers, setHeaders] = useState<Array<{
    id: string; project_id: string; version_name: string;
    template_name: string | null; status: string; is_active_version: boolean;
  }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [filterType, setFilterType] = useState<"ALL" | "MATERIAL" | "LABOUR" | "PLANT">("ALL");

  useEffect(() => {
    if (!lotId) return;
    Promise.allSettled([
      boqApi.getLotBOQSummary(lotId).then(setSummary),
      boqApi.getLotHeaders(lotId).then(setHeaders),
    ])
      .catch(() => setError("Failed to load lot data."))
      .finally(() => setLoading(false));
  }, [lotId]);

  const overruns = summary?.items.filter((i) => i.is_over) || [];
  const allItems = summary?.items || [];
  const filtered = filterType === "ALL" ? allItems : allItems.filter((i) => i.item_type === filterType);
  const normalItems = filtered.filter((i) => !i.is_over);
  const visible = showAll ? normalItems : normalItems.slice(0, 8);

  // Primary BOQ header for this lot (active version, or first found)
  const primaryHeader = headers.find((h) => h.is_active_version) || headers[0];

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/projects" className="p-2 rounded-lg hover:bg-muted shrink-0">
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-lg font-bold">
              Lot {summary?.lot_number || lotId?.slice(0, 8)}
            </h1>
            <p className="text-sm text-muted-foreground">BOQ Allocation vs Actual Usage</p>
          </div>
        </div>

        {/* BOQ actions */}
        <div className="flex gap-2 shrink-0">
          {primaryHeader ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate(`/boq/${primaryHeader.project_id}/${primaryHeader.id}/build`)}
            >
              <Pencil className="w-4 h-4 mr-1" />
              Edit BOQ
            </Button>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate("/boq-templates")}
            >
              <BookTemplate className="w-4 h-4 mr-1" />
              Apply Template
            </Button>
          )}
        </div>
      </div>

      {/* BOQ header info */}
      {headers.length > 0 && (
        <div className="bg-card border border-border rounded-xl px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs text-muted-foreground">BOQ Version</p>
              <p className="text-sm font-medium mt-0.5">
                {primaryHeader?.version_name}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={primaryHeader?.status === "ACTIVE" ? "success" : "outline"} className="text-xs">
                {primaryHeader?.status}
              </Badge>
              {headers.length > 1 && (
                <span className="text-xs text-muted-foreground">{headers.length} versions</span>
              )}
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20 rounded-xl" />)}
        </div>
      ) : summary ? (
        <>
          {/* Cost summary */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-card border border-border rounded-xl p-4">
              <p className="text-xs text-muted-foreground">Planned Cost</p>
              <p className="text-xl font-bold">{fmt(summary.total_planned_cost)}</p>
            </div>
            <div className={cn(
              "border rounded-xl p-4",
              summary.total_used_cost > summary.total_planned_cost && summary.total_planned_cost > 0
                ? "bg-destructive/5 border-destructive/30"
                : "bg-card border-border"
            )}>
              <p className="text-xs text-muted-foreground">Actual Cost</p>
              <p className={cn(
                "text-xl font-bold",
                summary.total_used_cost > summary.total_planned_cost && summary.total_planned_cost > 0
                  ? "text-destructive" : ""
              )}>
                {fmt(summary.total_used_cost)}
              </p>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-card border border-border rounded-xl p-3 text-center">
              <p className="text-2xl font-bold">{summary.total_items}</p>
              <p className="text-xs text-muted-foreground">Items</p>
            </div>
            <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                {summary.total_items - summary.overrun_count}
              </p>
              <p className="text-xs text-muted-foreground">On track</p>
            </div>
            <div className={cn(
              "border rounded-xl p-3 text-center",
              summary.overrun_count > 0 ? "bg-destructive/10 border-destructive/30" : "bg-card border-border"
            )}>
              <p className={cn(
                "text-2xl font-bold",
                summary.overrun_count > 0 ? "text-destructive" : "text-muted-foreground"
              )}>
                {summary.overrun_count}
              </p>
              <p className="text-xs text-muted-foreground">Overruns</p>
            </div>
          </div>

          {/* Overruns first */}
          {overruns.length > 0 && (
            <div className="bg-destructive/5 border border-destructive/30 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-4 h-4 text-destructive" />
                <span className="text-sm font-semibold text-destructive">
                  {overruns.length} Overrun{overruns.length !== 1 ? "s" : ""}
                </span>
              </div>
              {overruns.map((i) => <AllocationRow key={i.boq_item_id} item={i} />)}
            </div>
          )}

          {/* Filter tabs */}
          <div className="flex gap-1 overflow-x-auto">
            {(["ALL", "MATERIAL", "LABOUR", "PLANT"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setFilterType(t)}
                className={cn(
                  "shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                  filterType === t
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted"
                )}
              >
                {t}
                {t !== "ALL" && (
                  <span className="ml-1 opacity-60">
                    ({allItems.filter((i) => i.item_type === t).length})
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Items */}
          {allItems.length === 0 ? (
            <div className="bg-card border border-border rounded-xl p-10 text-center">
              <Package className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm font-medium">No BOQ allocated to this lot.</p>
              <p className="text-xs text-muted-foreground mt-1">
                Generate lots with a BOQ template, or go to
                {" "}<Link to="/boq-templates" className="text-primary underline">BOQ Templates</Link>{" "}
                and clone a template to this lot.
              </p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="bg-card border border-border rounded-xl p-6 text-center">
              <p className="text-sm text-muted-foreground">No {filterType.toLowerCase()} items.</p>
            </div>
          ) : (
            <div className="bg-card border border-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold">
                  {filterType === "ALL" ? "All Items" : filterType} ({filtered.length})
                </p>
                {primaryHeader && (
                  <button
                    onClick={() => navigate(`/boq/${primaryHeader.project_id}/${primaryHeader.id}/build`)}
                    className="text-xs text-primary hover:underline flex items-center gap-1"
                  >
                    <Pencil className="w-3 h-3" />Edit
                  </button>
                )}
              </div>
              <div>
                {visible.map((i) => <AllocationRow key={i.boq_item_id} item={i} />)}
                {normalItems.length > 8 && (
                  <button
                    onClick={() => setShowAll(!showAll)}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground pt-3"
                  >
                    {showAll ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    {showAll ? "Show less" : `Show ${normalItems.length - 8} more`}
                  </button>
                )}
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
