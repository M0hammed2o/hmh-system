/**
 * SiteWorkshop — Workshop MR panel embedded in the site dashboard.
 * Site staff can:
 *   - View their workshop MRs and track status
 *   - Create a new Workshop MR (vehicle + reason + parts from catalog)
 *   - Submit a draft MR to the office for approval
 */

import { useEffect, useState, useCallback } from "react";
import {
  Wrench, Plus, ChevronRight, RefreshCw, ClipboardList,
  Trash2, CheckCircle2, Clock, Ban, X,
} from "lucide-react";
import {
  workshopApi,
  type WorkshopMR,
  type WorkshopItem,
  type WorkshopCategory,
  type MRPriority,
  type WorkshopMRLineCreate,
} from "@/api/workshop";
import { vehiclesApi, type Vehicle } from "@/api/vehicles";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

// ── Status display helpers ────────────────────────────────────────────────────

const MR_STATUS_BADGE: Record<string, string> = {
  DRAFT:     "bg-gray-100 text-gray-600 border-gray-200",
  SUBMITTED: "bg-blue-100 text-blue-700 border-blue-200",
  APPROVED:  "bg-green-100 text-green-700 border-green-200",
  REJECTED:  "bg-red-100 text-red-700 border-red-200",
};

const MR_STATUS_LABEL: Record<string, string> = {
  DRAFT:     "Draft",
  SUBMITTED: "Pending Approval",
  APPROVED:  "Approved",
  REJECTED:  "Rejected",
};

const PRIORITY_BADGE: Record<string, string> = {
  LOW:    "bg-gray-100 text-gray-500",
  NORMAL: "bg-blue-50 text-blue-600",
  HIGH:   "bg-amber-100 text-amber-700",
  URGENT: "bg-red-100 text-red-700",
};

function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

// ── ModalShell (local copy matching the one in SiteDashboardPage) ─────────────

function ModalShell({ title, onClose, children }: {
  title: string; onClose: () => void; children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end sm:items-center justify-center">
      <div className="w-full sm:max-w-lg bg-card rounded-t-2xl sm:rounded-2xl shadow-xl max-h-[94vh] overflow-y-auto">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border sticky top-0 bg-card z-10">
          <h3 className="font-semibold text-sm">{title}</h3>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-muted text-muted-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-4 space-y-4">{children}</div>
      </div>
    </div>
  );
}

// ── Create Workshop MR modal ──────────────────────────────────────────────────

interface LineRow {
  key: string;
  item: WorkshopItem | null;
  qty: string;
  remarks: string;
}

