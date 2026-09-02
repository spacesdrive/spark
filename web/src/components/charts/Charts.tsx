/**
 * Charts.
 *
 * Every chart takes data straight from the API. None of them has a default
 * dataset, a placeholder series, or a synthetic axis: given nothing, they
 * render an empty state that says nothing was measured.
 *
 * Colours match the risk tokens, and every chart also labels its values, so a
 * reader who cannot separate the hues still gets the numbers.
 */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ReactNode } from "react";
import { RadarChart } from "@/components/charts/RadarChart";
import { EmptyState } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/icons";

const AXIS = {
  stroke: "var(--text-faint)",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const;

function ChartFrame({
  title,
  description,
  source,
  children,
  height = 240,
  empty,
}: {
  title: string;
  description?: string;
  source?: string;
  children: ReactNode;
  height?: number;
  empty?: boolean;
}) {
  return (
    <section className="card p-5">
      <div className="mb-4">
        <h3 className="text-[14px] font-semibold">{title}</h3>
        {description ? (
          <p className="mt-1 text-[12.5px] leading-relaxed text-text-muted">
            {description}
          </p>
        ) : null}
      </div>
      {empty ? (
        <EmptyState
          icon={<Icon.Chart size={26} />}
          title="Not measured"
          description="This chart needs numbers the backend has not produced."
        />
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            {children as React.ReactElement}
          </ResponsiveContainer>
        </div>
      )}
      {source && !empty ? (
        <p className="mt-3 text-[11.5px] text-text-faint">Source: {source}</p>
      ) : null}
    </section>
  );
}

/** The subset of the chart tooltip payload this component reads. */
interface TooltipEntry {
  name?: string;
  dataKey?: string | number;
  value?: number | string;
}

interface TooltipBoxProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
  unit?: string;
}

function TooltipBox({ active, payload, label, unit }: TooltipBoxProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-[8px] border border-border bg-surface px-3 py-2 text-[12px] shadow-[--shadow-md]">
      {label !== undefined ? (
        <p className="mb-1 font-medium">{String(label)}</p>
      ) : null}
      {payload.map((entry) => (
        <p
          key={String(entry.dataKey ?? entry.name)}
          className="tabular-nums text-text-muted"
        >
          {entry.name}:{" "}
          <span className="text-text">{formatValue(entry.value, unit)}</span>
        </p>
      ))}
    </div>
  );
}

function formatValue(value: unknown, unit?: string): string {
  if (typeof value !== "number") return String(value);
  if (unit === "count") return value.toLocaleString();
  return value.toFixed(4);
}

/** Risk spread across a scored dataset: how many rows land in each band. */
export function RiskDistributionChart({
  data,
  reviewThreshold,
  blockThreshold,
}: {
  data: { bucket: string; from: number; to: number; count: number }[];
  reviewThreshold?: number;
  blockThreshold?: number;
}) {
  return (
    <ChartFrame
      title="Risk distribution"
      description="How the risk scores in this run are spread out. The two lines
        are the review and block thresholds, so anything to their right was sent
        to a person or stopped."
      source="the run you just did"
      empty={!data?.length}
      height={220}
    >
      <AreaChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.32} />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="bucket" {...AXIS} interval={3} />
        <YAxis {...AXIS} allowDecimals={false} />
        <Tooltip content={<TooltipBox unit="count" />} />
        {reviewThreshold !== undefined ? (
          <ReferenceLine
            x={reviewThreshold.toFixed(2)}
            stroke="var(--medium)"
            strokeDasharray="4 3"
            label={{ value: "review", fontSize: 10, fill: "var(--medium)" }}
          />
        ) : null}
        {blockThreshold !== undefined ? (
          <ReferenceLine
            x={blockThreshold.toFixed(2)}
            stroke="var(--high)"
            strokeDasharray="4 3"
            label={{ value: "block", fontSize: 10, fill: "var(--high)" }}
          />
        ) : null}
        <Area
          type="monotone"
          dataKey="count"
          name="Transactions"
          stroke="var(--accent)"
          strokeWidth={1.8}
          fill="url(#riskFill)"
        />
      </AreaChart>
    </ChartFrame>
  );
}

const DECISION_COLOURS: Record<string, string> = {
  APPROVE: "var(--low)",
  REVIEW: "var(--medium)",
  BLOCK: "var(--high)",
};

