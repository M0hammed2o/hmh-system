/**
 * One end-to-end upload against LIVE production, through the real UI.
 *
 * Verifies that the newly created private bucket accepts a PDF: upload →
 * document record → file retrievable from private storage → AI processing.
 *
 * Deliberately stops there. The document is NOT reviewed, authorised or
 * posted, so nothing reaches stock, finance or a BOQ. The file itself is
 * unmistakably synthetic and says on its face that it must be rejected.
 */

import { expect, test } from "playwright/test";
import { mkdirSync } from "node:fs";

const SHOTS = "docs/testing/live-production-screenshots";
const BASE = "https://app.hmhgroup.co.za";
const API = "https://hmh-backend-uhzu.onrender.com/api/v1";
const PDF = process.env.TEST_PDF;

if (!process.env.PROD_EMAIL || !process.env.PROD_PASSWORD || !PDF) {
  throw new Error("Set PROD_EMAIL, PROD_PASSWORD and TEST_PDF.");
}

mkdirSync(SHOTS, { recursive: true });
test.setTimeout(240_000);

test("PROD: a PDF delivery note uploads, stores and is read", async ({ page }) => {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await page.getByLabel(/email/i).fill(process.env.PROD_EMAIL);
  await page.getByLabel(/password/i).fill(process.env.PROD_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.includes("/login"), { timeout: 45_000 });

  const token = await page.evaluate(() => localStorage.getItem("hmh_access_token"));
  const auth = { Authorization: `Bearer ${token}` };
  const api = async (path) => {
    const r = await page.request.get(`${API}${path}`, { headers: auth, timeout: 90_000 });
    return { status: r.status(), body: r.ok() ? await r.json() : await r.text() };
  };

  // Automatic posting must be off before anything is uploaded.
  const status = await api("/ai-import/service-status");
  expect(status.status).toBe(200);
  expect(status.body.data.auto_post_enabled,
    "AUTOMATIC POSTING IS ON — aborting before uploading").toBe(false);
  console.log("service status:", JSON.stringify(status.body.data));

  const before = await api("/ai-import/documents?page=1&limit=1");
  const countBefore = before.body?.data?.total ?? 0;
  console.log("documents before:", countBefore);

  await page.goto(`${BASE}/ai-document-import`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${SHOTS}/U01-bypass-orders-before-upload.png` });

  // Upload through the real file input.
  await page.setInputFiles('input[type="file"]', PDF);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${SHOTS}/U02-file-selected.png` });

  // Must require a digit: /^Import \d* ?document/ also matches the
  // "Import Documents" TAB, and .first() would click that instead.
  const submit = page.getByRole("button", { name: /^Import \d+ documents?$/i }).first();
  await expect(submit).toBeVisible({ timeout: 15_000 });
  await submit.click();

  // Wait for the result banner, success or failure.
  await page.waitForFunction(
    () => /document\(s\) received|Upload failed/i.test(document.body.innerText),
    { timeout: 120_000 },
  );
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${SHOTS}/U03-upload-result.png` });

  const banner = await page.locator("body").innerText();
  console.log("banner:", banner.split("\n").filter((l) =>
    /received|failed|could not|rejected|background/i.test(l)).join(" | "));

  expect(banner, "the upload reported a failure").not.toMatch(/Upload failed/i);
  expect(banner).toMatch(/1 document\(s\) received/i);

  // The record must exist in the production database.
  const after = await api("/ai-import/documents?page=1&limit=5");
  expect(after.status).toBe(200);
  const docs = after.body.data.items ?? [];
  expect(after.body.data.total, "no new document row").toBeGreaterThan(countBefore);

  const doc = docs.find((d) => /SYNTHETIC-TEST/i.test(d.file_name ?? ""));
  expect(doc, "the uploaded document is not in the list").toBeTruthy();
  console.log("document:", doc.id, doc.file_name, "status:", doc.status);

  // The file must be retrievable from private storage — a row without a
  // fetchable file is a promise the system cannot keep.
  const file = await api(`/ai-import/documents/${doc.id}/file`);
  expect(file.status, "could not get a link to the stored file").toBe(200);
  const url = file.body.data?.url ?? file.body.data?.signed_url ?? file.body.data;
  console.log("signed url host:", String(url).split("/")[2]);

  const fetched = await page.request.get(String(url), { timeout: 60_000 });
  console.log("file fetch:", fetched.status(), "bytes:", (await fetched.body()).length);
  expect(fetched.status(), "the stored file is not retrievable").toBe(200);
  expect((await fetched.body()).length, "the stored file is empty").toBeGreaterThan(1000);

  // Follow processing for a while, without posting anything.
  let latest = doc;
  for (let i = 0; i < 20; i += 1) {
    await page.waitForTimeout(6000);
    const r = await api(`/ai-import/documents/${doc.id}`);
    if (r.status !== 200) break;
    latest = r.body.data;
    console.log(`  t+${(i + 1) * 6}s status=${latest.status}`);
    if (!["UPLOADED", "QUEUED", "PROCESSING", "EXTRACTED", "CLASSIFIED", "MATCHING"]
          .includes(latest.status)) break;
  }

  await page.goto(`${BASE}/ai-document-import`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: /^Documents/i }).first().click().catch(() => {});
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${SHOTS}/U04-document-list.png` });

  console.log("FINAL status:", latest.status);
  console.log("outcome:", latest.processing_outcome, latest.outcome_reasons);
  console.log("failure_reason:", latest.failure_reason);
  console.log("document_type:", latest.document_type);
  console.log("pipeline:", JSON.stringify(latest.pipeline ?? "(not deployed yet)"));

  // Nothing may have been posted.
  expect(latest.status, "the test document was posted").not.toBe("POSTED");
});
