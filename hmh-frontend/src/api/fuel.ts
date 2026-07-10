import client from "./client";
import { API_BASE } from "@/lib/constants";

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
  vehicle_id: string | null;
  fuel_type: FuelType;
  usage_type: FuelUsageType;
  equipment_ref: string | null;
  litres: number;
  cost_per_litre: number | null;
  total_cost: number | null;
  fuelled_by: string | null;
  recorded_by: string;
  fuel_date: string;
  // Odometer & consumption (migration 0012)
  odometer_reading: number | null;
  distance_km:      number | null;
  efficiency_kpl:   number | null;
  l_per_100km:      number | null;
  // Machine hours (migration 0063)
  hours_reading:    number | null;
  hours_operated:   number | null;
  fuel_per_hour:    number | null;
  // Evidence photos (migration 0012)
  photo_odometer: string | null;
  photo_pump:     string | null;
  photo_invoice:  string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface FuelLogCreate {
  fuel_type?: FuelType;
  usage_type?: FuelUsageType;
  equipment_ref?: string | null;
  vehicle_id?: string | null;
  litres: number;
  cost_per_litre?: number | null;
  fuelled_by?: string | null;
  site_id?: string | null;
  fuel_date?: string | null;
  odometer_reading?: number | null;
  hours_reading?:    number | null;
  hours_operated?:   number | null;
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
  odometer_reading?: number | null;
  notes?: string | null;
}

export interface FuelLogWithEvidence extends FuelLogCreate {
  photo_odometer?: File | null;
  photo_pump?:     File | null;
  photo_invoice?:  File | null;
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

  listByVehicle: async (projectId: string, vehicleId: string): Promise<FuelLog[]> => {
    const res = await client.get<{ data: FuelLog[] }>(
      `/projects/${projectId}/fuel/vehicle/${vehicleId}`
    );
    return res.data.data;
  },

  get: async (logId: string): Promise<FuelLog> => {
    const res = await client.get<{ data: FuelLog }>(`/fuel/${logId}`);
    return res.data.data;
  },

  /** Create fuel log with optional evidence photos via multipart/form-data. */
  createWithEvidence: async (
    projectId: string,
    data: FuelLogWithEvidence
  ): Promise<FuelLog> => {
    const fd = new FormData();
    fd.append("fuel_type",  data.fuel_type  || "DIESEL");
    fd.append("usage_type", data.usage_type || "EQUIPMENT");
    fd.append("litres", String(data.litres));
    if (data.vehicle_id)       fd.append("vehicle_id",       data.vehicle_id);
    if (data.cost_per_litre != null) fd.append("cost_per_litre", String(data.cost_per_litre));
    if (data.equipment_ref)    fd.append("equipment_ref",    data.equipment_ref);
    if (data.fuelled_by)       fd.append("fuelled_by",       data.fuelled_by);
    if (data.site_id)          fd.append("site_id",          data.site_id);
    if (data.fuel_date)        fd.append("fuel_date",        data.fuel_date);
    if (data.odometer_reading != null) fd.append("odometer_reading", String(data.odometer_reading));
    if (data.notes)            fd.append("notes",            data.notes);
    if (data.photo_odometer)   fd.append("photo_odometer",   data.photo_odometer);
    if (data.photo_pump)       fd.append("photo_pump",       data.photo_pump);
    if (data.photo_invoice)    fd.append("photo_invoice",    data.photo_invoice);

    const res = await client.post<{ data: FuelLog }>(
      `/projects/${projectId}/fuel/with-evidence`,
      fd,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return res.data.data;
  },

  /** Legacy JSON create (no photos). */
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

  delete: async (logId: string): Promise<void> => {
    await client.delete(`/fuel/${logId}`);
  },
};

/** Convert a relative /uploads/ path to an absolute backend URL. */
const BACKEND_ORIGIN = API_BASE.replace(/\/api\/v1\/?$/, "");
export function fuelPhotoUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (path.startsWith("http")) return path;
  if (path.startsWith("/uploads/")) return `${BACKEND_ORIGIN}${path}`;
  return path;
}
