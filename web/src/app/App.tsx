/**
 * The application root: global state, the skip link, the shell and the routes.
 */

import { AppProvider } from "@/stores/app";
import { AppShell } from "@/layouts/AppShell";
import { AppRoutes } from "@/app/routes";

export function App() {
  return (
    <AppProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3
          focus:z-[80] focus:rounded-[8px] focus:border focus:border-border
          focus:bg-surface focus:px-3 focus:py-2 focus:text-[13px]"
      >
        Skip to the main content
      </a>
      <AppShell>
        <AppRoutes />
      </AppShell>
    </AppProvider>
  );
}
