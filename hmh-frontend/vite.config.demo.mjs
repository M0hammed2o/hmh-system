/**
 * Vite config for the local demo stack used by the audit browser tests.
 *
 * It exists because `vite preview --outDir dist-demo` does NOT reliably
 * serve that directory — preview resolves its root from the config's
 * `build.outDir`, so the CLI flag was silently ignored and the previous
 * production build in `dist/` was served instead. That bundle points at the
 * live Render backend, so a test intended to run entirely against a local
 * throwaway database was sending its logins to production.
 *
 * Setting outDir here, in the config preview actually reads, removes the
 * possibility. The `define` below is the second belt: the API base URL is
 * pinned to the local backend at build time regardless of which .env file
 * Vite decides to load, so a bundle built with this config cannot address
 * production even if it is served from the wrong place.
 *
 *   npx vite build  --config vite.config.demo.mjs
 *   npx vite preview --config vite.config.demo.mjs --host 127.0.0.1 --port 4191
 */

import { defineConfig, mergeConfig } from "vite";

import base from "./vite.config.ts";

const DEMO_API = process.env.DEMO_API_BASE_URL ?? "http://127.0.0.1:8011/api/v1";

if (!/^http:\/\/(127\.0\.0\.1|localhost):/.test(DEMO_API)) {
  throw new Error(
    `The demo stack only ever talks to a local backend. Refusing to build ` +
    `against ${DEMO_API}.`,
  );
}

export default defineConfig(async (env) => {
  const resolved = typeof base === "function" ? await base(env) : base;
  return mergeConfig(resolved, {
    build: { outDir: "dist-demo" },
    define: {
      "import.meta.env.VITE_API_BASE_URL": JSON.stringify(DEMO_API),
    },
  });
});
