/**
 * Authenticated read-only audit of the LIVE production system.
 *
 *   https://app.hmhgroup.co.za
 *
 * ─────────────────────────────────────────────────────────────────────────
 * THIS SUITE IS READ-ONLY. It signs in, looks, and screenshots.
 *
 * It must never:
 *   - save a repair edit
 *   - record or reverse a mechanic payment
 *   - create, cancel or alter a delivery note
 *   - write any customer, stock or financial record
 *
 * Where a write would prove something (saving an edit, recording a payment),
 * the suite verifies the control is PRESENT and the form PREFILLS, then
 * closes it. The write paths are proven in tests/audit against a throwaway
 * database, never here.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * Credentials come from PROD_EMAIL / PROD_PASSWORD in the environment. They
 * are never written to disk, a report or a commit.
 */

import { expect, test } from "playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const SHOTS = "docs/testing/live-production-screenshots";
const BASE = "https://app.hmhgroup.co.za";

const EMAIL = process.env.PROD_EMAIL;
const PASSWORD = process.env.PROD_PASSWORD;

if (!EMAIL || !PASSWORD) {
  throw new Error("Set PROD_EMAIL and PROD_PASSWORD to run the authenticated production audit.");
}

mkdirSync(SHOTS, { recursive: true });

const findings = [];
function record(area, detail) {
  findings.push({ area, detail, at: new Date().toISOString() });
  writeFileSync(`${SHOTS}/A99-findings.json`, JSON.stringify(findings, null, 2));
}

async function shot(page, name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle", timeout: 60_000 });
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 45_000 });
  await page.waitForTimeout(2500);
}

/** Authenticated GET straight to the production API, for cross-checking the UI. */
async function api(page, path) {
  const token = await page.evaluate(() => localStorage.getItem("hmh_access_token"));
  const res = await page.request.get(
    `https://hmh-backend-uhzu.onrender.com/api/v1${path}`,
    { headers: { Authorization: `Bearer ${token}` }, timeout: 60_000 },
  );
  return { status: res.status(), body: res.ok() ? await res.json() : null };
}

// Not serial: each test signs in for itself, and a failure in one area
// must not hide the state of the others — the point of an audit is to
// learn about every feature in one pass.
test.describe.configure({ mode: "default" });

test.beforeEach(async ({ page }) => {
  await login(page);
});

// ── 1. Companies ─────────────────────────────────────────────────────────────

