import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "./ProtectedRoute";
import { SiteRoute } from "./SiteRoute";
import LoginPage from "@/pages/LoginPage";
import SiteLoginPage from "@/pages/SiteLoginPage";
import SiteDashboardPage from "@/pages/SiteDashboardPage";
import DashboardPage from "@/pages/DashboardPage";
import OwnerDashboardPage from "@/pages/OwnerDashboardPage";
import UsersPage from "@/pages/UsersPage";
import ProjectsPage from "@/pages/ProjectsPage";
import ProjectDetailPage from "@/pages/ProjectDetailPage";
import BOQPage from "@/pages/BOQPage";
import BOQBuilderPage from "@/pages/BOQBuilderPage";
import BOQTemplatesPage from "@/pages/BOQTemplatesPage";
import ProcurementPage from "@/pages/ProcurementPage";
import DeliveriesPage from "@/pages/DeliveriesPage";
import StockPage from "@/pages/StockPage";
import PaymentsPage from "@/pages/PaymentsPage";
import AlertsPage from "@/pages/AlertsPage";
import SettingsPage from "@/pages/SettingsPage";
import FuelPage from "@/pages/FuelPage";
import SuppliersPage from "@/pages/SuppliersPage";
import SetPasswordPage from "@/pages/SetPasswordPage";
import VehiclesPage from "@/pages/VehiclesPage";
import LotDetailPage from "@/pages/LotDetailPage";
import SiteMaterialsPage from "@/pages/SiteMaterialsPage";
import InvoiceReconciliationPage from "@/pages/InvoiceReconciliationPage";
import LabourPage from "@/pages/LabourPage";
import WhatsAppQueuePage from "@/pages/WhatsAppQueuePage";
import GmailInboxPage from "@/pages/GmailInboxPage";

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        {/* ── Public routes ── */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/site-login" element={<SiteLoginPage />} />
        <Route path="/set-password" element={<SetPasswordPage />} />

        {/* ── Site portal ── */}
        <Route
          path="/site"
          element={
            <SiteRoute>
              <SiteDashboardPage />
            </SiteRoute>
          }
        />

        {/* ── Office / owner portal ── */}
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="owner" element={<OwnerDashboardPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="lots/:lotId" element={<LotDetailPage />} />
          <Route path="boq" element={<BOQPage />} />
          <Route path="boq/:projectId/:headerId/build" element={<BOQBuilderPage />} />
          <Route path="boq-templates" element={<BOQTemplatesPage />} />
          <Route path="procurement" element={<ProcurementPage />} />
          <Route path="deliveries" element={<DeliveriesPage />} />
          <Route path="stock" element={<StockPage />} />
          <Route path="site-materials" element={<SiteMaterialsPage />} />
          <Route path="payments" element={<PaymentsPage />} />
          <Route path="reconciliation" element={<InvoiceReconciliationPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="labour" element={<LabourPage />} />
          <Route path="whatsapp-queue" element={<WhatsAppQueuePage />} />
          <Route path="gmail-inbox" element={<GmailInboxPage />} />
          <Route path="fuel" element={<FuelPage />} />
          <Route path="suppliers" element={<SuppliersPage />} />
          <Route path="vehicles" element={<VehiclesPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
