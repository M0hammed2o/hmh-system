/**
 * AttachmentGallery — enhanced gallery with grid, lightbox, category chips,
 * caption support, and strip-preview (first 3 + "+X more").
 *
 * Phase FINAL-2: Used by MilestonesPage (with BEFORE/COMPLETION/ISSUE chips)
 * and DeliveriesPage (with DELIVERY_EVIDENCE category).
 *
 * Features:
 *   - Category filter chips (configurable per use-site)
 *   - Grid layout (thumbnails sized 80px)
 *   - Full lightbox: prev/next navigation, keyboard (←/→/Esc), caption, uploader
 *   - Strip preview mode: first 3 thumbnails + "+X more" chip
 *   - Upload zone with type pre-selected from active chip
 *   - Caption input field on upload (optional)
 *   - Loading skeleton placeholders
 *   - Empty state message
 *   - SITE_STAFF own-delete handled server-side (client shows delete button for own uploads)
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Camera, ChevronLeft, ChevronRight, FileText, RefreshCw,
  Upload, X as XIcon, Eye, User, Images,
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

// ── Category chip config ──────────────────────────────────────────────────────

export interface GalleryCategory {
  value: AttachmentType | "ALL";
  label: string;
}

// ── Lightbox ──────────────────────────────────────────────────────────────────

interface LightboxProps {
  images:   Attachment[];
  index:    number;
  onClose:  () => void;
  onChange: (idx: number) => void;
}

function GalleryLightbox({ images, index, onClose, onChange }: LightboxProps) {
  const att     = images[index];
  const hasPrev = index > 0;
  const hasNext = index < images.length - 1;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape")     onClose();
      if (e.key === "ArrowLeft"  && hasPrev) onChange(index - 1);
      if (e.key === "ArrowRight" && hasNext) onChange(index + 1);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [index, hasPrev, hasNext, onClose, onChange]);

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/90 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Close */}
      <button
        className="absolute top-4 right-4 p-2 rounded-full bg-black/50 text-white/80 hover:text-white z-10"
        onClick={onClose}
      >
        <XIcon className="w-5 h-5" />
      </button>

      {/* Prev */}
      {hasPrev && (
        <button
          className="absolute left-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black/50 text-white/80 hover:text-white z-10"
          onClick={e => { e.stopPropagation(); onChange(index - 1); }}
        >
          <ChevronLeft className="w-6 h-6" />
        </button>
      )}

      {/* Next */}
      {hasNext && (
        <button
          className="absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black/50 text-white/80 hover:text-white z-10"
          onClick={e => { e.stopPropagation(); onChange(index + 1); }}
        >
          <ChevronRight className="w-6 h-6" />
        </button>
      )}

      {/* Image */}
      <img
        src={att.download_url}
        alt={att.caption ?? att.file_name}
        className="max-h-[90vh] max-w-[90vw] rounded-xl shadow-2xl object-contain"
        onClick={e => e.stopPropagation()}
      />

      {/* Footer */}
      <div
        className="absolute bottom-4 left-0 right-0 flex flex-col items-center gap-1.5 px-8"
        onClick={e => e.stopPropagation()}
      >
        {images.length > 1 && (
          <p className="text-white/50 text-xs">{index + 1} / {images.length}</p>
        )}
        {att.caption && (
          <p className="text-white text-sm font-semibold text-center max-w-lg">{att.caption}</p>
        )}
        <p className="text-white/60 text-xs">
          {ATTACHMENT_TYPE_LABELS[att.attachment_type] ?? att.attachment_type}
        </p>
        {att.uploaded_by_name && (
          <p className="text-white/50 text-xs flex items-center gap-1">
            <User className="w-3 h-3" />
            {att.uploaded_by_name}
            {att.uploaded_at && ` · ${new Date(att.uploaded_at).toLocaleDateString("en-ZA")}`}
          </p>
        )}
        <a
          href={att.download_url} target="_blank" rel="noopener noreferrer"
          className="text-white/40 hover:text-white text-xs underline mt-0.5"
        >
          Open original
        </a>
      </div>
    </div>
  );
}

// ── Single thumbnail ──────────────────────────────────────────────────────────

