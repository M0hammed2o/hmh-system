import axios from "axios";
import { TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY, API_BASE, SITE_ROLE_SET } from "@/lib/constants";

const client = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// Attach access token to every request
client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On 401: clear session and redirect to the correct login page
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(ROLE_KEY);

      // Redirect to site-login if the user was on a site route, else admin login
      const isSiteRoute = window.location.pathname.startsWith("/site");
      window.location.href = isSiteRoute ? "/site-login" : "/login";
    }
    return Promise.reject(err);
  }
);

export default client;
