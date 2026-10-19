/**
 * Correcting a vehicle cost, in the browser.
 *
 * The reported gap: a repair description could be edited, but a cost entry
 * could not — there was no update endpoint and the rows rendered read-only.
 *
 * Runs against the local audit stack. Every record is synthetic.
 */

import { expect, test } from "playwright/test";
import { mkdirSync } from "node:fs";

const SHOTS = "docs/testing/screenshots";
const EMAIL = process.env.AUDIT_EMAIL;
const PASSWORD = process.env.AUDIT_PASSWORD;

if (!EMAIL || !PASSWORD) {
  throw new Error("Set AUDIT_EMAIL and AUDIT_PASSWORD to run the cost-editing audit.");
}

mkdirSync(SHOTS, { recursive: true });

async function login(page) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 30_000 });
}

async function openCosts(page) {
  await page.goto("/vehicles");
  await page.waitForLoadState("networkidle");
  await page.getByText("ND 411 AUD").first().click();
  await page.getByRole("button", { name: /^Costs/ }).first().click();
  await page.waitForTimeout(1500);
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("a cost entry offers an Edit control and the form prefills", async ({ page }) => {
  await openCosts(page);
  await page.screenshot({ path: `${SHOTS}/18-cost-list-with-edit.png` });

  const edit = page.getByRole("button", { name: /^Edit cost/i }).first();
  await expect(edit, "no Edit control on a cost row").toBeVisible({ timeout: 10_000 });
  await edit.click();

  await expect(page.getByRole("heading", { name: /edit cost/i })).toBeVisible();

  // Prefilled from the saved record, not blank.
  const amount = page.getByLabel(/amount/i).first();
  const existing = await amount.inputValue();
  expect(Number(existing), "edit form opened with an empty amount").toBeGreaterThan(0);
  await page.screenshot({ path: `${SHOTS}/19-edit-cost-form.png` });
});

test("a corrected cost persists after a reload", async ({ page }) => {
  await openCosts(page);

  await page.getByRole("button", { name: /^Edit cost/i }).first().click();
  await expect(page.getByRole("heading", { name: /edit cost/i })).toBeVisible();

  const marker = `Audit corrected ${Date.now()}`;
  await page.getByLabel(/amount/i).first().fill("1234.56");
  await page.getByLabel(/description/i).first().fill(marker);
  await page.getByRole("button", { name: /save changes/i }).click();
  await page.waitForTimeout(1500);

  // Re-read from the server rather than trusting the in-memory list.
  await openCosts(page);
  await expect(page.getByText(marker)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/1[\s,]?234\.56|1[\s ]234,56/).first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/20-cost-corrected.png` });
});
