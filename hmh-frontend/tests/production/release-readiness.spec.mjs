/**
 * Read-only pre-release check of the live site.
 *
 * Runs against https://app.hmhgroup.co.za as it stands TODAY — before the
 * release. Its job is to record the baseline: what works now, and which of
 * the new screens are genuinely not there yet because the backend has not
 * been deployed.
 *
 * Strictly read-only. It navigates, reads and screenshots. It creates
 * nothing, edits nothing, posts nothing and imports nothing.
 *
 * Screenshots are written outside the repository, because they are pictures
 * of the live system and this repository is public.
 */

import { expect, test } from "playwright/test";
import { mkdirSync } from "node:fs";

const SHOTS = process.env.SHOT_DIR;
const EMAIL = process.env.PROD_EMAIL;
const PASSWORD = process.env.PROD_PASSWORD;

if (!SHOTS || !EMAIL || !PASSWORD) {
  throw new Error("Set SHOT_DIR, PROD_EMAIL and PROD_PASSWORD.");
}
mkdirSync(SHOTS, { recursive: true });

const BASE = "https://app.hmhgroup.co.za";

test.use({ baseURL: BASE, serviceWorkers: "block" });

async function login(page) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 60_000 });
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("company selectors are populated", async ({ page }) => {
  await page.goto("/companies");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2500);
  const body = await page.locator("body").innerText();
  console.log("COMPANIES PAGE:", body.replace(/\n+/g, " | ").slice(0, 400));
  await page.screenshot({ path: `${SHOTS}/01-companies.png`, fullPage: true });
});

test("bypass orders loads and reports its capability", async ({ page }) => {
  await page.goto("/ai-document-import");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(3000);
  const body = await page.locator("body").innerText();
  console.log("BYPASS TABS:", (body.match(/Import Documents|Batch Review|Documents|Reconciliation/g) || []).join(","));
  console.log("BYPASS NOTICE:", (body.match(/reduced capability[\s\S]{0,260}/) || [""])[0].replace(/\n+/g, " | "));
  await page.screenshot({ path: `${SHOTS}/02-bypass-orders.png`, fullPage: true });
});

test("payments: tabs, and whether pending charges is live yet", async ({ page }) => {
  await page.goto("/payments");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(3000);
  const buttons = await page.getByRole("button").evaluateAll(
    (els) => els.map((e) => e.textContent.trim()).filter(Boolean),
  );
  console.log("PAYMENTS BUTTONS:", buttons.join(" | ").slice(0, 400));
  await page.screenshot({ path: `${SHOTS}/03-payments.png`, fullPage: true });
});

test("invoices: every supplier payable and its status", async ({ page }) => {
  await page.goto("/payments");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2500);
  const invoices = page.getByRole("button", { name: /^Invoices/i });
  await expect(invoices).toBeVisible({ timeout: 30_000 });
  await invoices.click();
  await page.waitForTimeout(2500);
  const body = await page.locator("body").innerText();
  console.log("INVOICE STATUSES:", (body.match(/\b(DRAFT|UNPAID|PARTIALLY_PAID|PAID|OVERPAID|MATCHED|RECEIVED)\b/g) || []).join(","));
  console.log("INVOICES TEXT:", body.replace(/\n+/g, " | ").slice(0, 500));
  await page.screenshot({ path: `${SHOTS}/04-invoices.png`, fullPage: true });
});

test("stock and warehouse screens load", async ({ page }) => {
  for (const [path, name] of [["/main-warehouse", "05-main-warehouse"],
                              ["/project-warehouse", "06-project-warehouse"]]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2500);
    const body = await page.locator("body").innerText();
    console.log(`${path}:`, body.replace(/\n+/g, " | ").slice(0, 260));
    await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
  }
});

test("dassenhoek BOQ loads", async ({ page }) => {
  await page.goto("/boq");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(3500);
  const body = await page.locator("body").innerText();
  console.log("BOQ:", body.replace(/\n+/g, " | ").slice(0, 400));
  await page.screenshot({ path: `${SHOTS}/07-boq.png`, fullPage: true });
});
