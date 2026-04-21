import client from "./client";

export type BoqStatus = "DRAFT" | "UNDER_REVIEW" | "ACTIVE" | "SUPERSEDED" | "ARCHIVED";
export type ItemType = "MATERIAL" | "SERVICE" | "PACKAGE";

export interface BOQHeader {
  id: string;
  project_id: string;
  version_name: string;
  source_file_name: string | null;
  source_type: string;
  status: BoqStatus;
  is_active_version: boolean;
  uploaded_by: string | null;
  uploaded_at: string;
  notes: string | null;
}

export interface BOQSection {
  id: string;
  boq_header_id: string;
  stage_id: string | null;
  section_name: string;
  sequence_order: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface BOQItem {
  id: string;
  boq_section_id: string;
  project_id: string;
  site_id: string | null;
  lot_id: string | null;
  stage_id: string | null;
  item_id: string | null;
  supplier_id: string | null;
  raw_description: string;
  normalized_description: string | null;
  specification: string | null;
  item_type: ItemType;
  unit: string | null;
  planned_quantity: number | null;
  planned_rate: number | null;
  planned_total: number | null;
  sort_order: number;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface BOQHeaderCreate {
  version_name: string;
  source_type?: string;
  notes?: string | null;
}

export interface BOQHeaderUpdate {
  version_name?: string;
  status?: BoqStatus;
  is_active_version?: boolean;
  notes?: string | null;
}

export interface BOQSectionCreate {
  section_name: string;
  stage_id?: string | null;
  sequence_order?: number;
  notes?: string | null;
}

export interface BOQItemCreate {
  raw_description: string;
  item_type?: ItemType;
  unit?: string | null;
  planned_quantity?: number | null;
  planned_rate?: number | null;
  site_id?: string | null;
  lot_id?: string | null;
  stage_id?: string | null;
  item_id?: string | null;
  supplier_id?: string | null;
  specification?: string | null;
  sort_order?: number;
  notes?: string | null;
}

export interface BOQItemUpdate {
  raw_description?: string;
  item_type?: ItemType;
  unit?: string | null;
  planned_quantity?: number | null;
  planned_rate?: number | null;
  is_active?: boolean;
  notes?: string | null;
}

export const boqApi = {
  listHeaders: async (projectId: string): Promise<BOQHeader[]> => {
    const res = await client.get<{ data: BOQHeader[] }>(`/projects/${projectId}/boq/`);
    return res.data.data;
  },

  createHeader: async (projectId: string, body: BOQHeaderCreate): Promise<BOQHeader> => {
    const res = await client.post<{ data: BOQHeader }>(`/projects/${projectId}/boq/`, body);
    return res.data.data;
  },

  updateHeader: async (projectId: string, headerId: string, body: BOQHeaderUpdate): Promise<BOQHeader> => {
    const res = await client.patch<{ data: BOQHeader }>(`/projects/${projectId}/boq/${headerId}`, body);
    return res.data.data;
  },

  listSections: async (headerId: string): Promise<BOQSection[]> => {
    const res = await client.get<{ data: BOQSection[] }>(`/boq/${headerId}/sections/`);
    return res.data.data;
  },

  createSection: async (headerId: string, body: BOQSectionCreate): Promise<BOQSection> => {
    const res = await client.post<{ data: BOQSection }>(`/boq/${headerId}/sections/`, body);
    return res.data.data;
  },

  listItems: async (sectionId: string): Promise<BOQItem[]> => {
    const res = await client.get<{ data: BOQItem[] }>(`/boq/sections/${sectionId}/items/`);
    return res.data.data;
  },

  createItem: async (sectionId: string, body: BOQItemCreate): Promise<BOQItem> => {
    const res = await client.post<{ data: BOQItem }>(`/boq/sections/${sectionId}/items/`, body);
    return res.data.data;
  },

  updateItem: async (itemId: string, body: BOQItemUpdate): Promise<BOQItem> => {
    const res = await client.patch<{ data: BOQItem }>(`/boq/items/${itemId}`, body);
    return res.data.data;
  },

  importCsv: async (projectId: string, file: File, versionName: string): Promise<BOQHeader> => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("version_name", versionName);
    const res = await client.post<{ data: BOQHeader }>(
      `/projects/${projectId}/boq/import-csv`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data.data;
  },
};
