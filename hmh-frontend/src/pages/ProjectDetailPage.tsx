import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, Plus, MapPin, Calendar, Building2, Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/shared/PageHeader";
import { Tabs } from "@/components/shared/Tabs";
import { Modal } from "@/components/shared/Modal";
import { cn } from "@/lib/utils";
import { projectsApi, type Project, type ProjectUpdate, type ProjectStatus } from "@/api/projects";
import { sitesApi, type Site, type SiteCreate } from "@/api/sites";
import { lotsApi, type Lot, type LotCreate, type LotStatus } from "@/api/lots";
import { stagesApi, type ProjectStageStatus, type StageMaster, type StageStatus } from "@/api/stages";
import { formatDate } from "@/lib/format";

// ── Status display maps ───────────────────────────────────────────────────────

const lotStatusVariant: Record<LotStatus, "success" | "default" | "secondary" | "outline"> = {
  AVAILABLE: "secondary",
  IN_PROGRESS: "default",
  COMPLETED: "success",
  ON_HOLD: "outline",
};

const lotStatusLabel: Record<LotStatus, string> = {
  AVAILABLE: "Available",
  IN_PROGRESS: "In Progress",
  COMPLETED: "Completed",
  ON_HOLD: "On Hold",
};

const stageStatusColor: Record<StageStatus, string> = {
  NOT_STARTED: "bg-muted text-muted-foreground",
  IN_PROGRESS: "bg-primary/10 text-primary",
  AWAITING_INSPECTION: "bg-warning/10 text-warning",
  CERTIFIED: "bg-success/10 text-success",
  COMPLETED: "bg-success/10 text-success",
};

const stageStatusLabel: Record<StageStatus, string> = {
  NOT_STARTED: "Not Started",
  IN_PROGRESS: "In Progress",
  AWAITING_INSPECTION: "Awaiting Inspection",
  CERTIFIED: "Certified",
  COMPLETED: "Completed",
};

const projectStatusVariant: Record<ProjectStatus, "success" | "default" | "secondary" | "outline"> = {
  ACTIVE: "success",
  PLANNED: "secondary",
  PAUSED: "outline",
  COMPLETED: "default",
};

const projectStatusLabel: Record<ProjectStatus, string> = {
  ACTIVE: "Active",
  PLANNED: "Planned",
  PAUSED: "Paused",
  COMPLETED: "Completed",
};

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "sites",    label: "Sites" },
  { key: "lots",     label: "Lots" },
  { key: "stages",   label: "Stages" },
];

// ── Edit Project modal ────────────────────────────────────────────────────────

