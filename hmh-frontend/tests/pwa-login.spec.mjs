import { expect, test } from "playwright/test";

const apiUser = (role) => ({
  id: "00000000-0000-0000-0000-000000000001",
  full_name: "PWA Test User",
  email: "pwa@example.test",
  phone: null,
  role,
  is_active: true,
  must_reset_password: false,
  last_login_at: null,
  failed_login_attempts: 0,
  locked_until: null,
  created_by: null,
  created_at: "2026-08-02T00:00:00Z",
  updated_at: "2026-08-02T00:00:00Z",
  project_access_count: 1,
});

async function mockLoginApi(page, role = "OFFICE_USER") {
  await page.route("**/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith("/auth/login")) {
      return route.fulfill({
        json: {
          access_token: "test-access-token",
          refresh_token: "test-refresh-token",
          token_type: "bearer",
          expires_in: 3600,
          must_reset_password: false,
        },
      });
    }
    if (pathname.endsWith("/users/me")) {
      return route.fulfill({ json: { data: apiUser(role) } });
    }
    return route.fulfill({ status: 200, json: { data: { items: [], total: 0, page: 1, limit: 100, total_pages: 0 } } });
  });
}

test("direct login routes and refreshes render without a blank screen", async ({ page }) => {
  for (const path of ["/login", "/site-login"]) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  }
});

