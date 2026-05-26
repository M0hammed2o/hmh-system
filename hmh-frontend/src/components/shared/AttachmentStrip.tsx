/**
 * AttachmentStrip — universal reusable attachment gallery.
 *
 * Phase 3K / FINAL-2.5 hardened:
 *   - Prev/next lightbox navigation with keyboard (←/→/Esc) and touch swipe
 *   - Body scroll lock when lightbox is open
 *   - Upload guard ref — prevents duplicate submissions
 *   - Client-side file validation (size + MIME) with error feedback
 *   - caption display in lightbox footer
 *   - compact mode for inline/table use
 *
 * Used by:
 *   Payments, Fuel Logs, Procurement (MR + PO),
 *   Project Warehouse, Suppliers, Lots, Projects
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Camera, FileText, RefreshCw, X as XIcon, Upload, Eye, User,
  ChevronLeft, ChevronRight, AlertCircle,
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

// ── File validation ───────────────────────────────────────────────────────────

const MAX_FILE_MB = 5;  // must match backend settings.MAX_UPLOAD_SIZE_MB

const ALLOWED_MIME_TYPES = new Set([
  "image/jpeg", "image/png", "image/webp", "image/gif",
  "image/heic", "image/heif",
  "application/pdf",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/csv", "text/plain",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

function validateFile(file: File): string | null {
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    return `"${file.name}" is too large (max ${MAX_FILE_MB} MB)`;
  }
  if (file.type && !ALLOWED_MIME_TYPES.has(file.type)) {
    return `"${file.name}" — unsupported type (${file.type})`;
  }
  return null;
}

// ── Lightbox ──────────────────────────────────────────────────────────────────

interface LightboxProps {
  images:   Attachment[];
  index:    number;
  onClose:  () => void;
  onChange: (idx: number) => void;
}

function Lightbox({ images, index, onClose, onChange }: LightboxProps) {
  const att     = images[index];
  const hasPrev = index > 0;
  const hasNext = index < images.length - 1;
  const touchX  = useRef<number | null>(null);

  // Prevent body scroll bleed-through (critical on iOS Safari)
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape")                onClose();
      if (e.key === "ArrowLeft"  && hasPrev) onChange(index - 1);
      if (e.key === "ArrowRight" && hasNext) onChange(index + 1);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [index, hasPrev, hasNext, onClose, onChange]);

  // Touch swipe
  const onTouchStart = (e: React.TouchEvent) => {
    touchX.current = e.touches[0].clientX;
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchX.current === null) return;
    const dx = e.changedTouches[0].clientX - touchX.current;
    touchX.current = null;
    if (dx >  50 && hasPrev) onChange(index - 1);
    if (dx < -50 && hasNext) onChange(index + 1);
  };

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/88 backdrop-blur-sm overscroll-contain"
      style={{ touchAction: "pan-y" }}
      onClick={onClose}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      {/* Close */}
      <button
        className="absolute top-3 right-3 p-3 rounded-full bg-black/50 text-white/80 hover:text-white min-w-[44px] min-h-[44px] flex items-center justify-center"
        onClick={onClose}
        aria-label="Close"
      >
        <XIcon className="w-5 h-5" />
      </button>

      {hasPrev && (
        <button
          className="absolute left-2 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black/50 text-white/80 hover:text-white min-w-[44px] min-h-[44px] flex items-center justify-center"
          onClick={e => { e.stopPropagation(); onChange(index - 1); }}
          aria-label="Previous image"
        >
          <ChevronLeft className="w-6 h-6" />
        </button>
      )}

      {hasNext && (
        <button
          className="absolute right-2 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black/50 text-white/80 hover:text-white min-w-[44px] min-h-[44px] flex items-center justify-center"
          onClick={e => { e.stopPropagation(); onChange(index + 1); }}
          aria-label="Next image"
        >
          <ChevronRight className="w-6 h-6" />
        </button>
      )}

      <img
        key={att.id}
        src={att.download_url}
        alt={att.caption ?? att.file_name}
        className="max-h-[85vh] max-w-[92vw] rounded-xl shadow-2xl object-contain select-none"
        draggable={false}
        onClick={e => e.stopPropagation()}
      />

      <div
        className="absolute bottom-3 left-0 right-0 flex flex-col items-center gap-1 px-6"
        onClick={e => e.stopPropagation()}
      >
        {images.length > 1 && (
          <p className="text-white/50 text-xs">{index + 1} / {images.length}</p>
        )}
        {att.caption && (
          <p className="text-white/90 text-sm font-medium text-center max-w-sm leading-snug">{att.caption}</p>
        )}
        {att.uploaded_by_name && (
          <p className="text-white/60 text-xs flex items-center gap-1">
            <User className="w-3 h-3" />
            {att.uploaded_by_name}
            {att.uploaded_at && ` · ${new Date(att.uploaded_at).toLocaleDateString("en-ZA")}`}
          </p>
        )}
        <a
          href={att.download_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-white/60 hover:text-white text-xs underline"
          onClick={e => e.stopPropagation()}
        >
          Open original in new tab
        </a>
      </div>
    </div>
  );
}

