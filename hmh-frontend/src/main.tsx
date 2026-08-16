import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import { AppRouter } from "./routes/AppRouter";
import { AuthProvider } from "./context/AuthContext";
import { PwaUpdatePrompt } from "./components/PwaUpdatePrompt";
import { registerServiceWorker } from "./pwa/registerServiceWorker";

// Apply saved theme before first paint
const saved = localStorage.getItem("theme");
if (saved === "dark") document.documentElement.classList.add("dark");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <PwaUpdatePrompt />
      <AppRouter />
    </AuthProvider>
  </React.StrictMode>
);

registerServiceWorker();
