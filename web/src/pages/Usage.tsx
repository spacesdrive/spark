/**
 * What your keys have been doing.
 *
 * Counts come from recorded requests. An organization that has sent nothing
 * sees zeros and a prompt, not a demo number.
 */

import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useApp } from "@/stores/app";
import { useAsync } from "@/hooks/useAsync";
import { Icon } from "@/components/ui/icons";
import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  PageHeader,
  ScrollTable,
  Spinner,
  Td,
  Th,
} from "@/components/ui/primitives";
import { money, ms, ratio, relativeTime } from "@/lib/format";
import { SignInRequired } from "./ApiKeys";
import { DecisionChart } from "@/components/charts/Charts";

export function Usage() {
  const { user, activeOrg } = useApp();
  const usage = useAsync(
    () => (activeOrg ? api.organizations.usage(activeOrg.id) : Promise.resolve(null)),
    [activeOrg?.id]
  );

  if (!user) return <SignInRequired what="Usage" />;
  if (!activeOrg) {
    return (
      <div className="space-y-6">
        <PageHeader
        breadcrumb={[{ label: "Developers" }, { label: "Usage" }]}
        title="Usage"
      />
        <Card>
          <EmptyState
            icon={<Icon.Building size={26} />}
            title="Create an organization first"
            description="Usage is recorded against the organization a key belongs to."
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

  if (usage.loading) {
    return (
      <Card className="p-6">
        <Spinner label="Loading usage" />
      </Card>
    );
  }

  const data = usage.data;
  const empty = !data || data.total_requests === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Developers" }, { label: "Usage" }]}
        title="Usage"
        description={`API requests made with keys belonging to ${activeOrg.name}.`}
        action={
          <Button size="sm" onClick={usage.reload} icon={<Icon.Refresh size={14} />}>
            Refresh
          </Button>
        }
      />

      {empty ? (
        <Card>
          <EmptyState
            icon={<Icon.Gauge size={26} />}
            title="No requests yet"
            description="Once your servers start calling Spark, every request
              appears here with the decision it produced and how long it took."
            action={
              <Link to="/sandbox">
                <Button variant="primary">Send your first request</Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Requests", data.total_requests.toLocaleString()],
              ["Approved", data.decisions.APPROVE.toLocaleString()],
              ["Sent to review", data.decisions.REVIEW.toLocaleString()],
              ["Blocked", data.decisions.BLOCK.toLocaleString()],
            ].map(([label, value]) => (
              <Card key={String(label)} className="p-4" interactive>
                <p className="text-[12px] text-text-muted">{label}</p>
                <p className="mt-1 text-[21px] font-semibold tabular-nums">{value}</p>
              </Card>
            ))}
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <DecisionChart
              data={Object.entries(data.decisions).map(([decision, count]) => ({
                decision,
                count,
              }))}
              source="your API requests"
            />
            <Card>
              <CardHeader
                title="Value of blocked transactions"
                description="What the transactions Spark stopped were worth."
              />
              <div className="p-5">
                <p className="text-[26px] font-semibold tabular-nums">
                  {money(data.blocked_amount)}
                </p>
                <Callout tone="warning" title="This is not a measured saving">
                  {data.blocked_amount_note}
                </Callout>
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Recent requests"
              description="The most recent calls, newest first."
            />
            <ScrollTable>
              <thead>
                <tr>
                  <Th>When</Th>
                  <Th>Endpoint</Th>
                  <Th>Mode</Th>
                  <Th align="right">Risk</Th>
                  <Th>Decision</Th>
                  <Th align="right">Amount</Th>
                  <Th align="right">Took</Th>
                  <Th align="right">Status</Th>
                </tr>
              </thead>
              <tbody>
                {data.recent.map((e) => (
                  <tr key={e.id}>
                    <Td>{relativeTime(e.created_at)}</Td>
                    <Td className="font-mono text-[12px]">{e.endpoint}</Td>
                    <Td>
                      <Badge tone={e.mode === "live" ? "high" : "neutral"}>{e.mode}</Badge>
                    </Td>
                    <Td align="right">{ratio(e.risk_score)}</Td>
                    <Td>{e.decision ?? "-"}</Td>
                    <Td align="right">{money(e.amount)}</Td>
                    <Td align="right">{ms(e.latency_ms)}</Td>
                    <Td align="right">{e.status_code}</Td>
                  </tr>
                ))}
              </tbody>
            </ScrollTable>
            <p className="border-t border-border px-5 py-3 text-[11.5px] leading-relaxed text-text-faint">
              Spark records the model, the score, the decision, the amount and the
              timing for each request, so you can always answer which model made a
              given decision. It does not keep the customer or merchant IDs you
              sent.
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
