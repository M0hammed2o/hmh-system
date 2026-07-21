import { useCallback, useEffect, useState } from "react";
import { Plus, RefreshCw, GitBranch, Lock } from "lucide-react";
import {
  listActivities, createActivity, updateActivity, setBaseline,
  ProgrammeActivity, ProgrammeActivityCreate,
} from "@/api/programme";
import { projectsApi } from "@/api/projects";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_COLORS: Record<string, string> = {
  NOT_STARTED: "bg-slate-100 text-slate-700",
  IN_PROGRESS: "bg-blue-100 text-blue-700",
  DELAYED:     "bg-orange-100 text-orange-700",
  BLOCKED:     "bg-red-100 text-red-700",
  COMPLETED:   "bg-green-100 text-green-700",
  VERIFIED:    "bg-emerald-100 text-emerald-700",
  CANCELLED:   "bg-slate-200 text-slate-500",
};

const TYPE_COLORS: Record<string, string> = {
  CONSTRUCTION: "bg-blue-50 text-blue-700",
  PROCUREMENT:  "bg-purple-50 text-purple-700",
  INSPECTION:   "bg-yellow-50 text-yellow-700",
  ADMIN:        "bg-slate-50 text-slate-700",
  MILESTONE:    "bg-emerald-50 text-emerald-700",
};

type Project = { id: string; name: string };

