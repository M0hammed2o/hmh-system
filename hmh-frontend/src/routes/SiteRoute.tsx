import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { TOKEN_KEY } from "@/lib/constants";
import { usersApi, type UserRole } from "@/api/users";

const SITE_ROLES: UserRole[] = ["SITE_MANAGER", "SITE_STAFF"];

type Status = "loading" | "site" | "office" | "unauthenticated";

/**
 * Guards /site.
 * - No token            → /site-login
 * - SITE_MANAGER/STAFF  → render children (the site dashboard)
 * - Any other role      → / (office dashboard)
 */
export function SiteRoute({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) { setStatus("unauthenticated"); return; }

    usersApi
      .me()
      .then((user) => {
        setStatus(SITE_ROLES.includes(user.role) ? "site" : "office");
      })
      .catch(() => setStatus("unauthenticated"));
  }, []);

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
  if (status === "office") return <Navigate to="/" replace />;
  return <>{children}</>;
}

export { SITE_ROLES };
