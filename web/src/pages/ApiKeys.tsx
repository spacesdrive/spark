/**
 * API keys.
 *
 * The full secret is shown exactly once, at creation, because only a hash is
 * stored. Everything else in this page shows a masked form.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { HoldButton } from "@/components/ui/ActionButtons";
import { useApp } from "@/stores/app";
import { useAsync } from "@/hooks/useAsync";
import type { ApiKeyCreated } from "@/types";
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
  Select,
  Spinner,
  Td,
  Th,
} from "@/components/ui/primitives";
import { relativeTime, shortDate } from "@/lib/format";

export function ApiKeys() {
  const { user, activeOrg, notify } = useApp();
  const keys = useAsync(
    () => (activeOrg ? api.organizations.keys(activeOrg.id) : Promise.resolve([])),
    [activeOrg?.id]
  );

  const [name, setName] = useState("");
  const [mode, setMode] = useState<"test" | "live">("test");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  if (!user) {
    return <SignInRequired what="API keys" />;
  }
  if (!activeOrg) {
    return (
      <div className="space-y-6">
        <PageHeader
        breadcrumb={[{ label: "Developers" }, { label: "API Keys" }]}
        title="API keys"
      />
        <Card>
          <EmptyState
            icon={<Icon.Building size={26} />}
            title="Create an organization first"
            description="Keys belong to an organization, and every request made
              with one is recorded against it."
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

  async function create() {
    if (!activeOrg || !name.trim()) return;
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const key = await api.organizations.createKey(activeOrg.id, name.trim(), mode);
      setCreated(key);
      setName("");
      keys.reload();
      notify({
        tone: "success",
        title: `${mode === "test" ? "Test" : "Production"} key created`,
        body: "Copy it now. It cannot be shown again.",
      });
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, { message: "Failed." }));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    try {
      await api.organizations.revokeKey(id);
      keys.reload();
      notify({ tone: "warning", title: "Key revoked", body: "It stops working now." });
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, { message: "Failed." }));
    }
  }

  async function rotate(id: string) {
    try {
      const key = await api.organizations.rotateKey(id);
      setCreated(key);
      keys.reload();
      notify({
        tone: "warning",
        title: "Key rotated",
        body: "The old key stopped working immediately.",
      });
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, { message: "Failed." }));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "Developers" }, { label: "API Keys" }]}
        title="API keys"
        description="Keys let your servers call Spark. They belong to your
          organization and nobody outside it can use or see them."
      />

      {created ? (
        <Card className="border-accent/30">
          <CardHeader
            title="Your new key"
            description={created.warning}
            action={<Badge tone="accent">{created.mode}</Badge>}
          />
          <div className="flex flex-wrap items-center gap-3 px-5 py-4">
            <code className="min-w-0 flex-1 overflow-x-auto rounded-[8px] border border-border bg-bg-subtle px-3 py-2 font-mono text-[12.5px]">
              {created.secret}
            </code>
            <CopyButton value={created.secret} label="Copy key" />
            <Button size="sm" variant="ghost" onClick={() => setCreated(null)}>
              Done
            </Button>
          </div>
        </Card>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
        <Card>
          <CardHeader
            title="Create a key"
            description="Give it a name you will recognise later."
          />
          <div className="space-y-4 p-5">
            <Field
              label="Name"
              placeholder="Checkout service"
              value={name}
              onChange={(e) => setName(e.target.value)}
              hint="Something that says where this key is used."
            />
            <Select
              label="Kind"
              value={mode}
              onChange={(v) => setMode(v as "test" | "live")}
              options={[
                { value: "test", label: "Test key" },
                { value: "live", label: "Production key" },
              ]}
              hint={
                mode === "test"
                  ? "Safe to experiment with. Test requests never touch production state."
                  : "Calls the model your organization approved for production."
              }
            />
            {mode === "live" && !activeOrg.production_model_id ? (
              <Callout tone="warning" title="No production model yet">
                A production key needs an approved production model. Until one
                exists, the server will refuse to issue one. Use a test key for
                now.
              </Callout>
            ) : null}
            <Button
              variant="primary"
              loading={busy}
              disabled={!name.trim()}
              onClick={() => void create()}
              icon={<Icon.Plus size={15} />}
            >
              Create key
            </Button>
            {error ? <ErrorState message={error.message} fix={error.body.fix} /> : null}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Your keys"
            description="Only the masked form is ever shown after creation."
            action={
              <Button size="sm" onClick={keys.reload} icon={<Icon.Refresh size={14} />}>
                Refresh
              </Button>
            }
          />
          {keys.loading ? (
            <div className="p-6">
              <Spinner label="Loading keys" />
            </div>
          ) : !keys.data?.length ? (
            <EmptyState
              icon={<Icon.Key size={24} />}
              title="No keys yet"
              description="Create a test key to start sending requests."
            />
          ) : (
            <ScrollTable>
              <thead>
                <tr>
                  <Th>Name</Th>
                  <Th>Key</Th>
                  <Th>Kind</Th>
                  <Th>Created</Th>
                  <Th>Last used</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {keys.data.map((k) => (
                  <tr key={k.id} className={k.active ? undefined : "opacity-55"}>
                    <Td className="font-medium">{k.name}</Td>
                    <Td className="font-mono text-[12px]">{k.masked}</Td>
                    <Td>
                      <Badge tone={k.mode === "live" ? "high" : "neutral"}>{k.mode}</Badge>
                    </Td>
                    <Td>{shortDate(k.created_at)}</Td>
                    <Td>
                      {k.last_used_at ? relativeTime(k.last_used_at) : (
                        <span className="text-text-faint">never</span>
                      )}
                    </Td>
                    <Td align="right">
                      {k.active ? (
                        <span className="flex justify-end gap-1">
                          <Button size="sm" variant="ghost" onClick={() => void rotate(k.id)}>
                            Rotate
                          </Button>
                          {/* Held rather than clicked: revoking is immediate
                              and cannot be undone, and a dialog here would be
                              dismissed without reading. */}
                          <HoldButton onConfirm={() => void revoke(k.id)}>
                            Revoke
                          </HoldButton>
                        </span>
                      ) : (
                        <Badge tone="neutral">revoked</Badge>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </ScrollTable>
          )}
          <p className="border-t border-border px-5 py-3 text-[11.5px] leading-relaxed text-text-faint">
            Spark stores a hash of each key, never the key itself, so a copy of
            the database does not hand anyone a working key. Rotating issues a new
            secret and stops the old one immediately.
          </p>
        </Card>
      </div>
    </div>
  );
}

export function SignInRequired({ what }: { what: string }) {
  return (
    <div className="space-y-6">
      <PageHeader title={what} />
      <Card>
        <CardHeader
          title="This needs an account"
          description={`${what} create or read things that belong to one
            organization, so the server needs to know who you are.`}
        />
        <div className="space-y-4 p-5">
          <p className="text-[13px] leading-relaxed text-text-muted">
            Scoring transactions, uploading a test dataset and reading every
            measured result all work without signing in.
          </p>
          <ActionGroup>
            <Link to="/login">
              <Button variant="primary" icon={<Icon.Google size={15} />}>
                Sign in
              </Button>
            </Link>
            <Link to="/transaction">
              <Button>Test a transaction instead</Button>
            </Link>
          </ActionGroup>
        </div>
      </Card>
    </div>
  );
}
