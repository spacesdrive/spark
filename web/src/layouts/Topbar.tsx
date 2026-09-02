/**
 * The top bar: where you are, which model runs, and what just happened.
 *
 * The notification tray only carries things worth interrupting for: a job
 * finishing, a validation failure, a model becoming active. Nothing posts a
 * notification for an ordinary click.
 */

import { useLocation, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { useApp } from "@/stores/app";
import { findNavItem } from "@/config/navigation";
import { ModelSelector } from "@/components/model/ModelSelector";
import { Icon } from "@/components/ui/icons";
import { Badge, Button } from "@/components/ui/primitives";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { theme, toggleTheme, user, health, activeOrg, organizations, setActiveOrg } =
    useApp();
  const item = findNavItem(location.pathname);

  return (
    <header
      className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border
        bg-bg/85 px-4 backdrop-blur-sm lg:px-6"
    >
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open the menu"
        className="interactive rounded-md p-2 text-text-muted lg:hidden"
      >
        <Icon.Menu size={18} />
      </button>

      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-semibold">
          {item?.label ?? "Spark"}
        </p>
      </div>

      {health && !health.model.available ? (
        <Badge tone="high">no model loaded</Badge>
      ) : null}

      {organizations.length > 1 ? (
        <select
          aria-label="Organization"
          value={activeOrg?.id ?? ""}
          onChange={(e) => setActiveOrg(e.target.value)}
          className="interactive hidden h-9 rounded-[8px] border border-border
            bg-surface px-2.5 text-[13px] md:block"
        >
          {organizations.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </select>
      ) : null}

      <div className="hidden sm:block">
        <ModelSelector />
      </div>

      <NotificationTray />

      <button
        type="button"
        onClick={toggleTheme}
        aria-label={theme === "dark" ? "Use the light theme" : "Use the dark theme"}
        className="interactive rounded-[8px] border border-border bg-surface p-2
          text-text-muted"
      >
        {theme === "dark" ? <Icon.Sun size={16} /> : <Icon.Moon size={16} />}
      </button>

      {user ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => navigate("/settings")}
          icon={<Icon.Settings size={15} />}
          aria-label="Settings"
        />
      ) : (
        <Button size="sm" variant="primary" onClick={() => navigate("/login")}>
          Sign in
        </Button>
      )}
    </header>
  );
}

function NotificationTray() {
  const { notifications, dismiss } = useApp();
  const [open, setOpen] = useState(false);
  const [ping, setPing] = useState(false);
  const seen = useRef(0);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (notifications.length > seen.current) {
      setPing(true);
      const t = window.setTimeout(() => setPing(false), 1400);
      return () => window.clearTimeout(t);
    }
    seen.current = notifications.length;
  }, [notifications.length]);

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

  // Each kind of activity gets its own icon as well as its own colour, so the
  // list is readable without relying on colour alone.
  const tones = {
    info: { className: "text-link", icon: Icon.Info },
    success: { className: "text-low", icon: Icon.CheckCircle },
    warning: { className: "text-medium", icon: Icon.Alert },
    error: { className: "text-high", icon: Icon.Block },
  } as const;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          seen.current = notifications.length;
        }}
        aria-label={
          notifications.length
            ? `Notifications, ${notifications.length} new`
            : "Notifications"
        }
        className="interactive relative rounded-[8px] border border-border bg-surface
          p-2 text-text-muted"
      >
        <Icon.Bell size={16} animate={ping} />
        {notifications.length ? (
          <span
            aria-hidden="true"
            className="absolute -right-0.5 -top-0.5 flex size-[15px] items-center
              justify-center rounded-full bg-accent text-[9.5px] font-semibold
              text-accent-text"
          >
            {notifications.length}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          className="enter absolute right-0 z-50 mt-1.5 w-[330px] overflow-hidden
            rounded-[--radius] border border-border bg-surface shadow-[--shadow-md]"
        >
          <div className="flex items-center justify-between gap-3 border-b
            border-border px-4 py-2.5">
            <p className="text-[12px] font-medium">Activity</p>
            {notifications.length ? (
              <button
                type="button"
                onClick={() => notifications.forEach((n) => dismiss(n.id))}
                className="interactive rounded-[6px] px-1.5 py-0.5 text-[11.5px]
                  text-text-muted hover:text-text"
              >
                Clear all
              </button>
            ) : null}
          </div>
          {notifications.length === 0 ? (
            <p className="px-4 py-8 text-center text-[13px] text-text-muted">
              Nothing yet. Uploads, scoring runs and model changes appear here.
            </p>
          ) : (
            <ul className="max-h-[60vh] overflow-y-auto">
              {notifications.map((n) => (
                <li
                  key={n.id}
                  className="flex items-start gap-2.5 border-b border-border px-4 py-3
                    last:border-b-0"
                >
                  {(() => {
                    const tone = tones[n.tone];
                    return (
                      <tone.icon
                        size={15}
                        className={cn("mt-0.5 shrink-0", tone.className)}
                      />
                    );
                  })()}
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium">{n.title}</p>
                    {n.body ? (
                      <p className="mt-0.5 text-[12.5px] leading-snug text-text-muted">
                        {n.body}
                      </p>
                    ) : null}
                    <p className="mt-1 text-[11px] text-text-faint">
                      {relativeTime(new Date(n.at).toISOString())}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => dismiss(n.id)}
                    aria-label="Dismiss"
                    className="interactive rounded p-1 text-text-faint"
                  >
                    <Icon.Close size={13} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
