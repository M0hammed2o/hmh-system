import client from "./client";

export interface ExtraItem {
  description: string;
  quantity: number;
  unit: string | null;
  notes: string | null;
}

export interface ExtraCostGroup {
  type: "BREAKAGE" | "MISMANAGEMENT" | "EXTRAS" | "OTHER";
  items: ExtraItem[];
  count: number;
}

export interface ProjectCostSummary {
  project_id: string;
  project_name: string;
  project_code: string;
  project_status: string;
  // Budget
  boq_budget: number;
  // Actuals
  procurement_spend: number;
  labour_cost: number;
  subcontractor_cost: number;
  fuel_cost: number;
  fuel_litres: number;
  vehicle_repair_cost: number;
  // Derived
  total_actual: number;
  variance: number;
  variance_pct: number | null;
  // Extra/breakage detail
  extra_costs: ExtraCostGroup[];
  extra_items_total: number;
}

export const costSummaryApi = {
  get: async (projectId: string): Promise<ProjectCostSummary> => {
    const res = await client.get<{ data: ProjectCostSummary }>(
      `/projects/${projectId}/cost-summary`
    );
    return res.data.data;
  },
};

export const EXTRA_TYPE_LABELS: Record<string, string> = {
  BREAKAGE:       "Breakage",
  MISMANAGEMENT:  "Mismanagement",
  EXTRAS:         "Extras / Additional",
  OTHER:          "Other",
};

export const EXTRA_TYPE_COLORS: Record<string, string> = {
  BREAKAGE:       "text-destructive bg-destructive/10",
  MISMANAGEMENT:  "text-amber-700 bg-amber-100 dark:text-amber-400 dark:bg-amber-950/40",
  EXTRAS:         "text-blue-700 bg-blue-100 dark:text-blue-400 dark:bg-blue-950/40",
  OTHER:          "text-muted-foreground bg-muted",
};
