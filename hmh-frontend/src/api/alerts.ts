import client from "./client";

export type AlertStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
export type AlertSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AlertType = string;
export type NotificationStatus = "PENDING" | "SENT" | "FAILED" | "MOCK_SENT" | "ACKNOWLEDGED" | "CANCELLED";

export interface Alert {
  id: string;
  project_id: string | null;
  site_id: string | null;
  lot_id: string | null;
  reference_type: string | null;
  reference_id: string | null;
  alert_type: AlertType;
  severity: AlertSeverity;
  title: string;
  message: string;
  status: AlertStatus;
  target_role: string | null;
  target_user_id: string | null;
  notification_channel: string;
  sent_at: string | null;
  read_at: string | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface AlertStats {
  total: number;
  open: number;
  acknowledged: number;
  resolved: number;
  critical_open: number;
  high_open: number;
  pending_whatsapp_ack: number;
  failed_whatsapp_sends: number;
}

export interface AlertRecipient {
  id: string;
  name: string;
  phone_number: string;
  label: string | null;
  receives_critical_alerts: boolean;
  receives_daily_summary: boolean;
  receives_invoice_alerts: boolean;
  receives_delivery_alerts: boolean;
  receives_vehicle_alerts: boolean;
  receives_material_alerts: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AlertRecipientCreate {
  name: string;
  phone_number: string;
  label?: string;
  receives_critical_alerts?: boolean;
  receives_daily_summary?: boolean;
  receives_invoice_alerts?: boolean;
  receives_delivery_alerts?: boolean;
  receives_vehicle_alerts?: boolean;
  receives_material_alerts?: boolean;
}

export interface NotificationQueueEntry {
  id: string;
  alert_id: string | null;
  recipient_id: string | null;
  channel: string;
  phone_number: string;
  message_body: string;
  status: NotificationStatus;
  attempt_count: number;
  last_attempt_at: string | null;
  next_attempt_at: string | null;
  error_message: string | null;
  requires_acknowledgement: boolean;
  acknowledged_at: string | null;
  created_at: string;
}

export interface QueueStats {
  pending: number;
  sent: number;
  mock_sent: number;
  failed: number;
  acknowledged: number;
  cancelled: number;
}

export const alertsApi = {
  list: async (params?: { project_id?: string; status?: AlertStatus; alert_type?: string; limit?: number }): Promise<Alert[]> => {
    const res = await client.get<{ data: Alert[] }>("/alerts/", { params });
    return res.data.data;
  },

  stats: async (projectId?: string): Promise<AlertStats> => {
    const res = await client.get<{ data: AlertStats }>("/alerts/stats", {
      params: projectId ? { project_id: projectId } : {},
    });
    return res.data.data;
  },

  update: async (alertId: string, body: { status?: AlertStatus }): Promise<Alert> => {
    const res = await client.patch<{ data: Alert }>(`/alerts/${alertId}`, body);
    return res.data.data;
  },

  acknowledge: async (alertId: string): Promise<Alert> => {
    const res = await client.post<{ data: Alert }>(`/alerts/${alertId}/acknowledge`);
    return res.data.data;
  },

  resolve: async (alertId: string): Promise<Alert> => {
    const res = await client.post<{ data: Alert }>(`/alerts/${alertId}/resolve`);
    return res.data.data;
  },

  generateDailySummary: async (): Promise<{ summary_text: string; queued: number; send_counts: Record<string, number> }> => {
    const res = await client.post<{ data: { summary_text: string; queued: number; send_counts: Record<string, number> } }>("/alerts/daily-summary");
    return res.data.data;
  },

  // Recipients
  listRecipients: async (): Promise<AlertRecipient[]> => {
    const res = await client.get<{ data: AlertRecipient[] }>("/alerts/recipients");
    return res.data.data;
  },

  createRecipient: async (body: AlertRecipientCreate): Promise<AlertRecipient> => {
    const res = await client.post<{ data: AlertRecipient }>("/alerts/recipients", body);
    return res.data.data;
  },

  updateRecipient: async (id: string, body: Partial<AlertRecipientCreate & { is_active: boolean }>): Promise<AlertRecipient> => {
    const res = await client.patch<{ data: AlertRecipient }>(`/alerts/recipients/${id}`, body);
    return res.data.data;
  },

  deactivateRecipient: async (id: string): Promise<void> => {
    await client.delete(`/alerts/recipients/${id}`);
  },

  testRecipient: async (id: string): Promise<{ status: string; provider_message_id: string | null }> => {
    const res = await client.post<{ data: { status: string; provider_message_id: string | null } }>(`/alerts/recipients/${id}/test`);
    return res.data.data;
  },

  // Notification queue
  getQueue: async (status?: NotificationStatus, limit = 50): Promise<NotificationQueueEntry[]> => {
    const res = await client.get<{ data: NotificationQueueEntry[] }>("/alerts/queue", {
      params: { ...(status ? { status } : {}), limit },
    });
    return res.data.data;
  },

  getQueueStats: async (): Promise<QueueStats> => {
    const res = await client.get<{ data: QueueStats }>("/alerts/queue/stats");
    return res.data.data;
  },

  processQueue: async (): Promise<Record<string, number>> => {
    const res = await client.post<{ data: Record<string, number> }>("/alerts/queue/process");
    return res.data.data;
  },
};
