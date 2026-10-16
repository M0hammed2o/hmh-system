/**
 * Payments made to mechanics and workshops for vehicle repairs.
 *
 * Recording only — nothing here initiates a bank payment.
 *
 * What is owed is always computed by the server from the repair itself, so
 * there is no payable field to send and no status to set. `payment_status`
 * follows the money: a repair reads Paid because it has been paid, not
 * because someone marked it so.
 */

import client from "./client";

export type MechanicPaymentStatus = "UNPAID" | "PARTIALLY_PAID" | "PAID";

/** Where the payable figure came from, so a balance can be read in context. */
export type PayableBasis = "invoice" | "quote" | "recorded costs";

export interface RepairPaymentSummary {
  repair_job_id: string;
  repair_title: string;
  repair_date: string | null;
  repair_status: string;
  vehicle_id: string;
  vehicle_name: string | null;
  vehicle_registration: string | null;
  mechanic_name: string | null;
  total_payable: number;
  payable_basis: PayableBasis;
  total_paid: number;
  outstanding: number;
  payment_status: MechanicPaymentStatus;
  last_payment_date: string | null;
}

export interface MechanicPayment {
  id: string;
  repair_job_id: string;
  supplier_id: string | null;
  mechanic_name: string | null;
  amount: number;
  payment_date: string;
  payment_method: string | null;
  payment_reference: string | null;
  notes: string | null;
  proof_file_url: string | null;
  is_reversed: boolean;
  reversed_at: string | null;
  reversal_reason: string | null;
  recorded_by: string | null;
  created_at: string;
}

export interface RepairPaymentHistory extends RepairPaymentSummary {
  payments: MechanicPayment[];
}

export interface MechanicPaymentTotals {
  total_payable: number;
  total_paid: number;
  total_outstanding: number;
  repairs: number;
  unpaid: number;
  partially_paid: number;
  paid: number;
}

export interface MechanicPaymentOverview {
  items: RepairPaymentSummary[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
  /** Covers everything the filters match, not just the page. */
  totals: MechanicPaymentTotals;
}

export interface MechanicPaymentFilters {
  page?: number;
  limit?: number;
  mechanic?: string;
  vehicle_id?: string;
  company_id?: string;
  status?: MechanicPaymentStatus;
  date_from?: string;
  date_to?: string;
  unpaid_only?: boolean;
}

export interface MechanicPaymentCreate {
  amount: number;
  payment_date: string;
  supplier_id?: string;
  mechanic_name?: string;
  payment_method?: string;
  payment_reference?: string;
  notes?: string;
  proof_file_url?: string;
}

export const PAYMENT_STATUS_LABELS: Record<MechanicPaymentStatus, string> = {
  UNPAID: "Unpaid",
  PARTIALLY_PAID: "Partially Paid",
  PAID: "Paid",
};

export const mechanicPaymentsApi = {
  overview: async (filters: MechanicPaymentFilters = {}): Promise<MechanicPaymentOverview> => {
    const res = await client.get<{ data: MechanicPaymentOverview }>(
      "/workshop/mechanic-payments",
      { params: { page: 1, limit: 25, ...filters } },
    );
    return res.data.data;
  },

  history: async (repairJobId: string): Promise<RepairPaymentHistory> => {
    const res = await client.get<{ data: RepairPaymentHistory }>(
      `/workshop/repairs/${repairJobId}/payments`,
    );
    return res.data.data;
  },

  record: async (
    repairJobId: string,
    body: MechanicPaymentCreate,
  ): Promise<{ payment: MechanicPayment } & RepairPaymentSummary> => {
    const res = await client.post<{ data: { payment: MechanicPayment } & RepairPaymentSummary }>(
      `/workshop/repairs/${repairJobId}/payments`,
      body,
    );
    return res.data.data;
  },

  /** Withdraw a payment recorded in error. It stays visible; nothing is deleted. */
  reverse: async (
    paymentId: string,
    reason: string,
  ): Promise<{ payment: MechanicPayment } & RepairPaymentSummary> => {
    const res = await client.post<{ data: { payment: MechanicPayment } & RepairPaymentSummary }>(
      `/workshop/mechanic-payments/${paymentId}/reverse`,
      { reason },
    );
    return res.data.data;
  },
};
