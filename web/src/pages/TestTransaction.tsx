/**
 * Score one transaction.
 *
 * The page is two halves and says so: you describe a transaction on the left,
 * and the decision with its evidence appears on the right. The form used to be
 * five stacked cards with a threshold selector and an essay about unsupported
 * fields between you and the button; the fields are now grouped by what they
 * describe, each marked required, recommended or optional, and there is exactly
 * one primary action.
 *
 * The form only asks for what the backend can use. Device and network are
 * shown as a clearly labelled unsupported group rather than collected and
 * thrown away.
 */

import { useState } from "react";
import { api, ApiError } from "@/api/client";
import { useApp } from "@/stores/app";
import { useAsync } from "@/hooks/useAsync";
import type { ScoreResult } from "@/types";
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
  EmptyState,
  ErrorState,
  Field,
  PageHeader,
  ScrollTable,
  Section,
  Select,
  Td,
  Th,
  WaveSpinner,
} from "@/components/ui/primitives";
import { HoverPreview } from "@/components/ui/HoverPreview";
import { RiskResult } from "@/components/risk/RiskResult";

/** Ready-made transactions from the dataset the model was measured on. */
const EXAMPLES = [
  {
    id: "ring",
    label: "Looks like a ring",
    description:
      "A tiny payment to the merchant a detected ring runs through, from an "
      + "account with no history.",
    values: {
      transaction_id: "example_ring_1",
      amount: "0.95",
      customer_id: "S31249",
      merchant_id: "T1822",
      location: "L100",
      payment_type: "TP110",
    },
  },
  {
    id: "ordinary",
    label: "Ordinary payment",
    description:
      "A normal-sized payment from a returning customer through a busy channel.",
    values: {
      transaction_id: "example_normal_1",
      amount: "84.20",
      customer_id: "S1",
      merchant_id: "T2",
      location: "L1",
      payment_type: "TP1",
    },
  },
  {
    id: "new",
    label: "Everything brand new",
    description:
      "A customer, merchant, location and channel Spark has never seen. Shows "
      + "the cold-start floor.",
    values: {
      transaction_id: "example_cold_1",
      amount: "310.00",
      customer_id: "new_customer_001",
      merchant_id: "new_merchant_001",
      location: "new_location",
      payment_type: "new_channel",
    },
  },
];

const BLANK = {
  transaction_id: "",
  amount: "",
  customer_id: "",
  merchant_id: "",
  location: "",
  payment_type: "",
};

/** A small heading inside the form, with the requirement level attached. */
function Group({
  title,
  requirement,
  children,
}: {
  title: string;
  requirement: "Required" | "Recommended" | "Optional" | "Not supported";
  children: React.ReactNode;
}) {
  const tone = {
    Required: "high",
    Recommended: "medium",
    Optional: "neutral",
    "Not supported": "neutral",
  }[requirement] as "high" | "medium" | "neutral";

  return (
    <section className="border-t border-border pt-4 first:border-t-0 first:pt-0">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-[13px] font-semibold">{title}</h3>
        <Badge tone={tone}>{requirement}</Badge>
      </div>
      {children}
    </section>
  );
}

