/**
 * Playwright config for live production checks.
 *
 * Starts no server: these run against https://app.hmhgroup.co.za itself.
 * Nothing here authenticates — see the spec header.
 */
import { defineConfig } from "playwright/test";

export default defineConfig({
  testDir: "./tests/production",
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [["list"]],
  use: {
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    ignoreHTTPSErrors: false,
  },
});
