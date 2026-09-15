import { expect, test } from "playwright/test";

// Client review 2026-09-15:
//  1. Site Clerk picks a supplier per BOQ material request line (BOQ default preselected).
//  2. Add to Warehouse is gone from the Site Dashboard; Site Clerks see no Remove stock action.
//  3. BOQ builder Add item accepts a supplier (and specification) before the item is created.

const apiUser = (role) => ({
  id: "00000000-0000-0000-0000-000000000001",
  full_name: "Site Test User",
  email: "site@example.test",
  phone: null,
  role,
  is_active: true,
  must_reset_password: false,
  last_login_at: null,
  failed_login_attempts: 0,
  locked_until: null,
  created_by: null,
  created_at: "2026-09-15T00:00:00Z",
  updated_at: "2026-09-15T00:00:00Z",
  project_access_count: 1,
});

const SUPPLIERS = [
  { id: "sup-a", name: "Default Cement Co", email: null, is_active: true },
  { id: "sup-b", name: "Other Cement Co", email: null, is_active: true },
];

const WAREHOUSE_SITE = { id: "s1", project_id: "p1", name: "Project Warehouse", code: null, site_type: "warehouse", location_description: null, is_active: true };

const BOQ_HIT = {
  id: "boq-1", description: "Cement 42.5R", unit: "bag", planned_quantity: 10, total_planned_quantity: 200,
  preferred_supplier_id: "sup-a", supplier_name: "Default Cement Co", lot_id: "l1", site_id: "s1", item_id: "i1",
};

function recordWrite(route, writes) {
  const req = route.request();
  if (req.method() === "GET") return;
  let body = null;
  try { body = req.postDataJSON(); } catch { body = null; }
  writes.push({ method: req.method(), path: new URL(req.url()).pathname, body });
}

async function mockSiteDashboard(page, { role = "SITE_STAFF", projects, sites, globalStock = [], writes }) {
  await page.addInitScript((r) => {
    localStorage.setItem("hmh_access_token", "site-token");
    localStorage.setItem("hmh_user_role", r);
  }, role);
  await page.route("**/api/v1/**", async (route) => {
    recordWrite(route, writes);
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path.endsWith("/users/me")) return route.fulfill({ json: { data: apiUser(role) } });
    if (path.endsWith("/projects/")) return route.fulfill({ json: { data: { items: projects, total: projects.length, page: 1, limit: 100, total_pages: 1 } } });
    if (path.endsWith("/sites/")) return route.fulfill({ json: { data: sites } });
    if (path.endsWith("/suppliers/")) return route.fulfill({ json: { data: SUPPLIERS } });
    if (path.endsWith("/boq/items/search")) return route.fulfill({ json: { data: [BOQ_HIT] } });
    if (path.endsWith("/warehouse/main/")) return route.fulfill({ json: { data: globalStock } });
    if (method === "POST" && path.endsWith("/material-requests/")) {
      return route.fulfill({ status: 201, json: { data: { id: "mr-1", status: "DRAFT", items: [] } } });
    }
    if (method === "POST" && path.endsWith("/material-requests/mr-1/submit")) {
      return route.fulfill({ json: { data: { id: "mr-1", status: "SUBMITTED", items: [] } } });
    }
    return route.fulfill({ json: { data: [] } });
  });
}

