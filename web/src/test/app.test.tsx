/**
 * Frontend tests.
 *
 * These cover the behaviour that has to stay true no matter what the styling
 * does: the API client shapes errors usefully, numbers that were not measured
 * never render as zero, risk is stated in words as well as colour, and the
 * navigation has no dead entries.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ApiError, api } from "@/api/client";
import { NOT_MEASURED, formatMetric, money, percent, ratio } from "@/lib/format";
import { ALL_NAV_ITEMS, NAV } from "@/config/navigation";
import { Button, DecisionBadge, Field, Meter, RiskBadge } from "@/components/ui/primitives";
import { RiskResult } from "@/components/risk/RiskResult";
import type { ScoreResult } from "@/types";

// formatting

describe("formatting never invents a number", () => {
  it("says a value was not measured instead of showing zero", () => {
    expect(ratio(null)).toBe(NOT_MEASURED);
    expect(ratio(undefined)).toBe(NOT_MEASURED);
    expect(ratio(Number.NaN)).toBe(NOT_MEASURED);
    expect(percent(null)).toBe(NOT_MEASURED);
    expect(money(null)).toBe(NOT_MEASURED);
    expect(formatMetric(null, "count")).toBe(NOT_MEASURED);
  });

  it("formats real values", () => {
    expect(ratio(0.6299)).toBe("0.6299");
    expect(percent(0.6299, 1)).toBe("63.0%");
    expect(formatMetric(5100, "count")).toBe("5,100");
    expect(formatMetric(1.72, "ms")).toBe("1.72 ms");
  });

  it("does not round a real zero away into 'not measured'", () => {
    expect(ratio(0)).toBe("0.0000");
    expect(formatMetric(0, "count")).toBe("0");
  });
});

// navigation

describe("navigation", () => {
  it("has no duplicate paths", () => {
    const paths = ALL_NAV_ITEMS.map((i) => i.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("never routes a page under the backend prefix", () => {
    for (const item of ALL_NAV_ITEMS) {
      expect(item.path.startsWith("/api")).toBe(false);
    }
  });

  it("gives every entry a description", () => {
    for (const item of ALL_NAV_ITEMS) {
      expect(item.label.length).toBeGreaterThan(0);
      expect(item.description.length).toBeGreaterThan(0);
    }
  });

  it("groups every item", () => {
    const grouped = NAV.flatMap((g) => g.items).length;
    expect(grouped).toBe(ALL_NAV_ITEMS.length);
  });
});

// accessibility of risk display

describe("risk is never colour alone", () => {
  it("states the level in words", () => {
    render(<RiskBadge band="HIGH" />);
    expect(screen.getByText("HIGH RISK")).toBeInTheDocument();
  });

  it("states the decision in words", () => {
    render(<DecisionBadge decision="BLOCK" />);
    expect(screen.getByText("BLOCK")).toBeInTheDocument();
  });

  it("exposes a meter to assistive technology", () => {
    render(<Meter value={0.42} label="Risk score" />);
    const meter = screen.getByRole("meter");
    expect(meter).toHaveAttribute("aria-valuenow", "42");
    expect(meter).toHaveAttribute("aria-label", "Risk score");
  });
});

// API client

describe("the API client", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("turns a backend error body into a readable ApiError", async () => {
    // A Response body can only be read once, so the mock builds a fresh one
    // per call rather than handing back the same object twice.
    global.fetch = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            detail: {
              message: "The amount column contains text that is not a number.",
              reason: "validation_failed",
              fix: "Remove currency symbols.",
            },
          }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        )
    ) as unknown as typeof fetch;

    await expect(api.health()).rejects.toThrowError(
      "The amount column contains text that is not a number."
    );

    expect.assertions(4);
    try {
      await api.health();
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).reason).toBe("validation_failed");
      expect((err as ApiError).body.fix).toBe("Remove currency symbols.");
    }
  });

  it("marks a 401 as needing sign-in", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: { message: "Sign in to use this.", reason: "authentication_required" },
        }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      )
    ) as unknown as typeof fetch;

    try {
      await api.organizations.list();
      throw new Error("should have thrown");
    } catch (err) {
      expect((err as ApiError).needsSignIn).toBe(true);
    }
  });

  it("marks a 501 as upcoming rather than broken", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: { message: "Not available yet.", reason: "upcoming" },
        }),
        { status: 501, headers: { "Content-Type": "application/json" } }
      )
    ) as unknown as typeof fetch;

    try {
      await api.training.createJob({
        organization_id: "o",
        dataset_id: "d",
        name: "m",
      });
      throw new Error("should have thrown");
    } catch (err) {
      expect((err as ApiError).isUpcoming).toBe(true);
    }
  });

  it("says the server is unreachable rather than showing a raw network error", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch")) as
      unknown as typeof fetch;
    try {
      await api.health();
      throw new Error("should have thrown");
    } catch (err) {
      expect((err as ApiError).message).toContain("Could not reach the Spark server");
    }
  });

  it("never leaks a stack trace from a 500", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response("Traceback (most recent call last): secret internals", {
        status: 500,
      })
    ) as unknown as typeof fetch;
    try {
      await api.health();
      throw new Error("should have thrown");
    } catch (err) {
      expect((err as ApiError).message).not.toContain("Traceback");
    }
  });
});

// the risk result panel

const RESULT: ScoreResult = {
  transaction_id: "txn_1",
  amount: 4.5,
  customer_id: "cust_1",
  merchant_id: "merch_1",
  location: "IN-KA",
  payment_type: "upi",
  risk_score: 0.2143,
  risk_band: "HIGH",
  decision: "BLOCK",
  mode: "balanced",
  model_id: "hybrid-v1",
  model_version: "spark-hybrid-v1",
  path: "MODEL",
  review_threshold: 0.0771,
  block_threshold: 0.1402,
  channel_scores: { tabular: 0.04, graph: 0.88, behavioral: 0.42, velocity: 0.06 },
  channel_attribution: { tabular: 0.02, graph: 0.96, behavioral: 0, velocity: 0.02 },
  reasons: [
    {
      text: "account has 2 prior transactions",
      direction: "increases",
      contribution: 0.57,
      feature: "Source_txn_count",
    },
  ],
  entity_risk: {},
  entity_history: {
    Source: { role: "customer account", prior_transactions: 2, is_new: false },
    Target: { role: "merchant", prior_transactions: 1433, is_new: false },
  },
  graph_evidence: {},
  related_ring: null,
  stages: [{ name: "Building features", ms: 2.02 }],
  latency_ms: 20.6,
  notes: [],
};

describe("the risk result", () => {
  it("shows the decision, the score and the model version", () => {
    render(
      <MemoryRouter>
        <RiskResult result={RESULT} />
      </MemoryRouter>
    );
    expect(screen.getByText("HIGH RISK")).toBeInTheDocument();
    expect(screen.getByText("BLOCK")).toBeInTheDocument();
    expect(screen.getByText("0.2143")).toBeInTheDocument();
    expect(screen.getByText("spark-hybrid-v1")).toBeInTheDocument();
  });

  // The detail moved behind tabs so the decision is not buried under it. The
  // guarantee is unchanged: it must still be reachable and still be honest, so
  // these open the tab rather than dropping the assertion.
  function openTab(name: RegExp) {
    fireEvent.click(screen.getByRole("tab", { name }));
  }

  it("shows the real processing steps the backend reported", async () => {
    render(
      <MemoryRouter>
        <RiskResult result={RESULT} />
      </MemoryRouter>
    );
    openTab(/processing/i);
    expect(await screen.findByText("Building features")).toBeInTheDocument();
  });

  it("says so when nothing is connected instead of leaving the panel blank", async () => {
    render(
      <MemoryRouter>
        <RiskResult result={RESULT} />
      </MemoryRouter>
    );
    openTab(/relationships/i);
    expect(
      await screen.findByText(/No earlier transactions share any of this transaction/i)
    ).toBeInTheDocument();
  });

  it("marks device and network as unsupported rather than hiding them", async () => {
    render(
      <MemoryRouter>
        <RiskResult result={RESULT} />
      </MemoryRouter>
    );
    openTab(/data coverage/i);
    expect(await screen.findByText("Device history")).toBeInTheDocument();
    expect(screen.getAllByText("Not supported").length).toBeGreaterThan(0);
  });

  it("leads with the strongest reason before any of the detail", () => {
    render(
      <MemoryRouter>
        <RiskResult result={RESULT} />
      </MemoryRouter>
    );
    // The lead reason is outside the tabs, so it is on screen with no clicks.
    expect(screen.getByText("Why this result")).toBeInTheDocument();
    expect(
      screen.getByText(/moved the score more than anything else/i)
    ).toBeInTheDocument();
  });

  it("does not claim a ring when the backend reported none", () => {
    render(
      <MemoryRouter>
        <RiskResult result={RESULT} />
      </MemoryRouter>
    );
    expect(screen.queryByText(/detected ring involves/i)).toBeNull();
  });

  it("words explanations as contribution, never as cause", () => {
    render(
      <MemoryRouter>
        <RiskResult result={RESULT} />
      </MemoryRouter>
    );
    const body = document.body.textContent ?? "";
    expect(body).toMatch(/contributed to the score|Pushed the score up/i);
    expect(body).not.toMatch(/\bcaused the fraud\b|\bproves\b/i);
  });
});

describe("a field with its own action", () => {
  it("puts the control in a row with the input, not below the hint", () => {
    // The Create button used to sit beside the whole Field in an items-end
    // row, which aligned it to the bottom of the hint text and left it visibly
    // lower than the input. The action slot places it next to the input.
    render(
      <Field
        label="New organization"
        hint="You become its owner."
        action={<Button variant="primary">Create</Button>}
      />
    );

    const input = screen.getByLabelText("New organization");
    const button = screen.getByRole("button", { name: "Create" });
    const row = input.parentElement!;

    expect(row).toContainElement(button);
    expect(row.className).toContain("items-center");
    // The hint is a sibling of the row, so it cannot drag the button down.
    expect(row).not.toContainElement(screen.getByText("You become its owner."));
  });
});
