import client from "./client";
import type { RecordStatus } from "./purchaseOrders";

export interface DeliveryItem {
  id: string;
  delivery_id: string;
  purchase_order_item_id: string | null;
  item_id: string | null;
  boq_item_id: string | null;
  description: string;
  quantity_expected: number | null;
  quantity_received: number;
  unit: string | null;
  discrepancy_reason: string | null;
  created_at: string;
}

export interface Delivery {
  id: string;
  delivery_number: string | null;
  purchase_order_id: string | null;
  supplier_id: string;
  project_id: string;
  site_id: string;
  received_by_user_id: string;
  delivery_date: string;
  supplier_delivery_note_number: string | null;
  delivery_status: RecordStatus;
  comments: string | null;
  receiver_name: string | null;
  delivery_note_image_url: string | null;
  signature_image_url: string | null;
  ocr_raw_data: { driver_name?: string; driver_signature_path?: string; signed_at?: string; receiver_name?: string } | null;
  gps_lat: number | null;
  gps_lng: number | null;
  created_at: string;
  updated_at: string;
  items: DeliveryItem[];
}

export interface DeliveryItemCreate {
  description: string;
  quantity_received: number;
  quantity_expected?: number | null;
  unit?: string | null;
  item_id?: string | null;
  boq_item_id?: string | null;
  purchase_order_item_id?: string | null;
  discrepancy_reason?: string | null;
}

export interface DeliveryCreate {
  supplier_id: string;
  site_id: string;
  purchase_order_id?: string | null;
  delivery_number?: string | null;
  supplier_delivery_note_number?: string | null;
  delivery_date?: string | null;
  comments?: string | null;
  items: DeliveryItemCreate[];
  // Signature fields
  receiver_name?: string | null;
  signature_data?: string | null;         // site staff base64 PNG data URL
  driver_name?: string | null;
  driver_signature_data?: string | null;  // driver base64 PNG data URL
}

export interface DeliveryUpdate {
  delivery_status?: RecordStatus;
  comments?: string | null;
  supplier_delivery_note_number?: string | null;
}

export const deliveriesApi = {
  list: async (projectId: string): Promise<Delivery[]> => {
    const res = await client.get<{ data: Delivery[] }>(
      `/projects/${projectId}/deliveries/`
    );
    return res.data.data;
  },

  get: async (deliveryId: string): Promise<Delivery> => {
    const res = await client.get<{ data: Delivery }>(`/deliveries/${deliveryId}`);
    return res.data.data;
  },

  create: async (projectId: string, body: DeliveryCreate): Promise<Delivery> => {
    const res = await client.post<{ data: Delivery }>(
      `/projects/${projectId}/deliveries/`,
      body
    );
    return res.data.data;
  },

  update: async (deliveryId: string, body: DeliveryUpdate): Promise<Delivery> => {
    const res = await client.patch<{ data: Delivery }>(`/deliveries/${deliveryId}`, body);
    return res.data.data;
  },

  receiveWithDocument: async (formData: FormData): Promise<{
    delivery_id:          string;
    delivery_number:      string;
    status:               string;
    items_count:          number;
    is_partial:           boolean;
    has_file:             boolean;
    unlinked_items:       Array<{ description: string; quantity_received: number; unit: string | null }>;
    unlinked_count:       number;
    stock_updated_count:  number;
  }> => {
    const res = await client.post(
      "/deliveries/receive-with-document",
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data.data;
  },

  linkDeliveryItem: async (
    deliveryId:     string,
    deliveryItemId: string,
    catalogItemId:  string,
  ): Promise<Delivery> => {
    const res = await client.patch<{ data: Delivery }>(
      `/deliveries/${deliveryId}/items/${deliveryItemId}/link`,
      { item_id: catalogItemId },
    );
    return res.data.data;
  },

  reconcile: async (deliveryId: string): Promise<{
    delivery_id:          string;
    delivery_number:      string;
    po_number:            string | null;
    supplier:             string | null;
    invoice_number:       string | null;
    delivery_note_number: string | null;
    ordered_total:        number | null;
    invoice_total:        number | null;
    overall_status:       string;
    checks:               Array<{ type: string; status: string; item?: string; ordered_qty?: number; received_qty?: number }>;
  }> => {
    const res = await client.get(`/deliveries/${deliveryId}/reconcile`);
    return res.data.data;
  },
};
