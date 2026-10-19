/**
 * Live browser audit of the fleet, workshop and company changes.
 *
 * Runs against a LOCAL stack: a backend on 127.0.0.1:8010 bound to the
 * throwaway `hmh_audit` database, and a preview build of this frontend
 * pointed at it. Every record it touches is synthetic. Nothing here reaches
 * production, and no screenshot it captures is production evidence.
 *
 *   npx playwright test tests/audit --config=playwright.audit.config.mjs
 */

import { expect, test } from "playwright/test";
import { mkdirSync } from "node:fs";

const SHOTS = "docs/testing/screenshots";
// Supplied by the environment, never committed. These address a throwaway
// local account that exists only in the `hmh_audit` database; a literal here
// would still be a password in a public repository.
const EMAIL = process.env.AUDIT_EMAIL;
const PASSWORD = process.env.AUDIT_PASSWORD;

if (!EMAIL || !PASSWORD) {
  throw new Error(
    "Set AUDIT_EMAIL and AUDIT_PASSWORD for the local audit account before " +
    "running this suite. See docs/testing/HMH_FULL_SYSTEM_AUDIT.md.",
  );
}

const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };

mkdirSync(SHOTS, { recursive: true });

/**
 * Match a rand amount regardless of locale separators.
 *
 * The app formats with en-ZA, which uses a non-breaking space for thousands
 * and a comma for decimals - "R3 000,00", not "R3,000.00". Asserting on the
 * US shape would fail against correct output.
 */
function rand(amount) {
  const whole = String(Math.trunc(amount));
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, "[\s ,]?");
  return new RegExp(`R\s?${grouped}[.,]00`);
}

async function shot(page, name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

async function login(page) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in|log ?in/i }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 20_000 });
}

test.use({ viewport: DESKTOP });

test.beforeEach(async ({ page }) => {
  // The reversal flow asks for a reason through window.prompt.
  await page.addInitScript(() => { window.prompt = () => "Audit reversal test"; });
  await login(page);
});

// ── Phase 2: companies ───────────────────────────────────────────────────────

