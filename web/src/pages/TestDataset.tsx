/**
 * Upload a CSV and score every row.
 *
 * The flow is upload, preview, validate, configure, run, results, and the
 * stepper at the top is the page's structure rather than an ornament above it:
 * only the stage you are in is on screen. Scoring runs as a backend job, and
 * the progress bar shows the stage the server reported. It never advances on a
 * timer.
 *
 * The most important behaviour here is the label distinction. With labels,
 * real precision and recall are computed. Without them, the page says clearly
 * that accuracy cannot be measured, and shows no accuracy numbers at all.
 */

import { useCallback, useRef, useState } from "react";
import { api, ApiError, pollJob } from "@/api/client";
import { useApp } from "@/stores/app";
import { useAsync } from "@/hooks/useAsync";
import type { DatasetRecord, Job, JobResult, ScoredRow } from "@/types";
import { DOCS } from "@/config/docs";
import { Icon } from "@/components/ui/icons";
import {
  ActionGroup,
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  CopyButton,
  ErrorState,
  PageHeader,
  ProgressBar,
  ScrollTable,
  Section,
  Select,
  Spinner,
  Td,
  Th,
} from "@/components/ui/primitives";
import { CooldownButton } from "@/components/ui/ActionButtons";
import { HoverPreview } from "@/components/ui/HoverPreview";
import { Drawer, Tabs } from "@/components/ui/Tabs";
import { DefinitionList, MetricStrip } from "@/components/ui/Layout";
import { Dropzone, FilePreview, RowPreview } from "@/components/data/Dropzone";
import { Stepper, type StepState } from "@/components/data/Stepper";
import { DecisionChart, RiskDistributionChart } from "@/components/charts/Charts";
import { money, percent, ratio } from "@/lib/format";
import { WhatDataCanIProvide } from "./TestTransaction";

const STEPS = [
  { id: "upload", label: "Upload", hint: "Choose a CSV" },
  { id: "validate", label: "Validate", hint: "Check the columns" },
  { id: "configure", label: "Configure", hint: "Model and thresholds" },
  { id: "run", label: "Run", hint: "Score every row" },
  { id: "results", label: "Results", hint: "Read and download" },
];

