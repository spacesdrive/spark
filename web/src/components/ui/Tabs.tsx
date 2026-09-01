/**
 * Tabs, a detail drawer, and skeletons.
 *
 * These exist so a page can hold a lot without showing a lot. A model has an
 * overview, an evaluation, its training run and its usage; putting all four on
 * screen at once is what made pages feel like reports. Tabs keep one visible
 * and the rest one click away, and the drawer does the same for a row in a
 * table.
 *
 * Both are built on plain elements with the right roles rather than pulled
 * from another library, so they match the rest of the dashboard exactly and
 * add nothing to the bundle.
 */

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icons";

export interface TabItem {
  id: string;
  label: string;
  /** Shown after the label, for a count or a status. */
  badge?: ReactNode;
  content: ReactNode;
}

/**
 * A tab strip with arrow-key navigation, as the pattern requires.
 */
export function Tabs({
  items,
  initial,
  className,
}: {
  items: TabItem[];
  initial?: string;
  className?: string;
}) {
  const [active, setActive] = useState(initial ?? items[0]?.id);
  const strip = useRef<HTMLDivElement>(null);
  // Scopes the shared indicator, so two tab strips on one page do not animate
  // into each other.
  const id = useId();
  const reduceMotion = useReducedMotion();

  const move = useCallback(
    (delta: number) => {
      const index = items.findIndex((t) => t.id === active);
      const next = items[(index + delta + items.length) % items.length];
      setActive(next.id);
      // Follow the selection with focus, which is what makes the arrow keys
      // useful rather than just changing what is on screen.
      const buttons = strip.current?.querySelectorAll("button");
      buttons?.[items.indexOf(next)]?.focus();
    },
    [active, items]
  );

  const current = items.find((t) => t.id === active) ?? items[0];

  return (
    <div className={className}>
      <div
        ref={strip}
        role="tablist"
        className="flex gap-1 overflow-x-auto border-b border-border"
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") {
            e.preventDefault();
            move(1);
          }
          if (e.key === "ArrowLeft") {
            e.preventDefault();
            move(-1);
          }
        }}
      >
        {items.map((tab) => {
          const selected = tab.id === current?.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(tab.id)}
              className={cn(
                "relative -mb-px flex h-9 shrink-0 items-center px-3 text-[13px]",
                "font-medium transition-colors focus-visible:outline-none",
                "focus-visible:ring-2 focus-visible:ring-accent/50",
                selected ? "text-text" : "text-text-muted hover:text-text"
              )}
            >
              <span className="inline-flex items-center gap-1.5">
                {tab.label}
                {tab.badge}
              </span>
              {/*
                One shared indicator that travels between tabs rather than a
                border switching on and off, so the eye follows the selection
                instead of finding it again. Spring-shaped, and it settles once.
              */}
              {selected ? (
                <motion.span
                  layoutId={`tab-indicator-${id}`}
                  aria-hidden="true"
                  className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-accent"
                  transition={
                    reduceMotion
                      ? { duration: 0 }
                      : { type: "spring", stiffness: 520, damping: 38, mass: 0.7 }
                  }
                />
              ) : null}
            </button>
          );
        })}
      </div>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={current?.id}
          role="tabpanel"
          className="pt-4"
          initial={reduceMotion ? false : { opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? { opacity: 1 } : { opacity: 0, y: -4 }}
          transition={{ duration: reduceMotion ? 0 : 0.16, ease: [0.16, 1, 0.3, 1] }}
        >
          {current?.content}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/**
 * A panel that slides in from the right for the detail behind a row.
 *
 * Used instead of navigating away, so the table keeps its scroll position and
 * the context you were reading stays behind the panel.
 */
export function Drawer({
  open,
  onClose,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    // Moving focus into the panel is what makes Escape and Tab behave.
    panel.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 bg-black/40"
        style={{ animation: "spark-fade-in 140ms ease-out" }}
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative flex h-full w-full max-w-[520px] flex-col border-l
          border-border bg-bg shadow-xl outline-none"
        style={{ animation: "spark-slide-in 180ms cubic-bezier(.2,.8,.2,1)" }}
      >
        <header className="flex items-start justify-between gap-4 border-b
          border-border px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
            {description ? (
              <p className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                {description}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="interactive -mr-1 -mt-1 shrink-0 rounded-[8px] p-1.5
              text-text-muted hover:bg-bg-subtle hover:text-text"
          >
            <Icon.Close size={16} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer ? (
          <footer className="border-t border-border px-5 py-3">{footer}</footer>
        ) : null}
      </div>
    </div>
  );
}
