/**
 * Detected abuse rings, laid out as an investigation rather than a report.
 *
 * The page used to show every ring's full detail stacked down the page, which
 * meant the interesting one was somewhere past the fold behind four others.
 * Now the list is a table you scan, and picking a row opens the evidence for
 * that one ring beside it. Nothing is hidden: everything the detector returned
 * is still here, in the panel for the ring it belongs to.
 *
 * Ring detection reads no fraud labels at all. Precision is only checked
 * against the real outcomes afterwards, which is what makes it a fair number
 * rather than a circular one.
 */

import { useMemo, useState } from "react";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { money, percent, ratio } from "@/lib/format";
import { DOCS } from "@/config/docs";
import { Icon } from "@/components/ui/icons";
import {
  Badge,
  Button,
  Card,
  CopyButton,
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
import { Drawer } from "@/components/ui/Tabs";
import { CircuitBoard, type CircuitNodeType } from "@/components/ui/CircuitBoard";
import { DefinitionList, FilterBar, MetricStrip } from "@/components/ui/Layout";
import { HoverPreview } from "@/components/ui/HoverPreview";
import type { RingSummary } from "@/types";

/**
 * The five signals the detector scores a group on.
 *
 * These are the measured separations from the evaluation, not guesses about
 * what fraud looks like. They describe the detector, so they live behind a tab
 * rather than above the rings themselves.
 */
const SIGNALS = [
  {
    name: "Accounts per transaction",
    plain: "How many different accounts are involved, compared with how many "
      + "transactions there are. Close to 1 means almost every payment came "
      + "from a different account.",
    fraud: "0.84",
    normal: "0.38",
  },
  {
    name: "How tightly packed in time",
    plain: "Whether the activity happened in a short burst or was spread out.",
    fraud: "0.029",
    normal: "0.008",
  },
  {
    name: "Number of accounts",
    plain: "How many separate accounts the group uses.",
    fraud: "58",
    normal: "13",
  },
  {
    name: "How similar the amounts are",
    plain: "Whether the payments are all nearly the same size.",
    fraud: "more similar",
    normal: "more varied",
  },
  {
    name: "Average amount",
    plain: "How big the typical payment is. Very small and very similar amounts "
      + "are what card testing looks like.",
    fraud: "4.67",
    normal: "59.81",
  },
];

type RiskFilter = "all" | "high" | "medium";

export function AbuseRings() {
  const rings = useAsync(() => api.metrics.rings(), []);
  const [selected, setSelected] = useState<RingSummary | null>(null);
  const [risk, setRisk] = useState<RiskFilter>("all");
  const [channel, setChannel] = useState("all");

  // Memoised so the derived lists below do not recompute on every render just
  // because the fallback array is a new object each time.
  const all = useMemo(() => rings.data?.top_rings ?? [], [rings.data]);

  const channels = useMemo(() => {
    const set = new Set<string>();
    for (const ring of all) for (const c of ring.channels ?? []) set.add(c);
    return [...set].sort();
  }, [all]);

  const visible = useMemo(
    () =>
      all.filter((ring) => {
        if (risk === "high" && ring.risk_score < 0.8) return false;
        if (risk === "medium" && (ring.risk_score >= 0.8 || ring.risk_score < 0.5))
          return false;
        if (channel !== "all" && !(ring.channels ?? []).includes(channel))
          return false;
        return true;
      }),
    [all, risk, channel]
  );

  if (rings.loading) {
    return (
      <div className="space-y-6">
        <PageHeader
          breadcrumb={[{ label: "Analysis" }, { label: "Abuse Rings" }]}
          title="Abuse rings"
        />
        <Card className="p-6">
          <Spinner label="Reading ring detection results" />
        </Card>
      </div>
    );
  }
  if (rings.error) {
    return (
      <ErrorState
        title="No ring results to show"
        message={rings.error.message}
        fix={rings.error.body.fix}
        onRetry={rings.reload}
      />
    );
  }
  if (!rings.data) return null;

  const data = rings.data;
  const test = data.test;
  const activeFilters = (risk !== "all" ? 1 : 0) + (channel !== "all" ? 1 : 0);

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Analysis" }, { label: "Abuse Rings" }]}
        title="Abuse rings"
        description="A single suspicious payment is the easy case. The harder one
          is a group of fake accounts spending small amounts through the same
          merchant, where each payment looks fine on its own."
        action={
          <HoverPreview
            term="Abuse ring"
            href={DOCS.abuseRing.href}
            trigger={
              <Button size="sm">What is a ring</Button>
            }
          >
            {DOCS.abuseRing.text}
          </HoverPreview>
        }
      />

      <MetricStrip
        items={[
          {
            label: "Rings alerted",
            value: test.rings_alerted?.toLocaleString(),
            sub: `out of ${data.n_candidate_rings?.toLocaleString()} candidates`,
          },
          {
            label: "Precision",
            value: ratio(test.precision),
            sub: "of transactions inside those rings",
            doc: DOCS.precision,
          },
          {
            label: "Recall of test fraud",
            value: ratio(test.recall_of_test_fraud),
            sub: "of all fraud in the window",
            doc: DOCS.recall,
          },
          {
            label: "Lift over base rate",
            value: `${ratio(test.lift_over_base, 2)}x`,
            sub: "versus picking at random",
          },
        ]}
      />

      <Section
        title="Detected rings"
        description={`The highest-scoring groups, alerted at a threshold of
          ${data.threshold_selected_on_validation} chosen on validation data.
          Select a ring to see its evidence.`}
        action={
          visible.length ? (
            <span className="text-[12px] text-text-muted">
              {visible.length} of {all.length} shown
            </span>
          ) : null
        }
      >
        <FilterBar count={activeFilters}>
          <Select
            label="Risk"
            value={risk}
            onChange={(v) => setRisk(v as RiskFilter)}
            options={[
              { value: "all", label: "Any risk" },
              { value: "high", label: "0.80 and above" },
              { value: "medium", label: "0.50 to 0.80" },
            ]}
          />
          <Select
            label="Channel"
            value={channel}
            onChange={setChannel}
            options={[
              { value: "all", label: "Any channel" },
              ...channels.map((c) => ({ value: c, label: c })),
            ]}
          />
        </FilterBar>

        {visible.length ? (
          <Card>
            <ScrollTable>
              <thead>
                <tr>
                  <Th>Ring</Th>
                  <Th align="right">Accounts</Th>
                  <Th align="right">Transactions</Th>
                  <Th align="right">Value</Th>
                  <Th align="right">Risk</Th>
                  <Th>Really fraud</Th>
                  <Th>Merchants</Th>
                </tr>
              </thead>
              <tbody>
                {visible.map((ring) => (
                  <tr
                    key={ring.cluster_id}
                    onClick={() => setSelected(ring)}
                    className="interactive cursor-pointer"
                  >
                    <Td>
                      <span className="flex items-center gap-2">
                        <Icon.Ring size={14} className="shrink-0 text-medium" />
                        <span className="font-mono text-[12px] font-medium">
                          {ring.cluster_id}
                        </span>
                      </span>
                    </Td>
                    <Td align="right">{ring.n_accounts?.toLocaleString()}</Td>
                    <Td align="right">{ring.n_transactions?.toLocaleString()}</Td>
                    <Td align="right">{money(ring.total_value, 0)}</Td>
                    <Td align="right">{ratio(ring.risk_score, 3)}</Td>
                    <Td>
                      {typeof ring.precision === "number" ? (
                        <Badge tone={ring.precision > 0.8 ? "low" : "medium"}>
                          {percent(ring.precision, 0)}
                        </Badge>
                      ) : (
                        <span className="text-text-faint">not checked</span>
                      )}
                    </Td>
                    <Td className="max-w-[180px] truncate font-mono text-[12px]">
                      {ring.merchants?.join(", ")}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </ScrollTable>
          </Card>
        ) : (
          <Card>
            <EmptyState
              title={all.length ? "No ring matches those filters" : "No rings were alerted"}
              description={
                all.length
                  ? "Widen the risk range or clear the channel filter."
                  : "The detector found no group above the alert threshold in this window."
              }
              action={
                all.length ? (
                  <Button
                    size="sm"
                    onClick={() => {
                      setRisk("all");
                      setChannel("all");
                    }}
                  >
                    Clear filters
                  </Button>
                ) : undefined
              }
            />
          </Card>
        )}
      </Section>

      {/*
        Everything below is reference material about the detector rather than
        a finding. It used to sit in four tabs under the rings, which made the
        page look like a manual. One disclosure, closed by default.
      */}
      <details className="group rounded-[10px] border border-border bg-surface">
        <summary
          className="flex cursor-pointer list-none items-center justify-between
            gap-3 px-4 py-3 text-[13px] font-medium"
        >
          How ring detection works
          <Icon.ChevronDown
            size={16}
            className="shrink-0 text-text-muted transition-transform
              group-open:rotate-180"
          />
        </summary>

        <div className="space-y-5 border-t border-border px-4 py-4">
          <p className="text-[12.5px] leading-relaxed text-text-muted">
            {data.how_it_works}
          </p>

          <Section
            title="What makes a group look like a ring"
            description="Five signals, measured on real data before any of them
              was used."
          >
            <ScrollTable>
              <thead>
                <tr>
                  <Th>Signal</Th>
                  <Th align="right">Ring</Th>
                  <Th align="right">Normal traffic</Th>
                </tr>
              </thead>
              <tbody>
                {SIGNALS.map((s) => (
                  <tr key={s.name}>
                    <Td>
                      <HoverPreview
                        term={s.name}
                        trigger={<span className="font-medium">{s.name}</span>}
                      >
                        {s.plain}
                      </HoverPreview>
                    </Td>
                    <Td align="right">{s.fraud}</Td>
                    <Td align="right">{s.normal}</Td>
                  </tr>
                ))}
              </tbody>
            </ScrollTable>
          </Section>

          <Section
            title="Coverage on the held-out test"
            description={`Alerted at ${data.threshold_selected_on_validation},
              a threshold swept on validation data and chosen on F1.`}
          >
            <DefinitionList
              items={[
                {
                  label: "Confirmed transactions inside alerted rings",
                  value: money(test.confirmed_transactions_covered, 0),
                },
                {
                  label: "Of those, confirmed fraud",
                  value: money(test.confirmed_fraud_captured, 0),
                },
                {
                  label: "Fraud rate in the test window",
                  value: ratio(test.test_base_rate),
                },
              ]}
            />
            <p className="text-[11.5px] leading-relaxed text-text-faint">
              Ring detection never reads a fraud label, so it is unaffected by
              how long confirmations take to arrive. That is why it runs
              alongside the scoring models.
            </p>
          </Section>
        </div>
      </details>

      <RingDrawer ring={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

/**
 * Everything the detector returned about one ring.
 *
 * The graph draws only what the backend actually reported: how many accounts
 * fanned into which merchants over which channels. Individual account IDs are
 * not in the ring summary, so the accounts appear as one counted node rather
 * than as invented identifiers.
 */
function RingDrawer({
  ring,
  onClose,
}: {
  ring: RingSummary | null;
  onClose: () => void;
}) {
  if (!ring) return null;

  const window_ =
    ring.last_seen > ring.first_seen
      ? `${(ring.last_seen - ring.first_seen).toLocaleString()} between first and last`
      : "all within one step";

  return (
    <Drawer
      open={!!ring}
      onClose={onClose}
      title={ring.cluster_id}
      description={`${ring.n_accounts?.toLocaleString()} accounts across
        ${ring.n_transactions?.toLocaleString()} transactions`}
      footer={
        <div className="flex items-center justify-between gap-3">
          <span className="text-[12px] text-text-muted">
            Detected without reading any fraud label.
          </span>
          <CopyButton value={ring.cluster_id} label="Copy ring ID" />
        </div>
      }
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="medium">score {ratio(ring.risk_score, 3)}</Badge>
          <Badge tone="neutral">confidence {ratio(ring.confidence, 2)}</Badge>
          {typeof ring.precision === "number" ? (
            <Badge tone={ring.precision > 0.8 ? "low" : "medium"}>
              {percent(ring.precision, 0)} really fraud
            </Badge>
          ) : null}
        </div>

        <Section title="Why was this identified">
          {ring.reasons?.length ? (
            <ul className="space-y-2">
              {ring.reasons.map((r) => (
                <li
                  key={r}
                  className="flex items-start gap-2.5 rounded-[8px] border
                    border-border bg-bg-subtle px-3 py-2 text-[12.5px]
                    leading-snug text-text-muted"
                >
                  <Icon.Check size={14} className="mt-0.5 shrink-0 text-medium" />
                  {r}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12.5px] text-text-muted">
              The detector returned no written reasons for this group.
            </p>
          )}
        </Section>

        <Section title="Relationships">
          <RingGraph ring={ring} />
        </Section>

        {/*
          Only what the table row could not carry. The accounts, transactions,
          value and merchants are all columns you clicked through, so repeating
          them here would be the same data in a second form.
        */}
        <Section title="Detail">
          <DefinitionList
            columns={1}
            items={[
              {
                label: "Channels",
                value: (
                  <span className="font-mono text-[12px]">
                    {ring.channels?.join(", ") || "none reported"}
                  </span>
                ),
              },
              {
                label: "Locations",
                value: (
                  <span className="font-mono text-[12px]">
                    {ring.locations?.join(", ") || "none reported"}
                  </span>
                ),
              },
              { label: "Median amount", value: money(ring.median_amount) },
              { label: "Time window", value: window_ },
            ]}
          />
          <p className="text-[11.5px] leading-relaxed text-text-faint">
            The individual transactions are not listed because the ring report
            summarises them rather than enumerating them. Score a transaction on
            the Test Transaction page to see whether it links to this ring.
          </p>
        </Section>
      </div>
    </Drawer>
  );
}

/**
 * The shape of the finding, as something you can point at.
 *
 * Many accounts converging on few merchants through few channels is the whole
 * of what the detector found, and it reads far faster as a diagram than as a
 * list of counts. Every node here is a number or a name the backend returned:
 * the accounts are one counted node because the ring summary reports a count
 * and not identifiers, so inventing individual accounts to fill the board
 * would be inventing evidence.
 */
function RingGraph({ ring }: { ring: RingSummary }) {
  const merchants = (ring.merchants ?? []).slice(0, 3);
  const channels = (ring.channels ?? []).slice(0, 3);

  // The board positions nodes in pixels, not percentages, so these are laid
  // out against its real width and height. Three rows: the accounts that fan
  // in, the merchants they converge on, and the channels underneath.
  const W = 430;
  const H = 250;
  const spread = (count: number, i: number) =>
    count <= 1 ? W / 2 : 70 + ((W - 140) / (count - 1)) * i;

  const nodes: CircuitNodeType[] = [
    {
      id: "accounts",
      x: W / 2,
      y: 40,
      label: `${ring.n_accounts?.toLocaleString()} accounts`,
      status: "active",
      size: "md",
    },
    ...merchants.map((m, i) => ({
      id: `m${i}`,
      x: spread(merchants.length, i),
      y: 130,
      label: m,
      status: "processing" as const,
      size: "sm" as const,
    })),
    ...channels.map((c, i) => ({
      id: `c${i}`,
      x: spread(channels.length, i),
      y: 210,
      label: c,
      status: "inactive" as const,
      size: "sm" as const,
    })),
  ];

  const connections = [
    ...merchants.map((_, i) => ({ from: "accounts", to: `m${i}`, animated: true })),
    ...merchants.flatMap((_, mi) =>
      channels.map((_, ci) => ({ from: `m${mi}`, to: `c${ci}`, animated: false }))
    ),
  ];

  const fanIn = Number.isFinite(ring.fan_in) && ring.fan_in > 0 ? ring.fan_in : null;
  const truncated =
    (ring.merchants?.length ?? 0) > 3 || (ring.channels?.length ?? 0) > 3;

  return (
    <div className="overflow-hidden rounded-[10px] border border-border bg-bg-subtle">
      <div className="overflow-x-auto">
        <CircuitBoard nodes={nodes} connections={connections} width={W} height={H} showGrid />
      </div>
      <p className="border-t border-border px-3 py-2.5 text-[11.5px] leading-relaxed text-text-faint">
        {fanIn === null
          ? "A high fan-in with small, similar amounts is what separates a ring from a merchant that is simply busy."
          : `${ratio(fanIn, 2)} accounts per merchant. A high fan-in with small, similar amounts is what separates a ring from a merchant that is simply busy.`}
        {truncated ? " The busiest three of each are drawn; the full lists are below." : ""}
      </p>
    </div>
  );
}
