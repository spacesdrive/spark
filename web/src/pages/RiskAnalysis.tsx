/**
 * The full evaluation, organised rather than poured onto the page.
 *
 * This page exists to show what was measured, on which split, and where it
 * breaks. It carries more than the Overview does on purpose, so the job here
 * is not to cut content but to stop it arriving all at once: a summary you can
 * read in a glance, then tabs for the parts you go looking for.
 *
 * The operating point that does not transfer is still displayed as a failure
 * rather than quietly dropped.
 */

import { useMemo, useState } from "react";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/stores/app";
import { ms, money, ratio } from "@/lib/format";
import { DOCS } from "@/config/docs";
import { Icon } from "@/components/ui/icons";
import {
  Badge,
  Button,
  Card,
  Callout,
  EmptyState,
  ErrorState,
  PageHeader,
  ScrollTable,
  Section,
  Select,
  Spinner,
  Td,
  Th,
} from "@/components/ui/primitives";
import { Tabs } from "@/components/ui/Tabs";
import { DefinitionList, FilterBar } from "@/components/ui/Layout";
import { HoverPreview } from "@/components/ui/HoverPreview";
import {
  CalibrationChart,
  CapabilityRadar,
  ChannelChart,
  PerformanceChart,
} from "@/components/charts/Charts";
import type { MetricsOverview } from "@/types";

/** The metrics table, with a plain definition attached to each row. */
const EXPLANATIONS: Record<string, { href: string; text: string }> = {
  "PR-AUC": DOCS.prAuc,
  "ROC-AUC": DOCS.rocAuc,
  Precision: DOCS.precision,
  Recall: DOCS.recall,
  "False positive rate": DOCS.fpr,
  "False negative rate": DOCS.fnr,
};