export function DecisionChart({
  data,
  source,
}: {
  data: { decision: string; count: number }[];
  source: string;
}) {
  return (
    <ChartFrame
      title="Decisions"
      description="What Spark decided to do. Approve lets it through, review
        sends it to a person, block stops it."
      source={source}
      empty={!data?.length}
      height={220}
    >
      <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="decision" {...AXIS} />
        <YAxis {...AXIS} allowDecimals={false} />
        <Tooltip content={<TooltipBox unit="count" />} cursor={{ fill: "var(--bg-subtle)" }} />
        <Bar dataKey="count" name="Transactions" radius={[5, 5, 0, 0]} maxBarSize={72}>
          {data.map((d) => (
            <Cell key={d.decision} fill={DECISION_COLOURS[d.decision] ?? "var(--accent)"} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function PerformanceChart({
  data,
  source,
}: {
  data: { metric: string; value: number }[];
  source: string;
}) {
  return (
    <ChartFrame
      title="Model performance"
      description="Each bar runs from 0 to 1, and higher is better. Precision and
        recall pull against each other, so both matter."
      source={source}
      empty={!data?.length}
      height={220}
    >
      <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="metric" {...AXIS} />
        <YAxis {...AXIS} domain={[0, 1]} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--bg-subtle)" }} />
        <Bar
          dataKey="value"
          name="Score"
          fill="var(--accent)"
          radius={[5, 5, 0, 0]}
          maxBarSize={54}
        />
      </BarChart>
    </ChartFrame>
  );
}

export function ChannelChart({
  data,
}: {
  data: { channel: string; train_pr_auc: number; val_pr_auc: number; test_pr_auc: number }[];
}) {
  return (
    <ChartFrame
      title="Each part of the model, on its own"
      description="PR-AUC for the four scores that get combined, on each split.
        The tree model looks strongest during training and is not the strongest
        on the held-out test. That gap is the reason training scores are never
        reported as results."
      source="training, validation and held-out test"
      empty={!data?.length}
      height={250}
    >
      <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="channel" {...AXIS} />
        <YAxis {...AXIS} domain={[0, 1]} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--bg-subtle)" }} />
        <Bar dataKey="train_pr_auc" name="Train" fill="var(--text-faint)" radius={[4, 4, 0, 0]} />
        <Bar dataKey="val_pr_auc" name="Validation" fill="var(--medium)" radius={[4, 4, 0, 0]} />
        <Bar dataKey="test_pr_auc" name="Held-out test" fill="var(--accent)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartFrame>
  );
}

/**
 * The capability radar.
 *
 * Only axes the backend put a number on appear. There is no axis for
 * "explainability" or "speed" because neither has a comparable 0 to 1 score,
 * and inventing one would make the whole chart decorative.
 */
/**
 * Measured capability across the axes that have a real number behind them.
 *
 * A thin wrapper over the shared RadarChart, so this chart is defined in one
 * place and looks the same as any other. Axes without a comparable 0 to 1
 * score never reach here: the backend leaves them out rather than inventing a
 * value to complete the shape.
 */
export function CapabilityRadar({
  data,
  note,
}: {
  data: { axis: string; value: number; measured: string }[];
  note: string;
}) {
  if (!data?.length) {
    return (
      <ChartFrame
        title="Measured capability"
        description={note}
        source="held-out test"
        empty
        height={260}
      >
        <div />
      </ChartFrame>
    );
  }

  return (
    <RadarChart
      data={data as unknown as Record<string, string | number>[]}
      angleKey="axis"
      valueKeys="value"
      title="Measured capability"
      description={note}
      footer="Held-out test. Each axis is a separately measured number, not a rating."
      height={270}
    />
  );
}

export function CalibrationChart({
  data,
}: {
  data: { bin: string; mean_predicted: number; observed_rate: number; n: number }[];
}) {
  return (
    <ChartFrame
      title="Do the scores mean what they say"
      description="A calibrated score of 0.8 should mean about 80 out of 100 of
        those turn out to be fraud. The two bars in each band should match."
      source="held-out test"
      empty={!data?.length}
      height={230}
    >
      <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="bin" {...AXIS} />
        <YAxis {...AXIS} domain={[0, 1]} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--bg-subtle)" }} />
        <Bar dataKey="mean_predicted" name="Predicted" fill="var(--accent)" radius={[4, 4, 0, 0]} />
        <Bar dataKey="observed_rate" name="Actually happened" fill="var(--low)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartFrame>
  );
}
