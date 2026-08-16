import { Navigate, useLocation } from "react-router-dom";
import { TOKEN_KEY, SITE_ROLE_SET, DUAL_ACCESS_ROLE_SET } from "@/lib/constants";
import { type UserRole } from "@/api/users";
import { useAuthContext } from "@/context/AuthContext";
import { loginUrlFor } from "./authNavigation";

/** Typed list kept for use in login pages that import from here. */
export const SITE_ROLES: UserRole[] = ["SITE_MANAGER", "SITE_MANAGER_VIEW", "SITE_STAFF"];

/** Guards the site portal with a server-verified current user. */
export function SiteRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { user, loading } = useAuthContext();
  const token = localStorage.getItem(TOKEN_KEY);
  const loginUrl = loginUrlFor(location.pathname, location.search);

  if (token && loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-sm">Verifying access…</p>
        </div>
      </div>
    );
  }

  if (!token || !user) return <Navigate to={loginUrl} replace />;
  if (!SITE_ROLE_SET.has(user.role) && !DUAL_ACCESS_ROLE_SET.has(user.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}
