import { SITE_ROLE_SET, DUAL_ACCESS_ROLE_SET } from "@/lib/constants";

const AUTH_PATHS = new Set(["/login", "/site-login", "/set-password"]);

export function safeReturnTo(search: string): string | null {
  const candidate = new URLSearchParams(search).get("returnTo");
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) return null;

  const pathname = candidate.split(/[?#]/, 1)[0];
  if (AUTH_PATHS.has(pathname)) return null;
  return candidate;
}

export function landingForRole(role: string, requestedPath: string | null): string {
  const isSiteUser = SITE_ROLE_SET.has(role);
  const canReachSitePortal = isSiteUser || DUAL_ACCESS_ROLE_SET.has(role);
  if (requestedPath) {
    const requestsSitePortal = requestedPath === "/site" || requestedPath.startsWith("/site/");
    // A site-portal request is honoured for anyone who can reach it (pure site
    // roles, or a dual-access office role returning to /site); a non-site
    // request is honoured for anyone who isn't locked into the site portal.
    if (requestsSitePortal ? canReachSitePortal : !isSiteUser) return requestedPath;
  }
  return isSiteUser ? "/site" : "/";
}

export function loginUrlFor(pathname: string, search = ""): string {
  const isSiteRoute = pathname === "/site" || pathname.startsWith("/site/");
  const loginPath = isSiteRoute ? "/site-login" : "/login";
  const returnTo = `${pathname}${search}`;
  return `${loginPath}?returnTo=${encodeURIComponent(returnTo)}`;
}
