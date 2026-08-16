import { Navigate, useLocation } from "react-router-dom";
import { TOKEN_KEY, SITE_ROLE_SET } from "@/lib/constants";
import { useAuthContext } from "@/context/AuthContext";
import { loginUrlFor } from "./authNavigation";

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
  const location = useLocation();
  const token = localStorage.getItem(TOKEN_KEY);
  const { user, loading } = useAuthContext();
  const loginUrl = loginUrlFor(location.pathname, location.search);
  if (!token) return <Navigate to={loginUrl} replace />;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="h-8 w-8 rounded-full border-4 border-primary border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!user) return <Navigate to={loginUrl} replace />;

  if (SITE_ROLE_SET.has(user.role)) {
    return <Navigate to="/site" replace />;
  }

  return <>{children}</>;
}
