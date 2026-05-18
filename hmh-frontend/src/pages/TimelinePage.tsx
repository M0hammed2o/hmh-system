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
import { Truck, Zap, AlertTriangle, Camera, ChevronDown, ChevronRight, RefreshCw, X as XIcon } from "lucide-react";
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
  record_id?: string;   // DB record UUID for photo replacement
  record_type?: string; // "delivery" | "stage" | "usage"
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
  const [replacingId,  setReplacingId]  = useState<string | null>(null);
  const [replaceError, setReplaceError] = useState("");
  const [lightboxUrl,  setLightboxUrl]  = useState<string | null>(null);

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
          record_id:   del.id,
          record_type: "delivery",
          title: `Delivery: ${del.delivery_number || del.id.slice(0, 8)}`,
          subtitle: del.delivery_status,
          date: del.delivery_date,
          status: del.delivery_status,
          photo_url: toAbsUrl(del.delivery_note_image_url || undefined),
        };
      });

      const activity: TimelineEntry[] = ((activityRes as { data: { data: TimelineEntry[] } }).data.data ?? []).map((a) => ({
        ...a,
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

  const handleReplacePhoto = async (entry: TimelineEntry, file: File) => {
    if (!entry.record_id || !entry.record_type) return;
    setReplacingId(entry.record_id);
    setReplaceError("");
    try {
      const fd = new FormData();
      fd.append("record_type", entry.record_type);
      fd.append("record_id",   entry.record_id);
      fd.append("photo",       file);
      await client.post("/site-dashboard/replace-photo", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await loadTimeline();  // refresh so new photo appears
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || "Failed to replace photo.";
      setReplaceError(msg);
    } finally {
      setReplacingId(null);
    }
  };

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

                  {/* Evidence photo — inline thumbnail + replace button */}
                  <div className="mt-2 flex items-start gap-2 flex-wrap">
                    {entry.photo_url && (
                      <button
                        onClick={() => setLightboxUrl(entry.photo_url!)}
                        className="block group shrink-0 focus:outline-none"
                        title="Click to view full-size image"
                      >
                        <img
                          src={entry.photo_url}
                          alt="Evidence photo"
                          className="h-20 w-auto rounded-lg border border-border object-cover group-hover:opacity-80 transition-opacity cursor-zoom-in"
                          onError={(e) => { e.currentTarget.style.display = "none"; }}
                        />
                      </button>
                    )}

                    {/* Replace photo — only for record types the endpoint supports */}
                    {entry.record_id && entry.type !== "alert" && (
                      <label
                        className={`flex items-center gap-1 text-xs cursor-pointer px-2 py-1 rounded border border-border hover:bg-muted/60 transition-colors mt-0.5 ${
                          replacingId === entry.record_id ? "opacity-50 pointer-events-none" : ""
                        }`}
                        title={entry.photo_url ? "Replace photo" : "Add photo"}
                      >
                        {replacingId === entry.record_id
                          ? <RefreshCw className="w-3 h-3 animate-spin" />
                          : <Camera className="w-3 h-3" />}
                        <span>{entry.photo_url ? "Replace" : "Add photo"}</span>
                        <input
                          type="file"
                          accept="image/*,application/pdf"
                          className="sr-only"
                          disabled={replacingId === entry.record_id}
                          onChange={(e) => {
                            const file = e.target.files?.[0];
                            if (file) handleReplacePhoto(entry, file);
                            e.target.value = "";  // reset so same file can be reselected
                          }}
                        />
                      </label>
                    )}
                  </div>

                  {replaceError && replacingId === null && (
                    <p className="text-xs text-destructive mt-1">{replaceError}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {/* Lightbox */}
      {lightboxUrl && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setLightboxUrl(null)}
        >
          <button
            className="absolute top-4 right-4 text-white/70 hover:text-white p-2 rounded-full bg-black/40"
            onClick={() => setLightboxUrl(null)}
            aria-label="Close"
          >
            <XIcon className="w-6 h-6" />
          </button>
          <img
            src={lightboxUrl}
            alt="Full-size evidence"
            className="max-h-[90vh] max-w-[90vw] rounded-xl shadow-2xl object-contain"
            onClick={(e) => e.stopPropagation()}
          />
          <a
            href={lightboxUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="absolute bottom-4 text-white/70 hover:text-white text-xs underline"
            onClick={(e) => e.stopPropagation()}
          >
            Open original in new tab
          </a>
        </div>
      )}
    </div>
  );
}
