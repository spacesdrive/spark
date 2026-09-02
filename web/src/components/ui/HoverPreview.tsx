/**
 * A small definition that appears on hover, and on focus, and on tap.
 *
 * This exists so the dashboard can show a number without the paragraph that
 * explains it. The explanation is one hover away rather than permanently
 * taking up space next to every metric.
 *
 * Four things make it usable rather than decorative:
 *
 * - it opens on focus as well as hover, so it is reachable from the keyboard;
 * - it opens on tap on touch devices, where hover does not exist at all;
 * - it closes on Escape, and never traps focus;
 * - the card renders in a portal, fixed to the viewport.
 *
 * That last point is not a detail. An absolutely positioned card is clipped by
 * any ancestor with a clipping overflow, and the places these previews are most
 * useful are exactly those ancestors: metric strips, scrolling tables, drawers.
 * The card was being cut in half by the metric strip that contained it. A
 * portal takes it out of that stacking context entirely, and the position is
 * then measured from the trigger and flipped up or nudged sideways so it always
 * lands on screen.
 *
 * The indicator icon belongs to this component and nothing else should add one.
 * Callers passing their own produced two icons side by side.
 */

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Icon } from "@/components/ui/icons";
import { TooltipCat } from "@/components/ui/TooltipCat";

export interface HoverPreviewProps {
  /** The short name of the thing being explained, for example "PR-AUC". */
  term: string;
  /** Two or three plain sentences. No formulas. */
  children: ReactNode;
  /** Where "Learn more" goes. Omit it and no link is shown. */
  href?: string;
  /** The element the preview attaches to. */
  trigger: ReactNode;
  className?: string;
}

const WIDTH = 268;
/**
 * Room for the card, its link, and the cat sitting on top of it.
 *
 * The cat is absolutely positioned so it adds no layout height, but it does
 * occupy space on screen, and the flip decision has to know about it or the
 * cat ends up off the top of the window.
 */
const HEIGHT = 190;
const CAT_CLEARANCE = 46;
const GAP = 8;
const EDGE = 12;

export function HoverPreview({
  term,
  children,
  href,
  trigger,
  className = "",
}: HoverPreviewProps) {
  const [open, setOpen] = useState(false);
  const [box, setBox] = useState<{ top: number; left: number } | null>(null);
  const wrapper = useRef<HTMLSpanElement>(null);
  const card = useRef<HTMLSpanElement>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const id = useId();

  /**
   * Work out where the card goes, in viewport coordinates.
   *
   * Below the trigger by default. Above it when there is no room below, and
   * pulled back from whichever edge it would otherwise cross, so a preview on
   * a right-aligned header button stays fully visible instead of running off
   * the side of the window.
   */
  const place = useCallback(() => {
    const anchor = wrapper.current?.getBoundingClientRect();
    if (!anchor) return;

    const below = window.innerHeight - anchor.bottom;
    const flip = below < HEIGHT && anchor.top > below + CAT_CLEARANCE;
    const height = card.current?.offsetHeight ?? HEIGHT;

    let left = anchor.left;
    const maxLeft = window.innerWidth - WIDTH - EDGE;
    if (left > maxLeft) left = maxLeft;
    if (left < EDGE) left = EDGE;

    setBox({
      top: flip
        ? anchor.top - height - GAP
        : anchor.bottom + GAP + CAT_CLEARANCE,
      left,
    });
  }, []);

  const show = useCallback(() => {
    window.clearTimeout(closeTimer.current);
    place();
    setOpen(true);
  }, [place]);

  // A small delay on close, so moving the pointer from the trigger into the
  // card does not dismiss it on the way.
  const hide = useCallback(() => {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => setOpen(false), 120);
  }, []);

  useEffect(() => () => window.clearTimeout(closeTimer.current), []);

  // Measure again once the card exists, because its real height decides
  // whether the flipped position is right.
  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (wrapper.current?.contains(target)) return;
      if (card.current?.contains(target)) return;
      setOpen(false);
    }
    // The card is fixed to the viewport, so anything that moves the trigger
    // has to move the card with it or leave it stranded.
    const reposition = () => place();
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [open, place]);

  return (
    <span
      ref={wrapper}
      className={`relative inline-flex ${className}`}
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onFocus={show}
        onBlur={hide}
        onClick={(e) => {
          e.preventDefault();
          // On a device with hover, focus has already opened this, so a plain
          // toggle would close it again and the click would look broken. Only
          // a device without hover needs the tap to toggle.
          const touch =
            typeof window !== "undefined" &&
            window.matchMedia("(hover: none)").matches;
          setOpen((v) => (touch ? !v : true));
        }}
        className="group inline-flex items-center gap-1 rounded-[6px] text-left
          outline-none focus-visible:ring-2 focus-visible:ring-accent/60"
      >
        {trigger}
        <Icon.Info
          size={12}
          className="shrink-0 text-text-faint transition-colors
            group-hover:text-text-muted"
        />
      </button>

      {open && box
        ? createPortal(
            <span
              ref={card}
              id={id}
              role="tooltip"
              onMouseEnter={show}
              onMouseLeave={hide}
              style={{
                position: "fixed",
                top: box.top,
                left: box.left,
                width: WIDTH,
                animation: "spark-preview-in 140ms cubic-bezier(.2,.8,.2,1)",
              }}
              className="cat-card z-[100] block rounded-[10px] border border-border
                bg-surface p-3.5 text-left shadow-lg"
            >
              {/*
                The cat sits on the top edge of the card rather than inside it,
                so it never pushes the text around or changes the card height.
              */}
              <TooltipCat className="absolute -top-[50px] right-3" />
              <span className="block text-[12.5px] font-semibold">{term}</span>
              <span className="mt-1 block text-[12px] leading-relaxed text-text-muted">
                {children}
              </span>
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2.5 inline-flex items-center gap-1 text-[12px]
                    font-medium text-link hover:underline"
                >
                  Learn more
                  <Icon.ArrowRight size={12} />
                </a>
              ) : null}
            </span>,
            document.body
          )
        : null}
    </span>
  );
}
