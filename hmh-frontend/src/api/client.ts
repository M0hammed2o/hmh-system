import axios from "axios";
import { TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY, API_BASE } from "@/lib/constants";

const client = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// Attach access token to every request
client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // For FormData, delete the default Content-Type so the browser can set
  // multipart/form-data with the correct boundary automatically.
  if (config.data instanceof FormData) {
    delete config.headers["Content-Type"];
  }
  return config;
});

// On 401: clear session and redirect to the correct login page
client.interceptors.response.use(
  (res) => res,
  (err) => {
    const requestUrl = String(err.config?.url ?? "");
    const isLoginRequest = requestUrl.includes("/auth/login");
    const isLoginPage = window.location.pathname === "/login" || window.location.pathname === "/site-login";

    if (err.response?.status === 401 && !isLoginRequest) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(ROLE_KEY);

      if (!isLoginPage) {
        const isSiteRoute = window.location.pathname === "/site" || window.location.pathname.startsWith("/site/");
        const loginPath = isSiteRoute ? "/site-login" : "/login";
        const returnTo = `${window.location.pathname}${window.location.search}`;
        window.location.replace(`${loginPath}?returnTo=${encodeURIComponent(returnTo)}`);
      }
    }
    return Promise.reject(err);
  }
);

export default client;