export function TestDataset() {
  const { mode, setMode, activeModel, notify, health } = useApp();
  const format = useAsync(() => api.datasets.format(), []);
  const example = useAsync(() => api.datasets.example(), []);

  const [dataset, setDataset] = useState<DatasetRecord | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{
    columns: string[];
    rows: Record<string, string>[];
    total_rows: number;
  } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const cancelled = useRef(false);

  const states: Record<string, StepState> = {
    upload: dataset ? "done" : "active",
    validate: !dataset ? "pending" : dataset.validation.ok ? "done" : "failed",
    configure: dataset?.validation.ok ? (job ? "done" : "active") : "pending",
    run: !job
      ? "pending"
      : job.status === "failed"
        ? "failed"
        : job.status === "succeeded"
          ? "done"
          : "active",
    results: result ? "done" : "pending",
  };

  const reset = useCallback(() => {
    cancelled.current = true;
    setDataset(null);
    setFile(null);
    setPreview(null);
    setJob(null);
    setResult(null);
    setError(null);
  }, []);

  async function upload(chosen: File) {
    cancelled.current = false;
    setUploading(true);
    setError(null);
    setResult(null);
    setJob(null);
    setFile(chosen);
    try {
      const record = await api.datasets.upload(chosen, "test");
      setDataset(record);
      const rows = await api.datasets.preview(record.id, 8);
      setPreview(rows);
      if (record.validation.ok) {
        notify({
          tone: "success",
          title: "Upload checked",
          body: `${record.n_rows.toLocaleString()} rows read from ${record.original_name}.`,
        });
      } else {
        notify({
          tone: "warning",
          title: "That file needs fixing",
          body: `${record.validation.issues.filter((i) => i.severity === "error").length} problems stop it being scored.`,
        });
      }
    } catch (err) {
      setError(
        err instanceof ApiError ? err : new ApiError(0, { message: "Upload failed." })
      );
      setFile(null);
    } finally {
      setUploading(false);
    }
  }

  async function run() {
    if (!dataset) return;
    setError(null);
    setResult(null);
    cancelled.current = false;
    try {
      const started = await api.datasets.score(dataset.id, mode, activeModel?.id);
      setJob(started);
      const finished = await pollJob(started.id, (tick) => {
        if (!cancelled.current) setJob(tick);
      });
      if (cancelled.current) return;
      if (finished.status === "failed") {
        setError(
          new ApiError(500, {
            message: "Scoring failed.",
            detail: finished.error ?? undefined,
          })
        );
        notify({ tone: "error", title: "Scoring failed", body: finished.error ?? "" });
        return;
      }
      const output = await api.jobs.result(started.id, 0, 100);
      setResult(output);
      notify({
        tone: "success",
        title: "Scoring complete",
        body: `${output.n_rows.toLocaleString()} rows scored${
          output.evaluation ? " and measured against your labels." : "."
        }`,
      });
    } catch (err) {
      setError(
        err instanceof ApiError ? err : new ApiError(0, { message: "Scoring failed." })
      );
    }
  }

  const limits = format.data?.limits;
  const modelUnavailable = health && !health.model.available;
  const running = !!job && job.status !== "succeeded" && job.status !== "failed";

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Test Spark" }, { label: "Test Dataset" }]}
        title="Test a dataset"
        description="Upload your own transactions as a CSV. Spark scores every
          row, and if your file says what actually happened, it measures how
          accurate those scores were."
        action={
          dataset ? (
            <Button size="sm" onClick={reset} icon={<Icon.Refresh size={14} />}>
              Start over
            </Button>
          ) : null
        }
      />

      <Stepper steps={STEPS} states={states} />

      {modelUnavailable ? (
        <Callout tone="warning" title="No model is loaded">
          Nothing can be scored until a model has been trained on the server.
        </Callout>
      ) : null}

      {!dataset ? (
        <UploadStage
          limits={limits}
          uploading={uploading}
          disabled={!!modelUnavailable}
          error={error}
          onFile={(f) => void upload(f)}
          example={example.data}
          columns={format.data?.columns}
          exampleCsv={format.data?.example_csv}
        />
      ) : (
        <div className="space-y-6">
          {file ? (
            <FilePreview
              name={dataset.original_name}
              size={dataset.size_bytes}
              rows={dataset.n_rows}
              onRemove={reset}
            />
          ) : null}

          <ValidationSummary dataset={dataset} preview={preview} />

          {dataset.validation.ok ? (
            <Section
              title="Configure the run"
              description="Only the settings the backend actually accepts."
            >
              <Card>
                <div className="grid gap-4 p-4 sm:grid-cols-2 sm:p-5">
                  <Select
                    label="Model"
                    value={activeModel?.id ?? ""}
                    onChange={() => undefined}
                    options={
                      activeModel
                        ? [
                            {
                              value: activeModel.id,
                              label: `${activeModel.name} ${activeModel.version}`,
                            },
                          ]
                        : [{ value: "", label: "No model available" }]
                    }
                    hint="Change this in the model selector at the top of the page."
                  />
                  <Select
                    label="Threshold setting"
                    value={mode}
                    onChange={setMode}
                    options={[
                      { value: "balanced", label: "Balanced (lowest expected cost)" },
                      { value: "high_precision", label: "High precision" },
                      { value: "high_recall", label: "High recall" },
                    ]}
                    hint="Chosen on validation data, then applied unchanged."
                  />
                </div>
                <div className="border-t border-border p-4 sm:p-5">
                  <ActionGroup>
                    <Button
                      variant="primary"
                      onClick={() => void run()}
                      loading={running}
                      disabled={!!modelUnavailable}
                      icon={<Icon.Play size={15} />}
                    >
                      Score {dataset.n_rows.toLocaleString()} rows
                    </Button>
                  </ActionGroup>
                </div>
              </Card>
            </Section>
          ) : null}

          {running ? (
            <Section title="Scoring" description="Progress reported by the server.">
              <Card className="p-4 sm:p-5">
                <ProgressBar
                  value={job!.progress}
                  stage={job!.stage}
                  status={
                    job!.elapsed_seconds !== null
                      ? `${job!.elapsed_seconds.toFixed(1)} seconds elapsed`
                      : undefined
                  }
                />
              </Card>
            </Section>
          ) : null}

          {error && dataset ? (
            <div className="space-y-3">
              <ErrorState
                title="Scoring did not finish"
                message={error.message}
                fix={error.body.detail}
              />
              <CooldownButton cooldownSeconds={10} onClick={() => void run()}>
                Retry scoring
              </CooldownButton>
            </div>
          ) : null}

          {result ? <DatasetResults result={result} jobId={job!.id} /> : null}
        </div>
      )}
    </div>
  );
}

