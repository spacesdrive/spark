/**
 * Catches a crash in one page so the rest of the app survives it.
 *
 * Without this, a single component reading a field the API did not send
 * unmounts the whole tree and the user gets a blank white page with no idea
 * what happened. That is the worst possible failure mode: it looks like the
 * product is broken rather than that one panel is.
 *
 * The message shown is deliberately plain. The real error goes to the console
 * for whoever is debugging, and is shown behind a toggle rather than thrown at
 * someone who just wanted to score a transaction.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button, Card, CardHeader } from "@/components/ui/primitives";
import { Icon } from "@/components/ui/icons";

interface Props {
  children: ReactNode;
  /** Changing this resets the boundary, so navigating away clears the error. */
  resetKey?: string;
}

interface State {
  error: Error | null;
  showDetail: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, showDetail: false };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null, showDetail: false });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Spark: a page failed to render", error, info.componentStack);
  }

  render() {
    const { error, showDetail } = this.state;
    if (!error) return this.props.children;

    return (
      <Card>
        <CardHeader
          title="This page could not be displayed"
          description="Something on this page failed to render. The rest of Spark
            is still working, so you can carry on elsewhere."
          action={
            <Button
              size="sm"
              icon={<Icon.Refresh size={14} />}
              onClick={() => this.setState({ error: null, showDetail: false })}
            >
              Try again
            </Button>
          }
        />
        <div className="space-y-3 px-5 py-4">
          <p className="text-[13px] leading-relaxed text-text-muted">
            This is a bug in Spark, not something you did. Reloading sometimes
            helps. If it keeps happening, the details below are what a developer
            needs.
          </p>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => this.setState({ showDetail: !showDetail })}
          >
            {showDetail ? "Hide details" : "Show details"}
          </Button>
          {showDetail ? (
            <pre className="overflow-x-auto rounded-[8px] border border-border bg-bg-subtle p-3 font-mono text-[11.5px] leading-relaxed">
              {error.message}
            </pre>
          ) : null}
        </div>
      </Card>
    );
  }
}
