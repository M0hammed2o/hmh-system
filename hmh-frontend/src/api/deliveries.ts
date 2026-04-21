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
};
