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
  fuel_consumption_per_hour: number | null;
  fuel_tolerance_pct: number;
  fuel_minimum_issue_interval_hours: number;
  fuel_override_required: boolean;
  hour_meter_required: boolean;
  tracker_provider: string | null;
  tracker_external_id: string | null;
  current_odometer_km: number | null;
  service_interval_km: number | null;
  uses_hours: boolean;
  current_hours_reading: number | null;
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
  assigned_project_id?: string | null;
  assigned_site_id?: string | null;
  vin_number?: string;
  make?: string;
  model?: string;
  year?: number;
  fuel_type?: FuelType;
  tank_capacity_l?: number;
  fuel_consumption_per_100km?: number;
  fuel_consumption_per_hour?: number;
  fuel_tolerance_pct?: number;
  fuel_minimum_issue_interval_hours?: number;
  fuel_override_required?: boolean;
  hour_meter_required?: boolean;
  tracker_provider?: string;
  tracker_external_id?: string;
  current_odometer_km?: number;
  service_interval_km?: number;
  uses_hours?: boolean;
  current_hours_reading?: number;
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
  repair_job_id: string | null;
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

export interface RepairJobCost {
  id: string;
  cost_type: VehicleCostType;
  amount: number;
  description: string | null;
  cost_date: string;
  notes: string | null;
}

export interface RepairJobMR {
  id: string;
  mr_number: string | null;
  status: string;
  requested_date: string | null;
}

export interface RepairJob {
  id: string;
  vehicle_id: string;
  title: string;
  description: string | null;
  status: string;
  workshop_name: string | null;
  date_opened: string;
  date_closed: string | null;
  odometer_at_repair: number | null;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  // Quotation / approval / invoice
  quote_amount: number | null;
  quote_file_url: string | null;
  invoice_amount: number | null;
  invoice_file_url: string | null;
  approval_stage: number;
  approval_1_by: string | null;
  approval_1_at: string | null;
  approval_2_by: string | null;
  approval_2_at: string | null;
  approval_3_by: string | null;
  approval_3_at: string | null;
  // Costs
  total_labour_cost: number;
  total_parts_cost: number;
  labour_cost_count: number;
  mr_count: number;
  labour_costs: RepairJobCost[];
  material_requests: RepairJobMR[];
}

export interface RepairJobCreate {
  title: string;
  description?: string;
  status?: string;
  workshop_name?: string;
  date_opened: string;
  date_closed?: string;
  odometer_at_repair?: number;
  notes?: string;
}

export interface FuelDelivery {
  id: string;
  site_id: string;
  project_id: string | null;
  delivery_date: string;
  fuel_type: string;
  litres_delivered: number;
  litres_dispensed: number;
  litres_remaining: number;
  cost_per_litre: number | null;
  supplier_name: string | null;
  invoice_number: string | null;
  notes: string | null;
  recorded_by: string | null;
  created_at: string;
}

export interface VehicleTransferRequest {
  id: string;
  vehicle_id: string;
  from_site_id: string | null;
  to_site_id: string;
  reason: string | null;
  status: "PENDING" | "APPROVED" | "REJECTED";
  requested_by: string | null;
  approved_by: string | null;
  approved_at: string | null;
  rejected_reason: string | null;
  created_at: string;
}

