import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft, Plus, MapPin, Calendar, Building2, Pencil, Layers, Wand2,
  FileSpreadsheet, ChevronRight, Copy, Trash2, Tag, X, Check, Zap, Warehouse, BarChart2,
} from "lucide-react";
import { SitesBulkCreateModal } from "@/components/SitesBulkCreateModal";
import { LotsGeneratorModal } from "@/components/LotsGeneratorModal";
import { ApplyBOQTemplateModal } from "@/components/ApplyBOQTemplateModal";
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
import { lotTypesApi, type LotType, type LotTypeCreate, type LotTypeUpdate } from "@/api/lotTypes";
import { BulkPropagateModal } from "@/components/BulkPropagateModal";
import { boqApi, type BOQTemplate } from "@/api/boq";
import { warehouseApi, type WarehouseStockItem } from "@/api/warehouse";
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
  { key: "overview",   label: "Overview"   },
  { key: "sites",      label: "Sites"      },
  { key: "lots",       label: "Lots"       },
  { key: "lot-types",  label: "Lot Types"  },
  { key: "stages",     label: "Stages"     },
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
          <div className="space-y-2">
            <Label className="flex items-center gap-1.5">
              <Building2 className="w-3.5 h-3.5" />
              Company
            </Label>
            <select
              value={(form.client_name as string) ?? ""}
              onChange={(e) => setForm({ ...form, client_name: e.target.value })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">— Select company —</option>
              <option value="HMH Group">HMH Group</option>
              <option value="Minerat Construction &amp; Civils">Minerat Construction &amp; Civils</option>
            </select>
          </div>
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

// ── Lot Types tab ─────────────────────────────────────────────────────────────

function LotTypesTab({
  projectId, lotTypes, lots, templates, loading,
  showCreate, editingType, assigningType, propagatingType,
  onShowCreate, onCloseCreate, onEditType, onCloseEdit,
  onAssignType, onCloseAssign, onPropagateType, onClosePropagate, onRefresh,
}: {
  projectId:      string;
  lotTypes:       LotType[];
  lots:           import("@/api/lots").Lot[];
  templates:      BOQTemplate[];
  loading:        boolean;
  showCreate:     boolean;
  editingType:    LotType | null;
  assigningType:  LotType | null;
  propagatingType: LotType | null;
  onShowCreate:    () => void;
  onCloseCreate:   () => void;
  onEditType:      (t: LotType) => void;
  onCloseEdit:     () => void;
  onAssignType:    (t: LotType) => void;
  onCloseAssign:   () => void;
  onPropagateType: (t: LotType) => void;
  onClosePropagate: () => void;
  onRefresh:       () => void;
}) {
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1 max-w-xl">
          <p className="text-sm text-muted-foreground">
            Define unit types for bulk BOQ management and milestone propagation.
          </p>
          <p className="text-xs text-muted-foreground bg-muted/50 border border-border rounded-lg px-3 py-2">
            <strong>What are Lot Types?</strong> A Lot Type is a reusable template for a category of work — for example "3-bedroom house" or "single garage". Each type stores a Bill of Quantities (BOQ) and a set of milestone stages. When you assign a Lot Type to a lot, it copies that BOQ and stage checklist to the lot so you only define them once and reuse across the project.
          </p>
        </div>
        <Button size="sm" onClick={onShowCreate} className="shrink-0">
          <Plus className="w-4 h-4" />New Type
        </Button>
      </div>

      {/* List */}
      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 rounded-xl" />)}
        </div>
      ) : lotTypes.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-10 text-center space-y-3">
          <Tag className="w-8 h-8 text-muted-foreground mx-auto" />
          <p className="text-sm text-muted-foreground">
            No lot types yet. Create your first type to enable bulk BOQ management.
          </p>
          <Button size="sm" variant="outline" onClick={onShowCreate}>
            <Plus className="w-4 h-4" />Create Lot Type
          </Button>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          {lotTypes.map((lt, i) => (
            <div
              key={lt.id}
              className={cn(
                "flex items-center gap-4 px-4 py-4 hover:bg-muted/30 transition-colors",
                i < lotTypes.length - 1 && "border-b border-border",
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm">{lt.name}</span>
                  {lt.code && (
                    <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded font-mono">
                      {lt.code}
                    </span>
                  )}
                  <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">
                    {lt.lot_count} lot{lt.lot_count !== 1 ? "s" : ""}
                  </span>
                </div>
                {lt.description && (
                  <p className="text-xs text-muted-foreground mt-0.5 truncate">{lt.description}</p>
                )}
                {lt.default_template_name && (
                  <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                    <FileSpreadsheet className="w-3 h-3" />
                    {lt.default_template_name}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {lt.default_template_id && lt.lot_count > 0 && (
                  <Button size="sm" variant="outline"
                    className="h-8 text-xs gap-1 border-primary/30 text-primary hover:bg-primary/5"
                    onClick={() => onPropagateType(lt)}>
                    <Zap className="w-3.5 h-3.5" />Propagate
                  </Button>
                )}
                <Button size="sm" variant="outline" className="h-8 text-xs gap-1" onClick={() => onAssignType(lt)}>
                  <Layers className="w-3.5 h-3.5" />Assign Lots
                </Button>
                <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => onEditType(lt)}>
                  <Pencil className="w-3.5 h-3.5" />
                </Button>
                <button
                  onClick={async () => {
                    if (lt.lot_count > 0) {
                      alert(`Cannot delete "${lt.name}": ${lt.lot_count} lot(s) are assigned. Unassign them first.`);
                      return;
                    }
                    if (!window.confirm(`Delete lot type "${lt.name}"?`)) return;
                    try {
                      await lotTypesApi.delete(lt.id);
                      onRefresh();
                    } catch {
                      alert("Failed to delete lot type.");
                    }
                  }}
                  className="p-1.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <LotTypeFormModal
          projectId={projectId}
          templates={templates}
          onClose={onCloseCreate}
          onSaved={() => { onCloseCreate(); onRefresh(); }}
        />
      )}

      {/* Edit modal */}
      {editingType && (
        <LotTypeFormModal
          projectId={projectId}
          templates={templates}
          existing={editingType}
          onClose={onCloseEdit}
          onSaved={() => { onCloseEdit(); onRefresh(); }}
        />
      )}

      {/* Assign lots modal */}
      {assigningType && (
        <AssignLotsModal
          lotType={assigningType}
          allLots={lots}
          onClose={onCloseAssign}
          onSaved={() => { onCloseAssign(); onRefresh(); }}
        />
      )}

      {/* Propagate modal */}
      {propagatingType && (
        <BulkPropagateModal
          lotType={propagatingType}
          onClose={onClosePropagate}
          onDone={() => { onClosePropagate(); onRefresh(); }}
        />
      )}
    </div>
  );
}

// ── Lot Type Form Modal ───────────────────────────────────────────────────────

function LotTypeFormModal({
  projectId, templates, existing, onClose, onSaved,
}: {
  projectId:  string;
  templates:  BOQTemplate[];
  existing?:  LotType | null;
  onClose:    () => void;
  onSaved:    () => void;
}) {
  const [name,       setName]       = useState(existing?.name       ?? "");
  const [code,       setCode]       = useState(existing?.code       ?? "");
  const [desc,       setDesc]       = useState(existing?.description ?? "");
  const [templateId, setTemplateId] = useState(existing?.default_template_id ?? "");
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");

  const submit = async () => {
    if (!name.trim()) { setError("Name is required."); return; }
    setLoading(true); setError("");
    const body = {
      name:                name.trim(),
      code:                code.trim() || null,
      description:         desc.trim() || null,
      default_template_id: templateId || null,
    };
    try {
      if (existing) {
        await lotTypesApi.update(existing.id, body);
      } else {
        await lotTypesApi.create(projectId, body);
      }
      onSaved();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Failed to save.");
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-2xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">{existing ? "Edit Lot Type" : "New Lot Type"}</h2>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="space-y-3">
          <div>
            <Label>Name *</Label>
            <input value={name} onChange={e => setName(e.target.value)} autoFocus
              placeholder="e.g. Type A House, 3BR Unit, Corner Unit"
              className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Code (optional)</Label>
              <input value={code} onChange={e => setCode(e.target.value)}
                placeholder="TYPE-A"
                className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm" />
            </div>
            <div>
              <Label>Default BOQ Template</Label>
              <select value={templateId} onChange={e => setTemplateId(e.target.value)}
                className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm">
                <option value="">— None —</option>
                {templates.map(t => (
                  <option key={t.id} value={t.id}>{t.template_name || t.version_name}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <Label>Description</Label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2}
              placeholder="Optional description"
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none" />
          </div>
        </div>

        {error && <p className="text-sm text-destructive bg-destructive/10 rounded px-3 py-2">{error}</p>}

        <div className="flex gap-2 pt-1">
          <Button onClick={submit} disabled={loading} className="flex-1">
            {loading ? "Saving…" : existing ? "Save Changes" : "Create Type"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}

// ── Assign Lots Modal ─────────────────────────────────────────────────────────

function AssignLotsModal({
  lotType, allLots, onClose, onSaved,
}: {
  lotType:  LotType;
  allLots:  import("@/api/lots").Lot[];
  onClose:  () => void;
  onSaved:  () => void;
}) {
  const alreadyAssigned = new Set(
    allLots.filter(l => l.lot_type_id === lotType.id).map(l => l.id)
  );
  const [selected, setSelected]   = useState<Set<string>>(new Set(alreadyAssigned));
  const [loading,  setLoading]    = useState(false);
  const [error,    setError]      = useState("");

  const toggleLot = (id: string) =>
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const submit = async () => {
    setLoading(true); setError("");
    try {
      const toAssign = Array.from(selected).filter(id => !alreadyAssigned.has(id));
      const toRemove = Array.from(alreadyAssigned).filter(id => !selected.has(id));
      if (toAssign.length) await lotTypesApi.assignLots(lotType.id, toAssign);
      if (toRemove.length) await lotTypesApi.removeLots(lotType.id, toRemove);
      onSaved();
    } catch (err: unknown) {
      const d = (err as { response?: { data?: { detail?: string } } })?.response?.data;
      setError(d?.detail ?? "Failed to update assignment.");
    } finally { setLoading(false); }
  };

  // Sort lots naturally: "12" < "12A" < "B-17" < "Unit 5A"
  const sorted = [...allLots].sort((a, b) =>
    a.lot_number.localeCompare(b.lot_number, undefined, { numeric: true, sensitivity: "base" })
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-foreground/40">
      <div className="bg-card border border-border rounded-2xl w-full max-w-md flex flex-col max-h-[85vh]">
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border">
          <div>
            <h2 className="text-base font-semibold">Assign Lots — {lotType.name}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              {selected.size} of {allLots.length} lots selected
            </p>
          </div>
          <button onClick={onClose}><X className="w-4 h-4 text-muted-foreground" /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          <div className="border border-border rounded-lg overflow-hidden">
            {sorted.map((lot, i) => {
              const isChecked  = selected.has(lot.id);
              const otherType  = lot.lot_type_id && lot.lot_type_id !== lotType.id;
              return (
                <label key={lot.id}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-muted/30 transition-colors",
                    i < sorted.length - 1 && "border-b border-border/50",
                    isChecked && "bg-primary/5",
                  )}>
                  <input type="checkbox" checked={isChecked} onChange={() => toggleLot(lot.id)}
                    className="rounded shrink-0" />
                  <span className="flex-1 text-sm min-w-0">
                    <span className="font-medium font-mono">{lot.lot_number}</span>
                    {lot.unit_type && <span className="text-muted-foreground ml-1.5">· {lot.unit_type}</span>}
                    {!lot.site_id && <span className="text-muted-foreground ml-1 text-xs">(freestanding)</span>}
                  </span>
                  {isChecked && <Check className="w-3.5 h-3.5 text-primary shrink-0" />}
                  {otherType && !isChecked && (
                    <span className="text-[10px] text-amber-600 shrink-0">other type</span>
                  )}
                </label>
              );
            })}
          </div>
        </div>

        {error && <p className="mx-5 text-sm text-destructive bg-destructive/10 rounded px-3 py-2">{error}</p>}

        <div className="px-5 pb-5 pt-3 border-t border-border flex gap-2">
          <Button onClick={submit} disabled={loading} className="flex-1">
            {loading ? "Saving…" : "Apply Assignment"}
          </Button>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
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
  const [showBulkSites, setShowBulkSites] = useState(false);
  const [editingSite, setEditingSite] = useState<Site | null>(null);

  // Lots state — real
  const [lots, setLots] = useState<Lot[]>([]);
  const [lotsLoading, setLotsLoading] = useState(false);
  const [showAddLot, setShowAddLot] = useState(false);
  const [showGenerateLots, setShowGenerateLots] = useState(false);
  const [showApplyBOQ, setShowApplyBOQ] = useState(false);
  const [lotSiteFilter, setLotSiteFilter] = useState<string>("");
  const [lotStatusFilter, setLotStatusFilter] = useState<string>("");

  // Lot Types state — Phase 3D.2
  const [lotTypes, setLotTypes] = useState<LotType[]>([]);
  const [lotTypesLoading, setLotTypesLoading] = useState(false);
  const [showCreateType,    setShowCreateType]    = useState(false);
  const [editingType,       setEditingType]       = useState<LotType | null>(null);
  const [assigningType,     setAssigningType]     = useState<LotType | null>(null);
  const [propagatingType,   setPropagatingType]   = useState<LotType | null>(null);
  const [templates,         setTemplates]         = useState<BOQTemplate[]>([]);

  // Unassigned lots admin helper
  const [assigningSiteId, setAssigningSiteId] = useState("");
  const [assigningLots, setAssigningLots] = useState(false);
  const [assignMsg, setAssignMsg] = useState("");

  // Stage update state
  const [updatingStage, setUpdatingStage] = useState<string | null>(null); // stage master id
  const [stageUpdateStatus, setStageUpdateStatus] = useState<string>("");
  const [stageUpdateNotes, setStageUpdateNotes] = useState("");
  const [stageUpdateDelay, setStageUpdateDelay] = useState("");
  const [stageUpdateSaving, setStageUpdateSaving] = useState(false);

  // Stages state — real
  const [stageMasters, setStageMasters] = useState<StageMaster[]>([]);
  const [stageStatuses, setStageStatuses] = useState<ProjectStageStatus[]>([]);
  const [stagesLoading, setStagesLoading] = useState(false);

  // Warehouse summary — loaded for Overview tab
  const [warehouseStock, setWarehouseStock] = useState<WarehouseStockItem[]>([]);
  const [warehouseLoading, setWarehouseLoading] = useState(false);

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

  // ── Load lot types when Lot Types tab is active ─────────────────────────────
  useEffect(() => {
    if (tab !== "lot-types" || !projectId) return;
    setLotTypesLoading(true);
    Promise.all([
      lotTypesApi.list(projectId),
      boqApi.listTemplates(),
      // also load lots so the assign modal has data
      lotsApi.list(projectId),
    ])
      .then(([types, tmpl, ls]) => {
        setLotTypes(types);
        setTemplates(tmpl);
        setLots(ls);
      })
      .catch(() => {})
      .finally(() => setLotTypesLoading(false));
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

  // ── Load warehouse summary + sites for Overview tab ─────────────────────────
  useEffect(() => {
    if (tab !== "overview" || !projectId) return;
    setWarehouseLoading(true);
    Promise.all([
      warehouseApi.getMainStock(projectId),
      sitesApi.list(projectId, false),
    ])
      .then(([stock, activeSites]) => {
        setWarehouseStock(stock);
        setSites(activeSites);
      })
      .catch(() => setWarehouseStock([]))
      .finally(() => setWarehouseLoading(false));
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
    if (t.key === "sites")     return { ...t, count: sites.length };
    if (t.key === "lots")      return { ...t, count: lots.length || undefined };
    if (t.key === "lot-types") return { ...t, count: lotTypes.length || undefined };
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
              <Link to={`/projects/${project.id}/cost-summary`}>
                <Button size="sm" variant="outline">
                  <BarChart2 className="w-3.5 h-3.5" />
                  Cost Summary
                </Button>
              </Link>
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

          {/* Project Warehouse card */}
          <div className="bg-card border border-border rounded-xl p-5 space-y-3 sm:col-span-2 lg:col-span-1">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                <Warehouse className="w-3.5 h-3.5" />
                Project Warehouse
              </p>
              <Link
                to={`/project-warehouse?project=${projectId}`}
                className="text-xs text-primary hover:underline font-medium"
              >
                Open →
              </Link>
            </div>
            {warehouseLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map(i => <div key={i} className="h-8 bg-muted/50 rounded animate-pulse" />)}
              </div>
            ) : warehouseStock.length === 0 ? (
              <p className="text-sm text-muted-foreground italic">No stock on hand.</p>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <div className="text-center p-3 bg-muted/50 rounded-lg">
                  <p className="text-2xl font-bold">{warehouseStock.length}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">SKUs on hand</p>
                </div>
                <div className="text-center p-3 bg-primary/10 rounded-lg">
                  <p className="text-2xl font-bold text-primary">
                    {warehouseStock.reduce((s, i) => s + i.on_hand, 0).toLocaleString()}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">Total units</p>
                </div>
                <div className="col-span-2 text-xs text-muted-foreground pt-1 border-t border-border">
                  {(() => {
                    const latest = warehouseStock
                      .map(i => i.last_movement)
                      .filter(Boolean)
                      .sort()
                      .at(-1);
                    return latest ? `Last movement: ${formatDate(latest)}` : "No movements yet";
                  })()}
                </div>
              </div>
            )}
            {sites.filter(s => s.is_active).length > 0 && (
              <div className="pt-1 border-t border-border">
                <p className="text-xs text-muted-foreground">
                  {sites.filter(s => s.is_active).length} active site{sites.filter(s => s.is_active).length !== 1 ? "s" : ""}
                </p>
              </div>
            )}
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
            <Button size="sm" variant="outline" onClick={() => setShowBulkSites(true)}>
              <Layers className="w-4 h-4" />
              Bulk Create
            </Button>
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
                      onClick={() => { setTab("lots"); setLotSiteFilter(site.id); setLotStatusFilter(""); }}
                      className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors cursor-pointer group"
                    >
                      <td className="px-4 py-3 font-medium flex items-center gap-1.5">
                        {site.name}
                        <ChevronRight className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100" />
                      </td>
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
                        <div className="flex items-center gap-1">
                          <button
                            onClick={(e) => { e.stopPropagation(); setEditingSite(site); }}
                            className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                            title="Edit site"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          {site.is_active && (
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (!window.confirm(
                                  `Deactivate site "${site.name}"?\n\n` +
                                  `The site will be hidden from all lists. All historical data ` +
                                  `(deliveries, stock, BOQ) is preserved.\n\n` +
                                  `This can be undone by editing the site and setting it back to Active.`
                                )) return;
                                try {
                                  await sitesApi.delete(site.id);
                                  setSites(prev => prev.filter(s => s.id !== site.id));
                                } catch (err: unknown) {
                                  const msg = (err as { response?: { data?: { detail?: string } } })
                                    ?.response?.data?.detail ?? "Cannot delete site.";
                                  alert(`⚠ ${msg}`);
                                }
                              }}
                              className="p-1.5 rounded-md hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive"
                              title="Deactivate site (soft delete)"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
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
      {tab === "lots" && (() => {
        const naturalSortedLots = [...lots].sort((a, b) =>
          a.lot_number.localeCompare(b.lot_number, undefined, { numeric: true, sensitivity: "base" })
        );
        const displayLots = naturalSortedLots.filter(l => {
          if (lotSiteFilter && l.site_id !== lotSiteFilter) return false;
          if (lotStatusFilter === "__incomplete__" && l.status === "COMPLETED") return false;
          if (lotStatusFilter && lotStatusFilter !== "__incomplete__" && l.status !== lotStatusFilter) return false;
          return true;
        });
        const activeSiteName = lotSiteFilter ? sites.find(s => s.id === lotSiteFilter)?.name : null;
        return (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-sm text-muted-foreground">
                {displayLots.length} of {lots.length} lot{lots.length !== 1 ? "s" : ""}
                {activeSiteName ? <> in <span className="font-medium text-foreground">{activeSiteName}</span></> : ""}
              </p>
              {/* Filter chips */}
              {(lotSiteFilter || lotStatusFilter) && (
                <button
                  onClick={() => { setLotSiteFilter(""); setLotStatusFilter(""); }}
                  className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary hover:bg-primary/20 flex items-center gap-1"
                >
                  Clear filters ×
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowApplyBOQ(true)}>
                <FileSpreadsheet className="w-4 h-4" />
                Apply BOQ Template
              </Button>
              <Button size="sm" variant="outline" onClick={() => setShowGenerateLots(true)}>
                <Wand2 className="w-4 h-4" />
                Generate Lots
              </Button>
              <Button size="sm" onClick={() => setShowAddLot(true)}>
                <Plus className="w-4 h-4" />
                Add Lot
              </Button>
            </div>
          </div>

          {/* Filter bar */}
          <div className="flex gap-2 flex-wrap">
            {sites.length > 1 && (
              <select
                value={lotSiteFilter}
                onChange={e => setLotSiteFilter(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 text-xs"
              >
                <option value="">All sites</option>
                {[...sites].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" })).map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            )}
            <select
              value={lotStatusFilter}
              onChange={e => setLotStatusFilter(e.target.value)}
              className="h-8 rounded-md border border-input bg-background px-2 text-xs"
            >
              <option value="">All statuses</option>
              <option value="__incomplete__">Incomplete only</option>
              <option value="AVAILABLE">Available</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="ON_HOLD">On Hold</option>
              <option value="COMPLETED">Completed</option>
            </select>
          </div>

          {/* Unassigned lots admin banner — only when project HAS sites but some lots are unassigned.
               Freestanding projects (sites.length=0) intentionally have lots without site_id. */}
          {!lotsLoading && lots.some(l => !l.site_id) && sites.length > 1 && (
            <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 space-y-3">
              <div>
                <p className="text-sm font-semibold text-amber-800">
                  {lots.filter(l => !l.site_id).length} lot{lots.filter(l => !l.site_id).length !== 1 ? "s" : ""} are not assigned to a site
                </p>
                <p className="text-xs text-amber-700 mt-0.5">
                  This project has multiple sites. Assigning these lots to the correct site
                  helps with BOQ generation and reporting.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={assigningSiteId}
                  onChange={e => { setAssigningSiteId(e.target.value); setAssignMsg(""); }}
                  className="h-8 rounded-md border border-amber-300 bg-white px-2 text-xs min-w-[180px]"
                >
                  <option value="">— Select site to assign to —</option>
                  {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <button
                  disabled={!assigningSiteId || assigningLots}
                  onClick={async () => {
                    if (!assigningSiteId || !projectId) return;
                    setAssigningLots(true);
                    try {
                      const unassignedIds = lots.filter(l => !l.site_id).map(l => l.id);
                      const res = await import("@/api/client").then(m =>
                        m.default.patch<{ data: { updated: number; skipped: number }; message: string }>(
                          `/projects/${projectId}/lots/assign-site`,
                          { site_id: assigningSiteId, lot_ids: unassignedIds },
                        )
                      );
                      setAssignMsg(res.data.message);
                      // Reload lots
                      const updated = await import("@/api/lots").then(m => m.lotsApi.list(projectId));
                      setLots(updated);
                    } catch { setAssignMsg("Failed to assign lots. Try again."); }
                    finally { setAssigningLots(false); }
                  }}
                  className="text-xs px-3 py-1.5 rounded-md bg-amber-600 text-white disabled:opacity-50 hover:bg-amber-700"
                >
                  {assigningLots ? "Assigning…" : "Assign unassigned lots to this site"}
                </button>
              </div>
              {assignMsg && (
                <p className="text-xs font-medium text-amber-900">{assignMsg}</p>
              )}
            </div>
          )}

          <div className="bg-card border border-border rounded-xl overflow-hidden">
            {lotsLoading ? (
              <div className="p-4 space-y-3">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 rounded-lg" />)}
              </div>
            ) : displayLots.length === 0 ? (
              <div className="p-12 text-center">
                <p className="text-sm font-medium mb-1">{lots.length === 0 ? "No lots yet" : "No lots match the current filters"}</p>
                <p className="text-xs text-muted-foreground mb-4">
                  {lots.length === 0
                    ? "Add the first lot for this project."
                    : "Try changing the site or status filter above."}
                </p>
                {lots.length === 0 && (
                  <Button size="sm" variant="outline" onClick={() => setShowAddLot(true)}>
                    <Plus className="w-4 h-4" />
                    Add Lot
                  </Button>
                )}
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Lot #</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Unit Type</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Site</th>
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                    <th className="px-4 py-3 text-center font-medium text-muted-foreground">BOQ</th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody>
                  {displayLots.map((lot) => (
                    <tr
                      key={lot.id}
                      onClick={() => navigate(`/lots/${lot.id}`)}
                      className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors cursor-pointer group"
                    >
                      <td className="px-4 py-3 font-medium font-mono">{lot.lot_number}</td>
                      <td className="px-4 py-3 text-muted-foreground hidden sm:table-cell">
                        {lot.unit_type ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-xs hidden md:table-cell">
                        {lot.site_id
                          ? <span className="text-muted-foreground">{sites.find((s) => s.id === lot.site_id)?.name ?? lot.site_id.slice(0, 8)}</span>
                          : <span className="text-muted-foreground italic">Freestanding</span>
                        }
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={lotStatusVariant[lot.status]}>
                          {lotStatusLabel[lot.status]}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {lot.boq_template_id ? (
                          <FileSpreadsheet className="w-4 h-4 text-green-500 mx-auto" title="BOQ applied" />
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-2 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <ChevronRight className="w-4 h-4 text-muted-foreground" />
                          <button
                            onClick={async (e) => {
                              e.stopPropagation();
                              const hasStock = lot.status !== "AVAILABLE";
                              const confirmMsg = hasStock
                                ? `Delete lot ${lot.lot_number}?\n\n` +
                                  `Status: ${lot.status}. BOQ items linked to this lot will become ` +
                                  `unlinked (lot_id cleared). Stock ledger entries and usage logs ` +
                                  `will block deletion — you will see an error if they exist.\n\n` +
                                  `This action cannot be undone.`
                                : `Delete lot ${lot.lot_number}?\n\nThis cannot be undone.`;
                              if (!window.confirm(confirmMsg)) return;
                              try {
                                const res = await lotsApi.delete(lot.id);
                                setLots(prev => prev.filter(l => l.id !== lot.id));
                                if (res.boq_items_unlinked > 0) {
                                  alert(`Lot ${res.deleted_lot_number} deleted. ${res.boq_items_unlinked} BOQ item(s) were unlinked.`);
                                }
                              } catch (err: unknown) {
                                const msg = (err as { response?: { data?: { detail?: string } } })
                                  ?.response?.data?.detail ?? "Cannot delete lot.";
                                alert(`⚠ ${msg}`);
                              }
                            }}
                            className="p-1.5 rounded-md hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100"
                            title="Delete lot"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
        );
      })()}

      {/* ── LOT TYPES (Phase 3D.2) ───────────────────────────────────────── */}
      {tab === "lot-types" && (
        <LotTypesTab
          projectId={projectId!}
          lotTypes={lotTypes}
          lots={lots}
          templates={templates}
          loading={lotTypesLoading}
          showCreate={showCreateType}
          editingType={editingType}
          assigningType={assigningType}
          propagatingType={propagatingType}
          onShowCreate={() => setShowCreateType(true)}
          onCloseCreate={() => setShowCreateType(false)}
          onEditType={setEditingType}
          onCloseEdit={() => setEditingType(null)}
          onAssignType={setAssigningType}
          onCloseAssign={() => setAssigningType(null)}
          onPropagateType={setPropagatingType}
          onClosePropagate={() => setPropagatingType(null)}
          onRefresh={() => {
            setLotTypesLoading(true);
            Promise.all([lotTypesApi.list(projectId!), lotsApi.list(projectId!)])
              .then(([types, ls]) => { setLotTypes(types); setLots(ls); })
              .catch(() => {})
              .finally(() => setLotTypesLoading(false));
          }}
        />
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
                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Notes</th>
                    <th className="px-4 py-3 w-20" />
                  </tr>
                </thead>
                <tbody>
                  {stageMasters.map((master) => {
                    const status = stageStatuses.find((s) => s.stage_id === master.id);
                    const currentStatus = (status?.status ?? "NOT_STARTED") as StageStatus;
                    const isUpdating = updatingStage === master.id;
                    return (
                      <>
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
                          <td className="px-4 py-3 text-muted-foreground text-xs max-w-[160px] truncate">
                            {status?.notes ?? "—"}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => {
                                  if (isUpdating) { setUpdatingStage(null); return; }
                                  setUpdatingStage(master.id);
                                  setStageUpdateStatus(currentStatus);
                                  setStageUpdateNotes(status?.notes ?? "");
                                  setStageUpdateDelay("");
                                }}
                                className="text-xs text-primary hover:underline"
                              >
                                {isUpdating ? "Cancel" : "Update"}
                              </button>
                              <button
                                onClick={() => {
                                  const newName = window.prompt("Rename this stage:", master.name);
                                  if (!newName || newName.trim() === master.name) return;
                                  stagesApi.renameMaster(master.id, newName.trim())
                                    .then(updated => setStageMasters(prev => prev.map(m => m.id === updated.id ? updated : m)))
                                    .catch(() => alert("Failed to rename stage."));
                                }}
                                className="text-xs text-muted-foreground hover:text-foreground"
                                title="Rename stage"
                              >
                                Rename
                              </button>
                              {status && (
                                <button
                                  onClick={async () => {
                                    const blocked = currentStatus === "COMPLETED" || currentStatus === "CERTIFIED";
                                    if (blocked) {
                                      alert(`Cannot remove a ${currentStatus.toLowerCase()} stage. Reset its status first.`);
                                      return;
                                    }
                                    if (!window.confirm(`Remove "${master.name}" from this project's stage tracking?\n\nThis only removes the tracking entry — the stage definition remains.`)) return;
                                    try {
                                      await stagesApi.deleteStatus(project!.id, status.id);
                                      setStageStatuses(prev => prev.filter(s => s.id !== status.id));
                                    } catch (err: unknown) {
                                      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
                                      alert(detail ?? "Failed to remove stage.");
                                    }
                                  }}
                                  className="text-xs text-muted-foreground hover:text-destructive"
                                  title="Remove from project tracking"
                                >
                                  Remove
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                        {isUpdating && (
                          <tr key={`${master.id}-update`} className="border-b border-border bg-primary/5">
                            <td colSpan={5} className="px-4 py-3">
                              <div className="space-y-3">
                                <div className="grid grid-cols-2 gap-3">
                                  <div className="space-y-1">
                                    <label className="text-xs text-muted-foreground font-medium">Status</label>
                                    <select
                                      value={stageUpdateStatus}
                                      onChange={(e) => setStageUpdateStatus(e.target.value)}
                                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
                                    >
                                      {(["NOT_STARTED","IN_PROGRESS","COMPLETED","AWAITING_INSPECTION","CERTIFIED"] as StageStatus[]).map((s) => (
                                        <option key={s} value={s}>{stageStatusLabel[s]}</option>
                                      ))}
                                    </select>
                                  </div>
                                  <div className="space-y-1">
                                    <label className="text-xs text-muted-foreground font-medium">Notes</label>
                                    <input
                                      value={stageUpdateNotes}
                                      onChange={(e) => setStageUpdateNotes(e.target.value)}
                                      placeholder="Progress note"
                                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
                                    />
                                  </div>
                                </div>
                                {stageUpdateStatus === "IN_PROGRESS" && (
                                  <div className="space-y-1">
                                    <label className="text-xs text-muted-foreground font-medium">Delay reason (if delayed)</label>
                                    <input
                                      value={stageUpdateDelay}
                                      onChange={(e) => setStageUpdateDelay(e.target.value)}
                                      placeholder="Leave blank if on schedule"
                                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
                                    />
                                  </div>
                                )}
                                <div className="flex gap-2">
                                  <button
                                    disabled={stageUpdateSaving}
                                    onClick={async () => {
                                      if (!project) return;
                                      setStageUpdateSaving(true);
                                      try {
                                        await stagesApi.upsert(project.id, {
                                          stage_id: master.id,
                                          status: stageUpdateStatus as StageStatus,
                                          notes: stageUpdateNotes || undefined,
                                          delay_reason: stageUpdateDelay || undefined,
                                        });
                                        const [ms2, ss2] = await Promise.all([
                                          stagesApi.listMasters(),
                                          stagesApi.listProjectStatuses(project.id),
                                        ]);
                                        setStageMasters(ms2);
                                        setStageStatuses(ss2);
                                        setUpdatingStage(null);
                                      } catch { /* ignore */ }
                                      finally { setStageUpdateSaving(false); }
                                    }}
                                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                                  >
                                    {stageUpdateSaving ? "Saving…" : "Save"}
                                  </button>
                                  <button
                                    onClick={() => setUpdatingStage(null)}
                                    className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border hover:bg-muted"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
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
      {showBulkSites && (
        <SitesBulkCreateModal
          projectId={project.id}
          onClose={() => setShowBulkSites(false)}
          onCreated={() => {
            // Reload sites
            setSitesLoading(true);
            sitesApi.list(project.id, includeInactive)
              .then(setSites)
              .catch(() => {})
              .finally(() => setSitesLoading(false));
          }}
        />
      )}
      {showGenerateLots && (
        <LotsGeneratorModal
          projectId={project.id}
          onClose={() => setShowGenerateLots(false)}
          onGenerated={() => {
            setLotsLoading(true);
            lotsApi.list(project.id)
              .then(setLots)
              .catch(() => {})
              .finally(() => setLotsLoading(false));
          }}
        />
      )}
      {showApplyBOQ && (
        <ApplyBOQTemplateModal
          projectId={project.id}
          onClose={() => setShowApplyBOQ(false)}
          onApplied={() => {
            setLotsLoading(true);
            lotsApi.list(project.id)
              .then(setLots)
              .catch(() => {})
              .finally(() => setLotsLoading(false));
          }}
        />
      )}
    </div>
  );
}
