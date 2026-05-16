// <reference types="vite/client" />

export const TOKEN_KEY         = "hmh_access_token";
export const REFRESH_TOKEN_KEY = "hmh_refresh_token";
export const ROLE_KEY          = "hmh_user_role";

/**
 * API base URL resolution — three-tier fallback:
 *
 * 1. VITE_API_BASE_URL env var (set in Cloudflare Pages dashboard or .env.production)
 * 2. Auto-detect production by hostname (covers case where env var is not set but
 *    the app is running on the real production domain — .env.production is gitignored
 *    so this ensures production always hits the correct Render backend).
 * 3. Local development default.
 */
const PRODUCTION_BACKEND = "https://hmh-backend-uhzu.onrender.com/api/v1";
const PRODUCTION_HOSTS   = ["app.hmhgroup.co.za", "www.app.hmhgroup.co.za"];

function resolveApiBase(): string {
  // Tier 1: explicit env var always wins
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL as string;
  }
  // Tier 2: running on the production domain → use the Render backend
  if (typeof window !== "undefined" && PRODUCTION_HOSTS.includes(window.location.hostname)) {
    return PRODUCTION_BACKEND;
  }
  // Tier 3: local dev
  return "http://localhost:8000/api/v1";
}

export const API_BASE = resolveApiBase();

/** Roles that belong to the site portal. All other roles use the office portal. */
export const SITE_ROLE_SET = new Set(["SITE_MANAGER", "SITE_STAFF"]);
