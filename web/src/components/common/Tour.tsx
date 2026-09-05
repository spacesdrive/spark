/**
 * A short first-time tour.
 *
 * Eight steps, not thirty. Each one points at something on screen, says what
 * it is in one sentence, and can be skipped. It runs once and can be restarted
 * from Settings or the command menu.
 *
 * A step whose target is not on the page is dropped when the tour starts, so
 * the tour never shows a card pointing at nothing. That matters on a narrow
 * screen, where the sidebar sits off canvas and half the steps have no target
 * to speak about.
 *
 * The dimming is drawn by the highlight itself, as a very large shadow around
 * the cut-out, rather than by a sheet over the whole page. A sheet covers the
 * thing being pointed at as much as everything else, which is the one place it
 * must not.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useApp } from "@/stores/app";
import { Button } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/icons";

interface TourStep {
  target: string;
  title: string;
  body: string;
}

const STEPS: TourStep[] = [
  {
    target: "[data-tour='nav-overview']",
    title: "Everything lives here",
    body: "The sidebar takes you to each part of Spark. Press Ctrl and K at any "
      + "time to jump straight to a page.",
  },
  {
    target: "[data-tour='model-selector']",
    title: "This picks the model",
    body: "Choose which Spark model scores your transactions. Whatever is "
      + "selected here is what the server actually runs.",
  },
  {
    target: "[data-tour='flow']",
    title: "How a transaction moves through Spark",
    body: "Your data goes in, two models score it, the scores combine into one "
      + "risk number, and that number becomes a decision with an explanation.",
  },
  {
    target: "[data-tour='metrics']",
    title: "Real measured results",
    body: "Every number here came from actually running the model. Each one says "
      + "which slice of data it was measured on.",
  },
  {
    target: "[data-tour='nav-transaction']",
    title: "Try one transaction",
    body: "Type in a payment, or pick an example, and see the score, the decision "
      + "and the reasons behind it.",
  },
  {
    target: "[data-tour='nav-dataset']",
    title: "Try a whole file",
    body: "Upload a CSV of your own transactions. Spark checks it, scores every "
      + "row, and lets you download the results.",
  },
  {
    target: "[data-tour='nav-models']",
    title: "See what the models are",
    body: "What each model is made of, how the parts are blended, and what each "
      + "one scored.",
  },
  {
    target: "[data-tour='nav-training']",
    title: "Later, train your own",
    body: "With an account you can train a model on your own history. That part "
      + "is not built yet, and Spark says so rather than pretending.",
  },
];

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const CARD_WIDTH = 340;
const CARD_HEIGHT = 200;
const GAP = 12;

/**
 * The element a step points at, if it is really there to be pointed at.
 *
 * An element can be in the document and still be no use: the sidebar is
 * translated off canvas below the large breakpoint, and a collapsed element
 * measures zero. Both still have a bounding rectangle, so existence alone does
 * not decide it.
 */
function visibleTarget(selector: string): Element | null {
  const el = document.querySelector(selector);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return null;
  if (r.right <= 0 || r.left >= window.innerWidth) return null;
  return el;
}

