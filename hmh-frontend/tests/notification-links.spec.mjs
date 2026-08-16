import { expect, test } from "playwright/test";

const user = { id: "00000000-0000-0000-0000-000000000001", full_name: "Notification User",
  email: "notify@example.test", phone: null, role: "OFFICE_ADMIN", is_active: true,
  must_reset_password: false, last_login_at: null, failed_login_attempts: 0, locked_until: null,
  created_by: null, created_at: "2026-08-02T00:00:00Z", updated_at: "2026-08-02T00:00:00Z", project_access_count: 1 };
const projectId = "00000000-0000-0000-0000-000000000101";
const fuelOrderId = "00000000-0000-0000-0000-000000000201";
const fuelTypeId = "00000000-0000-0000-0000-000000000301";
const fuelOrder = {
  id: fuelOrderId, order_number: "FUR-REAL-RECORD", project_id: projectId, site_id: null,
  fuel_type_id: fuelTypeId, supplier_id: null, storage_location_id: null,
  requested_by: user.id, requester_name: user.full_name, request_date: "2026-08-02",
  requested_litres: 80, expected_delivery_date: "2026-08-05", delivery_location: "Main site",
  purpose: "Generator", intended_use: "Night shift", destination_type: "GENERATOR",
  vehicle_id: null, equipment_reference: "GEN-REAL-1", notes: null, status: "SUBMITTED",
  supplier_reference: null, purchase_order_reference: null, delivered_litres: 0,
  submitted_at: "2026-08-02T00:05:00Z", next_approver: "Fuel approver",
  feasibility_status: "OK", feasibility_message: null, estimated_remaining_litres: null,
  history: [{ id: "history-1", from_status: "DRAFT", to_status: "SUBMITTED",
    actor_name: user.full_name, reason: null, created_at: "2026-08-02T00:05:00Z" }],
  created_at: "2026-08-02T00:00:00Z",
};

async function authenticated(page) {
  await page.addInitScript(() => {
    localStorage.setItem("hmh_access_token", "notification-token");
    localStorage.setItem("hmh_user_role", "OFFICE_ADMIN");
  });
}

async function routeNotification(page, { action = `/fuel-management/orders?order=${fuelOrderId}`, openStatus = 200 } = {}) {
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/users/me")) return route.fulfill({ json: { data: user } });
    if (url.pathname.endsWith("/open")) {
      if (openStatus !== 200) return route.fulfill({ status: openStatus, json: { detail: openStatus === 403 ? "Forbidden" : "Notification not found" } });
      return route.fulfill({ json: { data: { id: "alert-1", status: "OPEN", read_at: "2026-08-02T01:00:00Z", action_url: action } } });
    }
    if (url.pathname.endsWith("/read")) return route.fulfill({ json: { data: { id: "alert-1", status: "OPEN", read_at: "2026-08-02T01:00:00Z", action_url: action } } });
    if (url.pathname.endsWith(`/fuel-management/orders/${fuelOrderId}`)) return route.fulfill({ json: { data: fuelOrder } });
    if (url.pathname.endsWith("/fuel-management/fuel-types")) return route.fulfill({ json: { data: [{ id: fuelTypeId, code: "DIESEL", name: "Diesel", is_active: true }] } });
    if (url.pathname.endsWith(`/projects/${projectId}/fuel-management/orders`)) return route.fulfill({ json: { data: [fuelOrder] } });
    if (url.pathname.endsWith(`/projects/${projectId}/fuel-management/storage`)) return route.fulfill({ json: { data: [] } });
    if (url.pathname.endsWith("/projects/")) return route.fulfill({ json: { data: { items: [{ id: projectId, name: "Linked Project" }], total: 1, page: 1, limit: 100, total_pages: 1 } } });
    return route.fulfill({ json: { data: [] } });
  });
}

test("fuel and material-request notification links open the correct record", async ({ page }) => {
  await authenticated(page); await routeNotification(page);
  await page.goto("/notifications/00000000-0000-0000-0000-000000000010");
  await expect(page).toHaveURL(new RegExp(`/fuel-management/orders\\?order=${fuelOrderId}$`));
  await expect(page.getByTestId(`fuel-order-${fuelOrderId}`)).toBeVisible();
  await expect(page.getByText("FUR-REAL-RECORD", { exact: true })).toBeVisible();
  await expect(page.getByText(/SUBMITTED by Notification User/)).toBeVisible();

  await page.unroute("**/api/v1/**");
  await routeNotification(page, { action: "/procurement?mr=mr-7" });
  await page.goto("/notifications/00000000-0000-0000-0000-000000000011");
  await expect(page).toHaveURL(/\/procurement\?mr=mr-7$/);
});

