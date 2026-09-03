/**
 * Train a model on your own data.
 *
 * Training runs the same pipeline as the built-in model, on your transactions.
 * It produces a candidate with held-out results, and nothing it produces is
 * used for your live traffic until a person approves it here.
 *
 * Progress comes from the pipeline's own stages, so the bar moves when a step
 * finishes. It does not advance on a timer, which means a stalled run looks
 * stalled instead of looking busy.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, pollJob } from "@/api/client";
import { useApp } from "@/stores/app";
import { useAsync } from "@/hooks/useAsync";
import { useModelEvaluation } from "@/hooks/useModelEvaluation";
import type { DatasetRecord, Job, ModelInfo } from "@/types";
import { Icon } from "@/components/ui/icons";
import {
  ActionGroup,
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  ScrollTable,
  Spinner,
  Td,
  Th,
} from "@/components/ui/primitives";
import { Dropzone, FilePreview } from "@/components/data/Dropzone";
import { Stepper, type StepState } from "@/components/data/Stepper";
import { bytes, duration, ratio, shortDate } from "@/lib/format";

const STEPS = [
  { id: "dataset", label: "Dataset", hint: "Upload your history" },
  { id: "model", label: "Base model", hint: "What to start from" },
  { id: "settings", label: "Settings", hint: "Within safe limits" },
  { id: "training", label: "Training", hint: "Runs on the server" },
  { id: "results", label: "Results", hint: "Held-out evaluation" },
];

export function Training() {
  const { user, activeOrg, notify } = useApp();
  const limits = useAsync(() => api.training.limits(), []);
  const datasets = useAsync(
    () =>
      activeOrg
        ? api.datasets.forOrganization(activeOrg.id)
        : Promise.resolve([] as DatasetRecord[]),
    [activeOrg?.id]
  );

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<ApiError | null>(null);
  const [selected, setSelected] = useState<DatasetRecord | null>(null);
  const [name, setName] = useState("");
  const [attempt, setAttempt] = useState<ApiError | null>(null);
  const [trying, setTrying] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [promoting, setPromoting] = useState(false);

  if (!user) {
    return (
      <div className="space-y-6">
        <PageHeader
        breadcrumb={[{ label: "Models" }, { label: "Train My Model" }]}
          title="Train my model"
          description="Train Spark on your own historical transactions."
        />
        <Card>
          <CardHeader
            title="This needs an account"
            description="Training uses server resources and creates a model that
              belongs to your organization, so it cannot be done anonymously."
          />
          <div className="space-y-4 p-5">
            <p className="text-[13px] leading-relaxed text-text-muted">
              Everything else in Spark works without signing in. You can score a
              transaction, upload a test dataset, measure accuracy on your own
              labelled data and read the whole evaluation without an account.
            </p>
            <ActionGroup>
              <Link to="/login">
                <Button variant="primary" icon={<Icon.Google size={15} />}>
                  Sign in
                </Button>
              </Link>
              <Link to="/dataset">
                <Button>Test a dataset instead</Button>
              </Link>
            </ActionGroup>
          </div>
        </Card>
        {limits.data ? <LimitsPanel limits={limits.data} /> : null}
      </div>
    );
  }

  if (!activeOrg) {
    return (
      <div className="space-y-6">
        <PageHeader
        breadcrumb={[{ label: "Models" }, { label: "Train My Model" }]}
        title="Train my model"
      />
        <Card>
          <EmptyState
            icon={<Icon.Building size={26} />}
            title="Create an organization first"
            description="Datasets, models and API keys all belong to an
              organization. Create one and it becomes the owner of everything you
              upload or train."
            action={
              <Link to="/settings">
                <Button variant="primary">Go to Settings</Button>
              </Link>
            }
          />
        </Card>
      </div>
    );
  }

  const states: Record<string, StepState> = {
    dataset: selected ? "done" : "active",
    model: selected ? "done" : "pending",
    settings: selected ? "done" : "pending",
    training: job
      ? job.status === "succeeded"
        ? "done"
        : job.status === "failed"
          ? "failed"
          : "active"
      : "pending",
    results: model ? "done" : "pending",
  };

  async function upload(file: File) {
    if (!activeOrg) return;
    setUploading(true);
    setUploadError(null);
    try {
      const record = await api.datasets.upload(file, "training", activeOrg.id);
      setSelected(record);
      datasets.reload();
      notify({
        tone: record.validation.ok ? "success" : "warning",
        title: record.validation.ok
          ? "Training data uploaded"
          : "Training data needs fixing",
        body: `${record.n_rows.toLocaleString()} rows in ${record.original_name}.`,
      });
    } catch (err) {
      setUploadError(
        err instanceof ApiError ? err : new ApiError(0, { message: "Upload failed." })
      );
    } finally {
      setUploading(false);
    }
  }

  async function startTraining() {
    if (!activeOrg || !selected) return;
    setTrying(true);
    setAttempt(null);
    setJob(null);
    setModel(null);
    try {
      const started = await api.training.createJob({
        organization_id: activeOrg.id,
        dataset_id: selected.id,
        name: name.trim() || "My model",
      });
      setJob(started.job);
      notify({
        tone: "info",
        title: "Training started",
        body: started.note,
      });

      // The job runner reports the pipeline's real stages, so this reflects
      // work finished rather than time passed.
      const finished = await pollJob(started.job.id, setJob);
      if (finished.status === "succeeded") {
        const trained = await api.models.get(started.model_id);
        setModel(trained);
        notify({
          tone: "success",
          title: "Training finished",
          body: `${trained.name} is ready to compare. Nothing changes for your
            live traffic until you approve it.`,
        });
      } else {
        notify({
          tone: "error",
          title: "Training failed",
          body: finished.error ?? "The job did not finish.",
        });
      }
    } catch (err) {
      setAttempt(
        err instanceof ApiError ? err : new ApiError(0, { message: "Request failed." })
      );
    } finally {
      setTrying(false);
    }
  }

  async function promote() {
    if (!model) return;
    setPromoting(true);
    try {
      const result = await api.models.promote(model.id);
      setModel(result.model);
      notify({
        tone: "success",
        title: "Approved for production",
        body: result.note ?? "Live API keys now score with this model.",
      });
    } catch (err) {
      notify({
        tone: "error",
        title: "Could not approve that model",
        body: err instanceof ApiError ? err.message : "Request failed.",
      });
    } finally {
      setPromoting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Models" }, { label: "Train My Model" }]}
        title="Train my model"
        description="Train Spark on your own historical transactions, then compare
          the result with the built-in model on held-out data."
        action={<Badge tone="low">Available</Badge>}
      />

      <Callout tone="info" title="Training does not touch your live traffic">
        A training run produces a candidate model with held-out results. Your
        live API keys keep using whatever is already approved until you approve
        the new one yourself, and you can roll back afterwards.
      </Callout>

      <Card className="p-4">
        <Stepper steps={STEPS} states={states} />
      </Card>

      <Card>
        <CardHeader
          title="Your training data"
          description="A CSV of your historical transactions, with a label column
            saying what actually happened to each one."
          action={<Badge tone="low">Available</Badge>}
        />
        <div className="space-y-4 p-5">
          <Callout tone="info" title="This is kept separate from test data">
            Training data and test data are stored and marked separately, and
            Spark never trains on something you uploaded for testing. Mixing them
            is how a model ends up being measured on data it has already seen.
          </Callout>

          {limits.data?.max_upload_bytes && limits.data?.max_training_rows ? (
            <Dropzone
              onFile={(f) => void upload(f)}
              maxBytes={limits.data.max_upload_bytes}
              maxRows={limits.data.max_training_rows}
              busy={uploading}
            />
          ) : (
            <Spinner label="Reading the limits" />
          )}

          {uploadError ? (
            <ErrorState
              title="That file was not accepted"
              message={uploadError.message}
              fix={uploadError.body.fix}
            />
          ) : null}

          {selected ? (
            <>
              <FilePreview
                name={selected.original_name}
                size={selected.size_bytes}
                rows={selected.n_rows}
                onRemove={() => setSelected(null)}
              />
              {!selected.has_labels ? (
                <Callout tone="warning" title="No labels found">
                  Training needs to know what actually happened. Add a column with
                  1 for fraud and 0 for normal, then upload it again.
                </Callout>
              ) : null}
            </>
          ) : null}
        </div>
      </Card>

      {datasets.data?.length ? (
        <Card>
          <CardHeader
            title="Datasets in this organization"
            description="Uploaded by members of your organization, and visible to
              nobody else."
          />
          <ScrollTable>
            <thead>
              <tr>
                <Th>File</Th>
                <Th>Kind</Th>
                <Th align="right">Rows</Th>
                <Th align="right">Size</Th>
                <Th>Labels</Th>
                <Th>Uploaded</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {datasets.data.map((d) => (
                <tr key={d.id}>
                  <Td className="max-w-[220px] truncate">{d.original_name}</Td>
                  <Td>
                    <Badge tone={d.kind === "training" ? "accent" : "neutral"}>
                      {d.kind}
                    </Badge>
                  </Td>
                  <Td align="right">{d.n_rows.toLocaleString()}</Td>
                  <Td align="right">{bytes(d.size_bytes)}</Td>
                  <Td>{d.has_labels ? "yes" : "no"}</Td>
                  <Td>{shortDate(d.created_at)}</Td>
                  <Td align="right">
                    {d.kind === "training" ? (
                      <Button size="sm" onClick={() => setSelected(d)}>
                        Select
                      </Button>
                    ) : null}
                  </Td>
                </tr>
              ))}
            </tbody>
          </ScrollTable>
        </Card>
      ) : null}

      {limits.data ? <LimitsPanel limits={limits.data} /> : null}

      <Card>
        <CardHeader
          title="What training will do"
          description="The plan, so you know what the checks above are for."
        />
        <ol className="divide-y divide-border">
          {[
            [
              "Split your data by time",
              "The oldest rows train, the middle chooses thresholds, the newest is "
                + "held back and read once. Never shuffled, because shuffling lets "
                + "the model learn from transactions that happen after the ones it "
                + "is tested on.",
            ],
            [
              "Build features from the past only",
              "Each transaction is described using what came before it and nothing "
                + "later, with the same delay before a confirmed outcome becomes "
                + "usable that the built-in model applies.",
            ],
            [
              "Fit both models and search the weights",
              "The tree model and the graph model, then a search over how to blend "
                + "the four scores, decided on validation data.",
            ],
            [
              "Measure it on data it has never seen",
              "Precision, recall, F1, PR-AUC, ROC-AUC, the confusion matrix and the "
                + "expected cost, all on the held-out split.",
            ],
            [
              "Compare it with the built-in model",
              "On the same held-out data. If yours is worse, the comparison will "
                + "say so.",
            ],
          ].map(([title, detail], i) => (
            <li key={title} className="flex items-start gap-3 px-5 py-3.5">
              <span
                aria-hidden="true"
                className="flex size-5 shrink-0 items-center justify-center rounded-full
                  border border-border text-[11px] font-semibold text-text-faint"
              >
                {i + 1}
              </span>
              <div>
                <p className="text-[13px] font-medium">{title}</p>
                <p className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                  {detail}
                </p>
              </div>
            </li>
          ))}
        </ol>
        <p className="border-t border-border px-5 py-3 text-[12px] leading-relaxed text-text-muted">
          A better score on training data does not mean a better model. That is
          why the held-out split exists, and why it is read only once.
        </p>
      </Card>

      <Card>
        <CardHeader
          title="Start training"
          description="Runs the same pipeline as the built-in model, on your
            data, and measures the result on a held-out split."
        />
        <div className="space-y-4 p-5">
          <Field
            label="Model name"
            placeholder="My fraud model"
            value={name}
            onChange={(e) => setName(e.target.value)}
            hint="What this model is called in your registry."
          />
          <Button
            variant="primary"
            loading={trying}
            disabled={!selected || trying}
            onClick={() => void startTraining()}
            icon={<Icon.Train size={15} />}
          >
            {trying ? "Training" : "Start training"}
          </Button>
          {!selected ? (
            <p className="text-[12px] text-text-faint">
              Upload or select a training dataset first.
            </p>
          ) : null}

          {attempt ? (
            <ErrorState
              title="That request was refused"
              message={attempt.message}
              fix={attempt.body.fix}
            />
          ) : null}

          {job ? <JobProgress job={job} /> : null}
          {model ? (
            <TrainedModel
              model={model}
              promoting={promoting}
              onPromote={() => void promote()}
            />
          ) : null}
        </div>
      </Card>
    </div>
  );
}

/**
 * Where a running job has got to.
 *
 * The stage name comes from the pipeline itself, so it names real work. The bar
 * only moves when a stage completes; if a run stalls, this stops moving rather
 * than filling up regardless.
 */