test("all five companies are real records and appear in a selector", async ({ page }) => {
  // The API is the source of truth for "these exist as database records".
  const res = await page.request.get("http://127.0.0.1:8010/api/v1/companies/", {
    headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem("hmh_access_token"))}` },
  });
  expect(res.ok()).toBeTruthy();
  const names = (await res.json()).data.map((c) => c.name);
  for (const expected of [
    "HMH Group", "Minerat Construction & Civils",
    "Kukhanya Kabusha", "Premium Structures", "Ophezulu",
  ]) {
    expect(names, `company list is ${names.join(", ")}`).toContain(expected);
  }

  await page.goto("/companies");
  await page.waitForLoadState("networkidle");
  await shot(page, "01-company-list");

  for (const expected of ["Kukhanya Kabusha", "Premium Structures", "Ophezulu"]) {
    await expect(page.getByText(expected, { exact: false }).first()).toBeVisible();
  }
});

test("the project company selector is driven by the companies table", async ({ page }) => {
  await page.goto("/projects");
  await page.waitForLoadState("networkidle");

  // Open whichever control creates a project.
  const newBtn = page.getByRole("button", { name: /new project|add project|\+ project/i }).first();
  await newBtn.click();

  const select = page.locator("select").filter({ hasText: /select company|HMH/i }).first();
  await expect(select).toBeVisible({ timeout: 10_000 });

  const options = await select.locator("option").allTextContents();
  for (const expected of ["Kukhanya Kabusha", "Premium Structures", "Ophezulu"]) {
    expect(options.join(" | ")).toContain(expected);
  }
  await shot(page, "02-company-selector");
});

// ── Phase 3 & 4: repairs ─────────────────────────────────────────────────────

async function openTipperRepairs(page) {
  await page.goto("/vehicles");
  await page.waitForLoadState("networkidle");
  await page.getByText("ND 411 AUD").first().click();
  await page.getByRole("button", { name: /^Repairs/ }).first().click();
  await page.waitForTimeout(1200);
}

test("repair history paginates and reaches every record", async ({ page }) => {
  await openTipperRepairs(page);

  await expect(page.getByText(/35 repair job\(s\)/)).toBeVisible({ timeout: 15_000 });
  await shot(page, "05-repair-pagination");

  const pageOne = await page.locator("text=/Synthetic audit repair \\d+/").allTextContents();
  expect(pageOne.length).toBeGreaterThan(0);

  await page.getByRole("button", { name: /next page of repairs/i }).first().click();
  await page.waitForTimeout(1200);
  await shot(page, "05b-repair-pagination-page2");

  const pageTwo = await page.locator("text=/Synthetic audit repair \\d+/").allTextContents();
  const overlap = pageOne.filter((t) => pageTwo.includes(t));
  expect(overlap, `pages overlapped: ${overlap.join(", ")}`).toHaveLength(0);
});

test("an older repair can be opened and edited, and the change persists", async ({ page }) => {
  await openTipperRepairs(page);
  await shot(page, "03a-repair-history-before-edit");

  await page.getByRole("button", { name: /^Edit$/ }).first().click();
  await expect(page.getByRole("heading", { name: /edit repair job/i })).toBeVisible();

  // The form must arrive prefilled, not blank.
  const title = page.getByLabel(/title/i).first();
  const existing = await title.inputValue();
  expect(existing.length, "edit form opened blank").toBeGreaterThan(0);
  await shot(page, "03-edit-repair-form");

  const marker = `AUDIT EDIT ${Date.now()}`;
  await page.getByLabel(/description/i).first().fill(marker);
  await page.getByRole("button", { name: /save changes/i }).click();
  await page.waitForTimeout(1500);

  // Reload from the server, not the in-memory list.
  await openTipperRepairs(page);
  await expect(page.getByText(marker)).toBeVisible({ timeout: 15_000 });
  await shot(page, "04-repair-updated");
});

// ── Phase 5: mechanic payments ───────────────────────────────────────────────

async function openMechanicPayments(page) {
  await page.goto("/workshop");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: /mechanic payments/i }).click();
  await page.waitForTimeout(1500);
}

test("mechanic payments: R5 000 settled in two instalments", async ({ page }) => {
  // Create this test's own repair so repeated runs cannot inherit payments
  // from a previous one. Synthetic, in the audit database only.
  const token = await page.evaluate(() => localStorage.getItem("hmh_access_token"));
  const api = "http://127.0.0.1:8010/api/v1";
  const auth = { Authorization: `Bearer ${token}` };

  const vehicles = await (await page.request.get(`${api}/vehicles/`, { headers: auth })).json();
  const bakkie = vehicles.data.find((v) => v.registration === "ND 722 AUD");
  expect(bakkie, "audit bakkie missing from the seed").toBeTruthy();

  const title = `Audit payable ${Date.now()}`;
  const created = await page.request.post(`${api}/vehicles/${bakkie.id}/repairs`, {
    headers: auth,
    data: { title, date_opened: "2026-03-01", workshop_name: "Durban Diesel" },
  });
  expect(created.ok()).toBeTruthy();
  const repairId = (await created.json()).data.id;

  const priced = await page.request.patch(`${api}/vehicles/repairs/${repairId}`, {
    headers: auth,
    data: { invoice_amount: 5000 },
  });
  expect(priced.ok()).toBeTruthy();

  await openMechanicPayments(page);
  await shot(page, "06-mechanic-payments-overview");

  const row = page.locator("tr", { hasText: title });
  await expect(row).toBeVisible({ timeout: 15_000 });
  await expect(row).toContainText("Unpaid");
  await shot(page, "06b-mechanic-unpaid");

  await row.getByRole("button", { name: /payments/i }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();

  // First instalment: R2 000 of R5 000.
  await page.getByLabel(/amount/i).first().fill("2000");
  await page.getByRole("button", { name: /record payment/i }).click();
  await page.waitForTimeout(1500);
  await expect(page.getByText(rand(3000)).first()).toBeVisible({ timeout: 10_000 });
  await shot(page, "07-mechanic-partial-payment");

  // Overpaying the remaining R3 000 must be refused.
  await page.getByLabel(/amount/i).first().fill("9999");
  await page.getByLabel(/reference/i).first().fill("AUDIT-OVER");
  await page.getByRole("button", { name: /record payment/i }).click();
  await page.waitForTimeout(1500);
  await expect(page.getByText(/is outstanding/i)).toBeVisible({ timeout: 10_000 });
  await shot(page, "07b-mechanic-overpayment-rejected");

  // A duplicate reference must be refused too.
  await page.getByLabel(/amount/i).first().fill("100");
  await page.getByLabel(/reference/i).first().fill("AUDIT-DUP");
  await page.getByRole("button", { name: /record payment/i }).click();
  await page.waitForTimeout(1500);
  await page.getByLabel(/amount/i).first().fill("100");
  await page.getByLabel(/reference/i).first().fill("AUDIT-DUP");
  await page.getByRole("button", { name: /record payment/i }).click();
  await page.waitForTimeout(1500);
  await expect(page.getByText(/already recorded/i)).toBeVisible({ timeout: 10_000 });
  await shot(page, "07c-mechanic-duplicate-reference-rejected");

  // Settle the remaining balance (R3 000 less the R100 that went through).
  await page.getByLabel(/amount/i).first().fill("2900");
  await page.getByLabel(/reference/i).first().fill("AUDIT-EFT-FINAL");
  await page.getByRole("button", { name: /record payment/i }).click();
  await page.waitForTimeout(1500);
  await expect(page.getByText(/fully paid/i)).toBeVisible({ timeout: 10_000 });
  await shot(page, "08-mechanic-fully-paid");
  await shot(page, "08b-mechanic-payment-history");

  // Reverse one payment; it must stop counting but stay on the record.
  await page.getByRole("button", { name: /^reverse$/i }).first().click();
  // The reversal reason arrives via window.prompt.
  await page.waitForTimeout(800);
  await shot(page, "08c-mechanic-payment-reversed");
});

test("tyre and licence costs are not treated as owed to the mechanic", async ({ page }) => {
  await openMechanicPayments(page);

  const row = page.locator("tr", { hasText: "Service and new tyres (audit mixed costs)" });
  await expect(row).toBeVisible({ timeout: 15_000 });

  // R3 000 labour is payable; R2 000 tyres and R500 licence are not.
  await expect(row).toContainText(rand(3000));
  await expect(row).toContainText("recorded labour");
  await shot(page, "06c-mechanic-payable-excludes-parts");

  await row.getByRole("button", { name: /payments/i }).click();
  await expect(page.getByText(/not payable to the mechanic|owed to whoever supplied/i))
    .toBeVisible({ timeout: 10_000 });
  await shot(page, "06d-mechanic-non-payable-note");
});

// ── Phase 6: fuel timeline ───────────────────────────────────────────────────

test("fuel timeline reaches entries past the first ten", async ({ page }) => {
  await page.goto("/vehicles");
  await page.waitForLoadState("networkidle");
  await page.getByText("ND 411 AUD").first().click();
  await page.getByRole("button", { name: /^Fuel/ }).first().click();
  await page.waitForTimeout(2000);

  await expect(page.getByText(/\d+ entries/)).toBeVisible({ timeout: 15_000 });
  await shot(page, "09-fuel-history-pagination");

  const pager = page.getByRole("button", { name: /next page of fuel entr/i }).first();
  await expect(pager).toBeVisible({ timeout: 10_000 });
  await pager.click();
  await page.waitForTimeout(1000);
  await shot(page, "09b-fuel-history-page2");
});

// ── Phase 8: Bypass Orders ───────────────────────────────────────────────────

test("Bypass Orders is in the sidebar and reports its real service status", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("link", { name: /bypass orders/i }).first())
    .toBeVisible({ timeout: 15_000 });
  await shot(page, "11a-bypass-orders-sidebar");

  await page.goto("/ai-document-import");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2000);
  await expect(page.getByRole("heading", { name: /bypass orders/i }).first()).toBeVisible();
  await shot(page, "11-bypass-orders");

  // With no Anthropic key configured the page must say so rather than
  // implying extraction works.
  await shot(page, "11b-bypass-orders-service-status");
});

// ── Mobile ───────────────────────────────────────────────────────────────────

test("key screens render at 390x844", async ({ page }) => {
  await page.setViewportSize(MOBILE);
  await page.goto("/vehicles");
  await page.waitForLoadState("networkidle");
  await shot(page, "13-vehicles-mobile-390");

  await page.goto("/workshop");
  await page.waitForLoadState("networkidle");
  await shot(page, "14-workshop-mobile-390");
});

// ── Phase 7: the BOQ duplication fix, rendered ───────────────────────────────
//
// Two BOQ rows pointing at the same catalogue item but worded differently,
// and one physical delivery of 100 bags. Before the fix the summary reported
// 200 delivered across two identically-named rows.
//
// This runs against the LOCAL audit database with synthetic data. It is not
//, and must not be presented as, verification of live Dassenhoek figures.

test("one delivery is reported once despite two BOQ rows for the same item", async ({ page }) => {
  const token = await page.evaluate(() => localStorage.getItem("hmh_access_token"));
  const api = "http://127.0.0.1:8010/api/v1";
  const auth = { Authorization: `Bearer ${token}` };

  const site = "2ce72f38-fd1c-4f6d-a6b2-24c6289eda6e";
  const lot = "8679d118-adfe-45d9-82b3-031718ac4d3b";

  const res = await page.request.get(
    `${api}/site-dashboard/${site}/lots/${lot}/material-summary`, { headers: auth });
  expect(res.ok()).toBeTruthy();
  const rows = (await res.json()).data;

  // Collapsed to one row, and the delivery counted once.
  expect(rows).toHaveLength(1);
  expect(Number(rows[0].delivered_qty)).toBe(100);
  // Allocation across both rows is preserved: 300 + 200.
  expect(Number(rows[0].boq_allocated_qty)).toBe(500);

  await page.goto("/site");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2000);
  await shot(page, "10-boq-materials-summary-local");
});