function CreateWorkshopMRModal({
  siteId,
  onClose,
  onDone,
}: {
  siteId: string;
  onClose: () => void;
  onDone: (mr: WorkshopMR) => void;
}) {
  const [vehicles,   setVehicles]   = useState<Vehicle[]>([]);
  const [categories, setCategories] = useState<WorkshopCategory[]>([]);
  const [items,      setItems]      = useState<WorkshopItem[]>([]);
  const [loadingRef, setLoadingRef] = useState(true);

  const [vehicleId, setVehicleId] = useState("");
  const [reason,    setReason]    = useState("");
  const [priority,  setPriority]  = useState<MRPriority>("NORMAL");
  const [neededBy,  setNeededBy]  = useState("");
  const [notes,     setNotes]     = useState("");
  const [lines,     setLines]     = useState<LineRow[]>([]);

  const [catFilter,    setCatFilter]    = useState("");
  const [itemSearch,   setItemSearch]   = useState("");
  const [showPicker,   setShowPicker]   = useState(false);

  const [saving,   setSaving]   = useState(false);
  const [error,    setError]    = useState("");

  useEffect(() => {
    Promise.all([
      vehiclesApi.list(undefined, siteId).catch(() => [] as Vehicle[]),
      workshopApi.listCategories().catch(() => [] as WorkshopCategory[]),
      workshopApi.listItems().catch(() => [] as WorkshopItem[]),
    ]).then(([v, c, i]) => {
      setVehicles(v);
      setCategories(c);
      setItems(i);
    }).finally(() => setLoadingRef(false));
  }, [siteId]);

  const filteredItems = items.filter(it => {
    if (catFilter && it.category_id !== catFilter) return false;
    if (itemSearch.trim()) {
      const q = itemSearch.toLowerCase();
      return it.name.toLowerCase().includes(q) || (it.part_number ?? "").toLowerCase().includes(q);
    }
    return true;
  });

  const addItem = (it: WorkshopItem) => {
    if (lines.some(l => l.item?.id === it.id)) return;
    setLines(prev => [...prev, { key: it.id, item: it, qty: "1", remarks: "" }]);
    setShowPicker(false);
    setItemSearch("");
  };

  const updateLine = (key: string, field: "qty" | "remarks", val: string) =>
    setLines(prev => prev.map(l => l.key === key ? { ...l, [field]: val } : l));

  const removeLine = (key: string) =>
    setLines(prev => prev.filter(l => l.key !== key));

  const validLines = lines.filter(l => l.item && parseFloat(l.qty) > 0);

  const submit = async (andSubmit: boolean) => {
    if (!vehicleId) { setError("Select a vehicle."); return; }
    if (!reason.trim()) { setError("Enter a reason for the request."); return; }
    if (validLines.length === 0) { setError("Add at least one parts line."); return; }

    setSaving(true);
    setError("");
    try {
      const body = {
        site_id: siteId,
        vehicle_id: vehicleId,
        reason: reason.trim(),
        priority,
        needed_by_date: neededBy || null,
        notes: notes.trim() || null,
        lines: validLines.map<WorkshopMRLineCreate>(l => ({
          item_id: l.item!.id,
          quantity_requested: parseFloat(l.qty),
          remarks: l.remarks.trim() || undefined,
        })),
      };
      let mr = await workshopApi.createMR(body);
      if (andSubmit) {
        mr = await workshopApi.submitMR(mr.id);
      }
      onDone(mr);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? "Failed to save request. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const todayStr = () => new Date().toISOString().split("T")[0];

  return (
    <ModalShell title="New Workshop Parts Request" onClose={onClose}>
      {loadingRef ? (
        <div className="py-10 text-center text-sm text-muted-foreground">Loading…</div>
      ) : (
        <div className="space-y-4">

          {/* Vehicle */}
          <div className="space-y-1">
            <Label className="text-xs">Vehicle *</Label>
            <select
              value={vehicleId}
              onChange={e => setVehicleId(e.target.value)}
              className="w-full h-10 px-3 text-sm rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">— Select vehicle —</option>
              {vehicles.map(v => (
                <option key={v.id} value={v.id}>
                  {v.registration} — {v.name}
                </option>
              ))}
            </select>
            {vehicles.length === 0 && (
              <p className="text-xs text-amber-600">No vehicles assigned to this site.</p>
            )}
          </div>

          {/* Reason */}
          <div className="space-y-1">
            <Label className="text-xs">Reason / description of work *</Label>
            <textarea
              rows={2}
              value={reason}
              onChange={e => setReason(e.target.value)}
              placeholder="e.g. Tyre replacement — front left blowout, routine service…"
              className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none
                         focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          {/* Priority + Needed by */}
          <div className="flex gap-3">
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Priority</Label>
              <select
                value={priority}
                onChange={e => setPriority(e.target.value as MRPriority)}
                className="w-full h-9 px-3 text-sm rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="LOW">Low</option>
                <option value="NORMAL">Normal</option>
                <option value="HIGH">High</option>
                <option value="URGENT">Urgent</option>
              </select>
            </div>
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Needed by</Label>
              <Input
                type="date"
                min={todayStr()}
                value={neededBy}
                onChange={e => setNeededBy(e.target.value)}
                className="h-9 text-sm"
              />
            </div>
          </div>

          {/* Parts lines */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs">Parts / items required *</Label>
              <button
                type="button"
                onClick={() => setShowPicker(p => !p)}
                className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 font-medium"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Part
              </button>
            </div>

            {/* Item picker */}
            {showPicker && (
              <div className="border border-border rounded-xl bg-background overflow-hidden shadow-sm">
                <div className="p-2 border-b border-border space-y-1.5">
                  <select
                    value={catFilter}
                    onChange={e => setCatFilter(e.target.value)}
                    className="w-full h-8 px-2 text-xs rounded-md border border-border bg-card"
                  >
                    <option value="">All categories</option>
                    {categories.map(c => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                  <Input
                    placeholder="Search part name or number…"
                    value={itemSearch}
                    onChange={e => setItemSearch(e.target.value)}
                    className="h-8 text-xs"
                    autoFocus
                  />
                </div>
                <div className="max-h-44 overflow-y-auto divide-y divide-border">
                  {filteredItems.length === 0 ? (
                    <p className="text-xs text-muted-foreground px-3 py-3 text-center">No parts found.</p>
                  ) : filteredItems.map(it => (
                    <button
                      key={it.id}
                      type="button"
                      onClick={() => addItem(it)}
                      disabled={lines.some(l => l.item?.id === it.id)}
                      className={cn(
                        "w-full text-left px-3 py-2 text-xs hover:bg-muted transition-colors",
                        lines.some(l => l.item?.id === it.id) && "opacity-40 cursor-not-allowed"
                      )}
                    >
                      <span className="font-medium">{it.name}</span>
                      {it.part_number && (
                        <span className="ml-1.5 text-muted-foreground">#{it.part_number}</span>
                      )}
                      <span className="ml-1.5 text-muted-foreground">· {it.unit}</span>
                      <span className={cn(
                        "ml-1.5 text-[10px] rounded px-1 py-0.5",
                        it.quantity_on_hand > 0 ? "text-green-700 bg-green-50" : "text-amber-700 bg-amber-50"
                      )}>
                        {it.quantity_on_hand > 0 ? `${it.quantity_on_hand} in stock` : "out of stock"}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Lines table */}
            {lines.length > 0 && (
              <div className="space-y-1.5">
                {lines.map(l => (
                  <div key={l.key} className="flex items-start gap-2 bg-muted/30 rounded-lg px-2.5 py-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate">{l.item?.name}</p>
                      {l.item?.part_number && (
                        <p className="text-[10px] text-muted-foreground">#{l.item.part_number}</p>
                      )}
                      <div className="flex items-center gap-2 mt-1.5">
                        <Input
                          type="number" min="0.001" step="any"
                          placeholder="Qty"
                          value={l.qty}
                          onChange={e => updateLine(l.key, "qty", e.target.value)}
                          className="h-7 text-xs w-20"
                        />
                        <span className="text-xs text-muted-foreground shrink-0">{l.item?.unit}</span>
                        <Input
                          placeholder="Remarks (optional)"
                          value={l.remarks}
                          onChange={e => updateLine(l.key, "remarks", e.target.value)}
                          className="h-7 text-xs flex-1"
                        />
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeLine(l.key)}
                      className="mt-0.5 p-1 text-muted-foreground hover:text-destructive transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Notes */}
          <div className="space-y-1">
            <Label className="text-xs">Additional notes (optional)</Label>
            <textarea
              rows={2}
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Any extra info for the office…"
              className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background resize-none
                         focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          {error && (
            <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex gap-2 pt-1">
            <Button
              variant="outline"
              className="flex-1"
              disabled={saving}
              onClick={() => submit(false)}
            >
              {saving ? "Saving…" : "Save as Draft"}
            </Button>
            <Button
              className="flex-1"
              disabled={saving}
              onClick={() => submit(true)}
            >
              {saving ? "Submitting…" : "Submit for Approval"}
            </Button>
          </div>
        </div>
      )}
    </ModalShell>
  );
}

// ── Main SiteWorkshop component ───────────────────────────────────────────────

interface Props {
  siteId: string;
  isViewOnly?: boolean;
}

export function SiteWorkshop({ siteId, isViewOnly = false }: Props) {
  const [mrs,       setMrs]       = useState<WorkshopMR[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState("");
  const [expanded,  setExpanded]  = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const [submitting, setSubmitting] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    workshopApi.listMRs({ site_id: siteId })
      .then(setMrs)
      .catch(() => setError("Failed to load workshop requests."))
      .finally(() => setLoading(false));
  }, [siteId]);

  useEffect(() => { load(); }, [load]);

  const handleSubmit = async (mrId: string) => {
    setSubmitting(mrId);
    try {
      const updated = await workshopApi.submitMR(mrId);
      setMrs(prev => prev.map(m => m.id === updated.id ? updated : m));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      alert(detail ?? "Failed to submit MR.");
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Wrench className="w-4 h-4 text-primary" />
          <span className="font-semibold text-sm">Workshop Requests</span>
          {mrs.length > 0 && (
            <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
              {mrs.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={load}
            disabled={loading}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          </button>
          {!isViewOnly && (
            <Button
              size="sm"
              onClick={() => setShowCreate(true)}
              className="h-8 text-xs"
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              New Request
            </Button>
          )}
        </div>
      </div>

      {error && (
        <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>
      )}

      {loading ? (
        <div className="py-8 text-center text-sm text-muted-foreground">Loading…</div>
      ) : mrs.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-8 text-center space-y-2">
          <ClipboardList className="w-8 h-8 text-muted-foreground mx-auto" />
          <p className="text-sm text-muted-foreground">No workshop requests yet.</p>
          {!isViewOnly && (
            <p className="text-xs text-muted-foreground">
              Tap <strong>New Request</strong> to request parts for a vehicle repair.
            </p>
          )}
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden divide-y divide-border">
          {mrs.map(mr => {
            const isOpen = expanded === mr.id;
            const badge  = MR_STATUS_BADGE[mr.status] ?? "bg-gray-100 text-gray-600 border-gray-200";
            const label  = MR_STATUS_LABEL[mr.status] ?? mr.status;
            const priCls = PRIORITY_BADGE[mr.priority] ?? PRIORITY_BADGE.NORMAL;
            return (
              <div key={mr.id}>
                <button
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/30 text-left transition-colors"
                  onClick={() => setExpanded(isOpen ? null : mr.id)}
                >
                  {/* Status icon */}
                  <div className="shrink-0">
                    {mr.status === "APPROVED" ? (
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                    ) : mr.status === "SUBMITTED" ? (
                      <Clock className="w-4 h-4 text-blue-500" />
                    ) : mr.status === "REJECTED" ? (
                      <Ban className="w-4 h-4 text-red-500" />
                    ) : (
                      <Wrench className="w-4 h-4 text-muted-foreground" />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium">{mr.mr_number}</span>
                      <span className={cn("text-xs px-1.5 py-0.5 rounded border font-medium", badge)}>
                        {label}
                      </span>
                      {mr.priority !== "NORMAL" && (
                        <span className={cn("text-xs px-1.5 py-0.5 rounded font-medium", priCls)}>
                          {mr.priority}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">
                      {mr.reason}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {mr.lines.length} part{mr.lines.length !== 1 ? "s" : ""}
                      {" · "}{shortDate(mr.created_at)}
                    </p>
                  </div>

                  <ChevronRight className={cn("w-4 h-4 text-muted-foreground shrink-0 transition-transform", isOpen && "rotate-90")} />
                </button>

                {isOpen && (
                  <div className="px-4 pb-4 pt-2 bg-muted/20 border-t border-border/50 space-y-3">
                    {/* Parts */}
                    {mr.lines.length > 0 && (
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Parts</p>
                        <div className="divide-y divide-border border border-border rounded-lg overflow-hidden">
                          {mr.lines.map((line, i) => (
                            <div key={line.id ?? i} className="flex items-center gap-2 px-3 py-2 bg-card">
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium truncate">
                                  {line.item?.name ?? "Unknown item"}
                                </p>
                                {line.item?.part_number && (
                                  <p className="text-[10px] text-muted-foreground">#{line.item.part_number}</p>
                                )}
                                {line.remarks && (
                                  <p className="text-[10px] text-muted-foreground italic">{line.remarks}</p>
                                )}
                              </div>
                              <div className="text-right shrink-0">
                                <p className="text-xs font-semibold tabular-nums">
                                  {line.quantity_requested} {line.item?.unit ?? ""}
                                </p>
                                {line.quantity_approved != null && (
                                  <p className="text-[10px] text-green-600">
                                    Approved: {line.quantity_approved}
                                  </p>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Notes */}
                    {mr.notes && (
                      <p className="text-xs text-muted-foreground italic">{mr.notes}</p>
                    )}

                    {/* Rejection reason */}
                    {mr.rejection_reason && (
                      <p className="text-xs text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                        Rejected: {mr.rejection_reason}
                      </p>
                    )}

                    {/* Needed by date */}
                    {mr.needed_by_date && (
                      <p className="text-xs text-muted-foreground">
                        Needed by: <span className="font-medium text-foreground">{shortDate(mr.needed_by_date)}</span>
                      </p>
                    )}

                    {/* Submit draft action */}
                    {!isViewOnly && mr.status === "DRAFT" && (
                      <Button
                        size="sm"
                        className="w-full"
                        disabled={submitting === mr.id}
                        onClick={() => handleSubmit(mr.id)}
                      >
                        {submitting === mr.id ? "Submitting…" : "Submit for Approval"}
                      </Button>
                    )}

                    {mr.status === "APPROVED" && mr.approved_at && (
                      <p className="text-xs text-green-700 bg-green-50 rounded-lg px-3 py-2">
                        Approved {shortDate(mr.approved_at)} — office will arrange parts.
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <CreateWorkshopMRModal
          siteId={siteId}
          onClose={() => setShowCreate(false)}
          onDone={mr => {
            setMrs(prev => [mr, ...prev]);
            setShowCreate(false);
          }}
        />
      )}
    </div>
  );
}
