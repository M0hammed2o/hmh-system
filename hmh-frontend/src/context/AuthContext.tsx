import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { usersApi, type User, type UserRole } from "@/api/users";
import { TOKEN_KEY } from "@/lib/constants";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  role: UserRole | null;
  /** True when logged in with the READ_ONLY role — can view but not write */
  isReadOnly: boolean;
  /** Re-fetch the current user (e.g. after role change) */
  refresh: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  role: null,
  isReadOnly: false,
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
      value={{
        user,
        loading,
        role: (user?.role as UserRole) ?? null,
        isReadOnly: user?.role === "READ_ONLY",
        refresh: fetchMe,
      }}
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
/** READ_ONLY role — view-only, all write actions blocked at both backend and frontend */
export const READ_ONLY_ROLE: UserRole = "READ_ONLY";
/** Roles that can access general office data (read-only modules) */
export const OFFICE_ROLES: UserRole[] = ["OWNER", "OFFICE_ADMIN", "OFFICE_USER", "PROCUREMENT_LEAD"];
