import { useEffect, useRef, useState } from "react";
import { FileSpreadsheet, TrendingUp, Plus, Upload } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Modal } from "@/components/shared/Modal";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatCard } from "@/components/shared/StatCard";
import { projectsApi, type Project } from "@/api/projects";
import { boqApi, type BOQHeader, type BOQSection, type BOQItem, type BoqStatus } from "@/api/boq";
import { formatCurrency } from "@/lib/format";

const boqStatusVariant: Record<BoqStatus, "success" | "outline" | "secondary" | "default"> = {
  ACTIVE: "success",
  SUPERSEDED: "outline",
  UNDER_REVIEW: "secondary",
  DRAFT: "default",
  ARCHIVED: "outline",
};

const boqStatusLabel: Record<BoqStatus, string> = {
  ACTIVE: "Active",
  SUPERSEDED: "Superseded",
  UNDER_REVIEW: "Under Review",
  DRAFT: "Draft",
  ARCHIVED: "Archived",
};

interface SectionWithItems {
  section: BOQSection;
  items: BOQItem[];
}

function NewHeaderModal({
  open,
  onClose,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (versionName: string, notes: string) => Promise<void>;
}) {
  const [versionName, setVersionName] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!versionName.trim()) return;
    setSaving(true);
    try {
      await onSubmit(versionName.trim(), notes.trim());
      setVersionName("");
      setNotes("");
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="New BOQ Version" onClose={onClose} size="sm">
      <div className="p-6 space-y-4">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Version Name *</label>
          <input
            value={versionName}
            onChange={(e) => setVersionName(e.target.value)}
            placeholder="e.g. Rev 1 — April 2025"
            className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Notes</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
          />
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={handleSubmit} disabled={saving || !versionName.trim()}>
            {saving ? "Creating…" : "Create"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function ImportCsvModalReal({
  open,
  projectId,
  onClose,
  onImported,
}: {
  open: boolean;
  projectId: string;
  onClose: () => void;
  onImported: (header: BOQHeader) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [versionName, setVersionName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) { setVersionName(""); setFile(null); setError(""); }
  }, [open]);

  const handleSubmit = async () => {
    if (!file || !versionName.trim()) return;
    setSaving(true);
    setError("");
    try {
      const header = await boqApi.importCsv(projectId, file, versionName.trim());
      onImported(header);
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
        || "Import failed. Check the file format and try again.";
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} title="Import BOQ from CSV" onClose={onClose} size="sm">
      <div className="p-6 space-y-4">
        <div className="bg-muted/50 border border-border rounded-lg px-4 py-3 text-xs text-muted-foreground space-y-1">
          <p className="font-medium text-foreground">Expected CSV columns:</p>
          <p><code className="font-mono">section, description, unit, quantity, rate, type, specification, notes</code></p>
          <p>Only <strong>description</strong> is required. <strong>type</strong> must be MATERIAL, SERVICE, or PACKAGE.</p>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Version Name *</label>
          <input
            value={versionName}
            onChange={(e) => setVersionName(e.target.value)}
            placeholder="e.g. Rev 1 — April 2025"
            className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">CSV File *</label>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-muted-foreground file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-muted file:text-foreground hover:file:bg-muted/80 cursor-pointer"
          />
          {file && (
            <p className="mt-1 text-xs text-muted-foreground">{file.name}</p>
          )}
        </div>
        {error && (
          <p className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={saving || !file || !versionName.trim()}
          >
            {saving ? "Importing…" : "Import"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default function BOQPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [headers, setHeaders] = useState<BOQHeader[]>([]);
  const [selectedHeaderId, setSelectedHeaderId] = useState<string>("");
  const [sectionsWithItems, setSectionsWithItems] = useState<SectionWithItems[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingHeaders, setLoadingHeaders] = useState(false);
  const [loadingItems, setLoadingItems] = useState(false);
  const [showNewHeader, setShowNewHeader] = useState(false);
  const [showImportCsv, setShowImportCsv] = useState(false);

  // Load projects on mount
  useEffect(() => {
    projectsApi
      .list(1, 100)
      .then((res) => {
        setProjects(res.items);
        if (res.items.length > 0) setSelectedProjectId(res.items[0].id);
      })
      .catch(() => setProjects([]))
      .finally(() => setLoadingProjects(false));
  }, []);

  // Load headers when project changes
  useEffect(() => {
    if (!selectedProjectId) return;
    setLoadingHeaders(true);
    setHeaders([]);
    setSelectedHeaderId("");
    setSectionsWithItems([]);
    boqApi
      .listHeaders(selectedProjectId)
      .then((data) => {
        setHeaders(data);
        const active = data.find((h) => h.is_active_version) ?? data[0];
        if (active) setSelectedHeaderId(active.id);
      })
      .catch(() => setHeaders([]))
      .finally(() => setLoadingHeaders(false));
  }, [selectedProjectId]);

  // Load sections + items when header changes
  useEffect(() => {
    if (!selectedHeaderId) return;
    setLoadingItems(true);
    setSectionsWithItems([]);
    boqApi
      .listSections(selectedHeaderId)
      .then(async (sections) => {
        const all: SectionWithItems[] = await Promise.all(
          sections.map(async (section) => {
            const items = await boqApi.listItems(section.id).catch(() => []);
            return { section, items };
          })
        );
        setSectionsWithItems(all);
      })
      .catch(() => setSectionsWithItems([]))
      .finally(() => setLoadingItems(false));
  }, [selectedHeaderId]);

  const activeHeader = headers.find((h) => h.id === selectedHeaderId);
  const allItems = sectionsWithItems.flatMap((s) => s.items);
  const totalPlanned = allItems.reduce((sum, i) => sum + (i.planned_total ?? 0), 0);

  const handleCreateHeader = async (versionName: string, notes: string) => {
    const created = await boqApi.createHeader(selectedProjectId, { version_name: versionName, notes: notes || null });
    setHeaders((prev) => [...prev, created]);
    setSelectedHeaderId(created.id);
  };

  const handleImported = (header: BOQHeader) => {
    setHeaders((prev) => [...prev, header]);
    setSelectedHeaderId(header.id);
  };

  if (loadingProjects) {
    return (
      <div className="space-y-5 animate-fade-in">
        <Skeleton className="h-12 rounded-xl" />
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <PageHeader
        title="Bill of Quantities"
        description="Review and manage BOQ versions linked to projects."
        actions={
          selectedProjectId ? (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowImportCsv(true)}>
                <Upload className="w-4 h-4" />
                Import CSV
              </Button>
              <Button size="sm" onClick={() => setShowNewHeader(true)}>
                <Plus className="w-4 h-4" />
                New BOQ Version
              </Button>
            </div>
          ) : undefined
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Project</label>
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[220px]"
          >
            {projects.length === 0 ? (
              <option disabled>No projects</option>
            ) : (
              projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))
            )}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground block mb-1">BOQ Version</label>
          <select
            value={selectedHeaderId}
            onChange={(e) => setSelectedHeaderId(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm min-w-[220px]"
            disabled={loadingHeaders}
          >
            {loadingHeaders ? (
              <option>Loading…</option>
            ) : headers.length === 0 ? (
              <option disabled>No BOQ versions</option>
            ) : (
              headers.map((h) => (
                <option key={h.id} value={h.id}>{h.version_name}</option>
              ))
            )}
          </select>
        </div>
        {activeHeader && (
          <div className="mt-5">
            <Badge variant={boqStatusVariant[activeHeader.status]}>
              {boqStatusLabel[activeHeader.status]}
            </Badge>
            {activeHeader.is_active_version && (
              <Badge variant="success" className="ml-1.5">Active Version</Badge>
            )}
          </div>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Total Planned Value"
          value={formatCurrency(totalPlanned)}
          icon={FileSpreadsheet}
          color="bg-primary/10 text-primary"
        />
        <StatCard
          title="Sections"
          value={sectionsWithItems.length}
          icon={FileSpreadsheet}
          color="bg-warning/10 text-warning"
        />
        <StatCard
          title="Line Items"
          value={allItems.length}
          icon={TrendingUp}
          color="bg-success/10 text-success"
        />
      </div>

      {/* Notes */}
      {activeHeader?.notes && (
        <div className="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Note: </span>{activeHeader.notes}
        </div>
      )}

      {/* Body */}
      {loadingItems ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <Skeleton key={i} className="h-40 rounded-xl" />)}
        </div>
      ) : !selectedProjectId || headers.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">
          {!selectedProjectId ? "Select a project to view BOQ data." : "No BOQ versions for this project."}
        </div>
      ) : sectionsWithItems.length === 0 ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-sm text-muted-foreground">
          This BOQ version has no sections yet.
        </div>
      ) : (
        <div className="space-y-4">
          {sectionsWithItems.map(({ section, items }) => {
            const sectionTotal = items.reduce((sum, i) => sum + (i.planned_total ?? 0), 0);
            return (
              <div key={section.id} className="bg-card border border-border rounded-xl overflow-hidden">
                <div className="px-4 py-3 bg-muted/50 border-b border-border flex items-center justify-between">
                  <p className="text-sm font-semibold">{section.section_name}</p>
                  <p className="text-sm font-semibold text-primary">{formatCurrency(sectionTotal)}</p>
                </div>
                {items.length === 0 ? (
                  <p className="px-4 py-6 text-sm text-center text-muted-foreground">No items in this section.</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs">#</th>
                        <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs">Description</th>
                        <th className="text-right px-4 py-2.5 font-medium text-muted-foreground text-xs">Qty</th>
                        <th className="text-right px-4 py-2.5 font-medium text-muted-foreground text-xs">Unit</th>
                        <th className="text-right px-4 py-2.5 font-medium text-muted-foreground text-xs">Rate (R)</th>
                        <th className="text-right px-4 py-2.5 font-medium text-muted-foreground text-xs">Planned Total</th>
                        <th className="text-left px-4 py-2.5 font-medium text-muted-foreground text-xs">Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => (
                        <tr
                          key={item.id}
                          className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors"
                        >
                          <td className="px-4 py-2.5 text-muted-foreground text-xs">{item.sort_order}</td>
                          <td className="px-4 py-2.5">{item.raw_description}</td>
                          <td className="px-4 py-2.5 text-right tabular-nums">
                            {item.planned_quantity != null
                              ? item.planned_quantity.toLocaleString("en-ZA")
                              : "—"}
                          </td>
                          <td className="px-4 py-2.5 text-right text-muted-foreground">{item.unit ?? "—"}</td>
                          <td className="px-4 py-2.5 text-right tabular-nums">
                            {item.planned_rate != null
                              ? item.planned_rate.toLocaleString("en-ZA")
                              : "—"}
                          </td>
                          <td className="px-4 py-2.5 text-right tabular-nums font-medium">
                            {item.planned_total != null ? formatCurrency(item.planned_total) : "—"}
                          </td>
                          <td className="px-4 py-2.5 text-xs text-muted-foreground">{item.item_type}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="bg-muted/30 border-t border-border">
                        <td colSpan={5} className="px-4 py-2.5 text-xs font-semibold text-muted-foreground text-right">
                          Section Total
                        </td>
                        <td className="px-4 py-2.5 text-right font-semibold tabular-nums">
                          {formatCurrency(sectionTotal)}
                        </td>
                        <td />
                      </tr>
                    </tfoot>
                  </table>
                )}
              </div>
            );
          })}
          {/* Grand total */}
          <div className="flex justify-end px-1">
            <div className="bg-card border border-border rounded-xl px-5 py-3 flex items-center gap-6">
              <span className="text-sm font-medium text-muted-foreground">Grand Total (Planned)</span>
              <span className="text-lg font-bold text-primary">{formatCurrency(totalPlanned)}</span>
            </div>
          </div>
        </div>
      )}

      <NewHeaderModal
        open={showNewHeader}
        onClose={() => setShowNewHeader(false)}
        onSubmit={handleCreateHeader}
      />

      <ImportCsvModalReal
        open={showImportCsv}
        projectId={selectedProjectId}
        onClose={() => setShowImportCsv(false)}
        onImported={handleImported}
      />
    </div>
  );
}
