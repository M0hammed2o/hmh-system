import client from "./client";

export type AttachmentEntity =
  | "BOQ_HEADER"
  | "PURCHASE_ORDER"
  | "DELIVERY"
  | "INVOICE"
  | "USAGE_LOG"
  | "CERTIFICATION";

export type AttachmentType =
  | "PHOTO"
  | "PDF"
  | "DELIVERY_NOTE"
  | "INVOICE_COPY"
  | "PROOF"
  | "CERTIFICATE";

export interface Attachment {
  id: string;
  entity_type: AttachmentEntity;
  entity_id: string;
  file_name: string;
  mime_type: string;
  file_size_bytes: number | null;
  file_size_display: string;
  attachment_type: AttachmentType;
  uploaded_by: string | null;
  uploaded_at: string;
  is_active: boolean;
  is_image: boolean;
  download_url: string;
}

export const attachmentsApi = {
  /**
   * Upload a file linked to an entity.
   * Uses multipart/form-data — do NOT set Content-Type manually.
   */
  upload: async (
    file: File,
    entityType: AttachmentEntity,
    entityId: string,
    attachmentType: AttachmentType
  ): Promise<Attachment> => {
    const form = new FormData();
    form.append("file", file);
    form.append("entity_type", entityType);
    form.append("entity_id", entityId);
    form.append("attachment_type", attachmentType);
    const res = await client.post<{ data: Attachment }>("/attachments/upload", form);
    return res.data.data;
  },

  /**
   * List all active attachments linked to an entity.
   */
  listByEntity: async (
    entityType: AttachmentEntity,
    entityId: string
  ): Promise<Attachment[]> => {
    const res = await client.get<{ data: Attachment[] }>("/attachments/", {
      params: { entity_type: entityType, entity_id: entityId },
    });
    return res.data.data;
  },

  /**
   * Returns the full URL to stream/download a single attachment.
   * Use this as an <a href> or <img src>.
   */
  downloadUrl: (attachmentId: string): string =>
    `/api/v1/attachments/${attachmentId}/download`,
};
