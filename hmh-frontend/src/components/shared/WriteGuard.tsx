/**
 * WriteGuard — renders children only when the current user is NOT read-only.
 *
 * Usage:
 *   <WriteGuard><Button onClick={handleApprove}>Approve</Button></WriteGuard>
 *
 * When the user has the READ_ONLY role, the children are not rendered at all.
 * The backend also enforces this — any write attempt returns 403.
 */
import { useAuthContext } from "@/context/AuthContext";
import type { ReactNode } from "react";

interface WriteGuardProps {
  children: ReactNode;
}

export function WriteGuard({ children }: WriteGuardProps) {
  const { isReadOnly } = useAuthContext();
  if (isReadOnly) return null;
  return <>{children}</>;
}
