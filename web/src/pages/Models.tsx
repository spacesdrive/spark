/**
 * Model management.
 *
 * A list, not a wall of cards. Every model used to occupy a large panel with
 * its metadata spelled out, which made two models fill a screen and five
 * unusable. The table answers "what have I got and which one is live", and the
 * detail behind any row opens in a drawer so the list keeps its place.
 *
 * Built-in models are shown to everyone. Custom models only appear for members
 * of the organization that owns them, because that is all the API returns.
 */

import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { useModelEvaluation } from "@/hooks/useModelEvaluation";
import { useApp } from "@/stores/app";
import { ratio, shortDate } from "@/lib/format";
import { Icon } from "@/components/ui/icons";
import {
  ActionGroup,
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  PageHeader,
  ScrollTable,
  Section,
  Spinner,
  Td,
  Th,
} from "@/components/ui/primitives";
import { Drawer, Tabs } from "@/components/ui/Tabs";
import { HoldButton } from "@/components/ui/ActionButtons";
import { HoverPreview } from "@/components/ui/HoverPreview";
import { PinnedList } from "@/components/ui/PinnedList";
import { DOCS } from "@/config/docs";
import type { ModelInfo } from "@/types";

export function Models() {
  const { models, activeModel, setActiveModel, user, activeOrg } = useApp();
  const [openModel, setOpenModel] = useState<ModelInfo | null>(null);

  const builtin = models.filter((m) => m.kind === "builtin");

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Models" }]}
        title="Models"
        description="What Spark can score with, and which one is live."
        action={
          user && activeOrg ? (
            <Link to="/training">
              <Button variant="primary" icon={<Icon.Train size={15} />}>
                Train a model
              </Button>
            </Link>
          ) : null
        }
      />

      {!models.length ? (
        <Card>
          <EmptyState
            icon={<Icon.Model size={26} />}
            title="No model is available"
            description="Train one on the server first, with python -m spark.models.train."
          />
        </Card>
      ) : (
        <Section
          title="Built in"
          description="Ships with Spark and is always available."
        >
          <div className="overflow-hidden rounded-[10px] border border-border">
            <ScrollTable>
              <thead>
                <tr>
                  <Th>Model</Th>
                  <Th>Status</Th>
                  <Th align="right">
                    <HoverPreview
                      term="PR-AUC"
                      href={DOCS.prAuc.href}
                      trigger={<span>Held-out PR-AUC</span>}
                    >
                      {DOCS.prAuc.text}
                    </HoverPreview>
                  </Th>
                  <Th align="right">Trained</Th>
                  <Th align="right">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {builtin.map((m) => (
                  <tr key={m.id}>
                    <Td>
                      <span className="font-medium">{m.name}</span>
                      <span className="ml-2 font-mono text-[11.5px] text-text-faint">
                        {m.version}
                      </span>
                    </Td>
                    <Td>
                      {m.id === activeModel?.id ? (
                        <Badge tone="accent">in use</Badge>
                      ) : (
                        <Badge tone="neutral">{m.status}</Badge>
                      )}
                    </Td>
                    <Td align="right">
                      {typeof m.held_out_pr_auc === "number"
                        ? ratio(m.held_out_pr_auc)
                        : "not measured"}
                    </Td>
                    <Td align="right" className="text-text-muted">
                      {m.trained_at ? shortDate(m.trained_at) : "not recorded"}
                    </Td>
                    <Td align="right">
                      <ActionGroup align="end">
                        {m.id !== activeModel?.id ? (
                          <Button size="sm" onClick={() => setActiveModel(m.id)}>
                            Use this
                          </Button>
                        ) : null}
                        <Button size="sm" variant="ghost" onClick={() => setOpenModel(m)}>
                          Details
                        </Button>
                      </ActionGroup>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </ScrollTable>
          </div>
        </Section>
      )}

      <Section
        title="Your models"
        description="Trained on your own history, and visible only to your
          organization."
        action={<Badge tone="low">Available</Badge>}
      >
        {!user ? (
          <Callout tone="info" title="An account is needed for this">
            Training produces a model that belongs to your organization, so it
            cannot be done anonymously.{" "}
            <Link to="/login" className="text-link hover:underline">
              Sign in
            </Link>{" "}
            to set that up. Everything else on this page works without one.
          </Callout>
        ) : !activeOrg ? (
          <Callout tone="info" title="Create an organization first">
            Models belong to an organization.{" "}
            <Link to="/settings" className="text-link hover:underline">
              Create one in Settings
            </Link>
            .
          </Callout>
        ) : (
          <CustomModels organizationId={activeOrg.id} />
        )}
      </Section>

      <ModelDrawer model={openModel} onClose={() => setOpenModel(null)} />
    </div>
  );
}

/**
 * Everything about one model, without leaving the list.
 *
 * Tabbed because the four things you might want are unrelated: what it is,
 * how it scored, what it was fitted on, and how the blend is weighted.
 */
function ModelDrawer({
  model,
  onClose,
  footer,
}: {
  model: ModelInfo | null;
  onClose: () => void;
  /** Actions for this one model, shown pinned to the bottom of the panel. */
  footer?: ReactNode;
}) {
  const detail = useAsync(
    () => (model ? api.models.get(model.id) : Promise.resolve(null)),
    [model?.id]
  );

  const { test, balanced, metrics, rows, loading: reportLoading } =
    useModelEvaluation(model);

  // Every hook above runs unconditionally; the early return comes after them.
  if (!model) return null;

  const weights = (detail.data as unknown as {
    fusion_weights?: Record<string, number>;
  })?.fusion_weights;

  return (
    <Drawer
      open
      onClose={onClose}
      title={model.name}
      description={`${model.kind === "builtin" ? "Built in" : "Custom"} model, version ${model.version}`}
      footer={footer}
    >
      <Tabs
        items={[
          {
            id: "overview",
            label: "Overview",
            content: (
              <dl className="space-y-0 divide-y divide-border">
                {[
                  ["Version", model.version],
                  ["Kind", model.kind],
                  ["Status", model.is_production ? "in production" : model.status],
                  ["Trained", model.trained_at ? shortDate(model.trained_at) : "not recorded"],
                  ["Input", model.input_format],
                  ["Modes", model.modes.join(", ")],
                ].map(([label, value]) => (
                  <div key={String(label)} className="flex justify-between gap-4 py-2.5">
                    <dt className="text-[12.5px] text-text-muted">{label}</dt>
                    <dd className="text-right text-[12.5px] font-medium">{value}</dd>
                  </div>
                ))}
              </dl>
            ),
          },
          {
            id: "evaluation",
            label: "Evaluation",
            content: reportLoading ? (
              <Spinner label="Reading the evaluation report" />
            ) : test.pr_auc == null && !model.held_out_pr_auc ? (
              <p className="py-6 text-center text-[12.5px] text-text-faint">
                This model has no stored held-out results. Built-in model results
                are on the Risk Analysis page.
              </p>
            ) : (
              <dl className="space-y-0 divide-y divide-border">
                {[
                  ["PR-AUC", ratio(test.pr_auc ?? model.held_out_pr_auc ?? undefined)],
                  ["ROC-AUC", ratio(test.roc_auc)],
                  ["Precision", ratio(balanced.precision)],
                  ["Recall", ratio(balanced.recall)],
                  ["F1", ratio(balanced.f1)],
                  ["False positive rate", ratio(balanced.fpr)],
                ].map(([label, value]) => (
                  <div key={String(label)} className="flex justify-between gap-4 py-2.5">
                    <dt className="text-[12.5px] text-text-muted">{label}</dt>
                    <dd className="text-right font-mono text-[12.5px]">{value}</dd>
                  </div>
                ))}
              </dl>
            ),
          },
          {
            id: "training",
            label: "Training",
            content: (
              <dl className="space-y-0 divide-y divide-border">
                {[
                  ["Rows used", rows?.toLocaleString() ?? "not recorded"],
                  ["Rows in file", (metrics.n_rows ?? rows)?.toLocaleString() ?? "not recorded"],
                  // A built-in model is not fine-tuned from anything, so
                  // "not recorded" was the wrong word for it.
                  [
                    "Base model",
                    model.base_model ??
                      (model.kind === "builtin" ? "trained from scratch" : "not recorded"),
                  ],
                  ["Measured on", metrics.measured_on ?? "held-out test"],
                  [
                    "Training time",
                    metrics.total_train_seconds
                      ? `${Math.round(metrics.total_train_seconds)}s`
                      : "not recorded",
                  ],
                ].map(([label, value]) => (
                  <div key={String(label)} className="flex justify-between gap-4 py-2.5">
                    <dt className="text-[12.5px] text-text-muted">{label}</dt>
                    <dd className="text-right text-[12.5px] font-medium">{value}</dd>
                  </div>
                ))}
              </dl>
            ),
          },
          {
            id: "blend",
            label: "Blend",
            content: detail.loading ? (
              <Spinner label="Reading the model" />
            ) : weights ? (
              <>
                <p className="mb-3 text-[12px] leading-relaxed text-text-muted">
                  These weights were searched over 400 combinations on validation
                  data. They were not chosen by hand.
                </p>
                <dl className="space-y-0 divide-y divide-border">
                  {Object.entries(weights).map(([channel, weight]) => (
                    <div key={channel} className="flex justify-between gap-4 py-2.5">
                      <dt className="text-[12.5px] text-text-muted">
                        {CHANNEL_LABELS[channel] ?? channel}
                      </dt>
                      <dd className="text-right font-mono text-[12.5px]">
                        {ratio(weight)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </>
            ) : (
              <p className="py-6 text-center text-[12.5px] text-text-faint">
                No blend weights are recorded for this model.
              </p>
            ),
          },
        ]}
      />
    </Drawer>
  );
}

const CHANNEL_LABELS: Record<string, string> = {
  tabular: "Tree model",
  graph: "Graph model",
  behavioral: "Behaviour score",
  velocity: "Velocity score",
};


function CustomModels({ organizationId }: { organizationId: string }) {
  const { notify } = useApp();
  // The drawer lives here rather than on the page, so its footer can reach the
  // same reload and busy state the actions need.
  const [detail, setDetail] = useState<ModelInfo | null>(null);
  const models = useAsync(
    () => api.models.list(organizationId),
    [organizationId]
  );
  const [busy, setBusy] = useState<string | null>(null);

  const mine = (models.data?.models ?? []).filter((m) => m.kind === "custom");
  const production = mine.find((m) => m.is_production) ?? null;

  async function run(
    label: string,
    id: string,
    // Each endpoint returns its own shape; only the optional note is read here.
    action: () => Promise<{ note?: string } | Record<string, unknown>>
  ) {
    setBusy(id);
    try {
      const result = (await action()) as { note?: string };
      models.reload();
      notify({ tone: "success", title: label, body: result.note ?? "Done." });
    } catch (err) {
      notify({
        tone: "error",
        title: `Could not ${label.toLowerCase()}`,
        body: err instanceof ApiError ? err.message : "Request failed.",
      });
    } finally {
      setBusy(null);
    }
  }

  if (models.loading) return <Spinner label="Reading your models" />;

  if (!mine.length) {
    return (
      <Callout tone="info" title="You have not trained a model yet">
        Upload your historical transactions with labels on the{" "}
        <Link to="/training" className="text-link hover:underline">
          Train My Model
        </Link>{" "}
        page. Training runs the same pipeline as the built-in model and reports
        held-out results you can compare against.
      </Callout>
    );
  }

  return (
    <div className="space-y-4">
      <PinnedList
        storageKey="spark.models.pinned"
        items={mine.map((m) => ({
          id: m.id,
          name: `${m.name} ${m.version}`,
          subtitle: [
            m.is_production ? "production" : m.status,
            typeof m.held_out_pr_auc === "number"
              ? `PR-AUC ${ratio(m.held_out_pr_auc)}`
              : "not measured",
            m.training_rows ? `${m.training_rows.toLocaleString()} rows` : null,
          ]
            .filter(Boolean)
            .join("  ·  "),
          icon: <Icon.Model size={16} />,
          onOpen: () => setDetail(m),
        }))}
      />

      {production ? (
        <div className="space-y-3 rounded-[--radius] border border-border bg-bg-subtle p-4">
          <p className="text-[13px]">
            <span className="font-medium">{production.name}</span> is serving
            your live API keys.
          </p>
          <p className="text-[12.5px] leading-relaxed text-text-muted">
            Rolling back returns production to whatever it was before the last
            approval. If there was nothing before it, production returns to the
            built-in model and your live keys keep working.
          </p>
          <HoldButton
            onConfirm={() =>
              void run("Rolled back", organizationId, () =>
                api.organizations.rollback(organizationId)
              )
            }
          >
            Roll back production
          </HoldButton>
        </div>
      ) : (
        <Callout tone="info" title="Nothing is in production yet">
          Your live API keys use the built-in model until you approve one of
          your own. Test keys always use the built-in model, whatever you
          approve.
        </Callout>
      )}

      <ModelDrawer
        model={detail}
        onClose={() => setDetail(null)}
        footer={
          detail && !detail.is_production && detail.status === "trained" ? (
            <ActionGroup>
              <Button
                variant="primary"
                loading={busy === detail.id}
                onClick={() =>
                  void run("Approved for production", detail.id, () =>
                    api.models.promote(detail.id)
                  ).then(() => setDetail(null))
                }
              >
                Approve for production
              </Button>
              <Button
                variant="ghost"
                loading={busy === detail.id}
                onClick={() =>
                  void run("Rejected", detail.id, () =>
                    api.models.reject(detail.id)
                  ).then(() => setDetail(null))
                }
              >
                Reject
              </Button>
            </ActionGroup>
          ) : null
        }
      />
    </div>
  );
}
