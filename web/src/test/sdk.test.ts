/**
 * Node SDK tests.
 *
 * These drive the real SDK source. Only fetch is replaced, so request shaping,
 * header handling, error mapping, retry policy and response conversion are all
 * exercised as written.
 */

import { describe, expect, it, vi } from "vitest";

import {
  Spark,
  SparkAuthError,
  SparkNotAvailableError,
  SparkRateLimitError,
  SparkRequestError,
  SparkServerError,
} from "../../../sdk/node/src/index";

/** A fetch stub that replies with the given status and body every time. */
function replyWith(status: number, body: unknown) {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const SCORED = {
  transaction_id: "txn_123",
  amount: 1499,
  customer_id: "customer_42",
  merchant_id: "merchant_7",
  risk_score: 0.81,
  risk_band: "HIGH",
  decision: "REVIEW",
  mode: "balanced",
  model_id: "hybrid-v1",
  model_version: "spark-hybrid-v1",
  path: "MODEL",
  review_threshold: 0.05,
  block_threshold: 0.14,
  latency_ms: 22.4,
  reasons: [],
  notes: [],
};

describe("Spark Node SDK", () => {
  it("refuses to start without an API key", () => {
    expect(() => new Spark({ apiKey: "" })).toThrow(SparkAuthError);
  });

  it("never exposes the key when serialised", () => {
    const client = new Spark({ apiKey: "sk_test_secret_value" });
    const dumped = JSON.stringify(client);
    expect(dumped).not.toContain("sk_test_secret_value");
    expect(dumped).toContain("test");
  });

  it("knows a test key from a live key", () => {
    expect(new Spark({ apiKey: "sk_test_a" }).isTestMode).toBe(true);
    expect(new Spark({ apiKey: "sk_live_a" }).isTestMode).toBe(false);
  });

  it("sends the documented request and converts the response", async () => {
    const fetchStub = replyWith(200, SCORED);
    const client = new Spark({
      apiKey: "sk_test_k",
      baseUrl: "https://spark.example",
      fetch: fetchStub as unknown as typeof fetch,
    });

    const result = await client.risk.score({
      transactionId: "txn_123",
      amount: 1499,
      customerId: "customer_42",
      merchantId: "merchant_7",
    });

    const [url, init] = fetchStub.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://spark.example/api/v1/risk/score");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer sk_test_k",
    );
    // The API uses snake_case; the SDK surface is camelCase.
    expect(JSON.parse(init.body as string)).toEqual({
      amount: 1499,
      customer_id: "customer_42",
      merchant_id: "merchant_7",
      explain: true,
      transaction_id: "txn_123",
    });

    expect(result.decision).toBe("REVIEW");
    expect(result.riskScore).toBe(0.81);
    expect(result.modelVersion).toBe("spark-hybrid-v1");
    expect(result.raw).toEqual(SCORED);
  });

  it("omits optional fields that were not supplied", async () => {
    const fetchStub = replyWith(200, SCORED);
    const client = new Spark({
      apiKey: "sk_test_k",
      fetch: fetchStub as unknown as typeof fetch,
    });
    await client.risk.score({ amount: 1, customerId: "c", merchantId: "m" });
    const [, init] = fetchStub.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body).not.toHaveProperty("location");
    expect(body).not.toHaveProperty("payment_type");
    expect(body).not.toHaveProperty("mode");
  });

  it("maps each status onto its own error type", async () => {
    const cases: [number, unknown, unknown][] = [
      [401, { detail: { message: "bad key", reason: "invalid_api_key" } }, SparkAuthError],
      [422, { detail: { message: "bad input", reason: "invalid" } }, SparkRequestError],
      [429, { detail: { message: "slow down", reason: "rate_limited" } }, SparkRateLimitError],
      [501, { detail: { message: "not built", reason: "upcoming" } }, SparkNotAvailableError],
      [500, { detail: { message: "boom", reason: "internal" } }, SparkServerError],
    ];

    for (const [status, body, type] of cases) {
      const client = new Spark({
        apiKey: "sk_test_k",
        maxRetries: 0,
        fetch: replyWith(status, body) as unknown as typeof fetch,
      });
      await expect(
        client.risk.score({ amount: 1, customerId: "c", merchantId: "m" }),
      ).rejects.toBeInstanceOf(type as never);
    }
  });

  it("does not retry a request the API rejected", async () => {
    // Resending a rejected request cannot help, so it must not happen.
    const fetchStub = replyWith(422, { detail: { message: "no", reason: "invalid" } });
    const client = new Spark({
      apiKey: "sk_test_k",
      maxRetries: 3,
      fetch: fetchStub as unknown as typeof fetch,
    });
    await expect(
      client.risk.score({ amount: -1, customerId: "", merchantId: "" }),
    ).rejects.toBeInstanceOf(SparkRequestError);
    expect(fetchStub).toHaveBeenCalledTimes(1);
  });

  it("carries the field list through a validation error", async () => {
    const client = new Spark({
      apiKey: "sk_test_k",
      maxRetries: 0,
      fetch: replyWith(422, {
        detail: {
          message: "Check these fields.",
          reason: "invalid",
          fields: [{ field: "amount", problem: "must be positive" }],
        },
      }) as unknown as typeof fetch,
    });

    await expect(
      client.risk.score({ amount: -1, customerId: "c", merchantId: "m" }),
    ).rejects.toSatisfy(
      (e: SparkRequestError) =>
        e.fields.length === 1 && e.fields[0].field === "amount",
    );
  });
});
