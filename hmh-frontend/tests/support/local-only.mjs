/**
 * A `test` that cannot reach the application backend over the network.
 *
 * Local browser suites drive a built bundle, and which backend that bundle
 * addresses is decided at build time by whichever .env file Vite happened to
 * load. `npm run preview` serves `dist/`, and `dist/` is normally a
 * production build — so a suite meant to exercise a throwaway database was
 * one stale directory away from driving the live system. That is not a
 * hypothetical: it happened here, and the symptom was a login failure, not
 * an alarm.
 *
 * Pinning the build is necessary but not sufficient, because it only holds
 * for as long as everyone remembers to pass the right config. This is the
 * part that does not depend on remembering.
 *
 * Import `test` from here instead of from `playwright/test` in any suite
 * that is supposed to stay local. The deliberate production suites under
 * tests/production/ import from `playwright/test` directly, which is how
 * they stay able to do their job.
 */

import { test as base, expect } from "playwright/test";

const LOCAL_HOST = /^(127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1\])(:\d+)?$/;

/**
 * Static asset hosts the application loads from a CDN.
 *
 * Allowed because they are stylesheets and font files: they carry no
 * application data, they are not an API, and blocking them makes every
 * screenshot render in a fallback font, which quietly degrades the evidence
 * these suites exist to produce. The API rule below still applies to them,
 * so an allowlisted host cannot become a backdoor to a backend.
 */
const STATIC_ASSET_HOSTS = new Set([
  "fonts.googleapis.com",
  "fonts.gstatic.com",
]);

/**
 * Anything that looks like the application's own API must be local, whatever
 * host it claims to be. This is the rule that actually matters; the host
 * allowlist above is a convenience that cannot weaken it.
 */
const API_PATH = /\/api\/v\d/;

export const test = base.extend({
  context: async ({ context }, use) => {
    const escaped = [];

    await context.route("**/*", (route) => {
      const url = route.request().url();
      let parsed;
      try {
        parsed = new URL(url);
      } catch {
        // Not an absolute URL (data:, blob:, about:). Nothing leaves the
        // machine, so let it through.
        return route.continue();
      }

      const local = LOCAL_HOST.test(parsed.host);
      if (local) return route.continue();

      if (API_PATH.test(parsed.pathname)) {
        escaped.push(`${url}  (API call to a remote host)`);
        return route.abort("blockedbyclient");
      }

      if (STATIC_ASSET_HOSTS.has(parsed.hostname)) return route.continue();

      escaped.push(url);
      return route.abort("blockedbyclient");
    });

    await use(context);

    if (escaped.length > 0) {
      const unique = [...new Set(escaped)];
      throw new Error(
        "This suite is local-only and the page tried to reach a remote host. " +
        "The requests were blocked, so nothing was sent — but the build under " +
        "test may be addressing the wrong backend. Rebuild it with " +
        "vite.config.demo.mjs.\n  " + unique.slice(0, 10).join("\n  "),
      );
    }
  },
});

export { expect };
