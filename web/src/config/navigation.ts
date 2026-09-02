/**
 * The one definition of the navigation tree.
 *
 * The sidebar, the command menu and the slash commands all read this, so a
 * page can never appear in one and be missing from another, and there is no
 * way to leave a dead link behind.
 *
 * `requiresAuth` is a display hint only. The backend enforces access on every
 * request; hiding a link is a convenience, never a control.
 */

import type { ComponentType } from "react";
import { Icon, type IconProps } from "@/components/ui/icons";

export interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<IconProps>;
  description: string;
  requiresAuth?: boolean;
  slash?: string;
  tourId?: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    label: "Test Spark",
    items: [
      {
        path: "/",
        label: "Overview",
        icon: Icon.Home,
        description: "What Spark does, and how well it does it",
        slash: "/overview",
        tourId: "nav-overview",
      },
      {
        path: "/transaction",
        label: "Test Transaction",
        icon: Icon.Transaction,
        description: "Score one transaction and see why",
        slash: "/test",
        tourId: "nav-transaction",
      },
      {
        path: "/dataset",
        label: "Test Dataset",
        icon: Icon.Dataset,
        description: "Upload a CSV and score every row",
        slash: "/dataset",
        tourId: "nav-dataset",
      },
    ],
  },
  {
    label: "Analysis",
    items: [
      {
        path: "/analysis",
        label: "Risk Analysis",
        icon: Icon.Chart,
        description: "Measured results, split by split",
        slash: "/evaluate",
      },
      {
        path: "/rings",
        label: "Abuse Rings",
        icon: Icon.Ring,
        description: "Groups of accounts working together",
        slash: "/rings",
      },
    ],
  },
  {
    label: "Models",
    items: [
      {
        path: "/models",
        label: "Models",
        icon: Icon.Model,
        description: "Which models exist and what they scored",
        slash: "/models",
        tourId: "nav-models",
      },
      {
        path: "/training",
        label: "Train My Model",
        icon: Icon.Train,
        description: "Train on your own data",
        requiresAuth: true,
        slash: "/train",
        tourId: "nav-training",
      },
    ],
  },
  {
    label: "Developers",
    items: [
      {
        // Not "/api": that path is the backend prefix and never reaches the
        // dashboard router, in development or behind the production proxy.
        path: "/developers",
        label: "API",
        icon: Icon.Code,
        description: "Endpoints, requests and responses",
        slash: "/api",
      },
      {
        path: "/sandbox",
        label: "Sandbox",
        icon: Icon.Terminal,
        description: "Send a real request with a test key",
        requiresAuth: true,
        slash: "/sandbox",
      },
      {
        path: "/keys",
        label: "API Keys",
        icon: Icon.Key,
        description: "Create, rotate and revoke keys",
        requiresAuth: true,
        slash: "/keys",
      },
      {
        path: "/usage",
        label: "Usage",
        icon: Icon.Gauge,
        description: "What your keys have been doing",
        requiresAuth: true,
        slash: "/usage",
      },
    ],
  },
  {
    label: "More",
    items: [
      {
        path: "/docs",
        label: "Documentation",
        icon: Icon.Book,
        description: "How to use Spark, in plain language",
        slash: "/docs",
      },
      {
        path: "/settings",
        label: "Settings",
        icon: Icon.Settings,
        description: "Theme, model, thresholds and the tour",
        slash: "/settings",
      },
    ],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAV.flatMap((g) => g.items);

export function findNavItem(path: string): NavItem | undefined {
  return ALL_NAV_ITEMS.find((i) => i.path === path);
}
