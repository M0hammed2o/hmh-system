import client from "./client";

export type BoqStatus = "DRAFT" | "UNDER_REVIEW" | "ACTIVE" | "SUPERSEDED" | "ARCHIVED";
export type ItemType = "MATERIAL" | "LABOUR" | "PLANT" | "SERVICE" | "PACKAGE";

export interface BOQHeader {
  id: string;
  project_id: string;
  version_name: string;
  source_file_name: string | null;
  source_type: string;
  status: BoqStatus;
  is_active_version: boolean;
  is_template: boolean;
  template_name: string | null;
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

export interface SectionWithItems {
  section: BOQSection;
  items: BOQItem[];
  section_total: number;
}

export interface FullBOQ {
  header: BOQHeader;
  sections: SectionWithItems[];
  grand_total: number;
}

export interface BOQHeaderCreate {
  version_name: string;
  source_type?: string;
  notes?: string | null;
  is_template?: boolean;
  template_name?: string | null;
}

export interface BOQHeaderUpdate {
  version_name?: string;
  status?: BoqStatus;
  is_active_version?: boolean;
  is_template?: boolean;
  template_name?: string | null;
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
  specification?: string | null;
  is_active?: boolean;
  notes?: string | null;
}

export interface LotBOQSummaryItem {
  boq_item_id: string;
  item_id: string | null;
  description: string;
  item_type: ItemType;
  unit: string | null;
  item_name: string;
  allocated_quantity: number;
  used_quantity: number;
  remaining_quantity: number;
  over_quantity: number;
  is_over: boolean;
  planned_rate: number;
  planned_total: number;
  used_cost: number;
}

export interface LotBOQSummary {
  lot_id: string;
  lot_number: string;
  items: LotBOQSummaryItem[];
  total_planned_cost: number;
  total_used_cost: number;
  total_items: number;
  overrun_count: number;
}

// ── Hierarchy types ───────────────────────────────────────────────────────────

export interface TypeBreakdown {
  material_total: number;
  labour_total:   number;
  plant_total:    number;
  service_total:  number;
  other_total?:   number;
}

export interface Variance {
  variance_amount: number;
  variance_pct:    number;
}

export interface MasterSummarySite extends TypeBreakdown, Variance {
  site_id:        string;
  site_name:      string;
  unit_total:     number;
  lot_count:      number;
  site_total:     number;
  item_count:     number;
  has_boq:        boolean;
  boq_header_ids: string[];
}

export interface ProjectMasterSummary extends TypeBreakdown {
  project_id:       string;
  total_planned:    number;
  site_count:       number;
  total_lot_count:  number;
  legacy_lot_count: number;
  sites:            MasterSummarySite[];
}

export interface SiteBOQItem {
  id: string;
  description: string;
  unit: string | null;
  planned_quantity: number;
  planned_rate: number;
  line_total: number;
  item_type: ItemType;
}

export interface SiteBOQSection {
  section_id: string;
  section_name: string;
  sequence_order: number;
  items: SiteBOQItem[];
  section_total: number;
}

export interface SiteBOQSummary extends TypeBreakdown, Variance {
  site_id:           string;
  site_name:         string;
  project_id:        string;
  unit_total:        number;
  lot_count:         number;
  site_total:        number;
  item_count:        number;
  sections:          SiteBOQSection[];
  boq_header_ids:    string[];
  derived_from_lots: boolean;
}

export interface LotBOQRow extends TypeBreakdown, Variance {
  lot_id:         string;
  lot_number:     string;
  lot_status:     string;
  lot_total:      number;
  has_lot_boq:    boolean;
  has_custom_boq: boolean;
  item_count:     number;
  boq_header_ids: string[];
}

// ─────────────────────────────────────────────────────────────────────────────

export interface BOQTemplate {
  id:            string;
  version_name:  string;
  template_name: string | null;
  notes:         string | null;
}

export type BOQApplyMode = "CREATE" | "SAFE" | "FORCE";

export interface BOQTemplatePreviewLot {
  lot_id:                   string;
  lot_number:               string;
  unit_type:                string | null;
  is_freestanding:          boolean;
  is_customized:            boolean;
  has_existing_boq:         boolean;
  existing_item_count:      number;
  new_item_count:           number;
  has_existing_milestones:  boolean;
  existing_milestone_count: number;
  new_milestone_count:      number;
  action:                   "create" | "overwrite" | "skip";
  skip_reason:              string | null;
}

export interface BOQTemplatePreview {
  template_id:            string;
  template_name:          string;
  template_section_count: number;
  template_item_count:    number;
  template_stage_count:   number;
  mode:                   BOQApplyMode;
  lots:                   BOQTemplatePreviewLot[];
  lots_to_apply:          number;
  lots_to_skip:           number;
  lots_needing_overwrite: number;
  total_lots:             number;
}

export interface BOQCloneResult {
  created_count:       number;
  milestones_created:  number;
  deactivated_count:   number;
  skipped_count:       number;
  skipped_reasons:     Record<string, string>;
  lot_ids:             string[];
  freestanding_master: boolean;
  mode:                BOQApplyMode;
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

  getFullBOQ: async (projectId: string, headerId: string): Promise<FullBOQ> => {
    const res = await client.get<{ data: FullBOQ }>(`/projects/${projectId}/boq/${headerId}/full`);
    return res.data.data;
  },

