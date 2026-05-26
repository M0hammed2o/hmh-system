/**
 * Notification Settings API — Phase 3Q.1.
 * Manages WhatsApp alert recipients and per-project notification configuration.
 */
import client from "./client";

export const ALERT_CATEGORIES = [
  { key: "receives_critical_alerts",    label: "Critical",    description: "CRITICAL and HIGH severity alerts" },
  { key: "receives_procurement_alerts", label: "Procurement", description: "MR approved, PO sent, deliveries" },
  { key: "receives_milestone_alerts",   label: "Milestones",  description: "Completions and delays" },
  { key: "receives_payment_alerts",     label: "Payments",    description: "Invoices, payments, overdue" },
  { key: "receives_delivery_alerts",    label: "Deliveries",  description: "Delivery mismatches and notes" },
  { key: "receives_material_alerts",    label: "Materials",   description: "Stock shortages and overuse" },
  { key: "receives_invoice_alerts",     label: "Invoices",    description: "Invoice issues and mismatches" },
  { key: "receives_vehicle_alerts",     label: "Vehicles",    description: "Fleet repairs and fuel" },
  { key: "receives_daily_summary",      label: "Daily Summary", description: "Morning digest" },
] as const;

export type AlertCategoryKey = typeof ALERT_CATEGORIES[number]["key"];

export interface AlertRecipient {
  id:                          string;
  name:                        string;
  phone_number:                string;
  label:                       string | null;
  project_id:                  string | null;
  is_active:                   boolean;
  receives_critical_alerts:    boolean;
  receives_daily_summary:      boolean;
  receives_invoice_alerts:     boolean;
  receives_delivery_alerts:    boolean;
  receives_vehicle_alerts:     boolean;
  receives_material_alerts:    boolean;
  receives_procurement_alerts: boolean;
  receives_milestone_alerts:   boolean;
  receives_payment_alerts:     boolean;
  last_inbound_at:             string | null;
  created_at:                  string | null;
}

export interface RecipientCreate {
  name:                        string;
  phone_number:                string;
  label?:                      string | null;
  project_id?:                 string | null;
  receives_critical_alerts?:    boolean;
  receives_daily_summary?:      boolean;
  receives_invoice_alerts?:     boolean;
  receives_delivery_alerts?:    boolean;
  receives_vehicle_alerts?:     boolean;
  receives_material_alerts?:    boolean;
  receives_procurement_alerts?: boolean;
  receives_milestone_alerts?:   boolean;
  receives_payment_alerts?:     boolean;
}

export interface RecipientUpdate extends Partial<RecipientCreate> {
  is_active?: boolean;
}

export interface QueueStats {
  pending:      number;
  sent:         number;
  mock_sent:    number;
  failed:       number;
  acknowledged: number;
  total:        number;
}

export const notificationSettingsApi = {
  listRecipients: async (params?: {
    include_inactive?: boolean;
    project_id?: string;
  }): Promise<AlertRecipient[]> => {
    const res = await client.get<{ data: AlertRecipient[] }>(
      "/notification-settings/recipients",
      { params }
    );
    return res.data.data;
  },

  createRecipient: async (body: RecipientCreate): Promise<AlertRecipient> => {
    const res = await client.post<{ data: AlertRecipient }>(
      "/notification-settings/recipients",
      body
    );
    return res.data.data;
  },

  updateRecipient: async (id: string, body: RecipientUpdate): Promise<AlertRecipient> => {
    const res = await client.patch<{ data: AlertRecipient }>(
      `/notification-settings/recipients/${id}`,
      body
    );
    return res.data.data;
  },

  deleteRecipient: async (id: string): Promise<void> => {
    await client.delete(`/notification-settings/recipients/${id}`);
  },

  sendTest: async (id: string): Promise<{ recipient: string; phone: string; status: string }> => {
    const res = await client.post<{ data: { recipient: string; phone: string; status: string } }>(
      `/notification-settings/recipients/${id}/send-test`
    );
    return res.data.data;
  },

  getQueueStats: async (): Promise<QueueStats> => {
    const res = await client.get<{ data: QueueStats }>("/notification-settings/queue-stats");
    return res.data.data;
  },
};