test("expired notification stays authenticated and shows unavailable", async ({ page }) => {
  await authenticated(page); await routeNotification(page, { openStatus: 404 });
  await page.goto("/notifications/00000000-0000-0000-0000-000000000012");
  await expect(page.getByText(/unavailable or has expired/i)).toBeVisible();
  await expect(page).toHaveURL(/\/notifications\//);
});

test("permission denial renders a clear page without a login loop", async ({ page }) => {
  await authenticated(page); await routeNotification(page, { openStatus: 403 });
  await page.goto("/notifications/00000000-0000-0000-0000-000000000013");
  await expect(page.getByTestId("notification-forbidden")).toBeVisible();
  await expect(page).not.toHaveURL(/\/login/);
});

test("expired authentication returns through login to the same Fuel order", async ({ page }) => {
  await authenticated(page);
  let openAttempts = 0;
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/users/me")) return route.fulfill({ json: { data: user } });
    if (path.endsWith("/auth/login")) return route.fulfill({ json: {
      access_token: "renewed-token", refresh_token: "renewed-refresh", token_type: "bearer",
      expires_in: 3600, must_reset_password: false,
    } });
    if (path.endsWith("/open")) {
      openAttempts += 1;
      if (openAttempts === 1) return route.fulfill({ status: 401, json: { detail: "Expired" } });
      return route.fulfill({ json: { data: { id: "alert-1", status: "OPEN",
        read_at: "2026-08-02T01:00:00Z", action_url: `/fuel-management/orders?order=${fuelOrderId}` } } });
    }
    if (path.endsWith("/read")) return route.fulfill({ json: { data: { id: "alert-1", status: "OPEN",
      read_at: "2026-08-02T01:00:00Z", action_url: `/fuel-management/orders?order=${fuelOrderId}` } } });
    if (path.endsWith(`/fuel-management/orders/${fuelOrderId}`)) return route.fulfill({ json: { data: fuelOrder } });
    if (path.endsWith("/fuel-management/fuel-types")) return route.fulfill({ json: { data: [{ id: fuelTypeId, code: "DIESEL", name: "Diesel", is_active: true }] } });
    if (path.endsWith(`/projects/${projectId}/fuel-management/orders`)) return route.fulfill({ json: { data: [fuelOrder] } });
    if (path.endsWith(`/projects/${projectId}/fuel-management/storage`)) return route.fulfill({ json: { data: [] } });
    if (path.endsWith("/projects/")) return route.fulfill({ json: { data: { items: [{ id: projectId, name: "Linked Project" }], total: 1, page: 1, limit: 100, total_pages: 1 } } });
    return route.fulfill({ json: { data: [] } });
  });
  await page.goto("/notifications/00000000-0000-0000-0000-000000000014");
  await expect(page).toHaveURL(/\/login\?returnTo=%2Fnotifications%2F00000000-0000-0000-0000-000000000014/);
  await page.waitForTimeout(500);
  if (new URL(page.url()).pathname === "/login") {
    await page.getByLabel("Email address").fill("notify@example.test");
    await page.getByLabel("Password").fill("password");
    await page.getByRole("button", { name: "Sign in" }).click();
  }
  await expect(page).toHaveURL(new RegExp(`/fuel-management/orders\\?order=${fuelOrderId}$`));
  await expect(page.getByTestId(`fuel-order-${fuelOrderId}`)).toBeVisible();
});

test("read notifications remain available in history", async ({ page }) => {
  await authenticated(page);
  const base = { project_id: null, site_id: null, lot_id: null, reference_type: null, reference_id: null,
    alert_type: "LOW_STOCK", severity: "LOW", status: "OPEN", target_role: null, target_user_id: null,
    notification_channel: "in_app", sent_at: null, acknowledged_by: null, acknowledged_at: null,
    created_at: "2026-08-02T00:00:00Z", resolved_at: null, resolved_by: null, message: "Review" };
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/users/me")) return route.fulfill({ json: { data: user } });
    if (path.endsWith("/alerts/")) return route.fulfill({ json: { data: [
      { ...base, id: "unread", title: "Unread fuel notification", read_at: null },
      { ...base, id: "read", title: "Read fuel notification", read_at: "2026-08-02T01:00:00Z" },
    ] } });
    if (path.endsWith("/alerts/stats")) return route.fulfill({ json: { data: { total: 2, open: 2, acknowledged: 0, resolved: 0, critical_open: 0, high_open: 0, pending_whatsapp_ack: 0, failed_whatsapp_sends: 0 } } });
    if (path.endsWith("/queue/stats")) return route.fulfill({ json: { data: { pending: 0, sent: 0, mock_sent: 0, failed: 0, acknowledged: 0, cancelled: 0 } } });
    return route.fulfill({ json: { data: [] } });
  });
  await page.goto("/alerts");
  await expect(page.getByText("Unread fuel notification", { exact: true })).toBeVisible();
  await expect(page.getByText("Read fuel notification", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "History" }).click();
  await expect(page.getByText("Read fuel notification", { exact: true })).toBeVisible();
});
