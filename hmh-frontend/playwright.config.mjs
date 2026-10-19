import { defineConfig } from "playwright/test";

export default defineConfig({
  testDir: "./tests",
  // The audit and production suites need their own environments - a local
  // backend bound to a throwaway database, or the live site - and each has
  // its own config. Sweeping them in here would point the audit specs at
  // whatever this preview happens to serve, which at one point meant posting
  // a local test login at production.
  testIgnore: ["audit/**", "production/**", "verify/**"],
  timeout: 30_000,
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:4173",
    serviceWorkers: "allow",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173/login",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
