/**
 * A radar chart for comparing several dimensions at once.
 *
 * Built to the referenced contract: `data`, `angleKey`, `valueKeys`, plus a
 * title, description, footer and an optional palette. One or many series are
 * supported, the legend appears on its own once there are two, and the fills
 * are translucent so overlapping shapes stay readable.
 *
 * The axis ticks show the dimension and its value together, which is what
 * makes a radar worth reading. A radar is good at showing the shape of a
 * strength and weakness profile and bad at letting you read a number off it,
 * so the number is printed rather than left to be estimated from the ring
 * spacing.
 *
 * Colours come from the shared chart tokens, so a series looks the same here
 * as it does in any other chart and follows the theme.
 */

import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart as RechartsRadar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Card, CardHeader } from "@/components/ui/primitives";

export const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

export interface RadarChartProps {
  /** Chart data rows. */
  data: Record<string, string | number>[];
  /** Key on each row used for the axis label. */
  angleKey: string;
  /** One or more numeric keys to plot. */
  valueKeys: string | string[];
  title?: string;
  description?: string;
  footer?: string;
  /** Custom palette for the series. */
  colors?: string[];
  /** Upper bound of the radius axis. Values here are 0 to 1 scores. */
  domain?: [number, number];
  height?: number;
}

/** Dimension name on one line, its value on the next. */
function AxisTick({
  payload,
  x,
  y,
  textAnchor,
  values,
}: {
  payload?: { value?: string };
  x?: number;
  y?: number;
  textAnchor?: "end" | "inherit" | "middle" | "start";
  values: Record<string, number>;
}) {
  const label = payload?.value ?? "";
  const value = values[label];
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        textAnchor={textAnchor}
        fill="var(--text-muted)"
        fontSize={11}
        dy={0}
      >
        {label}
      </text>
      {typeof value === "number" ? (
        <text
          textAnchor={textAnchor}
          fill="var(--text-faint)"
          fontSize={10.5}
          dy={13}
        >
          {value.toFixed(3)}
        </text>
      ) : null}
    </g>
  );
}

function TooltipBox({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name?: string; value?: number; color?: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-[8px] border border-border bg-surface px-3 py-2
        text-[12px] shadow-[--shadow-md]"
    >
      <p className="font-medium">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="mt-0.5 flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="size-2 shrink-0 rounded-full"
            style={{ background: entry.color }}
          />
          <span className="text-text-muted">{entry.name}</span>
          <span className="tabular-nums">{entry.value?.toFixed(4)}</span>
        </p>
      ))}
    </div>
  );
}

export function RadarChart({
  data,
  angleKey,
  valueKeys,
  title,
  description,
  footer,
  colors = CHART_COLORS,
  domain = [0, 1],
  height = 280,
}: RadarChartProps) {
  const keys = Array.isArray(valueKeys) ? valueKeys : [valueKeys];

  // The tick needs each axis's value, and only the first series can be printed
  // beside the label without the chart turning into a table.
  const values: Record<string, number> = {};
  for (const row of data) {
    const v = row[keys[0]];
    if (typeof v === "number") values[String(row[angleKey])] = v;
  }

  const body = (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsRadar data={data} outerRadius="68%">
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis
            dataKey={angleKey}
            tick={(props) => <AxisTick {...props} values={values} />}
          />
          <PolarRadiusAxis
            domain={domain}
            tick={{ fontSize: 10, fill: "var(--text-faint)" }}
            axisLine={false}
          />
          <Tooltip content={<TooltipBox />} />
          {keys.length > 1 ? (
            <Legend
              wrapperStyle={{ fontSize: 12, color: "var(--text-muted)" }}
              iconType="circle"
            />
          ) : null}
          {keys.map((key, i) => (
            <Radar
              key={key}
              name={key}
              dataKey={key}
              stroke={colors[i % colors.length]}
              strokeWidth={1.8}
              fill={colors[i % colors.length]}
              fillOpacity={0.2}
              isAnimationActive={false}
            />
          ))}
        </RechartsRadar>
      </ResponsiveContainer>
    </div>
  );

  if (!title && !description && !footer) return body;

  return (
    <Card>
      {title || description ? (
        <CardHeader title={title} description={description} />
      ) : null}
      <div className="p-4">{body}</div>
      {footer ? (
        <p className="border-t border-border px-4 py-3 text-[11.5px] leading-relaxed text-text-faint">
          {footer}
        </p>
      ) : null}
    </Card>
  );
}
