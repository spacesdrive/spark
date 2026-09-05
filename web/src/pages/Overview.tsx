/**
 * The first page anyone sees.
 *
 * It answers four questions and stops: what is Spark, which model is running,
 * what is happening with risk, and what should I do next.
 *
 * Everything that used to be here still exists, on the page that owns it. The
 * full metric set, the cost model, distribution shift, the per-split table and
 * the known limitations are all on Risk Analysis. Definitions are one hover
 * away instead of printed beside every number. Nothing was deleted to make
 * this shorter; it was moved to where someone would look for it.
 *
 * Every number and every chart comes from the API. A signed-in organization
 * sees its own request activity; a guest sees the held-out test window, and
 * the label says which it is rather than letting one be mistaken for the
 * other.
 */

import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/stores/app";
import { formatMetric } from "@/lib/format";
import { Icon } from "@/components/ui/icons";
import { Stepper } from "@/components/ui/Stepper";
import { StatRow } from "@/components/ui/StatRow";
import {
  Badge,
  Callout,
  Card,
  CardHeader,
  ErrorState,
  PageHeader,
} from "@/components/ui/primitives";
import { HoverPreview } from "@/components/ui/HoverPreview";
import { DecisionChart } from "@/components/charts/Charts";
import { DOCS } from "@/config/docs";

//: The numbers worth putting on a front page, in order of preference. The
//: rest are one click on.
//:
//: Longer than the four that are shown, because latency is measured for the
//: built-in model and not for a model you trained. Taking the first four that
//: were actually measured keeps the grid full for either, without a card
//: standing empty and without inventing a number to fill it.
const HEADLINE = [
  { key: "precision", label: "Precision", doc: DOCS.precision },
  { key: "recall", label: "Recall", doc: DOCS.recall },
  { key: "pr_auc", label: "PR-AUC", doc: DOCS.prAuc },
  { key: "p95_latency", label: "p95 latency", doc: DOCS.latency },
  { key: "roc_auc", label: "ROC-AUC", doc: DOCS.rocAuc },
];

/** How many of them the grid shows. */
const HEADLINE_COUNT = 4;

const ACTIONS = [
  {
    to: "/transaction",
    label: "Test a transaction",
    hint: "Score one payment and see why",
    icon: Icon.Transaction,
    primary: true,
  },
  {
    to: "/dataset",
    label: "Test a dataset",
    hint: "Upload a CSV and measure it",
    icon: Icon.Dataset,
  },
  {
    to: "/training",
    label: "Train a model",
    hint: "Fit Spark to your own history",
    icon: Icon.Train,
  },
  {
    to: "/sandbox",
    label: "Open the sandbox",
    hint: "Call the API with a test key",
    icon: Icon.Terminal,
  },
];

/**
 * The four stages every scored transaction goes through, in order.
 *
 * This is a description of the pipeline, not a progress indicator: all four
 * always run, so none of them is marked done or pending.
 */
const DECISION_STEPS = [
  {
    icon: Icon.Transaction,
    title: "Transaction",
    description: "Who paid whom, how much",
  },
  {
    icon: Icon.Gauge,
    title: "Risk analysis",
    description: "Four scores, combined and calibrated",
  },
  {
    icon: Icon.CheckCircle,
    title: "Decision",
    description: "Approve, review or block",
  },
  {
    icon: Icon.Chart,
    title: "Explanation",
    description: "What moved the score, and what it links to",
  },
];

