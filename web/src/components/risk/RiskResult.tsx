/**
 * Everything shown after a transaction is scored.
 *
 * The rule for this whole file: nothing is displayed that the backend did not
 * return. Where a section has no data, it says what is missing and why, rather
 * than filling the space.
 */

import type { ReactNode } from "react";
import type { ScoreResult } from "@/types";
import {
  CHANNEL_HELP,
  CHANNEL_LABELS,
  RELATION_LABELS,
  ms,
  money,
  percent,
  ratio,
} from "@/lib/format";
import { Icon } from "@/components/ui/icons";
import {
  Badge,
  Callout,
  Card,
  CardHeader,
  DecisionBadge,
  Explained,
  Meter,
  RiskBadge,
  ScrollTable,
  Section,
  Td,
  Th,
} from "@/components/ui/primitives";
import { Tabs } from "@/components/ui/Tabs";
import { HoverPreview } from "@/components/ui/HoverPreview";
import { DOCS } from "@/config/docs";
import { cn } from "@/lib/utils";

/**
 * The result, most important thing first.
 *
 * A scored transaction produces a great deal: four component scores, a SHAP
 * explanation, every backward link in the graph, a coverage table and possibly
 * a ring. Showing all of it at once buried the one line that answers the
 * question, so the decision and the single strongest reason come first, and
 * the rest sits in tabs a click away. Nothing was removed.
 */
export function RiskResult({ result }: { result: ScoreResult }) {
  const linked = Object.entries(result.graph_evidence).filter(
    ([, links]) => links.length > 0
  );

  return (
    <div className="space-y-4" data-tour="risk-result">
      <Headline result={result} />
      <LeadReason result={result} />

      <Tabs
        items={[
          {
            id: "explanation",
            label: "Explanation",
            content: (
              <div className="grid gap-4 lg:grid-cols-2">
                <WhyPanel result={result} />
                <ChannelPanel result={result} />
              </div>
            ),
          },
          {
            id: "relationships",
            label: "Relationships",
            badge: linked.length ? (
              <Badge tone="neutral">{linked.length}</Badge>
            ) : undefined,
            content: <GraphEvidence result={result} />,
          },
          {
            id: "coverage",
            label: "Data coverage",
            content: <DataCoverage result={result} />,
          },
          ...(result.related_ring
            ? [
                {
                  id: "ring",
                  label: "Abuse ring",
                  badge: <Badge tone="medium">1</Badge>,
                  content: <RingPanel result={result} />,
                },
              ]
            : []),
          {
            id: "processing",
            label: "Processing",
            content: <ProcessingSteps result={result} />,
          },
        ]}
      />
    </div>
  );
}

/**
 * The single strongest reason, stated before any of the detail.
 *
 * It is the first entry the backend returned, which is the largest SHAP
 * contribution. If no explanation was requested there is nothing to lead with,
 * and the block says so rather than inventing a summary.
 */
function LeadReason({ result }: { result: ScoreResult }) {
  const lead = result.reasons[0];
  if (!lead) return null;

  return (
    <Section title="Why this result">
      <div className="flex items-start gap-3 rounded-[10px] border border-border
        bg-surface px-4 py-3.5">
        <span
          className={cn(
            "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full",
            "text-[14px] font-semibold",
            lead.direction === "increases"
              ? "bg-high-soft text-high"
              : "bg-low-soft text-low"
          )}
          aria-hidden="true"
        >
          {lead.direction === "increases" ? "+" : "-"}
        </span>
        <div className="min-w-0">
          <p className="text-[13.5px] leading-snug">{lead.text}</p>
          <p className="mt-1 text-[12px] text-text-muted">
            This moved the score more than anything else.
            {result.reasons.length > 1
              ? ` ${result.reasons.length - 1} more ${
                  result.reasons.length === 2 ? "factor is" : "factors are"
                } in the Explanation tab.`
              : ""}
          </p>
        </div>
      </div>
    </Section>
  );
}

/**
 * Risk, decision, score, model and time, in one row.
 *
 * These five are what someone reads first and often all they need. The terms
 * that carry a real caveat carry a hover definition with them, so the caveat
 * travels with the number instead of sitting in a paragraph further down.
 */
