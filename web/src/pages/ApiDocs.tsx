/**
 * The API reference.
 *
 * Organised as tabs rather than a stack of cards. A developer arrives wanting
 * one of six things, and the previous layout made them scroll past the other
 * five. Quickstart is the landing tab because sending a first request is what
 * most people come here to do.
 *
 * The endpoint list is written here rather than generated, so it can carry
 * plain-language explanations. It sits alongside the live OpenAPI document,
 * which is generated, so the two can be checked against each other.
 */

import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { Icon } from "@/components/ui/icons";
import { Link } from "react-router-dom";
import {
  ActionGroup,
  Badge,
  Button,
  Callout,
  CopyButton,
  PageHeader,
  ScrollTable,
  Section,
  Td,
  Th,
} from "@/components/ui/primitives";
import { Tabs } from "@/components/ui/Tabs";
import { DOCS } from "@/config/docs";

interface Endpoint {
  method: string;
  path: string;
  what: string;
  auth: "none" | "key" | "account";
}

const ENDPOINTS: { group: string; items: Endpoint[] }[] = [
  {
    group: "Scoring",
    items: [
      {
        method: "POST",
        path: "/api/v1/risk/score",
        what: "Score one transaction. This is the endpoint your servers call.",
        auth: "key",
      },
      {
        method: "POST",
        path: "/api/risk/score",
        what: "The same scoring, used by this dashboard. Rate limited, no key needed.",
        auth: "none",
      },
      {
        method: "GET",
        path: "/api/risk/thresholds",
        what: "The three threshold settings, and whether each still works on held-out data.",
        auth: "none",
      },
    ],
  },
  {
    group: "Models",
    items: [
      { method: "GET", path: "/api/models", what: "Models you can use.", auth: "none" },
      { method: "GET", path: "/api/models/{id}", what: "One model, with its weights and thresholds.", auth: "none" },
      { method: "POST", path: "/api/models/{id}/activate", what: "Make a custom model the one your organization uses.", auth: "account" },
      { method: "POST", path: "/api/models/{id}/deactivate", what: "Stop using a custom model.", auth: "account" },
    ],
  },
  {
    group: "Datasets",
    items: [
      { method: "GET", path: "/api/datasets/format", what: "Which columns Spark needs, and what each one is for.", auth: "none" },
      { method: "GET", path: "/api/datasets/example", what: "Details of the built-in example dataset.", auth: "none" },
      { method: "POST", path: "/api/datasets/upload", what: "Upload a CSV. Returns the validation result.", auth: "none" },
      { method: "GET", path: "/api/datasets/{id}", what: "One dataset you uploaded.", auth: "none" },
      { method: "GET", path: "/api/datasets/{id}/preview", what: "The first rows, as the server parsed them.", auth: "none" },
      { method: "POST", path: "/api/datasets/{id}/validate", what: "Re-check a dataset, optionally with your own column mapping.", auth: "none" },
      { method: "POST", path: "/api/datasets/score", what: "Queue scoring for an uploaded dataset. Returns a job.", auth: "none" },
      { method: "DELETE", path: "/api/datasets/{id}", what: "Delete an upload now instead of waiting for the retention window.", auth: "none" },
    ],
  },
  {
    group: "Jobs",
    items: [
      { method: "GET", path: "/api/jobs/{id}", what: "How far a job has got. Poll this.", auth: "none" },
      { method: "GET", path: "/api/jobs/{id}/result", what: "The finished result, with the rows paged.", auth: "none" },
      { method: "GET", path: "/api/jobs/{id}/download", what: "The scored rows as a CSV.", auth: "none" },
    ],
  },
  {
    group: "Organizations and keys",
    items: [
      { method: "GET", path: "/api/organizations", what: "Organizations you belong to.", auth: "account" },
      { method: "POST", path: "/api/organizations", what: "Create one. You become its owner.", auth: "account" },
      { method: "GET", path: "/api/organizations/{id}", what: "One organization, with members and onboarding stage.", auth: "account" },
      { method: "GET", path: "/api/organizations/{id}/api-keys", what: "Your keys, masked.", auth: "account" },
      { method: "POST", path: "/api/organizations/{id}/api-keys", what: "Create a key. The secret is returned once.", auth: "account" },
      { method: "POST", path: "/api/api-keys/{id}/rotate", what: "Issue a new secret and stop the old one.", auth: "account" },
      { method: "POST", path: "/api/api-keys/{id}/revoke", what: "Turn a key off permanently.", auth: "account" },
      { method: "GET", path: "/api/organizations/{id}/usage", what: "What your keys have been doing.", auth: "account" },
    ],
  },
  {
    group: "Other",
    items: [
      { method: "GET", path: "/api/health", what: "Whether the API, the model and the database are working.", auth: "none" },
      { method: "GET", path: "/api/config", what: "What the browser needs to start up. No private credentials.", auth: "none" },
      { method: "GET", path: "/api/metrics/overview", what: "The measured results, each labelled with its split.", auth: "none" },
      { method: "GET", path: "/api/metrics/charts", what: "The same numbers shaped for charts.", auth: "none" },
      { method: "GET", path: "/api/metrics/limitations", what: "What the measured numbers do not cover.", auth: "none" },
      { method: "GET", path: "/api/metrics/rings", what: "Abuse-ring detection results.", auth: "none" },
      { method: "GET", path: "/api/training/limits", what: "The training limits this server is configured with.", auth: "none" },
      { method: "POST", path: "/api/training/jobs", what: "Training is not built yet. Runs the real checks, then returns 501.", auth: "account" },
    ],
  },
];