export default function ProgrammePlanPage() {
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<ProgrammeActivityCreate>({
    title: "",
    planned_start_date: "",
    planned_finish_date: "",
    activity_type: "CONSTRUCTION",
  });

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [activities, setActivities] = useState<ProgrammeActivity[]>([]);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    projectsApi.list().then((r) => setProjects(r.items)).finally(() => setProjectsLoading(false));
  }, []);

  const fetchActivities = useCallback(() => {
    if (!selectedProject) return;
    setActivitiesLoading(true);
    listActivities(selectedProject).then(setActivities).finally(() => setActivitiesLoading(false));
  }, [selectedProject]);

  useEffect(() => {
    setActivities([]);
    fetchActivities();
  }, [fetchActivities]);

  const handleCreate = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      await createActivity(selectedProject, form);
      fetchActivities();
      setShowCreate(false);
      setForm({ title: "", planned_start_date: "", planned_finish_date: "", activity_type: "CONSTRUCTION" });
    } catch (e: any) {
      setCreateError(e?.response?.data?.detail || "Failed to create activity.");
    } finally {
      setCreating(false);
    }
  };

  const handleSetBaseline = async (id: string) => {
    try {
      await setBaseline(id);
      fetchActivities();
    } catch {
      // ignore
    }
  };

  const handleProgressUpdate = async (id: string, progress_pct: number) => {
    try {
      const updated = await updateActivity(id, { progress_pct });
      setActivities((prev) => prev.map((a) => a.id === id ? { ...a, ...updated } : a));
    } catch {
      // ignore
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Programme Plan</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Gantt-style activity planning with baseline tracking and progress propagation.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchActivities}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          {selectedProject && (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="w-4 h-4 mr-1" /> New Activity
            </Button>
          )}
        </div>
      </div>

      {/* Project picker */}
      <div className="mb-6">
        <Label className="text-sm font-medium mb-2 block">Select Project</Label>
        {projectsLoading ? (
          <Skeleton className="h-9 w-64" />
        ) : (
          <select
            className="border rounded-md px-3 py-2 text-sm bg-background w-64"
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
          >
            <option value="">— choose a project —</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        )}
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40">
          <div className="bg-background rounded-xl shadow-xl p-6 w-full max-w-lg mx-4">
            <h2 className="text-lg font-semibold mb-4">New Programme Activity</h2>
            <div className="space-y-4">
              <div>
                <Label>Title *</Label>
                <Input
                  placeholder="e.g. Excavation and Platforms — Site A"
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                />
              </div>
              <div>
                <Label>Activity Type</Label>
                <select
                  className="border rounded-md px-3 py-2 text-sm bg-background w-full"
                  value={form.activity_type}
                  onChange={(e) => setForm((f) => ({ ...f, activity_type: e.target.value as any }))}
                >
                  {["CONSTRUCTION","PROCUREMENT","INSPECTION","ADMIN","MILESTONE"].map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Planned Start *</Label>
                  <Input
                    type="date"
                    value={form.planned_start_date}
                    onChange={(e) => setForm((f) => ({ ...f, planned_start_date: e.target.value }))}
                  />
                </div>
                <div>
                  <Label>Planned Finish *</Label>
                  <Input
                    type="date"
                    value={form.planned_finish_date}
                    onChange={(e) => setForm((f) => ({ ...f, planned_finish_date: e.target.value }))}
                  />
                </div>
              </div>
              <div>
                <Label>Responsible Team</Label>
                <Input
                  placeholder="e.g. Site Team A"
                  value={form.responsible_team || ""}
                  onChange={(e) => setForm((f) => ({ ...f, responsible_team: e.target.value }))}
                />
              </div>
            </div>
            {createError && <p className="text-destructive text-sm mt-3">{createError}</p>}
            <div className="flex justify-end gap-2 mt-5">
              <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button
                onClick={handleCreate}
                disabled={!form.title || !form.planned_start_date || !form.planned_finish_date || creating}
              >
                {creating ? "Creating..." : "Create Activity"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Activities */}
      {!selectedProject ? (
        <div className="text-center text-muted-foreground py-20">Select a project to view its programme.</div>
      ) : activitiesLoading ? (
        <div className="space-y-3">{[1,2,3].map((i) => <Skeleton key={i} className="h-20 w-full" />)}</div>
      ) : activities.length === 0 ? (
        <div className="text-center text-muted-foreground py-20">
          <GitBranch className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No programme activities yet. Add the first one to start planning.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {activities.map((activity) => (
            <ActivityRow
              key={activity.id}
              activity={activity}
              onSetBaseline={() => handleSetBaseline(activity.id)}
              onProgressUpdate={(pct) => handleProgressUpdate(activity.id, pct)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ActivityRow({
  activity,
  onSetBaseline,
  onProgressUpdate,
}: {
  activity: ProgrammeActivity;
  onSetBaseline: () => void;
  onProgressUpdate: (pct: number) => void;
}) {
  const daysLeft = activity.actual_finish_date
    ? null
    : Math.ceil((new Date(activity.planned_finish_date).getTime() - Date.now()) / 86400000);

  return (
    <div className="bg-card border rounded-xl p-4">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="font-semibold text-sm">{activity.activity_number}</span>
            <Badge className={STATUS_COLORS[activity.status] || ""}>{activity.status.replace(/_/g, " ")}</Badge>
            <Badge className={`text-[10px] ${TYPE_COLORS[activity.activity_type] || ""}`}>{activity.activity_type}</Badge>
            {activity.is_milestone && <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">MILESTONE</Badge>}
            {activity.is_critical_path && <Badge className="bg-red-100 text-red-700 text-[10px]">CRITICAL PATH</Badge>}
          </div>
          <p className="text-sm font-medium">{activity.title}</p>
          <div className="flex gap-4 mt-1.5 text-xs text-muted-foreground flex-wrap">
            <span>Plan: {activity.planned_start_date} → {activity.planned_finish_date}</span>
            {activity.baseline_start_date && (
              <span className="text-slate-400">Baseline: {activity.baseline_start_date} → {activity.baseline_finish_date}</span>
            )}
            {activity.responsible_team && <span>Team: {activity.responsible_team}</span>}
            {daysLeft !== null && (
              <span className={daysLeft < 0 ? "text-destructive font-medium" : daysLeft < 7 ? "text-orange-600" : ""}>
                {daysLeft < 0 ? `${Math.abs(daysLeft)}d overdue` : `${daysLeft}d remaining`}
              </span>
            )}
          </div>

          {/* Progress bar */}
          <div className="mt-2 flex items-center gap-3">
            <div className="flex-1 bg-muted rounded-full h-2">
              <div
                className="bg-primary h-2 rounded-full transition-all"
                style={{ width: `${activity.progress_pct}%` }}
              />
            </div>
            <span className="text-xs font-medium w-10 text-right">{activity.progress_pct}%</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-1 shrink-0">
          {!activity.baseline_start_date && activity.status === "NOT_STARTED" && (
            <Button variant="outline" size="sm" onClick={onSetBaseline} title="Freeze current planned dates as baseline">
              <Lock className="w-3.5 h-3.5 mr-1" /> Baseline
            </Button>
          )}
          {activity.status === "IN_PROGRESS" && (
            <select
              className="border rounded text-xs px-2 py-1"
              value={activity.progress_pct}
              onChange={(e) => onProgressUpdate(parseInt(e.target.value))}
            >
              {[0,10,20,25,30,40,50,60,70,75,80,90,95,100].map((v) => (
                <option key={v} value={v}>{v}%</option>
              ))}
            </select>
          )}
        </div>
      </div>
    </div>
  );
}
