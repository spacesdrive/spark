/**
 * Turning numbers into text a person can read.
 *
 * The rule throughout: a missing value renders as an em-free placeholder, not
 * as zero. Showing 0.00 for "we did not measure this" is the small lie that
 * makes a dashboard untrustworthy.
 */

export const NOT_MEASURED = "not measured";

export function ratio(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return NOT_MEASURED;
  }
  return value.toFixed(digits);
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return NOT_MEASURED;
  }
  return `${(value * 100).toFixed(digits)}%`;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return NOT_MEASURED;
  }
  return value.toLocaleString();
}

export function money(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return NOT_MEASURED;
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return NOT_MEASURED;
  }
  return value < 10 ? `${value.toFixed(2)} ms` : `${value.toFixed(1)} ms`;
}

export function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatMetric(
  value: number | null | undefined,
  format: "ratio" | "count" | "ms"
): string {
  if (format === "count") return count(value);
  if (format === "ms") return ms(value);
  return ratio(value);
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return NOT_MEASURED;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return NOT_MEASURED;
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
  return `${Math.floor(seconds / 86400)} days ago`;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return NOT_MEASURED;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return NOT_MEASURED;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return NOT_MEASURED;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  return `${mins}m ${Math.round(seconds % 60)}s`;
}

/** Friendly names for the four score channels. */
export const CHANNEL_LABELS: Record<string, string> = {
  tabular: "Tree model",
  graph: "Graph model",
  behavioral: "Behaviour score",
  velocity: "Velocity score",
};

/** What each channel actually looks at, in one sentence. */
export const CHANNEL_HELP: Record<string, string> = {
  tabular:
    "A gradient boosted tree over amounts, counts and history. It reads no "
    + "fraud labels.",
  graph:
    "A small network that mixes each transaction with the transactions it "
    + "shares a customer, merchant, location or channel with. It only ever "
    + "looks backwards in time.",
  behavioral:
    "How unusual this is for this account, compared with what the account "
    + "normally does. No fraud labels involved.",
  velocity:
    "How fast and how concentrated the recent activity is. No fraud labels "
    + "involved.",
};

/** How the four graph relations are described to a person. */
export const RELATION_LABELS: Record<string, string> = {
  Source: "Same customer account",
  Target: "Same merchant",
  Location: "Same location",
  Type: "Same payment channel",
};
