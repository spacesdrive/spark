/**
 * A stepper for multi-stage work.
 *
 * A step is only marked done when the work behind it finished. Nothing here
 * advances because a page was opened.
 */

import { Icon } from "@/components/ui/icons";
import { cn } from "@/lib/utils";

export interface Step {
  id: string;
  label: string;
  hint?: string;
}

export type StepState = "pending" | "active" | "done" | "failed";

export function Stepper({
  steps,
  states,
  onSelect,
}: {
  steps: Step[];
  states: Record<string, StepState>;
  onSelect?: (id: string) => void;
}) {
  return (
    <ol className="flex flex-col gap-1 sm:flex-row sm:items-stretch sm:gap-0">
      {steps.map((step, i) => {
        const state = states[step.id] ?? "pending";
        const clickable = onSelect && (state === "done" || state === "active");
        const Tag = clickable ? "button" : "div";
        return (
          <li key={step.id} className="flex min-w-0 flex-1 items-center">
            <Tag
              {...(clickable
                ? { type: "button" as const, onClick: () => onSelect(step.id) }
                : {})}
              aria-current={state === "active" ? "step" : undefined}
              className={cn(
                "flex min-w-0 flex-1 items-center gap-2.5 rounded-[8px] px-3 py-2.5 text-left",
                clickable && "interactive",
                state === "active" && "bg-accent-soft"
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full border text-[11.5px] font-semibold",
                  state === "done" && "border-low bg-low text-white",
                  state === "active" && "border-accent bg-accent text-accent-text",
                  state === "failed" && "border-high bg-high text-white",
                  state === "pending" && "border-border text-text-faint"
                )}
              >
                {state === "done" ? (
                  <Icon.Check size={12} />
                ) : state === "failed" ? (
                  <Icon.Close size={12} />
                ) : (
                  i + 1
                )}
              </span>
              <span className="min-w-0">
                <span
                  className={cn(
                    "block truncate text-[13px]",
                    state === "active" ? "font-semibold text-accent" : "font-medium"
                  )}
                >
                  {step.label}
                </span>
                {step.hint ? (
                  <span className="block truncate text-[11.5px] text-text-muted">
                    {step.hint}
                  </span>
                ) : null}
              </span>
            </Tag>
            {i < steps.length - 1 ? (
              <span
                aria-hidden="true"
                className={cn(
                  "mx-1 hidden h-px w-6 shrink-0 sm:block",
                  states[steps[i + 1].id] === "pending" ? "bg-border" : "bg-low"
                )}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