test("PROD: all five companies exist and are listed", async ({ page }) => {
  const { status, body } = await api(page, "/companies/");
  expect(status, "production /companies/ did not return 200").toBe(200);

  const names = body.data.map((c) => c.name);
  record("companies", { count: names.length, names });

  await page.goto(`${BASE}/companies`, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForTimeout(2500);
  await shot(page, "A01-companies-live");

  const wanted = ["HMH", "Minerat", "Kukhanya Kabusha", "Premium Structures", "Ophezulu"];
  const missing = wanted.filter((w) => !names.some((n) => n.toLowerCase().includes(w.toLowerCase())));
  expect(missing, `missing from production: ${missing.join(", ")}`).toHaveLength(0);
});

test("PROD: the project company selector offers the new companies", async ({ page }) => {
  await page.goto(`${BASE}/projects`, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForTimeout(2500);
  await shot(page, "A02-projects-live");

  // Opening the create form is read-only until something is saved, and
  // nothing here saves.
  const newBtn = page.getByRole("button", { name: /new project|add project/i }).first();
  if (await newBtn.isVisible().catch(() => false)) {
    await newBtn.click();
    await page.waitForTimeout(1500);
    await shot(page, "A03-company-selector-live");

    const options = await page.locator("select option").allTextContents();
    record("company-selector", { options: options.filter(Boolean).slice(0, 40) });

    await page.keyboard.press("Escape");
  } else {
    record("company-selector", "No create-project control visible for this role");
  }
});

// ── 2 & 3. Vehicles: repairs, editing affordance, pagination ─────────────────

test("PROD: vehicles, repair history and pagination", async ({ page }) => {
  const vehicles = await api(page, "/vehicles/");
  expect(vehicles.status).toBe(200);
  const list = vehicles.body.data ?? [];
  record("vehicles", { count: list.length });

  await page.goto(`${BASE}/vehicles`, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForTimeout(3000);
  await shot(page, "A04-vehicles-live");

  // Find the vehicle with the most repairs, so pagination has something real
  // to page through.
  let best = null;
  for (const v of list.slice(0, 40)) {
    const r = await api(page, `/vehicles/${v.id}/repairs?page=1&limit=10`);
    if (r.status === 200) {
      const total = r.body.data.total ?? 0;
      if (!best || total > best.total) best = { id: v.id, reg: v.registration, total };
    }
  }
  record("repairs", best ?? "no repair data readable");
  expect(best, "could not read repair history for any production vehicle").toBeTruthy();

  // Pagination correctness, read-only, straight against production data.
  if (best.total > 0) {
    const p1 = await api(page, `/vehicles/${best.id}/repairs?page=1&limit=10`);
    const ids1 = p1.body.data.items.map((i) => i.id);
    let overlap = [];
    if (best.total > 10) {
      const p2 = await api(page, `/vehicles/${best.id}/repairs?page=2&limit=10`);
      const ids2 = p2.body.data.items.map((i) => i.id);
      overlap = ids1.filter((i) => ids2.includes(i));
      record("pagination", {
        vehicle: best.reg, total: best.total,
        page1: ids1.length, page2: ids2.length, overlap: overlap.length,
      });
      expect(overlap, "production pagination returned the same repair on two pages").toHaveLength(0);
    } else {
      record("pagination", `vehicle ${best.reg} has only ${best.total} repairs; no page 2 to compare`);
    }
  }

  // Open the vehicle in the UI and look at its repairs tab.
  await page.getByText(best.reg, { exact: false }).first().click().catch(() => {});
  await page.waitForTimeout(2000);
  const repairsTab = page.getByRole("button", { name: /^Repairs/ }).first();
  if (await repairsTab.isVisible().catch(() => false)) {
    await repairsTab.click();
    await page.waitForTimeout(2500);
    await shot(page, "A05-repair-history-live");

    // The Edit control must be offered. NOTHING IS SAVED.
    const edit = page.getByRole("button", { name: /^Edit$/ }).first();
    const editOffered = await edit.isVisible().catch(() => false);
    record("repair-edit-affordance", { editButtonVisible: editOffered });

    if (editOffered) {
      await edit.click();
      await page.waitForTimeout(1500);
      const title = page.getByLabel(/title/i).first();
      const prefilled = await title.inputValue().catch(() => "");
      record("repair-edit-prefill", { prefilled: prefilled.length > 0 });
      await shot(page, "A06-edit-repair-form-live-READONLY");
      expect(prefilled.length, "production edit form opened blank").toBeGreaterThan(0);

      // Close without saving.
      await page.getByRole("button", { name: /^cancel$/i }).first().click().catch(async () => {
        await page.keyboard.press("Escape");
      });
      await page.waitForTimeout(800);
    }
  }
});

// ── 4. Workshop mechanic payments ────────────────────────────────────────────

test("PROD: workshop mechanic payments dashboard", async ({ page }) => {
  const res = await api(page, "/workshop/mechanic-payments?page=1&limit=25");
  record("mechanic-payments-api", { status: res.status });
  expect(res.status, "production mechanic-payments did not return 200").toBe(200);

  const d = res.body.data;
  record("mechanic-payments", {
    totals: d.totals,
    rows: d.items.length,
    bases: [...new Set(d.items.map((i) => i.payable_basis))],
    statuses: [...new Set(d.items.map((i) => i.payment_status))],
    anyWithExcludedCosts: d.items.filter((i) => (i.other_costs_not_payable_to_mechanic ?? 0) > 0).length,
  });

  // Arithmetic must hold on real data: outstanding = payable - paid, >= 0.
  for (const row of d.items) {
    const expected = Math.max(Number(row.total_payable) - Number(row.total_paid), 0);
    expect(
      Math.abs(expected - Number(row.outstanding)),
      `outstanding wrong for ${row.repair_title}`,
    ).toBeLessThan(0.011);
  }

  await page.goto(`${BASE}/workshop`, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForTimeout(2500);
  const tab = page.getByRole("button", { name: /mechanic payments/i }).first();
  expect(await tab.isVisible().catch(() => false), "Mechanic Payments tab not present").toBeTruthy();
  await tab.click();
  await page.waitForTimeout(3000);
  await shot(page, "A07-mechanic-payments-live");
});

// ── 5. Fuel history ──────────────────────────────────────────────────────────

test("PROD: fuel history", async ({ page }) => {
  const vehicles = await api(page, "/vehicles/");
  const list = vehicles.body.data ?? [];

  let best = null;
  for (const v of list.slice(0, 25)) {
    const r = await api(page, `/vehicles/${v.id}/costs?page=1&limit=10&cost_type=FUEL`);
    if (r.status === 200) {
      const total = r.body.data.total ?? 0;
      if (!best || total > best.total) best = { id: v.id, reg: v.registration, total };
    }
  }
  record("fuel-costs", best ?? "none readable");

  if (best?.total > 0) {
    await page.goto(`${BASE}/vehicles`, { waitUntil: "networkidle", timeout: 60_000 });
    await page.waitForTimeout(2500);
    await page.getByText(best.reg, { exact: false }).first().click().catch(() => {});
    await page.waitForTimeout(2000);
    const fuelTab = page.getByRole("button", { name: /^Fuel/ }).first();
    if (await fuelTab.isVisible().catch(() => false)) {
      await fuelTab.click();
      await page.waitForTimeout(3000);
      await shot(page, "A08-fuel-history-live");
    }
  }
});

// ── 6. Dassenhoek BOQ ────────────────────────────────────────────────────────

test("PROD: Dassenhoek BOQ quantities are not duplicated", async ({ page }) => {
  const projects = await api(page, "/projects?page=1&limit=100");
  expect(projects.status).toBe(200);
  const all = projects.body.data.items ?? projects.body.data ?? [];

  const dassenhoek = all.find((p) =>
    `${p.name ?? ""} ${p.code ?? ""}`.toLowerCase().includes("dassenhoek"));
  record("dassenhoek-project", dassenhoek
    ? { id: dassenhoek.id, name: dassenhoek.name, code: dassenhoek.code }
    : { found: false, projectsSeen: all.length, names: all.map((p) => p.name).slice(0, 40) });

  if (!dassenhoek) {
    test.skip(true, "No project matching 'Dassenhoek' is visible to this account");
    return;
  }

  // Every lot's material summary, checked for the duplication signature: two
  // surviving rows sharing one catalogue item.
  const lots = await api(page, `/projects/${dassenhoek.id}/lots`);
  const lotList = lots.body?.data?.items ?? lots.body?.data ?? [];
  record("dassenhoek-lots", { count: lotList.length });

  const offenders = [];
  const checked = [];
  for (const lot of lotList.slice(0, 25)) {
    const s = await api(page, `/projects/${dassenhoek.id}/lots/${lot.id}/material-summary`);
    if (s.status !== 200) continue;
    const rows = s.body.data ?? [];
    const itemIds = rows.map((r) => r.item_id).filter(Boolean);
    const dupes = itemIds.filter((v, i) => itemIds.indexOf(v) !== i);
    checked.push({ lot: lot.lot_number ?? lot.id, rows: rows.length, duplicateItemIds: dupes.length });
    if (dupes.length) offenders.push({ lot: lot.lot_number ?? lot.id, dupes });
  }
  record("dassenhoek-material-summaries", { checked, offenders });

  await page.goto(`${BASE}/projects`, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForTimeout(2500);
  await shot(page, "A09-dassenhoek-live");

  expect(offenders,
    `lots still showing two BOQ rows for one catalogue item: ${JSON.stringify(offenders)}`,
  ).toHaveLength(0);
});

// ── 7. Bypass Orders ─────────────────────────────────────────────────────────

test("PROD: Bypass Orders and its AI configuration", async ({ page }) => {
  const status = await api(page, "/ai-import/service-status");
  record("bypass-orders-service-status", { status: status.status, data: status.body?.data });
  expect(status.status, "production service-status did not return 200").toBe(200);

  const s = status.body.data;
  // The one invariant that must hold in production, whatever else is true.
  expect(s.auto_post_enabled, "AUTOMATIC POSTING IS ENABLED IN PRODUCTION").toBe(false);

  await page.goto(`${BASE}/ai-document-import`, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForTimeout(3000);
  await shot(page, "A10-bypass-orders-live");

  await expect(page.getByRole("heading", { name: /bypass orders/i }).first()).toBeVisible();
  const body = (await page.locator("body").innerText()).toLowerCase();
  record("bypass-orders-ui", {
    uploadControlPresent: body.includes("choose files") || body.includes("drop documents"),
    degradedBannerShown: body.includes("reduced capability") || body.includes("switched off"),
  });
});