  markAsTemplate: async (projectId: string, headerId: string, templateName: string): Promise<BOQHeader> => {
    const res = await client.post<{ data: BOQHeader }>(
      `/projects/${projectId}/boq/${headerId}/mark-template`,
      { template_name: templateName },
    );
    return res.data.data;
  },

  seedStandardTemplate: async (projectId: string): Promise<BOQHeader> => {
    const res = await client.post<{ data: BOQHeader }>(
      `/projects/${projectId}/boq/seed-standard-template`,
    );
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

  updateSection: async (headerId: string, sectionId: string, body: { section_name?: string; sequence_order?: number; notes?: string }): Promise<BOQSection> => {
    const res = await client.patch<{ data: BOQSection }>(`/boq/${headerId}/sections/${sectionId}`, body);
    return res.data.data;
  },

  deleteSection: async (headerId: string, sectionId: string): Promise<void> => {
    await client.delete(`/boq/${headerId}/sections/${sectionId}`);
  },

  deleteSectionScoped: async (
    headerId: string,
    sectionId: string,
    scope: "lot" | "site",
  ): Promise<{ scope: string; sections_deleted: number; lots_affected: number; items_deleted: number; message: string }> => {
    const res = await client.delete<{ data: { scope: string; sections_deleted: number; lots_affected: number; items_deleted: number; message: string } }>(
      `/boq/${headerId}/sections/${sectionId}?scope=${scope}`,
    );
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

  applyItemToAllSiteLots: async (
    itemId: string,
    body: BOQItemUpdate,
  ): Promise<{ updated: number; lots_affected: number; warning: string | null }> => {
    const res = await client.post<{ data: { updated: number; lots_affected: number; warning: string | null } }>(
      `/boq/items/${itemId}/apply-to-all-site-lots`,
      body,
    );
    return res.data.data;
  },

  deleteItem: async (itemId: string): Promise<void> => {
    await client.delete(`/boq/items/${itemId}`);
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

  getLotBOQSummary: async (lotId: string): Promise<LotBOQSummary> => {
    const res = await client.get<{ data: LotBOQSummary }>(`/lots/${lotId}/boq-summary`);
    return res.data.data;
  },

  getLotHeaders: async (lotId: string): Promise<Array<{
    id: string; project_id: string; version_name: string;
    template_name: string | null; status: string;
    is_active_version: boolean; is_template: boolean;
  }>> => {
    const res = await client.get<{ data: Array<{ id: string; project_id: string; version_name: string; template_name: string | null; status: string; is_active_version: boolean; is_template: boolean }> }>(`/lots/${lotId}/boq-headers`);
    return res.data.data;
  },

  // ── Hierarchy endpoints ──────────────────────────────────────────────────

  masterSummary: async (projectId: string): Promise<ProjectMasterSummary> => {
    const res = await client.get<{ data: ProjectMasterSummary }>(
      `/boq/items/projects/${projectId}/master-summary`,
    );
    return res.data.data;
  },

  siteBoqSummary: async (siteId: string): Promise<SiteBOQSummary> => {
    const res = await client.get<{ data: SiteBOQSummary }>(
      `/boq/items/sites/${siteId}/boq-summary`,
    );
    return res.data.data;
  },

  siteLotBoqs: async (siteId: string): Promise<LotBOQRow[]> => {
    const res = await client.get<{ data: LotBOQRow[] }>(
      `/boq/items/sites/${siteId}/lot-boqs`,
    );
    return res.data.data;
  },

  generateSiteLotBoqs: async (siteId: string): Promise<{
    created: number;
    lot_count: number;
    used_fallback: boolean;
    unassigned_lots: number;
    warning: string | null;
  }> => {
    const res = await client.post<{ data: {
      created: number; lot_count: number;
      used_fallback: boolean; unassigned_lots: number; warning: string | null;
    } }>(
      `/boq/items/sites/${siteId}/generate-lot-boqs`,
    );
    return res.data.data;
  },

  resetLotToSiteBoq: async (lotId: string): Promise<{ created: number }> => {
    const res = await client.post<{ data: { created: number } }>(
      `/boq/items/lots/${lotId}/reset-to-site-boq`,
    );
    return res.data.data;
  },

  // ── Template operations ────────────────────────────────────────────────────

  /** List all global reusable templates (GET /boq-templates/). */
  listTemplates: async (): Promise<BOQTemplate[]> => {
    const res = await client.get<{ data: BOQTemplate[] }>("/boq-templates/");
    return res.data.data;
  },

  /** Dry-run preview — see what will change before applying. */
  previewClone: async (body: {
    template_boq_id: string;
    project_id:      string;
    lot_ids:         string[];
    mode?:           BOQApplyMode;
  }): Promise<BOQTemplatePreview> => {
    const res = await client.post<{ data: BOQTemplatePreview }>(
      "/boq-templates/preview-clone",
      { mode: "CREATE", ...body },
    );
    return res.data.data;
  },

  /** Apply a template to a set of lots. */
  cloneToLots: async (body: {
    template_boq_id:     string;
    project_id:          string;
    lot_ids:             string[];
    mode?:               BOQApplyMode;  // CREATE | SAFE | FORCE
    overwrite?:          boolean;       // deprecated alias for mode="FORCE"
    generate_milestones?: boolean;
  }): Promise<BOQCloneResult> => {
    const res = await client.post<{ data: BOQCloneResult }>(
      "/boq-templates/clone-to-lots",
      { mode: "CREATE", ...body },
    );
    return res.data.data;
  },
};
