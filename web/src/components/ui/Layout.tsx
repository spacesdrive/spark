/**
 * Layout parts that replace the card grid.
 *
 * Four numbers used to mean four bordered boxes on every page. A number is not
 * a card: it is a label and a value, and putting a border round each one costs
 * a lot of vertical space to say nothing. MetricStrip lays them out in a single
 * divided row instead, which is what the reference dashboards do.
 *
 * FilterBar exists for the same reason on the other axis. Filters spread down
 * the page push the content they filter below the fold, so on a wide screen
 * they sit in one toolbar, and on a narrow one they collapse behind a button.
 */

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icons";
import { Button } from "@/components/ui/primitives";
import { HoverPreview } from "@/components/ui/HoverPreview";
import type { DocEntry } from "@/config/docs";

export interface MetricItem {
  label: string;
  value: ReactNode;
  /** A smaller line under the value, for the split or the share. */
  sub?: ReactNode;
  /** Attaches a hover definition and a documentation link to the label. */
  doc?: DocEntry;
  tone?: "default" | "low" | "medium" | "high";
}

const TONE: Record<string, string> = {
  default: "",
  low: "text-low",
  medium: "text-medium",
  high: "text-high",
};

/**
 * A row of numbers separated by rules rather than boxed individually.
 *
 * The `columns` count only sets the widest breakpoint. Below that it steps
 * down to two and then one, so a metric never gets squeezed to the point that
 * the value wraps mid-number.
 */
export function MetricStrip({
  items,
  columns = 4,
  className,
}: {
  items: MetricItem[];
  columns?: 3 | 4 | 5;
  className?: string;
}) {
  const wide = { 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5" }[
    columns
  ];
  return (
    <dl
      className={cn(
        "grid grid-cols-1 gap-px overflow-hidden rounded-[10px] border",
        "border-border bg-border sm:grid-cols-2",
        wide,
        className
      )}
    >
      {items.map((item) => (
        <div key={item.label} className="bg-surface px-4 py-3.5">
          <dt className="flex items-center gap-1 text-[12px] text-text-muted">
            {item.doc ? (
              <HoverPreview
                term={item.label}
                href={item.doc.href}
                trigger={
                  <span>{item.label}</span>
                }
              >
                {item.doc.text}
              </HoverPreview>
            ) : (
              item.label
            )}
          </dt>
          <dd
            className={cn(
              "mt-1 text-[20px] font-semibold leading-none tabular-nums",
              TONE[item.tone ?? "default"]
            )}
          >
            {item.value}
          </dd>
          {item.sub ? (
            <dd className="mt-1.5 text-[11.5px] leading-snug text-text-faint">
              {item.sub}
            </dd>
          ) : null}
        </div>
      ))}
    </dl>
  );
}

/**
 * Filters in one toolbar, or behind a button when there is no room for one.
 *
 * The mobile branch is a real disclosure rather than a media-query hide: the
 * controls stay in the DOM and keep their state, so opening the panel does not
 * reset what was already chosen.
 */
export function FilterBar({
  children,
  action,
  count,
}: {
  children: ReactNode;
  /** The apply or reset control, pinned to the end of the toolbar. */
  action?: ReactNode;
  /** How many filters are currently narrowing the view. */
  count?: number;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-[10px] border border-border bg-surface">
      <div className="flex items-center justify-between gap-3 px-3 py-2 md:hidden">
        <Button
          size="sm"
          onClick={() => setOpen((v) => !v)}
          icon={<Icon.Filter size={14} />}
          aria-expanded={open}
        >
          Filters{count ? ` (${count})` : ""}
        </Button>
        {action}
      </div>

      <div
        className={cn(
          "flex-col gap-3 p-3 md:flex md:flex-row md:flex-wrap md:items-end",
          open ? "flex border-t border-border md:border-t-0" : "hidden"
        )}
      >
        {children}
        {action ? <div className="hidden md:ml-auto md:block">{action}</div> : null}
      </div>
    </div>
  );
}

/**
 * Label and value pairs, aligned in a column.
 *
 * Used for the supporting detail under a metric strip, where a table would be
 * heavier than the content deserves.
 */
export function DefinitionList({
  items,
  columns = 2,
}: {
  items: { label: ReactNode; value: ReactNode }[];
  columns?: 1 | 2 | 3;
}) {
  const cols = { 1: "", 2: "sm:grid-cols-2", 3: "sm:grid-cols-3" }[columns];
  return (
    <dl className={cn("grid gap-x-8 gap-y-2 text-[12.5px]", cols)}>
      {items.map((item, i) => (
        <div
          key={i}
          className="flex items-baseline justify-between gap-4 border-b
            border-border/60 pb-2"
        >
          <dt className="text-text-muted">{item.label}</dt>
          <dd className="shrink-0 tabular-nums">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
