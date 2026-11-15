import { Link, useLocation } from "react-router-dom";
import { cn } from "@/utils/cn.js";

export default function AppShell({ title, back, actions, banner, children }) {
  const location = useLocation();
  const onSettings = location.pathname.startsWith("/settings");

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-20 border-b bg-card/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
            {back}
            <Link to="/" className="shrink-0 text-sm font-semibold tracking-wide">
              StarFerret
            </Link>
            {title && (
              <span className="truncate text-xs text-muted-foreground sm:text-sm">{title}</span>
            )}
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5 sm:gap-2">
            {actions}
            <Link
              to="/settings"
              className={cn(
                "rounded-md px-2.5 py-1.5 text-xs sm:text-sm",
                onSettings
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              Settings
            </Link>
          </div>
        </div>
      </header>
      {banner}
      <main className="mx-auto w-full max-w-6xl flex-1 px-3 py-4 sm:px-4 sm:py-6">{children}</main>
    </div>
  );
}
