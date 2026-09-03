/**
 * A vertical stepper.
 *
 * Built to the same structure as the shadcn stepper: an item per step, a
 * separator drawn between them, a circular trigger, and a title with a
 * description beside it. The source pattern is Vue, so this is the React
 * equivalent rather than a port, and it uses Spark's own tokens and icon set
 * so it matches the rest of the dashboard.
 *
 * One deliberate difference. The reference marks each step completed, active
 * or inactive, which suits a form you are working through. The place this is
 * used describes a pipeline that runs the same way every time, so there is no
 * progress to report and claiming a step was "completed" would be inventing
 * state. Steps here carry their own icon instead, which says what the stage
 * does rather than pretending something has happened.
 */

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { IconProps } from "@/components/ui/icons";

export interface Step {
  /** The stage's own icon, drawn inside the circle. */
  icon: (props: IconProps) => ReactNode;
  title: string;
  description: string;
}

export function Stepper({
  steps,
  className,
}: {
  steps: Step[];
  className?: string;
}) {
  return (
    <ol className={cn("flex w-full flex-col", className)}>
      {steps.map((step, index) => {
        const last = index === steps.length - 1;
        return (
          <li
            key={step.title}
            className={cn(
              "relative flex w-full items-start gap-3.5",
              !last && "pb-5"
            )}
          >
            {/*
              The rail runs from just under this circle to the top of the next
              one. It is drawn from the item rather than between items so it
              cannot fall out of step with the row heights, and it is hidden on
              the last one so the line does not dangle past the end.
            */}
            {last ? null : (
              <span
                aria-hidden="true"
                className="absolute left-[15px] top-[30px] block w-0.5
                  -translate-x-1/2 rounded-full bg-border"
                style={{ height: "calc(100% - 30px)" }}
              />
            )}

            <span
              aria-hidden="true"
              className="relative z-10 flex size-[30px] shrink-0 items-center
                justify-center rounded-full border border-border bg-surface
                text-text-muted"
            >
              <step.icon size={15} />
            </span>

            <span className="min-w-0 pt-1">
              <span className="block text-[13px] font-medium leading-tight">
                {step.title}
              </span>
              <span className="mt-1 block text-[12px] leading-snug text-text-muted">
                {step.description}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
