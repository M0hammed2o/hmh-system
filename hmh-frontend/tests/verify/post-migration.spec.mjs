/**
 * Proof that migration 0079 fixes the production symptom.
 *
 * Runs against a database built to production's exact shape — schema at
 * 0078 with only the three companies 0077 added, two projects carrying
 * client_name "Minerat Construction & Civils" — then migrated to 0079.
 *
 * Synthetic throwaway database. Nothing here touches production.
 */
import { expect, test } from "playwright/test";
import { mkdirSync } from "node:fs";

const SHOTS = "docs/testing/screenshots";
mkdirSync(SHOTS, { recursive: true });

test("all five companies are selectable after migration 0079", async ({ page }) => {
  await page.goto("http://127.0.0.1:4191/login", { waitUntil: "networkidle" });
  await page.getByLabel(/email/i).fill(process.env.VERIFY_EMAIL);
  await page.getByLabel(/password/i).fill(process.env.VERIFY_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 30_000 });

  await page.goto("http://127.0.0.1:4191/companies", { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${SHOTS}/15-companies-after-0079.png` });

  for (const name of ["HMH Group", "Minerat Construction & Civils",
                      "Kukhanya Kabusha", "Premium Structures", "Ophezulu"]) {
    await expect(page.getByText(name, { exact: false }).first(),
      `${name} missing from the company list`).toBeVisible();
  }

  // The selector that regressed.
  await page.goto("http://127.0.0.1:4191/projects", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: /new project|add project/i }).first().click();
  await page.waitForTimeout(1500);

  const select = page.locator("select").filter({ hasText: /select company/i }).first();
  await expect(select).toBeVisible({ timeout: 10_000 });
  const options = (await select.locator("option").allTextContents()).join(" | ");
  await page.screenshot({ path: `${SHOTS}/16-company-selector-after-0079.png` });

  for (const name of ["HMH Group", "Minerat Construction & Civils",
                      "Kukhanya Kabusha", "Premium Structures", "Ophezulu"]) {
    expect(options, `${name} missing from the selector`).toContain(name);
  }
});

test("existing projects keep their company association", async ({ page }) => {
  await page.goto("http://127.0.0.1:4191/login", { waitUntil: "networkidle" });
  await page.getByLabel(/email/i).fill(process.env.VERIFY_EMAIL);
  await page.getByLabel(/password/i).fill(process.env.VERIFY_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 30_000 });

  await page.goto("http://127.0.0.1:4191/projects", { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);

  // Both simulated projects still show the company they were created under,
  // now matching a real row rather than an unrecognised leftover.
  const body = await page.locator("body").innerText();
  expect(body).toContain("Minerat Construction & Civils");
  expect(body).not.toContain("not in company list");
  await page.screenshot({ path: `${SHOTS}/17-projects-retain-company.png` });
});