/**
 * The first stage: what to upload, and the limits it must fit inside.
 *
 * The reference material used to sit permanently below the dropzone. It is
 * behind tabs now, because it is something you consult once while preparing a
 * file and never again.
 */
function UploadStage({
  limits,
  uploading,
  disabled,
  error,
  onFile,
  example,
  columns,
  exampleCsv,
}: {
  limits?: { max_upload_bytes: number; max_test_rows: number };
  uploading: boolean;
  disabled: boolean;
  error: ApiError | null;
  onFile: (file: File) => void;
  example?: {
    name: string;
    description: string;
    rows?: number;
    labeled?: number;
    source: string;
    caution: string;
  } | null;
  columns?: { column: string; label: string; requirement: string; why: string }[];
  exampleCsv?: string;
}) {
  const required = (columns ?? [])
    .filter((c) => c.requirement === "required")
    .map((c) => c.label);

  return (
    <div className="space-y-6">
      <Section
        title="Upload"
        description="A CSV where each row is one transaction."
        action={
          <HoverPreview
            term="What data should I upload"
            href={DOCS.dataset}
            trigger={
              <span className="cursor-help text-[12px] text-text-muted">
                What should I upload
              </span>
            }
          >
            One row per transaction, with an amount, a customer and a merchant.
            Add a label column saying what actually happened and Spark will also
            measure how accurate its scores were.
          </HoverPreview>
        }
      >
        <Card className="p-4 sm:p-5">
          {limits ? (
            <>
              <Dropzone
                onFile={onFile}
                maxBytes={limits.max_upload_bytes}
                maxRows={limits.max_test_rows}
                busy={uploading}
                disabled={disabled}
              />
              <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-text-muted">
                <li>CSV only</li>
                <li>
                  up to {(limits.max_upload_bytes / 1_000_000).toFixed(0)} MB
                </li>
                <li>up to {limits.max_test_rows.toLocaleString()} rows</li>
                {required.length ? <li>needs {required.join(", ")}</li> : null}
              </ul>
            </>
          ) : (
            <Spinner label="Reading the limits" />
          )}
          {error ? (
            <div className="mt-4">
              <ErrorState
                title="That file was not accepted"
                message={error.message}
                fix={error.body.fix}
              />
            </div>
          ) : null}
        </Card>
      </Section>

      <p className="text-[12.5px] leading-relaxed text-text-muted">
        Spark was not trained on data from your business, so these scores are
        risk signals rather than proof. An uploaded file is scored using only
        its own history, so the customers and merchants in it start with no
        past.
      </p>

      <Tabs
        items={[
          {
            id: "fields",
            label: "Fields",
            content: columns ? (
              <WhatDataCanIProvide columns={columns} />
            ) : (
              <Card className="p-5">
                <Spinner label="Reading the field reference" />
              </Card>
            ),
          },
          {
            id: "example-csv",
            label: "Example CSV",
            content: exampleCsv ? (
              <Card>
                <CardHeader
                  title="A small example"
                  description="The shape Spark expects."
                  action={<CopyButton value={exampleCsv} label="Copy" />}
                />
                <pre className="overflow-x-auto p-4 font-mono text-[11.5px] leading-relaxed">
                  {exampleCsv}
                </pre>
              </Card>
            ) : (
              <Card className="p-5">
                <Spinner label="Reading the example" />
              </Card>
            ),
          },
          ...(example
            ? [
                {
                  id: "spark-data",
                  label: "Spark's own data",
                  content: (
                    <Card>
                      <CardHeader
                        title={example.name}
                        description={example.description}
                        action={<Badge tone="accent">example</Badge>}
                      />
                      <div className="space-y-3 p-4 sm:p-5">
                        <DefinitionList
                          items={[
                            {
                              label: "Transactions",
                              value: example.rows?.toLocaleString(),
                            },
                            {
                              label: "With a confirmed outcome",
                              value: example.labeled?.toLocaleString(),
                            },
                            { label: "Source", value: example.source },
                          ]}
                        />
                        <Callout tone="warning" title="What this example is for">
                          {example.caution}
                        </Callout>
                        <p className="text-[12.5px] leading-relaxed text-text-muted">
                          The measured results for this dataset are already on the
                          Overview and Risk Analysis pages, produced by the pipeline
                          itself rather than re-scored in the browser.
                        </p>
                      </div>
                    </Card>
                  ),
                },
              ]
            : []),
        ]}
      />
    </div>
  );
}