function Headline({ result }: { result: ScoreResult }) {
  const tone =
    result.risk_band === "HIGH"
      ? "border-high/30 bg-high-soft"
      : result.risk_band === "MEDIUM"
        ? "border-medium/30 bg-medium-soft"
        : "border-low/30 bg-low-soft";

  const facts: { label: string; value: ReactNode; doc?: { href: string; text: string } }[] = [
    {
      label: "Risk level",
      value: <RiskBadge band={result.risk_band} />,
      doc: DOCS.riskScore,
    },
    {
      label: "Decision",
      value: <DecisionBadge decision={result.decision} />,
    },
    {
      label: "Risk score",
      value: (
        <span className="text-[20px] font-semibold tabular-nums">
          {ratio(result.risk_score)}
        </span>
      ),
      doc: DOCS.riskScore,
    },
    {
      label: "Model",
      value: (
        <span className="font-mono text-[12.5px]">{result.model_version}</span>
      ),
      doc: DOCS.modelVersion,
    },
    {
      label: "Processing",
      value: (
        <span className="text-[13px] tabular-nums">{ms(result.latency_ms)}</span>
      ),
      doc: DOCS.latency,
    },
  ];

  return (
    <div className={cn("enter rounded-[--radius] border p-4 sm:p-5", tone)}>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
        {facts.map((fact) => (
          <div key={fact.label} className="min-w-0">
            <dt className="text-[11.5px] font-medium uppercase tracking-wider text-text-muted">
              {fact.doc ? (
                <HoverPreview
                  term={fact.label}
                  href={fact.doc.href}
                  trigger={
                    <span>{fact.label}</span>
                  }
                >
                  {fact.doc.text}
                </HoverPreview>
              ) : (
                fact.label
              )}
            </dt>
            <dd className="mt-1.5 flex items-center">{fact.value}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-5 border-t border-black/5 pt-4 dark:border-white/5">
        <Meter
          value={result.risk_score}
          tone={
            result.risk_band === "HIGH"
              ? "high"
              : result.risk_band === "MEDIUM"
                ? "medium"
                : "low"
          }
          label={`Risk score ${ratio(result.risk_score)} out of 1`}
        />
        <div className="mt-1.5 flex flex-wrap justify-between gap-x-4 text-[11px] text-text-muted">
          <span>0 safe</span>
          <span>review at {ratio(result.review_threshold, 3)}</span>
          <span>block at {ratio(result.block_threshold, 3)}</span>
          <span>1 risky</span>
        </div>
      </div>

      {result.path === "COLD_START" ? (
        <div className="mt-4">
          <HoverPreview
            term="Cold start"
            href={DOCS.coldStart.href}
            trigger={
              <Badge tone="neutral">cold start</Badge>
            }
          >
            {DOCS.coldStart.text}
          </HoverPreview>
        </div>
      ) : null}

      {result.notes.length ? (
        <ul className="mt-4 space-y-1.5">
          {result.notes.map((n) => (
            <li key={n} className="flex items-start gap-2 text-[12px] text-text-muted">
              <Icon.Info size={13} className="mt-0.5 shrink-0" />
              {n}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** The stages the backend actually timed, in the order it ran them. */
function ProcessingSteps({ result }: { result: ScoreResult }) {
  const total = result.stages.reduce((sum, s) => sum + s.ms, 0);
  return (
    <Card>
      <CardHeader
        title="What Spark did"
        description="The steps the server ran for this transaction, with how long
          each one took."
      />
      <ol className="divide-y divide-border">
        {result.stages.map((stage) => (
          <li key={stage.name} className="flex items-center gap-3 px-5 py-2.5">
            <Icon.CheckCircle size={15} className="shrink-0 text-low" />
            <span className="min-w-0 flex-1 text-[13px]">{stage.name}</span>
            <span className="w-24 shrink-0">
              <Meter value={total ? stage.ms / total : 0} />
            </span>
            <span className="w-16 shrink-0 text-right text-[12px] tabular-nums text-text-muted">
              {stage.ms.toFixed(2)} ms
            </span>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function WhyPanel({ result }: { result: ScoreResult }) {
  return (
    <Card>
      <CardHeader
        title="Why did Spark decide this"
        description="The features that moved the score most, worked out with SHAP
          over the tree model. These contributed to the score. They are not proof
          that anything is fraud."
      />
      {result.reasons.length === 0 ? (
        <p className="px-5 py-6 text-[13px] text-text-muted">
          No explanation was requested for this run.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {result.reasons.map((r, i) => (
            <li key={`${r.feature}-${i}`} className="flex items-start gap-3 px-5 py-3">
              <span
                className={cn(
                  "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold",
                  r.direction === "increases"
                    ? "bg-high-soft text-high"
                    : "bg-low-soft text-low"
                )}
                aria-hidden="true"
              >
                {r.direction === "increases" ? "+" : "-"}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] leading-snug">{r.text}</p>
                <p className="mt-0.5 text-[11.5px] text-text-faint">
                  {r.direction === "increases" ? "Pushed the score up" : "Pulled the score down"}
                  {r.contribution
                    ? ` by ${Math.abs(r.contribution).toFixed(3)} in log-odds`
                    : ""}
                  {r.feature !== "cold_start" ? ` (${r.feature})` : ""}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ChannelPanel({ result }: { result: ScoreResult }) {
  const entries = Object.entries(result.channel_scores);
  return (
    <Card>
      <CardHeader
        title="The four scores behind the number"
        description="Spark runs four separate scores and blends them with weights
          that were searched on validation data, not chosen by hand."
      />
      <ul className="divide-y divide-border">
        {entries.map(([channel, score]) => {
          const share = result.channel_attribution[channel];
          return (
            <li key={channel} className="px-5 py-3">
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[13px] font-medium">
                  <Explained
                    term={CHANNEL_LABELS[channel] ?? channel}
                    meaning={CHANNEL_HELP[channel] ?? ""}
                  />
                </span>
                <span className="text-[13px] tabular-nums">{ratio(score)}</span>
              </div>
              <div className="mt-2">
                <Meter value={score} label={`${channel} score`} />
              </div>
              {typeof share === "number" ? (
                <p className="mt-1.5 text-[11.5px] text-text-faint">
                  {percent(share, 0)} of the final score came from this
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/**
 * The relationships the graph actually used.
 *
 * Every link shown here points at an earlier transaction. Nothing later in
 * time can appear, because the graph only ever builds backward edges.
 */
function GraphEvidence({ result }: { result: ScoreResult }) {
  const relations = Object.entries(result.graph_evidence).filter(
    ([, links]) => links.length > 0
  );

  return (
    <Card data-tour="graph-evidence">
      <CardHeader
        title="What this transaction is connected to"
        description="Earlier transactions that share a customer, merchant,
          location or payment channel. Spark only ever looks backwards, so
          nothing that happened after this transaction is used."
      />
      {relations.length === 0 ? (
        <div className="px-5 py-6">
          <p className="text-[13px] text-text-muted">
            No earlier transactions share any of this transaction's details.
          </p>
          <p className="mt-1.5 text-[12.5px] text-text-faint">
            That is normal for a completely new customer and merchant. The graph
            model still runs, but it has no neighbours to learn from, so the
            score leans on the other three signals.
          </p>
        </div>
      ) : (
        <>
          <div className="border-b border-border px-5 py-4">
            <EntityDiagram result={result} relations={relations.map(([r]) => r)} />
            <p className="mt-3 text-[11.5px] leading-relaxed text-text-faint">
              A detail worth knowing: a value shared by a very large number of
              transactions creates no link at all. One location in this dataset
              covers tens of thousands of payments, and connecting all of them
              would only say "both of these are transactions". So a busy location
              or channel can show plenty of history in the table below and still
              show no link here.
            </p>
          </div>
          {relations.map(([relation, links]) => (
            <div key={relation}>
              <p className="border-b border-border bg-bg-subtle px-5 py-2 text-[12px] font-medium">
                {RELATION_LABELS[relation] ?? relation}
                <span className="ml-2 font-normal text-text-faint">
                  {links.length} earlier {links.length === 1 ? "transaction" : "transactions"}
                </span>
              </p>
              <ScrollTable>
                <thead>
                  <tr>
                    <Th>Previous transaction</Th>
                    <Th>Customer</Th>
                    <Th>Merchant</Th>
                    <Th align="right">Amount</Th>
                    <Th>Outcome</Th>
                  </tr>
                </thead>
                <tbody>
                  {links.map((link) => (
                    <tr key={link.transaction_id}>
                      <Td>
                        <span className="font-mono text-[12px]">{link.transaction_id}</span>
                      </Td>
                      <Td className="font-mono text-[12px]">{link.source}</Td>
                      <Td className="font-mono text-[12px]">{link.target}</Td>
                      <Td align="right">{money(link.amount)}</Td>
                      <Td>
                        {link.outcome === "fraud" ? (
                          <Badge tone="high">confirmed fraud</Badge>
                        ) : link.outcome === "legitimate" ? (
                          <Badge tone="low">confirmed normal</Badge>
                        ) : (
                          <span className="text-[12px] text-text-faint">
                            never confirmed
                          </span>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </ScrollTable>
            </div>
          ))}
        </>
      )}
    </Card>
  );
}

/** A small diagram of which links exist. Only drawn for relations that fired. */
function EntityDiagram({
  result,
  relations,
}: {
  result: ScoreResult;
  relations: string[];
}) {
  const nodes = [
    { key: "Source", label: "Customer", value: result.customer_id },
    { key: "Target", label: "Merchant", value: result.merchant_id },
    { key: "Location", label: "Location", value: result.location },
    { key: "Type", label: "Payment channel", value: result.payment_type },
  ];

  return (
    <div className="flex flex-col items-stretch gap-2.5 sm:flex-row sm:items-center">
      <div className="rounded-[8px] border border-accent/30 bg-accent-soft px-3 py-2">
        <p className="text-[10.5px] font-semibold uppercase tracking-wider text-accent">
          This transaction
        </p>
        <p className="font-mono text-[12px]">{result.transaction_id}</p>
      </div>
      <Icon.ArrowRight size={16} className="hidden shrink-0 text-text-faint sm:block" />
      <Icon.ArrowDown size={16} className="shrink-0 self-center text-text-faint sm:hidden" />
      <ul className="grid flex-1 gap-2 sm:grid-cols-2">
        {nodes.map((node) => {
          const linked = relations.includes(node.key);
          return (
            <li
              key={node.key}
              className={cn(
                "rounded-[8px] border px-3 py-2",
                linked ? "border-border-strong bg-surface" : "border-dashed border-border"
              )}
            >
              <p className="text-[10.5px] font-semibold uppercase tracking-wider text-text-faint">
                {node.label}
              </p>
              <p className="truncate font-mono text-[12px]">{node.value}</p>
              <p className="mt-0.5 text-[11px] text-text-muted">
                {linked ? "linked to earlier transactions" : "no link"}
              </p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * How much history Spark actually had.
 *
 * Fields the source data has never carried, like a device fingerprint or an IP
 * address, are listed as not supported rather than quietly left out.
 */
function DataCoverage({ result }: { result: ScoreResult }) {
  const history = Object.entries(result.entity_history);

  const level = (n: number) =>
    n === 0 ? "None" : n < 3 ? "Limited" : n < 25 ? "Some" : "Good";

  const tone = (n: number) =>
    n === 0 ? "high" : n < 3 ? "medium" : "low";

  return (
    <Card>
      <CardHeader
        title="What Spark knew"
        description="How much history each part of this transaction had before it
          was scored."
      />
      <ScrollTable>
        <thead>
          <tr>
            <Th>Information</Th>
            <Th>Coverage</Th>
            <Th align="right">Earlier transactions</Th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <Td>Transaction details</Td>
            <Td>
              <Badge tone="low">Available</Badge>
            </Td>
            <Td align="right">supplied by you</Td>
          </tr>
          {history.map(([key, h]) => (
            <tr key={key}>
              <Td className="capitalize">{h.role} history</Td>
              <Td>
                <Badge tone={tone(h.prior_transactions) as "low" | "medium" | "high"}>
                  {level(h.prior_transactions)}
                </Badge>
              </Td>
              <Td align="right">{h.prior_transactions.toLocaleString()}</Td>
            </tr>
          ))}
          <tr>
            <Td>Device history</Td>
            <Td>
              <Badge tone="neutral">Not supported</Badge>
            </Td>
            <Td align="right" className="text-text-faint">
              no device field in the data
            </Td>
          </tr>
          <tr>
            <Td>IP and network history</Td>
            <Td>
              <Badge tone="neutral">Not supported</Badge>
            </Td>
            <Td align="right" className="text-text-faint">
              no IP field in the data
            </Td>
          </tr>
        </tbody>
      </ScrollTable>
      <div className="px-5 py-4">
        <Callout tone="info">
          A single transaction can be scored, but it comes with limited history and
          few relationships. The graph and abuse-ring parts of Spark get much more
          useful once several related transactions exist. Device and IP are two of
          the strongest ring signals in real fraud work, and the data Spark was
          trained on does not have them, so it does not pretend to use them.
        </Callout>
      </div>
    </Card>
  );
}

function RingPanel({ result }: { result: ScoreResult }) {
  const ring = result.related_ring!;
  return (
    <Card>
      <CardHeader
        title="A detected ring involves this merchant"
        description={`Spark's ring detector previously flagged a group that this
          transaction's ${ring.matched_on ?? "merchant"} belongs to. That is not
          the same as saying this transaction is part of it.`}
        action={<Badge tone="medium">related</Badge>}
      />
      <div className="grid gap-x-6 gap-y-3 px-5 py-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Ring", ring.cluster_id],
          ["Accounts", ring.n_accounts.toLocaleString()],
          ["Transactions", ring.n_transactions.toLocaleString()],
          ["Ring score", ratio(ring.risk_score, 3)],
        ].map(([label, value]) => (
          <div key={label}>
            <p className="text-[11.5px] text-text-muted">{label}</p>
            <p className="font-mono text-[13px]">{value}</p>
          </div>
        ))}
      </div>
      {ring.reasons?.length ? (
        <ul className="border-t border-border px-5 py-4 space-y-1.5">
          {ring.reasons.slice(0, 4).map((r) => (
            <li key={r} className="flex items-start gap-2 text-[12.5px] text-text-muted">
              <Icon.Ring size={13} className="mt-0.5 shrink-0 text-medium" />
              {r}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="border-t border-border px-5 py-3 text-[11.5px] leading-relaxed text-text-faint">
        Ring detection reads no fraud labels. It groups transactions by shared
        merchant, channel and location inside a time window, then scores each
        group on how many separate accounts it uses, how tightly packed it is,
        and how similar the amounts are.
      </p>
    </Card>
  );
}