export function TestTransaction() {
  const { activeModel, mode, setMode, notify, health } = useApp();
  const [values, setValues] = useState({ ...BLANK });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const format = useAsync(() => api.datasets.format(), []);

  function set(key: keyof typeof BLANK, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => ({ ...e, [key]: "" }));
  }

  function validate(): boolean {
    const next: Record<string, string> = {};
    const amount = Number(values.amount);
    if (!values.amount.trim()) next.amount = "Enter an amount.";
    else if (Number.isNaN(amount)) next.amount = "That is not a number.";
    else if (amount < 0) next.amount = "An amount cannot be negative.";
    if (!values.customer_id.trim()) next.customer_id = "Enter a customer ID.";
    if (!values.merchant_id.trim()) next.merchant_id = "Enter a merchant ID.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function score() {
    if (!validate()) return;
    setBusy(true);
    setFailure(null);
    setResult(null);
    try {
      const scored = await api.risk.score({
        transaction_id: values.transaction_id || undefined,
        amount: Number(values.amount),
        customer_id: values.customer_id.trim(),
        merchant_id: values.merchant_id.trim(),
        location: values.location.trim() || undefined,
        payment_type: values.payment_type.trim() || undefined,
        mode,
        explain: true,
      });
      setResult(scored);
      notify({
        tone: scored.decision === "BLOCK" ? "warning" : "success",
        title: `Scored: ${scored.decision}`,
        body: `Risk ${scored.risk_score.toFixed(4)} on ${scored.transaction_id}.`,
      });
    } catch (err) {
      const apiError =
        err instanceof ApiError
          ? err
          : new ApiError(0, { message: "Something went wrong." });
      setFailure(apiError);
      if (apiError.body.fields) {
        setErrors(
          Object.fromEntries(
            apiError.body.fields.map((f) => [f.field, f.problem])
          )
        );
      }
    } finally {
      setBusy(false);
    }
  }

  const modelUnavailable = health && !health.model.available;

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Test Spark" }, { label: "Test Transaction" }]}
        title="Test a transaction"
        description="Describe one transaction and Spark will score it, decide what
          to do with it, and show you the evidence. No account needed."
        action={
          activeModel ? (
            <Badge tone="accent">
              {activeModel.name} {activeModel.version}
            </Badge>
          ) : null
        }
      />

      {modelUnavailable ? (
        <Callout tone="warning" title="No model is loaded">
          Nothing can be scored until a model has been trained on the server.
        </Callout>
      ) : null}

      {/*
        Two equal halves. A 440px form running far past the panel beside it was
        what made this page look lopsided, so the columns are even and the
        fields sit two to a row, which roughly halves the form height.
      */}
      <div className="grid items-start gap-6 xl:grid-cols-2">
        {/* Input */}
        <div className="space-y-4">
          <Section
            title="Transaction information"
            description="Start from an example, or fill these in yourself."
          >
            <Card>
              <div className="space-y-5 p-4 sm:p-5">
                {/* The examples belong with the form they fill in. */}
                <div className="flex flex-wrap gap-2 border-b border-border pb-4">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex.id}
                      type="button"
                      title={ex.description}
                      onClick={() => {
                        setValues({ ...ex.values });
                        setErrors({});
                      }}
                      className="interactive inline-flex h-8 items-center rounded-full
                        border border-border px-3 text-[12.5px] font-medium
                        text-text-muted hover:text-text"
                    >
                      {ex.label}
                    </button>
                  ))}
                </div>

                <Group title="Transaction" requirement="Required">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field
                      label="Amount"
                      type="number"
                      step="0.01"
                      min="0"
                      inputMode="decimal"
                      placeholder="49.90"
                      value={values.amount}
                      onChange={(e) => set("amount", e.target.value)}
                      error={errors.amount}
                    />
                    <Field
                      label="Transaction ID"
                      optional
                      placeholder="txn_000123"
                      value={values.transaction_id}
                      onChange={(e) => set("transaction_id", e.target.value)}
                      hint="Generated if you leave this blank."
                    />
                    <Field
                      label="Customer ID"
                      placeholder="cust_8813"
                      value={values.customer_id}
                      onChange={(e) => set("customer_id", e.target.value)}
                      error={errors.customer_id}
                      hint="Who paid."
                    />
                    <Field
                      label="Merchant ID"
                      placeholder="merch_204"
                      value={values.merchant_id}
                      onChange={(e) => set("merchant_id", e.target.value)}
                      error={errors.merchant_id}
                      hint="Who was paid."
                    />
                  </div>
                </Group>

                <details className="group border-t border-border pt-4">
                  <summary
                    className="flex cursor-pointer list-none items-center
                      justify-between gap-3 text-[13px] font-semibold"
                  >
                    More options
                    <span className="flex items-center gap-2 text-[12px] font-normal text-text-muted">
                      channel, location, threshold
                      <Icon.ChevronDown
                        size={15}
                        className="transition-transform group-open:rotate-180"
                      />
                    </span>
                  </summary>

                  <div className="mt-4 space-y-5">
                    <Group title="Payment route" requirement="Recommended">
                      <div className="grid gap-4 sm:grid-cols-2">
                        <Field
                          label="Payment channel"
                          optional
                          placeholder="upi"
                          value={values.payment_type}
                          onChange={(e) => set("payment_type", e.target.value)}
                          hint="For example card or upi."
                        />
                        <Field
                          label="Location"
                          optional
                          placeholder="IN-KA"
                          value={values.location}
                          onChange={(e) => set("location", e.target.value)}
                          hint="Any consistent code works."
                        />
                      </div>
                      <p className="mt-3 text-[12px] leading-relaxed text-text-faint">
                        Both are used as links in the graph. Leaving them blank is
                        allowed and does not change the score on its own.
                      </p>
                    </Group>

                    <Group title="Threshold setting" requirement="Optional">
                      <div className="grid gap-4 sm:grid-cols-2">
                        <Select
                          label="How careful should Spark be"
                          value={mode}
                          onChange={setMode}
                          options={[
                            { value: "balanced", label: "Balanced (lowest expected cost)" },
                            { value: "high_precision", label: "High precision" },
                            { value: "high_recall", label: "High recall" },
                          ]}
                        />
                        <p className="self-end pb-1.5 text-[12px] leading-relaxed text-text-faint">
                          Three sets of thresholds picked on validation data. They do
                          not change the model.
                        </p>
                      </div>
                      {mode === "high_precision" ? (
                        <div className="mt-3">
                          <Callout tone="warning" title="This setting does not transfer well">
                            Its threshold was chosen correctly on validation data, but
                            the score distribution moved afterwards, so almost nothing
                            reaches it in the later window.
                          </Callout>
                        </div>
                      ) : null}
                    </Group>

                    <Group title="Device and network" requirement="Not supported">
                      <HoverPreview
                        term="Device and network"
                        href={DOCS.dataset}
                        trigger={
                          <span className="cursor-help text-[12.5px] text-text-muted">
                            Not collected by this model
                          </span>
                        }
                      >
                        Device fingerprints and IP addresses are among the strongest
                        signals in real fraud work, but the data this model was trained
                        on does not contain them. Adding them would mean retraining,
                        not adding boxes to this form.
                      </HoverPreview>
                    </Group>
                  </div>
                </details>
              </div>

              <div className="border-t border-border p-4 sm:p-5">
                <ActionGroup align="between">
                  <Button
                    variant="primary"
                    onClick={() => void score()}
                    loading={busy}
                    disabled={!!modelUnavailable}
                    icon={<Icon.Play size={15} />}
                  >
                    Run risk check
                  </Button>
                  <Button
                    onClick={() => {
                      setValues({ ...BLANK });
                      setErrors({});
                      setResult(null);
                      setFailure(null);
                    }}
                  >
                    Clear
                  </Button>
                </ActionGroup>
              </div>
            </Card>
          </Section>
        </div>

        {/* Result */}
        <div className="min-w-0">
          <Section
            title="Risk decision"
            description="What Spark decided, and the evidence behind it."
            action={
              result ? (
                <CopyButton
                  value={JSON.stringify(result, null, 2)}
                  label="Copy response"
                />
              ) : null
            }
          >
          {busy ? (
            <Card>
              <WaveSpinner label="Building features, running both models, and writing the explanation" />
            </Card>
          ) : failure ? (
            <ErrorState
              title="Could not score that"
              message={failure.message}
              fix={failure.body.fix}
              onRetry={() => void score()}
            />
          ) : result ? (
            <RiskResult result={result} />
          ) : (
            <Card>
              <EmptyState
                icon={<Icon.Transaction size={28} />}
                title="Nothing scored yet"
                description="Fill in the transaction, or pick an example, then run
                  the risk check. The decision, the reasons behind it and the
                  earlier transactions Spark linked it to will appear here."
              />
            </Card>
          )}
          </Section>
        </div>
      </div>

      {/* Full width, under both columns: it is a wide table and it is
          reference rather than part of the task. */}
      {!result && format.data ? (
        <WhatDataCanIProvide columns={format.data.columns} />
      ) : null}
    </div>
  );
}

