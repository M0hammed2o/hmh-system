export const PWA_UPDATE_EVENT = "hmh:pwa-update";

/**
 * Injected by Vite at build time; changes with every build.
 * See the BUILD_ID comment in vite.config.ts for why it has to.
 */
declare const __BUILD_ID__: string;

export function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || !import.meta.env.PROD) return;

  window.addEventListener("load", () => {
    // Registered under a URL carrying the build id.
    //
    // The browser decides whether to install a new worker by comparing the
    // script it fetches with the one it already has. public/sw.js is a
    // static file whose contents had not changed since August, so across
    // twenty-nine frontend releases the comparison always said "same
    // worker": nothing installed, `updatefound` never fired, and the update
    // prompt below never appeared. People kept running whatever build their
    // browser had, which is how a shipped feature can be missing from the
    // screen while being present in the deployed bundle.
    //
    // A different URL is a different worker as far as the browser is
    // concerned, so this moves on every deploy while sw.js itself stays a
    // plain static file.
    navigator.serviceWorker
      .register(`/sw.js?v=${__BUILD_ID__}`, { scope: "/" })
      .then((registration) => {
        const announceUpdate = () => {
          if (registration.waiting && navigator.serviceWorker.controller) {
            window.dispatchEvent(
              new CustomEvent(PWA_UPDATE_EVENT, { detail: registration })
            );
          }
        };

        announceUpdate();
        registration.addEventListener("updatefound", () => {
          const installing = registration.installing;
          installing?.addEventListener("statechange", () => {
            if (installing.state === "installed") announceUpdate();
          });
        });

        // A tab left open for days would otherwise only re-check on
        // navigation. Checking when it comes back to the foreground is what
        // makes the prompt reach somebody who keeps the app open all week,
        // which on a construction site is most people.
        const checkWhenVisible = () => {
          if (document.visibilityState === "visible") {
            registration.update().catch(() => {
              // Offline, or the check raced a reload. The next one will do.
            });
          }
        };
        document.addEventListener("visibilitychange", checkWhenVisible);
      })
      .catch((error) => {
        console.warn("HMH offline support could not be registered.", error);
      });
  });
}
