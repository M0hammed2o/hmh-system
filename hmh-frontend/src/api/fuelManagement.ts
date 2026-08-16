import client from "./client";

export interface FuelTypeDefinition { id: string; code: string; name: string; is_active: boolean }
export interface FuelStorage { id: string; project_id: string; site_id: string | null; fuel_type_id: string; name: string; location_type: string; capacity_litres: number | null; low_stock_threshold_litres: number | null; calculated_balance_litres: number; notes: string | null }
export interface FuelEquipmentProfile { id: string; project_id: string; site_id: string | null; equipment_reference: string; destination_type: string; is_active: boolean }
export interface FuelOrder { id: string; order_number: string; project_id: string; site_id: string | null; fuel_type_id: string; supplier_id: string | null; storage_location_id: string | null; requested_by: string; requester_name?: string | null; request_date: string; requested_litres: number; expected_delivery_date: string | null; delivery_location: string; purpose: string | null; intended_use?: string | null; destination_type?: string | null; vehicle_id?: string | null; equipment_reference?: string | null; notes?: string | null; status: string; supplier_reference: string | null; purchase_order_reference: string | null; delivered_litres: number; submitted_at?: string | null; next_approver?: string | null; feasibility_status?: string; feasibility_message?: string | null; estimated_remaining_litres?: number | null; history?: Array<{ id: string; from_status: string | null; to_status: string; actor_name: string | null; reason: string | null; created_at: string }>; created_at: string }
export interface FuelDelivery { id: string; order_id: string | null; procurement_delivery_item_id: string | null; project_id: string; site_id: string; storage_location_id: string | null; delivery_note_number: string | null; delivered_at: string | null; litres_delivered: number; confirmed_litres: number | null; variance_litres: number | null; supplier_variance_litres: number | null; meter_variance_litres: number | null; is_manual_emergency: boolean; emergency_reason: string | null; verification_status: string; excess_override: boolean; notes: string | null; created_at: string }
export interface FuelPendingConfirmation { delivery_item_id: string; description: string; quantity_received: number; unit: string | null; delivery_id: string; delivery_number: string | null; delivery_date: string; supplier_delivery_note_number: string | null; po_id: string; po_number: string; supplier_id: string }
export interface FuelIssue { id: string; issue_number: string; project_id: string; storage_location_id: string; fuel_type_id: string; vehicle_id: string | null; destination_type: string; equipment_reference: string | null; issued_at: string; litres: number; odometer_reading: number | null; hour_meter_reading: number | null; litres_per_100km: number | null; litres_per_hour: number | null; anomaly_flag: boolean; anomaly_reason: string | null; feasibility_status: string; reading_source: string; estimated_remaining_litres: number | null; evidence: Array<{ type: string; attachment_id: string }>; is_reversed: boolean; unit_cost: number | null; total_cost: number | null }
export interface FuelReconciliation { id: string; reconciliation_number: string; storage_location_id: string; reconciliation_date: string; calculated_balance_litres: number; physical_balance_litres: number; variance_litres: number; variance_pct: number | null; explanation: string; status: string; requires_approval: boolean }
export interface FuelDashboard { litres_requested: number; litres_approved: number; litres_ordered: number; litres_delivered: number; litres_issued: number; current_calculated_stock: number; outstanding_orders: number; overdue_deliveries: number; anomalies_for_review: number; storage_locations: { id: string; name: string; balance_litres: number }[] }

const data = <T>(promise: Promise<{ data: { data: T } }>) => promise.then((r) => r.data.data);

