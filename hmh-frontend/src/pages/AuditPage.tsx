/**
 * User Activity page — owner-friendly audit trail.
 * Shows human-readable descriptions instead of raw UUIDs and JSON.
 */
import { useEffect, useState, useCallback, useMemo } from "react";
import { RefreshCw, Search, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import client from "@/api/client";
import { usersApi, type User } from "@/api/users";

// ── Types ──────────────────────────────────────────────────────────────────────

interface AuditEvent {
  id: string;
  actor_id:     string | null;
  action:       string;
  entity_type:  string;
  entity_id:    string | null;
  before_value: Record<string, unknown> | null;
  after_value:  Record<string, unknown> | null;
  notes:        string | null;
  created_at:   string;
}

// ── Display helpers ───────────────────────────────────────────────────────────

const ACTION_LABEL: Record<string, string> = {
  CREATE:   "Created",
  UPDATE:   "Updated",
  DELETE:   "Deleted",
  APPROVE:  "Approved",
  REJECT:   "Rejected",
  LOGIN:    "Logged in",
  LOGOUT:   "Logged out",
  SEND:     "Sent",
  UPLOAD:   "Uploaded",
  SIGN:     "Signed",
  TRANSFER: "Transferred",
  ISSUE:    "Issued",
  OVERRUN_ACCEPTED: "Overrun accepted",
};

const MODULE_LABEL: Record<string, string> = {
  boq_header:         "BOQ",
  boq_section:        "BOQ Section",
  boq_item:           "BOQ Item",
  material_request:   "Material Request",
  purchase_order:     "Purchase Order",
  delivery:           "Delivery",
  invoice:            "Invoice",
  payment:            "Payment",
  job_card:           "Job Card",
  vehicle:            "Vehicle",
  vehicle_cost:       "Vehicle Cost",
  fuel_log:           "Fuel Log",
  project:            "Project",
  site:               "Site",
  lot:                "Lot",
  stage:              "Stage",
  user:               "User",
  stock:              "Stock",
  usage_log:          "Usage",
  alert:              "Alert",
};

const ACTION_COLOR: Record<string, string> = {
  CREATE:   "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  UPDATE:   "bg-blue-100  text-blue-700  dark:bg-blue-900/30  dark:text-blue-400",
  DELETE:   "bg-red-100   text-red-700   dark:bg-red-900/30   dark:text-red-400",
  APPROVE:  "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  REJECT:   "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  SEND:     "bg-indigo-100 text-indigo-700",
  LOGIN:    "bg-muted text-muted-foreground",
  LOGOUT:   "bg-muted text-muted-foreground",
};

const fmtAction  = (a: string) => ACTION_LABEL[a]  ?? a.charAt(0).toUpperCase() + a.slice(1).toLowerCase();
const fmtModule  = (m: string) => MODULE_LABEL[m]  ?? m.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
const fmtCurrency = (n: unknown) => n != null ? `R${Number(n).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}` : null;

/** Convert an audit after_value / notes into a short human-readable description. */
function summarize(ev: AuditEvent): string {
  const v = ev.after_value ?? {};
  const mod = ev.entity_type;
  const act = ev.action;

  // BOQ
  if (mod === "boq_header") {
    if (v.lot_number)           return `BOQ cloned to Lot ${v.lot_number}`;
    if (v.version_name)         return `BOQ "${v.version_name}"`;
    if (v.template_name)        return `Template "${v.template_name}"`;
  }

  // Material Request
  if (mod === "material_request") {
    if (v.request_number)       return `${v.request_number}${v.status ? ` → ${String(v.status).replace(/_/g, " ")}` : ""}`;
    if (ev.notes && typeof ev.notes === "string") return ev.notes;
  }

  // Purchase Order
  if (mod === "purchase_order") {
    if (v.po_number)            return `${v.po_number}${v.email_status ? ` (email: ${v.email_status})` : ""}${v.from_mr ? ` from ${v.from_mr}` : ""}`;
  }

  // Invoice
  if (mod === "invoice") {
    const num = v.invoice_number ?? v.number;
    const total = fmtCurrency(v.total_amount ?? v.total);
    if (num && total)           return `Invoice ${num} for ${total}`;
    if (num)                    return `Invoice ${num}`;
  }

  // Payment
  if (mod === "payment") {
    const ref   = v.payment_reference ?? v.reference;
    const amt   = fmtCurrency(v.amount_paid ?? v.amount);
    const ptype = v.payment_type;
    if (ref && amt)             return `${ptype ? String(ptype) + " p" : "P"}ayment ${ref}: ${amt}`;
    if (amt)                    return `Payment of ${amt}`;
  }

  // Job Card
  if (mod === "job_card") {
    const num = v.job_card_number ?? v.number;
    const amt = fmtCurrency(v.total_amount ?? v.total);
    if (num && amt)             return `${num} — ${amt}`;
    if (num)                    return String(num);
    if (v.status)               return `Status → ${String(v.status).replace(/_/g, " ")}`;
  }

  // Delivery
  if (mod === "delivery") {
    if (v.delivery_number)      return `Delivery ${v.delivery_number}`;
  }

  // Stage
  if (mod === "stage") {
    if (v.status)               return `Stage → ${String(v.status).replace(/_/g, " ")}`;
  }

  // Stock / usage
  if (mod === "usage_log") {
    if (v.quantity_used)        return `${v.quantity_used} ${v.unit ?? ""}`.trim();
  }

  // Vehicle
  if (mod === "vehicle_cost") {
    const amt = fmtCurrency(v.amount);
    const typ = v.cost_type;
    if (typ && amt)             return `${String(typ).replace(/_/g, " ")}: ${amt}`;
  }

  if (mod === "fuel_log") {
    const litres = v.litres;
    const cost   = fmtCurrency(v.total_cost ?? v.cost);
    if (litres && cost)         return `${litres} L — ${cost}`;
    if (litres)                 return `${litres} L`;
  }

  // Generic status change
  if (v.status)                 return `Status → ${String(v.status).replace(/_/g, " ")}`;
  if (v.reason)                 return String(v.reason);

  // Use notes if available
  if (ev.notes)                 return ev.notes;

  return "";
}

/** Parse a date into a readable group label. */
function dateGroup(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  const weekAgo   = new Date(today); weekAgo.setDate(today.getDate() - 7);

  const eventDay = new Date(d); eventDay.setHours(0, 0, 0, 0);
  if (eventDay.getTime() === today.getTime())         return "Today";
  if (eventDay.getTime() === yesterday.getTime())     return "Yesterday";
  if (eventDay >= weekAgo)                            return "This Week";
  return d.toLocaleDateString("en-ZA", { month: "long", year: "numeric" });
}

/** Format timestamp for display. */
function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit" });
}
function fmtDateShort(iso: string) {
  return new Date(iso).toLocaleDateString("en-ZA", { weekday: "short", day: "numeric", month: "short" });
}

