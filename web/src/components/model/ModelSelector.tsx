/**
 * The model selector.
 *
 * Choosing a model here changes the `model_id` sent on every scoring call, so
 * the backend runs what is selected. If the list is empty it says so rather
 * than showing a name with nothing behind it.
 *
 * Custom models appear only when an organization is selected and the API
 * returned them, which it does only for members of that organization.
 */

import { useEffect, useRef, useState } from "react";
import { useApp } from "@/stores/app";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icons";
import { Badge } from "@/components/ui/primitives";
import { ratio, shortDate } from "@/lib/format";

export function ModelSelector() {
  const { models, activeModel, setActiveModel, theme } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!models.length) {
    return (
      <div
        className="flex h-9 items-center gap-2 rounded-[8px] border border-border
          bg-surface px-3 text-[13px] text-text-muted"
        data-tour="model-selector"
      >
        <Icon.Alert size={15} className="text-medium" />
        No model available
      </div>
    );
  }

  const mark =
    theme === "dark"
      ? "/brand/spark-banner-dark.png"
      : "/brand/spark-banner-light.png";

  return (
    <div className="relative" ref={ref} data-tour="model-selector">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="interactive flex h-9 max-w-[248px] items-center gap-2 rounded-[8px]
          border border-border bg-surface pl-2 pr-2.5 text-[13px]"
      >
        <img src={mark} alt="" className="h-3.5 w-auto opacity-90" />
        <span className="min-w-0 flex-1 truncate text-left font-medium">
          {activeModel?.name ?? "Choose a model"}
        </span>
        {activeModel?.kind === "custom" ? (
          <Badge tone="accent">custom</Badge>
        ) : null}
        <Icon.ChevronDown size={14} className="text-text-faint" />
      </button>

      {open ? (
        <div
          role="listbox"
          aria-label="Model"
          className="enter absolute right-0 z-50 mt-1.5 w-[340px] overflow-hidden
            rounded-[--radius] border border-border bg-surface shadow-[--shadow-md]"
        >
          <p className="border-b border-border px-3.5 py-2.5 text-[11.5px] text-text-muted">
            The model chosen here is the model the server runs.
          </p>
          <ul className="max-h-[380px] overflow-y-auto p-1.5">
            {models.map((m) => {
              const selected = m.id === activeModel?.id;
              const usable = m.supports_transaction;
              return (
                <li key={m.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    disabled={!usable}
                    onClick={() => {
                      setActiveModel(m.id);
                      setOpen(false);
                    }}
                    className={cn(
                      "interactive w-full rounded-[8px] px-2.5 py-2 text-left",
                      selected && "bg-accent-soft",
                      !usable && "opacity-55"
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <img src={mark} alt="" className="h-3 w-auto opacity-80" />
                      <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium">
                        {m.name}
                      </span>
                      {selected ? (
                        <Icon.Check size={14} className="text-accent" />
                      ) : null}
                    </span>
                    <span className="mt-1 block text-[12px] leading-snug text-text-muted">
                      {m.description}
                    </span>
                    <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <Badge tone="neutral">{m.version}</Badge>
                      {m.status !== "ready" ? (
                        <Badge tone="medium">{m.status}</Badge>
                      ) : null}
                      {typeof m.held_out_pr_auc === "number" ? (
                        <Badge tone="neutral">
                          held-out PR-AUC {ratio(m.held_out_pr_auc, 3)}
                        </Badge>
                      ) : null}
                      {m.trained_at ? (
                        <span className="text-[11px] text-text-faint">
                          trained {shortDate(m.trained_at)}
                        </span>
                      ) : null}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
