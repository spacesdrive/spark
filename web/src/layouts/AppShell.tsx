/**
 * The frame every page is rendered inside: sidebar, top bar, and the global
 * chrome that is available from anywhere.
 *
 * Nothing renders until the app has asked the server what it can do, because a
 * shell drawn from guessed capabilities would show controls that do not work.
 */

import { Suspense, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useApp } from "@/stores/app";
import { Toaster } from "@/components/ui/Toaster";
import { Sidebar } from "@/layouts/Sidebar";
import { Topbar } from "@/layouts/Topbar";
import { CommandMenu } from "@/components/common/CommandMenu";
import { Tour } from "@/components/common/Tour";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { Card, WaveSpinner } from "@/components/ui/primitives";

export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { ready } = useApp();
  const location = useLocation();

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <WaveSpinner label="Starting Spark" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Toaster />
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="lg:pl-64">
        <Topbar onMenu={() => setMenuOpen(true)} />
        <main
          id="main"
          className="mx-auto w-full max-w-[1400px] px-4 py-6 lg:px-6"
        >
          <ErrorBoundary resetKey={location.pathname}>
            <Suspense
              fallback={
                <Card className="p-6">
                  <WaveSpinner label="Loading" />
                </Card>
              }
            >
              {children}
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      <CommandMenu />
      <Tour />
    </div>
  );
}
