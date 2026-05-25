import client from "./client";

export type AttachmentEntity =
  | "BOQ_HEADER"
  | "PURCHASE_ORDER"
  | "DELIVERY"
  | "INVOICE"
  | "USAGE_LOG"
  | "CERTIFICATION"
  | "STAGE_STATUS"
  | "PAYMENT"
  | "FUEL_LOG"
  | "MATERIAL_REQUEST"
  | "SUPPLIER"
  | "LOT"       // Phase 3K
  | "PROJECT";  // Phase 3K

export type AttachmentType =
  | "PHOTO"
  | "PDF"
  | "DELIVERY_NOTE"
  | "INVOICE_COPY"
  | "PROOF"
  | "CERTIFICATE"
  // Phase 3K additions
  | "PROGRESS_PHOTO"
  | "PROOF_OF_WORK"
  | "FUEL_SLIP"
  | "QUOTATION"
  | "PO_DOCUMENT"
  // Phase FINAL-2 additions
  | "BEFORE_PHOTO"
  | "COMPLETION_PHOTO"
  | "ISSUE_PHOTO"
  | "DELIVERY_EVIDENCE";

/** Human-readable labels for attachment type selector. */
export const ATTACHMENT_TYPE_LABELS: Record<AttachmentType, string> = {
  PHOTO:              "Photo",
  PDF:                "PDF Document",
  DELIVERY_NOTE:      "Delivery Note",
  INVOICE_COPY:       "Invoice",
  PROOF:              "Proof",
  CERTIFICATE:        "Certificate",
  PROGRESS_PHOTO:     "Progress Photo",
  PROOF_OF_WORK:      "Proof of Work",
  FUEL_SLIP:          "Fuel Slip / Receipt",
  QUOTATION:          "Quotation",
  PO_DOCUMENT:        "PO Document",
  BEFORE_PHOTO:       "Before Photo",
  COMPLETION_PHOTO:   "Completion Photo",
  ISSUE_PHOTO:        "Issue / Defect Photo",
  DELIVERY_EVIDENCE:  "Delivery Evidence",
};

export interface Attachment {
  id: string;
  entity_type: AttachmentEntity;
  entity_id: string;
  file_name: string;
  stored_path: string;          // direct URL (Supabase) or /uploads/... (local)
  mime_type: string;
  file_size_bytes: number | null;
  file_size_display: string;
  attachment_type: AttachmentType;
  uploaded_by: string | null;
  uploaded_by_name: string | null;   // populated at API layer
  uploaded_at: string;
  is_active: boolean;
  is_image: boolean;
  /** Direct URL (Supabase) or /api/v1/attachments/{id}/download (local). */
  download_url: string;
  // Phase FINAL-2 additions
  caption: string | null;
  uploaded_role: string | null;
}

export const attachmentsApi = {
  upload: async (
    file: File,
    entityType: AttachmentEntity,
    entityId: string,
    attachmentType: AttachmentType = "PHOTO",
    caption?: string,
  ): Promise<Attachment> => {
    const form = new FormData();
    form.append("file", file);
    form.append("entity_type", entityType);
    form.append("entity_id", entityId);
    form.append("attachment_type", attachmentType);
    if (caption) form.append("caption", caption);
    const res = await client.post<{ data: Attachment }>("/attachments/upload", form);
    return res.data.data;
  },

  listByEntity: async (
    entityType: AttachmentEntity,
    entityId: string,
    options?: {
      attachment_type?: AttachmentType;
      limit?: number;
      offset?: number;
    }
  ): Promise<Attachment[]> => {
    const res = await client.get<{ data: Attachment[] }>("/attachments/", {
      params: {
        entity_type: entityType,
        entity_id: entityId,
        ...(options?.attachment_type ? { attachment_type: options.attachment_type } : {}),
        ...(options?.limit != null ? { limit: options.limit } : {}),
        ...(options?.offset != null ? { offset: options.offset } : {}),
      },
    });
    return res.data.data;
  },

  delete: async (attachmentId: string): Promise<void> => {
    await client.delete(`/attachments/${attachmentId}`);
  },

  /** Backward-compatible helper — use att.download_url directly instead. */
  downloadUrl: (attachmentId: string): string =>
    `/api/v1/attachments/${attachmentId}/download`,
};
