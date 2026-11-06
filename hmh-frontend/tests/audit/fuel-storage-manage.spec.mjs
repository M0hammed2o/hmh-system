/**
 * Managing a fuel storage location in the browser: price per litre, edit, and
 * remove.
 *
 * Reproduces the reported case. The Stock & Reconciliation screen could only
 * create and list tanks, so a wrong name meant a second tank beside the first,
 * a test tank stayed forever, and nothing on the screen could record what the
 * fuel cost.
 *
 * Runs against the local audit stack, seeded by
 * hmh-backend/scripts/seed_fuel_storage_audit.py. `test` comes from the
 * local-only guard, so nothing here can reach a remote host. Screenshots are
 * written outside the repository, because production screenshots must never be
 * committed and a path inside docs/ is one careless `git add -A` from being.
 */

import { expect, test } from "../support/local-only.mjs";
import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const SHOTS = process.env.FUEL_AUDIT_SHOTS ?? join(tmpdir(), "hmh-fuel-storage-audit");
const EMAIL = process.env.AUDIT_EMAIL;
const PASSWORD = process.env.AUDIT_PASSWORD;
const PROJECT = process.env.AUDIT_FUEL_PROJECT ?? "Fuel Audit Project";

if (!EMAIL || !PASSWORD) {
  throw new Error("Set AUDIT_EMAIL and AUDIT_PASSWORD to run the fuel storage audit.");
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

async function openStock(page) {
  await page.goto("/fuel-management/stock");
  await page.waitForLoadState("networkidle");
  await page.getByLabel(/^Project$/).selectOption({ label: PROJECT });
  // The cards only render once the project's storage has loaded.
  await expect(page.getByRole("button", { name: /^Edit storage/ }).first())
    .toBeVisible({ timeout: 30_000 });
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("every storage card offers Edit and Delete", async ({ page }) => {
  await openStock(page);
  await page.screenshot({ path: `${SHOTS}/01-storage-cards.png`, fullPage: true });

  const edits = await page.getByRole("button", { name: /^Edit storage/ }).count();
  const deletes = await page.getByRole("button", { name: /^Delete storage/ }).count();
  expect(edits).toBeGreaterThan(0);
  expect(deletes).toBe(edits);
});

test("the card reports the average cost, or says there is none", async ({ page }) => {
  /**
   * Without this line somebody who types a price has no way of seeing that it
   * took — and a missing price has to read as missing, not as free fuel.
   */
  await openStock(page);
  await expect(page.getByText(/Average cost R18\.00\/L/)).toBeVisible();
  await expect(page.getByText(/No price recorded/).first()).toBeVisible();
});

test("a new tank created with a price shows that price", async ({ page }) => {
  await openStock(page);
  const name = `Priced Tank ${Date.now()}`;

  await page.getByRole("button", { name: /^New storage$/ }).click();
  await page.getByLabel(/^Storage name$/).fill(name);
  await page.getByLabel(/^Capacity \(litres\)$/).fill("2000");
  await page.getByLabel(/^Opening stock$/).fill("500");
  await page.getByLabel(/^Price per litre \(R\)$/).fill("21.50");
  await page.getByRole("button", { name: /^Create storage$/ }).click();

  await expect(page.getByText(name)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Average cost R21\.50\/L/)).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/02-priced-tank.png`, fullPage: true });
});

test("Edit prefills the tank and renaming does not create a second one", async ({ page }) => {
  await openStock(page);
  const before = await page.getByRole("button", { name: /^Edit storage/ }).count();

  await page.getByRole("button", { name: /^Edit storage Audit Diesel Tank$/ }).click();
  await expect(page.getByLabel(/^Storage name$/)).toHaveValue("Audit Diesel Tank");
  // The opening balance is a recorded adjustment, not a property of the tank,
  // so the form must not offer to restate it.
  await expect(page.getByLabel(/^Opening stock$/)).toHaveCount(0);
  await expect(page.getByLabel(/^Price per litre \(R\)$/)).toHaveCount(0);

  await page.getByLabel(/^Storage name$/).fill("Audit Diesel Tank A");
  await page.getByRole("button", { name: /^Save changes$/ }).click();

  await expect(page.getByText("Audit Diesel Tank A")).toBeVisible({ timeout: 20_000 });
  expect(await page.getByRole("button", { name: /^Edit storage/ }).count()).toBe(before);
  await page.screenshot({ path: `${SHOTS}/03-renamed-in-place.png`, fullPage: true });

  // Put it back, so the suite can be run twice.
  await page.getByRole("button", { name: /^Edit storage Audit Diesel Tank A$/ }).click();
  await page.getByLabel(/^Storage name$/).fill("Audit Diesel Tank");
  await page.getByRole("button", { name: /^Save changes$/ }).click();
  await expect(page.getByText("Audit Diesel Tank", { exact: true })).toBeVisible({ timeout: 20_000 });
});

test("the fuel type is locked once fuel has moved through the tank", async ({ page }) => {
  await openStock(page);
  await page.getByRole("button", { name: /^Edit storage Audit Diesel Tank$/ }).click();
  await expect(page.getByLabel(/^Fuel type$/)).toBeDisabled();
  await expect(page.getByText(/its fuel type is fixed/)).toBeVisible();
});

test("the confirmation distinguishes deleting from deactivating", async ({ page }) => {
  /**
   * Which of the two happens is decided by history the user cannot see, so it
   * has to be said before they commit, not reported afterwards.
   */
  await openStock(page);

  let message = "";
  page.once("dialog", async (dialog) => { message = dialog.message(); await dialog.dismiss(); });
  await page.getByRole("button", { name: /^Delete storage Audit Unused Tank$/ }).click();
  await expect.poll(() => message, { timeout: 10_000 }).not.toBe("");
  expect(message).toContain("permanently deleted");

  message = "";
  page.once("dialog", async (dialog) => { message = dialog.message(); await dialog.dismiss(); });
  await page.getByRole("button", { name: /^Delete storage Audit Diesel Tank$/ }).click();
  await expect.poll(() => message, { timeout: 10_000 }).not.toBe("");
  expect(message).toContain("DEACTIVATED");
  expect(message).toContain("written off");
});

test("dismissing the write-off prompt removes nothing", async ({ page }) => {
  await openStock(page);
  const before = await page.getByRole("button", { name: /^Delete storage/ }).count();

  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: /^Delete storage Audit Diesel Tank$/ }).click();
  await page.waitForTimeout(1500);

  expect(await page.getByRole("button", { name: /^Delete storage/ }).count()).toBe(before);
});

test("an unused tank is deleted outright and the notice says so", async ({ page }) => {
  await openStock(page);
  const before = await page.getByRole("button", { name: /^Delete storage/ }).count();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: /^Delete storage Audit Unused Tank$/ }).click();

  await expect
    .poll(() => page.getByRole("button", { name: /^Delete storage/ }).count(), { timeout: 20_000 })
    .toBe(before - 1);
  // Both outcomes take the card off the screen, so the strip is the only place
  // the difference between them is visible.
  await expect(page.getByText(/deleted — nothing had been recorded against it/))
    .toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: `${SHOTS}/04-unused-deleted.png`, fullPage: true });
});

test("a tank holding stock is written off and deactivated, with the litres named",
  async ({ page }) => {
    await openStock(page);

    page.once("dialog", (dialog) => dialog.accept("Tank removed from site"));
    await page.getByRole("button", { name: /^Delete storage Audit Write-Off Tank$/ }).click();

    await expect(page.getByText(/deactivated and hidden/)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/800\.00 L were written off/)).toBeVisible();
    await expect(page.getByRole("button", { name: /^Delete storage Audit Write-Off Tank$/ }))
      .toHaveCount(0);
    await page.screenshot({ path: `${SHOTS}/05-written-off.png`, fullPage: true });
  });

test("both delivery forms ask for a price, and only one calls it an override",
  async ({ page }) => {
    /**
     * The procurement path falls back to the purchase-order line rate when the
     * field is blank; the legacy path has no such fallback. Saying "overrides"
     * on both would be wrong in one place and saying it on neither would hide
     * that a PO rate is being replaced.
     */
    await page.goto("/fuel-management/deliveries");
    await page.waitForLoadState("networkidle");
    await page.getByLabel(/^Project$/).selectOption({ label: PROJECT });

    await page.getByRole("button", { name: /Record legacy delivery/ }).click();
    const legacy = page.getByLabel(/^Price per litre \(R\)$/);
    await expect(legacy).toBeVisible({ timeout: 20_000 });
    await expect(page.getByLabel(/overrides the purchase-order rate/)).toHaveCount(0);
    await page.screenshot({ path: `${SHOTS}/06-legacy-delivery-price.png`, fullPage: true });

    const confirm = page.getByRole("button", { name: /^Confirm into stock$/ }).first();
    if (await confirm.count()) {
      await confirm.click();
      await expect(page.getByLabel(/overrides the purchase-order rate/))
        .toBeVisible({ timeout: 20_000 });
      await page.screenshot({ path: `${SHOTS}/07-procurement-delivery-price.png`, fullPage: true });
    }
  });

test("the cards do not overflow on a phone", async ({ page }) => {
  /**
   * The cards gained two controls inside a 3-up grid, and a tank name is as
   * long as somebody typed it.
   */
  await page.setViewportSize({ width: 360, height: 640 });
  await openStock(page);
  await page.screenshot({ path: `${SHOTS}/08-phone-cards.png`, fullPage: true });

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
