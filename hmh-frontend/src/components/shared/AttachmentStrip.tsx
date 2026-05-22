/**
 * AttachmentStrip — universal reusable attachment gallery.
 *
 * Phase 3K: The ONE attachment component used across the entire platform.
 *
 * Supports:
 *   - Multiple image uploads (sequential, with per-file progress)
 *   - Multiple PDF/document uploads
 *   - Thumbnail grid with lightbox image preview
 *   - PDF/doc download links
 *   - Soft-delete with optimistic UI
 *   - Optional category selector on upload
 *   - uploaded_by_name display on hover
 *   - READ_ONLY enforcement (no upload/delete)
 *   - SITE_STAFF: upload-only (can delete own uploads during same session)
 *   - compact mode for inline/table use
 *
 * Used by:
 *   Deliveries, Payments, Fuel Logs, Procurement (MR + PO),
 *   Milestones, Project Warehouse, Suppliers, Lots, Projects
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Camera, FileText, RefreshCw, X as XIcon, Upload, Eye, User,
} from "lucide-react";
import {
  attachmentsApi,
  type Attachment,
  type AttachmentEntity,
  type AttachmentType,
  ATTACHMENT_TYPE_LABELS,
} from "@/api/attachments";
import { ROLE_KEY } from "@/lib/constants";
import { cn } from "@/lib/utils";

// ── Lightbox ──────────────────────────────────────────────────────────────────

function Lightbox({ att, onClose }: { att: Attachment; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/88 backdrop-blur-sm"
      onClick={onClose}
    >
      <button
        className="absolute top-4 right-4 p-2 rounded-full bg-black/50 text-white/80 hover:text-white"
        onClick={onClose}
      >
        <XIcon className="w-5 h-5" />
      </button>

      <img
        src={att.download_url}
        alt={att.file_name}
        className="max-h-[90vh] max-w-[90vw] rounded-xl shadow-2xl object-contain"
        onClick={e => e.stopPropagation()}
      />

      <div className="absolute bottom-4 left-0 right-0 flex flex-col items-center gap-1" onClick={e => e.stopPropagation()}>
        {att.uploaded_by_name && (
          <p className="text-white/60 text-xs flex items-center gap-1">
            <User className="w-3 h-3" />
            {att.uploaded_by_name}
            {att.uploaded_at && ` · ${new Date(att.uploaded_at).toLocaleDateString("en-ZA")}`}
          </p>
        )}
        <a
          href={att.download_url} target="_blank" rel="noopener noreferrer"
          className="text-white/60 hover:text-white text-xs underline"
        >
          Open original in new tab
        </a>
      </div>
    </div>
  );
}

// ── Single attachment thumbnail ───────────────────────────────────────────────

function AttachmentThumb({
  att, canDelete, compact, onDelete,
}: {
  att: Attachment;
  canDelete: boolean;
  compact: boolean;
  onDelete: (id: string) => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [lightbox, setLightbox] = useState(false);

  const size = compact ? "h-14 w-14" : "h-20 w-20";

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Remove "${att.file_name}"?`)) return;
    setDeleting(true);
    try {
      await attachmentsApi.delete(att.id);
      onDelete(att.id);
    } catch {
      setDeleting(false);
    }
  };

  const typeLabel = ATTACHMENT_TYPE_LABELS[att.attachment_type] ?? att.attachment_type;

  return (
    <>
      <div
        className="relative group shrink-0"
        title={`${att.file_name} · ${typeLabel}${att.uploaded_by_name ? ` · ${att.uploaded_by_name}` : ""}`}
      >
        {att.is_image ? (
          <img
            src={att.download_url}
            alt={att.file_name}
            className={cn(
              "rounded-lg object-cover border border-border cursor-zoom-in hover:opacity-85 transition-opacity",
              size
            )}
            onClick={() => setLightbox(true)}
            onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        ) : (
          <a
            href={att.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "rounded-lg border border-border bg-muted/50 flex flex-col items-center justify-center",
              "hover:bg-muted transition-colors cursor-pointer gap-1",
              size
            )}
          >
            <FileText className="w-6 h-6 text-muted-foreground" />
            <span className="text-[9px] text-muted-foreground text-center leading-tight px-1 truncate max-w-full">
              {att.file_name.split(".").pop()?.toUpperCase() ?? "FILE"}
            </span>
          </a>
        )}

        {/* Size badge */}
        <span className="absolute bottom-0.5 left-0.5 bg-black/50 text-white rounded text-[8px] px-1 py-0.5 leading-none select-none">
          {att.file_size_display}
        </span>

        {/* Type badge (non-compact only) */}
        {!compact && att.attachment_type !== "PHOTO" && (
          <span className="absolute top-0.5 left-0.5 bg-primary/80 text-white rounded text-[8px] px-1 py-0.5 leading-none select-none max-w-[90%] truncate">
            {typeLabel.split(" ")[0]}
          </span>
        )}

        {/* Delete button */}
        {canDelete && (
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-destructive text-white
                       flex items-center justify-center opacity-0 group-hover:opacity-100
                       transition-opacity disabled:opacity-50 z-10"
            title="Remove"
          >
            {deleting
              ? <RefreshCw className="w-2.5 h-2.5 animate-spin" />
              : <XIcon className="w-2.5 h-2.5" />}
          </button>
        )}

        {/* View overlay on hover for images */}
        {att.is_image && (
          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none rounded-lg">
            <Eye className="w-5 h-5 text-white drop-shadow-lg" />
          </div>
        )}
      </div>

      {lightbox && <Lightbox att={att} onClose={() => setLightbox(false)} />}
    </>
  );
}

