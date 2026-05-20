/**
 * AttachmentStrip — reusable multi-file photo/document strip.
 *
 * Used by Deliveries, Payments, Fuel Logs, and anywhere else an entity
 * can have multiple uploaded files.
 *
 * Features:
 *  - Auto-loads attachments when entityId changes
 *  - Upload button (file input, hidden)
 *  - Image thumbnails + click to open lightbox
 *  - Non-image files shown as a document badge
 *  - Soft-delete with ×
 *  - READ_ONLY users see attachments but cannot upload/delete
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, FileText, RefreshCw, X as XIcon, Upload, Eye } from "lucide-react";
import { attachmentsApi, type Attachment, type AttachmentEntity, type AttachmentType } from "@/api/attachments";
import { ROLE_KEY } from "@/lib/constants";
import { cn } from "@/lib/utils";

// ── Lightbox ──────────────────────────────────────────────────────────────────

function Lightbox({ url, name, onClose }: { url: string; name: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/85 backdrop-blur-sm"
      onClick={onClose}
    >
      <button
        className="absolute top-4 right-4 p-2 rounded-full bg-black/50 text-white/80 hover:text-white"
        onClick={onClose}
      >
        <XIcon className="w-5 h-5" />
      </button>
      <img
        src={url}
        alt={name}
        className="max-h-[90vh] max-w-[90vw] rounded-xl shadow-2xl object-contain"
        onClick={e => e.stopPropagation()}
      />
      <a
        href={url} target="_blank" rel="noopener noreferrer"
        className="absolute bottom-4 text-white/60 hover:text-white text-xs underline"
        onClick={e => e.stopPropagation()}
      >
        Open original in new tab
      </a>
    </div>
  );
}

// ── Thumbnail ─────────────────────────────────────────────────────────────────

function AttachmentThumb({
  att, canDelete, onDelete,
}: {
  att: Attachment;
  canDelete: boolean;
  onDelete: (id: string) => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [lightbox, setLightbox] = useState(false);

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleting(true);
    try {
      await attachmentsApi.delete(att.id);
      onDelete(att.id);
    } catch {
      setDeleting(false);
    }
  };

  return (
    <>
      <div className="relative group shrink-0">
        {att.is_image ? (
          <img
            src={att.download_url}
            alt={att.file_name}
            className="h-20 w-20 rounded-lg object-cover border border-border cursor-zoom-in
                       hover:opacity-85 transition-opacity"
            onClick={() => setLightbox(true)}
            onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        ) : (
          <a
            href={att.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="h-20 w-20 rounded-lg border border-border bg-muted/50 flex flex-col
                       items-center justify-center hover:bg-muted transition-colors cursor-pointer gap-1"
          >
            <FileText className="w-6 h-6 text-muted-foreground" />
            <span className="text-[9px] text-muted-foreground text-center leading-tight px-1 truncate max-w-full">
              {att.file_name}
            </span>
          </a>
        )}

        {/* Size badge */}
        <span className="absolute bottom-0.5 left-0.5 bg-black/50 text-white rounded text-[8px] px-1 py-0.5 leading-none">
          {att.file_size_display}
        </span>

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

        {/* View button for non-images on hover */}
        {att.is_image && (
          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none rounded-lg">
            <Eye className="w-5 h-5 text-white drop-shadow-lg" />
          </div>
        )}
      </div>

      {lightbox && (
        <Lightbox url={att.download_url} name={att.file_name} onClose={() => setLightbox(false)} />
      )}
    </>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface AttachmentStripProps {
  entityType:     AttachmentEntity;
  entityId:       string;               // must be truthy to load/upload
  attachmentType?: AttachmentType;       // default: "PHOTO"
  accept?:         string;               // default: "image/*,application/pdf"
  label?:          string;               // section heading
  canWrite?:       boolean;              // override — defaults to !READ_ONLY
  compact?:        boolean;              // 14×14 thumbs instead of 20×20
  className?:      string;
}

export function AttachmentStrip({
  entityType,
  entityId,
  attachmentType = "PHOTO",
  accept = "image/*,application/pdf",
  label,
  canWrite,
  compact = false,
  className,
}: AttachmentStripProps) {
  const defaultCanWrite = localStorage.getItem(ROLE_KEY) !== "READ_ONLY";
  const writeEnabled = canWrite ?? defaultCanWrite;

  const fileRef = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [loading,     setLoading]     = useState(false);
  const [uploading,   setUploading]   = useState(false);

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

  const handleUpload = async (file: File) => {
    if (!entityId) return;
    setUploading(true);
    try {
      const att = await attachmentsApi.upload(file, entityType, entityId, attachmentType);
      setAttachments(prev => [att, ...prev]);
    } catch { /* keep existing state */ }
    finally { setUploading(false); }
  };

  const handleDelete = (id: string) => {
    setAttachments(prev => prev.filter(a => a.id !== id));
  };

  const thumbSize = compact ? "h-14 w-14" : "h-20 w-20";

  return (
    <div className={cn("space-y-2", className)}>
      {label && (
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
          <Camera className="w-3.5 h-3.5" />
          {label}
          {attachments.length > 0 && (
            <span className="text-primary font-bold">{attachments.length}</span>
          )}
        </p>
      )}

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
              canDelete={writeEnabled}
              onDelete={handleDelete}
            />
          ))}

          {/* Upload button */}
          {writeEnabled && (
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className={cn(
                "rounded-lg border-2 border-dashed border-border flex flex-col items-center justify-center",
                "hover:border-primary hover:bg-muted/40 transition-colors text-muted-foreground hover:text-primary shrink-0",
                uploading && "opacity-50 pointer-events-none",
                thumbSize,
              )}
              title="Upload file"
            >
              {uploading
                ? <RefreshCw className="w-4 h-4 animate-spin" />
                : <>
                    <Upload className="w-4 h-4 mb-0.5" />
                    <span className="text-[9px] leading-tight text-center">Upload</span>
                  </>}
            </button>
          )}

          {/* Empty state */}
          {attachments.length === 0 && !writeEnabled && (
            <p className="text-xs text-muted-foreground">No attachments.</p>
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
          for (const f of files) await handleUpload(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
