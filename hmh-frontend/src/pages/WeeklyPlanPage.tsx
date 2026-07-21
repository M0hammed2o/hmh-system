import { useCallback, useEffect, useState } from "react";
import { Plus, RefreshCw, Calendar, CheckSquare } from "lucide-react";
import {
  listWeeklyPlans, getWeeklyPlan, createWeeklyPlan, submitWeeklyPlan, approveWeeklyPlan,
  markItemDone, addPlanItem,
  WeeklyPlan, WeeklyPlanItem,
} from "@/api/weeklyPlans";
import { projectsApi } from "@/api/projects";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_COLORS: Record<string, string> = {
  DRAFT:       "bg-slate-100 text-slate-700",
  SUBMITTED:   "bg-blue-100 text-blue-700",
  APPROVED:    "bg-green-100 text-green-700",
  IN_PROGRESS: "bg-yellow-100 text-yellow-700",
  COMPLETED:   "bg-emerald-100 text-emerald-700",
  REVIEWED:    "bg-purple-100 text-purple-700",
  CANCELLED:   "bg-red-100 text-red-700",
};

function getMonday(d: Date): string {
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  const monday = new Date(new Date(d).setDate(diff));
  return monday.toISOString().split("T")[0];
}

type Project = { id: string; name: string };

export default function WeeklyPlanPage() {
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newWeekStart, setNewWeekStart] = useState(getMonday(new Date()));
  const [newItemDesc, setNewItemDesc] = useState("");
  const [newItemPct, setNewItemPct] = useState(0);

  const [projects, setProjects] = useState<Project[]>([]);
  const [plans, setPlans] = useState<WeeklyPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [approving, setApproving] = useState(false);
  const [addingItem, setAddingItem] = useState(false);

  useEffect(() => {
    projectsApi.list().then((r) => setProjects(r.items));
  }, []);

  const fetchPlans = useCallback(() => {
    if (!selectedProject) return;
    setPlansLoading(true);
    listWeeklyPlans(selectedProject).then(setPlans).finally(() => setPlansLoading(false));
  }, [selectedProject]);

  useEffect(() => {
    setPlans([]);
    setSelectedPlanId(null);
    fetchPlans();
  }, [fetchPlans]);

  const currentPlan = plans.find((p) => p.id === selectedPlanId) ?? null;

  const handleCreate = async () => {
    setCreating(true);
    try {
      const plan = await createWeeklyPlan(selectedProject, { week_start_date: newWeekStart });
      await fetchPlans();
      setShowCreate(false);
      setSelectedPlanId(plan.id);
    } finally {
      setCreating(false);
    }
  };

  const handleSubmit = async () => {
    if (!currentPlan) return;
    setSubmitting(true);
    try {
      const updated = await submitWeeklyPlan(currentPlan.id);
      setPlans((prev) => prev.map((p) => p.id === updated.id ? updated : p));
    } finally {
      setSubmitting(false);
    }
  };

  const handleApprove = async () => {
    if (!currentPlan) return;
    setApproving(true);
    try {
      const updated = await approveWeeklyPlan(currentPlan.id);
      setPlans((prev) => prev.map((p) => p.id === updated.id ? updated : p));
    } finally {
      setApproving(false);
    }
  };

  const refreshPlan = async (planId: string) => {
    const updated = await getWeeklyPlan(planId);
    setPlans((prev) => prev.map((p) => p.id === updated.id ? updated : p));
  };

  const handleMarkDone = async (itemId: string, pct: number) => {
    if (!currentPlan) return;
    try {
      await markItemDone(currentPlan.id, itemId, pct);
      await refreshPlan(currentPlan.id);
    } catch {
      // ignore
    }
  };

  const handleAddItem = async () => {
    if (!currentPlan || !newItemDesc.trim()) return;
    setAddingItem(true);
    try {
      await addPlanItem(currentPlan.id, { description: newItemDesc, planned_progress_pct: newItemPct });
      await refreshPlan(currentPlan.id);
      setNewItemDesc("");
      setNewItemPct(0);
    } finally {
      setAddingItem(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Weekly Work Plans</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Operational week-by-week task planning linked to the programme.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchPlans}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          {selectedProject && (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="w-4 h-4 mr-1" /> New Plan
            </Button>
          )}
        </div>
      </div>

      {/* Project picker */}
      <div className="mb-6">
        <Label className="text-sm font-medium mb-2 block">Select Project</Label>
        <select
          className="border rounded-md px-3 py-2 text-sm bg-background w-64"
          value={selectedProject}
          onChange={(e) => { setSelectedProject(e.target.value); setSelectedPlanId(null); }}
        >
          <option value="">— choose a project —</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40">
          <div className="bg-background rounded-xl shadow-xl p-6 w-full max-w-md mx-4">
            <h2 className="text-lg font-semibold mb-4">New Weekly Plan</h2>
            <div>
              <Label>Week Starting (Monday) *</Label>
              <Input
                type="date"
                value={newWeekStart}
                onChange={(e) => setNewWeekStart(e.target.value)}
              />
              <p className="text-xs text-muted-foreground mt-1">Will be adjusted to the nearest Monday.</p>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button onClick={handleCreate} disabled={creating}>
                {creating ? "Creating..." : "Create Plan"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Two-column layout */}
      {!selectedProject ? (
        <div className="text-center text-muted-foreground py-20">Select a project to view weekly plans.</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Plan list */}
          <div className="space-y-2">
            {plansLoading ? (
              [1,2,3].map((i) => <Skeleton key={i} className="h-16 w-full" />)
            ) : plans.length === 0 ? (
              <div className="text-center text-muted-foreground py-10">
                <Calendar className="w-10 h-10 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No plans yet.</p>
              </div>
            ) : (
              plans.map((plan) => (
                <div
                  key={plan.id}
                  className={`bg-card border rounded-lg p-3 cursor-pointer transition-all ${
                    selectedPlanId === plan.id ? "border-primary shadow-sm" : "hover:border-primary/40"
                  }`}
                  onClick={() => setSelectedPlanId(plan.id)}
                >
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-medium">{plan.plan_number}</span>
                    <Badge className={`text-[10px] ${STATUS_COLORS[plan.status] || ""}`}>{plan.status}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {plan.week_start_date} → {plan.week_end_date}
                  </p>
                  <p className="text-xs text-muted-foreground">{plan.items.length} items</p>
                </div>
              ))
            )}
          </div>

          {/* Plan detail */}
          <div className="lg:col-span-2">
            {!currentPlan ? (
              <div className="text-center text-muted-foreground py-20 bg-muted/20 rounded-xl">
                Select a plan to view its items.
              </div>
            ) : (
              <PlanDetail
                plan={currentPlan}
                submitting={submitting}
                approving={approving}
                addingItem={addingItem}
                onSubmit={handleSubmit}
                onApprove={handleApprove}
                onMarkDone={handleMarkDone}
                newItemDesc={newItemDesc}
                setNewItemDesc={setNewItemDesc}
                newItemPct={newItemPct}
                setNewItemPct={setNewItemPct}
                onAddItem={handleAddItem}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function PlanDetail({
  plan, submitting, approving, addingItem,
  onSubmit, onApprove, onMarkDone,
  newItemDesc, setNewItemDesc, newItemPct, setNewItemPct, onAddItem,
}: {
  plan: WeeklyPlan;
  submitting: boolean;
  approving: boolean;
  addingItem: boolean;
  onSubmit: () => void;
  onApprove: () => void;
  onMarkDone: (itemId: string, pct: number) => void;
  newItemDesc: string;
  setNewItemDesc: (v: string) => void;
  newItemPct: number;
  setNewItemPct: (v: number) => void;
  onAddItem: () => void;
}) {
  const canEdit = ["DRAFT", "APPROVED", "IN_PROGRESS"].includes(plan.status);
  const completedItems = plan.items.filter((i) => i.actual_progress_pct != null).length;

  return (
    <div className="bg-card border rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b bg-muted/30 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm">{plan.plan_number}</span>
            <Badge className={STATUS_COLORS[plan.status] || ""}>{plan.status}</Badge>
          </div>
          <p className="text-xs text-muted-foreground">{plan.week_start_date} → {plan.week_end_date}</p>
        </div>
        <div className="flex gap-2">
          {plan.status === "DRAFT" && (
            <Button size="sm" variant="outline" onClick={onSubmit} disabled={submitting}>
              {submitting ? "Submitting..." : "Submit for Approval"}
            </Button>
          )}
          {plan.status === "SUBMITTED" && (
            <Button size="sm" onClick={onApprove} disabled={approving}>
              <CheckSquare className="w-4 h-4 mr-1" />
              {approving ? "Approving..." : "Approve"}
            </Button>
          )}
        </div>
      </div>

      <div className="px-4 py-2 bg-muted/10 text-xs text-muted-foreground border-b">
        {completedItems} / {plan.items.length} items marked done
      </div>

      <div className="divide-y">
        {plan.items.map((item, idx) => (
          <PlanItemRow key={item.id} item={item} index={idx + 1} onMarkDone={onMarkDone} />
        ))}
        {plan.items.length === 0 && (
          <div className="py-8 text-center text-sm text-muted-foreground">No items yet.</div>
        )}
      </div>

      {canEdit && (
        <div className="px-4 py-3 border-t bg-muted/10 flex gap-2">
          <Input
            className="flex-1 text-sm"
            placeholder="Add a task..."
            value={newItemDesc}
            onChange={(e) => setNewItemDesc(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && newItemDesc.trim() && onAddItem()}
          />
          <select
            className="border rounded-md px-2 py-1 text-sm bg-background"
            value={newItemPct}
            onChange={(e) => setNewItemPct(parseInt(e.target.value))}
          >
            {[0,25,50,75,100].map((v) => <option key={v} value={v}>{v}%</option>)}
          </select>
          <Button size="sm" onClick={onAddItem} disabled={!newItemDesc.trim() || addingItem}>
            <Plus className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

function PlanItemRow({
  item, index, onMarkDone,
}: {
  item: WeeklyPlanItem;
  index: number;
  onMarkDone: (itemId: string, pct: number) => void;
}) {
  const isDone = item.actual_progress_pct != null;

  return (
    <div className={`flex items-center gap-3 px-4 py-3 ${isDone ? "opacity-60" : ""}`}>
      <span className="text-xs text-muted-foreground w-5 shrink-0">{index}</span>
      <div className="flex-1 min-w-0">
        <p className={`text-sm ${isDone ? "line-through" : ""}`}>{item.description}</p>
        <div className="flex gap-3 mt-0.5 text-xs text-muted-foreground">
          <span>Plan: {item.planned_progress_pct}%</span>
          {item.actual_progress_pct != null && (
            <span className="text-green-600 font-medium">Done: {item.actual_progress_pct}%</span>
          )}
          {item.carry_forward && <span className="text-orange-500">↩ Carried forward</span>}
        </div>
      </div>
      {!isDone && (
        <select
          className="border rounded text-xs px-2 py-1 bg-background"
          defaultValue=""
          onChange={(e) => e.target.value && onMarkDone(item.id, parseInt(e.target.value))}
        >
          <option value="">Mark done…</option>
          {[25,50,75,100].map((v) => <option key={v} value={v}>{v}%</option>)}
        </select>
      )}
    </div>
  );
}
