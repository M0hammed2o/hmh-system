/**
 * Read-only confirmation that the cost Edit control is live in production.
 * Opens the form to show it prefills, then closes it WITHOUT saving.
 * No production record is modified.
 */
import { expect, test } from "playwright/test";
import { mkdirSync } from "node:fs";
const SHOTS = "docs/testing/live-production-screenshots";
mkdirSync(SHOTS, { recursive: true });

test("PROD: a vehicle cost offers Edit and the form prefills", async ({ page }) => {
  await page.goto("https://app.hmhgroup.co.za/login", { waitUntil: "networkidle" });
  await page.getByLabel(/email/i).fill(process.env.PROD_EMAIL);
  await page.getByLabel(/password/i).fill(process.env.PROD_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 45_000 });

  await page.goto("https://app.hmhgroup.co.za/vehicles", { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  await page.getByText("BW13SX-ZN").first().click();
  await page.getByRole("button", { name: /^Costs/ }).first().click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${SHOTS}/A11-cost-edit-live.png` });

  const edit = page.getByRole("button", { name: /^Edit cost/i }).first();
  await expect(edit, "no Edit control on a production cost row").toBeVisible({ timeout: 15_000 });

  await edit.click();
  await expect(page.getByRole("heading", { name: /edit cost/i })).toBeVisible();
  const amount = await page.getByLabel(/amount/i).first().inputValue();
  expect(Number(amount), "production edit form opened empty").toBeGreaterThan(0);
  await page.screenshot({ path: `${SHOTS}/A12-cost-edit-form-live-READONLY.png` });

  // Close without saving — nothing is written to production.
  await page.getByRole("button", { name: /^cancel$/i }).first().click();
  await page.waitForTimeout(500);
});