function GalleryThumb({
  att, canDelete, onDelete, onOpen, size = "h-20 w-20",
}: {
  att:       Attachment;
  canDelete: boolean;
  onDelete:  (id: string) => void;
  onOpen?:   () => void;
  size?:     string;
}) {
  const [deleting, setDeleting] = useState(false);
  const typeLabel = ATTACHMENT_TYPE_LABELS[att.attachment_type] ?? att.attachment_type;

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Remove "${att.caption ?? att.file_name}"?`)) return;
    setDeleting(true);
    try {
      await attachmentsApi.delete(att.id);
      onDelete(att.id);
    } catch {
      setDeleting(false);
    }
  };

  return (
    <div
      className="relative group shrink-0"
      title={`${att.file_name}${att.caption ? ` · ${att.caption}` : ""} · ${typeLabel}`}
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
          onClick={onOpen}
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

      {/* Type badge */}
      {att.attachment_type !== "PHOTO" && att.attachment_type !== "BEFORE_PHOTO" && (
        <span className="absolute top-0.5 left-0.5 bg-primary/80 text-white rounded text-[8px] px-1 py-0.5 leading-none select-none max-w-[90%] truncate">
          {typeLabel.split(" ")[0]}
        </span>
      )}

      {/* Delete */}
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

      {/* View overlay */}
      {att.is_image && (
        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none rounded-lg">
          <Eye className="w-5 h-5 text-white drop-shadow-lg" />
        </div>
      )}
    </div>
  );
}

// ── Upload row ────────────────────────────────────────────────────────────────

interface UploadState {
  name:  string;
  done:  boolean;
  error: boolean;
}

// ── Main component ────────────────────────────────────────────────────────────

export interface AttachmentGalleryProps {
  entityType:        AttachmentEntity;
  entityId:          string;
  label?:            string;
  canWrite?:         boolean;
  /** Category filter chips. When provided, adds chip bar above gallery. */
  categories?:       GalleryCategory[];
  /** Default attachment type used on upload (overridden by active category chip). */
  defaultType?:      AttachmentType;
  /** Show upload caption input. Default false. */
  showCaptionInput?: boolean;
  /** Strip preview mode: show first N thumbs + "+X more" chip, expand on click. */
  previewCount?:     number;
  className?:        string;
}

export function AttachmentGallery({
  entityType,
  entityId,
  label,
  canWrite,
  categories,
  defaultType = "PHOTO",
  showCaptionInput = false,
  previewCount,
  className,
}: AttachmentGalleryProps) {
  const userRole    = localStorage.getItem(ROLE_KEY) || "";
  const isReadOnly  = userRole === "READ_ONLY";

  const canUpload    = canWrite ?? !isReadOnly;
  // SITE_STAFF can attempt delete (server enforces own-only via 403);
  // SITE_MANAGER and READ_ONLY cannot delete
  const canDeleteAny = canWrite ?? (!isReadOnly && userRole !== "SITE_MANAGER");

  const fileRef = useRef<HTMLInputElement>(null);
  const [attachments,  setAttachments]  = useState<Attachment[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [uploads,      setUploads]      = useState<UploadState[]>([]);
  const [lightboxIdx,  setLightboxIdx]  = useState<number | null>(null);
  const [activeChip,   setActiveChip]   = useState<AttachmentType | "ALL">("ALL");
  const [caption,      setCaption]      = useState("");
  const [expanded,     setExpanded]     = useState(!previewCount);

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

  // Derive upload type from active chip
  const uploadType: AttachmentType =
    activeChip !== "ALL" ? activeChip : defaultType;

  // Filtered view
  const filtered = activeChip === "ALL"
    ? attachments
    : attachments.filter(a => a.attachment_type === activeChip);

  // Strip preview: show first N or all
  const displayed = previewCount && !expanded
    ? filtered.slice(0, previewCount)
    : filtered;

  // Only images participate in lightbox
  const imageAttachments = filtered.filter(a => a.is_image);

  const handleUpload = async (files: File[]) => {
    if (!entityId) return;
    const newUploads: UploadState[] = files.map(f => ({ name: f.name, done: false, error: false }));
    setUploads(newUploads);

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        const att = await attachmentsApi.upload(
          file, entityType, entityId, uploadType, caption || undefined
        );
        setAttachments(prev => [att, ...prev]);
        setUploads(prev => prev.map((u, idx) => idx === i ? { ...u, done: true } : u));
      } catch {
        setUploads(prev => prev.map((u, idx) => idx === i ? { ...u, error: true } : u));
      }
    }

    setCaption("");
    setTimeout(() => setUploads([]), 2500);
  };

  const handleDelete = (id: string) => {
    setAttachments(prev => prev.filter(a => a.id !== id));
  };

  const isUploading = uploads.some(u => !u.done && !u.error);

  // Determine if a given attachment can be deleted by the current user
  const canDeleteAtt = (_att: Attachment) => canDeleteAny;

  return (
    <div className={cn("space-y-3", className)}>
      {/* Header */}
      {label && (
        <div className="flex items-center gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
            <Images className="w-3.5 h-3.5" />
            {label}
          </p>
          {attachments.length > 0 && (
            <span className="text-xs font-bold text-primary">{attachments.length}</span>
          )}
        </div>
      )}

      {/* Category chips */}
      {categories && categories.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {categories.map(c => (
            <button
              key={c.value}
              onClick={() => setActiveChip(c.value)}
              className={cn(
                "px-2.5 py-1 rounded-full text-xs font-medium transition-colors",
                activeChip === c.value
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              )}
            >
              {c.label}
              {c.value !== "ALL" && (
                <span className="ml-1 opacity-70">
                  ({attachments.filter(a => a.attachment_type === c.value).length})
                </span>
              )}
              {c.value === "ALL" && (
                <span className="ml-1 opacity-70">({attachments.length})</span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Caption input (shown above upload button when enabled) */}
      {showCaptionInput && canUpload && (
        <input
          type="text"
          value={caption}
          onChange={e => setCaption(e.target.value)}
          placeholder="Caption for next upload (optional)"
          className="w-full h-8 rounded-md border border-input bg-background px-3 text-xs"
          maxLength={500}
        />
      )}

      {/* Upload progress */}
      {uploads.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
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

      {/* Grid */}
      {loading ? (
        <div className="flex gap-2 flex-wrap">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-20 w-20 rounded-lg bg-muted animate-pulse shrink-0" />
          ))}
        </div>
      ) : (
        <div className="flex items-start gap-2 flex-wrap">
          {displayed.map(att => {
            const imgIdx = att.is_image ? imageAttachments.indexOf(att) : -1;
            return (
              <GalleryThumb
                key={att.id}
                att={att}
                canDelete={canDeleteAtt(att)}
                onDelete={handleDelete}
                onOpen={att.is_image ? () => setLightboxIdx(imgIdx) : undefined}
              />
            );
          })}

          {/* "+X more" chip */}
          {previewCount && !expanded && filtered.length > previewCount && (
            <button
              onClick={() => setExpanded(true)}
              className="h-20 w-20 rounded-lg border-2 border-dashed border-border flex flex-col items-center justify-center text-muted-foreground hover:border-primary hover:text-primary transition-colors shrink-0"
            >
              <span className="text-sm font-semibold">+{filtered.length - previewCount}</span>
              <span className="text-[9px]">more</span>
            </button>
          )}

          {/* Upload button */}
          {canUpload && (
            <button
              onClick={() => fileRef.current?.click()}
              disabled={isUploading}
              className={cn(
                "h-20 w-20 rounded-lg border-2 border-dashed border-border flex flex-col items-center justify-center",
                "hover:border-primary hover:bg-muted/40 transition-colors text-muted-foreground hover:text-primary shrink-0",
                isUploading && "opacity-50 pointer-events-none"
              )}
              title="Upload file"
            >
              {isUploading
                ? <RefreshCw className="w-4 h-4 animate-spin" />
                : <>
                    <Upload className="w-4 h-4 mb-0.5" />
                    <span className="text-[9px] leading-tight text-center">
                      {categories && activeChip !== "ALL"
                        ? categories.find(c => c.value === activeChip)?.label.split(" ")[0]
                        : "Upload"}
                    </span>
                  </>}
            </button>
          )}

          {/* Empty state */}
          {filtered.length === 0 && !canUpload && (
            <p className="text-xs text-muted-foreground italic">No attachments.</p>
          )}
          {filtered.length === 0 && canUpload && !isUploading && (
            <p className="text-xs text-muted-foreground self-center">
              <Camera className="w-3 h-3 inline mr-1" />
              Tap upload to add photos
            </p>
          )}
        </div>
      )}

      {/* Collapse link when expanded from preview */}
      {previewCount && expanded && filtered.length > previewCount && (
        <button
          onClick={() => setExpanded(false)}
          className="text-xs text-muted-foreground hover:text-foreground underline"
        >
          Show less
        </button>
      )}

      {/* Lightbox */}
      {lightboxIdx !== null && imageAttachments.length > 0 && (
        <GalleryLightbox
          images={imageAttachments}
          index={lightboxIdx}
          onClose={() => setLightboxIdx(null)}
          onChange={setLightboxIdx}
        />
      )}

      <input
        ref={fileRef}
        type="file"
        accept="image/*,application/pdf"
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
