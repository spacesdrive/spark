/**
 * Icons.
 *
 * One stroke-based set drawn in the Hugeicons style: 24 by 24, 1.5 stroke,
 * round caps, no fills. They are inlined rather than pulled from a package so
 * the bundle carries exactly the icons that are used and nothing else, and so
 * every icon in the app comes from one place instead of three libraries with
 * different weights.
 *
 * Animation is opt-in through `animate`, and only a handful of icons use it:
 * a spinner that spins, and a bell that leans when something arrives. Nothing
 * animates just because it can.
 */

import type { SVGProps } from "react";
import { cn } from "@/lib/utils";

export interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number;
  animate?: boolean;
}

function Svg({ size = 18, className, children, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={cn("shrink-0", className)}
      {...props}
    >
      {children}
    </svg>
  );
}

export const Icon = {
  Home: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" />
    </Svg>
  ),
  Transaction: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 8h14l-3-3" />
      <path d="M21 16H7l3 3" />
    </Svg>
  ),
  Dataset: (p: IconProps) => (
    <Svg {...p}>
      <ellipse cx="12" cy="6" rx="8" ry="3" />
      <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6" />
      <path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
    </Svg>
  ),
  Chart: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 3v16a2 2 0 0 0 2 2h16" />
      <path d="M7 15l3.5-4 3 3L20 7" />
    </Svg>
  ),
  Ring: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="5" r="2.2" />
      <circle cx="5" cy="17" r="2.2" />
      <circle cx="19" cy="17" r="2.2" />
      <path d="M10.6 6.8 6.4 15.2M13.4 6.8l4.2 8.4M7.2 17h9.6" />
    </Svg>
  ),
  Model: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 2 3 7v10l9 5 9-5V7z" />
      <path d="M3 7l9 5 9-5M12 12v10" />
    </Svg>
  ),
  Train: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
      <circle cx="12" cy="12" r="4" />
      <path d="m5.6 5.6 2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
    </Svg>
  ),
  Key: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="7.5" cy="12" r="3.5" />
      <path d="M11 12h10M18 12v3M15 12v2.5" />
    </Svg>
  ),
  Code: (p: IconProps) => (
    <Svg {...p}>
      <path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16" />
    </Svg>
  ),
  Terminal: (p: IconProps) => (
    <Svg {...p}>
      <rect x="2.5" y="4" width="19" height="16" rx="2" />
      <path d="m7 9 3 3-3 3M13 15h4" />
    </Svg>
  ),
  Gauge: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 18a8 8 0 1 1 16 0" />
      <path d="m12 14 3.5-3.5" />
      <circle cx="12" cy="14" r="1.2" />
    </Svg>
  ),
  Book: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H19v16H5.5A1.5 1.5 0 0 0 4 20.5z" />
      <path d="M4 17.5A1.5 1.5 0 0 1 5.5 16H19" />
    </Svg>
  ),
  Settings: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z" />
    </Svg>
  ),
  Search: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </Svg>
  ),
  TrendUp: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 17.5 9.5 11l4 4L21 7.5" />
      <path d="M15 7.5h6v6" />
    </Svg>
  ),
  TrendDown: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 6.5 9.5 13l4-4L21 16.5" />
      <path d="M15 16.5h6v-6" />
    </Svg>
  ),
  TrendFlat: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 12h14" />
      <path d="m17 8 4 4-4 4" />
    </Svg>
  ),
  Pin: (p: IconProps) => (
    <Svg {...p}>
      <path d="M9 4h6l-1 6 4 3v2h-6.5" />
      <path d="M12.5 15H6v-2l4-3-1-6" />
      <path d="M11.5 15 11 21" />
    </Svg>
  ),
  Filter: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 5h18l-7 8v6l-4 2v-8Z" />
    </Svg>
  ),
  Network: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="18" r="2.5" />
      <circle cx="19" cy="18" r="2.5" />
      <path d="M12 7.5v4m0 0-5 4m5-4 5 4" />
    </Svg>
  ),
  Upload: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 16V4M8 8l4-4 4 4" />
      <path d="M4 16v2a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-2" />
    </Svg>
  ),
  Download: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 4v12M8 12l4 4 4-4" />
      <path d="M4 16v2a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-2" />
    </Svg>
  ),
  File: (p: IconProps) => (
    <Svg {...p}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </Svg>
  ),
  Check: (p: IconProps) => (
    <Svg {...p}>
      <path d="m4 12.5 5 5L20 6.5" />
    </Svg>
  ),
  CheckCircle: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.2 2.6 2.6L16 9.4" />
    </Svg>
  ),
  Alert: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10.3 4.3 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0z" />
      <path d="M12 9.5v4M12 17h.01" />
    </Svg>
  ),
  Info: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 7.8h.01" />
    </Svg>
  ),
  Block: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="m5.6 5.6 12.8 12.8" />
    </Svg>
  ),
  Close: (p: IconProps) => (
    <Svg {...p}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Svg>
  ),
  ChevronDown: (p: IconProps) => (
    <Svg {...p}>
      <path d="m6 9 6 6 6-6" />
    </Svg>
  ),
  ChevronRight: (p: IconProps) => (
    <Svg {...p}>
      <path d="m9 6 6 6-6 6" />
    </Svg>
  ),
  ArrowRight: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 12h15M13 6l6 6-6 6" />
    </Svg>
  ),
  ArrowDown: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 4v15M6 13l6 6 6-6" />
    </Svg>
  ),
  Copy: (p: IconProps) => (
    <Svg {...p}>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1" />
    </Svg>
  ),
  Refresh: (p: IconProps) => (
    <Svg {...p}>
      <path d="M20 11a8 8 0 0 0-13.6-4.6L3 9" />
      <path d="M4 13a8 8 0 0 0 13.6 4.6L21 15" />
      <path d="M3 4v5h5M21 20v-5h-5" />
    </Svg>
  ),
  Google: ({ size = 18, className, ...props }: IconProps) => (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={cn("shrink-0", className)}
      {...props}
    >
      <path
        fill="#4285F4"
        d="M23 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.17a5.28 5.28 0 0 1-2.29 3.46v2.88h3.7C21.74 18.8 23 15.82 23 12.27z"
      />
      <path
        fill="#34A853"
        d="M12 23.5c3.1 0 5.7-1.03 7.6-2.79l-3.71-2.88c-1.03.69-2.35 1.1-3.89 1.1-2.99 0-5.52-2.02-6.43-4.74H1.74v2.97A11.5 11.5 0 0 0 12 23.5z"
      />
      <path
        fill="#FBBC05"
        d="M5.57 14.19a6.9 6.9 0 0 1 0-4.38V6.84H1.74a11.5 11.5 0 0 0 0 10.32z"
      />
      <path
        fill="#EA4335"
        d="M12 5.07c1.69 0 3.2.58 4.4 1.72l3.28-3.28C17.7 1.63 15.1.5 12 .5A11.5 11.5 0 0 0 1.74 6.84l3.83 2.97C6.48 7.09 9.01 5.07 12 5.07z"
      />
    </svg>
  ),
  Logout: (p: IconProps) => (
    <Svg {...p}>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
      <path d="M10 16l-4-4 4-4M6 12h10" />
    </Svg>
  ),
  Menu: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Svg>
  ),
  Sun: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Svg>
  ),
  Moon: (p: IconProps) => (
    <Svg {...p}>
      <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
    </Svg>
  ),
  Plus: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  ),
  Trash: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 7h16M10 4h4M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13" />
      <path d="M10 11v7M14 11v7" />
    </Svg>
  ),
  Building: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 21V5a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v16" />
      <path d="M15 10h3a2 2 0 0 1 2 2v9M2 21h20" />
      <path d="M8 7h3M8 11h3M8 15h3" />
    </Svg>
  ),
  Star: (p: IconProps) => (
    <Svg {...p}>
      <path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.9-5.2-2.8-5.2 2.8 1-5.9L3.5 9.7l5.9-.8z" />
    </Svg>
  ),
  Play: (p: IconProps) => (
    <Svg {...p}>
      <path d="M7 4.5v15l12-7.5z" />
    </Svg>
  ),
  Bell: ({ animate, className, ...p }: IconProps) => (
    <Svg
      {...p}
      className={cn(className, animate && "origin-top motion-safe:animate-[wave_1.2s_ease-in-out]")}
    >
      <path d="M18 9a6 6 0 1 0-12 0c0 5-2 6-2 6h16s-2-1-2-6" />
      <path d="M13.7 20a2 2 0 0 1-3.4 0" />
    </Svg>
  ),
  Spinner: ({ className, size = 18, ...p }: IconProps) => (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={cn(
        "shrink-0 motion-safe:animate-[spin_800ms_linear_infinite]",
        className
      )}
      {...p}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2.2"
        opacity="0.2"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  ),
};
