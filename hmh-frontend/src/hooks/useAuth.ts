// Re-export from AuthContext so there is a single source of truth.
// DashboardPage and anything importing useAuth() will get the shared context value
// (no extra /users/me fetch on every component mount).
export { useAuthContext as useAuth } from "@/context/AuthContext";
