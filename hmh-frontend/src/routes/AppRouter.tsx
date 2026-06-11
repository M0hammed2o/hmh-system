import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "./ProtectedRoute";
import { SiteRoute } from "./SiteRoute";

// Auth pages — always needed at startup, keep static
import LoginPage from "@/pages/LoginPage";
import SiteLoginPage from "@/pages/SiteLoginPage";
import SetPasswordPage from "@/pages/SetPasswordPage";

// All operational pages — lazy loaded per route
const SiteDashboardPage       = lazy(() => import("@/pages/SiteDashboardPage"));
const DashboardPage           = lazy(() => import("@/pages/DashboardPage"));
const OwnerDashboardPage      = lazy(() => import("@/pages/OwnerDashboardPage"));
const UsersPage               = lazy(() => import("@/pages/UsersPage"));
const ProjectsPage            = lazy(() => import("@/pages/ProjectsPage"));
const ProjectDetailPage       = lazy(() => import("@/pages/ProjectDetailPage"));
const BOQPage                 = lazy(() => import("@/pages/BOQPage"));
const BOQBuilderPage          = lazy(() => import("@/pages/BOQBuilderPage"));
const BOQTemplatesPage        = lazy(() => import("@/pages/BOQTemplatesPage"));
const ProcurementPage         = lazy(() => import("@/pages/ProcurementPage"));
const DeliveriesPage          = lazy(() => import("@/pages/DeliveriesPage"));
const MainWarehousePage       = lazy(() => import("@/pages/MainWarehousePage"));
const ProjectWarehousePage    = lazy(() => import("@/pages/ProjectWarehousePage"));
const PaymentsPage            = lazy(() => import("@/pages/PaymentsPage"));
const PaymentReportsPage      = lazy(() => import("@/pages/PaymentReportsPage"));
const InvoiceReconciliationPage = lazy(() => import("@/pages/InvoiceReconciliationPage"));
const ReconciliationPage        = lazy(() => import("@/pages/ReconciliationPage"));
const AlertsPage              = lazy(() => import("@/pages/AlertsPage"));
const LabourPage              = lazy(() => import("@/pages/LabourPage"));
const WhatsAppQueuePage       = lazy(() => import("@/pages/WhatsAppQueuePage"));
const GmailInboxPage          = lazy(() => import("@/pages/GmailInboxPage"));
const FuelPage                = lazy(() => import("@/pages/FuelPage"));
const SuppliersPage           = lazy(() => import("@/pages/SuppliersPage"));
const SupplierProfilePage     = lazy(() => import("@/pages/SupplierProfilePage"));
const VehiclesPage            = lazy(() => import("@/pages/VehiclesPage"));
const LotDetailPage           = lazy(() => import("@/pages/LotDetailPage"));
const MilestonesPage          = lazy(() => import("@/pages/MilestonesPage"));
const TimelinePage            = lazy(() => import("@/pages/TimelinePage"));
const AuditPage               = lazy(() => import("@/pages/AuditPage"));
const NotificationSettingsPage    = lazy(() => import("@/pages/NotificationSettingsPage"));
const ProcurementAnalyticsPage    = lazy(() => import("@/pages/ProcurementAnalyticsPage"));
const SettingsPage            = lazy(() => import("@/pages/SettingsPage"));
const WorkDonePage            = lazy(() => import("@/pages/WorkDonePage"));
const MonthlySubcontractorSummaryPage = lazy(() => import("@/pages/MonthlySubcontractorSummaryPage"));

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="h-8 w-8 rounded-full border-4 border-primary border-t-transparent animate-spin" />
    </div>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
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
            <Route path="stock" element={<Navigate to="/warehouse" replace />} />
            <Route path="site-materials" element={<Navigate to="/warehouse" replace />} />
            <Route path="warehouse" element={<MainWarehousePage />} />
            <Route path="project-warehouse" element={<ProjectWarehousePage />} />
            <Route path="payments" element={<PaymentsPage />} />
            <Route path="payment-reports" element={<PaymentReportsPage />} />
            <Route path="reconciliation" element={<ReconciliationPage />} />
            <Route path="reconciliation/proof-packs" element={<InvoiceReconciliationPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="labour" element={<LabourPage />} />
            <Route path="whatsapp-queue" element={<WhatsAppQueuePage />} />
            <Route path="gmail-inbox" element={<GmailInboxPage />} />
            <Route path="fuel" element={<FuelPage />} />
            <Route path="suppliers" element={<SuppliersPage />} />
            <Route path="suppliers/:supplierId" element={<SupplierProfilePage />} />
            <Route path="vehicles" element={<VehiclesPage />} />
            <Route path="milestones" element={<MilestonesPage />} />
            <Route path="timeline" element={<TimelinePage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="notification-settings" element={<NotificationSettingsPage />} />
            <Route path="procurement-analytics" element={<ProcurementAnalyticsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="work-done" element={<WorkDonePage />} />
            <Route path="work-done/monthly-summary" element={<MonthlySubcontractorSummaryPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