test("protected nested route retains its destination through office login", async ({ page }) => {
  await mockLoginApi(page, "OFFICE_USER");
  await page.goto("/fuel-management/orders?project=alpha");
  await expect(page).toHaveURL(/\/login\?returnTo=%2Ffuel-management%2Forders%3Fproject%3Dalpha/);

  await page.getByLabel("Email address").fill("pwa@example.test");
  await page.getByLabel("Password").fill("correct-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/fuel-management\/orders\?project=alpha$/);
  await expect(page.getByRole("main").getByRole("heading", { name: "Fuel Management" })).toBeVisible();
});

test("site compatibility login routes site users only to the site portal", async ({ page }) => {
  await mockLoginApi(page, "SITE_MANAGER");
  await page.goto("/site-login?returnTo=%2Fsite");
  await page.getByLabel("Email address").fill("site@example.test");
  await page.getByLabel("Password").fill("correct-password");
  await page.getByRole("button", { name: /sign in to site portal/i }).click();
  await expect(page).toHaveURL(/\/site$/);
});

test("manifest, worker scope and offline nested navigation are usable", async ({ page, context }) => {
  await page.goto("/login");
  const manifest = await page.evaluate(async () => (await fetch("/manifest.json")).json());
  expect(manifest.start_url).toBe("/login?source=pwa");
  expect(manifest.scope).toBe("/");
  expect(manifest.icons.some((icon) => icon.sizes === "192x192")).toBeTruthy();
  expect(manifest.icons.some((icon) => icon.sizes === "512x512" && icon.purpose === "maskable")).toBeTruthy();

  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  await context.setOffline(true);
  await page.goto("/fuel-management/stock", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/login\?returnTo=/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("service worker never caches private fuel evidence images", async ({ page }) => {
  await page.route("**/uploads/attachments/FUEL_ISSUE/**", route => route.fulfill({
    status: 200, contentType: "image/png", body: Buffer.from("iVBORw0KGgo=", "base64"),
  }));
  await page.goto("/login");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.evaluate(async () => { await fetch("/uploads/attachments/FUEL_ISSUE/test/evidence.png"); });
  const cached = await page.evaluate(async () => {
    for (const name of await caches.keys()) {
      if (await (await caches.open(name)).match("/uploads/attachments/FUEL_ISSUE/test/evidence.png")) return true;
    }
    return false;
  });
  expect(cached).toBeFalsy();
});

test("site Fuel request is usable at a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => { localStorage.setItem("hmh_access_token", "site-token"); localStorage.setItem("hmh_user_role", "SITE_STAFF"); });
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/users/me")) return route.fulfill({ json: { data: apiUser("SITE_STAFF") } });
    if (path.endsWith("/projects/")) return route.fulfill({ json: { data: { items: [{ id: "p1", name: "Mobile Project" }], total: 1, page: 1, limit: 100, total_pages: 1 } } });
    if (path.endsWith("/fuel-types")) return route.fulfill({ json: { data: [{ id: "f1", code: "DIESEL", name: "Diesel", is_active: true }] } });
    if (path.endsWith("/sites/")) return route.fulfill({ json: { data: [{ id: "s1", project_id: "p1", name: "Site One", code: null, site_type: "CONSTRUCTION", location_description: null, is_active: true }] } });
    if (path.endsWith("/vehicles")) return route.fulfill({ json: { data: [] } });
    if (path.endsWith("/fuel-management/orders")) return route.fulfill({ json: { data: [] } });
    return route.fulfill({ json: { data: [] } });
  });
  await page.goto("/site/fuel-request");
  await expect(page.getByRole("heading", { name: "Request fuel" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await expect(page.getByRole("button", { name: "Submit fuel request" })).toBeVisible();
});

// ── Physical mobile-viewport coverage (task: PWA physical layout readiness) ──

const MOBILE_VIEWPORTS = [
  { name: "360x640 (small Android)", width: 360, height: 640 },
  { name: "390x844 (iPhone 12/13)",  width: 390, height: 844 },
  { name: "412x915 (large Android)", width: 412, height: 915 },
];

async function mockSiteFuelRequestApi(page, { storage } = {}) {
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/users/me")) return route.fulfill({ json: { data: apiUser("SITE_STAFF") } });
    if (path.endsWith("/projects/")) return route.fulfill({ json: { data: { items: [{ id: "p1", name: "Mobile Project" }], total: 1, page: 1, limit: 100, total_pages: 1 } } });
    if (path.endsWith("/fuel-types")) return route.fulfill({ json: { data: [{ id: "f1", code: "DIESEL", name: "Diesel", is_active: true }] } });
    if (path.endsWith("/sites/")) return route.fulfill({ json: { data: [{ id: "s1", project_id: "p1", name: "Site One", code: null, site_type: "CONSTRUCTION", location_description: null, is_active: true }] } });
    if (path.endsWith("/vehicles")) return route.fulfill({ json: { data: [] } });
    if (path.endsWith("/fuel-management/orders")) return route.fulfill({ json: { data: [] } });
    if (path.endsWith("/fuel-management/storage")) return route.fulfill({ json: { data: storage ?? [] } });
    return route.fulfill({ json: { data: [] } });
  });
}

for (const viewport of MOBILE_VIEWPORTS) {
  test(`site Fuel request has no horizontal overflow or clipped submit button at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.addInitScript(() => { localStorage.setItem("hmh_access_token", "site-token"); localStorage.setItem("hmh_user_role", "SITE_STAFF"); });
    await mockSiteFuelRequestApi(page);
    await page.goto("/site/fuel-request");
    await expect(page.getByRole("heading", { name: "Request fuel" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    const submit = page.getByRole("button", { name: "Submit fuel request" });
    await expect(submit).toBeVisible();
    const box = await submit.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
  });

  test(`site dashboard has no horizontal overflow or clipped header controls at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.addInitScript(() => { localStorage.setItem("hmh_access_token", "site-token"); localStorage.setItem("hmh_user_role", "SITE_STAFF"); });
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/users/me")) return route.fulfill({ json: { data: apiUser("SITE_STAFF") } });
      if (path.endsWith("/projects/")) return route.fulfill({ json: { data: { items: [{ id: "p1", name: "Mobile Project" }], total: 1, page: 1, limit: 100, total_pages: 1 } } });
      if (path.endsWith("/sites/")) return route.fulfill({ json: { data: [{ id: "s1", project_id: "p1", name: "Site One", code: null, site_type: "CONSTRUCTION", location_description: null, is_active: true }] } });
      return route.fulfill({ json: { data: [] } });
    });
    await page.goto("/site");
    await expect(page.getByRole("button", { name: "Fuel request" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    const fuelBtn = page.getByRole("button", { name: "Fuel request" });
    const box = await fuelBtn.boundingBox();
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
  });
}

test("site Fuel request shows the estimated fuel balance with type and storage location", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => { localStorage.setItem("hmh_access_token", "site-token"); localStorage.setItem("hmh_user_role", "SITE_STAFF"); });
  await mockSiteFuelRequestApi(page, {
    storage: [{
      id: "st1", project_id: "p1", site_id: "s1", fuel_type_id: "f1",
      name: "Main Diesel Tank", location_type: "TANK", capacity_litres: 5000,
      low_stock_threshold_litres: 100, calculated_balance_litres: 850, notes: null,
    }],
  });
  await page.goto("/site/fuel-request");
  await expect(page.getByText("Estimated fuel remaining")).toBeVisible();
  await expect(page.getByText("Main Diesel Tank · Diesel")).toBeVisible();
  await expect(page.getByText("850 L")).toBeVisible();
});

