/** A small, always-visible guard against confusing TEST with production. */
export function EnvironmentBadge() {
  const environment = (import.meta.env.VITE_APP_ENV || "production").toLowerCase();

  if (environment !== "test") return null;

  return (
    <div
      className="fixed right-3 top-3 z-[100] rounded-full border border-amber-300/70 bg-amber-50/95 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-amber-900 shadow-sm backdrop-blur"
      role="status"
      aria-label="Test environment"
    >
      Test environment
    </div>
  );
}
