/**
 * Playwright config for the live system audit.
 *
 * Unlike playwright.config.mjs this does NOT start its own server — the
 * audit runs against a backend and preview build that are already up and
 * bound to the throwaway `hmh_audit` database, so the UI exercises real
 * endpoints and real rows rather than a stubbed shell.
 */

import { defineConfig } from "playwright/test";

export default defineConfig({
  testDir: "./tests/audit",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.AUDIT_BASE_URL ?? "http://127.0.0.1:4190",
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    video: "off",
    trace: "retain-on-failure",
  },
});
