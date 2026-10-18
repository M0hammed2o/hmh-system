/**
 * Live production browser checks — https://app.hmhgroup.co.za
 *
 * These run a real browser against the real production site.
 *
 * NOTHING HERE LOGS IN. No authorised production credential exists in this
 * environment, and guessing one or forging a session would be an
 * unauthorised access attempt, so everything behind the login is out of
 * reach and is reported as NOT VERIFIED rather than assumed.
 *
 * What these checks CAN establish about production, genuinely:
 *   - the site is reachable and renders;
 *   - which build is deployed, by reading the live JavaScript bundles and
 *     looking for strings only the new features introduce;
 *   - that protected routes demand authentication rather than leaking.
 *
 * That is verification of DEPLOYMENT, not of FUNCTIONALITY.
 */

import { expect, test } from "playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const SHOTS = "docs/testing/live-production-screenshots";
const FRONTEND = "https://app.hmhgroup.co.za";
const BACKEND = "https://hmh-backend-uhzu.onrender.com";

mkdirSync(SHOTS, { recursive: true });

async function shot(page, name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

test.describe.configure({ mode: "serial" });

test("the live site loads and serves its login page", async ({ page }) => {
  const res = await page.goto(FRONTEND, { waitUntil: "networkidle", timeout: 60_000 });
  expect(res?.status(), "production frontend did not return 200").toBe(200);

  await page.waitForTimeout(2500);
  await shot(page, "P01-live-login-desktop-1440x900");

  // The real app shell must be there, not an error or placeholder page.
  const body = await page.locator("body").innerText();
  expect(body.length, "production page rendered empty").toBeGreaterThan(20);
  writeFileSync(`${SHOTS}/P01-live-login-text.txt`, body.slice(0, 2000));
});

test("the live site renders at mobile width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(FRONTEND, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForTimeout(2000);
  await shot(page, "P02-live-login-mobile-390x844");

  // No horizontal overflow at phone width.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "production login overflows horizontally on mobile").toBeLessThanOrEqual(1);
});

test("protected routes redirect to login rather than leaking data", async ({ page }) => {
  for (const path of ["/vehicles", "/workshop", "/companies", "/ai-document-import"]) {
    await page.goto(`${FRONTEND}${path}`, { waitUntil: "networkidle", timeout: 60_000 });
    await page.waitForTimeout(1500);

    const text = (await page.locator("body").innerText()).toLowerCase();
    // Either bounced to a login screen, or showing nothing of substance —
    // never the real screen's data.
    const looksAuthenticated =
      text.includes("mechanic payments") && text.includes("outstanding");
    expect(looksAuthenticated, `${path} rendered authenticated content without a login`).toBeFalsy();
  }
  await shot(page, "P03-protected-route-requires-login");
});

/**
 * Which build is live.
 *
 * The deployed bundles are the ground truth for "is this feature shipped".
 * Each marker below is a literal string that only exists because of the
 * recent work, so finding it proves that code is serving to real users.
 */
test("the deployed production bundle contains the new features", async ({ page }) => {
  await page.goto(FRONTEND, { waitUntil: "networkidle", timeout: 60_000 });

  const scripts = await page.evaluate(() =>
    Array.from(document.querySelectorAll("script[src]")).map((s) => s.src),
  );
  expect(scripts.length, "no scripts found on the production page").toBeGreaterThan(0);

  // Pull every bundle the page loads, plus the lazy chunks it references.
  const seen = new Set();
  let combined = "";
  const fetchAll = async (urls) => {
    for (const url of urls) {
      if (seen.has(url)) continue;
      seen.add(url);
      try {
        const r = await page.request.get(url, { timeout: 45_000 });
        if (r.ok()) combined += await r.text();
      } catch { /* a missing chunk is itself reported by the markers below */ }
    }
  };

  await fetchAll(scripts);

  const origin = new URL(scripts[0]).origin;
  const base = scripts[0].slice(0, scripts[0].lastIndexOf("/"));
  expect(origin).toContain("hmhgroup");

  // Route-level code splitting means the interesting screens live in lazy
  // chunks the entry bundle only names. Collect every asset filename that
  // appears anywhere in what we have, then fetch those too — twice, since a
  // chunk can name further chunks.
  for (let pass = 0; pass < 2; pass += 1) {
    const names = new Set(
      [...combined.matchAll(/["'`/]([A-Za-z0-9_.-]+-[A-Za-z0-9_-]{8}\.js)\b/g)].map((m) => m[1]),
    );
    await fetchAll([...names].map((n) => `${base}/${n}`));
  }

  // Literal runtime strings only. Anything type-only is erased at build time
  // and its absence would say nothing about what shipped — an earlier
  // version of this test used one and produced a false negative.
  const markers = {
    "Bypass Orders rename": "Bypass Orders",
    "Import Documents tab": "Import Documents",
    "Mechanic Payments tab": "Mechanic Payments",
    "record a payment form": "Record a payment",
    "still-owing filter": "Still owing",
    "non-mechanic cost note": "is booked against this repair",
    "history pager page size": "/ page",
    "repair edit modal": "Edit Repair Job",
    "repair count label": "repair job(s)",
    "service status endpoint": "/ai-import/service-status",
  };

  const found = {};
  for (const [label, needle] of Object.entries(markers)) {
    found[label] = combined.includes(needle);
  }
  writeFileSync(
    `${SHOTS}/P04-deployed-bundle-markers.json`,
    JSON.stringify({ checkedAt: new Date().toISOString(), origin, bundles: seen.size, found }, null, 2),
  );

  // Report every marker, then assert, so the artifact records the full picture
  // even when one fails.
  for (const [label, present] of Object.entries(found)) {
    expect(present, `"${label}" is NOT in the deployed production bundle`).toBeTruthy();
  }
});

test("the production API demands authentication on the new routes", async ({ request }) => {
  const results = {};
  for (const path of [
    "/api/v1/workshop/mechanic-payments",
    "/api/v1/ai-import/service-status",
    "/api/v1/companies/",
    "/api/v1/vehicles/",
  ]) {
    const r = await request.get(`${BACKEND}${path}`, { timeout: 45_000 });
    results[path] = r.status();
    // 401/403 means the route exists and is protected. 404 would mean the
    // build predates it.
    expect([401, 403], `${path} returned ${r.status()}`).toContain(r.status());
  }
  writeFileSync(
    `${SHOTS}/P05-production-api-auth.json`,
    JSON.stringify({ checkedAt: new Date().toISOString(), results }, null, 2),
  );
});