test("site Fuel request shows a clear message when no storage location is configured", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => { localStorage.setItem("hmh_access_token", "site-token"); localStorage.setItem("hmh_user_role", "SITE_STAFF"); });
  await mockSiteFuelRequestApi(page, { storage: [] });
  await page.goto("/site/fuel-request");
  await expect(page.getByText(/No fuel storage location has been configured/i)).toBeVisible();
});

// ── Dual-access Site Dashboard entry points (task: clear Site Dashboard access) ──

test("login page offers a Go to Site Dashboard link to /site-login", async ({ page }) => {
  await page.goto("/login");
  const link = page.getByRole("link", { name: /Go to Site Dashboard/i });
  await expect(link).toBeVisible();
  await link.click();
  await expect(page).toHaveURL(/\/site-login/);
});

test("OWNER sees a Go to Site Dashboard link in the main dashboard and can reach /site", async ({ page }) => {
  await mockLoginApi(page, "OWNER");
  await page.goto("/");
  await page.getByLabel("Email address").fill("owner@example.test");
  await page.getByLabel("Password").fill("correct-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/^http:\/\/[^/]+\/$/);
  await expect(page.getByRole("link", { name: /Go to Site Dashboard/i })).toBeVisible();

  // Navigate directly (rather than clicking) to isolate the routing/access-
  // control assertion from unrelated dashboard-load render churn.
  await page.goto("/site");
  await expect(page).toHaveURL(/\/site$/);
  await expect(page.getByRole("button", { name: "Fuel request" })).toBeVisible();
});

test("OFFICE_USER (non dual-access) does not see a Go to Site Dashboard link and cannot open /site", async ({ page }) => {
  await mockLoginApi(page, "OFFICE_USER");
  await page.goto("/");
  await page.getByLabel("Email address").fill("office@example.test");
  await page.getByLabel("Password").fill("correct-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/^http:\/\/[^/]+\/$/);
  await expect(page.getByRole("link", { name: /Go to Site Dashboard/i })).toHaveCount(0);
  await page.goto("/site");
  await expect(page).toHaveURL(/^http:\/\/[^/]+\/$/);
});

test("an expired session on /site redirects to /site-login with returnTo=/site (no dead end)", async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("hmh_access_token", "stale-token"); localStorage.setItem("hmh_user_role", "OWNER"); });
  await page.route("**/api/v1/users/me", route => route.fulfill({ status: 401, json: { detail: "Session expired" } }));
  await page.goto("/site");
  await expect(page).toHaveURL(/\/site-login\?returnTo=%2Fsite/);
  await expect(page.getByRole("button", { name: /sign in to site portal/i })).toBeVisible();
});

test("dual-access role logging in via /site-login with returnTo=/site lands on /site, not an access-denied screen", async ({ page }) => {
  // Regression test for the SiteLoginPage bug this task fixed: previously any
  // non-SITE_ROLE_SET role (including the now-supported OWNER/OFFICE_ADMIN
  // dual-access roles) hit the "Site portal access only" dead end here,
  // which combined with SiteRoute now admitting them would have been a
  // login loop back to /site-login every time their session needed refreshing.
  await mockLoginApi(page, "OWNER");
  await page.goto("/site-login?returnTo=%2Fsite");
  await page.getByLabel("Email address").fill("owner@example.test");
  await page.getByLabel("Password").fill("correct-password");
  await page.getByRole("button", { name: /sign in to site portal/i }).click();
  await expect(page).toHaveURL(/\/site$/);
  await expect(page.getByText(/Site portal access only/i)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Fuel request" })).toBeVisible();
});
