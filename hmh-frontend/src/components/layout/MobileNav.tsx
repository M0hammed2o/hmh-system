import { NavLink, useLocation } from "react-router-dom";
import { Smartphone, Bell, HardHat, MessageSquare, ShoppingCart } from "lucide-react";
import { cn } from "@/lib/utils";

const mobileNavItems = [
  { title: "Owner",     path: "/owner",           icon: Smartphone },
  { title: "Alerts",    path: "/alerts",           icon: Bell },
  { title: "Labour",    path: "/labour",           icon: HardHat },
  { title: "WhatsApp",  path: "/whatsapp-queue",   icon: MessageSquare },
  { title: "Procure",   path: "/procurement",      icon: ShoppingCart },
];

export function MobileNav() {
  const location = useLocation();

  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-sidebar border-t border-sidebar-border pb-safe">
      <div className="flex items-center justify-around">
        {mobileNavItems.map((item) => {
          const isActive = item.path === "/"
            ? location.pathname === "/"
            : location.pathname.startsWith(item.path);
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={cn(
                "flex flex-col items-center gap-0.5 px-3 py-3 text-xs font-medium transition-colors min-w-[60px]",
                isActive
                  ? "text-sidebar-primary"
                  : "text-sidebar-muted hover:text-sidebar-accent-foreground"
              )}
            >
              <item.icon className="w-5 h-5" />
              <span>{item.title}</span>
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
