import client from "./client";

export type FuelType = "DIESEL" | "PETROL" | "PARAFFIN" | "OTHER";
export type FuelUsageType = "EQUIPMENT" | "DELIVERY_VEHICLE" | "TRANSPORT" | "GENERATOR" | "OTHER";

export const FUEL_TYPE_LABELS: Record<FuelType, string> = {
  DIESEL: "Diesel",
  PETROL: "Petrol",
  PARAFFIN: "Paraffin",
  OTHER: "Other",
};

export const FUEL_USAGE_LABELS: Record<FuelUsageType, string> = {
  EQUIPMENT: "Equipment / Plant",
  DELIVERY_VEHICLE: "Delivery Vehicle",
  TRANSPORT: "Transport",
  GENERATOR: "Generator",
  OTHER: "Other",
};

export interface FuelLog {
  id: string;
  project_id: string;
  site_id: string | null;
  fuel_type: FuelType;
  usage_type: FuelUsageType;
  equipment_ref: string | null;
  litres: number;
  cost_per_litre: number | null;
  total_cost: number | null;
  fuelled_by: string | null;
  recorded_by: string;
  fuel_date: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface FuelLogCreate {
  fuel_type?: FuelType;
  usage_type?: FuelUsageType;
  equipment_ref?: string | null;
  litres: number;
  cost_per_litre?: number | null;
  fuelled_by?: string | null;
  site_id?: string | null;
  fuel_date?: string | null;
  notes?: string | null;
}

export interface FuelLogUpdate {
  fuel_type?: FuelType;
  usage_type?: FuelUsageType;
  equipment_ref?: string | null;
  litres?: number;
  cost_per_litre?: number | null;
  fuelled_by?: string | null;
  site_id?: string | null;
  fuel_date?: string | null;
  notes?: string | null;
}

export const fuelApi = {
  list: async (
    projectId: string,
    params?: { site_id?: string; limit?: number }
  ): Promise<FuelLog[]> => {
    const res = await client.get<{ data: FuelLog[] }>(
      `/projects/${projectId}/fuel/`,
      { params }
    );
    return res.data.data;
  },

  get: async (logId: string): Promise<FuelLog> => {
    const res = await client.get<{ data: FuelLog }>(`/fuel/${logId}`);
    return res.data.data;
  },

  create: async (projectId: string, body: FuelLogCreate): Promise<FuelLog> => {
    const res = await client.post<{ data: FuelLog }>(
      `/projects/${projectId}/fuel/`,
      body
    );
    return res.data.data;
  },

  update: async (logId: string, body: FuelLogUpdate): Promise<FuelLog> => {
    const res = await client.patch<{ data: FuelLog }>(`/fuel/${logId}`, body);
    return res.data.data;
  },
};
