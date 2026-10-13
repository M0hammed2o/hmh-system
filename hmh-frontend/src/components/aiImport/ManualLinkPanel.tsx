/**
 * Manual record linking.
 *
 * When the engine cannot find the purchase order or material request a
 * document belongs to, a reviewer picks it here. Only records in the
 * document's own project are offered, and the backend re-checks that — this
 * control narrows the choice, it does not grant any access.
 */
import { useEffect, useMemo, useState } from "react";
import { Link2, Loader2, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { aiImportApi, type ImportDocumentDetail } from "@/api/aiImport";
import { purchaseOrdersApi, type PurchaseOrder } from "@/api/purchaseOrders";
import { materialRequestsApi, type MaterialRequest } from "@/api/materialRequests";
import type { Supplier } from "@/api/suppliers";

type LinkKind = "purchase_order" | "material_request";

interface Option {
  id: string;
  label: string;
  sub: string;
}

const fmtMoney = (n: number | null | undefined) =>
  n === null || n === undefined
    ? ""
    : `R ${Number(n).toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const fmtDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" }) : "";

export function ManualLinkPanel({
  doc,
  suppliers,
  disabled,
  onLinked,
}: {
  doc: ImportDocumentDetail;
  suppliers: Supplier[];
  disabled: boolean;
  onLinked: (updated: ImportDocumentDetail) => void;
}) {
  const [kind, setKind] = useState<LinkKind>("purchase_order");
  const [options, setOptions] = useState<Option[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Orders carry supplier_id only, so names are resolved from the list the
  // drawer already loaded rather than fetching each supplier again.
  const supplierName = useMemo(() => {
    const byId = new Map(suppliers.map((s) => [s.id, s.name]));
    return (id: string | null) => (id ? byId.get(id) ?? "" : "");
  }, [suppliers]);

  // Already-linked targets are not offered again.
  const linkedIds = useMemo(
    () =>
      new Set(
        doc.matches
          .filter((m) => m.target_type === kind && m.status !== "REJECTED" && m.target_id)
          .map((m) => m.target_id as string),
      ),
    [doc.matches, kind],
  );

  useEffect(() => {
    if (!doc.project_id) {
      setOptions([]);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);

    const load =
      kind === "purchase_order"
        ? purchaseOrdersApi.list(doc.project_id).then((rows: PurchaseOrder[]) =>
            rows.map((po) => ({
              id: po.id,
              label: po.po_number,
              sub: [supplierName(po.supplier_id), fmtDate(po.po_date), fmtMoney(po.total_amount), po.status]
                .filter(Boolean)
                .join(" · "),
            })),
          )
        : materialRequestsApi.list(doc.project_id).then((rows: MaterialRequest[]) =>
            rows.map((mr) => ({
              id: mr.id,
              label: mr.request_number,
              sub: [fmtDate(mr.requested_date), mr.status].filter(Boolean).join(" · "),
            })),
          );

    load
      .then((rows) => { if (active) setOptions(rows); })
      .catch(() => { if (active) setError("That list could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });

    return () => { active = false; };
  }, [doc.project_id, kind, supplierName]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return options
      .filter((o) => !linkedIds.has(o.id))
      .filter((o) => !q || o.label.toLowerCase().includes(q) || o.sub.toLowerCase().includes(q))
      .slice(0, 50);
  }, [options, query, linkedIds]);

  const submit = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await aiImportApi.addMatch(doc.id, kind, selected, reason.trim() || undefined);
      setSelected("");
      setReason("");
      setQuery("");
      onLinked(updated);
    } catch (err: unknown) {
      const res = (err as { response?: { data?: { detail?: unknown; message?: string } } })?.response?.data;
      const detail = res?.detail;
      setError(
        typeof detail === "string" ? detail : res?.message ?? "That record could not be linked.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!doc.project_id) {
    return (
      <div className="bg-card border border-border rounded-xl p-4">
        <h4 className="text-sm font-semibold mb-1">Link a record by hand</h4>
        <p className="text-sm text-muted-foreground">
          Set this document&rsquo;s project first. Records can only be linked within the
          project the document belongs to.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <h4 className="text-sm font-semibold mb-1">Link a record by hand</h4>
      <p className="text-xs text-muted-foreground mb-3">
        Use this when the system could not find the order or request this document belongs to.
        Only records in this project are listed.
      </p>

      <div className="flex flex-wrap gap-2 mb-3">
        {(["purchase_order", "material_request"] as LinkKind[]).map((k) => (
          <button
            key={k}
            onClick={() => { setKind(k); setSelected(""); setQuery(""); }}
            disabled={disabled || busy}
            className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
              kind === k
                ? "border-primary text-primary bg-primary/5"
                : "border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {k === "purchase_order" ? "Purchase order" : "Material request"}
          </button>
        ))}
      </div>

      <div className="relative mb-2">
        <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={disabled || busy || loading}
          placeholder={kind === "purchase_order" ? "Search order number or supplier" : "Search request number"}
          className="w-full h-9 pl-8 pr-3 rounded-md border border-border bg-background text-sm"
        />
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground flex items-center gap-2 py-3">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading&hellip;
        </p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground py-3">
          {options.length === 0
            ? "This project has no records of that type yet."
            : "Nothing matches that search."}
        </p>
      ) : (
        <div className="max-h-56 overflow-y-auto border border-border rounded-md divide-y divide-border mb-3">
          {filtered.map((o) => (
            <label
              key={o.id}
              className={`flex items-start gap-2 px-3 py-2 cursor-pointer text-sm hover:bg-muted/40 ${
                selected === o.id ? "bg-primary/5" : ""
              }`}
            >
              <input
                type="radio"
                name="manual-link-target"
                className="mt-1"
                checked={selected === o.id}
                disabled={disabled || busy}
                onChange={() => setSelected(o.id)}
              />
              <span className="min-w-0">
                <span className="font-medium block truncate">{o.label}</span>
                {o.sub && <span className="text-xs text-muted-foreground block truncate">{o.sub}</span>}
              </span>
            </label>
          ))}
        </div>
      )}

      {error && (
        <div className="bg-destructive/10 border border-destructive/30 text-destructive rounded-md px-3 py-2 text-sm mb-3">
          {error}
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-2">
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={disabled || busy}
          placeholder="Why is this the right record? (optional, recorded in the audit trail)"
          className="flex-1 h-9 px-3 rounded-md border border-border bg-background text-sm"
        />
        <Button onClick={submit} disabled={disabled || busy || !selected}>
          {busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Link2 className="w-4 h-4 mr-2" />}
          Link
        </Button>
      </div>
    </div>
  );
}