// ── Single attachment thumbnail ───────────────────────────────────────────────

function AttachmentThumb({
  att, canDelete, compact, onDelete, onOpenLightbox,
}: {
  att:             Attachment;
  canDelete:       boolean;
  compact:         boolean;
  onDelete:        (id: string) => void;
  onOpenLightbox?: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const size = compact ? "h-14 w-14" : "h-20 w-20";

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Remove "${att.file_name}"?`)) return;
    setDeleting(true);
    try {
      await attachmentsApi.delete(att.id);
      onDelete(att.id);
    } catch (err: unknown) {
      setDeleting(false);
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (msg) alert(msg);
    }
  };

  const typeLabel = ATTACHMENT_TYPE_LABELS[att.attachment_type] ?? att.attachment_type;

  return (
    <div
      className="relative group shrink-0"
      title={`${att.file_name} · ${typeLabel}${att.uploaded_by_name ? ` · ${att.uploaded_by_name}` : ""}${att.caption ? ` · ${att.caption}` : ""}`}
    >
      {att.is_image ? (
        <img
          src={att.download_url}
          alt={att.caption ?? att.file_name}
          loading="lazy"
          decoding="async"
          className={cn(
            "rounded-lg object-cover border border-border cursor-zoom-in hover:opacity-85 transition-opacity",
            size
          )}
          onClick={onOpenLightbox}
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
          className="absolute -top-1.5 -right-1.5 w-6 h-6 rounded-full bg-destructive text-white
                     flex items-center justify-center opacity-0 group-hover:opacity-100 focus:opacity-100
                     transition-opacity disabled:opacity-50 z-10"
          title="Remove"
        >
          {deleting
            ? <RefreshCw className="w-2.5 h-2.5 animate-spin" />
            : <XIcon className="w-2.5 h-2.5" />}
        </button>
      )}

      {/* View overlay on hover for images (desktop only) */}
      {att.is_image && (
        <div className="hidden sm:flex absolute inset-0 items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none rounded-lg">
          <Eye className="w-5 h-5 text-white drop-shadow-lg" />
        </div>
      )}
    </div>
  );
}

// ── Upload state ──────────────────────────────────────────────────────────────

interface UploadItem {
  name:   string;
  done:   boolean;
  error:  boolean;
  errMsg: string;
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
  showTypeSelector?: boolean;
  maxFiles?:         number;
  className?:        string;
}

export function AttachmentStrip({
  entityType,
  entityId,
  attachmentType = "PHOTO",
  accept = "image/*,application/pdf,.csv,.xlsx,.xls,.doc,.docx",
  label,
  canWrite,
  compact = false,
  showTypeSelector = false,
  maxFiles = 0,
  className,
}: AttachmentStripProps) {
  const userRole   = localStorage.getItem(ROLE_KEY) || "";
  const isReadOnly = userRole === "READ_ONLY";
  const canDelete  = canWrite ?? (!isReadOnly && !["SITE_STAFF", "SITE_MANAGER"].includes(userRole));
  const canUpload  = canWrite ?? !isReadOnly;

  const fileRef      = useRef<HTMLInputElement>(null);
  const uploadingRef = useRef(false);  // prevents duplicate submissions

  const [attachments,      setAttachments]      = useState<Attachment[]>([]);
  const [loading,          setLoading]          = useState(false);
  const [uploads,          setUploads]          = useState<UploadItem[]>([]);
  const [selType,          setSelType]          = useState<AttachmentType>(attachmentType);
  const [lightboxIdx,      setLightboxIdx]      = useState<number | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

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

  const atMax = maxFiles > 0 && attachments.length >= maxFiles;

  const handleUpload = async (files: File[]) => {
    if (!entityId || atMax || uploadingRef.current) return;

    // Client-side validation
    const errors: string[] = [];
    const valid: File[] = [];
    for (const f of files) {
      const err = validateFile(f);
      if (err) errors.push(err);
      else valid.push(f);
    }
    setValidationErrors(errors);
    if (valid.length === 0) return;

    uploadingRef.current = true;
    const newItems: UploadItem[] = valid.map(f => ({ name: f.name, done: false, error: false, errMsg: "" }));
    setUploads(newItems);

    for (let i = 0; i < valid.length; i++) {
      const file = valid[i];
      try {
        const att = await attachmentsApi.upload(file, entityType, entityId, selType);
        setAttachments(prev => [att, ...prev]);
        setUploads(prev => prev.map((u, idx) => idx === i ? { ...u, done: true } : u));
      } catch (err: unknown) {
        const detail =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          ?? "Upload failed";
        setUploads(prev => prev.map((u, idx) =>
          idx === i ? { ...u, error: true, errMsg: detail } : u
        ));
      }
    }

    uploadingRef.current = false;
    setTimeout(() => setUploads([]), 3000);
  };

  const handleDelete = (id: string) => {
    setAttachments(prev => prev.filter(a => a.id !== id));
  };

  const isUploading = uploads.some(u => !u.done && !u.error);
  const thumbSize   = compact ? "h-14 w-14" : "h-20 w-20";
  const imageAttachments = attachments.filter(a => a.is_image);

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

      {/* Type selector */}
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

      {/* Client-side validation errors */}
      {validationErrors.length > 0 && (
        <div className="space-y-0.5">
          {validationErrors.map((e, i) => (
            <p key={i} className="text-xs text-destructive flex items-start gap-1">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              {e}
            </p>
          ))}
        </div>
      )}

      {/* Upload progress */}
      {uploads.length > 0 && (
        <div className="text-xs text-muted-foreground flex flex-wrap gap-1.5">
          {uploads.map((u, i) => (
            <span
              key={i}
              className={cn(
                "flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]",
                u.error ? "bg-destructive/10 text-destructive"
                : u.done  ? "bg-green-100 text-green-700 dark:bg-green-950/30 dark:text-green-400"
                :           "bg-muted text-muted-foreground"
              )}
              title={u.error ? u.errMsg : undefined}
            >
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
          {attachments.map(att => {
            const imgIdx = att.is_image ? imageAttachments.indexOf(att) : -1;
            return (
              <AttachmentThumb
                key={att.id}
                att={att}
                canDelete={canDelete}
                compact={compact}
                onDelete={handleDelete}
                onOpenLightbox={att.is_image ? () => setLightboxIdx(imgIdx) : undefined}
              />
            );
          })}

          {/* Upload button */}
          {canUpload && !atMax && (
            <button
              onClick={() => {
                setValidationErrors([]);
                fileRef.current?.click();
              }}
              disabled={isUploading}
              className={cn(
                "rounded-lg border-2 border-dashed border-border flex flex-col items-center justify-center",
                "hover:border-primary hover:bg-muted/40 transition-colors text-muted-foreground hover:text-primary shrink-0",
                "disabled:opacity-40 disabled:pointer-events-none",
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

          {attachments.length === 0 && !canUpload && (
            <p className="text-xs text-muted-foreground italic">No attachments.</p>
          )}

          {atMax && (
            <p className="text-[10px] text-muted-foreground self-center">
              Max {maxFiles} files
            </p>
          )}
        </div>
      )}

      {/* Lightbox */}
      {lightboxIdx !== null && imageAttachments.length > 0 && (
        <Lightbox
          images={imageAttachments}
          index={lightboxIdx}
          onClose={() => setLightboxIdx(null)}
          onChange={setLightboxIdx}
        />
      )}

      <input
        ref={fileRef}
        type="file"
        accept={accept}
        multiple
        className="sr-only"
        onChange={async e => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";       // reset before async so re-select works
          if (files.length > 0) await handleUpload(files);
        }}
      />
    </div>
  );
}
