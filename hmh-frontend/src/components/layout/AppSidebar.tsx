import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Users, FolderKanban, FileSpreadsheet,
  ShoppingCart, Truck, Package, CreditCard, Bell, Settings, LogOut, HardHat,
  Droplet, Building2, Car, FileCheck2, Smartphone, Mail, Clock, Flag, Warehouse, BarChart2, ClipboardList, Receipt, GitMerge, Wrench,
  FileText, GitBranch, CalendarCheck,
} from "lucide-react";
import { HMHLogo } from "@/components/HMHLogo";
import { TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY } from "@/lib/constants";
import { cn } from "@/lib/utils";

const navGroups = [
  {
    label: "Overview",
    items: [
      { title: "Dashboard",       path: "/",               icon: LayoutDashboard },
      { title: "Owner View",      path: "/owner",          icon: Smartphone },
      { title: "Alerts",          path: "/alerts",         icon: Bell },
    ],
  },
  {
    label: "Projects",
    items: [
      { title: "Projects",        path: "/projects",       icon: FolderKanban },
      { title: "BOQ",             path: "/boq",            icon: FileSpreadsheet },
    ],
  },
  {
    label: "Procurement",
    items: [
      { title: "Procurement",          path: "/procurement",           icon: ShoppingCart },
      { title: "Suppliers",            path: "/suppliers",             icon: Building2 },
      { title: "Companies",            path: "/companies",             icon: Building2 },
      { title: "Deliveries",           path: "/deliveries",            icon: Truck },
      { title: "Reconciliation",       path: "/reconciliation",        icon: GitMerge },
      { title: "Procurement Analytics",path: "/procurement-analytics", icon: BarChart2 },
      { title: "Gmail Inbox",          path: "/gmail-inbox",           icon: Mail },
    ],
  },
  {
    label: "Warehouse",
    items: [
      { title: "Main Warehouse",     path: "/warehouse",         icon: Warehouse },
      { title: "Project Warehouse",  path: "/project-warehouse", icon: Package   },
    ],
  },
  {
    label: "Labour",
    items: [
      { title: "Job Cards",              path: "/labour",                       icon: HardHat },
      { title: "Work Done / Claims",     path: "/work-done",                    icon: ClipboardList },
      { title: "Monthly Subcon Summary", path: "/work-done/monthly-summary",    icon: BarChart2 },
    ],
  },
  {
    label: "Finance",
    items: [
      { title: "Municipality Invoices", path: "/municipality-invoices", icon: Receipt },
      { title: "Payments",              path: "/payments",              icon: CreditCard },
      { title: "Payment Reports",       path: "/payment-reports",       icon: FileCheck2 },
    ],
  },
  {
    label: "Fleet",
    items: [
      { title: "Vehicles",        path: "/vehicles",       icon: Car    },
      { title: "Fuel",            path: "/fuel",           icon: Droplet },
      { title: "Workshop",        path: "/workshop",       icon: Wrench  },
    ],
  },
  {
    label: "Progress",
    items: [
      { title: "Milestones",       path: "/milestones",      icon: Flag          },
      { title: "Progress Claims",  path: "/progress-claims", icon: FileText      },
      { title: "Programme Plan",   path: "/programme",       icon: GitBranch     },
      { title: "Weekly Plans",     path: "/weekly-plans",    icon: CalendarCheck },
    ],
  },
  {
    label: "Admin",
    items: [
      { title: "Users",           path: "/users",          icon: Users },
      { title: "User Activity",   path: "/audit",          icon: Clock },
      { title: "Settings",        path: "/settings",       icon: Settings },
    ],
  },
];

export function AppSidebar() {
  const location = useLocation();

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
    window.location.href = "/login";
  };

  return (
    <aside className="hidden lg:flex flex-col w-64 bg-sidebar border-r border-sidebar-border h-screen overflow-y-auto sticky top-0 shrink-0">
      {/* Logo / brand */}
      <div className="flex items-center px-5 py-4 border-b border-sidebar-border shrink-0">
        <HMHLogo variant="light" size="md" />
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-4">
        {navGroups.map((group) => (
          <div key={group.label}>
            <p className="px-3 mb-1 text-[10px] font-semibold text-sidebar-muted uppercase tracking-widest">
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const isActive = item.path === "/"
                  ? location.pathname === "/"
                  : location.pathname.startsWith(item.path);
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                      isActive
                        ? "bg-sidebar-accent text-sidebar-primary"
                        : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                    )}
                  >
                    <item.icon className="w-4 h-4 shrink-0" />
                    {item.title}
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Logout */}
      <div className="px-3 pb-5 shrink-0">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium w-full text-sidebar-muted hover:bg-sidebar-accent hover:text-destructive transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Logout
        </button>
      </div>
    </aside>
  );
}