/**
 * What the validator found, as a summary rather than a dump.
 *
 * Backend issues already arrive as a plain problem and a plain fix, so nothing
 * here needs to translate an exception name. The checks that passed are shown
 * as well as the ones that failed, because "your file is fine" is the answer
 * most uploads need.
 */
function ValidationSummary({
  dataset,
  preview,
}: {
  dataset: DatasetRecord;
  preview: { columns: string[]; rows: Record<string, string>[]; total_rows: number } | null;
}) {
  const v = dataset.validation;
  const errors = v.issues.filter((i) => i.severity === "error");
  const warnings = v.issues.filter((i) => i.severity === "warning");

  const checks = [
    { label: "Columns", ok: v.columns.length > 0 },
    { label: "Required fields", ok: errors.every((e) => !/missing/i.test(e.problem)) },
    { label: "Data types", ok: !errors.some((e) => /number|numeric|type/i.test(e.problem)) },
    { label: "Labels", ok: v.has_labels, note: v.has_labels ? undefined : "not provided" },
  ];

  return (
    <Section
      title={v.ok ? "Your file is ready" : "Your file needs some fixes"}
      description={
        v.ok
          ? "Spark found the columns it needs."
          : "Spark cannot score this until the problems below are fixed."
      }
      action={
        <Badge tone={v.ok ? "low" : "high"}>
          {v.ok ? "Ready" : `${errors.length} to fix`}
        </Badge>
      }
    >
      <MetricStrip
        columns={3}
        items={[
          { label: "Rows", value: v.n_rows.toLocaleString() },
          { label: "Columns found", value: v.columns.length },
          {
            label: "Labels",
            value: v.has_labels ? "Yes" : "No",
            sub: v.has_labels
              ? "accuracy can be measured"
              : "accuracy cannot be measured",
          },
        ]}
      />

      <Card>
        <div className="flex flex-wrap gap-x-6 gap-y-2 border-b border-border px-4 py-3">
          {checks.map((check) => (
            <span
              key={check.label}
              className="inline-flex items-center gap-1.5 text-[12.5px]"
            >
              {check.ok ? (
                <Icon.Check size={14} className="text-low" />
              ) : (
                <Icon.Close size={14} className="text-text-faint" />
              )}
              {check.label}
              {check.note ? (
                <span className="text-text-faint">({check.note})</span>
              ) : null}
            </span>
          ))}
        </div>

        <div className="px-4 py-3">
          <p className="mb-2 text-[12.5px] font-medium">Columns Spark matched</p>
          <ul className="flex flex-wrap gap-1.5">
            {Object.entries(v.mapping).map(([sparkCol, yourCol]) => (
              <li key={sparkCol}>
                <Badge tone="accent">
                  {sparkCol} = {yourCol}
                </Badge>
              </li>
            ))}
          </ul>
          {v.missing_recommended.length ? (
            <p className="mt-2.5 text-[12px] text-text-muted">
              Not found: {v.missing_recommended.join(", ")}. Spark will treat those
              as one unknown value, so those links in the graph carry nothing.
            </p>
          ) : null}
        </div>

        {errors.length ? (
          <ul className="divide-y divide-border border-t border-border">
            {errors.map((issue, i) => (
              <li key={i} className="flex items-start gap-3 px-4 py-3">
                <Icon.Alert size={15} className="mt-0.5 shrink-0 text-high" />
                <div className="min-w-0">
                  <p className="text-[13px] font-medium">
                    {issue.column}: {issue.problem}
                  </p>
                  <p className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                    {issue.fix}
                  </p>
                  {issue.examples.length ? (
                    <p className="mt-1 font-mono text-[11.5px] text-text-faint">
                      For example: {issue.examples.join(", ")}
                    </p>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : null}

        {warnings.length ? (
          <ul className="divide-y divide-border border-t border-border">
            {warnings.map((issue, i) => (
              <li key={i} className="flex items-start gap-3 px-4 py-2.5">
                <Icon.Info size={15} className="mt-0.5 shrink-0 text-medium" />
                <div className="min-w-0">
                  <p className="text-[13px]">
                    {issue.column}: {issue.problem}
                  </p>
                  <p className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                    {issue.fix}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        ) : null}

        {v.notes.length ? (
          <ul className="space-y-1.5 border-t border-border px-4 py-3">
            {v.notes.map((n) => (
              <li
                key={n}
                className="flex items-start gap-2 text-[12.5px] text-text-muted"
              >
                <Icon.Info size={13} className="mt-0.5 shrink-0 text-text-faint" />
                {n}
              </li>
            ))}
          </ul>
        ) : null}
      </Card>

      {preview ? (
        <RowPreview
          columns={preview.columns}
          rows={preview.rows}
          total={preview.total_rows}
        />
      ) : null}
    </Section>
  );
}

function DatasetResults({ result, jobId }: { result: JobResult; jobId: string }) {
  const bands = result.summary.risk_bands;
  const fit = (result as unknown as { fit?: DataFit }).fit;
  const [row, setRow] = useState<ScoredRow | null>(null);

  return (
    <div className="space-y-6">
      <Section
        title="Results summary"
        description={`${result.n_rows.toLocaleString()} rows scored with
          ${result.model_version} at the ${result.mode} setting.`}
      >
        <MetricStrip
          items={[
            { label: "Total transactions", value: result.n_rows.toLocaleString() },
            {
              label: "Low risk",
              value: bands.LOW.toLocaleString(),
              sub: percent(bands.LOW / result.n_rows, 0),
              tone: "low",
            },
            {
              label: "Medium risk",
              value: bands.MEDIUM.toLocaleString(),
              sub: percent(bands.MEDIUM / result.n_rows, 0),
              tone: "medium",
            },
            {
              label: "High risk",
              value: bands.HIGH.toLocaleString(),
              sub: percent(bands.HIGH / result.n_rows, 0),
              tone: "high",
            },
          ]}
        />
      </Section>

      <div className="grid gap-4 lg:grid-cols-2">
        <RiskDistributionChart
          data={result.summary.histogram}
          reviewThreshold={result.review_threshold}
          blockThreshold={result.block_threshold}
        />
        <DecisionChart
          data={Object.entries(result.summary.decisions).map(([decision, count]) => ({
            decision,
            count,
          }))}
          source="your uploaded data"
        />
      </div>

      {fit ? <DataFitPanel fit={fit} /> : null}

      {result.evaluation ? (
        <EvaluationPanel evaluation={result.evaluation} />
      ) : (
        <Section title="Accuracy">
          <Callout tone="info" title="Accuracy was not measured">
            Predictions are available, but accuracy cannot be measured because
            actual outcomes were not provided. A label says what really happened
            after the transaction: 1 for fraud, 0 for normal. Precision, recall and
            PR-AUC are left out on purpose rather than filled in with a guess.
          </Callout>
        </Section>
      )}

      <Section
        title="Detailed results"
        description={`The highest-risk rows first. All
          ${result.row_count.toLocaleString()} scored rows are in the download.`}
        action={
          <a href={api.jobs.downloadUrl(jobId)} download>
            <Button variant="primary" size="sm" icon={<Icon.Download size={14} />}>
              Download CSV
            </Button>
          </a>
        }
      >
        <Card>
          <ScrollTable>
            <thead>
              <tr>
                <Th>Transaction ID</Th>
                <Th align="right">Risk score</Th>
                <Th>Risk level</Th>
                <Th>Decision</Th>
                <Th>Model version</Th>
              </tr>
            </thead>
            <tbody>
              {[...result.rows]
                .sort((a, b) => b.risk_score - a.risk_score)
                .slice(0, 25)
                .map((r) => (
                  <tr
                    key={r.transaction_id}
                    onClick={() => setRow(r)}
                    className="interactive cursor-pointer"
                  >
                    <Td className="font-mono text-[12px]">{r.transaction_id}</Td>
                    <Td align="right">{ratio(r.risk_score)}</Td>
                    <Td>
                      <Badge
                        tone={
                          r.risk_band === "HIGH"
                            ? "high"
                            : r.risk_band === "MEDIUM"
                              ? "medium"
                              : "low"
                        }
                      >
                        {r.risk_band}
                      </Badge>
                    </Td>
                    <Td>{r.decision}</Td>
                    <Td className="font-mono text-[12px] text-text-muted">
                      {r.model_version}
                    </Td>
                  </tr>
                ))}
            </tbody>
          </ScrollTable>
          <p className="px-4 py-3 text-[11.5px] leading-relaxed text-text-faint">
            Select a row for the customer, merchant, amount, the four component
            scores and your label. The download contains those same fields and
            nothing about the server.
          </p>
        </Card>
      </Section>

      <RowDrawer row={row} onClose={() => setRow(null)} />
    </div>
  );
}

/** Everything about one scored row, including the four component scores. */
function RowDrawer({ row, onClose }: { row: ScoredRow | null; onClose: () => void }) {
  if (!row) return null;
  return (
    <Drawer
      open={!!row}
      onClose={onClose}
      title={row.transaction_id}
      description={`Scored ${ratio(row.risk_score)} and ${row.decision.toLowerCase()}ed`}
      footer={<CopyButton value={JSON.stringify(row, null, 2)} label="Copy row" />}
    >
      <div className="space-y-5">
        <div className="flex flex-wrap gap-1.5">
          <Badge
            tone={
              row.risk_band === "HIGH"
                ? "high"
                : row.risk_band === "MEDIUM"
                  ? "medium"
                  : "low"
            }
          >
            {row.risk_band}
          </Badge>
          <Badge tone="neutral">{row.decision}</Badge>
          {row.path === "COLD_START" ? (
            <Badge tone="neutral">cold start</Badge>
          ) : null}
        </div>

        <Section title="Transaction">
          <DefinitionList
            columns={1}
            items={[
              { label: "Customer", value: row.customer_id },
              { label: "Merchant", value: row.merchant_id },
              { label: "Amount", value: money(row.amount) },
              { label: "Model version", value: row.model_version },
              {
                label: "Actual outcome",
                value:
                  row.label === null
                    ? "not provided"
                    : row.label === 1
                      ? "fraud"
                      : "normal",
              },
            ]}
          />
        </Section>

        <Section
          title="Component scores"
          description="The four signals Spark blends into the final score."
        >
          <DefinitionList
            columns={1}
            items={[
              { label: "Tabular", value: ratio(row.score_tabular) },
              { label: "Graph", value: ratio(row.score_graph) },
              { label: "Behavioural", value: ratio(row.score_behavioral) },
              { label: "Velocity", value: ratio(row.score_velocity) },
            ]}
          />
        </Section>
      </div>
    </Drawer>
  );
}

interface DataFit {
  verdict: "good" | "shifted" | "limited" | "unknown";
  explanation: string;
  psi: number | null;
  psi_status: string;
  psi_note: string;
  rows: number;
  distinct_customers: number;
  distinct_merchants: number;
  cold_share: number;
  limitations: string[];
}

/**
 * Whether your data resembles what the model was trained on.
 *
 * The verdict comes from PSI and from how much of the file is cold. It is not
 * turned into an accuracy claim, because a distribution distance cannot say
 * whether a score was right.
 */
function DataFitPanel({ fit }: { fit: DataFit }) {
  const tone =
    fit.verdict === "good" ? "low" : fit.verdict === "shifted" ? "high" : "medium";
  const heading = {
    good: "Good",
    shifted: "Shifted",
    limited: "Limited",
    unknown: "Not enough data to tell",
  }[fit.verdict];

  return (
    <Section
      title="Model and data fit"
      description="Whether your transactions look like the ones the model was
        trained on. This is about fit, not about accuracy."
      action={
        <HoverPreview
          term="Model and data fit"
          href={DOCS.distributionShift.href}
          trigger={
            <Badge tone={tone as "low" | "medium" | "high"}>{heading}</Badge>
          }
        >
          {DOCS.distributionShift.text}
        </HoverPreview>
      }
    >
      <Card className="space-y-3 p-4 sm:p-5">
        <p className="text-[13px] leading-relaxed text-text-muted">
          {fit.explanation}
        </p>
        <DefinitionList
          columns={3}
          items={[
            {
              label: "PSI against training scores",
              value:
                fit.psi === null
                  ? "not enough rows"
                  : `${fit.psi} (${fit.psi_status})`,
            },
            {
              label: "Distinct customers",
              value: fit.distinct_customers.toLocaleString(),
            },
            {
              label: "Distinct merchants",
              value: fit.distinct_merchants.toLocaleString(),
            },
          ]}
        />
        <p className="text-[11.5px] leading-relaxed text-text-faint">
          {fit.psi_note}
        </p>
        {fit.limitations.length ? (
          <ul className="space-y-1.5 border-t border-border pt-3">
            {fit.limitations.map((l) => (
              <li
                key={l}
                className="flex items-start gap-2 text-[12.5px] text-text-muted"
              >
                <Icon.Alert size={13} className="mt-0.5 shrink-0 text-medium" />
                {l}
              </li>
            ))}
          </ul>
        ) : null}
      </Card>
    </Section>
  );
}

/**
 * Accuracy on your own labels, as a compact table rather than eight tiles.
 *
 * Each metric carries its definition on hover, so the row stays short and the
 * explanation is still one gesture away.
 */
function EvaluationPanel({
  evaluation,
}: {
  evaluation: NonNullable<JobResult["evaluation"]>;
}) {
  const c = evaluation.confusion;

  const metrics: { label: string; value: string; doc?: { href: string; text: string } }[] =
    [
      { label: "Precision", value: ratio(evaluation.precision), doc: DOCS.precision },
      { label: "Recall", value: ratio(evaluation.recall), doc: DOCS.recall },
      { label: "F1", value: ratio(evaluation.f1) },
      { label: "PR-AUC", value: ratio(evaluation.pr_auc), doc: DOCS.prAuc },
      { label: "ROC-AUC", value: ratio(evaluation.roc_auc), doc: DOCS.rocAuc },
      { label: "False positive rate", value: ratio(evaluation.fpr), doc: DOCS.fpr },
      { label: "False negative rate", value: ratio(evaluation.fnr), doc: DOCS.fnr },
      { label: "Fraud in your file", value: percent(evaluation.base_rate, 1) },
    ];

  return (
    <Section
      title="How accurate was it on your data"
      description={`Measured against the ${evaluation.n.toLocaleString()} rows where
        you told Spark what actually happened.`}
      action={<Badge tone="accent">your data</Badge>}
    >
      <Card>
        <ScrollTable>
          <thead>
            <tr>
              <Th>Metric</Th>
              <Th align="right">Value</Th>
              <Th>What it means</Th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.label}>
                <Td className="font-medium">
                  {m.doc ? (
                    <HoverPreview
                      term={m.label}
                      href={m.doc.href}
                      trigger={
                        <span>{m.label}</span>
                      }
                    >
                      {m.doc.text}
                    </HoverPreview>
                  ) : (
                    m.label
                  )}
                </Td>
                <Td align="right">{m.value}</Td>
                <Td className="max-w-sm text-[12px] text-text-muted">
                  {m.doc ? m.doc.text.split(".")[0] + "." : ""}
                </Td>
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-[12.5px] font-medium">Confusion matrix</p>
          <Card>
            <ScrollTable>
              <thead>
                <tr>
                  <Th />
                  <Th align="right">Spark said risky</Th>
                  <Th align="right">Spark said fine</Th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <Td className="font-medium">Actually fraud</Td>
                  <Td align="right">{c.tp.toLocaleString()}</Td>
                  <Td align="right">{c.fn.toLocaleString()}</Td>
                </tr>
                <tr>
                  <Td className="font-medium">Actually normal</Td>
                  <Td align="right">{c.fp.toLocaleString()}</Td>
                  <Td align="right">{c.tn.toLocaleString()}</Td>
                </tr>
              </tbody>
            </ScrollTable>
          </Card>
        </div>
        <div>
          <p className="mb-2 text-[12.5px] font-medium">What that would cost</p>
          <DefinitionList
            columns={1}
            items={[
              ["Loss with no system", evaluation.cost.baseline_loss_no_system],
              ["Loss prevented", evaluation.cost.prevented_loss],
              ["Loss still getting through", evaluation.cost.residual_loss],
              ["Cost of running Spark", evaluation.cost.expected_cost],
              ["Net benefit", evaluation.cost.net_benefit],
            ].map(([label, value]) => ({
              label,
              value: money(value as number),
            }))}
          />
          <p className="mt-2 text-[11.5px] leading-relaxed text-text-faint">
            Using Spark's configured cost settings, in whatever units your amount
            column uses. Change those settings to match your business before
            reading anything into the total.
          </p>
        </div>
      </div>
    </Section>
  );
}
