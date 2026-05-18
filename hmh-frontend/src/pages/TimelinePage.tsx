/**
 * Timeline — read-only progress history for a project/site/lot.
 *
 * Shows in chronological order:
 *   - Stage updates (with evidence photos)
 *   - Deliveries
 *   - Material usage
 *   - Alerts
 */

import { useEffect, useState, useCallback } from "react";
import { Truck, Zap, AlertTriangle, Camera, ChevronDown, ChevronRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { projectsApi, type Project } from "@/api/projects";
import { sitesApi, type Site } from "@/api/sites";
import { lotsApi, type Lot } from "@/api/lots";
import client from "@/api/client";
import { formatDate } from "@/lib/format";
import { API_BASE } from "@/lib/constants";

// Convert a relative /uploads/… path to an absolute backend URL so the browser
// fetches the file from the API server, not from the frontend domain.
const BACKEND_ORIGIN = API_BASE.replace(/\/api\/v1\/?$/, "");
function toAbsUrl(path: string | undefined): string | undefined {
  if (!path) return undefined;
  if (path.startsWith("http")) return path;       // already absolute
  if (path.startsWith("/uploads/")) return `${BACKEND_ORIGIN}${path}`;
  return path;
}

// ── Types ──────────────────────────────────────────────────────────────────────

interface TimelineEntry {
  id: string;
  type: "delivery" | "stage" | "usage" | "alert";
  title: string;
  subtitle?: string;
  date: string;
  status?: string;
  photo_url?: string;
  severity?: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function entryIcon(type: TimelineEntry["type"]) {
  if (type === "delivery") return <Truck className="w-4 h-4" />;
  if (type === "stage")    return <ChevronRight className="w-4 h-4" />;
  if (type === "usage")    return <ChevronDown className="w-4 h-4" />;
  if (type === "alert")    return <AlertTriangle className="w-4 h-4" />;
  return null;
}

function entryColor(type: TimelineEntry["type"], severity?: string) {
  if (type === "delivery") return "bg-blue-500/10 text-blue-600";
  if (type === "stage")    return "bg-green-500/10 text-green-600";
  if (type === "usage")    return "bg-purple-500/10 text-purple-600";
  if (type === "alert") {
    if (severity === "CRITICAL") return "bg-destructive/10 text-destructive";
    return "bg-amber-500/10 text-amber-600";
  }
  return "bg-muted text-muted-foreground";
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TimelinePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [sites, setSites] = useState<Site[]>([]);
  const [lots, setLots] = useState<Lot[]>([]);

  const [projectId, setProjectId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [lotId, setLotId] = useState("");

  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Load projects on mount
  useEffect(() => {
    projectsApi.list(1, 100).then(r => {
      setProjects(r.items);
      if (r.items.length > 0) setProjectId(r.items[0].id);
    }).catch(() => {});
  }, []);

  // Load sites when project changes
  useEffect(() => {
    if (!projectId) return;
    sitesApi.list(projectId).then(ss => {
      setSites(ss);
      setSiteId(ss[0]?.id ?? "");
      setLots([]);
      setLotId("");
    }).catch(() => setSites([]));
  }, [projectId]);

  // Load lots when site changes
  useEffect(() => {
    if (!projectId || !siteId) return;
    lotsApi.list(projectId).then(ls => {
      const siteLots = ls.filter(l => l.site_id === siteId);
      setLots(siteLots);
      setLotId(siteLots[0]?.id ?? "");
    }).catch(() => setLots([]));
  }, [projectId, siteId]);

  const loadTimeline = useCallback(async () => {
    if (!projectId || !siteId) return;
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {};
      if (lotId) params.lot_id = lotId;

      const [deliveriesRes, activityRes] = await Promise.all([
        client.get<{ data: unknown[] }>(`/projects/${projectId}/deliveries/`, { params: { limit: 30 } }),
        lotId
          ? client.get<{ data: TimelineEntry[] }>(`/site-dashboard/${siteId}/lots/${lotId}/activity`, { params: { limit: 40 } })
          : Promise.resolve({ data: { data: [] } }),
      ]);

      const deliveries: TimelineEntry[] = (deliveriesRes.data.data ?? []).map((d: unknown) => {
        const del = d as { id: string; delivery_number: string | null; delivery_date: string; delivery_status: string; delivery_note_image_url?: string };
        return {
          id: del.id,
          type: "delivery" as const,
          title: `Delivery: ${del.delivery_number || del.id.slice(0, 8)}`,
          subtitle: del.delivery_status,
          date: del.delivery_date,
          status: del.delivery_status,
          photo_url: toAbsUrl(del.delivery_note_image_url || undefined),
        };
      });

      const activity: TimelineEntry[] = ((activityRes as { data: { data: TimelineEntry[] } }).data.data ?? []).map((a) => ({
        ...a,
        // Use backend-provided photo_url first; convert to absolute URL so the
        // browser fetches the file from the API server, not the frontend domain.
        photo_url: toAbsUrl(a.photo_url || (a.subtitle?.startsWith("/uploads/") ? a.subtitle : undefined)),
      }));

      const all = [...deliveries, ...activity].sort((a, b) =>
        new Date(b.date).getTime() - new Date(a.date).getTime()
      );

      setEntries(all);
    } catch {
      setError("Failed to load timeline.");
    } finally {
      setLoading(false);
    }
  }, [projectId, siteId, lotId]);

  useEffect(() => { loadTimeline(); }, [loadTimeline]);

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader title="Timeline" description="Progress history — stage updates, deliveries, and site activity." />

      {/* Selectors */}
      <div className="flex flex-wrap gap-3">
        <select
          value={projectId}
          onChange={e => setProjectId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select
          value={siteId}
          onChange={e => setSiteId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          disabled={sites.length === 0}
        >
          <option value="">— All sites —</option>
          {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select
          value={lotId}
          onChange={e => setLotId(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          disabled={lots.length === 0}
        >
          <option value="">— All lots —</option>
          {lots.map(l => <option key={l.id} value={l.id}>Lot {l.lot_number}</option>)}
        </select>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <div className="space-y-2">{[1,2,3,4,5].map(i => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>
      ) : entries.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">
          No activity recorded yet for this selection.
        </div>
      ) : (
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />

          <div className="space-y-3 pl-14">
            {entries.map((entry, i) => (
              <div key={`${entry.id}-${i}`} className="relative">
                {/* Dot on the line */}
                <div className={`absolute -left-[2.25rem] top-3 w-8 h-8 rounded-full flex items-center justify-center ${entryColor(entry.type, entry.severity)}`}>
                  {entryIcon(entry.type)}
                </div>

                <div className="bg-card border border-border rounded-xl px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-sm truncate">{entry.title}</p>
                      {entry.subtitle && (
                        <p className="text-xs text-muted-foreground mt-0.5 truncate">{entry.subtitle}</p>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">{formatDate(entry.date)}</span>
                  </div>

                  {/* Evidence / delivery note photo — inline thumbnail + full-size link */}
                  {entry.photo_url && (
                    <a
                      href={entry.photo_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 block group"
                      title="Click to open full-size image"
                    >
                      <img
                        src={entry.photo_url}
                        alt="Evidence photo"
                        className="h-24 w-auto rounded-lg border border-border object-cover group-hover:opacity-90 transition-opacity"
                        onError={(e) => {
                          // If image fails to load, fall back to a text link
                          const parent = e.currentTarget.parentElement;
                          if (parent) {
                            e.currentTarget.style.display = "none";
                            const link = document.createElement("span");
                            link.className = "flex items-center gap-1.5 text-xs text-primary hover:underline";
                            link.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"/></svg> View photo`;
                            parent.appendChild(link);
                          }
                        }}
                      />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
