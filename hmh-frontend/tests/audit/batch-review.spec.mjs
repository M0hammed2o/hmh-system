/**
 * Batch Review, in the browser.
 *
 * Proves the manifest actually renders what the routing service decided:
 * that a pro-forma is shown going somewhere other than Accounts Payable,
 * that a fuel order leaves the materials path, that a PAID stamp is shown
 * as a claim awaiting verification, and that a document with no supplier
 * asks for one instead of quietly importing.
 *
 * Runs against the local audit stack, seeded by
 * scripts/seed_mixed_batch_demo.py. Every supplier, project and document
 * number in that seed is fictional, so the screenshots disclose nothing.
 *
 * What this does not cover: AI extraction. The seeded documents carry
 * extractions written directly, because a live extraction still needs a
 * workspace-scoped Anthropic key. Reading a document is covered by the
 * backend suites.
 */

import { expect, test } from "playwright/test";
import { mkdirSync } from "node:fs";

const SHOTS = "docs/testing/screenshots/batch-review";
const EMAIL = process.env.AUDIT_EMAIL;
const PASSWORD = process.env.AUDIT_PASSWORD;

if (!EMAIL || !PASSWORD) {
  throw new Error("Set AUDIT_EMAIL and AUDIT_PASSWORD to run the batch review audit.");
}

mkdirSync(SHOTS, { recursive: true });

// The app registers a service worker. A stale one left on this origin by an
// earlier audit build serves that build's bundle, pointing at a backend that
// no longer exists — which surfaces as "invalid email or password" and sends
// you looking for a credential problem that is not there.
test.use({ serviceWorkers: "block" });

async function login(page) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 30_000 });
}

async function openBatchReview(page) {
  await page.goto("/ai-document-import");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: /^Batch Review$/i }).click();
  // The manifest is one request; wait for a row rather than a fixed delay.
  await expect(page.getByRole("table")).toBeVisible({ timeout: 20_000 });
}

/**
 * The row for one document.
 *
 * Anchored on the filename button, not on the row's text. A duplicate
 * warning names the sibling document it is warning about, so filtering by
 * text matches both rows — which is the feature working, and a locator that
 * cannot tell them apart.
 */
