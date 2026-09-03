/**
 * The developer sandbox.
 *
 * Requests sent from here are real requests to the real API, with a real key.
 * Nothing is simulated: the status code, the timing and the body are whatever
 * the server returned.
 */

import { useState } from "react";
import { api } from "@/api/client";
import { useApp } from "@/stores/app";
import { useAsync } from "@/hooks/useAsync";
import { Icon } from "@/components/ui/icons";
import { CooldownButton } from "@/components/ui/ActionButtons";
import {
  ActionGroup,
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  CopyButton,
  EmptyState,
  PageHeader,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui/primitives";
import { SignInRequired } from "./ApiKeys";
import { Link } from "react-router-dom";
import { ms } from "@/lib/format";

const ENDPOINTS = [
  {
    id: "score",
    method: "POST",
    path: "/v1/risk/score",
    label: "POST /api/v1/risk/score",
    description: "Score one transaction with your organization's model.",
    body: JSON.stringify(
      {
        transaction_id: "txn_000123",
        amount: 4.5,
        customer_id: "cust_8813",
        merchant_id: "T1822",
        location: "L100",
        payment_type: "TP110",
        mode: "balanced",
        explain: true,
      },
      null,
      2
    ),
  },
  {
    id: "thresholds",
    method: "GET",
    path: "/risk/thresholds",
    label: "GET /api/risk/thresholds",
    description: "The three threshold settings and whether each still works.",
    body: "",
  },
  {
    id: "models",
    method: "GET",
    path: "/models",
    label: "GET /api/models",
    description: "The models available to you.",
    body: "",
  },
  {
    id: "health",
    method: "GET",
    path: "/health",
    label: "GET /api/health",
    description: "Whether the API, the model and the database are working.",
    body: "",
  },
];

export function Sandbox() {
  const { user, activeOrg } = useApp();
  const keys = useAsync(
    () => (activeOrg ? api.organizations.keys(activeOrg.id) : Promise.resolve([])),
    [activeOrg?.id]
  );

  const [endpointId, setEndpointId] = useState(ENDPOINTS[0].id);
  const [body, setBody] = useState(ENDPOINTS[0].body);
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [response, setResponse] = useState<{
    status: number;
    ms: number;
    body: unknown;
  } | null>(null);

  if (!user) return <SignInRequired what="The sandbox" />;
  if (!activeOrg) {
    return (
      <div className="space-y-6">
        <PageHeader
        breadcrumb={[{ label: "Developers" }, { label: "Sandbox" }]}
        title="Sandbox"
      />
        <Card>
          <EmptyState
            icon={<Icon.Building size={26} />}
            title="Create an organization first"
            description="Sandbox requests are made with a key that belongs to an
              organization."
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

  const endpoint = ENDPOINTS.find((e) => e.id === endpointId)!;
  const testKeys = (keys.data ?? []).filter((k) => k.active && k.mode === "test");

  async function send() {
    setBusy(true);
    setResponse(null);
    try {
      const result = await api.sandbox(
        endpoint.method,
        endpoint.path,
        endpoint.method === "GET" ? undefined : body,
        secret
      );
      setResponse(result);
    } catch (err) {
      setResponse({
        status: 0,
        ms: 0,
        body: {
          message:
            err instanceof Error ? err.message : "The request could not be sent.",
        },
      });
    } finally {
      setBusy(false);
    }
  }

  const curl = [
    `curl -X ${endpoint.method} ${window.location.origin}/api${endpoint.path}`,
    `  -H "Authorization: Bearer ${secret || "sk_test_..."}"`,
    endpoint.method === "GET" ? null : `  -H "Content-Type: application/json"`,
    endpoint.method === "GET" ? null : `  -d '${body.replace(/\n\s*/g, " ")}'`,
  ]
    .filter(Boolean)
    .join(" \\\n");

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Developers" }, { label: "Sandbox" }]}
        title="Sandbox"
        description="Send a real request to the real API with a test key, and see
          exactly what your server would get back."
      />

      <Callout tone="info" title="Test mode">
        A test key is safe to experiment with. Test requests never change your
        production model, never touch production state, and are recorded
        separately from production traffic on the Usage page.
      </Callout>

      <div className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader title="Request" description="Pick an endpoint and a key." />
          <div className="space-y-4 p-5">
            <Select
              label="Endpoint"
              value={endpointId}
              onChange={(id) => {
                setEndpointId(id);
                setBody(ENDPOINTS.find((e) => e.id === id)?.body ?? "");
                setResponse(null);
              }}
              options={ENDPOINTS.map((e) => ({ value: e.id, label: e.label }))}
              hint={endpoint.description}
            />

            {keys.loading ? (
              <Spinner label="Loading your keys" />
            ) : testKeys.length ? (
              <Callout tone="info" title="Paste your key">
                Spark stores only a hash of each key, so it cannot fill this in
                for you. Paste the secret you copied when you created it, or{" "}
                <Link to="/keys" className="text-link hover:underline">
                  create a new test key
                </Link>
                .
              </Callout>
            ) : (
              <Callout tone="warning" title="No active test key">
                <Link to="/keys" className="text-link hover:underline">
                  Create a test key
                </Link>{" "}
                first. It takes a few seconds.
              </Callout>
            )}

            <div>
              <label
                htmlFor="sandbox-key"
                className="mb-1.5 block text-[13px] font-medium"
              >
                Test API key
              </label>
              <input
                id="sandbox-key"
                type="password"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder="sk_test_..."
                autoComplete="off"
                spellCheck={false}
                className="interactive h-9 w-full rounded-[8px] border border-border
                  bg-surface px-3 font-mono text-[12.5px]"
              />
              <p className="mt-1.5 text-[12px] text-text-faint">
                Sent only to this Spark server, and not stored by this page.
              </p>
            </div>

            {endpoint.method !== "GET" ? (
              <Textarea
                label="Request body"
                value={body}
                onChange={setBody}
                rows={14}
                hint="JSON. This is sent exactly as written."
              />
            ) : null}

            <ActionGroup>
              <Button
                variant="primary"
                loading={busy}
                disabled={!secret.trim()}
                onClick={() => void send()}
                icon={<Icon.Play size={15} />}
              >
                Send request
              </Button>
              {/* Only after the API said "too many requests". Retrying that
                  immediately just earns another refusal, so this one waits and
                  shows how long is left. The primary action above is never
                  throttled. */}
              {response?.status === 429 ? (
                <CooldownButton
                  cooldownSeconds={
                    Number(
                      (response.body as { retry_after_seconds?: number })
                        ?.retry_after_seconds
                    ) || 10
                  }
                  onClick={() => void send()}
                  disabled={busy}
                >
                  Retry
                </CooldownButton>
              ) : null}
            </ActionGroup>
          </div>
        </Card>

        <div className="space-y-3">
          <Card>
            <CardHeader
              title="Response"
              description="The real reply from the server."
              action={
                response ? (
                  <span className="flex items-center gap-2">
                    <Badge
                      tone={
                        response.status >= 200 && response.status < 300
                          ? "low"
                          : response.status >= 400
                            ? "high"
                            : "medium"
                      }
                    >
                      {response.status || "no response"}
                    </Badge>
                    <span className="text-[11.5px] tabular-nums text-text-muted">
                      {ms(response.ms)}
                    </span>
                  </span>
                ) : null
              }
            />
            <div className="p-5">
              {busy ? (
                <Spinner label="Sending" />
              ) : response ? (
                <>
                  <Textarea
                    value={JSON.stringify(response.body, null, 2)}
                    onChange={() => undefined}
                    rows={18}
                  />
                  <div className="mt-3">
                    <CopyButton
                      value={JSON.stringify(response.body, null, 2)}
                      label="Copy response"
                    />
                  </div>
                </>
              ) : (
                <EmptyState
                  icon={<Icon.Terminal size={24} />}
                  title="Nothing sent yet"
                  description="Paste a test key and press Send. The response here is
                    the real one, not a sample."
                />
              )}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="The same request as curl"
              action={<CopyButton value={curl} label="Copy" />}
            />
            <pre className="overflow-x-auto px-5 py-4 font-mono text-[11.5px] leading-relaxed">
              {curl}
            </pre>
          </Card>
        </div>
      </div>
    </div>
  );
}
