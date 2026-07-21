import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, FileText, RefreshCw } from "lucide-react";
import {
  listProgressClaims, createProgressClaim,
  ProgressClaimListItem, ProgressClaimCreate, ProgressClaimStatus,
} from "@/api/progressClaims";
import { projectsApi } from "@/api/projects";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_COLORS: Record<ProgressClaimStatus, string> = {
  DRAFT:             "bg-slate-100 text-slate-700",
  GENERATED:         "bg-blue-100 text-blue-700",
  UNDER_REVIEW:      "bg-yellow-100 text-yellow-700",
  READY_FOR_PRICING: "bg-orange-100 text-orange-700",
  APPROVED:          "bg-green-100 text-green-700",
  EXPORTED:          "bg-purple-100 text-purple-700",
  CANCELLED:         "bg-red-100 text-red-700",
};

type Project = { id: string; name: string };

export default function ProgressClaimsPage() {
  const navigate = useNavigate();
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<ProgressClaimCreate>({
    claim_title: "",
    period_start: "",
    period_end: "",
    municipality_name: "Ethekweni Municipality",
  });

  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [claims, setClaims] = useState<ProgressClaimListItem[]>([]);
  const [claimsLoading, setClaimsLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    projectsApi.list().then((r) => setProjects(r.items)).finally(() => setProjectsLoading(false));
  }, []);

  const fetchClaims = useCallback(() => {
    if (!selectedProject) return;
    setClaimsLoading(true);
    listProgressClaims(selectedProject).then(setClaims).finally(() => setClaimsLoading(false));
  }, [selectedProject]);

  useEffect(() => {
    setClaims([]);
    fetchClaims();
  }, [fetchClaims]);

  const handleCreate = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const claim = await createProgressClaim(selectedProject, form);
      fetchClaims();
      setShowCreate(false);
      setForm({ claim_title: "", period_start: "", period_end: "", municipality_name: "Ethekweni Municipality" });
      navigate(`/progress-claims/${claim.id}`);
    } catch (e: any) {
      setCreateError(e?.response?.data?.detail || "Failed to create claim");
    } finally {
      setCreating(false);
    }
  };

  const selectedProjectName = projects.find((p) => p.id === selectedProject)?.name;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Progress Claims</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Monthly progress claims submitted to municipalities. No pricing — work evidence only.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchClaims}>
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
          {selectedProject && (
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="w-4 h-4 mr-1" /> New Claim
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

      {/* Create form modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40">
          <div className="bg-background rounded-xl shadow-xl p-6 w-full max-w-md mx-4">
            <h2 className="text-lg font-semibold mb-4">New Progress Claim</h2>
            <div className="space-y-4">
              <div>
                <Label>Claim Title *</Label>
                <Input
                  placeholder="e.g. June 2026 Progress Claim"
                  value={form.claim_title}
                  onChange={(e) => setForm((f) => ({ ...f, claim_title: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Period Start *</Label>
                  <Input
                    type="date"
                    value={form.period_start}
                    onChange={(e) => setForm((f) => ({ ...f, period_start: e.target.value }))}
                  />
                </div>
                <div>
                  <Label>Period End *</Label>
                  <Input
                    type="date"
                    value={form.period_end}
                    onChange={(e) => setForm((f) => ({ ...f, period_end: e.target.value }))}
                  />
                </div>
              </div>
              <div>
                <Label>Municipality Name</Label>
                <Input
                  value={form.municipality_name}
                  onChange={(e) => setForm((f) => ({ ...f, municipality_name: e.target.value }))}
                />
              </div>
            </div>
            {createError && <p className="text-destructive text-sm mt-3">{createError}</p>}
            <div className="flex justify-end gap-2 mt-5">
              <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button
                onClick={handleCreate}
                disabled={!form.claim_title || !form.period_start || !form.period_end || creating}
              >
                {creating ? "Creating..." : "Create Claim"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Claims list */}
      {!selectedProject ? (
        <div className="text-center text-muted-foreground py-20">
          Select a project to view its progress claims.
        </div>
      ) : claimsLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
      ) : claims.length === 0 ? (
        <div className="text-center text-muted-foreground py-20">
          <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>No progress claims for {selectedProjectName}.</p>
          <p className="text-sm mt-1">Create the first claim to get started.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {claims.map((claim) => (
            <ClaimCard key={claim.id} claim={claim} onClick={() => navigate(`/progress-claims/${claim.id}`)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ClaimCard({ claim, onClick }: { claim: ProgressClaimListItem; onClick: () => void }) {
  return (
    <div
      className="bg-card border rounded-xl p-4 cursor-pointer hover:border-primary/50 hover:shadow-sm transition-all"
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-semibold text-sm">{claim.claim_number}</span>
            <Badge className={STATUS_COLORS[claim.status as ProgressClaimStatus] || ""}>
              {claim.status.replace(/_/g, " ")}
            </Badge>
          </div>
          <p className="text-sm font-medium truncate">{claim.claim_title}</p>
          <p className="text-xs text-muted-foreground mt-1">
            Period: {claim.period_start} → {claim.period_end}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-muted-foreground">
            {claim.included_line_count} / {claim.line_count} lines included
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {new Date(claim.updated_at).toLocaleDateString()}
          </p>
        </div>
      </div>
    </div>
  );
}
