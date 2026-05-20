import { useState, useEffect } from "react";
import { useLocation, NavLink } from "react-router-dom";
import {
  Menu, X, Moon, Sun, LogOut, HardHat,
  LayoutDashboard, Users, FolderKanban, FileSpreadsheet,
  ShoppingCart, Truck, Package, CreditCard, Bell, Settings,
  Copy, Building2, Mail, Layers, FileCheck2, Car, Droplet,
  Smartphone, Clock, User, Flag, Warehouse,
} from "lucide-react";
import { TOKEN_KEY, REFRESH_TOKEN_KEY, ROLE_KEY } from "@/lib/constants";
import { useAuthContext } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

const pageTitles: Record<string, string> = {
  "/":                "Dashboard",
  "/owner":           "Owner View",
  "/users":           "Users",
  "/projects":        "Projects",
  "/boq":             "BOQ",
  "/boq-templates":   "BOQ Templates",
  "/procurement":     "Procurement",
  "/suppliers":       "Suppliers",
  "/deliveries":      "Deliveries",
  "/gmail-inbox":     "Gmail Inbox",
  "/stock":           "Stock",
  "/site-materials":  "Site Materials",
  "/labour":          "Job Cards",
  "/payments":        "Payments",
  "/reconciliation":  "Reconciliation",
  "/vehicles":        "Vehicles",
  "/fuel":            "Fuel",
  "/milestones":      "Milestones",
  "/warehouse":       "Main Warehouse",
  "/timeline":        "Timeline",
  "/audit":           "User Activity",
  "/alerts":          "Alerts",
  "/whatsapp-queue":  "WhatsApp Queue",
  "/settings":        "Settings",
};

// Groups mirror the desktop sidebar exactly
const navGroups = [
  {
    label: "Overview",
    items: [
      { title: "Dashboard",       path: "/",               icon: LayoutDashboard },
      { title: "Owner View",      path: "/owner",           icon: User },
      { title: "Alerts",          path: "/alerts",          icon: Bell },
      { title: "WhatsApp Queue",  path: "/whatsapp-queue",  icon: Smartphone },
    ],
  },
  {
    label: "Projects",
    items: [
      { title: "Projects",        path: "/projects",        icon: FolderKanban },
      { title: "BOQ",             path: "/boq",             icon: FileSpreadsheet },
      { title: "BOQ Templates",   path: "/boq-templates",   icon: Copy },
    ],
  },
  {
    label: "Procurement",
    items: [
      { title: "Procurement",     path: "/procurement",     icon: ShoppingCart },
      { title: "Suppliers",       path: "/suppliers",       icon: Building2 },
      { title: "Deliveries",      path: "/deliveries",      icon: Truck },
      { title: "Gmail Inbox",     path: "/gmail-inbox",     icon: Mail },
    ],
  },
  {
    label: "Stock & Materials",
    items: [
      { title: "Main Warehouse",  path: "/warehouse",       icon: Warehouse },
      { title: "Stock",           path: "/stock",           icon: Package },
      { title: "Site Materials",  path: "/site-materials",  icon: Layers },
    ],
  },
  {
    label: "Labour",
    items: [
      { title: "Job Cards",       path: "/labour",          icon: HardHat },
    ],
  },
  {
    label: "Finance",
    items: [
      { title: "Payments",        path: "/payments",        icon: CreditCard },
      { title: "Reconciliation",  path: "/reconciliation",  icon: FileCheck2 },
    ],
  },
  {
    label: "Fleet",
    items: [
      { title: "Vehicles",        path: "/vehicles",        icon: Car },
      { title: "Fuel",            path: "/fuel",            icon: Droplet },
    ],
  },
  {
    label: "Progress",
    items: [
      { title: "Milestones",      path: "/milestones",      icon: Flag },
    ],
  },
  {
    label: "Admin",
    items: [
      { title: "Users",           path: "/users",           icon: Users },
      { title: "User Activity",   path: "/audit",           icon: Clock },
      { title: "Settings",        path: "/settings",        icon: Settings },
    ],
  },
];

export function AppTopbar() {
  const location = useLocation();
  const { isReadOnly } = useAuthContext();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dark, setDark] = useState(() =>
    typeof window !== "undefined" && localStorage.getItem("theme") === "dark"
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  const title = Object.entries(pageTitles).find(([path]) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path)
  )?.[1] ?? "HMH Group";

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
    window.location.href = "/login";
  };

  return (
    <>
      {isReadOnly && (
        <div className="sticky top-0 z-40 bg-amber-500 text-white text-xs font-medium text-center py-1.5 px-4 flex items-center justify-center gap-2">
          <span>👁 View-Only Mode — you can browse everything but cannot make changes.</span>
        </div>
      )}
      <header className={`${isReadOnly ? "" : "sticky top-0"} z-30 flex items-center justify-between h-14 px-4 lg:px-6 border-b border-border bg-card/80 backdrop-blur-sm`}>
        <div className="flex items-center gap-3">
          <button
            className="lg:hidden p-1.5 rounded-md hover:bg-muted"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          <h1 className="text-base font-semibold">{title}</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setDark(!dark)}
            className="p-1.5 rounded-md hover:bg-muted transition-colors text-muted-foreground"
            aria-label="Toggle theme"
          >
            {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          <span className="hidden sm:inline text-xs font-medium text-muted-foreground bg-muted px-2.5 py-1 rounded-full">
            HMH Admin
          </span>
          <button
            onClick={handleLogout}
            className="hidden lg:flex items-center gap-1.5 text-xs text-muted-foreground hover:text-destructive transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            Logout
          </button>
        </div>
      </header>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          {/* Backdrop */}
          <div className="fixed inset-0 bg-foreground/40" onClick={() => setMobileOpen(false)} />

          {/* Drawer */}
          <aside className="fixed left-0 top-0 bottom-0 w-72 bg-sidebar border-r border-sidebar-border flex flex-col max-h-screen">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-sidebar-border shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-sidebar-primary/20">
                  <HardHat className="w-4 h-4 text-sidebar-primary" />
                </div>
                <span className="text-base font-semibold text-sidebar-accent-foreground">HMH Group</span>
              </div>
              <button onClick={() => setMobileOpen(false)} className="text-sidebar-foreground p-1">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Scrollable nav */}
            <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
              {navGroups.map((group) => (
                <div key={group.label}>
                  <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-sidebar-foreground/40">
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
                          onClick={() => setMobileOpen(false)}
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

            {/* Logout pinned at bottom */}
            <div className="px-3 pb-5 pt-2 border-t border-sidebar-border shrink-0">
              <button
                onClick={handleLogout}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium w-full text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-destructive transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Logout
              </button>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