test("Site Clerk Request Materials: BOQ default supplier preselected, clerk picks another, request carries it", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes = [];
  await mockSiteDashboard(page, { projects: [{ id: "p1", name: "Cornubia" }], sites: [WAREHOUSE_SITE], writes });
  await page.goto("/site");

  await page.getByRole("button", { name: "Request Materials" }).click();
  await page.getByPlaceholder(/Type material name/).fill("Cement");
  await page.getByRole("button", { name: /Cement 42\.5R/ }).click();

  await expect(page.getByText("Default supplier:")).toBeVisible();
  await expect(page.getByText("Default supplier:")).toContainText("Default Cement Co");
  const supplier = page.getByLabel("Supplier for Cement 42.5R");
  await expect(supplier).toHaveValue("sup-a");
  await expect(supplier.locator("option")).toHaveText(["— No supplier —", "Default Cement Co (BOQ default)", "Other Cement Co"]);

  await supplier.selectOption("sup-b");
  await expect(supplier).toHaveValue("sup-b");
  await expect(page.getByText(/Changed for this request only/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();

  await page.getByPlaceholder("Qty").fill("25");
  await page.locator("#rm-date").fill("2026-12-01");
  await page.locator("#rm-notes").fill("Slab pour");
  await page.getByRole("button", { name: /Submit Request \(1 item\)/ }).click();

  await expect.poll(() => writes.some((w) => w.path.endsWith("/material-requests/mr-1/submit"))).toBeTruthy();
  const create = writes.find((w) => w.method === "POST" && w.path.endsWith("/projects/p1/material-requests/"));
  expect(create.body.preferred_supplier_id).toBe("sup-b");
  expect(create.body.needed_by_date).toBe("2026-12-01");
  expect(create.body.notes).toBe("Slab pour");
  expect(create.body.items).toHaveLength(1);
  expect(create.body.items[0]).toMatchObject({
    boq_item_id: "boq-1", preferred_supplier_id: "sup-b", quantity_requested: 25, unit: "bag",
  });
  // Picking a supplier for one request must never write to the BOQ item.
  expect(writes.filter((w) => w.path.includes("/boq/"))).toEqual([]);
});

test("Site Clerk keeping the BOQ default supplier submits the default", async ({ page }) => {
  const writes = [];
  await mockSiteDashboard(page, { projects: [{ id: "p1", name: "Cornubia" }], sites: [WAREHOUSE_SITE], writes });
  await page.goto("/site");

  await page.getByRole("button", { name: "Request Materials" }).click();
  await page.getByPlaceholder(/Type material name/).fill("Cement");
  await page.getByRole("button", { name: /Cement 42\.5R/ }).click();
  await expect(page.getByText(/Changed for this request only/)).toHaveCount(0);
  await page.getByPlaceholder("Qty").fill("5");
  await page.getByRole("button", { name: /Submit Request \(1 item\)/ }).click();

  await expect.poll(() => writes.some((w) => w.path.endsWith("/material-requests/mr-1/submit"))).toBeTruthy();
  const create = writes.find((w) => w.method === "POST" && w.path.endsWith("/projects/p1/material-requests/"));
  expect(create.body.items[0].preferred_supplier_id).toBe("sup-a");
});

test("Fuel tab of Request Materials is unchanged and has no supplier picker", async ({ page }) => {
  const writes = [];
  await mockSiteDashboard(page, { projects: [{ id: "p1", name: "Cornubia" }], sites: [WAREHOUSE_SITE], writes });
  await page.route("**/api/v1/fuel-management/fuel-types", (route) =>
    route.fulfill({ json: { data: [{ id: "f1", code: "DIESEL", name: "Diesel", is_active: true }] } }));
  await page.goto("/site");

  await page.getByRole("button", { name: "Fuel request" }).click();
  await expect(page.getByRole("button", { name: "Submit fuel request" })).toBeVisible();
  await expect(page.getByLabel(/Supplier for/)).toHaveCount(0);
  await page.getByPlaceholder("e.g. 1000").fill("300");
  await page.getByRole("button", { name: "Submit fuel request" }).click();

  await expect.poll(() => writes.some((w) => w.path.endsWith("/material-requests/mr-1/submit"))).toBeTruthy();
  const create = writes.find((w) => w.method === "POST" && w.path.endsWith("/projects/p1/material-requests/"));
  expect(create.body.procurement_category).toBe("FUEL");
  expect(create.body.items[0]).toMatchObject({ description: "Diesel", quantity_requested: 300, unit: "L" });
  expect(create.body.items[0].boq_item_id).toBeUndefined();
});

test("Site Dashboard warehouse quick actions no longer offer Add to Warehouse", async ({ page }) => {
  const writes = [];
  await mockSiteDashboard(page, { projects: [{ id: "p1", name: "Cornubia" }], sites: [WAREHOUSE_SITE], writes });
  await page.goto("/site");

  await expect(page.getByRole("button", { name: "Request Materials" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Receive Delivery" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Project Transfer" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add to Warehouse" })).toHaveCount(0);
  await expect(page.getByText("Add to Warehouse")).toHaveCount(0);
});

test("Site Clerk Project Transfer submits a vote-based transfer request and never calls the direct transfer route", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes = [];
  await page.addInitScript(() => {
    localStorage.setItem("site_project_id", "p1");
    localStorage.setItem("site_site_id", "s1");
  });
  await mockSiteDashboard(page, {
    projects: [{ id: "p1", name: "Cornubia" }, { id: "p2", name: "Umhlanga" }],
    sites: [WAREHOUSE_SITE], writes,
  });
  await page.route("**/api/v1/projects/p1/warehouse/", (route) => route.fulfill({ json: { data: [
    { item_id: "i1", item_name: "Paving Blocks", unit: "ea", on_hand: 40, total_in: 40, total_out: 0, last_movement: null },
  ] } }));
  await page.route("**/api/v1/projects/p1/warehouse-transfers/", (route) => {
    recordWrite(route, writes);
    return route.fulfill({ json: { data: {
      id: "wt-1", from_project_id: "p1", from_project_name: "Cornubia", to_project_id: "p2", to_project_name: "Umhlanga",
      item_id: "i1", item_name: "Paving Blocks", quantity: 15, unit: "ea", reason: "Needed on Umhlanga", notes: null,
      status: "PENDING", vote_count: 0, votes_required: 3, votes: [],
    } } });
  });
  await page.goto("/site");

  await page.getByRole("button", { name: "Project Transfer" }).click();
  const modal = page.locator("div.fixed", { has: page.getByRole("heading", { name: "Request Project Transfer" }) });
  await expect(modal.getByText(/office must approve it before any stock moves/)).toBeVisible();
  await modal.locator("select").nth(0).selectOption("p2");
  await modal.locator("select").nth(1).selectOption("i1");
  await modal.getByLabel("Quantity to transfer").fill("15");
  // Reason is required — an empty reason must not send a request.
  await modal.getByRole("button", { name: "Submit Transfer Request" }).click();
  await expect(modal.getByRole("heading", { name: "Request Project Transfer" })).toBeVisible();
  expect(writes.filter((w) => w.path.includes("warehouse-transfers"))).toEqual([]);

  await modal.getByLabel("Reason").fill("Needed on Umhlanga");
  await modal.getByRole("button", { name: "Submit Transfer Request" }).click();

  await expect(page.getByText("Pending office approval")).toBeVisible();
  await expect(page.getByText(/Stock has not moved yet/)).toBeVisible();
  const create = writes.find((w) => w.method === "POST" && w.path.endsWith("/projects/p1/warehouse-transfers/"));
  expect(create.body).toEqual({ to_project_id: "p2", item_id: "i1", quantity: 15, reason: "Needed on Umhlanga" });
  expect(writes.filter((w) => w.path.includes("transfer-to-project") || w.path.includes("/stock/"))).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

const GLOBAL_STOCK = [{
  project_id: null, project_name: "Global", project_code: "GLOBAL", item_id: "i1", item_name: "Cement 42.5R",
  item_type: "MATERIAL", unit: "bag", on_hand: 40, total_in: 40, total_out: 0, last_movement: null,
}];

test("Site Clerk viewing the Main Warehouse gets no Remove stock action", async ({ page }) => {
  const writes = [];
  await mockSiteDashboard(page, {
    projects: [{ id: "p1", name: "Cornubia" }, { id: "p2", name: "Other" }],
    sites: [WAREHOUSE_SITE], globalStock: GLOBAL_STOCK, writes,
  });
  await page.goto("/site");
  await page.locator("select").first().selectOption("__main_warehouse__");

  await expect(page.getByText("Cement 42.5R")).toBeVisible();
  await expect(page.getByTitle("Remove stock")).toHaveCount(0);
});

test("Owner (dual access) still sees Remove stock on the Main Warehouse view", async ({ page }) => {
  const writes = [];
  await mockSiteDashboard(page, {
    role: "OWNER",
    projects: [{ id: "p1", name: "Cornubia" }, { id: "p2", name: "Other" }],
    sites: [WAREHOUSE_SITE], globalStock: GLOBAL_STOCK, writes,
  });
  await page.goto("/site");
  await page.locator("select").first().selectOption("__main_warehouse__");

  await expect(page.getByText("Cement 42.5R")).toBeVisible();
  await expect(page.getByTitle("Remove stock")).toHaveCount(1);
});

// ── BOQ builder ──────────────────────────────────────────────────────────────

const boqItem = (overrides) => ({
  id: "item-existing", boq_section_id: "sec1", project_id: "p1", site_id: null, lot_id: null, stage_id: null,
  item_id: null, supplier_id: "sup-a", raw_description: "Existing sand", normalized_description: null,
  specification: null, item_type: "MATERIAL", unit: "m3", planned_quantity: 10, planned_rate: 450,
  planned_total: 4500, sort_order: 0, is_active: true, notes: null,
  created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z", ...overrides,
});

test("BOQ builder Add item saves the selected supplier and the edit form shows it", async ({ page }) => {
  const writes = [];
  const items = [boqItem({})];
  await page.addInitScript(() => {
    localStorage.setItem("hmh_access_token", "office-token");
    localStorage.setItem("hmh_user_role", "OFFICE_ADMIN");
  });
  await page.route("**/api/v1/**", async (route) => {
    recordWrite(route, writes);
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (path.endsWith("/users/me")) return route.fulfill({ json: { data: apiUser("OFFICE_ADMIN") } });
    if (path.endsWith("/suppliers/")) return route.fulfill({ json: { data: SUPPLIERS } });
    if (path.endsWith("/projects/p1/boq/h1/full")) {
      return route.fulfill({ json: { data: {
        header: { id: "h1", project_id: "p1", version_name: "Cornubia Phase 1", source_file_name: null, source_type: "manual",
                  status: "ACTIVE", is_active_version: true, is_template: false, template_name: null, uploaded_by: null,
                  uploaded_at: "2026-09-15T00:00:00Z", notes: null },
        sections: [{ section: { id: "sec1", boq_header_id: "h1", stage_id: null, section_name: "Substructure", sequence_order: 1,
                                notes: null, created_at: "2026-09-15T00:00:00Z", updated_at: "2026-09-15T00:00:00Z" },
                     items, section_total: 0 }],
        grand_total: 0,
      } } });
    }
    if (req.method() === "POST" && path.endsWith("/boq/sections/sec1/items/")) {
      const body = req.postDataJSON();
      const created = boqItem({ id: "item-new", ...body });
      items.push(created);
      return route.fulfill({ status: 201, json: { data: created } });
    }
    return route.fulfill({ json: { data: { items: [], total: 0, page: 1, limit: 100, total_pages: 0 } } });
  });

  await page.goto("/boq/p1/h1/build");
  await page.getByRole("button", { name: "Add item" }).click();

  await page.getByPlaceholder("Description *").fill("Y12 rebar");
  await page.getByPlaceholder("Unit").fill("t");
  await page.getByPlaceholder("Qty").fill("4");
  await page.getByPlaceholder("Rate").fill("18500");
  await page.getByPlaceholder("Specification (optional)").fill("SANS 920");
  const addSupplier = page.getByLabel("Supplier");
  await expect(addSupplier).toHaveValue("");
  await addSupplier.selectOption("sup-b");
  await page.getByRole("button", { name: "Add", exact: true }).click();

  await expect(page.getByText("Y12 rebar")).toBeVisible();
  const create = writes.find((w) => w.method === "POST" && w.path.endsWith("/boq/sections/sec1/items/"));
  expect(create.body).toMatchObject({
    raw_description: "Y12 rebar", unit: "t", planned_quantity: 4, planned_rate: 18500,
    item_type: "MATERIAL", specification: "SANS 920", supplier_id: "sup-b",
  });
  // One create call, no follow-up edit needed to attach the supplier.
  expect(writes.filter((w) => w.path.includes("/boq/items/"))).toEqual([]);

  // The new row lists the supplier, and opening Edit shows the same supplier selected.
  const newRow = page.locator("tr", { hasText: "Y12 rebar" });
  await expect(newRow).toContainText("Other Cement Co");
  await newRow.locator("button").first().click();
  await expect(page.getByLabel("Supplier")).toHaveValue("sup-b");

  // Existing item untouched.
  await expect(page.locator("tr", { hasText: "Existing sand" })).toContainText("Default Cement Co");
});
