import { defineConfig } from "playwright/test";
export default defineConfig({
  testDir: "./tests/verify",
  timeout: 90_000,
  workers: 1,
  reporter: [["list"]],
  use: { viewport: { width: 1440, height: 900 }, screenshot: "only-on-failure" },
});
