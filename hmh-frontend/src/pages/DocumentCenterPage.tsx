import { useEffect, useState, useCallback, useMemo } from "react";
import {
  FileText, Download, Eye, Search, RefreshCw, Files,
  ShoppingCart, Package, Receipt, Truck, CreditCard, Image as ImageIcon,
} from "lucide-react";
import { documentsApi, type ProjectDocument, type DocumentEntityType } from "@/api/documents";
import { projectsApi, type Project } from "@/api/projects";

// ── Helpers ────────────────────────────────────────────────────────────────────

const ENTITY_TABS: { key: DocumentEntityType | "ALL"; label: string; icon: React.ElementType }[] = [
  { key: "ALL",              label: "All",               icon: Files       },
  { key: "MATERIAL_REQUEST", label: "Material Requests", icon: ShoppingCart },
  { key: "PURCHASE_ORDER",   label: "Purchase Orders",   icon: Package     },
  { key: "INVOICE",          label: "Invoices",          icon: Receipt     },
  { key: "DELIVERY",         label: "Deliveries",        icon: Truck       },
  { key: "PAYMENT",          label: "Payments",          icon: CreditCard  },
];

const TYPE_BADGE: Record<string, string> = {
  PDF:            "bg-red-100 text-red-700",
  PO_DOCUMENT:    "bg-blue-100 text-blue-700",
  DELIVERY_NOTE:  "bg-green-100 text-green-700",
  INVOICE_COPY:   "bg-yellow-100 text-yellow-700",
  QUOTATION:      "bg-purple-100 text-purple-700",
  PHOTO:          "bg-gray-100 text-gray-700",
  PROOF:          "bg-orange-100 text-orange-700",
};

function typeBadgeClass(type: string) {
  return TYPE_BADGE[type] ?? "bg-gray-100 text-gray-600";
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-ZA", {
    day: "2-digit", month: "short", year: "numeric",
  });
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function DocumentCenterPage() {
  const [projects, setProjects]     = useState<Project[]>([]);
  const [projectId, setProjectId]   = useState<string>("");
  const [documents, setDocuments]   = useState<ProjectDocument[]>([]);
  const [loading, setLoading]       = useState(false);
  const [tab, setTab]               = useState<DocumentEntityType | "ALL">("ALL");
  const [search, setSearch]         = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  // Load projects on mount
  useEffect(() => {
    projectsApi.list(1, 200).then((r) => {
      setProjects(r.items);
      if (r.items.length > 0) setProjectId(r.items[0].id);
    }).catch(() => {});
  }, []);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    documentsApi.list(projectId, {
      entity_type: tab === "ALL" ? undefined : tab,
      search: debouncedSearch || undefined,
      limit: 200,
    }).then(setDocuments).catch(() => setDocuments([])).finally(() => setLoading(false));
  }, [projectId, tab, debouncedSearch]);

  useEffect(() => { load(); }, [load]);

  // Tab counts from the full loaded list (filtered client-side for "ALL" view)
  const tabCounts = useMemo(() => {
    const map: Record<string, number> = { ALL: documents.length };
    for (const d of documents) {
      map[d.entity_type] = (map[d.entity_type] ?? 0) + 1;
    }
    return map;
  }, [documents]);

  const displayed = useMemo(() => {
    if (tab === "ALL") return documents;
    return documents.filter((d) => d.entity_type === tab);
  }, [documents, tab]);

  function handleView(doc: ProjectDocument) {
    window.open(doc.download_url, "_blank", "noopener,noreferrer");
  }

  function handleDownload(doc: ProjectDocument) {
    const a = document.createElement("a");
    a.href = doc.download_url;
    a.download = doc.file_name;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.click();
  }

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Document Center</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            All project documents — material requests, POs, invoices, deliveries &amp; payments
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border text-sm hover:bg-muted transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap gap-3">
        {/* Project picker */}
        <select
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm bg-background min-w-[200px]"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        {/* Search */}
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search file name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b overflow-x-auto">
        {ENTITY_TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
              tab === key
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
            {tabCounts[key === "ALL" ? "ALL" : key] !== undefined && (
              <span className="ml-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold">
                {key === "ALL" ? tabCounts.ALL : (tabCounts[key] ?? 0)}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Document list */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground">
          <RefreshCw className="w-5 h-5 animate-spin mr-2" />
          Loading documents…
        </div>
      ) : displayed.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Files className="w-10 h-10 mb-3 opacity-30" />
          <p className="text-sm">No documents found</p>
          {search && (
            <button
              onClick={() => setSearch("")}
              className="mt-2 text-xs text-primary hover:underline"
            >
              Clear search
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {displayed.map((doc) => (
            <DocumentRow
              key={doc.id}
              doc={doc}
              onView={handleView}
              onDownload={handleDownload}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Document Row ───────────────────────────────────────────────────────────────

interface RowProps {
  doc: ProjectDocument;
  onView: (d: ProjectDocument) => void;
  onDownload: (d: ProjectDocument) => void;
}

function DocumentRow({ doc, onView, onDownload }: RowProps) {
  return (
    <div className="flex items-center gap-4 p-3.5 rounded-xl border bg-card hover:bg-muted/30 transition-colors group">
      {/* File icon */}
      <div className="shrink-0 w-10 h-10 rounded-lg bg-muted flex items-center justify-center">
        {doc.is_image
          ? <ImageIcon className="w-5 h-5 text-muted-foreground" />
          : <FileText className="w-5 h-5 text-muted-foreground" />
        }
      </div>

      {/* Main info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm truncate max-w-xs">{doc.file_name}</span>
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${typeBadgeClass(doc.attachment_type)}`}>
            {doc.attachment_type.replace(/_/g, " ")}
          </span>
        </div>
        <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground flex-wrap">
          <span className="font-medium text-foreground/70">{doc.entity_label}</span>
          {doc.entity_ref && <span>#{doc.entity_ref}</span>}
          {doc.caption && <span className="italic truncate max-w-[200px]">{doc.caption}</span>}
          <span>·</span>
          <span>{doc.file_size_display}</span>
          <span>·</span>
          <span>{formatDate(doc.uploaded_at)}</span>
          {doc.uploaded_by_name && (
            <>
              <span>·</span>
              <span>{doc.uploaded_by_name}</span>
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => onView(doc)}
          title="View"
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border hover:bg-background transition-colors"
        >
          <Eye className="w-3.5 h-3.5" />
          View
        </button>
        <button
          onClick={() => onDownload(doc)}
          title="Download"
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border hover:bg-background transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          Download
        </button>
      </div>
    </div>
  );
}