const AUTH_LABEL: Record<Endpoint["auth"], { text: string; tone: "neutral" | "accent" | "medium" }> = {
  none: { text: "public", tone: "neutral" },
  key: { text: "API key", tone: "accent" },
  account: { text: "signed in", tone: "medium" },
};

const EXAMPLE_REQUEST = `curl -X POST https://spark.spacesdrive.cc/api/v1/risk/score \\
  -H "Authorization: Bearer sk_test_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "transaction_id": "txn_000123",
    "amount": 4.5,
    "customer_id": "cust_8813",
    "merchant_id": "merch_204",
    "location": "IN-KA",
    "payment_type": "upi"
  }'`;

const EXAMPLE_RESPONSE = `{
  "transaction_id": "txn_000123",
  "risk_score": 0.4127,
  "risk_band": "HIGH",
  "decision": "BLOCK",
  "mode": "balanced",
  "model_id": "hybrid-v1",
  "model_version": "spark-hybrid-v1",
  "path": "MODEL",
  "review_threshold": 0.0771,
  "block_threshold": 0.1402,
  "channel_scores": {
    "tabular": 0.0966,
    "graph": 0.6359,
    "behavioral": 0.8812,
    "velocity": 0.7431
  },
  "reasons": [ ... ],
  "graph_evidence": { ... },
  "latency_ms": 21.4
}`;

const ERRORS = [
  ["400", "The request was understood but cannot be done. The body says why."],
  ["401", "No key, an invalid key, or a revoked one."],
  ["403", "You are signed in but not allowed to do this."],
  ["404", "Not found, or not yours. Spark does not tell you which."],
  ["409", "The job you asked about has not finished."],
  ["410", "The file expired and was deleted."],
  ["422", "A field was the wrong shape. The body lists which."],
  ["429", "Too many requests. The body says how long to wait."],
  ["500", "Something broke on the server. Details go to the server log, not to you."],
  ["501", "The feature is not built yet."],
  ["503", "No model is loaded, or the evaluation has not been run."],
];

const PYTHON_EXAMPLE = `pip install -e sdk/python

from spark_sdk import Spark

client = Spark(api_key=os.environ["SPARK_TEST_API_KEY"])
result = client.risk.score(
    amount=1499,
    customer_id="customer_42",
    merchant_id="merchant_7",
)
print(result.decision, result.risk_score)`;

const NODE_EXAMPLE = `import { Spark } from "@spark-ai/sdk";

const client = new Spark({ apiKey: process.env.SPARK_API_KEY });

const result = await client.risk.score({
  amount: 1499,
  customerId: "customer_42",
  merchantId: "merchant_7",
});

console.log(result.decision, result.riskScore);`;

