import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, FolderKanban, MapPin, Calendar, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { Modal } from "@/components/shared/Modal";
import { projectsApi, type Project, type ProjectCreate, type ProjectStatus } from "@/api/projects";
import { formatDate } from "@/lib/format";

const statusVariant: Record<ProjectStatus, "success" | "default" | "secondary" | "outline"> = {
  ACTIVE: "success",
  PLANNED: "secondary",
  PAUSED: "outline",
  COMPLETED: "default",
};

const statusLabel: Record<ProjectStatus, string> = {
  ACTIVE: "Active",
  PLANNED: "Planned",
  PAUSED: "Paused",
  COMPLETED: "Completed",
};

// ── Create modal ──────────────────────────────────────────────────────────────

interface CreateProjectModalProps {
  onClose: () => void;
  onCreated: (project: Project) => void;
}

function CreateProjectModal({ onClose, onCreated }: CreateProjectModalProps) {
  const [form, setForm] = useState<ProjectCreate>({
    name: "", code: "", client_name: "", location: "",
    start_date: "", estimated_end_date: "", description: "",
    status: "PLANNED",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const created = await projectsApi.create({
        name: form.name,
        code: form.code,
        client_name: form.client_name || null,
        location: form.location || null,
        start_date: form.start_date || null,
        estimated_end_date: form.estimated_end_date || null,
        description: form.description || null,
        status: form.status,
      });
      onCreated(created);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        "Failed to create project.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title="New Project" onClose={onClose} size="lg">
      <form onSubmit={submit} className="p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Project Name</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              placeholder="e.g. Cosmo City Phase 4"
            />
          </div>
          <div className="space-y-2">
            <Label>Project Code</Label>
            <Input
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              required
              placeholder="e.g. HMH-CCP4"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Client Name</Label>
            <Input
              value={form.client_name ?? ""}
              onChange={(e) => setForm({ ...form, client_name: e.target.value })}
              placeholder="e.g. Housing Development Agency"
            />
          </div>
          <div className="space-y-2">
            <Label>Location</Label>
            <Input
              value={form.location ?? ""}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              placeholder="e.g. Cosmo City, Johannesburg"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Start Date</Label>
            <Input
              type="date"
              value={form.start_date ?? ""}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
              required
            />
          </div>
          <div className="space-y-2">
            <Label>Estimated End Date</Label>
            <Input
              type="date"
              value={form.estimated_end_date ?? ""}
              onChange={(e) => setForm({ ...form, estimated_end_date: e.target.value })}
            />
          </div>
        </div>
        <div className="space-y-2">
          <Label>Status</Label>
          <select
            value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value as ProjectStatus })}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="PLANNED">Planned</option>
            <option value="ACTIVE">Active</option>
            <option value="PAUSED">Paused</option>
            <option value="COMPLETED">Completed</option>
          </select>
        </div>
        <div className="space-y-2">
          <Label>Description</Label>
          <textarea
            value={form.description ?? ""}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={3}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
            placeholder="Brief project description"
          />
        </div>
        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex gap-2 pt-1">
          <Button type="submit" disabled={loading} className="flex-1">
            {loading ? "Creating…" : "Create Project"}
          </Button>
          <Button type="button" variant="outline" onClick={onClose} className="flex-1">
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");

  const fetchProjects = () => {
    setLoading(true);
    projectsApi
      .list(1, 100)
      .then((res) => {
        setProjects(res.items);
        setTotal(res.total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  // Client-side search filter across loaded projects
  const filtered = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.code.toLowerCase().includes(search.toLowerCase()) ||
      (p.client_name ?? "").toLowerCase().includes(search.toLowerCase())
  );

  const activeCount = projects.filter((p) => p.status === "ACTIVE").length;
  const plannedCount = projects.filter((p) => p.status === "PLANNED").length;
  const completedCount = projects.filter((p) => p.status === "COMPLETED").length;

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Projects"
        description="Manage all construction projects, sites, and lots."
        meta={loading ? undefined : `${total} project${total !== 1 ? "s" : ""}`}
        actions={
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="w-4 h-4" />
            New Project
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {loading ? (
          [1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)
        ) : (
          <>
            <StatCard title="Active" value={activeCount} icon={FolderKanban} color="bg-success/10 text-success" />
            <StatCard title="Planned" value={plannedCount} icon={FolderKanban} color="bg-primary/10 text-primary" />
            <StatCard title="Completed" value={completedCount} icon={FolderKanban} color="bg-muted-foreground/10 text-muted-foreground" />
          </>
        )}
      </div>

      <div className="flex items-center gap-3">
        <Input
          placeholder="Search by name, code, or client…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      </div>

      <div className="grid grid-cols-1 gap-3">
        {loading ? (
          [1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)
        ) : filtered.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">
            {search ? "No projects match your search." : "No projects yet. Create the first one."}
          </div>
        ) : (
          filtered.map((project) => (
            <button
              key={project.id}
              onClick={() => navigate(`/projects/${project.id}`)}
              className="bg-card border border-border rounded-xl p-5 text-left hover:border-primary/40 hover:shadow-sm transition-all group"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-4 min-w-0">
                  <div className="flex items-center justify-center w-10 h-10 rounded-lg shrink-0 bg-primary/10 text-primary">
                    <FolderKanban className="w-5 h-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold">{project.name}</p>
                      <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full font-mono">
                        {project.code}
                      </span>
                      <Badge variant={statusVariant[project.status]}>
                        {statusLabel[project.status]}
                      </Badge>
                    </div>
                    {project.description && (
                      <p className="text-sm text-muted-foreground mt-1 line-clamp-1">
                        {project.description}
                      </p>
                    )}
                    <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground flex-wrap">
                      {project.location && (
                        <span className="flex items-center gap-1">
                          <MapPin className="w-3 h-3" />
                          {project.location}
                        </span>
                      )}
                      {project.start_date && (
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {formatDate(project.start_date)}
                          {" — "}
                          {project.estimated_end_date ? formatDate(project.estimated_end_date) : "TBD"}
                        </span>
                      )}
                      {project.client_name && (
                        <span>Client: {project.client_name}</span>
                      )}
                    </div>
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0 mt-1 group-hover:text-primary transition-colors" />
              </div>
            </button>
          ))
        )}
      </div>

      {showCreate && (
        <CreateProjectModal
          onClose={() => setShowCreate(false)}
          onCreated={(project) => {
            setShowCreate(false);
            setProjects((prev) => [project, ...prev]);
            setTotal((t) => t + 1);
          }}
        />
      )}
    </div>
  );
}
