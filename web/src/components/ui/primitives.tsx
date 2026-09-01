/**
 * The small building blocks: buttons, cards, fields, badges, states.
 *
 * Two accessibility rules run through all of them:
 *
 * Risk is never carried by colour alone. A high-risk badge says HIGH RISK in
 * words, and the colour is a second signal for people who read it.
 *
 * Every control is reachable and visible from the keyboard. Nothing here
 * removes an outline without replacing it.
 */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Icon } from "./icons";
import type { RiskBand, Decision } from "@/types";

// buttons

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-text border-transparent hover:bg-accent-hover "
    + "shadow-sm",
  secondary: "bg-surface text-text border-border hover:bg-surface-hover",
  ghost: "bg-transparent text-text-muted border-transparent hover:bg-surface-hover hover:text-text",
  danger: "bg-transparent text-high border-high/30 hover:bg-high-soft",
};

/**
 * Three heights and no others: 32, 36, 40.
 *
 * Every control that sits on a row with another control has to be the same
 * height or the row looks broken. The dashboard previously ran 32, 33, 38 and
 * 44 across different pages, which is what made action groups look ragged.
 * A fractional Tailwind height is what starts that, so there are none here.
 */
const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-9 px-4 text-[13.5px] gap-2",
  lg: "h-10 px-5 text-[14px] gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "interactive inline-flex items-center justify-center rounded-[8px] "
          + "border font-medium select-none whitespace-nowrap "
          + "disabled:opacity-50 disabled:pointer-events-none",
        VARIANTS[variant],
        SIZES[size],
        className
      )}
      {...props}
    >
      {loading ? <Icon.Spinner size={size === "sm" ? 14 : 16} /> : icon}
      {children}
    </button>
  );
}

// layout

