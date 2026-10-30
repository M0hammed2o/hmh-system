import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

/**
 * An identifier that changes with every build.
 *
 * It exists so the service worker can be registered under a URL that moves
 * when the app does. public/sw.js is copied verbatim and its contents had
 * not changed since August, so the browser — which decides whether to
 * install a new worker by byte-comparing the script — saw the same file
 * after every deploy and never installed one. No new worker means no
 * `updatefound`, no `registration.waiting`, and the "A new HMH version is
 * ready" prompt that has been in the app all along never once appeared.
 *
 * Vercel sets VERCEL_GIT_COMMIT_SHA, which ties the id to the commit. The
 * timestamp is the local fallback.
 */
const BUILD_ID =
  process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 12) ?? String(Date.now());

export default defineConfig({
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: {
          // React core — changes rarely, best for long-term caching
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          // Radix UI primitives — stable across releases
          "vendor-radix": [
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-label",
            "@radix-ui/react-select",
            "@radix-ui/react-slot",
            "@radix-ui/react-toast",
          ],
          // Utility libs
          "vendor-utils": ["axios", "clsx", "class-variance-authority", "tailwind-merge", "lucide-react"],
        },
      },
    },
  },
});
