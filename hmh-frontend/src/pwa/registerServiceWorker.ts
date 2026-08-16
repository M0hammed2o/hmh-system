export const PWA_UPDATE_EVENT = "hmh:pwa-update";

export function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || !import.meta.env.PROD) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).then((registration) => {
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
    }).catch((error) => {
      console.warn("HMH offline support could not be registered.", error);
    });
  });
}
