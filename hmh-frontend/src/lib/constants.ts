// <reference types="vite/client" />

export const TOKEN_KEY = "hmh_access_token";
export const REFRESH_TOKEN_KEY = "hmh_refresh_token";
export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";