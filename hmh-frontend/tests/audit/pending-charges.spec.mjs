/**
 * Pending Supplier Charges, in the browser.
 *
 * The thing being proved is a separation: what a supplier has asked for in
 * advance must be visible, and must not be anywhere near the figures for
 * what the business owes. A pro-forma counted as a payable overstates the
 * liability today and doubles it when the real invoice arrives.
 *
 * Runs against the local demo stack, whose suppliers, project and document
 * numbers are all fictional. It expects a FRESHLY SEEDED batch: re-run
 * scripts/seed_mixed_batch_demo.py against an empty database first. Running
 * scripts/verify_mixed_batch_workflow.py posts most of the documents, which
 * legitimately changes what these screens show. `test` is imported from the local-only guard,
 * which aborts any request that would leave the machine.
 */

import { expect, test } from "../support/local-only.mjs";
import { mkdirSync } from "node:fs";

const SHOTS = "docs/testing/screenshots/pending-charges";
const EMAIL = process.env.AUDIT_EMAIL;
const PASSWORD = process.env.AUDIT_PASSWORD;

if (!EMAIL || !PASSWORD) {
  throw new Error("Set AUDIT_EMAIL and AUDIT_PASSWORD to run the pending-charges audit.");
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

async function openPendingCharges(page) {
  await page.goto("/payments");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: /^Pending Charges$/i }).click();
  await expect(page.getByRole("table")).toBeVisible({ timeout: 20_000 });
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("the tab exists beside the payables tabs", async ({ page }) => {
  await page.goto("/payments");
  await page.waitForLoadState("networkidle");

  // The tab buttons carry a count badge, so their accessible name is
  // "Invoices 3" rather than "Invoices". Anchor the start, not the end.
  for (const label of ["Payments", "Invoices", "Outstanding", "Pending Charges"]) {
    await expect(page.getByRole("button", { name: new RegExp(`^${label}\\b`, "i") }))
      .toBeVisible();
  }
});

test("every column Rafiq needs is present", async ({ page }) => {
  await openPendingCharges(page);
  await page.screenshot({ path: `${SHOTS}/01-pending-charges.png`, fullPage: true });

  for (const heading of [
    "Supplier", "Reference", "Amount", "Matched order", "Status", "Final invoice",
  ]) {
    await expect(page.getByRole("columnheader", { name: heading })).toBeVisible();
  }
});

test("the screen says the total is not owed", async ({ page }) => {
  /**
   * A bare number on a finance screen gets added to the other numbers on
   * the same screen. This one has to carry its own warning.
   */
  await openPendingCharges(page);

  const notice = page.getByText(/not owed and is not part of Accounts Payable/i);
  await expect(notice).toBeVisible();
  await notice.screenshot({ path: `${SHOTS}/02-not-a-payable.png` });
});

test("an open request shows its supplier, reference and amount", async ({ page }) => {
  await openPendingCharges(page);

  const row = page.locator("table tbody tr", { hasText: "P88120" });
  await expect(row).toContainText("Vantage Readymix");
  // en-ZA groups thousands with U+00A0, not an ordinary space.
  await expect(row).toContainText(/20[\s\u00a0]?360[,.]89/);
  await expect(row).toContainText(/Awaiting invoice/i);
  await expect(row).toContainText(/Not yet issued/i);
  await row.screenshot({ path: `${SHOTS}/03-open-request.png` });
});

test("a settled request names the invoice that closed it", async ({ page }) => {
  /**
   * The reconciliation, visible. Without this the same purchase looks like
   * two separate obligations.
   */
  await openPendingCharges(page);
  await page.getByRole("button", { name: /settled or withdrawn/i }).click();

  const row = page.locator("table tbody tr", { hasText: "QTE5721" });
  await expect(row).toContainText(/Invoiced/);
  await expect(row).toContainText("MB-44120");
  await expect(row).toContainText("PO-DEMO-009");
  await row.screenshot({ path: `${SHOTS}/04-settled-request.png` });
});

test("a settled request is not counted as outstanding", async ({ page }) => {
  await openPendingCharges(page);

  // Four open requests; the fifth is closed and must not be among them.
  // Counted from the table rather than from the tile: the rows are the
  // thing being asserted about, and a tile's markup is not a contract.
  await expect(page.getByText("Open requests")).toBeVisible();
  await expect(page.locator("table tbody tr")).toHaveCount(4);

  // The settled one is there, just not by default.
  await page.getByRole("button", { name: /settled or withdrawn/i }).click();
  await expect(page.locator("table tbody tr")).toHaveCount(5);
});

test("pro-formas do not appear among the invoices", async ({ page }) => {
  /**
   * Stated from the other side: whatever the Invoices tab shows, a
   * pro-forma reference is not in it.
   */
  await page.goto("/payments");
  await page.waitForLoadState("networkidle");
  // "Invoices 1" — the tab carries a count badge, so the name is a prefix.
  await page.getByRole("button", { name: /^Invoices\b/i }).click();
  await page.waitForTimeout(1500);

  const body = await page.locator("body").innerText();
  for (const reference of ["P88120", "P88121", "QTE5410", "SQ470880"]) {
    expect(body, `pro-forma ${reference} is showing on the Invoices tab`)
      .not.toContain(reference);
  }
  await page.screenshot({ path: `${SHOTS}/05-invoices-tab-clean.png`, fullPage: true });
});

test("withdrawing a request asks why", async ({ page }) => {
  await openPendingCharges(page);

  const row = page.locator("table tbody tr", { hasText: "SQ470880" });
  await row.getByRole("button", { name: /withdraw/i }).click();

  const confirm = page.getByRole("button", { name: /^Withdraw request$/i });
  await expect(confirm).toBeVisible();
  // Disabled until a reason is given: a charge that simply vanished leaves
  // nobody able to say later whether it was refused, paid or forgotten.
  await expect(confirm).toBeDisabled();
  await page.screenshot({ path: `${SHOTS}/06-withdraw-needs-a-reason.png` });

  await page.getByLabel(/why/i).fill("Supplier withdrew the offer.");
  await expect(confirm).toBeEnabled();
});
