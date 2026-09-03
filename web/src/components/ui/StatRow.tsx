/**
 * A compact KPI tile.
 *
 * Follows the referenced StatRow contract: a title, a value, an optional unit
 * suffix, and an optional trend with its own label. Built on Spark's tokens
 * and icon set rather than pulled in as a dependency, so it themes with
 * everything else and adds nothing to the bundle.
 *
 * A note on the trend, because it is the part most easily misused. `trend` is
 * only meaningful when two measurements are actually being compared. Spark's
 * headline metrics come from a single held-out evaluation, so there is no
 * earlier figure to compare them against and no arrow is shown. An arrow that
 * is not backed by a second measurement is a decoration that reads as a fact,
 * which is worse than no arrow at all. The prop exists for the places that do
 * have a comparison; it is simply left off where nothing was measured.
 */

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icons";

export type Trend = "up" | "down" | "neutral";

export interface StatRowProps {
  /** Label for the KPI. */
  title: ReactNode;
  /** The primary value. */
  value: ReactNode;
  /** Optional unit suffix, for example "%" or "ms". */
  unit?: string;
  /** Direction of the trend. Omit when nothing was compared. */
  trend?: Trend;
  /** Text shown next to the trend icon, for example "+12.4%". */
  trendLabel?: string;
  /** A quieter line under the value, for the split a number came from. */
  source?: ReactNode;
  className?: string;
}

const TREND = {
  up: { icon: Icon.TrendUp, tone: "text-low" },
  down: { icon: Icon.TrendDown, tone: "text-high" },
  neutral: { icon: Icon.TrendFlat, tone: "text-text-muted" },
} as const;

export function StatRow({
  title,
  value,
  unit,
  trend,
  trendLabel,
  source,
  className,
}: StatRowProps) {
  const mark = trend ? TREND[trend] : null;

  return (
    <div className={cn("min-w-[9rem] px-5 py-4", className)}>
      <p className="text-[12px] text-text-muted">{title}</p>

      <p className="mt-1.5 flex items-baseline gap-1">
        <span className="font-mono text-[20px] leading-none tracking-tight">
          {value}
        </span>
        {unit ? (
          <span className="text-[12px] leading-none text-text-muted">{unit}</span>
        ) : null}
      </p>

      {mark || source ? (
        <p className="mt-1.5 flex items-center gap-1.5 text-[11px] leading-none">
          {mark ? (
            <span className={cn("inline-flex items-center gap-1", mark.tone)}>
              <mark.icon size={13} />
              {trendLabel ? <span>{trendLabel}</span> : null}
            </span>
          ) : null}
          {source ? <span className="text-text-faint">{source}</span> : null}
        </p>
      ) : null}
    </div>
  );
}
