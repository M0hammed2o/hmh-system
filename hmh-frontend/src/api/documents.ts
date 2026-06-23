import client from "./client";

export type DocumentEntityType =
  | "MATERIAL_REQUEST"
  | "PURCHASE_ORDER"
  | "INVOICE"
  | "DELIVERY"
  | "PAYMENT";

export interface ProjectDocument {
  id: string;
  entity_type: DocumentEntityType;
  entity_id: string;
  entity_ref: string | null;
  entity_label: string;
  file_name: string;
  mime_type: string;
  attachment_type: string;
  file_size_bytes: number | null;
  file_size_display: string;
  caption: string | null;
  uploaded_by_name: string | null;
  uploaded_role: string | null;
  uploaded_at: string;
  download_url: string;
  is_image: boolean;
}

export interface ListDocumentsParams {
  entity_type?: DocumentEntityType;
  search?: string;
  limit?: number;
  offset?: number;
}

export const documentsApi = {
  list(projectId: string, params: ListDocumentsParams = {}): Promise<ProjectDocument[]> {
    return client
      .get(`/projects/${projectId}/documents`, { params })
      .then((r) => r.data.data);
  },
};
