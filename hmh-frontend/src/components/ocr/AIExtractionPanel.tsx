/**
 * AIExtractionPanel — Phase 6A
 *
 * Displays Claude AI extraction results with per-field confidence indicators.
 * Shown after the user clicks "AI Extract" on a Gmail inbox suggestion.
 *
 * Confidence tiers:
 *   ≥ 80% green  — high confidence, likely correct
 *   50–79% amber — medium, review recommended
 *   < 50%  red   — low, manual verification required
 *
 * IMPORTANT: This panel is read-only. No automatic invoice creation occurs.
 * Human approval is always required via the CreateInvoiceFromSuggestionModal.
 */

import { CheckCircle2, AlertTriangle, XCircle, Sparkles, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  type AIExtractionResult,
  type AIExtractionHeader,
  type ConfidenceTier,
  confidenceTier,
  CONF_COLOR,
  CONF_BADGE,
  CONF_LABEL,
  HEADER_FIELD_LABELS,
} from "@/api/documentAi";

// ── Sub-components ────────────────────────────────────────────────────────────

function ConfidenceDot({ tier }: { tier: ConfidenceTier }) {
  const cls =
    tier === "high"   ? "bg-green-500" :
    tier === "medium" ? "bg-amber-500" :
                        "bg-red-500";
  return <span className={cn("inline-block w-2 h-2 rounded-full shrink-0", cls)} />;
}

function ConfidenceBadge({ score }: { score: number }) {
  const tier = confidenceTier(score);
  return (
    <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded border font-mono", CONF_BADGE[tier])}>
      {(score * 100).toFixed(0)}%
    </span>
  );
}

interface FieldRowProps {
  label: string;
  value: string | number | null;
  confidence: number;
}

function AIFieldRow({ label, value, confidence }: FieldRowProps) {
  const tier = confidenceTier(confidence);
  const isAmount = typeof value === "number";
  const displayValue = value == null
    ? <span className="text-muted-foreground italic">not found</span>
    : isAmount
      ? <span className="font-mono font-semibold">R{Number(value).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}</span>
      : <span className="font-semibold">{String(value)}</span>;

  return (
    <div className={cn(
      "flex items-center justify-between gap-2 px-3 py-2 border-b border-border last:border-b-0",
      tier === "low" && "bg-red-50/40",
      tier === "medium" && "bg-amber-50/30",
    )}>
      <div className="flex items-center gap-2 min-w-0">
        <ConfidenceDot tier={tier} />
        <span className="text-muted-foreground text-[11px] shrink-0">{label}</span>
      </div>
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-xs truncate max-w-[160px]">{displayValue}</span>
        <ConfidenceBadge score={confidence} />
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

interface AIExtractionPanelProps {
  result:    AIExtractionResult;
  className?: string;
}

export function AIExtractionPanel({ result, className }: AIExtractionPanelProps) {
  const tier = confidenceTier(result.overall_confidence);
  const OverallIcon =
    tier === "high"   ? CheckCircle2 :
    tier === "medium" ? AlertTriangle :
                        XCircle;

  const headerFields = Object.entries(result.header) as [keyof AIExtractionHeader, { value: string | number | null; confidence: number }][];

  return (
    <div className={cn("border border-border rounded-xl overflow-hidden text-xs", className)}>
      {/* Header bar */}
      <div className={cn("flex items-center gap-2 px-3 py-2.5 border-b border-border", CONF_COLOR[tier])}>
        <Sparkles className="w-3.5 h-3.5 shrink-0" />
        <span className="font-semibold flex-1">AI Extraction — {CONF_LABEL[tier]}</span>
        <OverallIcon className="w-3.5 h-3.5 shrink-0" />
        <span className="font-mono font-bold">{(result.overall_confidence * 100).toFixed(0)}%</span>
      </div>

      {/* Model badge */}
      <div className="px-3 py-1.5 border-b border-border bg-muted/30 flex items-center justify-between">
        <span className="text-muted-foreground text-[10px]">Powered by {result.model}</span>
        <span className={cn(
          "text-[10px] font-semibold px-2 py-0.5 rounded-full border",
          result.status === "AI_EXTRACTED" ? "bg-green-50 text-green-700 border-green-300" :
          result.status === "NEEDS_REVIEW" ? "bg-amber-50 text-amber-700 border-amber-300" :
                                             "bg-red-50 text-red-700 border-red-300"
        )}>
          {result.status.replace(/_/g, " ")}
        </span>
      </div>

      {/* Warnings */}
      {result.warnings.length > 0 && (
        <div className="px-3 py-2 bg-amber-50 border-b border-border space-y-1">
          {result.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1.5 text-amber-700">
              <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {/* Low-confidence summary */}
      {result.low_confidence_fields.length > 0 && (
        <div className="px-3 py-2 bg-red-50 border-b border-border">
          <p className="text-[10px] font-semibold text-red-700 uppercase tracking-wide mb-0.5">
            Low confidence — verify manually
          </p>
          <p className="text-red-700">
            {result.low_confidence_fields.map(f => HEADER_FIELD_LABELS[f as keyof AIExtractionHeader] ?? f).join(", ")}
          </p>
        </div>
      )}

      {/* Header fields */}
      <div>
        {headerFields.map(([key, field]) => (
          <AIFieldRow
            key={key}
            label={HEADER_FIELD_LABELS[key]}
            value={field.value}
            confidence={field.confidence}
          />
        ))}
      </div>

      {/* Line items */}
      {result.line_items.length > 0 && (
        <div className="border-t border-border">
          <div className="px-3 py-1.5 bg-muted/30">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Line Items ({result.line_items.length})
            </p>
          </div>
          {result.line_items.map((item, i) => {
            const itemTier = confidenceTier(item.confidence);
            return (
              <div
                key={i}
                className={cn(
                  "px-3 py-2 border-b border-border last:border-b-0 space-y-0.5",
                  itemTier === "low" && "bg-red-50/40",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <ConfidenceDot tier={itemTier} />
                    <span className="font-semibold truncate max-w-[200px]">{item.description || "—"}</span>
                  </div>
                  <ConfidenceBadge score={item.confidence} />
                </div>
                <div className="flex items-center gap-3 text-muted-foreground pl-3.5">
                  {item.quantity != null && <span>Qty: {item.quantity}</span>}
                  {item.unit_rate != null && (
                    <span>@R{Number(item.unit_rate).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}</span>
                  )}
                  {item.total != null && (
                    <span className="font-semibold text-foreground ml-auto">
                      R{Number(item.total).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Mandatory review disclaimer */}
      <div className="px-3 py-2 bg-muted/20 text-muted-foreground text-[10px] flex items-center gap-1.5">
        <AlertTriangle className="w-3 h-3 shrink-0" />
        Human review required. No invoice is created automatically.
      </div>
    </div>
  );
}

// ── Loading state ─────────────────────────────────────────────────────────────

export function AIExtractionLoading() {
  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2.5 bg-muted/40 border-b border-border">
        <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0 text-muted-foreground" />
        <span className="text-xs text-muted-foreground">Running AI extraction…</span>
        <Sparkles className="w-3.5 h-3.5 ml-auto text-muted-foreground" />
      </div>
      <div className="px-3 py-4 text-center text-xs text-muted-foreground">
        Claude is analysing the invoice. This may take a few seconds.
      </div>
    </div>
  );
}
