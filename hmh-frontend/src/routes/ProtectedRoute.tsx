import { Navigate } from "react-router-dom";
import { TOKEN_KEY, ROLE_KEY, SITE_ROLE_SET } from "@/lib/constants";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

/**
 * Guards all office/admin routes (anything under "/").
 * - No token            → /login
 * - Site role (stored)  → /site  (user logged in via wrong portal)
 * - Any office/owner role → render children
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return <Navigate to="/login" replace />;

  const role = localStorage.getItem(ROLE_KEY);
  if (role && SITE_ROLE_SET.has(role)) {
    return <Navigate to="/site" replace />;
  }

  return <>{children}</>;
}