// ── Single event card ─────────────────────────────────────────────────────────

function EventCard({
  ev, userName,
}: { ev: AuditEvent; userName: (id: string | null) => string }) {
  const [showRaw, setShowRaw] = useState(false);
  const description = summarize(ev);
  const color = ACTION_COLOR[ev.action] ?? "bg-muted text-muted-foreground";

  return (
    <div className="flex gap-3 group">
      {/* Action badge column */}
      <div className="shrink-0 pt-0.5">
        <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${color}`}>
          {fmtAction(ev.action)}
        </span>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pb-3 border-b border-border/50 last:border-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <span className="text-sm font-medium">{userName(ev.actor_id)}</span>
            <span className="text-sm text-muted-foreground"> {fmtAction(ev.action).toLowerCase()} </span>
            <span className="text-sm font-medium">{fmtModule(ev.entity_type)}</span>
          </div>
          <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">{fmtTime(ev.created_at)}</span>
        </div>

        {description && (
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{description}</p>
        )}

        {/* Raw JSON toggle (hidden by default) */}
        {(ev.after_value || ev.notes) && (
          <button
            onClick={() => setShowRaw(s => !s)}
            className="mt-1 text-[10px] text-muted-foreground/60 hover:text-muted-foreground flex items-center gap-0.5 transition-colors"
          >
            {showRaw ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            Technical details
          </button>
        )}
        {showRaw && (
          <pre className="mt-1 text-[10px] font-mono bg-muted rounded p-2 text-muted-foreground overflow-x-auto max-w-full">
            {JSON.stringify(ev.after_value ?? ev.notes, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function AuditPage() {
  const [events,  setEvents]  = useState<AuditEvent[]>([]);
  const [users,   setUsers]   = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  // Filters (sent to API)
  const [filterUser,   setFilterUser]   = useState("");
  const [filterModule, setFilterModule] = useState("");
  const [filterAction, setFilterAction] = useState("");
  const [filterFrom,   setFilterFrom]   = useState("");
  const [filterTo,     setFilterTo]     = useState("");
  const [limit,        setLimit]        = useState(150);

  // Client-side search
  const [search, setSearch] = useState("");

  useEffect(() => {
    usersApi.list(1, 200).then(r => setUsers(r.items)).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string | number> = { limit };
      if (filterUser)   params.actor_id    = filterUser;
      if (filterModule) params.entity_type = filterModule;
      if (filterAction) params.action      = filterAction;
      if (filterFrom)   params.from_date   = new Date(filterFrom).toISOString();
      if (filterTo)     params.to_date     = new Date(filterTo + "T23:59:59").toISOString();
      const res = await client.get<{ data: AuditEvent[] }>("/audit/", { params });
      setEvents(res.data.data || []);
    } catch { setError("Failed to load activity."); }
    finally { setLoading(false); }
  }, [filterUser, filterModule, filterAction, filterFrom, filterTo, limit]);

  useEffect(() => { load(); }, [load]);

  const userName = (id: string | null) => {
    if (!id) return "System";
    const u = users.find(u => u.id === id);
    return u ? u.full_name : "Unknown User";
  };

  // Client-side search over visible fields
  const filtered = useMemo(() => {
    if (!search.trim()) return events;
    const q = search.toLowerCase();
    return events.filter(ev => {
      const desc = summarize(ev).toLowerCase();
      const user = userName(ev.actor_id).toLowerCase();
      const mod  = fmtModule(ev.entity_type).toLowerCase();
      const raw  = JSON.stringify(ev.after_value ?? "").toLowerCase();
      return desc.includes(q) || user.includes(q) || mod.includes(q) || raw.includes(q);
    });
  }, [events, search, users]);

  // Group by date
  const groups = useMemo(() => {
    const map = new Map<string, AuditEvent[]>();
    for (const ev of filtered) {
      const g = dateGroup(ev.created_at);
      const arr = map.get(g) ?? [];
      arr.push(ev);
      map.set(g, arr);
    }
    return map;
  }, [filtered]);

  const moduleOptions = [
    "boq_header","material_request","purchase_order","delivery","invoice","payment",
    "job_card","vehicle","vehicle_cost","fuel_log","project","site","lot","stage","user",
  ];

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="User Activity"
        description="Track who did what and when across the system."
        actions={
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        }
      />

      {/* Search + Filters */}
      <div className="space-y-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
          <Input
            className="pl-9 h-10"
            placeholder="Search by name, lot, PO number, job card, invoice…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          <select value={filterUser} onChange={e => setFilterUser(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm col-span-2 sm:col-span-1">
            <option value="">All users</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>

          <select value={filterModule} onChange={e => setFilterModule(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm">
            <option value="">All modules</option>
            {moduleOptions.map(m => <option key={m} value={m}>{fmtModule(m)}</option>)}
          </select>

          <select value={filterAction} onChange={e => setFilterAction(e.target.value)}
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm">
            <option value="">All actions</option>
            {["CREATE","UPDATE","APPROVE","REJECT","DELETE","SEND","LOGIN"].map(a => (
              <option key={a} value={a}>{fmtAction(a)}</option>
            ))}
          </select>

          <Input type="date" value={filterFrom} onChange={e => setFilterFrom(e.target.value)}
                 className="h-9 text-sm" placeholder="From date" />
          <Input type="date" value={filterTo}   onChange={e => setFilterTo(e.target.value)}
                 className="h-9 text-sm" placeholder="To date" />
        </div>
      </div>

      {error && <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">{error}</p>}

      {/* Activity feed */}
      {loading ? (
        <div className="space-y-3">{[1,2,3,4,5,6].map(i => <Skeleton key={i} className="h-14 rounded-xl" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center">
          <Search className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">No activity found.</p>
          {search && <p className="text-xs text-muted-foreground mt-1">Try a different search term or clear filters.</p>}
        </div>
      ) : (
        <div className="space-y-6">
          {Array.from(groups.entries()).map(([groupLabel, groupEvents]) => (
            <div key={groupLabel}>
              {/* Date group header */}
              <div className="flex items-center gap-3 mb-3">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">
                  {groupLabel}
                </span>
                <div className="flex-1 border-t border-border/50" />
                <span className="text-xs text-muted-foreground shrink-0">{groupEvents.length} events</span>
              </div>

              {/* Cards for this group */}
              <div className="bg-card border border-border rounded-xl px-4 py-3 space-y-3">
                {groupEvents.map((ev, i) => (
                  <div key={ev.id}>
                    {/* Mobile: date shown inline */}
                    {groupLabel !== "Today" && groupLabel !== "Yesterday" && (
                      <p className="text-[10px] text-muted-foreground mb-1 sm:hidden">
                        {fmtDateShort(ev.created_at)} {fmtTime(ev.created_at)}
                      </p>
                    )}
                    <EventCard ev={ev} userName={userName} />
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Load more */}
          {filtered.length >= limit && (
            <div className="text-center">
              <button
                onClick={() => setLimit(l => l + 150)}
                className="text-sm text-primary hover:underline"
              >
                Load older activity…
              </button>
            </div>
          )}

          <p className="text-center text-xs text-muted-foreground">
            Showing {filtered.length} events{search ? ` matching "${search}"` : ""}
          </p>
        </div>
      )}
    </div>
  );
}