/**
 * The field reference, generated from the same table the validator uses.
 *
 * Kept compact: it is a reference for someone preparing data, not something to
 * read before every run, so it is a plain table with no surrounding essay.
 */
export function WhatDataCanIProvide({
  columns,
}: {
  columns: { column: string; label: string; requirement: string; why: string }[];
}) {
  const tone = (r: string) =>
    r === "required" ? "high" : r === "recommended" ? "medium" : "neutral";
  return (
    <Card>
      <CardHeader
        title="What data can I provide"
        description="Only these fields exist in the model Spark runs."
        action={
          <HoverPreview
            term="Data coverage"
            href={DOCS.dataCoverage.href}
            trigger={
              <span className="cursor-help text-[12px] text-text-muted">
                Coverage
              </span>
            }
          >
            {DOCS.dataCoverage.text}
          </HoverPreview>
        }
      />
      <ScrollTable>
        <thead>
          <tr>
            <Th>Data</Th>
            <Th>Needed</Th>
            <Th>Why it helps</Th>
          </tr>
        </thead>
        <tbody>
          {columns.map((c) => (
            <tr key={c.column}>
              <Td>
                <span className="font-medium">{c.label}</span>
              </Td>
              <Td>
                <Badge tone={tone(c.requirement) as "high" | "medium" | "neutral"}>
                  {c.requirement}
                </Badge>
              </Td>
              <Td className="text-text-muted">{c.why}</Td>
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Card>
  );
}
