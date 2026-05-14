// <reference types="vite/client" />

export const TOKEN_KEY         = "hmh_access_token";
export const REFRESH_TOKEN_KEY = "hmh_refresh_token";
export const ROLE_KEY          = "hmh_user_role";

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

/** Roles that belong to the site portal. All other roles use the office portal. */
export const SITE_ROLE_SET = new Set(["SITE_MANAGER", "SITE_STAFF"]);