export const vehiclesApi = {
  list: async (projectId?: string, siteId?: string): Promise<Vehicle[]> => {
    const params: Record<string, string> = {};
    if (projectId) params.project_id = projectId;
    if (siteId) params.site_id = siteId;
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

  listRepairs: async (vehicleId: string): Promise<RepairJob[]> => {
    const res = await client.get<{ data: RepairJob[] }>(`/vehicles/${vehicleId}/repairs`);
    return res.data.data;
  },

  createRepair: async (vehicleId: string, body: RepairJobCreate): Promise<RepairJob> => {
    const res = await client.post<{ data: RepairJob }>(`/vehicles/${vehicleId}/repairs`, body);
    return res.data.data;
  },

  updateRepair: async (
    repairJobId: string,
    body: Partial<RepairJobCreate> & { status?: string; date_closed?: string },
  ): Promise<RepairJob> => {
    const res = await client.patch<{ data: RepairJob }>(`/vehicles/repairs/${repairJobId}`, body);
    return res.data.data;
  },

  logRepairCost: async (repairJobId: string, body: VehicleCostCreate): Promise<VehicleCost> => {
    const res = await client.post<{ data: VehicleCost }>(`/vehicles/repairs/${repairJobId}/costs`, body);
    return res.data.data;
  },

  submitRepairQuote: async (
    repairJobId: string,
    quoteAmount: number,
    workshopName?: string,
    quoteFile?: File | null,
  ): Promise<RepairJob> => {
    const fd = new FormData();
    fd.append("quote_amount", String(quoteAmount));
    if (workshopName) fd.append("workshop_name", workshopName);
    if (quoteFile) fd.append("quote_file", quoteFile);
    const res = await client.post<{ data: RepairJob }>(
      `/vehicles/repairs/${repairJobId}/submit-quote`,
      fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data.data;
  },

  approveRepairQuote: async (repairJobId: string): Promise<RepairJob> => {
    const res = await client.post<{ data: RepairJob }>(`/vehicles/repairs/${repairJobId}/approve`);
    return res.data.data;
  },

  uploadRepairInvoice: async (
    repairJobId: string,
    invoiceAmount: number,
    invoiceFile?: File | null,
  ): Promise<RepairJob> => {
    const fd = new FormData();
    fd.append("invoice_amount", String(invoiceAmount));
    if (invoiceFile) fd.append("invoice_file", invoiceFile);
    const res = await client.post<{ data: RepairJob }>(
      `/vehicles/repairs/${repairJobId}/upload-invoice`,
      fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data.data;
  },

  // Fuel deliveries
  listFuelDeliveries: async (siteId: string): Promise<FuelDelivery[]> => {
    const res = await client.get<{ data: FuelDelivery[] }>("/vehicles/fuel-deliveries/", {
      params: { site_id: siteId },
    });
    return res.data.data;
  },

  createFuelDelivery: async (params: {
    site_id: string;
    project_id?: string;
    delivery_date: string;
    fuel_type?: string;
    litres_delivered: number;
    cost_per_litre?: number;
    supplier_name?: string;
    invoice_number?: string;
    notes?: string;
  }): Promise<FuelDelivery> => {
    const fd = new FormData();
    fd.append("site_id", params.site_id);
    fd.append("delivery_date", params.delivery_date);
    fd.append("fuel_type", params.fuel_type || "DIESEL");
    fd.append("litres_delivered", String(params.litres_delivered));
    if (params.project_id) fd.append("project_id", params.project_id);
    if (params.cost_per_litre != null) fd.append("cost_per_litre", String(params.cost_per_litre));
    if (params.supplier_name) fd.append("supplier_name", params.supplier_name);
    if (params.invoice_number) fd.append("invoice_number", params.invoice_number);
    if (params.notes) fd.append("notes", params.notes);
    const res = await client.post<{ data: FuelDelivery }>("/vehicles/fuel-deliveries/", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data.data;
  },

  fillFromDelivery: async (params: {
    vehicle_id: string;
    delivery_id: string;
    litres: number;
    hours_reading?: number;
    odometer_reading?: number;
    fuelled_by?: string;
    notes?: string;
  }): Promise<FuelDelivery> => {
    const fd = new FormData();
    fd.append("delivery_id", params.delivery_id);
    fd.append("litres", String(params.litres));
    if (params.hours_reading != null) fd.append("hours_reading", String(params.hours_reading));
    if (params.odometer_reading != null) fd.append("odometer_reading", String(params.odometer_reading));
    if (params.fuelled_by) fd.append("fuelled_by", params.fuelled_by);
    if (params.notes) fd.append("notes", params.notes);
    const res = await client.post<{ data: FuelDelivery }>(
      `/vehicles/${params.vehicle_id}/fill-from-delivery`,
      fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data.data;
  },

  // Transfer requests
  requestTransfer: async (vehicleId: string, toSiteId: string, reason?: string): Promise<VehicleTransferRequest> => {
    const fd = new FormData();
    fd.append("to_site_id", toSiteId);
    if (reason) fd.append("reason", reason);
    const res = await client.post<{ data: VehicleTransferRequest }>(
      `/vehicles/${vehicleId}/request-transfer`,
      fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data.data;
  },

  listTransferRequests: async (vehicleId?: string, siteId?: string): Promise<VehicleTransferRequest[]> => {
    const params: Record<string, string> = {};
    if (vehicleId) params.vehicle_id = vehicleId;
    if (siteId) params.site_id = siteId;
    const res = await client.get<{ data: VehicleTransferRequest[] }>("/vehicles/transfer-requests/", { params });
    return res.data.data;
  },

  approveTransfer: async (requestId: string): Promise<VehicleTransferRequest> => {
    const res = await client.post<{ data: VehicleTransferRequest }>(
      `/vehicles/transfer-requests/${requestId}/approve`,
    );
    return res.data.data;
  },

  rejectTransfer: async (requestId: string, reason?: string): Promise<VehicleTransferRequest> => {
    const fd = new FormData();
    if (reason) fd.append("rejected_reason", reason);
    const res = await client.post<{ data: VehicleTransferRequest }>(
      `/vehicles/transfer-requests/${requestId}/reject`,
      fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data.data;
  },
};
