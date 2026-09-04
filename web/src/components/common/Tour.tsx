/**
 * A short first-time tour.
 *
 * Eight steps, not thirty. Each one points at something on screen, says what
 * it is in one sentence, and can be skipped. It runs once and can be restarted
 * from Settings or the command menu.
 *
 * A step whose target is not on the page is skipped rather than pointing at
 * nothing.
 */

import { useCallback, useEffect, useLayoutEffect, useState } from "react";
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

export function Tour() {
  const { tourSeen, setTourSeen, ready } = useApp();
  const location = useLocation();
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const [active, setActive] = useState(false);

  // Only offer the tour on the overview page, and only after the app has
  // loaded, so the targets exist.
  useEffect(() => {
    if (!tourSeen && ready && location.pathname === "/") {
      const t = window.setTimeout(() => setActive(true), 700);
      return () => window.clearTimeout(t);
    }
    setActive(false);
  }, [tourSeen, ready, location.pathname]);

  const measure = useCallback(() => {
    const step = STEPS[index];
    if (!step) return;
    const el = document.querySelector(step.target);
    if (!el) {
      setBox(null);
      return;
    }
    const r = el.getBoundingClientRect();
    setBox({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, [index]);

  useLayoutEffect(() => {
    if (!active) return;
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
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
      if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, STEPS.length - 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, finish]);

  if (!active) return null;

  const step = STEPS[index];
  const last = index === STEPS.length - 1;

  // Place the card below the highlight when there is room, otherwise above.
  const cardTop = box
    ? box.top + box.height + 12 + 200 > window.innerHeight
      ? Math.max(12, box.top - 212)
      : box.top + box.height + 12
    : window.innerHeight / 2 - 100;
  const cardLeft = box
    ? Math.min(Math.max(12, box.left), window.innerWidth - 352)
    : window.innerWidth / 2 - 170;

  return (
    <div className="fixed inset-0 z-[70]" role="dialog" aria-modal="true" aria-label="Product tour">
      <div className="absolute inset-0 bg-black/45" onClick={finish} />

      {box ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute rounded-[10px] ring-2 ring-accent"
          style={{
            top: box.top - 5,
            left: box.left - 5,
            width: box.width + 10,
            height: box.height + 10,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.001)",
            background: "transparent",
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
            {STEPS.map((_, i) => (
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
          Step {index + 1} of {STEPS.length}. You can restart this from Settings.
        </p>
      </div>
    </div>
  );
}
