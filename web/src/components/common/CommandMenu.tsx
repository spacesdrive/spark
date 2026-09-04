/**
 * The command menu, opened with Ctrl+K or Cmd+K.
 *
 * It lists real destinations and real actions only. Every entry does
 * something; there is nothing here that opens a "coming soon" panel.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ALL_NAV_ITEMS } from "@/config/navigation";
import { useApp } from "@/stores/app";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icons";

interface Command {
  id: string;
  label: string;
  hint: string;
  group: string;
  icon: React.ReactNode;
  run: () => void;
  keywords?: string;
}

export function CommandMenu() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const navigate = useNavigate();
  const { toggleTheme, theme, signOut, user, setTourSeen } = useApp();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const commands = useMemo<Command[]>(() => {
    const nav: Command[] = ALL_NAV_ITEMS.map((item) => ({
      id: `go:${item.path}`,
      label: `Go to ${item.label}`,
      hint: item.description,
      group: "Navigate",
      icon: <item.icon size={15} />,
      run: () => navigate(item.path),
      keywords: `${item.label} ${item.slash ?? ""}`,
    }));

    const actions: Command[] = [
      {
        id: "theme",
        label: theme === "dark" ? "Switch to light theme" : "Switch to dark theme",
        hint: "Change how the dashboard looks",
        group: "Actions",
        icon: theme === "dark" ? <Icon.Sun size={15} /> : <Icon.Moon size={15} />,
        run: toggleTheme,
      },
      {
        id: "tour",
        label: "Restart the tour",
        hint: "Walk through the dashboard again",
        group: "Actions",
        icon: <Icon.Play size={15} />,
        run: () => {
          setTourSeen(false);
          navigate("/");
        },
      },
    ];

    if (user) {
      actions.push({
        id: "signout",
        label: "Sign out",
        hint: "End this session",
        group: "Actions",
        icon: <Icon.Logout size={15} />,
        run: () => void signOut(),
      });
    } else {
      actions.push({
        id: "signin",
        label: "Sign in",
        hint: "Needed to train and manage your own models",
        group: "Actions",
        icon: <Icon.Google size={15} />,
        run: () => navigate("/login"),
      });
    }
    return [...nav, ...actions];
  }, [navigate, theme, toggleTheme, signOut, user, setTourSeen]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase().replace(/^\//, "");
    if (!q) return commands;
    return commands.filter((c) =>
      `${c.label} ${c.hint} ${c.keywords ?? ""}`.toLowerCase().includes(q)
    );
  }, [commands, query]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery("");
        setCursor(0);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 10);
  }, [open]);

  useEffect(() => setCursor(0), [query]);

  if (!open) return null;

  function choose(index: number) {
    const command = results[index];
    if (!command) return;
    setOpen(false);
    command.run();
  }

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(cursor);
    }
  }

  let lastGroup = "";

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 px-4 pt-[12vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command menu"
        className="enter w-full max-w-lg overflow-hidden rounded-[--radius] border
          border-border bg-surface shadow-[--shadow-md]"
      >
        <div className="flex items-center gap-2.5 border-b border-border px-4">
          <Icon.Search size={16} className="text-text-faint" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="Search pages and actions, or type / for commands"
            aria-label="Search commands"
            className="h-12 w-full bg-transparent text-sm outline-none
              placeholder:text-text-faint"
          />
          <kbd className="rounded border border-border px-1.5 py-0.5 text-[10.5px] text-text-faint">
            esc
          </kbd>
        </div>

        <ul ref={listRef} className="max-h-[52vh] overflow-y-auto p-2">
          {results.length === 0 ? (
            <li className="px-3 py-8 text-center text-[13px] text-text-muted">
              Nothing matches that.
            </li>
          ) : (
            results.map((c, i) => {
              const showGroup = c.group !== lastGroup;
              lastGroup = c.group;
              return (
                <li key={c.id}>
                  {showGroup ? (
                    <p className="px-2.5 pb-1 pt-2.5 text-[10.5px] font-semibold uppercase tracking-wider text-text-faint">
                      {c.group}
                    </p>
                  ) : null}
                  <button
                    type="button"
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => choose(i)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-[8px] px-2.5 py-2 text-left",
                      i === cursor ? "bg-accent-soft text-accent" : "text-text"
                    )}
                  >
                    <span className={i === cursor ? "text-accent" : "text-text-faint"}>
                      {c.icon}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-medium">
                        {c.label}
                      </span>
                      <span className="block truncate text-[12px] text-text-muted">
                        {c.hint}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}