export function RiskAnalysis() {
  const { activeModel } = useApp();
  const modelId = activeModel?.id;
  const overview = useAsync(
    () => api.metrics.overview(modelId), [modelId]
  );
  const charts = useAsync(
    () => api.metrics.charts(modelId), [modelId]
  );
  const thresholds = useAsync(() => api.risk.thresholds(), []);
  const limitations = useAsync(
    () => api.metrics.limitations(modelId), [modelId]
  );

  const [split, setSplit] = useState("test");
  const [setting, setSetting] = useState("all");

  const data = overview.data;

  const chosen = useMemo(
    () => data?.splits.find((s) => s.split === split) ?? data?.splits.at(-1),
    [data, split]
  );

  const points = useMemo(() => {
    const all = data?.operating_points ?? [];
    return setting === "all" ? all : all.filter((op) => op.mode === setting);
  }, [data, setting]);

  if (overview.loading) {
    return (
      <div className="space-y-6">
        <PageHeader
          breadcrumb={[{ label: "Analysis" }, { label: "Risk Analysis" }]}
          title="Risk analysis"
        />
        <Card className="p-6">
          <Spinner label="Reading the evaluation report" />
        </Card>
      </div>
    );
  }
  if (overview.error) {
    return (
      <ErrorState
        title="No evaluation to show"
        message={overview.error.message}
        fix={overview.error.body.fix}
        onRetry={overview.reload}
      />
    );
  }
  if (!data || !chosen) return null;

  const stress = charts.data?.stress_slices ?? [];
  const balanced =
    data.operating_points.find((op) => op.mode === "balanced") ??
    data.operating_points[0];
  const activeFilters =
    (split !== "test" ? 1 : 0) + (setting !== "all" ? 1 : 0);

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Analysis" }, { label: "Risk Analysis" }]}
        title="Risk analysis"
        description="Everything Spark measured, and which split each number came
          from. The held-out test split was read once, after every weight and
          threshold had been frozen on validation data."
        action={
          activeModel ? (
            <Badge tone="accent">
              {activeModel.name} {activeModel.version}
            </Badge>
          ) : null
        }
      />

      <FilterBar
        count={activeFilters}
        action={
          activeFilters ? (
            <Button
              size="sm"
              onClick={() => {
                setSplit("test");
                setSetting("all");
              }}
            >
              Reset
            </Button>
          ) : null
        }
      >
        <Select
          label="Split"
          value={split}
          onChange={setSplit}
          options={data.splits.map((s) => ({
            value: s.split,
            label: s.split.charAt(0).toUpperCase() + s.split.slice(1),
          }))}
        />
        <Select
          label="Threshold setting"
          value={setting}
          onChange={setSetting}
          options={[
            { value: "all", label: "All settings" },
            ...data.operating_points.map((op) => ({
              value: op.mode,
              label: op.mode,
            })),
          ]}
        />
      </FilterBar>

      <Tabs
        items={[
          {
            id: "overview",
            label: "Overview",
            content: (
              <div className="space-y-6">
                <Section
                  title="Results by split"
                  description="Train fits the models. Validation chooses weights and
                    thresholds. Test is the only estimate of behaviour on unseen
                    data. The split chosen in the filter is highlighted."
                >
                  <Card>
                    <ScrollTable>
                      <thead>
                        <tr>
                          <Th>Split</Th>
                          <Th align="right">Rows</Th>
                          <Th align="right">Fraud</Th>
                          <Th align="right">Fraud rate</Th>
                          <Th align="right">PR-AUC</Th>
                          <Th align="right">ROC-AUC</Th>
                          <Th align="right">Brier</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.splits.map((s) => (
                          <tr
                            key={s.split}
                            className={s.split === split ? "bg-accent-soft" : undefined}
                          >
                            <Td className="font-medium capitalize">{s.split}</Td>
                            <Td align="right">{s.n.toLocaleString()}</Td>
                            <Td align="right">{s.n_positive.toLocaleString()}</Td>
                            <Td align="right">{ratio(s.base_rate)}</Td>
                            <Td align="right">{ratio(s.pr_auc)}</Td>
                            <Td align="right">{ratio(s.roc_auc)}</Td>
                            <Td align="right">{ratio(s.brier)}</Td>
                          </tr>
                        ))}
                      </tbody>
                    </ScrollTable>
                    <p className="px-4 py-3 text-[11.5px] leading-relaxed text-text-faint">
                      PR-AUC depends on how common fraud is in a split, so these
                      rows are not comparable with each other. The test window has
                      a much higher fraud rate because a ring operates in it.
                    </p>
                  </Card>
                </Section>

                <ModelAndDataFit drift={data.drift} />

                <Section
                  title="Where it gets harder"
                  description="The same model, measured separately on entities it
                    had barely seen and on ones it knew well."
                >
                  {stress.length ? (
                    <Card>
                      <ScrollTable>
                        <thead>
                          <tr>
                            <Th>Slice</Th>
                            <Th align="right">Rows</Th>
                            <Th align="right">Fraud rate</Th>
                            <Th align="right">PR-AUC</Th>
                            <Th align="right">Precision</Th>
                            <Th align="right">Recall</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {stress.map((s) => (
                            <tr key={String(s.slice)}>
                              <Td className="font-medium">
                                {s.slice === "cold_entities"
                                  ? "Barely seen before"
                                  : "Familiar entities"}
                              </Td>
                              <Td align="right">{Number(s.n).toLocaleString()}</Td>
                              <Td align="right">{ratio(Number(s.base_rate))}</Td>
                              <Td align="right">{ratio(Number(s.pr_auc))}</Td>
                              <Td align="right">{ratio(Number(s.precision))}</Td>
                              <Td align="right">{ratio(Number(s.recall))}</Td>
                            </tr>
                          ))}
                        </tbody>
                      </ScrollTable>
                      <p className="px-4 py-3 text-[12px] leading-relaxed text-text-muted">
                        History features cannot help on a merchant the system has
                        never seen. The gap between these two rows is exactly how
                        much Spark leans on already knowing an entity.
                      </p>
                    </Card>
                  ) : (
                    <Card>
                      <EmptyState
                        title="No slice breakdown in this report"
                        description="The evaluation did not include a cold-entity split."
                      />
                    </Card>
                  )}
                </Section>
              </div>
            ),
          },
          {
            id: "metrics",
            label: "Metrics",
            content: (
              <div className="space-y-6">
                <Section
                  title="Detailed metrics"
                  description="Every number below comes from the evaluation report.
                    Hover a metric name for what it means."
                >
                  <Card>
                    <ScrollTable>
                      <thead>
                        <tr>
                          <Th>Metric</Th>
                          <Th align="right">Value</Th>
                          <Th>Split</Th>
                          <Th>What it tells you</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          ["PR-AUC", ratio(chosen.pr_auc)],
                          ["ROC-AUC", ratio(chosen.roc_auc)],
                          ["Precision", ratio(balanced?.precision ?? 0)],
                          ["Recall", ratio(balanced?.recall ?? 0)],
                          ["F1", ratio(balanced?.f1 ?? 0)],
                        ].map(([label, value]) => {
                          const doc = EXPLANATIONS[String(label)];
                          return (
                            <tr key={String(label)}>
                              <Td className="font-medium">
                                {doc ? (
                                  <HoverPreview
                                    term={String(label)}
                                    href={doc.href}
                                    trigger={
                                      <span>{label}</span>
                                    }
                                  >
                                    {doc.text}
                                  </HoverPreview>
                                ) : (
                                  label
                                )}
                              </Td>
                              <Td align="right">{value}</Td>
                              <Td className="capitalize text-text-muted">
                                {chosen.split}
                              </Td>
                              <Td className="max-w-sm text-[12px] text-text-muted">
                                {doc ? doc.text.split(".")[0] + "." : ""}
                              </Td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </ScrollTable>
                  </Card>
                </Section>

                <Section
                  title="Speed"
                  description="Measured on one laptop CPU. Your machine will differ."
                >
                  {charts.data?.latency ? (
                    <DefinitionList
                      items={[
                        [
                          "Half of calls finish under",
                          ms(charts.data.latency.per_transaction.p50_ms),
                        ],
                        [
                          "19 in 20 finish under",
                          ms(charts.data.latency.per_transaction.p95_ms),
                        ],
                        [
                          "With an explanation, half under",
                          ms(charts.data.latency.with_explanation.p50_ms),
                        ],
                        [
                          "In a batch",
                          `${Math.round(
                            charts.data.latency.batch_throughput_per_s
                          ).toLocaleString()} per second`,
                        ],
                      ].map(([label, value]) => ({ label, value }))}
                    />
                  ) : (
                    <p className="text-[13px] text-text-muted">
                      Latency has not been measured on this server.
                    </p>
                  )}
                </Section>

                <Section
                  title="What it would cost"
                  description="A fraud system is only worth running if the money
                    number improves. These come from the cost sweep on the held-out
                    test."
                >
                  <DefinitionList
                    items={[
                      ["Loss with no system at all", data.cost.baseline_loss_no_system],
                      ["Loss Spark prevented", data.cost.prevented_loss],
                      ["Loss that still got through", data.cost.residual_loss],
                      ["Cost of running Spark", data.cost.expected_cost],
                      ["Cost per 1,000 transactions", data.cost.cost_per_1k],
                      ["Net benefit", data.cost.net_benefit],
                    ].map(([label, value]) => ({
                      label,
                      value: money(value as number),
                    }))}
                  />
                  <p className="text-[11.5px] leading-relaxed text-text-faint">
                    Review is counted as neither free nor perfect: it costs money
                    and lets 20% of the fraud sent to it through. Counting review as
                    a save is the easiest way to make these numbers look better than
                    they are.
                  </p>
                </Section>
              </div>
            ),
          },
          {
            id: "charts",
            label: "Charts",
            content: (
              <div className="space-y-4">
                {charts.data ? (
                  <div className="grid gap-4 lg:grid-cols-2">
                    <ChannelChart data={charts.data.channel_performance} />
                    <CalibrationChart data={charts.data.calibration} />
                  </div>
                ) : (
                  <Card className="p-6">
                    <Spinner label="Reading the charts" />
                  </Card>
                )}
                {charts.data?.model_performance?.length ||
                charts.data?.radar?.length ? (
                  <div className="grid gap-4 lg:grid-cols-2">
                    {charts.data.model_performance?.length ? (
                      <PerformanceChart
                        data={charts.data.model_performance}
                        source="held-out test, balanced setting"
                      />
                    ) : null}
                    {charts.data.radar?.length ? (
                      <CapabilityRadar
                        data={charts.data.radar}
                        note={charts.data.radar_note}
                      />
                    ) : null}
                  </div>
                ) : null}
              </div>
            ),
          },
          {
            id: "decisions",
            label: "Thresholds",
            badge: (
              <Badge tone={points.some((op) => !op.transfers) ? "high" : "neutral"}>
                {points.length}
              </Badge>
            ),
            content: (
              <div className="space-y-6">
                <Section
                  title="Threshold settings"
                  description="All of these were chosen on validation data and then
                    applied to the test data without being touched again."
                >
                  <Card>
                    <ScrollTable>
                      <thead>
                        <tr>
                          <Th>Setting</Th>
                          <Th align="right">Blocks at</Th>
                          <Th align="right">Precision</Th>
                          <Th align="right">Recall</Th>
                          <Th align="right">F1</Th>
                          <Th align="right">Alerts</Th>
                          <Th>Works on test</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {points.map((op) => (
                          <tr key={op.mode}>
                            <Td>
                              <span className="font-medium">{op.mode}</span>
                              <span className="mt-0.5 block text-[11.5px] text-text-muted">
                                {op.rationale}
                              </span>
                            </Td>
                            <Td align="right">{ratio(op.block_threshold)}</Td>
                            <Td align="right">{ratio(op.precision)}</Td>
                            <Td align="right">{ratio(op.recall)}</Td>
                            <Td align="right">{ratio(op.f1)}</Td>
                            <Td align="right">
                              {op.n_predicted_positive.toLocaleString()}
                            </Td>
                            <Td>
                              {op.transfers ? (
                                <Badge tone="low">yes</Badge>
                              ) : (
                                <Badge tone="high">no</Badge>
                              )}
                            </Td>
                          </tr>
                        ))}
                      </tbody>
                    </ScrollTable>
                  </Card>

                  {points.some((op) => !op.transfers) ? (
                    <Callout tone="warning" title="One setting does not carry over">
                      {points
                        .filter((op) => !op.transfers)
                        .map((op) => (
                          <span key={op.mode} className="block">
                            <strong>{op.mode}</strong>: its threshold was chosen
                            correctly on validation, but the score distribution moved
                            afterwards, so it fires on only{" "}
                            {op.n_predicted_positive.toLocaleString()} of{" "}
                            {(op.tp + op.fp + op.tn + op.fn).toLocaleString()} test
                            transactions. Precision on an almost empty set means
                            nothing, so this is reported as a failure.
                          </span>
                        ))}
                    </Callout>
                  ) : null}
                </Section>

                {thresholds.data ? (
                  <Section
                    title="As the API reports them"
                    description="What a caller gets from GET /api/risk/thresholds."
                  >
                    <Card>
                      <ScrollTable>
                        <thead>
                          <tr>
                            <Th>Mode</Th>
                            <Th align="right">Review at</Th>
                            <Th align="right">Block at</Th>
                            <Th>Chosen on</Th>
                            <Th>Transfers</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {thresholds.data.thresholds.map((t) => (
                            <tr key={t.mode}>
                              <Td className="font-medium">{t.mode}</Td>
                              <Td align="right">{ratio(t.review_threshold)}</Td>
                              <Td align="right">{ratio(t.block_threshold)}</Td>
                              <Td>{t.selected_on}</Td>
                              <Td>
                                {t.transfers_to_test === null ? (
                                  <span className="text-text-faint">not measured</span>
                                ) : t.transfers_to_test ? (
                                  <Badge tone="low">yes</Badge>
                                ) : (
                                  <Badge tone="high">no</Badge>
                                )}
                              </Td>
                            </tr>
                          ))}
                        </tbody>
                      </ScrollTable>
                    </Card>
                  </Section>
                ) : null}
              </div>
            ),
          },
        ]}
      />

      {/*
        The limits are a standing caveat on every number above, not a view you
        switch to, so they sit under the tabs where they apply to all of them.
      */}
      <details className="group rounded-[10px] border border-border bg-surface">
        <summary
          className="flex cursor-pointer list-none items-center justify-between
            gap-3 px-4 py-3 text-[13px] font-medium"
        >
          <span className="flex items-center gap-2">
            What these numbers do not cover
            {limitations.data?.limitations?.length ? (
              <Badge tone="medium">{limitations.data.limitations.length}</Badge>
            ) : null}
          </span>
          <Icon.ChevronDown
            size={16}
            className="shrink-0 text-text-muted transition-transform
              group-open:rotate-180"
          />
        </summary>

        <div className="space-y-3 border-t border-border px-4 py-4">
          {limitations.data?.limitations?.length ? (
            <ul className="space-y-3">
              {limitations.data.limitations.map((l) => (
                <li key={l.title} className="flex items-start gap-3">
                  <Icon.Alert size={15} className="mt-0.5 shrink-0 text-medium" />
                  <div className="min-w-0">
                    <p className="text-[13px] font-medium">{l.title}</p>
                    <p className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                      {l.detail}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="border-t border-border pt-3 text-[11.5px] leading-relaxed text-text-faint">
            A test fails the build if the held-out PR-AUC ever goes above 0.999.
            On messy, drifting data a near-perfect score almost always means a
            bug that leaks future information into the features.
          </p>
        </div>
      </details>
    </div>
  );
}

/**
 * Whether the score distribution moved, stated as a verdict.
 *
 * PSI is a distance between two distributions and nothing else. It does not
 * become an accuracy number here: the verdict says the thresholds need
 * refreshing, which is the actual consequence.
 */
function ModelAndDataFit({ drift }: { drift: MetricsOverview["drift"] }) {
  const shifted = drift.status === "SHIFTED";
  return (
    <Section
      title="Model and data fit"
      description="Comparing validation scores with held-out test scores."
      action={
        <HoverPreview
          term="Distribution shift"
          href={DOCS.distributionShift.href}
          trigger={
            <Badge tone={shifted ? "high" : "low"}>
              {shifted ? "Shifted" : "Good"}
            </Badge>
          }
        >
          {DOCS.distributionShift.text}
        </HoverPreview>
      }
    >
      <Card className="p-5">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
          <span className="text-[28px] font-semibold leading-none tabular-nums">
            {ratio(drift.psi, 3)}
          </span>
          <span className="text-[12.5px] text-text-muted">
            population stability index
          </span>
        </div>
        <p className="mt-3 text-[12.5px] leading-relaxed text-text-muted">
          {drift.implication}
        </p>
        <div className="mt-4">
          <DefinitionList
            items={[
              {
                label: `Mean on ${drift.reference}`,
                value: ratio(drift.reference_mean),
              },
              {
                label: `Mean on ${drift.current}`,
                value: ratio(drift.current_mean),
              },
            ]}
          />
        </div>
      </Card>
    </Section>
  );
}
