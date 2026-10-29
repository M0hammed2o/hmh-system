/**
 * A `test` that cannot reach anything but localhost.
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
 * part that does not depend on remembering: every request the page makes is
 * inspected, anything not addressed to localhost is aborted, and the test
 * fails naming the URL.
 *
 * Import `test` from here instead of from `playwright/test` in any suite
 * that is supposed to stay local. The deliberate production suites under
 * tests/production/ import from `playwright/test` directly, which is how
 * they stay able to do their job.
 */

import { test as base, expect } from "playwright/test";

const LOCAL_HOST = /^(127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1\])(:\d+)?$/;

export const test = base.extend({
  context: async ({ context }, use) => {
    const escaped = [];

    await context.route("**/*", (route) => {
      let host;
      try {
        host = new URL(route.request().url()).host;
      } catch {
        // Not an absolute URL (data:, blob:, about:). Nothing leaves the
        // machine, so let it through.
        return route.continue();
      }
      if (LOCAL_HOST.test(host)) return route.continue();

      escaped.push(route.request().url());
      return route.abort("blockedbyclient");
    });

    await use(context);

    if (escaped.length > 0) {
      const unique = [...new Set(escaped)];
      throw new Error(
        "This suite is local-only and the page tried to reach a remote host. " +
        "The requests were blocked, so nothing was sent — but the build under " +
        "test is addressing the wrong backend. Rebuild it with " +
        "vite.config.demo.mjs.\n  " + unique.slice(0, 10).join("\n  "),
      );
    }
  },
});

export { expect };
