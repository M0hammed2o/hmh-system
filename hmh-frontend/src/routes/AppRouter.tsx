import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "./ProtectedRoute";
import { SiteRoute } from "./SiteRoute";
import { SERVICE_BLOCKED } from "@/config/serviceBlock";

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
const GmailInboxPage          = lazy(() => import("@/pages/GmailInboxPage"));
const FuelPage                = lazy(() => import("@/pages/FuelPage"));
const SuppliersPage           = lazy(() => import("@/pages/SuppliersPage"));
const CompaniesPage             = lazy(() => import("@/pages/CompaniesPage"));
const ProjectCostSummaryPage    = lazy(() => import("@/pages/ProjectCostSummaryPage"));
const SupplierProfilePage     = lazy(() => import("@/pages/SupplierProfilePage"));
const VehiclesPage            = lazy(() => import("@/pages/VehiclesPage"));
const WorkshopPage            = lazy(() => import("@/pages/WorkshopPage"));
const LotDetailPage           = lazy(() => import("@/pages/LotDetailPage"));
const MilestonesPage          = lazy(() => import("@/pages/MilestonesPage"));
const TimelinePage            = lazy(() => import("@/pages/TimelinePage"));
const AuditPage               = lazy(() => import("@/pages/AuditPage"));
const ProcurementAnalyticsPage    = lazy(() => import("@/pages/ProcurementAnalyticsPage"));
const SettingsPage            = lazy(() => import("@/pages/SettingsPage"));
const WorkDonePage            = lazy(() => import("@/pages/WorkDonePage"));
const MonthlySubcontractorSummaryPage = lazy(() => import("@/pages/MonthlySubcontractorSummaryPage"));
const MunicipalityInvoicePage         = lazy(() => import("@/pages/MunicipalityInvoicePage"));
const DocumentCenterPage              = lazy(() => import("@/pages/DocumentCenterPage"));

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="h-8 w-8 rounded-full border-4 border-primary border-t-transparent animate-spin" />
    </div>
  );
}

function ServiceBlockedScreen() {
  return (
    <div className="min-h-screen bg-[#0f1117] flex flex-col items-center justify-center px-4">
      <div className="max-w-md w-full text-center space-y-8">
        {/* Logo */}
        <div className="flex flex-col items-center gap-2">
          <div className="w-16 h-16 rounded-2xl bg-[#e87c2a] flex items-center justify-center">
            <span className="text-white font-black text-2xl tracking-tight">HMH</span>
          </div>
          <p className="text-xs text-gray-500 uppercase tracking-widest mt-1">Construction OS</p>
        </div>

        {/* Block message */}
        <div className="bg-[#1a1d27] border border-red-800/60 rounded-2xl px-8 py-10 space-y-4">
          <div className="w-14 h-14 rounded-full bg-red-900/40 flex items-center justify-center mx-auto">
            <svg className="w-7 h-7 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-white">Service Unavailable</h1>
          <p className="text-gray-300 text-sm leading-relaxed">
            This service cannot be accessed at this time.
          </p>
          <div className="border-t border-gray-700 pt-4 space-y-1">
            <p className="text-gray-400 text-xs uppercase tracking-wide">For access, contact</p>
            <p className="text-white font-semibold text-base">Mohammed Moosa</p>
            <a
              href="tel:0837866021"
              className="inline-block text-[#e87c2a] font-bold text-lg hover:underline"
            >
              083 786 6021
            </a>
          </div>
        </div>

        <p className="text-gray-600 text-xs">HMH Group · Construction Management Platform</p>
      </div>
    </div>
  );
}

export function AppRouter() {
  if (SERVICE_BLOCKED) {
    return <ServiceBlockedScreen />;
  }

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
            <Route path="projects/:projectId/cost-summary" element={<ProjectCostSummaryPage />} />
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
            <Route path="whatsapp-queue" element={<Navigate to="/alerts" replace />} />
            <Route path="labour" element={<LabourPage />} />
            <Route path="gmail-inbox" element={<GmailInboxPage />} />
            <Route path="fuel" element={<FuelPage />} />
            <Route path="suppliers" element={<SuppliersPage />} />
            <Route path="suppliers/:supplierId" element={<SupplierProfilePage />} />
            <Route path="companies" element={<CompaniesPage />} />
            <Route path="vehicles" element={<VehiclesPage />} />
            <Route path="workshop" element={<WorkshopPage />} />
            <Route path="milestones" element={<MilestonesPage />} />
            <Route path="timeline" element={<TimelinePage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="notification-settings" element={<Navigate to="/alerts" replace />} />
            <Route path="procurement-analytics" element={<ProcurementAnalyticsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="work-done" element={<WorkDonePage />} />
            <Route path="work-done/monthly-summary" element={<MonthlySubcontractorSummaryPage />} />
            <Route path="municipality-invoices" element={<MunicipalityInvoicePage />} />
            <Route path="documents" element={<DocumentCenterPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
