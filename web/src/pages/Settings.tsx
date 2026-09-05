/**
 * Settings: appearance, defaults, organizations, and what the server reports
 * about itself.
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useApp } from "@/stores/app";
import { Icon } from "@/components/ui/icons";
import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  ErrorState,
  Field,
  PageHeader,
  ScrollTable,
  Select,
  Td,
  Th,
} from "@/components/ui/primitives";
import { shortDate } from "@/lib/format";

export function Settings() {
  const {
    theme,
    toggleTheme,
    mode,
    setMode,
    user,
    organizations,
    activeOrg,
    setActiveOrg,
    refreshUser,
    signOut,
    setTourSeen,
    health,
    config,
    notify,
  } = useApp();

  const navigate = useNavigate();
  const [orgName, setOrgName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function createOrg() {
    if (!orgName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const org = await api.organizations.create(orgName.trim());
      setOrgName("");
      await refreshUser();
      setActiveOrg(org.id);
      notify({
        tone: "success",
        title: "Organization created",
        body: `${org.name} is ready. Datasets, models and keys belong to it.`,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, { message: "Failed." }));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "More" }, { label: "Settings" }]}
        title="Settings"
        description="How the dashboard looks and behaves, and what this server is
          running."
      />

      <div className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader title="Appearance" />
          <div className="space-y-4 p-5">
            <Select
              label="Theme"
              value={theme}
              onChange={(v) => {
                if (v !== theme) toggleTheme();
              }}
              options={[
                { value: "light", label: "Light" },
                { value: "dark", label: "Dark" },
              ]}
              hint="Starts on whatever your system prefers."
            />
            <div>
              <p className="mb-1.5 text-[13px] font-medium">Product tour</p>
              <Button
                size="sm"
                onClick={() => {
                  // The tour points at the sidebar, the model selector and two
                  // panels on the overview, so it can only run there. Clearing
                  // the flag alone left the button doing nothing visible until
                  // the user happened to navigate home themselves.
                  setTourSeen(false);
                  navigate("/");
                }}
                icon={<Icon.Play size={14} />}
              >
                Show the tour again
              </Button>
              <p className="mt-1.5 text-[12px] text-text-faint">
                A short walkthrough of the sidebar, the model selector, the metrics
                and the two testing pages.
              </p>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Scoring defaults"
            description="Used wherever you have not chosen something else."
          />
          <div className="space-y-4 p-5">
            <Select
              label="Threshold setting"
              value={mode}
              onChange={setMode}
              options={[
                { value: "balanced", label: "Balanced (lowest expected cost)" },
                { value: "high_precision", label: "High precision" },
                { value: "high_recall", label: "High recall" },
              ]}
              hint="These are thresholds on the same model, not different models."
            />
            {mode === "high_precision" ? (
              <Callout tone="warning" title="This one does not transfer well">
                Its threshold was chosen correctly on validation data, but the score
                distribution moved afterwards, so almost nothing in the later window
                reaches it.
              </Callout>
            ) : null}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Organizations"
          description="An organization owns your datasets, models, jobs and API
            keys. Nobody outside it can see any of them."
        />
        {!user ? (
          <div className="space-y-3 p-5">
            <p className="text-[13px] leading-relaxed text-text-muted">
              Sign in to create one. Everything that does not need an account keeps
              working without one.
            </p>
            <Link to="/login">
              <Button variant="primary" icon={<Icon.Google size={15} />}>
                Sign in
              </Button>
            </Link>
          </div>
        ) : (
          <>
            {organizations.length ? (
              <ScrollTable>
                <thead>
                  <tr>
                    <Th>Name</Th>
                    <Th>Your role</Th>
                    <Th>Stage</Th>
                    <Th>Created</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {organizations.map((o) => (
                    <tr key={o.id}>
                      <Td className="font-medium">{o.name}</Td>
                      <Td>
                        <Badge tone="neutral">{o.role}</Badge>
                      </Td>
                      <Td className="text-text-muted">
                        {o.onboarding_stage.replace(/_/g, " ")}
                      </Td>
                      <Td>{shortDate(o.created_at)}</Td>
                      <Td align="right">
                        {activeOrg?.id === o.id ? (
                          <Badge tone="accent">selected</Badge>
                        ) : (
                          <Button size="sm" onClick={() => setActiveOrg(o.id)}>
                            Select
                          </Button>
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </ScrollTable>
            ) : null}

            <div className="border-t border-border p-5">
              <Field
                label="New organization"
                placeholder="Acme Payments"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                hint="You become its owner."
                action={
                  <Button
                    variant="primary"
                    loading={creating}
                    disabled={!orgName.trim()}
                    onClick={() => void createOrg()}
                    icon={<Icon.Plus size={15} />}
                  >
                    Create
                  </Button>
                }
              />
            </div>
            {error ? (
              <div className="px-5 pb-5">
                <ErrorState message={error.message} fix={error.body.fix} />
              </div>
            ) : null}
          </>
        )}
      </Card>

      <Card>
        <CardHeader
          title="This server"
          description="What the API reports about itself."
        />
        <ScrollTable>
          <thead>
            <tr>
              <Th>Thing</Th>
              <Th align="right">State</Th>
            </tr>
          </thead>
          <tbody>
            {[
              ["API", health?.status ?? "unreachable"],
              ["API version", health?.api_version ?? "unknown"],
              ["Environment", health?.environment ?? "unknown"],
              ["Model loaded", health?.model.loaded ? "yes" : "no"],
              ["Model version", health?.model.model_version ?? "none"],
              ["Model trained", health?.model.trained_at ? shortDate(health.model.trained_at) : "not recorded"],
              ["Database", health?.database.ok ? "connected" : "unreachable"],
              ["Sign-in configured", health?.auth_configured ? "yes" : "no"],
              ["Public domain", config?.public_domain ?? "not set"],
            ].map(([label, value]) => (
              <tr key={String(label)}>
                <Td>{label}</Td>
                <Td align="right" className="font-mono text-[12px]">
                  {String(value)}
                </Td>
              </tr>
            ))}
          </tbody>
        </ScrollTable>
        {health?.model.error ? (
          <div className="px-5 py-4">
            <Callout tone="warning" title="The model did not load">
              {health.model.error}
            </Callout>
          </div>
        ) : null}
      </Card>

      {config?.limits ? (
        <Card>
          <CardHeader
            title="Limits"
            description="The values this server is configured with."
          />
          <ScrollTable>
            <thead>
              <tr>
                <Th>Limit</Th>
                <Th align="right">Value</Th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Largest upload", `${(config.limits.max_upload_bytes / (1024 * 1024)).toFixed(0)} MB`],
                ["Rows in a test dataset", config.limits.max_test_rows.toLocaleString()],
                ["Rows in a training dataset", config.limits.max_training_rows.toLocaleString()],
                ["Jobs running at once", String(config.limits.max_concurrent_jobs)],
                ["Jobs per organization per day", String(config.limits.max_jobs_per_org_per_day)],
                ["Uploads kept for", `${config.limits.dataset_retention_hours} hours`],
                ["Accepted formats", config.limits.accepted_formats.join(", ").toUpperCase()],
              ].map(([label, value]) => (
                <tr key={String(label)}>
                  <Td>{label}</Td>
                  <Td align="right">{value}</Td>
                </tr>
              ))}
            </tbody>
          </ScrollTable>
        </Card>
      ) : null}

      {user ? (
        <Card>
          <CardHeader title="Account" description={user.email} />
          <div className="p-5">
            <Button
              variant="danger"
              onClick={() => void signOut()}
              icon={<Icon.Logout size={15} />}
            >
              Sign out
            </Button>
            <p className="mt-2 text-[12px] text-text-faint">
              This ends the session on the server, not just in this tab.
            </p>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
