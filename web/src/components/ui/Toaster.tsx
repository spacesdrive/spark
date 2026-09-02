/**
 * Transient toasts, on Sonner.
 *
 * The referenced docs are for vue-sonner in shadcn-vue; this is the React
 * package the Vue one is a port of, wired up the same way: one <Toaster /> at
 * the root, and `toast()` called from anywhere.
 *
 * This sits alongside the notification tray rather than replacing it. The two
 * answer different questions: a toast says "that worked" while you are looking
 * at the thing you just did, and the tray answers "what happened while I was
 * on another page". Something worth interrupting for goes to both, which is
 * why `notify()` in the store drives them together instead of callers having
 * to remember to fire two.
 *
 * Styling comes from Spark's own tokens rather than Sonner's defaults, so a
 * toast matches the surface, border and radius of every other panel and
 * follows the theme without a second definition.
 */

import { Toaster as Sonner, toast } from "sonner";
import { useApp } from "@/stores/app";

export { toast };

export function Toaster() {
  const { theme } = useApp();

  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      // Sonner's own close button is small and appears on hover; a toast that
      // dismisses itself does not need one, and the tray keeps the history.
      closeButton={false}
      duration={4500}
      visibleToasts={3}
      toastOptions={{
        classNames: {
          toast:
            "!bg-surface !border-border !text-text !rounded-[10px] !shadow-md "
            + "!font-sans !text-[13px]",
          title: "!text-[13px] !font-medium !text-text",
          description: "!text-[12.5px] !leading-snug !text-text-muted",
          actionButton: "!bg-accent !text-accent-text !rounded-[8px]",
          cancelButton: "!bg-bg-subtle !text-text-muted !rounded-[8px]",
          icon: "!size-4",
          success: "!text-low",
          error: "!text-high",
          warning: "!text-medium",
        },
      }}
    />
  );
}