function rowFor(page, fileName) {
  return page.locator("table tbody tr").filter({
    has: page.getByRole("button", { name: fileName, exact: true }),
  });
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("the manifest lists the batch with its destinations", async ({ page }) => {
  await openBatchReview(page);
  await page.screenshot({ path: `${SHOTS}/01-manifest.png`, fullPage: true });

  const rows = page.locator("table tbody tr");
  await expect(rows).toHaveCount(21);

  // Headings a reader needs in order to act on the page.
  for (const heading of ["Document", "Detected type", "Destination", "Proposed action"]) {
    await expect(page.getByRole("columnheader", { name: heading })).toBeVisible();
  }
});

test("a pro-forma is not shown heading for Accounts Payable", async ({ page }) => {
  await openBatchReview(page);

  const row = rowFor(page, "proforma-readymix-P89250.pdf");
  await expect(row).toBeVisible();

  // The destination cell, not the whole row: the row legitimately contains
  // the words "Accounts Payable" inside the sentence explaining that this
  // is not one. Asserting on the row would fail on the very text that makes
  // the point.
  const destination = row.locator("td").nth(5);
  await expect(destination).toContainText("Pending supplier charges");

  // The effect sentence Accounts Payable would carry must be absent.
  await expect(row).not.toContainText("Creates a supplier liability");
  // And the real consequence is spelled out, not implied by a module name.
  await expect(row).toContainText(/becomes a liability only when/i);
  await row.screenshot({ path: `${SHOTS}/02-proforma-row.png` });
});

test("a tax invoice is shown creating an unpaid liability", async ({ page }) => {
  await openBatchReview(page);

  const row = rowFor(page, "invoice-aggregate-85956.pdf");
  await expect(row).toContainText("Accounts Payable");
  await expect(row).toContainText(/UNPAID/);
  await row.screenshot({ path: `${SHOTS}/03-tax-invoice-row.png` });
});

test("the fuel order leaves the materials path", async ({ page }) => {
  await openBatchReview(page);

  const row = rowFor(page, "po-012-diesel.pdf");
  await expect(row).toContainText("Fuel procurement");
  await expect(row).toContainText(/litres/i);
  await expect(row).toContainText("Needs review");
  await row.screenshot({ path: `${SHOTS}/04-fuel-order-row.png` });
});

test("a PAID stamp is shown as a claim awaiting verification", async ({ page }) => {
  await openBatchReview(page);

  const row = rowFor(page, "po-007-plumbing.pdf");
  await expect(row).toContainText(/payment evidence detected/i);
  await expect(row).toContainText(/verification required/i);
  await expect(row).toContainText(/not a bank record/i);
  await row.screenshot({ path: `${SHOTS}/05-payment-evidence-row.png` });
});

test("the project selector is populated", async ({ page }) => {
  /**
   * Regression. The page asked for 200 projects; the API caps the limit at
   * 100 and returns 422, which the loader swallowed into an empty list. The
   * selector was therefore always empty and no document could be assigned a
   * project — which blocks every import, because nothing posts without one.
   */
  await openBatchReview(page);

  const project = rowFor(page, "invoice-aggregate-85956.pdf")
    .getByRole("combobox", { name: /project/i });
  const options = await project.locator("option").allTextContents();

  expect(options.length, "the project selector offered nothing to choose")
    .toBeGreaterThan(1);
  await expect(project).not.toHaveValue("");
});

test("a document with no supplier asks for one", async ({ page }) => {
  await openBatchReview(page);

  const row = rowFor(page, "proforma-merchant-QTE254210.pdf");
  await expect(row).toContainText("Needs review");
  await expect(row).toContainText(/supplier is not linked/i);
  // What the document said is still shown, so the reader can match it up.
  await expect(row).toContainText(/Lakeside Builders Merchant/i);
  await row.screenshot({ path: `${SHOTS}/06-missing-supplier-row.png` });
});

test("two pro-formas for the same amount are questioned, not resolved", async ({ page }) => {
  await openBatchReview(page);

  const row = rowFor(page, "proforma-readymix-P89381.pdf");
  await expect(row).toContainText(/same amount/i);
  await expect(row).toContainText(/proforma-readymix-P89250\.pdf/);
  await row.screenshot({ path: `${SHOTS}/07-duplicate-amount-row.png` });
});

test("the summary counts liabilities and stock separately", async ({ page }) => {
  await openBatchReview(page);

  // Two tax invoices create a liability; one delivery note moves stock.
  const liability = page.locator("div", { hasText: /^Create a liability$/ }).first();
  await expect(liability).toBeVisible();
  const stock = page.locator("div", { hasText: /^Move stock$/ }).first();
  await expect(stock).toBeVisible();

  await page
    .locator("div.grid")
    .first()
    .screenshot({ path: `${SHOTS}/08-summary.png` });
});

test("correcting the type changes the destination", async ({ page }) => {
  await openBatchReview(page);

  const row = rowFor(page, "proforma-coastal-SQ473889.pdf");
  await expect(row).toContainText("Pending supplier charges");
  await page.screenshot({ path: `${SHOTS}/09-before-correction.png`, fullPage: true });

  // Reclassify it as the tax invoice it is not, and watch where it would go.
  await row.getByRole("combobox", { name: /document type/i }).selectOption("SUPPLIER_INVOICE");
  await expect(row).toContainText("Accounts Payable", { timeout: 20_000 });
  await page.screenshot({ path: `${SHOTS}/10-after-correction.png`, fullPage: true });

  // Put it back, so the spec can be re-run against the same seed.
  await row.getByRole("combobox", { name: /document type/i }).selectOption("PRO_FORMA_INVOICE");
  await expect(row).toContainText("Pending supplier charges", { timeout: 20_000 });
});