function EditProjectModal({
  project,
  onClose,
  onUpdated,
}: {
  project: Project;
  onClose: () => void;
  onUpdated: (p: Project) => void;
}) {
  const [form, setForm] = useState<ProjectUpdate>({
    name: project.name,
    code: project.code,
    client_name: project.client_name ?? "",
    location: project.location ?? "",
    start_date: project.start_date ?? "",
    estimated_end_date: project.estimated_end_date ?? "",
    description: project.description ?? "",
    status: project.status,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const updated = await projectsApi.update(project.id, {
        name: form.name,
        code: form.code,
        client_name: (form.client_name as string) || null,
        location: (form.location as string) || null,
        start_date: (form.start_date as string) || null,
        estimated_end_date: (form.estimated_end_date as string) || null,
        description: (form.description as string) || null,
        status: form.status,
      });
      onUpdated(updated);
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
          "Failed to update project."
      );
    } finally {
      setLoading(false);
    }
  };

  const field = (label: string, key: keyof ProjectUpdate, opts?: { type?: string; mono?: boolean }) => (
    <div className="space-y-2">
      <Label>{label}</Label>
      <input
        type={opts?.type ?? "text"}
        className={cn(
          "h-10 w-full rounded-md border border-input bg-background px-3 text-sm",
          opts?.mono && "font-mono"
        )}
        value={(form[key] as string) ?? ""}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        required={key === "name" || key === "code"}
      />
    </div>
  );

  return (
    <Modal open title="Edit Project" onClose={onClose} size="lg">
      <form onSubmit={submit} className="p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          {field("Project Name", "name")}
          {field("Project Code", "code", { mono: true })}
        </div>
        <div className="grid grid-cols-2 gap-4">
          {field("Client Name", "client_name")}
          {field("Location", "location")}
        </div>
        <div className="grid grid-cols-2 gap-4">
          {field("Start Date", "start_date", { type: "date" })}
          {field("Estimated End Date", "estimated_end_date", { type: "date" })}
        </div>
        <div className="space-y-2">
          <Label>Status</Label>
          <select
            value={form.status ?? "PLANNED"}
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
            value={(form.description as string) ?? ""}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={3}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
          />
        </div>
        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex gap-2 pt-1">
          <Button type="submit" disabled={loading} className="flex-1">
            {loading ? "Saving…" : "Save Changes"}
          </Button>
          <Button type="button" variant="outline" onClick={onClose} className="flex-1">
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Add Site modal ────────────────────────────────────────────────────────────

function AddSiteModal({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: string;
  onClose: () => void;
  onCreated: (site: Site) => void;
}) {
  const [form, setForm] = useState<SiteCreate>({
    name: "",
    code: "",
    site_type: "construction_site",
    location_description: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const created = await sitesApi.create(projectId, {
        name: form.name,
        code: form.code || null,
        site_type: form.site_type || "construction_site",
        location_description: form.location_description || null,
      });
      onCreated(created);
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
          "Failed to create site."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title="Add Site" onClose={onClose} size="md">
      <form onSubmit={submit} className="p-6 space-y-4">
        <div className="space-y-2">
          <Label>Site Name <span className="text-destructive">*</span></Label>
          <Input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
            placeholder="e.g. Site A — Block 1–40"
          />
        </div>
        <div className="space-y-2">
          <Label>Site Code <span className="text-muted-foreground text-xs">(optional)</span></Label>
          <Input
            value={form.code ?? ""}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            placeholder="e.g. CCP3-A"
            className="font-mono"
          />
        </div>
        <div className="space-y-2">
          <Label>Site Type</Label>
          <select
            value={form.site_type ?? "construction_site"}
            onChange={(e) => setForm({ ...form, site_type: e.target.value })}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="construction_site">Construction Site</option>
            <option value="Residential">Residential</option>
            <option value="Commercial">Commercial</option>
            <option value="Industrial">Industrial</option>
            <option value="Mixed Use">Mixed Use</option>
          </select>
        </div>
        <div className="space-y-2">
          <Label>Location Description</Label>
          <Input
            value={form.location_description ?? ""}
            onChange={(e) => setForm({ ...form, location_description: e.target.value })}
            placeholder="e.g. Northern section, Cosmo City"
          />
        </div>
        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex gap-2 pt-1">
          <Button type="submit" disabled={loading} className="flex-1">
            {loading ? "Creating…" : "Create Site"}
          </Button>
          <Button type="button" variant="outline" onClick={onClose} className="flex-1">
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Edit Site modal ───────────────────────────────────────────────────────────

function EditSiteModal({
  site,
  onClose,
  onUpdated,
}: {
  site: Site;
  onClose: () => void;
  onUpdated: (site: Site) => void;
}) {
  const [form, setForm] = useState({
    name: site.name,
    code: site.code ?? "",
    site_type: site.site_type,
    location_description: site.location_description ?? "",
    is_active: site.is_active,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const updated = await sitesApi.update(site.id, {
        name: form.name,
        code: form.code || null,
        site_type: form.site_type,
        location_description: form.location_description || null,
        is_active: form.is_active,
      });
      onUpdated(updated);
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
          "Failed to update site."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title="Edit Site" onClose={onClose} size="md">
      <form onSubmit={submit} className="p-6 space-y-4">
        <div className="space-y-2">
          <Label>Site Name <span className="text-destructive">*</span></Label>
          <Input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </div>
        <div className="space-y-2">
          <Label>Site Code</Label>
          <Input
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            className="font-mono"
          />
        </div>
        <div className="space-y-2">
          <Label>Site Type</Label>
          <select
            value={form.site_type}
            onChange={(e) => setForm({ ...form, site_type: e.target.value })}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="construction_site">Construction Site</option>
            <option value="Residential">Residential</option>
            <option value="Commercial">Commercial</option>
            <option value="Industrial">Industrial</option>
            <option value="Mixed Use">Mixed Use</option>
          </select>
        </div>
        <div className="space-y-2">
          <Label>Location Description</Label>
          <Input
            value={form.location_description}
            onChange={(e) => setForm({ ...form, location_description: e.target.value })}
          />
        </div>
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="is_active"
            checked={form.is_active}
            onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            className="w-4 h-4 rounded border-input"
          />
          <Label htmlFor="is_active" className="cursor-pointer">Site is active</Label>
        </div>
        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex gap-2 pt-1">
          <Button type="submit" disabled={loading} className="flex-1">
            {loading ? "Saving…" : "Save Changes"}
          </Button>
          <Button type="button" variant="outline" onClick={onClose} className="flex-1">
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Add Lot modal ─────────────────────────────────────────────────────────────

function AddLotModal({
  projectId,
  sites,
  onClose,
  onCreated,
}: {
  projectId: string;
  sites: Site[];
  onClose: () => void;
  onCreated: (lot: Lot) => void;
}) {
  const [form, setForm] = useState<LotCreate>({
    lot_number: "",
    unit_type: "",
    block_number: "",
    status: "AVAILABLE",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const created = await lotsApi.create(projectId, {
        lot_number: form.lot_number,
        site_id: form.site_id || null,
        unit_type: form.unit_type || null,
        block_number: form.block_number || null,
        status: form.status,
      });
      onCreated(created);
    } catch (err: unknown) {
      setError(
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ||
          "Failed to create lot."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title="Add Lot" onClose={onClose} size="md">
      <form onSubmit={submit} className="p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Lot Number <span className="text-destructive">*</span></Label>
            <Input
              value={form.lot_number}
              onChange={(e) => setForm({ ...form, lot_number: e.target.value })}
              required
              placeholder="e.g. 001"
            />
          </div>
          <div className="space-y-2">
            <Label>Block Number</Label>
            <Input
              value={form.block_number ?? ""}
              onChange={(e) => setForm({ ...form, block_number: e.target.value })}
              placeholder="e.g. A"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Unit Type</Label>
            <Input
              value={form.unit_type ?? ""}
              onChange={(e) => setForm({ ...form, unit_type: e.target.value })}
              placeholder="e.g. 3-Bedroom"
            />
          </div>
          <div className="space-y-2">
            <Label>Site</Label>
            <select
              value={form.site_id ?? ""}
              onChange={(e) => setForm({ ...form, site_id: e.target.value || undefined })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— No site —</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="space-y-2">
          <Label>Status</Label>
          <select
            value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value as LotStatus })}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="AVAILABLE">Available</option>
            <option value="IN_PROGRESS">In Progress</option>
            <option value="COMPLETED">Completed</option>
            <option value="ON_HOLD">On Hold</option>
          </select>
        </div>
        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex gap-2 pt-1">
          <Button type="submit" disabled={loading} className="flex-1">
            {loading ? "Creating…" : "Create Lot"}
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

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [tab, setTab] = useState("overview");

  // Project state — real
  const [project, setProject] = useState<Project | null>(null);
  const [projectLoading, setProjectLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [showEditProject, setShowEditProject] = useState(false);

  // Sites state — real
  const [sites, setSites] = useState<Site[]>([]);
  const [sitesLoading, setSitesLoading] = useState(false);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [showAddSite, setShowAddSite] = useState(false);
  const [editingSite, setEditingSite] = useState<Site | null>(null);

  // Lots state — real
  const [lots, setLots] = useState<Lot[]>([]);
  const [lotsLoading, setLotsLoading] = useState(false);
  const [showAddLot, setShowAddLot] = useState(false);

  // Stages state — real
  const [stageMasters, setStageMasters] = useState<StageMaster[]>([]);
  const [stageStatuses, setStageStatuses] = useState<ProjectStageStatus[]>([]);
  const [stagesLoading, setStagesLoading] = useState(false);

  // ── Load project ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!projectId) return;
    setProjectLoading(true);
    projectsApi
      .get(projectId)
      .then(setProject)
      .catch((err) => {
        if (err?.response?.status === 404) setNotFound(true);
      })
      .finally(() => setProjectLoading(false));
  }, [projectId]);

  // ── Load sites when Sites tab is active ────────────────────────────────────
  useEffect(() => {
    if (tab !== "sites" || !projectId) return;
    setSitesLoading(true);
    sitesApi
      .list(projectId, includeInactive)
      .then(setSites)
      .catch(() => setSites([]))
      .finally(() => setSitesLoading(false));
  }, [tab, projectId, includeInactive]);

  // ── Load lots when Lots tab is active ───────────────────────────────────────
  useEffect(() => {
    if (tab !== "lots" || !projectId) return;
    setLotsLoading(true);
    lotsApi
      .list(projectId)
      .then(setLots)
      .catch(() => setLots([]))
      .finally(() => setLotsLoading(false));
  }, [tab, projectId]);

  // ── Load stages when Stages tab is active ───────────────────────────────────
  useEffect(() => {
    if (tab !== "stages" || !projectId) return;
    setStagesLoading(true);
    Promise.all([
      stagesApi.listMasters(),
      stagesApi.listProjectStatuses(projectId),
    ])
      .then(([masters, statuses]) => {
        setStageMasters(masters);
        setStageStatuses(statuses);
      })
      .catch(() => {})
      .finally(() => setStagesLoading(false));
  }, [tab, projectId]);

  // ── Render guards ───────────────────────────────────────────────────────────
  if (projectLoading) {
    return (
      <div className="space-y-5 animate-fade-in">
        <Skeleton className="h-5 w-28 rounded" />
        <Skeleton className="h-9 w-72 rounded" />
        <div className="flex gap-1">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-9 w-24 rounded-lg" />)}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-44 rounded-xl" />)}
        </div>
      </div>
    );
  }

  if (notFound || !project) {
    return (
      <div className="text-center py-16 text-muted-foreground text-sm">
        Project not found.{" "}
        <button onClick={() => navigate("/projects")} className="text-primary underline">
          Go back
        </button>
      </div>
    );
  }

  const tabsWithCount = TABS.map((t) => {
    if (t.key === "sites") return { ...t, count: sites.length };
    if (t.key === "lots") return { ...t, count: lots.length || undefined };
    return t;
  });

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Back + header */}
      <div>
        <button
          onClick={() => navigate("/projects")}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-3 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Projects
        </button>
        <PageHeader
          title={project.name}
          description={project.description ?? undefined}
          meta={project.code}
          actions={
            <div className="flex items-center gap-2">
              <Badge variant={projectStatusVariant[project.status]}>
                {projectStatusLabel[project.status]}
              </Badge>
              <Button size="sm" variant="outline" onClick={() => setShowEditProject(true)}>
                <Pencil className="w-3.5 h-3.5" />
                Edit
              </Button>
            </div>
          }
        />
      </div>

      <Tabs tabs={tabsWithCount} active={tab} onChange={setTab} />

      {/* ── OVERVIEW (real project data) ───────────────────────────────────── */}
      {tab === "overview" && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Project details card — real */}
          <div className="bg-card border border-border rounded-xl p-5 space-y-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Project Details
            </p>
            <div className="space-y-2 text-sm">
              {project.location && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <MapPin className="w-4 h-4 shrink-0" />
                  <span>{project.location}</span>
                </div>
              )}
              {project.client_name && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Building2 className="w-4 h-4 shrink-0" />
                  <span>{project.client_name}</span>
                </div>
              )}
              {project.start_date && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Calendar className="w-4 h-4 shrink-0" />
                  <span>Started {formatDate(project.start_date)}</span>
                </div>
              )}
              {project.estimated_end_date && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Calendar className="w-4 h-4 shrink-0" />
                  <span>Est. completion {formatDate(project.estimated_end_date)}</span>
                </div>
              )}
              {!project.location && !project.client_name && !project.start_date && (
                <p className="text-muted-foreground text-xs italic">No additional details recorded.</p>
              )}
            </div>
          </div>

          {/* Progress Summary — MOCK: replace when Lots API is built */}
          <div className="bg-card border border-border rounded-xl p-5 space-y-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Progress Summary
              <span className="ml-1.5 text-xs font-normal normal-case text-warning bg-warning/10 px-1.5 py-0.5 rounded">
                pending lots API
              </span>
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="text-center p-3 bg-muted/50 rounded-lg">
                <p className="text-2xl font-bold">{sites.length}</p>
                <p className="text-xs text-muted-foreground mt-0.5">Sites</p>
              </div>
              <div className="text-center p-3 bg-muted/50 rounded-lg">
                <p className="text-2xl font-bold text-muted-foreground">—</p>
                <p className="text-xs text-muted-foreground mt-0.5">Lots</p>
              </div>
              <div className="text-center p-3 bg-success/10 rounded-lg">
                <p className="text-2xl font-bold text-success">—</p>
                <p className="text-xs text-muted-foreground mt-0.5">Completed</p>
              </div>
              <div className="text-center p-3 bg-primary/10 rounded-lg">
                <p className="text-2xl font-bold text-primary">—</p>
                <p className="text-xs text-muted-foreground mt-0.5">In Progress</p>
              </div>
            </div>
          </div>

          {/* Stage Certifications — MOCK: replace when Stages API is built */}
          <div className="bg-card border border-border rounded-xl p-5 space-y-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Stage Certifications
              <span className="ml-1.5 text-xs font-normal normal-case text-warning bg-warning/10 px-1.5 py-0.5 rounded">
                pending stages API
              </span>
            </p>
            <div className="space-y-2">
              {(["CERTIFIED", "AWAITING_INSPECTION", "IN_PROGRESS", "NOT_STARTED"] as StageStatus[]).map((s) => (
                <div key={s} className="flex items-center justify-between text-sm">
                  <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", stageStatusColor[s])}>
                    {stageStatusLabel[s]}
                  </span>
                  <span className="font-semibold text-muted-foreground">—</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── SITES (real data) ──────────────────────────────────────────────── */}
      {tab === "sites" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(e) => setIncludeInactive(e.target.checked)}
                className="rounded border-input w-4 h-4"
              />
              Show inactive sites
            </label>
            <Button size="sm" onClick={() => setShowAddSite(true)}>
              <Plus className="w-4 h-4" />
              Add Site
            </Button>
          </div>

          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {sitesLoading ? (
              <div className="p-4 space-y-3">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 rounded-lg" />)}
              </div>
            ) : sites.length === 0 ? (
              <div className="p-12 text-center">
                <p className="text-sm font-medium mb-1">No sites yet</p>
                <p className="text-xs text-muted-foreground mb-4">
                  Add the first site for this project.
                </p>
                <Button size="sm" variant="outline" onClick={() => setShowAddSite(true)}>
                  <Plus className="w-4 h-4" />
                  Add Site
                </Button>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Name</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Code</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Type</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Location</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {sites.map((site) => (
                    <tr
                      key={site.id}
                      className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3 font-medium">{site.name}</td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                        {site.code ?? <span className="italic text-muted-foreground/60">—</span>}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-sm">{site.site_type}</td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">
                        {site.location_description ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={site.is_active ? "success" : "outline"}>
                          {site.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => setEditingSite(site)}
                          className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                          title="Edit site"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── LOTS (real data) ──────────────────────────────────────────────── */}
      {tab === "lots" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {lots.length} lot{lots.length !== 1 ? "s" : ""} in this project
            </p>
            <Button size="sm" onClick={() => setShowAddLot(true)}>
              <Plus className="w-4 h-4" />
              Add Lot
            </Button>
          </div>

          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {lotsLoading ? (
              <div className="p-4 space-y-3">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 rounded-lg" />)}
              </div>
            ) : lots.length === 0 ? (
              <div className="p-12 text-center">
                <p className="text-sm font-medium mb-1">No lots yet</p>
                <p className="text-xs text-muted-foreground mb-4">
                  Add the first lot for this project.
                </p>
                <Button size="sm" variant="outline" onClick={() => setShowAddLot(true)}>
                  <Plus className="w-4 h-4" />
                  Add Lot
                </Button>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Lot #</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Block</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Unit Type</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Site</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {lots.map((lot) => (
                    <tr
                      key={lot.id}
                      className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3 font-medium font-mono">{lot.lot_number}</td>
                      <td className="px-4 py-3 text-muted-foreground">{lot.block_number ?? "—"}</td>
                      <td className="px-4 py-3 text-muted-foreground">{lot.unit_type ?? "—"}</td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">
                        {lot.site_id
                          ? sites.find((s) => s.id === lot.site_id)?.name ?? lot.site_id.slice(0, 8)
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={lotStatusVariant[lot.status]}>
                          {lotStatusLabel[lot.status]}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── STAGES (real data) ────────────────────────────────────────────── */}
      {tab === "stages" && (
        <div className="space-y-4">
          {stagesLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
            </div>
          ) : stageMasters.length === 0 ? (
            <div className="bg-card border border-border rounded-xl p-12 text-center">
              <p className="text-sm font-medium mb-1">No stage definitions found</p>
              <p className="text-xs text-muted-foreground">
                Stage master data must be seeded in the database first.
              </p>
            </div>
          ) : (
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground w-8">#</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Stage</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Inspection</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Certification</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {stageMasters.map((master) => {
                    const status = stageStatuses.find((s) => s.stage_id === master.id);
                    const currentStatus = (status?.status ?? "NOT_STARTED") as StageStatus;
                    return (
                      <tr
                        key={master.id}
                        className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors"
                      >
                        <td className="px-4 py-3 text-muted-foreground text-xs">{master.sequence_order}</td>
                        <td className="px-4 py-3 font-medium">{master.name}</td>
                        <td className="px-4 py-3">
                          <span className={cn("text-xs px-2 py-0.5 rounded-full font-medium", stageStatusColor[currentStatus])}>
                            {stageStatusLabel[currentStatus]}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground text-xs">
                          {status?.inspection_required ? (
                            <span className="text-warning font-medium">Required</span>
                          ) : "—"}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground text-xs">
                          {status?.certification_required ? (
                            <span className="text-primary font-medium">Required</span>
                          ) : "—"}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground text-xs max-w-[200px] truncate">
                          {status?.notes ?? "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {stageStatuses.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {(["NOT_STARTED", "IN_PROGRESS", "AWAITING_INSPECTION", "CERTIFIED"] as StageStatus[]).map((s) => {
                const count = stageStatuses.filter((st) => st.status === s).length;
                return (
                  <div key={s} className={cn("rounded-xl p-4 text-center", stageStatusColor[s])}>
                    <p className="text-2xl font-bold">{count}</p>
                    <p className="text-xs mt-0.5 opacity-80">{stageStatusLabel[s]}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Modals ─────────────────────────────────────────────────────────── */}
      {showEditProject && (
        <EditProjectModal
          project={project}
          onClose={() => setShowEditProject(false)}
          onUpdated={(updated) => {
            setProject(updated);
            setShowEditProject(false);
          }}
        />
      )}
      {showAddSite && (
        <AddSiteModal
          projectId={project.id}
          onClose={() => setShowAddSite(false)}
          onCreated={(site) => {
            setSites((prev) => [...prev, site].sort((a, b) => a.name.localeCompare(b.name)));
            setShowAddSite(false);
          }}
        />
      )}
      {editingSite && (
        <EditSiteModal
          site={editingSite}
          onClose={() => setEditingSite(null)}
          onUpdated={(updated) => {
            setSites((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
            setEditingSite(null);
          }}
        />
      )}
      {showAddLot && (
        <AddLotModal
          projectId={project.id}
          sites={sites}
          onClose={() => setShowAddLot(false)}
          onCreated={(lot) => {
            setLots((prev) =>
              [...prev, lot].sort((a, b) => a.lot_number.localeCompare(b.lot_number))
            );
            setShowAddLot(false);
          }}
        />
      )}
    </div>
  );
}
