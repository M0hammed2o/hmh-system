import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Users, FolderKanban, FileSpreadsheet,
  ShoppingCart, Truck, Package, CreditCard, Bell, Settings, LogOut, HardHat,
  Droplet, Building2,
} from "lucide-react";
import { TOKEN_KEY, REFRESH_TOKEN_KEY } from "@/lib/constants";
import { cn } from "@/lib/utils";

const navItems = [
  { title: "Dashboard",   path: "/",            icon: LayoutDashboard },
  { title: "Users",       path: "/users",        icon: Users },
  { title: "Projects",    path: "/projects",     icon: FolderKanban },
  { title: "BOQ",         path: "/boq",          icon: FileSpreadsheet },
  { title: "Procurement", path: "/procurement",  icon: ShoppingCart },
  { title: "Deliveries",  path: "/deliveries",   icon: Truck },
  { title: "Stock",       path: "/stock",        icon: Package },
  { title: "Payments",    path: "/payments",     icon: CreditCard },
  { title: "Fuel",        path: "/fuel",         icon: Droplet },
  { title: "Suppliers",   path: "/suppliers",    icon: Building2 },
  { title: "Alerts",      path: "/alerts",       icon: Bell },
  { title: "Settings",    path: "/settings",     icon: Settings },
];

export function AppSidebar() {
  const location = useLocation();

  const handleLogout = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    window.location.href = "/login";
  };

  return (
    <aside className="hidden lg:flex flex-col w-64 bg-sidebar border-r border-sidebar-border min-h-screen">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-6 py-5 border-b border-sidebar-border">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-sidebar-primary/20">
          <HardHat className="w-4 h-4 text-sidebar-primary" />
        </div>
        <span className="text-base font-semibold text-sidebar-accent-foreground tracking-tight">
          HMH Group
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {navItems.map((item) => {
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
      </nav>

      {/* Logout */}
      <div className="px-3 pb-5">
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
