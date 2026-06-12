import client from "./client";
import type { FuelType } from "./fuel";

export type VehicleType = "BAKKIE" | "TRUCK" | "TLB" | "EXCAVATOR" | "CRANE" | "VAN" | "OTHER";
export type VehicleStatus = "ACTIVE" | "MAINTENANCE" | "RETIRED";
export type VehicleCostType = "FUEL" | "TYRE" | "REPAIR" | "SERVICE" | "LICENCE" | "INSURANCE" | "OTHER";
export type { FuelType };

export interface Vehicle {
  id: string;
  registration: string;
  name: string;
  vehicle_type: VehicleType;
  status: VehicleStatus;
  assigned_project_id: string | null;
  assigned_site_id: string | null;
  vin_number: string | null;
  make: string | null;
  model: string | null;
  year: number | null;
  fuel_type: FuelType | null;
  tank_capacity_l: number | null;
  fuel_consumption_per_100km: number | null;
  current_odometer_km: number | null;
  service_interval_km: number | null;
  last_service_date: string | null;
  next_service_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface VehicleCreate {
  registration: string;
  name: string;
  vehicle_type?: VehicleType;
  status?: VehicleStatus;
  assigned_project_id?: string;
  assigned_site_id?: string;
  vin_number?: string;
  make?: string;
  model?: string;
  year?: number;
  fuel_type?: FuelType;
  tank_capacity_l?: number;
  fuel_consumption_per_100km?: number;
  current_odometer_km?: number;
  service_interval_km?: number;
  last_service_date?: string;
  next_service_date?: string;
  notes?: string;
}

export interface VehicleCost {
  id: string;
  vehicle_id: string;
  cost_type: VehicleCostType;
  amount: number;
  description: string | null;
  project_id: string | null;
  site_id: string | null;
  lot_id: string | null;
  proof_image_url: string | null;
  cost_date: string;
  recorded_by: string | null;
  notes: string | null;
  created_at: string;
}

export interface VehicleCostCreate {
  cost_type: VehicleCostType;
  amount: number;
  description?: string;
  project_id?: string;
  site_id?: string;
  lot_id?: string;
  cost_date: string;
  notes?: string;
}

export const vehiclesApi = {
  list: async (projectId?: string): Promise<Vehicle[]> => {
    const params = projectId ? { project_id: projectId } : {};
    const res = await client.get<{ data: Vehicle[] }>("/vehicles/", { params });
    return res.data.data;
  },

  create: async (body: VehicleCreate): Promise<Vehicle> => {
    const res = await client.post<{ data: Vehicle }>("/vehicles/", body);
    return res.data.data;
  },

  get: async (id: string): Promise<Vehicle> => {
    const res = await client.get<{ data: Vehicle }>(`/vehicles/${id}`);
    return res.data.data;
  },

  update: async (id: string, body: Partial<VehicleCreate>): Promise<Vehicle> => {
    const res = await client.patch<{ data: Vehicle }>(`/vehicles/${id}`, body);
    return res.data.data;
  },

  logCost: async (vehicleId: string, body: VehicleCostCreate): Promise<VehicleCost> => {
    const res = await client.post<{ data: VehicleCost }>(`/vehicles/${vehicleId}/costs`, body);
    return res.data.data;
  },

  listCosts: async (vehicleId: string): Promise<VehicleCost[]> => {
    const res = await client.get<{ data: VehicleCost[] }>(`/vehicles/${vehicleId}/costs`);
    return res.data.data;
  },

  delete: async (vehicleId: string): Promise<void> => {
    await client.delete(`/vehicles/${vehicleId}`);
  },
};