const PRODUCTION_STEPS: [string, string][] = [
  ["Test key", "Create one in API Keys and build against it."],
  ["Train", "Upload your labelled history and train a model."],
  ["Evaluate", "Read the held-out results."],
  ["Approve", "Promote the model to production."],
  ["Live key", "Only possible once a model is approved."],
];

export function ApiDocs() {
  const config = useAsync(() => api.config(), []);
  const base = config.data
    ? `https://${config.data.public_domain}`
    : window.location.origin;

  const limits = config.data?.limits;

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Developers" }, { label: "API" }]}
        title="API"
        description="One endpoint does the work. Everything else is setup."
        action={
          <ActionGroup align="end">
            <Link to="/sandbox">
              <Button variant="primary" icon={<Icon.Terminal size={15} />}>
                Open sandbox
              </Button>
            </Link>
            <a href="/api/docs" target="_blank" rel="noreferrer">
              <Button icon={<Icon.Code size={15} />}>OpenAPI</Button>
            </a>
          </ActionGroup>
        }
      />

      <Tabs
        items={[
          {
            id: "quickstart",
            label: "Quickstart",
            content: (
              <div className="space-y-5">
                <Section
                  title="Send your first request"
                  description="Create a test key in API Keys, then run this. It works
                    against the built-in model straight away."
                  action={<CopyButton value={EXAMPLE_REQUEST} label="Copy" />}
                >
                  <pre className="overflow-x-auto rounded-[10px] border border-border bg-bg-subtle px-4 py-3.5 font-mono text-[11.5px] leading-relaxed">
                    {EXAMPLE_REQUEST.replace("https://spark.spacesdrive.cc", base)}
                  </pre>
                </Section>

                <Section title="What comes back">
                  <pre className="overflow-x-auto rounded-[10px] border border-border bg-bg-subtle px-4 py-3.5 font-mono text-[11.5px] leading-relaxed">
                    {EXAMPLE_RESPONSE}
                  </pre>
                </Section>

                <Callout tone="info" title="Authentication">
                  Send your key as{" "}
                  <code className="font-mono text-[12px]">
                    Authorization: Bearer sk_test_...
                  </code>
                  . A test key always uses the built-in model and never touches
                  production. A live key resolves to the model your organization
                  approved.
                </Callout>
              </div>
            ),
          },
          {
            id: "endpoints",
            label: "Endpoints",
            content: (
              <div className="space-y-6">
                {ENDPOINTS.map((group) => (
                  <Section key={group.group} title={group.group}>
                    <div className="overflow-hidden rounded-[10px] border border-border">
                      <ScrollTable>
                        <thead>
                          <tr>
                            <Th>Method</Th>
                            <Th>Path</Th>
                            <Th>What it does</Th>
                            <Th>Needs</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {group.items.map((e) => (
                            <tr key={e.method + e.path}>
                              <Td>
                                <Badge tone={e.method === "GET" ? "neutral" : "accent"}>
                                  {e.method}
                                </Badge>
                              </Td>
                              <Td className="font-mono text-[12px]">{e.path}</Td>
                              <Td className="max-w-md text-text-muted">{e.what}</Td>
                              <Td>
                                <Badge tone={AUTH_LABEL[e.auth].tone}>
                                  {AUTH_LABEL[e.auth].text}
                                </Badge>
                              </Td>
                            </tr>
                          ))}
                        </tbody>
                      </ScrollTable>
                    </div>
                  </Section>
                ))}
              </div>
            ),
          },
          {
            id: "sdks",
            label: "SDKs",
            badge: <Badge tone="low">Available</Badge>,
            content: (
              <div className="space-y-5">
                <Section
                  title="Python"
                  description="No dependencies. The client uses only the standard
                    library, so it cannot conflict with anything you already have."
                  action={
                    <a href={DOCS.sdk} target="_blank" rel="noreferrer">
                      <Button size="sm">Documentation</Button>
                    </a>
                  }
                >
                  <pre className="overflow-x-auto rounded-[10px] border border-border bg-bg-subtle px-4 py-3.5 font-mono text-[11.5px] leading-relaxed">
                    {PYTHON_EXAMPLE}
                  </pre>
                </Section>

                <Section
                  title="Node and TypeScript"
                  description="Needs Node 18 or newer for built-in fetch. No runtime
                    dependencies."
                  action={<CopyButton value={NODE_EXAMPLE} label="Copy" />}
                >
                  <pre className="overflow-x-auto rounded-[10px] border border-border bg-bg-subtle px-4 py-3.5 font-mono text-[11.5px] leading-relaxed">
                    {NODE_EXAMPLE}
                  </pre>
                </Section>

                <Callout tone="info" title="There is no currency or timestamp field">
                  The model was fitted on the amount, the parties, the payment type
                  and the location. It has no currency feature, so accepting one
                  would imply an accuracy Spark cannot deliver. Convert to a single
                  currency before you call.
                </Callout>
              </div>
            ),
          },
          {
            id: "errors",
            label: "Errors",
            content: (
              <Section
                title="Error responses"
                description="Every error carries a message written for a person and a
                  reason code for your code to switch on."
              >
                <div className="overflow-hidden rounded-[10px] border border-border">
                  <ScrollTable>
                    <thead>
                      <tr>
                        <Th>Status</Th>
                        <Th>What it means</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {ERRORS.map(([code, meaning]) => (
                        <tr key={code}>
                          <Td className="font-mono">{code}</Td>
                          <Td className="text-text-muted">{meaning}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </ScrollTable>
                </div>
                <p className="text-[11.5px] leading-relaxed text-text-faint">
                  Stack traces are never returned, and a failure message has every
                  filesystem path stripped out of it before it is stored.
                </p>
              </Section>
            ),
          },
          {
            id: "limits",
            label: "Rate limits",
            content: (
              <Section
                title="Configured limits"
                description="The real values this server runs with, not examples."
              >
                <div className="overflow-hidden rounded-[10px] border border-border">
                  <ScrollTable>
                    <thead>
                      <tr>
                        <Th>Limit</Th>
                        <Th align="right">Value</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {limits ? (
                        <>
                          <tr>
                            <Td>Largest upload</Td>
                            <Td align="right">
                              {(limits.max_upload_bytes / 1048576).toFixed(1)} MB
                            </Td>
                          </tr>
                          <tr>
                            <Td>Rows per test dataset</Td>
                            <Td align="right">
                              {limits.max_test_rows.toLocaleString()}
                            </Td>
                          </tr>
                          <tr>
                            <Td>Jobs running at once</Td>
                            <Td align="right">{limits.max_concurrent_jobs}</Td>
                          </tr>
                          <tr>
                            <Td>Jobs per organization per day</Td>
                            <Td align="right">{limits.max_jobs_per_org_per_day}</Td>
                          </tr>
                        </>
                      ) : (
                        <tr>
                          <Td className="text-text-faint">Reading the limits</Td>
                          <Td align="right"> </Td>
                        </tr>
                      )}
                    </tbody>
                  </ScrollTable>
                </div>
                <p className="text-[11.5px] leading-relaxed text-text-faint">
                  A rate limited response returns 429 with the seconds to wait. Both
                  SDKs read that and back off for you.
                </p>
              </Section>
            ),
          },
          {
            id: "production",
            label: "Production",
            content: (
              <div className="space-y-5">
                <Section title="Getting to a live key">
                  <ol className="space-y-2.5">
                    {PRODUCTION_STEPS.map(([step, detail], i) => (
                      <li key={step} className="flex items-start gap-2.5">
                        <span
                          aria-hidden="true"
                          className="mt-0.5 flex size-[18px] shrink-0 items-center justify-center rounded-full border border-border text-[10.5px] font-semibold text-text-faint"
                        >
                          {i + 1}
                        </span>
                        <span>
                          <span className="text-[12.5px] font-medium">{step}</span>
                          <span className="ml-1.5 text-[12.5px] text-text-muted">
                            {detail}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ol>
                </Section>
                <Callout tone="warning" title="Never put a live key in browser code">
                  Anything shipped to a browser is readable by anyone who opens it.
                  Live keys belong on your server only.
                </Callout>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
