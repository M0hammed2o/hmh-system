/**
 * Pager for server-paginated history lists.
 *
 * Built for vehicle repair and cost history, where the list only grows and
 * the old screens rendered the first ten records with no way to reach the
 * rest. The record count is always shown, so it is obvious when there is
 * more history than the page in front of you.
 *
 * Renders nothing when everything already fits on one page.
 */

import { ChevronLeft, ChevronRight } from "lucide-react";

import { HISTORY_PAGE_SIZES } from "@/api/vehicles";
import { cn } from "@/lib/utils";

interface HistoryPagerProps {
  page: number;
  limit: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  onLimitChange?: (limit: number) => void;
  /** Plural noun for the records being paged, e.g. "repair" or "cost". */
  noun?: string;
  className?: string;
}

export function HistoryPager({
  page,
  limit,
  total,
  totalPages,
  onPageChange,
  onLimitChange,
  noun = "record",
  className,
}: HistoryPagerProps) {
  if (total === 0) return null;

  const first = (page - 1) * limit + 1;
  const last = Math.min(page * limit, total);
  const onlyOnePage = totalPages <= 1;

  // With everything on one page there is nothing to navigate, but the count
  // still answers "is this all of it?" — so keep it and drop the controls.
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 pt-2 mt-2 border-t border-border/50",
        className,
      )}
    >
      <span className="text-xs text-muted-foreground">
        {onlyOnePage
          ? `${total} ${noun}${total === 1 ? "" : "s"}`
          : `${first}–${last} of ${total} ${noun}${total === 1 ? "" : "s"}`}
      </span>

      <div className="flex items-center gap-2">
        {onLimitChange && (
          <select
            aria-label={`${noun}s per page`}
            value={limit}
            onChange={(e) => onLimitChange(Number(e.target.value))}
            className="h-7 rounded-md border border-border bg-background px-1.5 text-xs"
          >
            {HISTORY_PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size} / page
              </option>
            ))}
          </select>
        )}

        {!onlyOnePage && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label={`Previous page of ${noun}s`}
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <span className="text-xs text-muted-foreground tabular-nums px-1">
              {page} / {totalPages}
            </span>
            <button
              type="button"
              aria-label={`Next page of ${noun}s`}
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              className="h-7 w-7 inline-flex items-center justify-center rounded-md border border-border disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
