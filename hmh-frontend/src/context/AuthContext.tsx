import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { usersApi, type User, type UserRole } from "@/api/users";
import { ROLE_KEY, TOKEN_KEY } from "@/lib/constants";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  role: UserRole | null;
  /** True when logged in with the READ_ONLY role — can view but not write */
  isReadOnly: boolean;
  /** Re-fetch the current user (e.g. after role change) */
  refresh: () => Promise<User | null>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  role: null,
  isReadOnly: false,
  refresh: async () => null,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async (): Promise<User | null> => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setUser(null);
      setLoading(false);
      return null;
    }
    setLoading(true);
    try {
      const currentUser = await usersApi.me();
      localStorage.setItem(ROLE_KEY, currentUser.role);
      setUser(currentUser);
      return currentUser;
    } catch {
      localStorage.removeItem(ROLE_KEY);
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchMe();
  }, [fetchMe]);

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
