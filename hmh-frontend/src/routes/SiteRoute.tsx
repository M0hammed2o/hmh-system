import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { TOKEN_KEY, ROLE_KEY, SITE_ROLE_SET } from "@/lib/constants";
import { usersApi, type UserRole } from "@/api/users";

/** Typed list kept for use in login pages that import from here. */
export const SITE_ROLES: UserRole[] = ["SITE_MANAGER", "SITE_STAFF"];

type Status = "loading" | "site" | "office" | "unauthenticated";

/**
 * Guards /site.
 * - No token                  → /site-login
 * - Stored role is a site role → render immediately (no API call)
 * - Stored role is office role → /  (wrong portal)
 * - No stored role             → verify via API, then cache it
 */
export function SiteRoute({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return "unauthenticated";

    const role = localStorage.getItem(ROLE_KEY);
    if (role) {
      return SITE_ROLE_SET.has(role) ? "site" : "office";
    }
    return "loading";
  });

  useEffect(() => {
    if (status !== "loading") return;

    usersApi
      .me()
      .then((user) => {
        localStorage.setItem(ROLE_KEY, user.role);
        setStatus(SITE_ROLE_SET.has(user.role) ? "site" : "office");
      })
      .catch(() => setStatus("unauthenticated"));
  }, [status]);

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-sm">Verifying access…</p>
        </div>
      </div>
    );
  }

  if (status === "unauthenticated") return <Navigate to="/site-login" replace />;
  if (status === "office")         return <Navigate to="/" replace />;
  return <>{children}</>;
}