export function Overview() {
  const { health, activeModel, activeOrg } = useApp();
  // Every panel below belongs to whichever model is selected.
  const modelId = activeModel?.id;
  const overview = useAsync(
    () => api.metrics.overview(modelId), [modelId]
  );
  const charts = useAsync(
    () => api.metrics.charts(modelId), [modelId]
  );
  const usage = useAsync(
    () =>
      activeOrg
        ? api.organizations.usage(activeOrg.id, undefined, modelId)
        : Promise.resolve(null),
    [activeOrg?.id, modelId]
  );

  const cards = overview.data?.cards ?? [];
  const headline = HEADLINE.map((h) => ({
    ...h,
    card: cards.find((c) => c.key === h.key),
  }))
    .filter((h) => h.card)
    .slice(0, HEADLINE_COUNT);

  // An organization with traffic sees its own decisions. Without traffic there
  // is nothing to plot, and the held-out test window is shown instead, said so.
  const live = usage.data && usage.data.total_requests > 0 ? usage.data : null;
  const decisions = live
    ? (["APPROVE", "REVIEW", "BLOCK"] as const).map((d) => ({
        decision: d,
        count: live.decisions[d] ?? 0,
      }))
    : (charts.data?.decision_distribution ?? []);
  const decisionSource = live
    ? `your API requests scored by ${activeModel?.name ?? "this model"}`
    : "held-out test, balanced setting";

  const modelReady = health?.model.available !== false;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Overview"
        description="What Spark is seeing, and what to do next."
        action={
          activeModel ? (
            <HoverPreview
              term="Active model"
              href={DOCS.modelVersion.href}
              trigger={
                <Badge tone="neutral">
                  {activeModel.name} {activeModel.version}
                </Badge>
              }
            >
              {DOCS.modelVersion.text}
            </HoverPreview>
          ) : null
        }
      />

      {!modelReady ? (
        <Callout tone="warning" title="No trained model is loaded">
          Scoring is unavailable until a model is trained on the server. Every
          other page still works.
        </Callout>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        {charts.loading ? (
          <ChartSkeleton />
        ) : decisions.length ? (
          <DecisionChart data={decisions} source={decisionSource} />
        ) : (
          <Card className="flex items-center justify-center p-10">
            <p className="text-[12.5px] text-text-faint">
              No decisions to show yet.
            </p>
          </Card>
        )}

        <Card>
          <CardHeader title="Next steps" />
          <ul className="divide-y divide-border">
            {ACTIONS.map((a) => (
              <li key={a.to}>
                <Link
                  to={a.to}
                  className="group flex items-center gap-3 px-5 py-[13px]
                    transition-colors hover:bg-bg-subtle"
                >
                  <span
                    className={`flex size-8 shrink-0 items-center justify-center
                      rounded-[8px] border border-border
                      ${a.primary ? "bg-accent/10 text-accent" : "text-text-muted"}`}
                  >
                    <a.icon size={15} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium leading-tight">
                      {a.label}
                    </span>
                    <span className="mt-0.5 block truncate text-[12px] text-text-muted">
                      {a.hint}
                    </span>
                  </span>
                  <Icon.ArrowRight
                    size={14}
                    className="shrink-0 text-text-faint transition-transform
                      group-hover:translate-x-0.5 group-hover:text-text-muted"
                  />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.55fr)]">
        <Card data-tour="flow">
          <CardHeader
            title="How a decision is made"
            action={
              <a
                href={DOCS.howItWorks}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 text-[12.5px] font-medium text-link
                  hover:underline"
              >
                Docs
              </a>
            }
          />
          <div className="px-5 py-4">
            <Stepper steps={DECISION_STEPS} />
          </div>
        </Card>

        <Card data-tour="metrics">
          <CardHeader
            title="Model health"
            description="Measured on a split the model never saw."
            action={
              <Link
                to="/analysis"
                className="shrink-0 text-[12.5px] font-medium text-link
                  hover:underline"
              >
                All metrics
              </Link>
            }
          />
          {overview.loading ? (
            <MetricSkeleton />
          ) : overview.error ? (
            <div className="p-5">
              <ErrorState
                title="No measured results yet"
                message={overview.error.message}
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-px border-t border-border bg-border">
              {headline.map(({ key, label, doc, card }) => (
                <StatRow
                  key={key}
                  className="bg-bg"
                  title={
                    <HoverPreview
                      term={label}
                      href={doc.href}
                      trigger={<span>{label}</span>}
                    >
                      {doc.text}
                    </HoverPreview>
                  }
                  value={formatMetric(card!.value, card!.format)}
                  source={card!.source}
                />
              ))}
            </div>
          )}
        </Card>
      </div>

      <p className="pb-2 text-[12px] leading-relaxed text-text-faint">
        Every number here was measured on data the model had not seen. The cost
        model, distribution shift, per-split results and the known limitations
        are on{" "}
        <Link to="/analysis" className="text-link hover:underline">
          Risk Analysis
        </Link>
        .
      </p>
    </div>
  );
}

function ChartSkeleton() {
  return (
    <Card className="p-5" aria-hidden="true">
      <div className="h-4 w-32 animate-pulse rounded bg-bg-subtle" />
      <div className="mt-4 h-[196px] animate-pulse rounded-[8px] bg-bg-subtle" />
    </Card>
  );
}

function MetricSkeleton() {
  return (
    <dl
      className="grid grid-cols-2 gap-px border-t border-border bg-border"
      aria-hidden="true"
    >
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="space-y-2 bg-bg px-5 py-4">
          <div className="h-3 w-16 animate-pulse rounded bg-bg-subtle" />
          <div className="h-5 w-20 animate-pulse rounded bg-bg-subtle" />
          <div className="h-2.5 w-24 animate-pulse rounded bg-bg-subtle" />
        </div>
      ))}
    </dl>
  );
}
