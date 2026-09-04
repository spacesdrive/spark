/**
 * Sign in.
 *
 * The page is explicit about what an account is for, because most of Spark
 * does not need one. Nobody should have to sign in to find out what the
 * product does.
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "@/stores/app";
import { signInWithGoogle } from "@/api/supabase";
import { Icon } from "@/components/ui/icons";
import {
  Button,
  Callout,
  Card,
  CardHeader,
  ErrorState,
} from "@/components/ui/primitives";

const PUBLIC = [
  "Read what Spark does and how it was measured",
  "Score a single transaction and see the full explanation",
  "Upload a CSV and score every row in it",
  "Measure accuracy on your own labelled data",
  "Read the documentation and the API reference",
];

const PRIVATE = [
  "Create an organization to hold your data and models",
  "Import your historical transactions",
  "Train a model on your own data",
  "Keep and download private models",
  "Create API keys and see what they have been doing",
];

export function Login() {
  const { config, user, theme } = useApp();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user) {
    return (
      <div className="mx-auto max-w-lg py-10">
        <Card>
          <CardHeader
            title="You are signed in"
            description={`Signed in as ${user.email}.`}
          />
          <div className="p-5">
            <Button variant="primary" onClick={() => navigate("/")}>
              Go to the dashboard
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      await signInWithGoogle(`${window.location.origin}/login`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in could not start.");
      setBusy(false);
    }
  }

  const configured = config?.auth_configured ?? false;
  const mark =
    theme === "dark"
      ? "/brand/spark-banner-dark.png"
      : "/brand/spark-banner-light.png";

  return (
    <div className="relative w-full px-4 py-10">
      <div
        className="relative mx-auto flex w-full max-w-sm flex-col justify-center
          border-x border-border"
      >
        <div className="flex flex-col gap-6 px-6">
          <img src={mark} alt="Spark" className="h-[18px] w-auto self-start" />
          <div className="space-y-1.5">
            <h1 className="text-[20px] font-semibold tracking-tight">
              Hey, welcome
            </h1>
            <p className="text-[13.5px] leading-relaxed text-text-muted">
              Sign in to train and manage your own models. Testing Spark needs no
              account at all.
            </p>
          </div>
        </div>

        {/* One action, framed by a rule above and below, as the block does. */}
        <div className="relative my-6 flex w-full flex-col gap-4 border-y border-border px-6 py-8">
          {configured ? (
            <Button
              variant="primary"
              size="lg"
              className="w-full"
              loading={busy}
              onClick={() => void signIn()}
              icon={<Icon.Google size={17} />}
            >
              Continue with Google
            </Button>
          ) : (
            <Callout tone="warning" title="Sign-in is not configured on this server">
              Google sign-in runs through Supabase, and this server has not been
              given a Supabase project yet. Everything that does not need an
              account still works.
            </Callout>
          )}

          {error ? <ErrorState title="Sign-in could not start" message={error} /> : null}

          <Link
            to="/"
            className="text-center text-[12.5px] text-link hover:underline"
          >
            Keep looking around without an account
          </Link>
        </div>

        <div className="space-y-4 px-6">
          <p className="text-center text-[12px] leading-relaxed text-text-faint">
            Signing in creates a session on the Spark server and stores it in a
            cookie your browser cannot read from a script. No access token is
            kept in browser storage.
          </p>

          <details className="group rounded-[10px] border border-border">
            <summary
              className="flex cursor-pointer list-none items-center justify-between
                gap-3 px-4 py-2.5 text-[12.5px] font-medium"
            >
              What needs an account
              <Icon.ChevronDown
                size={15}
                className="shrink-0 text-text-muted transition-transform
                  group-open:rotate-180"
              />
            </summary>
            <div className="border-t border-border px-4 py-3">
              <p className="mb-2 text-[12px] font-medium text-text-muted">
                Works without one
              </p>
              <ul className="space-y-1.5">
                {PUBLIC.map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <Icon.CheckCircle size={14} className="mt-0.5 shrink-0 text-low" />
                    <span className="text-[12.5px]">{item}</span>
                  </li>
                ))}
              </ul>

              <p className="mb-2 mt-4 text-[12px] font-medium text-text-muted">
                Needs an account
              </p>
              <ul className="space-y-1.5">
                {PRIVATE.map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <Icon.Key size={14} className="mt-0.5 shrink-0 text-text-muted" />
                    <span className="text-[12.5px]">{item}</span>
                  </li>
                ))}
              </ul>

              <p className="mt-3 border-t border-border pt-3 text-[11.5px] leading-relaxed text-text-faint">
                Training uses server time and produces a model built from your
                data, so it has to belong to an account. The server checks who
                owns every model, dataset and job on every request.
              </p>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}