function JobProgress({ job }: { job: Job }) {
  const failed = job.status === "failed";
  return (
    <div className="rounded-[--radius] border border-border bg-bg-subtle p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-medium">
          {failed ? "Training failed" : job.status === "succeeded"
            ? "Training finished"
            : `Training: ${job.stage}`}
        </p>
        <Badge tone={failed ? "high" : job.status === "succeeded" ? "low" : "neutral"}>
          {job.status}
        </Badge>
      </div>
      {!failed ? (
        <div
          className="mt-3 h-1.5 overflow-hidden rounded-full bg-border"
          role="progressbar"
          aria-valuenow={Math.round(job.progress * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-500"
            style={{ width: `${Math.max(2, job.progress * 100)}%` }}
          />
        </div>
      ) : null}
      {job.elapsed_seconds !== null ? (
        <p className="mt-2 text-[12px] text-text-faint">
          {duration(job.elapsed_seconds)} elapsed
        </p>
      ) : null}
      {failed && job.error ? (
        <p className="mt-2 text-[12.5px] leading-relaxed text-high">{job.error}</p>
      ) : null}
    </div>
  );
}

/**
 * A finished candidate, with the numbers needed to decide about it.
 *
 * Only held-out figures are shown. Training scores are deliberately absent,
 * because approving a model on the strength of what it memorised is the exact
 * mistake this screen exists to prevent.
 */
function TrainedModel({
  model,
  promoting,
  onPromote,
}: {
  model: ModelInfo;
  promoting: boolean;
  onPromote: () => void;
}) {
  // Same lookup as the model drawer. Reading the raw metrics field here is
  // what left the built-in model showing "not measured" beside numbers that
  // were sitting on the metrics endpoint.
  const { test, balanced, rows: trainedRows } = useModelEvaluation(model);

  const rows: [string, string][] = (
    [
      ["PR-AUC", ratio(test.pr_auc)],
      ["ROC-AUC", ratio(test.roc_auc)],
      ["Precision", ratio(balanced.precision)],
      ["Recall", ratio(balanced.recall)],
      ["F1", ratio(balanced.f1)],
      ["False positive rate", ratio(balanced.fpr)],
      ["Test transactions", test.n ? test.n.toLocaleString() : null],
      ["Rows trained on", trainedRows ? trainedRows.toLocaleString() : null],
    ] as [string, string | null][]
  ).filter((row): row is [string, string] => row[1] !== null);

  return (
    <Card>
      <CardHeader
        title={model.name}
        description="Measured on a held-out split that was read once, after every
          weight and threshold was fixed."
        action={
          <Badge tone={model.is_production ? "low" : "neutral"}>
            {model.is_production ? "In production" : "Candidate"}
          </Badge>
        }
      />
      <ScrollTable>
        <thead>
          <tr>
            <Th>Measure</Th>
            <Th align="right">Held-out test</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <Td>{label}</Td>
              <Td align="right">{value}</Td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
      <div className="space-y-3 border-t border-border px-5 py-4">
        <Callout tone="warning" title="Compare before you approve">
          These numbers describe your data, and the built-in model's numbers
          describe a different dataset, so they are not directly comparable. What
          matters is whether this model is good enough on your own held-out
          split.
        </Callout>
        {model.is_production ? (
          <p className="text-[12.5px] text-text-muted">
            Live API keys score with this model. You can roll back from Models.
          </p>
        ) : (
          <Button
            variant="primary"
            loading={promoting}
            onClick={onPromote}
            icon={<Icon.Check size={15} />}
          >
            Approve for production
          </Button>
        )}
      </div>
    </Card>
  );
}

/** Format a limit, or return null when the server did not send it. */
function num(value: number | undefined, unit?: string): string | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return unit ? `${value.toLocaleString()} ${unit}` : value.toLocaleString();
}

function LimitsPanel({
  limits,
}: {
  limits: import("@/types").TrainingLimits;
}) {
  // A row is dropped when the server did not send that limit, rather than
  // rendering "undefined" or throwing and taking the page down with it.
  const rows: [string, string][] = (
    [
      ["Smallest training dataset", num(limits.min_training_rows, "rows")],
      ["Largest training dataset", num(limits.max_training_rows, "rows")],
      ["Largest upload", limits.max_upload_bytes ? bytes(limits.max_upload_bytes) : null],
      ["Longest a training run may take", duration(limits.max_training_seconds)],
      ["Jobs running at once", num(limits.max_concurrent_jobs)],
      ["Jobs per organization per day", num(limits.max_jobs_per_org_per_day)],
      ["Uploads kept for", num(limits.dataset_retention_hours, "hours")],
      ["Accepted format", limits.accepted_formats?.join(", ").toUpperCase() ?? null],
    ] as [string, string | null][]
  ).filter((row): row is [string, string] => row[1] !== null);
  return (
    <Card>
      <CardHeader
        title="Limits"
        description="The values this server is actually configured with, not
          examples."
      />
      <ScrollTable>
        <thead>
          <tr>
            <Th>Limit</Th>
            <Th align="right">Value</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <Td>{label}</Td>
              <Td align="right">{value}</Td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
      <p className="px-5 py-3 text-[11.5px] leading-relaxed text-text-faint">
        Uploaded files are stored under a random name, never the one you chose,
        and are deleted after the retention window above. They are never executed
        and never loaded as Python objects.
      </p>
    </Card>
  );
}
