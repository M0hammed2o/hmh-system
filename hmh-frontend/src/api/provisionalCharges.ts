import client from "./client";

/**
 * Pending supplier charges — money a supplier has asked for in advance.
 *
 * Deliberately its own client, not a mode of the invoices client. A
 * pro-forma is not a payable, and a module that can fetch both through one
 * call is one whose results eventually get added together into a figure for
 * "what we owe" that is wrong.
 */

export type ProvisionalChargeStatus = "PENDING" | "INVOICED" | "CANCELLED";

export const PROVISIONAL_STATUS_LABELS: Record<ProvisionalChargeStatus, string> = {
  PENDING:   "Awaiting invoice",
  INVOICED:  "Invoiced",
  CANCELLED: "Cancelled",
};

export interface ProvisionalCharge {
  id: string;
  reference: string;
  supplier_id: string;
  supplier_name: string | null;
  project_id: string;
  purchase_order_id: string | null;
  /** The order's number, so the screen can name it rather than show a UUID. */
  purchase_order_number: string | null;
  quotation_id: string | null;
  issue_date: string | null;
  due_date: string | null;
  subtotal_amount: number | null;
  vat_amount: number | null;
  total_amount: number;
  status: ProvisionalChargeStatus;
  /** The tax invoice that superseded this request, once one exists. */
  settled_by_invoice_id: string | null;
  settled_by_invoice_number: string | null;
  /** A PAID stamp on the paperwork. A claim awaiting verification, never a settlement. */
  payment_evidence_detected: boolean;
  payment_evidence_note: string | null;
  notes: string | null;
  created_at: string | null;
}

export interface ProvisionalSummary {
  pending_count: number;
  pending_total: number;
  payment_evidence_count: number;
  /** The server's own words for what the total is and is not. Displayed verbatim. */
  meaning: string;
}

export const provisionalChargesApi = {
  list: async (
    projectId: string,
    status?: ProvisionalChargeStatus,
  ): Promise<ProvisionalCharge[]> => {
    const res = await client.get<{ data: ProvisionalCharge[] }>(
      `/projects/${projectId}/provisional-charges/`,
      { params: status ? { status } : undefined },
    );
    return res.data.data;
  },

  summary: async (projectId: string): Promise<ProvisionalSummary> => {
    const res = await client.get<{ data: ProvisionalSummary }>(
      `/projects/${projectId}/provisional-charges/summary`,
    );
    return res.data.data;
  },

  /** Withdraw a request for payment that will not be honoured. */
  cancel: async (chargeId: string, reason: string): Promise<ProvisionalCharge> => {
    const res = await client.post<{ data: ProvisionalCharge }>(
      `/provisional-charges/${chargeId}/cancel`, { reason },
    );
    return res.data.data;
  },
};
