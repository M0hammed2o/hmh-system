/**
 * User Activity / Audit Trail page.
 * Shows all audit events from the audit_events table via GET /api/v1/audit.
 * Admin-only view — read-only users may view but cannot edit.
 */
import { useEffect, useState, useCallback } from "react";
import { RefreshCw, Search, Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import client from "@/api/client";
import { formatDate } from "@/lib/format";
import { usersApi, type User } from "@/api/users";

interface AuditEvent {
  id: string;
  actor_id:    string | null;
  action:      string;
  entity_type: string;
  entity_id:   string | null;
  before_value: unknown;
  after_value:  unknown;
  notes:       string | null;
  created_at:  string;
}

const ACTION_COLOR: Record<string, string> = {
  CREATE: "bg-green-100 text-green-700",
  UPDATE: "bg-blue-100 text-blue-700",
  DELETE: "bg-red-100 text-red-700",
  APPROVE: "bg-purple-100 text-purple-700",
  REJECT: "bg-orange-100 text-orange-700",
  LOGIN: "bg-muted text-muted-foreground",
  LOGOUT: "bg-muted text-muted-foreground",
  SEND: "bg-indigo-100 text-indigo-700",
};

export default function AuditPage() {
  const [events, setEvents]     = useState<AuditEvent[]>([]);
  const [users, setUsers]       = useState<User[]>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  // Filters
  const [filterUser,       setFilterUser]       = useState("");
  const [filterEntityType, setFilterEntityType] = useState("");
  const [filterAction,     setFilterAction]     = useState("");
  const [filterFrom,       setFilterFrom]       = useState("");
  const [filterTo,         setFilterTo]         = useState("");
  const [limit,            setLimit]            = useState(100);

  useEffect(() => {
    usersApi.list(1, 200).then(r => setUsers(r.items)).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string | number> = { limit };
      if (filterUser)       params.actor_id    = filterUser;
      if (filterEntityType) params.entity_type = filterEntityType;
      if (filterAction)     params.action      = filterAction;
      if (filterFrom)       params.from_date   = new Date(filterFrom).toISOString();
      if (filterTo)         params.to_date     = new Date(filterTo).toISOString();

      const res = await client.get<{ data: AuditEvent[] }>("/audit/", { params });
      setEvents(res.data.data || []);
    } catch {
      setError("Failed to load audit events.");
    } finally { setLoading(false); }
  }, [filterUser, filterEntityType, filterAction, filterFrom, filterTo, limit]);

  useEffect(() => { load(); }, [load]);

  const userName = (actorId: string | null) => {
    if (!actorId) return "System";
    const u = users.find(u => u.id === actorId);
    return u ? `${u.full_name} (${u.role})` : actorId.slice(0, 8);
  };

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="User Activity"
        description="Audit trail of all system actions by users."
        actions={
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        }
      />

      {/* Filters */}
      <div className="bg-card border border-border rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <Filter className="w-3.5 h-3.5" />
          Filters
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <select
            value={filterUser}
            onChange={e => setFilterUser(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">All users</option>
            {users.map(u => (
              <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>
            ))}
          </select>

          <Input
            placeholder="Module (e.g. material_request)"
            value={filterEntityType}
            onChange={e => setFilterEntityType(e.target.value)}
            className="h-9 text-sm"
          />

          <select
            value={filterAction}
            onChange={e => setFilterAction(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">All actions</option>
            {["CREATE","UPDATE","DELETE","APPROVE","REJECT","LOGIN","LOGOUT","SEND","UPLOAD","SIGN"].map(a => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>

          <Input type="date" value={filterFrom} onChange={e => setFilterFrom(e.target.value)} className="h-9 text-sm" placeholder="From" />
          <Input type="date" value={filterTo}   onChange={e => setFilterTo(e.target.value)}   className="h-9 text-sm" placeholder="To" />
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* Table */}
      {loading ? (
        <div className="space-y-2">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-12 rounded-xl" />)}</div>
      ) : events.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center text-sm text-muted-foreground">
          No audit events found for the selected filters.
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground whitespace-nowrap">Timestamp</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">User</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Action</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Module</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Record</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Notes</th>
              </tr>
            </thead>
            <tbody>
              {events.map(ev => (
                <tr key={ev.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                    {formatDate(ev.created_at)}
                  </td>
                  <td className="px-4 py-2.5 text-xs">{userName(ev.actor_id)}</td>
                  <td className="px-4 py-2.5">
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${ACTION_COLOR[ev.action] || "bg-muted text-muted-foreground"}`}>
                      {ev.action}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-xs font-mono">{ev.entity_type}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground font-mono hidden md:table-cell">
                    {ev.entity_id ? ev.entity_id.slice(0, 8) : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground max-w-64 truncate hidden lg:table-cell">
                    {ev.notes ||
                      (ev.after_value
                        ? JSON.stringify(ev.after_value).slice(0, 80)
                        : "—")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-2.5 text-xs text-muted-foreground border-t border-border flex items-center justify-between">
            <span>Showing {events.length} events</span>
            {events.length >= limit && (
              <button
                onClick={() => setLimit(l => l + 100)}
                className="text-primary hover:underline"
              >
                Load more
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