export const fuelManagementApi = {
  fuelTypes: () => data<FuelTypeDefinition[]>(client.get("/fuel-management/fuel-types")),
  dashboard: (projectId: string) => data<FuelDashboard>(client.get(`/projects/${projectId}/fuel-management/dashboard`)),
  storage: (projectId: string) => data<FuelStorage[]>(client.get(`/projects/${projectId}/fuel-management/storage`)),
  equipmentProfiles: (projectId: string) => data<FuelEquipmentProfile[]>(client.get(`/projects/${projectId}/fuel-management/equipment-profiles`)),
  createStorage: (projectId: string, body: Record<string, unknown>) => data<FuelStorage>(client.post(`/projects/${projectId}/fuel-management/storage`, body)),
  orders: (projectId: string, mine = false) => data<FuelOrder[]>(client.get(`/projects/${projectId}/fuel-management/orders`, { params: { mine } })),
  order: (orderId: string) => data<FuelOrder>(client.get(`/fuel-management/orders/${orderId}`)),
  createOrder: (projectId: string, body: Record<string, unknown>) => data<FuelOrder>(client.post(`/projects/${projectId}/fuel-management/orders`, body)),
  submitRequest: (projectId: string, body: Record<string, unknown>) => data<FuelOrder>(client.post(`/projects/${projectId}/fuel-management/requests`, body)),
  transitionOrder: (orderId: string, action: "submit" | "approve" | "reject" | "mark-ordered" | "cancel" | "close", body: Record<string, unknown> = {}) => data<FuelOrder>(client.post(`/fuel-management/orders/${orderId}/${action}`, body)),
  deliveries: (projectId: string) => data<FuelDelivery[]>(client.get(`/projects/${projectId}/fuel-management/deliveries`)),
  pendingConfirmations: (projectId: string) => data<FuelPendingConfirmation[]>(client.get(`/projects/${projectId}/fuel-management/deliveries/pending-confirmation`)),
  receiveFromProcurement: (projectId: string, body: Record<string, unknown>) => data<FuelDelivery>(client.post(`/projects/${projectId}/fuel-management/deliveries/from-procurement`, body)),
  recordDelivery: (orderId: string, body: Record<string, unknown>) => data<FuelDelivery>(client.post(`/fuel-management/orders/${orderId}/deliveries`, body)),
  verifyDelivery: (deliveryId: string, approve = true) => data<FuelDelivery>(client.post(`/fuel-management/deliveries/${deliveryId}/${approve ? "verify" : "reject"}`)),
  issues: (projectId: string, params?: { vehicle_id?: string; equipment_reference?: string; anomaly_only?: boolean }) =>
    data<FuelIssue[]>(client.get(`/projects/${projectId}/fuel-management/issues`, { params })),
  createIssue: (projectId: string, body: Record<string, unknown>) => data<FuelIssue>(client.post(`/projects/${projectId}/fuel-management/issues`, body)),
  createIssueWithEvidence: (projectId: string, body: Record<string, unknown>, files: Record<string, File | null>, onProgress?: (pct: number) => void) => {
    const form = new FormData(); form.append("payload", JSON.stringify(body));
    Object.entries(files).forEach(([key, file]) => { if (file) form.append(key, file); });
    return data<FuelIssue>(client.post(`/projects/${projectId}/fuel-management/issues-with-evidence`, form, {
      onUploadProgress: (event) => onProgress?.(event.total ? Math.round(event.loaded * 100 / event.total) : 0),
    }));
  },
  reverseIssue: (issueId: string, reason: string) => data<FuelIssue>(client.post(`/fuel-management/issues/${issueId}/reverse`, { reason })),
  reconciliations: (projectId: string) => data<FuelReconciliation[]>(client.get(`/projects/${projectId}/fuel-management/reconciliations`)),
  reconcile: (projectId: string, body: Record<string, unknown>) => data<FuelReconciliation>(client.post(`/projects/${projectId}/fuel-management/reconciliations`, body)),
  approveReconciliation: (id: string, reason: string) => data<FuelReconciliation>(client.post(`/fuel-management/reconciliations/${id}/approve`, { reason })),
  downloadReport: async (projectId: string, report: "orders" | "usage") => {
    const response = await client.get(`/projects/${projectId}/fuel-management/reports/${report}.csv`, { responseType: "blob" });
    const url = URL.createObjectURL(response.data); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `fuel-${report}.csv`; anchor.click(); URL.revokeObjectURL(url);
  },
};