export function Tour() {
  const { tourSeen, setTourSeen, ready } = useApp();
  const location = useLocation();
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const [active, setActive] = useState(false);
  const [steps, setSteps] = useState<TourStep[]>([]);

  const onOverview = location.pathname === "/";

  // Only offer the tour on the overview page, and only after the app has
  // loaded, so the targets exist. The delay lets the first paint settle;
  // measuring before it does gives the wrong rectangle.
  useEffect(() => {
    if (tourSeen || !ready || !onOverview) {
      setActive(false);
      return;
    }
    const t = window.setTimeout(() => {
      const usable = STEPS.filter((s) => visibleTarget(s.target));
      setSteps(usable);
      setIndex(0);
      setActive(usable.length > 0);
    }, 700);
    return () => window.clearTimeout(t);
  }, [tourSeen, ready, onOverview]);

  const step = steps[index];

  const measure = useCallback(() => {
    if (!step) return;
    const el = document.querySelector(step.target);
    if (!el) {
      setBox(null);
      return;
    }
    const r = el.getBoundingClientRect();
    setBox({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, [step]);

  // Bring the target into view before measuring it. Without this a step for
  // something below the fold drew its ring off screen, which reads as the tour
  // highlighting nothing at all.
  useEffect(() => {
    if (!active || !step) return;
    const el = document.querySelector(step.target);
    if (!el) return;
    const r = el.getBoundingClientRect();
    if (r.top < GAP || r.bottom > window.innerHeight - GAP) {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [active, step]);

  useLayoutEffect(() => {
    if (!active) return;
    measure();
    // The scroll above is animated, so one measurement is not enough to land
    // the ring in the right place.
    const timer = window.setInterval(measure, 100);
    const stop = window.setTimeout(() => window.clearInterval(timer), 800);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(stop);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [active, measure]);

  const finish = useCallback(() => {
    setActive(false);
    setTourSeen(true);
    setIndex(0);
  }, [setTourSeen]);

  useEffect(() => {
    if (!active) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") finish();
      if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, steps.length - 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, finish, steps.length]);

  // Keep the card beside the highlight, and inside the window.
  const { cardTop, cardLeft } = useMemo(() => {
    if (!box) {
      return {
        cardTop: window.innerHeight / 2 - CARD_HEIGHT / 2,
        cardLeft: window.innerWidth / 2 - CARD_WIDTH / 2,
      };
    }
    const below = box.top + box.height + GAP;
    const fitsBelow = below + CARD_HEIGHT < window.innerHeight;
    return {
      cardTop: fitsBelow ? below : Math.max(GAP, box.top - CARD_HEIGHT - GAP),
      cardLeft: Math.min(
        Math.max(GAP, box.left),
        Math.max(GAP, window.innerWidth - CARD_WIDTH - GAP)
      ),
    };
  }, [box]);

  if (!active || !step) return null;

  const last = index === steps.length - 1;

  return (
    <div className="fixed inset-0 z-[70]" role="dialog" aria-modal="true" aria-label="Product tour">
      {/*
        Clicking away leaves the tour. This layer only dims when there is no
        highlight to dim around; otherwise the shadow below does it, so the
        thing being pointed at is the one thing left at full brightness.
      */}
      <div
        className={box ? "absolute inset-0" : "absolute inset-0 bg-black/45"}
        onClick={finish}
      />

      {box ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute rounded-[10px] ring-2 ring-accent"
          style={{
            top: box.top - 5,
            left: box.left - 5,
            width: box.width + 10,
            height: box.height + 10,
            // The cut-out: everything outside this rectangle is darkened and
            // the target itself is left alone.
            boxShadow: "0 0 0 9999px rgba(0, 0, 0, 0.55)",
            transition: "all 300ms var(--ease-out-soft)",
          }}
        />
      ) : null}

      <div
        className="enter absolute w-[340px] rounded-[--radius] border border-border
          bg-surface p-4 shadow-[--shadow-md]"
        style={{ top: cardTop, left: cardLeft, transition: "all 300ms var(--ease-out-soft)" }}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="text-[14px] font-semibold">{step.title}</p>
          <button
            type="button"
            onClick={finish}
            aria-label="Skip the tour"
            className="interactive -m-1 rounded p-1 text-text-faint"
          >
            <Icon.Close size={15} />
          </button>
        </div>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-text-muted">
          {step.body}
        </p>

        <div className="mt-4 flex items-center justify-between gap-3">
          <span className="flex gap-1" aria-hidden="true">
            {steps.map((_, i) => (
              <span
                key={i}
                className={
                  i === index
                    ? "h-1 w-4 rounded-full bg-accent"
                    : "h-1 w-1 rounded-full bg-border-strong"
                }
              />
            ))}
          </span>
          <span className="flex gap-1.5">
            <Button size="sm" variant="ghost" onClick={finish}>
              Skip
            </Button>
            {index > 0 ? (
              <Button size="sm" onClick={() => setIndex((i) => i - 1)}>
                Back
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="primary"
              onClick={() => (last ? finish() : setIndex((i) => i + 1))}
            >
              {last ? "Done" : "Next"}
            </Button>
          </span>
        </div>

        <p className="mt-2.5 text-[11px] text-text-faint">
          Step {index + 1} of {steps.length}. You can restart this from Settings.
        </p>
      </div>
    </div>
  );
}
