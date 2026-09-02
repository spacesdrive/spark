/**
 * Buttons whose interaction carries meaning, not decoration.
 *
 * Two of them, each chosen because the interaction does a job. Copying lives
 * in primitives.tsx, because one copy button is enough:
 *
 * - HoldButton makes a destructive action deliberate without a modal. You have
 *   to keep holding, and letting go early cancels.
 * - CooldownButton stops a retry being hammered against a rate limited
 *   endpoint, and shows how long is left rather than just refusing.
 *
 * Everything else uses the ordinary Button. A dashboard where every control is
 * a novelty is harder to use, not easier.
 *
 * Both honour prefers-reduced-motion and remain operable from the keyboard:
 * the hold button accepts a held Space or Enter.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Icon } from "@/components/ui/icons";

function reduceMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Hold to confirm something destructive.
 *
 * Preferred over a confirmation dialog for actions that are dangerous but
 * routine: it takes deliberate effort, but does not interrupt with a modal
 * that people learn to dismiss without reading.
 */
export function HoldButton({
  onConfirm,
  children,
  holdMs = 1200,
  className = "",
  disabled = false,
}: {
  onConfirm: () => void;
  children: ReactNode;
  holdMs?: number;
  className?: string;
  disabled?: boolean;
}) {
  const [progress, setProgress] = useState(0);
  const frame = useRef<number | undefined>(undefined);
  const started = useRef<number>(0);

  const stop = useCallback(() => {
    if (frame.current) cancelAnimationFrame(frame.current);
    frame.current = undefined;
    setProgress(0);
  }, []);

  useEffect(() => () => stop(), [stop]);

  const start = useCallback(() => {
    if (disabled || frame.current) return;

    // With reduced motion there is no bar to watch, so the hold would be a
    // mystery. Confirm immediately instead.
    if (reduceMotion()) {
      onConfirm();
      return;
    }

    started.current = performance.now();
    const step = () => {
      const done = Math.min(1, (performance.now() - started.current) / holdMs);
      setProgress(done);
      if (done >= 1) {
        stop();
        onConfirm();
        return;
      }
      frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
  }, [disabled, holdMs, onConfirm, stop]);

  return (
    <button
      type="button"
      disabled={disabled}
      onPointerDown={start}
      onPointerUp={stop}
      onPointerLeave={stop}
      onKeyDown={(e) => {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          start();
        }
      }}
      onKeyUp={stop}
      aria-describedby="hold-hint"
      className={`relative inline-flex h-8 items-center gap-1.5 overflow-hidden
        rounded-[8px] border border-high/40 px-3 text-[12.5px] font-medium
        text-high transition-colors hover:bg-high/10
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-high/50
        disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 bg-high/20"
        style={{ width: `${progress * 100}%` }}
      />
      <span className="relative inline-flex items-center gap-1.5">
        {children}
        <span className="text-[11px] font-normal opacity-70">
          {progress > 0 ? "keep holding" : "hold"}
        </span>
      </span>
    </button>
  );
}

/**
 * A button that refuses to be pressed again for a while.
 *
 * Used for retrying something rate limited, where the useful thing is to show
 * how long is left rather than to let the user generate more refusals.
 */
export function CooldownButton({
  onClick,
  children,
  cooldownSeconds = 5,
  className = "",
  disabled = false,
}: {
  onClick: () => void;
  children: ReactNode;
  cooldownSeconds?: number;
  className?: string;
  disabled?: boolean;
}) {
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    if (remaining <= 0) return;
    const id = window.setTimeout(() => setRemaining((r) => r - 1), 1000);
    return () => window.clearTimeout(id);
  }, [remaining]);

  const cooling = remaining > 0;

  return (
    <button
      type="button"
      disabled={disabled || cooling}
      onClick={() => {
        onClick();
        setRemaining(cooldownSeconds);
      }}
      className={`inline-flex h-8 items-center gap-1.5 rounded-[8px] border
        border-border bg-bg-subtle px-3 text-[12.5px] font-medium
        transition-colors hover:bg-border/60 focus-visible:outline-none
        focus-visible:ring-2 focus-visible:ring-accent/60
        disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
    >
      <Icon.Refresh size={14} className={cooling ? "" : ""} />
      {cooling ? `Wait ${remaining}s` : children}
    </button>
  );
}
