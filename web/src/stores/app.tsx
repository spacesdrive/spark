/**
 * Shared app state: who is signed in, which organization, which model, and
 * what the server said about itself.
 *
 * The selected model is kept here and passed to every scoring call, so
 * changing it in the selector changes what the backend runs. There is no
 * decorative selection anywhere in this app.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";

import { api, ApiError } from "@/api/client";
import {
  clearSupabaseSession,
  initSupabase,
  takeAccessToken,
} from "@/api/supabase";
import type {
  CurrentUser,
  Health,
  ModelInfo,
  Organization,
  PublicConfig,
} from "@/types";

export interface Notification {
  id: string;
  tone: "info" | "success" | "warning" | "error";
  title: string;
  body?: string;
  at: number;
}

interface AppState {
  ready: boolean;
  config: PublicConfig | null;
  health: Health | null;
  user: CurrentUser["user"];
  organizations: Organization[];
  activeOrg: Organization | null;
  setActiveOrg: (id: string) => void;
  models: ModelInfo[];
  activeModel: ModelInfo | null;
  setActiveModel: (id: string) => void;
  mode: string;
  setMode: (mode: string) => void;
  theme: "light" | "dark";
  toggleTheme: () => void;
  refreshUser: () => Promise<void>;
  refreshModels: () => Promise<void>;
  signOut: () => Promise<void>;
  notifications: Notification[];
  notify: (n: Omit<Notification, "id" | "at">) => void;
  dismiss: (id: string) => void;
  tourSeen: boolean;
  setTourSeen: (seen: boolean) => void;
}

const AppContext = createContext<AppState | null>(null);

const STORAGE = {
  org: "spark.org",
  model: "spark.model",
  mode: "spark.mode",
  theme: "spark.theme",
  tour: "spark.tour",
};

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Private windows and blocked site data are fine. The app just forgets.
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [user, setUser] = useState<CurrentUser["user"]>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [activeOrgId, setActiveOrgId] = useState<string | null>(
    () => readStored(STORAGE.org)
  );
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [activeModelId, setActiveModelId] = useState<string | null>(
    () => readStored(STORAGE.model)
  );
  const [mode, setModeState] = useState<string>(
    () => readStored(STORAGE.mode) ?? "balanced"
  );
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const stored = readStored(STORAGE.theme);
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [tourSeen, setTourSeenState] = useState(
    () => readStored(STORAGE.tour) === "yes"
  );

  useEffect(() => {
    const root = document.documentElement;
    const first = !root.dataset.themeReady;

    // The colour transition is switched on only around the change itself, so
    // the rest of the app keeps its instant hover and focus feedback. It is
    // also skipped on the very first paint, where there is nothing to ease
    // from and the page would otherwise fade in from the wrong palette.
    if (!first) root.classList.add("theme-switching");
    root.classList.toggle("dark", theme === "dark");
    root.dataset.themeReady = "yes";

    if (first) return;
    const done = window.setTimeout(
      () => root.classList.remove("theme-switching"),
      260
    );
    return () => window.clearTimeout(done);
  }, [theme]);

  const notify = useCallback((n: Omit<Notification, "id" | "at">) => {
    const item: Notification = {
      ...n,
      id: `n_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      at: Date.now(),
    };
    setNotifications((prev) => [item, ...prev].slice(0, 6));

    // The same event, shown twice for two different reasons: a toast while you
    // are still looking at what you did, and a tray entry you can come back to.
    const raise =
      n.tone === "success" ? toast.success
      : n.tone === "error" ? toast.error
      : n.tone === "warning" ? toast.warning
      : toast.info;
    raise(n.title, n.body ? { description: n.body } : undefined);
  }, []);

  const dismiss = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const me = await api.auth.me();
      setUser(me.user);
      setOrganizations(me.organizations);
      if (me.organizations.length) {
        const stored = readStored(STORAGE.org);
        const found = me.organizations.find((o) => o.id === stored);
        setActiveOrgId((found ?? me.organizations[0]).id);
      } else {
        setActiveOrgId(null);
      }
    } catch {
      // A guest is a normal caller, not a failure.
      setUser(null);
      setOrganizations([]);
    }
  }, []);

  const refreshModels = useCallback(async () => {
    try {
      const list = await api.models.list(activeOrgId ?? undefined);
      setModels(list.models);
      const stored = readStored(STORAGE.model);
      const found = list.models.find((m) => m.id === stored);
      const orgActive = list.models.find((m) => m.is_active);
      const chosen = found ?? orgActive ?? list.models[0] ?? null;
      setActiveModelId(chosen?.id ?? null);
    } catch {
      setModels([]);
      setActiveModelId(null);
    }
  }, [activeOrgId]);

  // Boot: read the public config, start Supabase, finish any pending OAuth
  // redirect, then find out who the caller is.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      let cfg: PublicConfig | null = null;
      try {
        cfg = await api.config();
        if (!cancelled) setConfig(cfg);
      } catch {
        if (!cancelled) setConfig(null);
      }

      if (cfg?.supabase_url && cfg.supabase_anon_key) {
        initSupabase(cfg.supabase_url, cfg.supabase_anon_key);

        // Whether this page load is the return leg of a sign-in. Supabase
        // sends the result back either as ?code= (PKCE), as an #access_token
        // fragment (implicit), or as an error on either. Knowing this is what
        // lets a failed sign-in say so: without it, an exchange that fails
        // leaves the user on a signed-out page with no message at all, which
        // is indistinguishable from never having pressed the button.
        const query = new URLSearchParams(window.location.search);
        const fragment = new URLSearchParams(
          window.location.hash.replace(/^#/, "")
        );
        const returning =
          query.has("code") || fragment.has("access_token") ||
          query.has("error") || fragment.has("error");
        const providerError =
          query.get("error_description") ?? fragment.get("error_description") ??
          query.get("error") ?? fragment.get("error");

        try {
          const token = await takeAccessToken();
          if (token) {
            await api.auth.session(token);
            await clearSupabaseSession();
            // Strip the OAuth parameters so a refresh does not replay them.
            window.history.replaceState({}, "", window.location.pathname);
          } else if (returning && !cancelled) {
            // Came back from the provider but no session came out of it.
            window.history.replaceState({}, "", window.location.pathname);
            notify({
              tone: "error",
              title: "Sign-in did not complete",
              body:
                providerError ??
                "The sign-in provider sent you back, but no session could be "
                  + "read from the reply. This usually means this address is "
                  + "not on the provider's list of allowed redirect URLs.",
            });
          }
        } catch (err) {
          if (!cancelled) {
            window.history.replaceState({}, "", window.location.pathname);
            notify({
              tone: "error",
              title: "Sign-in did not complete",
              body:
                err instanceof ApiError
                  ? err.message
                  : err instanceof Error
                    ? err.message
                    : "The sign-in reply could not be exchanged for a session.",
            });
          }
        }
      }

      try {
        const h = await api.health();
        if (!cancelled) setHealth(h);
      } catch {
        if (!cancelled) setHealth(null);
      }

      await refreshUser();
      if (!cancelled) setReady(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [notify, refreshUser]);

  useEffect(() => {
    void refreshModels();
  }, [refreshModels]);

  const setActiveOrg = useCallback((id: string) => {
    setActiveOrgId(id);
    writeStored(STORAGE.org, id);
  }, []);

  const setActiveModel = useCallback((id: string) => {
    setActiveModelId(id);
    writeStored(STORAGE.model, id);
  }, []);

  const setMode = useCallback((next: string) => {
    setModeState(next);
    writeStored(STORAGE.mode, next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      writeStored(STORAGE.theme, next);
      return next;
    });
  }, []);

  const setTourSeen = useCallback((seen: boolean) => {
    setTourSeenState(seen);
    writeStored(STORAGE.tour, seen ? "yes" : "no");
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.auth.logout();
    } finally {
      await clearSupabaseSession();
      setUser(null);
      setOrganizations([]);
      setActiveOrgId(null);
      notify({ tone: "info", title: "Signed out" });
    }
  }, [notify]);

  const value = useMemo<AppState>(
    () => ({
      ready,
      config,
      health,
      user,
      organizations,
      activeOrg: organizations.find((o) => o.id === activeOrgId) ?? null,
      setActiveOrg,
      models,
      activeModel: models.find((m) => m.id === activeModelId) ?? null,
      setActiveModel,
      mode,
      setMode,
      theme,
      toggleTheme,
      refreshUser,
      refreshModels,
      signOut,
      notifications,
      notify,
      dismiss,
      tourSeen,
      setTourSeen,
    }),
    [
      ready, config, health, user, organizations, activeOrgId, setActiveOrg,
      models, activeModelId, setActiveModel, mode, setMode, theme, toggleTheme,
      refreshUser, refreshModels, signOut, notifications, notify, dismiss,
      tourSeen, setTourSeen,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside AppProvider");
  return ctx;
}
