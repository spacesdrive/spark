/**
 * The sidebar.
 *
 * Collapses to a slide-over on narrow screens. Nested groups are shown
 * expanded because there are only five of them and hiding a page behind a
 * click is not a saving.
 *
 * Links that need an account are shown to guests with a small lock, rather
 * than hidden. Knowing a feature exists is useful; the backend is what stops
 * anyone from using it.
 */

import { NavLink } from "react-router-dom";
import { NAV } from "@/config/navigation";
import { useApp } from "@/stores/app";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icons";
import { Badge } from "@/components/ui/primitives";

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { user, theme } = useApp();

  return (
    <>
      {open ? (
        <button
          type="button"
          aria-label="Close the menu"
          onClick={onClose}
          className="fixed inset-0 z-30 bg-black/30 lg:hidden"
        />
      ) : null}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r "
            + "border-border bg-surface transition-transform lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
        style={{ transitionDuration: "260ms", transitionTimingFunction: "var(--ease-out-soft)" }}
      >
        <div className="flex h-14 items-center justify-between gap-2 border-b border-border px-4">
          <NavLink to="/" className="flex min-w-0 items-center" onClick={onClose}>
            <img
              src={
                theme === "dark"
                  ? "/brand/spark-banner-dark.png"
                  : "/brand/spark-banner-light.png"
              }
              alt="Spark"
              width={104}
              className="h-auto w-[104px]"
            />
          </NavLink>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close the menu"
            className="interactive rounded-md p-1.5 text-text-muted lg:hidden"
          >
            <Icon.Close size={17} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Main">
          {NAV.map((group) => (
            <div key={group.label} className="mb-5 last:mb-0">
              <p className="mb-1.5 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint">
                {group.label}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const locked = item.requiresAuth && !user;
                  return (
                    <li key={item.path}>
                      <NavLink
                        to={item.path}
                        onClick={onClose}
                        data-tour={item.tourId}
                        className={({ isActive }) =>
                          cn(
                            "interactive flex h-8 items-center gap-2.5 rounded-[8px] "
                              + "px-2 text-[14px] font-medium",
                            isActive
                              ? "bg-accent-soft text-accent"
                              : "text-text-muted hover:text-text"
                          )
                        }
                      >
                        <item.icon size={16} />
                        <span className="min-w-0 flex-1 truncate">{item.label}</span>
                        {locked ? (
                          <span
                            className="text-[10px] text-text-faint"
                            title="An account is needed for this"
                          >
                            account
                          </span>
                        ) : null}
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-border p-3">
          {user ? (
            <div className="flex items-center gap-2.5 px-1.5 py-1">
              <Avatar user={user} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium">
                  {user.display_name || user.email}
                </p>
                <p className="truncate text-[11.5px] text-text-faint">
                  {user.email}
                </p>
              </div>
            </div>
          ) : (
            <NavLink
              to="/login"
              onClick={onClose}
              className="interactive flex items-center gap-2 rounded-[7px] border
                border-border px-3 py-2 text-[13px] font-medium"
            >
              <Icon.Google size={15} />
              Sign in
            </NavLink>
          )}
          <p className="mt-2 px-1.5 text-[11px] leading-snug text-text-faint">
            {user ? (
              "You can train and manage your own models."
            ) : (
              <>Testing needs no account. <Badge tone="neutral">guest</Badge></>
            )}
          </p>
        </div>
      </aside>
    </>
  );
}

function Avatar({
  user,
}: {
  user: NonNullable<ReturnType<typeof useApp>["user"]>;
}) {
  if (user.avatar_url) {
    return (
      <img
        src={user.avatar_url}
        alt=""
        width={30}
        height={30}
        className="size-[30px] shrink-0 rounded-full object-cover"
      />
    );
  }
  const initial = (user.display_name || user.email || "?")
    .trim()
    .charAt(0)
    .toUpperCase();
  return (
    <span
      aria-hidden="true"
      className="flex size-[30px] shrink-0 items-center justify-center rounded-full
        bg-accent-soft text-[13px] font-semibold text-accent"
    >
      {initial}
    </span>
  );
}
