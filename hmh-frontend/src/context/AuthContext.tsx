import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { usersApi, type User, type UserRole } from "@/api/users";
import { TOKEN_KEY } from "@/lib/constants";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  role: UserRole | null;
  /** Re-fetch the current user (e.g. after role change) */
  refresh: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  role: null,
  refresh: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    usersApi
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchMe();
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, role: (user?.role as UserRole) ?? null, refresh: fetchMe }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthContext() {
  return useContext(AuthContext);
}

/** Roles that can access the office portal admin features */
export const ADMIN_ROLES: UserRole[] = ["OWNER", "OFFICE_ADMIN"];
/** Roles that can access general office data (read-only modules) */
export const OFFICE_ROLES: UserRole[] = ["OWNER", "OFFICE_ADMIN", "OFFICE_USER"];