export function Card({
  className,
  children,
  interactive = false,
  ...props
}: { interactive?: boolean } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("card", interactive && "card-lift", className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 border-b border-border px-5 py-4",
        className
      )}
    >
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold">{title}</h2>
        {description ? (
          <p className="mt-1 text-[13px] leading-relaxed text-text-muted">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

/**
 * The top of every page: where am I, what is this, what do I do here.
 *
 * The primary action sits on the title line rather than below the
 * description, so it lands in the same place on every page and does not move
 * when the description is long.
 */
export function PageHeader({
  title,
  description,
  action,
  breadcrumb,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  /** Trail above the title. The last entry is the current page. */
  breadcrumb?: { label: string; to?: string }[];
}) {
  return (
    <header className="enter mb-6">
      {breadcrumb?.length ? <Breadcrumb items={breadcrumb} /> : null}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 max-w-2xl">
          <h1 className="text-[24px] font-bold leading-tight tracking-[-0.02em]">
            {title}
          </h1>
          {description ? (
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-text-muted">
              {description}
            </p>
          ) : null}
        </div>
        {action ? (
          <div className="flex shrink-0 items-center gap-2">{action}</div>
        ) : null}
      </div>
    </header>
  );
}

/** Where you are. Rendered above the page title. */
export function Breadcrumb({
  items,
}: {
  items: { label: string; to?: string }[];
}) {
  return (
    <nav aria-label="Breadcrumb" className="mb-2">
      <ol className="flex flex-wrap items-center gap-1 text-[12px] text-text-faint">
        {items.map((item, i) => (
          <li key={item.label} className="flex items-center gap-1">
            {item.to && i < items.length - 1 ? (
              <Link to={item.to} className="hover:text-text-muted">
                {item.label}
              </Link>
            ) : (
              <span aria-current={i === items.length - 1 ? "page" : undefined}>
                {item.label}
              </span>
            )}
            {i < items.length - 1 ? <span aria-hidden="true">/</span> : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/**
 * A titled block that is not a card.
 *
 * Most groupings need a heading and some space, not a border and a shadow.
 * Reaching for Card every time is what turns a page into a wall of boxes, so
 * this is the default and Card is the exception for things that genuinely
 * need lifting off the page.
 */
export function Section({
  title,
  description,
  action,
  children,
  className,
}: {
  title?: string;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-3", className)}>
      {title || action ? (
        <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
            {title ? (
              <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
            ) : null}
            {description ? (
              <p className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                {description}
              </p>
            ) : null}
          </div>
          {action ? (
            <div className="flex shrink-0 items-center gap-2">{action}</div>
          ) : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/**
 * A row of buttons that stay aligned.
 *
 * Buttons are laid out here rather than with margins on each one, so a group
 * cannot drift out of line when a label gets longer. On a narrow screen the
 * group stacks and each button fills the width, which keeps the primary action
 * reachable instead of squeezed.
 */
export function ActionGroup({
  children,
  align = "start",
  className,
}: {
  children: ReactNode;
  align?: "start" | "end" | "between";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-2 sm:flex-row sm:items-center",
        align === "end" && "sm:justify-end",
        align === "between" && "sm:justify-between",
        "[&>*]:w-full sm:[&>*]:w-auto",
        className
      )}
    >
      {children}
    </div>
  );
}

// badges and risk

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "low" | "medium" | "high";
  className?: string;
}) {
  const tones = {
    neutral: "bg-bg-subtle text-text-muted border-border",
    accent: "bg-accent-soft text-accent border-accent/20",
    low: "bg-low-soft text-low border-low/25",
    medium: "bg-medium-soft text-medium border-medium/25",
    high: "bg-high-soft text-high border-high/25",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-px "
          + "text-[12px] font-medium leading-tight",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

const BAND_TONE: Record<RiskBand, "low" | "medium" | "high"> = {
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
};

const BAND_WORDS: Record<RiskBand, string> = {
  LOW: "LOW RISK",
  MEDIUM: "MEDIUM RISK",
  HIGH: "HIGH RISK",
};

/** Risk always states the level in words, so colour is never the only cue. */
export function RiskBadge({ band }: { band: RiskBand }) {
  return <Badge tone={BAND_TONE[band]}>{BAND_WORDS[band]}</Badge>;
}

const DECISION_TONE: Record<Decision, "low" | "medium" | "high"> = {
  APPROVE: "low",
  REVIEW: "medium",
  BLOCK: "high",
};

export function DecisionBadge({ decision }: { decision: Decision }) {
  return <Badge tone={DECISION_TONE[decision]}>{decision}</Badge>;
}

// form fields

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  optional?: boolean;
  error?: string | null;
  /**
   * A control that belongs to this input, placed beside it.
   *
   * It goes in a row with the input rather than beside the whole field, so it
   * lines up with the box and not with the bottom of the hint underneath.
   * Putting a button next to a Field by hand is what produced a Create button
   * sitting lower than the input it belonged to.
   */
  action?: ReactNode;
}

export function Field({
  label,
  hint,
  optional,
  error,
  action,
  className,
  id,
  ...props
}: FieldProps) {
  const generated = useId();
  const fieldId = id ?? generated;
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;

  return (
    <div className="min-w-0">
      <label
        htmlFor={fieldId}
        className="mb-1.5 flex items-baseline gap-2 text-[13px] font-medium"
      >
        {label}
        {optional ? (
          <span className="text-[11.5px] font-normal text-text-faint">
            optional
          </span>
        ) : null}
      </label>
      <div className={cn("flex items-center gap-3", !action && "contents")}>
        <input
          id={fieldId}
          aria-describedby={cn(hint && hintId, error && errorId) || undefined}
          aria-invalid={error ? true : undefined}
          className={cn(
            "interactive h-9 w-full min-w-0 rounded-[8px] border bg-surface px-3 "
              + "text-sm text-text placeholder:text-text-faint",
            error ? "border-high" : "border-border",
            className
          )}
          {...props}
        />
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {hint && !error ? (
        <p id={hintId} className="mt-1.5 text-[12px] leading-snug text-text-faint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="mt-1.5 text-[12px] text-high">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export interface SelectProps {
  label?: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string; description?: string }[];
  id?: string;
  className?: string;
}

/** A native select, styled. Keyboard and screen-reader behaviour comes free. */
export function Select({
  label,
  hint,
  value,
  onChange,
  options,
  id,
  className,
}: SelectProps) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <div className={cn("min-w-0", className)}>
      {label ? (
        <label htmlFor={fieldId} className="mb-1.5 block text-[13px] font-medium">
          {label}
        </label>
      ) : null}
      <div className="relative">
        <select
          id={fieldId}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="interactive h-9 w-full appearance-none rounded-[8px] border
            border-border bg-surface pl-3 pr-9 text-sm text-text"
        >
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <Icon.ChevronDown
          size={15}
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2
            text-text-faint"
        />
      </div>
      {hint ? (
        <p className="mt-1.5 text-[12px] leading-snug text-text-faint">{hint}</p>
      ) : null}
    </div>
  );
}

export function Textarea({
  label,
  hint,
  value,
  onChange,
  rows = 8,
  id,
  placeholder,
  className,
}: {
  label?: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  id?: string;
  placeholder?: string;
  className?: string;
}) {
  const generated = useId();
  const fieldId = id ?? generated;
  return (
    <div className="min-w-0">
      {label ? (
        <label htmlFor={fieldId} className="mb-1.5 block text-[13px] font-medium">
          {label}
        </label>
      ) : null}
      <textarea
        id={fieldId}
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className={cn(
          "interactive w-full rounded-[8px] border border-border bg-surface p-3 "
            + "font-mono text-[12.5px] leading-relaxed text-text "
            + "placeholder:text-text-faint",
          className
        )}
      />
      {hint ? (
        <p className="mt-1.5 text-[12px] leading-snug text-text-faint">{hint}</p>
      ) : null}
    </div>
  );
}

// state displays

export function Spinner({ label }: { label?: string }) {
  return (
    <div
      role="status"
      className="flex items-center gap-2.5 text-[13px] text-text-muted"
    >
      <Icon.Spinner size={16} />
      <span>{label ?? "Loading"}</span>
    </div>
  );
}

/** A wave of bars for waits long enough that a spinner feels stalled. */
export function WaveSpinner({ label }: { label?: string }) {
  return (
    <div role="status" className="flex flex-col items-center gap-3 py-8">
      <div className="flex h-6 items-end gap-1" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className="w-1 rounded-full bg-accent motion-safe:animate-[wave_1.1s_ease-in-out_infinite]"
            style={{ height: "100%", animationDelay: `${i * 110}ms` }}
          />
        ))}
      </div>
      {label ? (
        <span className="text-[13px] text-text-muted">{label}</span>
      ) : null}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      {icon ? <div className="text-text-faint">{icon}</div> : null}
      <div className="max-w-md">
        <p className="text-sm font-medium">{title}</p>
        {description ? (
          <p className="mt-1.5 text-[13px] leading-relaxed text-text-muted">
            {description}
          </p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  fix,
  onRetry,
}: {
  title?: string;
  message: string;
  fix?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-[--radius] border
        border-high/25 bg-high-soft px-5 py-4"
    >
      <div className="flex items-start gap-2.5">
        <Icon.Alert size={17} className="mt-0.5 shrink-0 text-high" />
        <div>
          <p className="text-sm font-medium text-text">{title}</p>
          <p className="mt-1 text-[13px] leading-relaxed text-text-muted">
            {message}
          </p>
          {fix ? (
            <p className="mt-1.5 text-[13px] leading-relaxed text-text-muted">
              <span className="font-medium text-text">How to fix it: </span>
              {fix}
            </p>
          ) : null}
        </div>
      </div>
      {onRetry ? (
        <Button size="sm" onClick={onRetry} icon={<Icon.Refresh size={14} />}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function Callout({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "warning" | "success";
  title?: string;
  children: ReactNode;
}) {
  const tones = {
    info: { box: "border-accent/20 bg-accent-soft", icon: "text-accent" },
    warning: { box: "border-medium/25 bg-medium-soft", icon: "text-medium" },
    success: { box: "border-low/25 bg-low-soft", icon: "text-low" },
  };
  const IconComponent =
    tone === "warning" ? Icon.Alert : tone === "success" ? Icon.CheckCircle : Icon.Info;
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-[--radius] border px-4 py-3",
        tones[tone].box
      )}
    >
      <IconComponent size={16} className={cn("mt-0.5 shrink-0", tones[tone].icon)} />
      <div className="min-w-0 text-[13px] leading-relaxed text-text-muted">
        {title ? (
          <p className="mb-0.5 font-medium text-text">{title}</p>
        ) : null}
        {children}
      </div>
    </div>
  );
}

/** A term with its plain-language meaning revealed on hover and on focus. */
export function Explained({
  term,
  meaning,
}: {
  term: ReactNode;
  meaning: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button
        type="button"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="cursor-help border-b border-dotted border-text-faint text-left"
        aria-describedby={open ? "explained-tip" : undefined}
      >
        {term}
      </button>
      {open ? (
        <span
          id="explained-tip"
          role="tooltip"
          className="enter absolute bottom-full left-0 z-40 mb-1.5 w-64 rounded-[8px]
            border border-border bg-surface px-3 py-2 text-[12.5px] font-normal
            leading-relaxed text-text-muted shadow-[--shadow-md]"
        >
          {meaning}
        </span>
      ) : null}
    </span>
  );
}

/**
 * Copy text, and say whether it worked.
 *
 * The failure branch matters more than the success one here. An API key is
 * shown exactly once, and navigator.clipboard is unavailable outside a secure
 * context, so a button that quietly does nothing would lose the key. This
 * falls back to a selection copy, and if even that fails it says so and tells
 * the user what to press instead.
 */
export function CopyButton({
  value,
  label = "Copy",
}: {
  value: string;
  label?: string;
}) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    let ok = false;
    try {
      await navigator.clipboard.writeText(value);
      ok = true;
    } catch {
      try {
        const area = document.createElement("textarea");
        area.value = value;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        ok = document.execCommand("copy");
        document.body.removeChild(area);
      } catch {
        ok = false;
      }
    }
    setState(ok ? "copied" : "failed");
    window.setTimeout(() => setState("idle"), 1800);
  }

  return (
    <Button
      size="sm"
      variant="ghost"
      aria-live="polite"
      icon={
        state === "copied" ? (
          <Icon.Check size={14} />
        ) : state === "failed" ? (
          <Icon.Info size={14} />
        ) : (
          <Icon.Copy size={14} />
        )
      }
      onClick={() => void copy()}
    >
      {state === "copied" ? "Copied" : state === "failed" ? "Press Ctrl and C" : label}
    </Button>
  );
}

/** A horizontal bar. `value` is 0 to 1. */
export function Meter({
  value,
  tone = "accent",
  label,
}: {
  value: number;
  tone?: "accent" | "low" | "medium" | "high";
  label?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const colours = {
    accent: "bg-accent",
    low: "bg-low",
    medium: "bg-medium",
    high: "bg-high",
  };
  return (
    <div
      role="meter"
      aria-valuenow={Number(pct.toFixed(1))}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className="h-1.5 w-full overflow-hidden rounded-full bg-bg-subtle"
    >
      <div
        className={cn("h-full rounded-full transition-[width]", colours[tone])}
        style={{ width: `${pct}%`, transitionDuration: "420ms" }}
      />
    </div>
  );
}

/** A determinate progress bar with a visible stage label. */
export function ProgressBar({
  value,
  stage,
  status,
}: {
  value: number;
  stage: string;
  status?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-3 text-[13px]">
        <span className="font-medium">{stage}</span>
        <span className="tabular-nums text-text-muted">{pct.toFixed(0)}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={Number(pct.toFixed(0))}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={stage}
        className="h-2 w-full overflow-hidden rounded-full bg-bg-subtle"
      >
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${pct}%`, transition: "width 380ms var(--ease-out-soft)" }}
        />
      </div>
      {status ? (
        <p className="mt-2 text-[12px] text-text-faint">{status}</p>
      ) : null}
    </div>
  );
}

/** A table that scrolls sideways on its own rather than pushing the page wide. */
export function ScrollTable({ children }: { children: ReactNode }) {
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-[13.5px]">
        {children}
      </table>
    </div>
  );
}

export function Th({
  children,
  align = "left",
  className,
}: {
  children?: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "h-10 border-b border-border px-3 text-[13.5px] font-medium",
        "text-text-muted",
        align === "right" ? "text-right" : "text-left",
        className
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  className,
}: {
  children?: ReactNode;
  align?: "left" | "right";
  className?: string;
}) {
  return (
    <td
      className={cn(
        "border-b border-border px-3 py-2 text-[13.5px]",
        align === "right" ? "text-right tabular-nums" : "text-left",
        className
      )}
    >
      {children}
    </td>
  );
}
