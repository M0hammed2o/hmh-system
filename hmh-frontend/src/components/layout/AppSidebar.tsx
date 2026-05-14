import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Users, FolderKanban, FileSpreadsheet,
  ShoppingCart, Truck, Package, CreditCard, Bell, Settings, LogOut, HardHat,
  Droplet, Building2, Car, FileCheck2, Copy, Smartphone, MessageSquare, Mail,
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
      { title: "WhatsApp Queue",  path: "/whatsapp-queue", icon: MessageSquare },
    ],
  },
  {
    label: "Projects",
    items: [
      { title: "Projects",        path: "/projects",       icon: FolderKanban },
      { title: "BOQ",             path: "/boq",            icon: FileSpreadsheet },
      { title: "BOQ Templates",   path: "/boq-templates",  icon: Copy },
    ],
  },
  {
    label: "Procurement",
    items: [
      { title: "Procurement",     path: "/procurement",    icon: ShoppingCart },
      { title: "Suppliers",       path: "/suppliers",      icon: Building2 },
      { title: "Deliveries",      path: "/deliveries",     icon: Truck },
      { title: "Gmail Inbox",     path: "/gmail-inbox",    icon: Mail },
    ],
  },
  {
    label: "Stock & Materials",
    items: [
      { title: "Stock",           path: "/stock",          icon: Package },
      { title: "Site Materials",  path: "/site-materials", icon: Package },
    ],
  },
  {
    label: "Labour",
    items: [
      { title: "Job Cards",       path: "/labour",         icon: HardHat },
    ],
  },
  {
    label: "Finance",
    items: [
      { title: "Payments",        path: "/payments",       icon: CreditCard },
      { title: "Reconciliation",  path: "/reconciliation", icon: FileCheck2 },
    ],
  },
  {
    label: "Fleet",
    items: [
      { title: "Vehicles",        path: "/vehicles",       icon: Car },
      { title: "Fuel",            path: "/fuel",           icon: Droplet },
    ],
  },
  {
    label: "Admin",
    items: [
      { title: "Users",           path: "/users",          icon: Users },
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
    <aside className="hidden lg:flex flex-col w-64 bg-sidebar border-r border-sidebar-border min-h-screen overflow-y-auto">
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
