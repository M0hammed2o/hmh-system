import { useEffect, useState } from "react";
import { PWA_UPDATE_EVENT } from "@/pwa/registerServiceWorker";

export function PwaUpdatePrompt() {
  const [registration, setRegistration] = useState<ServiceWorkerRegistration | null>(null);

  useEffect(() => {
    const onUpdate = (event: Event) => {
      setRegistration((event as CustomEvent<ServiceWorkerRegistration>).detail);
    };
    window.addEventListener(PWA_UPDATE_EVENT, onUpdate);
    return () => window.removeEventListener(PWA_UPDATE_EVENT, onUpdate);
  }, []);

  if (!registration) return null;

  const activate = () => {
    let reloaded = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (!reloaded) {
        reloaded = true;
        window.location.reload();
      }
    });
    registration.waiting?.postMessage({ type: "SKIP_WAITING" });
  };

  return (
    <div className="fixed inset-x-3 bottom-3 z-[100] mx-auto flex max-w-md items-center gap-3 rounded-xl border border-border bg-background p-3 shadow-xl" role="status">
      <p className="min-w-0 flex-1 text-sm">A new HMH version is ready.</p>
      <button className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground" onClick={activate}>
        Update now
      </button>
      <button className="px-2 py-2 text-sm text-muted-foreground" onClick={() => setRegistration(null)} aria-label="Dismiss update">
        Later
      </button>
    </div>
  );
}
