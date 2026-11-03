/**
 * Deleting a duplicated vehicle cost, in the browser.
 *
 * Reproduces the reported case: a vehicle carrying the same cost line twice
 * on the same date, which doubles that vehicle's spend until one is removed.
 *
 * Runs against the local demo stack. The registration and the part numbers
 * are invented; `test` comes from the local-only guard, so nothing can reach
 * a remote host.
 */

import { expect, test } from "../support/local-only.mjs";
import { mkdirSync } from "node:fs";

const SHOTS = "docs/testing/screenshots/vehicle-cost-delete";
const EMAIL = process.env.AUDIT_EMAIL;
const PASSWORD = process.env.AUDIT_PASSWORD;

if (!EMAIL || !PASSWORD) {
  throw new Error("Set AUDIT_EMAIL and AUDIT_PASSWORD to run the cost-delete audit.");
}
mkdirSync(SHOTS, { recursive: true });

test.use({ serviceWorkers: "block" });

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
  await page.getByText("4CXJCB").first().click();
  const costsTab = page.getByRole("button", { name: /^Costs/ }).first();
  await expect(costsTab).toBeVisible({ timeout: 20_000 });
  await costsTab.click();
  await expect(page.getByText(/GRILL LOCKS/).first()).toBeVisible({ timeout: 20_000 });
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("every cost row offers Delete beside Edit", async ({ page }) => {
  await openCosts(page);
  await page.screenshot({ path: `${SHOTS}/01-costs-with-delete.png`, fullPage: true });

  const edits = await page.getByRole("button", { name: /^Edit cost/ }).count();
  const deletes = await page.getByRole("button", { name: /^Delete cost/ }).count();
  expect(edits).toBeGreaterThan(0);
  expect(deletes).toBe(edits);
});

test("the confirmation names the amount and the description", async ({ page }) => {
  /**
   * On a list of near identical rows, "are you sure?" does not tell anybody
   * which one they are about to remove.
   */
  await openCosts(page);

  let message = "";
  page.once("dialog", async (dialog) => {
    message = dialog.message();
    await dialog.dismiss();
  });
  await page.getByRole("button", { name: /^Delete cost GRILL LOCKS/ }).first().click();
  await expect.poll(() => message, { timeout: 10_000 }).not.toBe("");

  expect(message).toContain("GRILL LOCKS");
  expect(message).toContain("138");
  expect(message).toContain("2026-06-23");
});

test("dismissing the confirmation deletes nothing", async ({ page }) => {
  await openCosts(page);
  const before = await page.getByRole("button", { name: /^Delete cost/ }).count();

  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: /^Delete cost GRILL LOCKS/ }).first().click();
  await page.waitForTimeout(1500);

  expect(await page.getByRole("button", { name: /^Delete cost/ }).count()).toBe(before);
});

test("confirming removes that row and leaves the other one", async ({ page }) => {
  await openCosts(page);

  const grillBefore = await page.getByText(/GRILL LOCKS/).count();
  expect(grillBefore, "the duplicate should be seeded twice").toBe(2);
  const rowsBefore = await page.getByRole("button", { name: /^Delete cost/ }).count();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: /^Delete cost GRILL LOCKS/ }).first().click();

  await expect
    .poll(async () => page.getByRole("button", { name: /^Delete cost/ }).count(),
          { timeout: 20_000 })
    .toBe(rowsBefore - 1);

  // One of the pair stays: the entry was duplicated, not wrong.
  await expect(page.getByText(/GRILL LOCKS/)).toHaveCount(1);
  await page.screenshot({ path: `${SHOTS}/02-duplicate-removed.png`, fullPage: true });
});

test("the removal survives a reload", async ({ page }) => {
  await page.goto("/vehicles");
  await page.waitForLoadState("networkidle");
  await page.getByText("4CXJCB").first().click();
  await page.getByRole("button", { name: /^Costs/ }).first().click();
  await page.waitForTimeout(2000);

  // The previous test removed one of the pair; it must not come back.
  await expect(page.getByText(/GRILL LOCKS/)).toHaveCount(1);
});