// ── Upload progress indicator ─────────────────────────────────────────────────

interface UploadState {
  name: string;
  done: boolean;
  error: boolean;
}

// ── Main component ────────────────────────────────────────────────────────────

export interface AttachmentStripProps {
  entityType:        AttachmentEntity;
  entityId:          string;
  attachmentType?:   AttachmentType;
  accept?:           string;
  label?:            string;
  canWrite?:         boolean;
  compact?:          boolean;
  showTypeSelector?: boolean;   // show category dropdown on upload
  maxFiles?:         number;    // max total files (0 = unlimited)
  className?:        string;
}

export function AttachmentStrip({
  entityType,
  entityId,
  attachmentType = "PHOTO",
  accept = "image/*,application/pdf",
  label,
  canWrite,
  compact = false,
  showTypeSelector = false,
  maxFiles = 0,
  className,
}: AttachmentStripProps) {
  const userRole = localStorage.getItem(ROLE_KEY) || "";
  const isReadOnly = userRole === "READ_ONLY";
  // Office/admin can delete; site users can only upload
  const canDelete  = canWrite ?? (!isReadOnly && !["SITE_STAFF", "SITE_MANAGER"].includes(userRole));
  const canUpload  = canWrite ?? !isReadOnly;

  const fileRef = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [loading,     setLoading]     = useState(false);
  const [uploads,     setUploads]     = useState<UploadState[]>([]);
  const [selType,     setSelType]     = useState<AttachmentType>(attachmentType);

  const load = useCallback(async () => {
    if (!entityId) return;
    setLoading(true);
    try {
      const list = await attachmentsApi.listByEntity(entityType, entityId);
      setAttachments(list.filter(a => a.is_active));
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [entityType, entityId]);

  useEffect(() => { load(); }, [load]);

  // Check if at max capacity
  const atMax = maxFiles > 0 && attachments.length >= maxFiles;

  const handleUpload = async (files: File[]) => {
    if (!entityId || atMax) return;

    const newUploads: UploadState[] = files.map(f => ({ name: f.name, done: false, error: false }));
    setUploads(newUploads);

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        const att = await attachmentsApi.upload(file, entityType, entityId, selType);
        setAttachments(prev => [att, ...prev]);
        setUploads(prev => prev.map((u, idx) => idx === i ? { ...u, done: true } : u));
      } catch {
        setUploads(prev => prev.map((u, idx) => idx === i ? { ...u, error: true } : u));
      }
    }

    // Clear upload indicators after a moment
    setTimeout(() => setUploads([]), 2500);
  };

  const handleDelete = (id: string) => {
    setAttachments(prev => prev.filter(a => a.id !== id));
  };

  const isUploading = uploads.some(u => !u.done && !u.error);
  const thumbSize   = compact ? "h-14 w-14" : "h-20 w-20";

  return (
    <div className={cn("space-y-2", className)}>
      {/* Header */}
      {label && (
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
          <Camera className="w-3.5 h-3.5" />
          {label}
          {attachments.length > 0 && (
            <span className="text-primary font-bold">{attachments.length}</span>
          )}
        </p>
      )}

      {/* Type selector (optional) */}
      {showTypeSelector && canUpload && (
        <select
          value={selType}
          onChange={e => setSelType(e.target.value as AttachmentType)}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs min-w-[160px]"
        >
          {(Object.entries(ATTACHMENT_TYPE_LABELS) as [AttachmentType, string][]).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      )}

      {/* Upload progress */}
      {uploads.length > 0 && (
        <div className="text-xs text-muted-foreground flex flex-wrap gap-1.5">
          {uploads.map((u, i) => (
            <span key={i} className={cn(
              "flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]",
              u.error ? "bg-destructive/10 text-destructive"
              : u.done  ? "bg-green-100 text-green-700 dark:bg-green-950/30 dark:text-green-400"
              :           "bg-muted text-muted-foreground"
            )}>
              {u.error  ? "✗" : u.done ? "✓" : <RefreshCw className="w-2.5 h-2.5 animate-spin" />}
              {u.name.length > 16 ? `${u.name.slice(0, 14)}…` : u.name}
            </span>
          ))}
        </div>
      )}

      {/* Gallery grid */}
      {loading ? (
        <div className="flex gap-2">
          {[1, 2].map(i => (
            <div key={i} className={cn("rounded-lg bg-muted animate-pulse shrink-0", thumbSize)} />
          ))}
        </div>
      ) : (
        <div className="flex items-start gap-2 flex-wrap">
          {attachments.map(att => (
            <AttachmentThumb
              key={att.id}
              att={att}
              canDelete={canDelete}
              compact={compact}
              onDelete={handleDelete}
            />
          ))}

          {/* Upload button */}
          {canUpload && !atMax && (
            <button
              onClick={() => fileRef.current?.click()}
              disabled={isUploading}
              className={cn(
                "rounded-lg border-2 border-dashed border-border flex flex-col items-center justify-center",
                "hover:border-primary hover:bg-muted/40 transition-colors text-muted-foreground hover:text-primary shrink-0",
                isUploading && "opacity-50 pointer-events-none",
                thumbSize,
              )}
              title={atMax ? `Maximum ${maxFiles} files reached` : "Upload file"}
            >
              {isUploading
                ? <RefreshCw className="w-4 h-4 animate-spin" />
                : <>
                    <Upload className="w-4 h-4 mb-0.5" />
                    <span className="text-[9px] leading-tight text-center">
                      {compact ? "+" : "Upload"}
                    </span>
                  </>}
            </button>
          )}

          {/* Empty state */}
          {attachments.length === 0 && !canUpload && (
            <p className="text-xs text-muted-foreground italic">No attachments.</p>
          )}

          {/* Max reached note */}
          {atMax && (
            <p className="text-[10px] text-muted-foreground self-center">
              Max {maxFiles} files
            </p>
          )}
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        accept={accept}
        multiple
        className="sr-only"
        onChange={async e => {
          const files = Array.from(e.target.files ?? []);
          if (files.length > 0) await handleUpload(files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
