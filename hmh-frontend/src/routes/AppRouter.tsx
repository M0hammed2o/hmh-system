import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "./ProtectedRoute";
import { SiteRoute } from "./SiteRoute";
import LoginPage from "@/pages/LoginPage";
import SiteLoginPage from "@/pages/SiteLoginPage";
import SiteDashboardPage from "@/pages/SiteDashboardPage";
import DashboardPage from "@/pages/DashboardPage";
import UsersPage from "@/pages/UsersPage";
import ProjectsPage from "@/pages/ProjectsPage";
import ProjectDetailPage from "@/pages/ProjectDetailPage";
import BOQPage from "@/pages/BOQPage";
import ProcurementPage from "@/pages/ProcurementPage";
import DeliveriesPage from "@/pages/DeliveriesPage";
import StockPage from "@/pages/StockPage";
import PaymentsPage from "@/pages/PaymentsPage";
import AlertsPage from "@/pages/AlertsPage";
import SettingsPage from "@/pages/SettingsPage";
import FuelPage from "@/pages/FuelPage";
import SuppliersPage from "@/pages/SuppliersPage";
import SetPasswordPage from "@/pages/SetPasswordPage";

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* ── Public routes ── */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/site-login" element={<SiteLoginPage />} />
        <Route path="/set-password" element={<SetPasswordPage />} />

        {/* ── Site portal — no office sidebar, role-gated to site roles ── */}
        <Route
          path="/site"
          element={
            <SiteRoute>
              <SiteDashboardPage />
            </SiteRoute>
          }
        />

        {/* ── Office / owner portal — full layout with sidebar ── */}
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="boq" element={<BOQPage />} />
          <Route path="procurement" element={<ProcurementPage />} />
          <Route path="deliveries" element={<DeliveriesPage />} />
          <Route path="stock" element={<StockPage />} />
          <Route path="payments" element={<PaymentsPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="fuel" element={<FuelPage />} />
          <Route path="suppliers" element={<SuppliersPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
