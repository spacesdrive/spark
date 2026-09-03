/**
 * A list you can pin things to the top of.
 *
 * Adapted from the supplied component. Three changes were needed to make it
 * Spark's rather than a demo.
 *
 * It used `bg-blue-100 dark:bg-blue-950/30` and `bg-blue-500` directly, which
 * ignores the theme entirely; those are Spark tokens now, so a pinned row
 * looks like every other selected surface.
 *
 * The pinned set is remembered. Pinning is a per-person preference with no
 * server behind it, so it lives in this browser under a key the caller names.
 * Nothing about it reaches the API, and it is wrapped because a browser with
 * site data blocked throws on the first read.
 *
 * Motion comes from framer-motion, already in the project, rather than the
 * `motion/react` package the source imported.
 */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  AnimatePresence,
  LayoutGroup,
  motion,
  useReducedMotion,
  type Variants,
} from "framer-motion";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icons";

export interface PinnedListItem {
  id: string;
  name: string;
  /** For example "Category, detail". */
  subtitle: string;
  icon: ReactNode;
  /** Where the row goes when it is clicked. Optional. */
  onOpen?: () => void;
}

const itemVariants: Variants = {
  hidden: { opacity: 0, scale: 0.98, y: -4 },
  visible: {
    opacity: 1,
    scale: 1,
    y: 0,
    transition: { type: "spring", stiffness: 380, damping: 26, mass: 0.7 },
  },
  exit: { opacity: 0, scale: 0.98, y: -4, transition: { duration: 0.16 } },
};

/** Remembers the pinned ids for one list, in this browser only. */
function usePinned(storageKey: string) {
  const [pinned, setPinned] = useState<Set<string>>(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      return new Set<string>(raw ? (JSON.parse(raw) as string[]) : []);
    } catch {
      // Private windows and blocked site data throw here rather than
      // returning null, so the list simply starts empty.
      return new Set<string>();
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify([...pinned]));
    } catch {
      // Nothing to do: the list still works, it just will not be remembered.
    }
  }, [pinned, storageKey]);

  const toggle = useCallback((id: string) => {
    setPinned((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  return { pinned, toggle };
}

function Row({
  item,
  pinned,
  onToggle,
  reduceMotion,
}: {
  item: PinnedListItem;
  pinned: boolean;
  onToggle: () => void;
  reduceMotion: boolean;
}) {
  return (
    <motion.div
      layoutId={item.id}
      layout={reduceMotion ? false : true}
      variants={itemVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
      className={cn(
        "flex items-center gap-3 rounded-[10px] border px-3 py-2.5",
        pinned
          ? "border-border-strong bg-accent-soft"
          : "border-border bg-surface"
      )}
    >
      <span
        className="flex size-9 shrink-0 items-center justify-center rounded-[8px]
          border border-border bg-bg text-text-muted"
      >
        {item.icon}
      </span>

      <button
        type="button"
        onClick={item.onOpen}
        disabled={!item.onOpen}
        className={cn(
          "min-w-0 flex-1 text-left",
          item.onOpen && "cursor-pointer"
        )}
      >
        <span className="block truncate text-[13.5px] font-medium leading-tight">
          {item.name}
        </span>
        <span className="mt-0.5 block truncate text-[12px] text-text-muted">
          {item.subtitle}
        </span>
      </button>

      <button
        type="button"
        onClick={onToggle}
        aria-pressed={pinned}
        aria-label={pinned ? `Unpin ${item.name}` : `Pin ${item.name}`}
        className={cn(
          "interactive flex size-7 shrink-0 items-center justify-center rounded-full",
          pinned
            ? "bg-accent text-accent-text"
            : "bg-bg-subtle text-text-muted hover:text-text"
        )}
      >
        <Icon.Pin
          size={14}
          className={cn("transition-transform", pinned && "-rotate-45")}
        />
      </button>
    </motion.div>
  );
}

export function PinnedList({
  items,
  storageKey,
  className,
}: {
  items: PinnedListItem[];
  /** Where this list remembers its pins. Unique per list. */
  storageKey: string;
  className?: string;
}) {
  const { pinned, toggle } = usePinned(storageKey);
  const reduceMotion = !!useReducedMotion();

  const up = items.filter((i) => pinned.has(i.id));
  const rest = items.filter((i) => !pinned.has(i.id));

  const group = (label: string, rows: PinnedListItem[], isPinned: boolean) =>
    rows.length ? (
      <div className="flex flex-col gap-1.5">
        <p className="px-1 pb-0.5 pt-1 text-[11px] font-semibold uppercase
          tracking-wider text-text-faint">
          {label}
        </p>
        <AnimatePresence mode="popLayout" initial={false}>
          {rows.map((item) => (
            <Row
              key={item.id}
              item={item}
              pinned={isPinned}
              onToggle={() => toggle(item.id)}
              reduceMotion={reduceMotion}
            />
          ))}
        </AnimatePresence>
      </div>
    ) : null;

  return (
    <LayoutGroup>
      <div className={cn("flex w-full flex-col gap-1.5", className)}>
        {group("Pinned", up, true)}
        {group(up.length ? "Everything else" : "All", rest, false)}
      </div>
    </LayoutGroup>
  );
}
