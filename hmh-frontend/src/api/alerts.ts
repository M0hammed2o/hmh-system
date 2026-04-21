import client from "./client";

export type AlertStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
export type AlertSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AlertType =
  | "BOQ_VARIANCE_OVERUSE" | "DELIVERY_WITHOUT_PO" | "INVOICE_MISMATCH"
  | "NEGATIVE_STOCK" | "LOW_STOCK" | "MISSING_REMAINING_STOCK_PHOTO"
  | "OVERDUE_PAYMENT" | "REQUEST_PENDING_TOO_LONG" | "DELIVERY_DISCREPANCY";

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

export interface AlertUpdate {
  status?: AlertStatus;
}

export const alertsApi = {
  list: async (params?: {
    project_id?: string;
    status?: AlertStatus;
    limit?: number;
  }): Promise<Alert[]> => {
    const res = await client.get<{ data: Alert[] }>("/alerts/", { params });
    return res.data.data;
  },

  update: async (alertId: string, body: AlertUpdate): Promise<Alert> => {
    const res = await client.patch<{ data: Alert }>(`/alerts/${alertId}`, body);
    return res.data.data;
  },
};
