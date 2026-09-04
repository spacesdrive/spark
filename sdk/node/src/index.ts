/**
 * Spark Node and TypeScript SDK.
 *
 * A thin, typed client for the Spark risk API. It contains no risk logic of
 * its own: every decision comes from the service, so the SDK cannot drift
 * away from the model.
 *
 *   import { Spark } from "@spark-ai/sdk";
 *
 *   const client = new Spark({ apiKey: process.env.SPARK_API_KEY });
 *   const result = await client.risk.score({
 *     transactionId: "txn_123",
 *     amount: 1499,
 *     customerId: "customer_42",
 *     merchantId: "merchant_7",
 *   });
 */

export type Decision = "APPROVE" | "REVIEW" | "BLOCK";
export type RiskBand = "LOW" | "MEDIUM" | "HIGH";
export type ThresholdMode = "balanced" | "high_precision" | "high_recall";

export interface Reason {
  text: string;
  direction: "increases" | "decreases";
  contribution: number;
  feature: string;
}

export interface ScoreResult {
  transactionId: string;
  amount: number;
  customerId: string;
  merchantId: string;
  riskScore: number;
  riskBand: RiskBand;
  decision: Decision;
  mode: string;
  modelId: string;
  modelVersion: string;
  /** MODEL, or COLD_START when nothing was known about any party. */
  path: string;
  reviewThreshold: number;
  blockThreshold: number;
  latencyMs: number;
  reasons: Reason[];
  notes: string[];
  /** Everything the server sent, so a newer API loses nothing here. */
  raw: Record<string, unknown>;
}

/**
 * Spark's model uses the amount, the parties, the payment type and the
 * location. There is deliberately no currency or timestamp field: the model
 * does not use one, and accepting it would imply an accuracy Spark cannot
 * deliver.
 */
export interface ScoreParams {
  amount: number;
  customerId: string;
  merchantId: string;
  transactionId?: string;
  location?: string;
  paymentType?: string;
  mode?: ThresholdMode;
  explain?: boolean;
}

export class SparkError extends Error {
  readonly statusCode?: number;
  readonly reason?: string;
  readonly body: Record<string, any>;

  constructor(
    message: string,
    opts: { statusCode?: number; reason?: string; body?: Record<string, any> } = {},
  ) {
    super(opts.reason ? `${message} (reason: ${opts.reason})` : message);
    this.name = new.target.name;
    this.statusCode = opts.statusCode;
    this.reason = opts.reason;
    this.body = opts.body ?? {};
  }
}

/** The key is missing, malformed, revoked or not allowed here. */
export class SparkAuthError extends SparkError {}

/** The request was rejected. `fields` says what to correct. */
export class SparkRequestError extends SparkError {
  get fields(): { field: string; problem: string }[] {
    return this.body.fields ?? [];
  }
}

/** Too many requests. */
export class SparkRateLimitError extends SparkError {
  get retryAfterSeconds(): number | undefined {
    return this.body.retry_after_seconds;
  }
}

/** The endpoint exists but the feature is not built yet. */
export class SparkNotAvailableError extends SparkError {}

/** Spark failed to handle the request. Safe to retry. */
export class SparkServerError extends SparkError {}

export interface SparkOptions {
  apiKey?: string;
  baseUrl?: string;
  timeoutMs?: number;
  maxRetries?: number;
  /** Injectable for tests. Defaults to global fetch. */
  fetch?: typeof globalThis.fetch;
}

const DEFAULT_BASE_URL = "https://spark.spacesdrive.cc";

/**
 * Read an environment variable without depending on Node's type definitions,
 * so the SDK also compiles and runs in edge runtimes that have no `process`.
 */
function envVar(name: string): string {
  const proc = (globalThis as any).process;
  return proc?.env?.[name] ?? "";
}

export class Spark {
  readonly baseUrl: string;
  readonly risk: RiskResource;

  private apiKey: string;
  private timeoutMs: number;
  private maxRetries: number;
  private fetchImpl: typeof globalThis.fetch;

  constructor(options: SparkOptions = {}) {
    const key = options.apiKey ?? envVar("SPARK_API_KEY");
    if (!key) {
      throw new SparkAuthError(
        "No API key. Pass apiKey or set the SPARK_API_KEY environment variable.",
        { reason: "missing_api_key" },
      );
    }
    this.apiKey = key;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? 30000;
    this.maxRetries = options.maxRetries ?? 2;
    this.fetchImpl = options.fetch ?? globalThis.fetch;
    this.risk = new RiskResource(this);
  }

  /** True for a test key. Test keys never touch production state. */
  get isTestMode(): boolean {
    return this.apiKey.startsWith("sk_test_");
  }

  /** Deliberately omits the key, so logging a client cannot leak it. */
  toJSON() {
    return { baseUrl: this.baseUrl, mode: this.isTestMode ? "test" : "live" };
  }

  async request<T = any>(method: string, path: string, body?: unknown): Promise<T> {
    let lastError: SparkError | undefined;

    for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);
      let response: Response;

      try {
        response = await this.fetchImpl(`${this.baseUrl}${path}`, {
          method,
          signal: controller.signal,
          headers: {
            Authorization: `Bearer ${this.apiKey}`,
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
      } catch (cause) {
        lastError = new SparkError(`Could not reach Spark at ${this.baseUrl}.`, {
          reason: "connection_failed",
        });
        if (attempt < this.maxRetries) {
          await this.backoff(attempt);
          continue;
        }
        throw lastError;
      } finally {
        clearTimeout(timer);
      }

      const text = await response.text();
      let parsed: any = null;
      try {
        parsed = text ? JSON.parse(text) : null;
      } catch {
        parsed = null;
      }

      if (response.ok) return parsed as T;

      const error = toError(response.status, parsed);
      const retryable = response.status === 429 || response.status >= 500;
      if (retryable && attempt < this.maxRetries) {
        lastError = error;
        await this.backoff(attempt, error);
        continue;
      }
      throw error;
    }

    throw lastError ?? new SparkError("Request failed.");
  }

  private async backoff(attempt: number, error?: SparkError): Promise<void> {
    const hinted =
      error instanceof SparkRateLimitError ? error.retryAfterSeconds : undefined;
    // Exponential backoff with jitter, so retries do not synchronise.
    const seconds = hinted ?? Math.pow(2, attempt) * 0.5 + Math.random() * 0.25;
    await new Promise((r) => setTimeout(r, Math.min(seconds, 30) * 1000));
  }
}

function toError(status: number, parsed: any): SparkError {
  const detail =
    parsed && typeof parsed.detail === "object" && parsed.detail !== null
      ? parsed.detail
      : parsed ?? {};
  const opts = {
    statusCode: status,
    reason: detail.reason,
    body: detail,
  };
  const message = detail.message ?? `Spark returned HTTP ${status}.`;

  if (status === 401 || status === 403) return new SparkAuthError(message, opts);
  if (status === 429) return new SparkRateLimitError(message, opts);
  if (status === 501) return new SparkNotAvailableError(message, opts);
  if (status >= 500) return new SparkServerError(message, opts);
  return new SparkRequestError(message, opts);
}

class RiskResource {
  // Declared explicitly rather than as a constructor parameter property,
  // because that syntax is not erasable and some build setups reject it.
  private readonly client: Spark;

  constructor(client: Spark) {
    this.client = client;
  }

  async score(params: ScoreParams): Promise<ScoreResult> {
    const body: Record<string, unknown> = {
      amount: params.amount,
      customer_id: params.customerId,
      merchant_id: params.merchantId,
      explain: params.explain ?? true,
    };
    if (params.transactionId !== undefined) body.transaction_id = params.transactionId;
    if (params.location !== undefined) body.location = params.location;
    if (params.paymentType !== undefined) body.payment_type = params.paymentType;
    if (params.mode !== undefined) body.mode = params.mode;

    const d = await this.client.request<Record<string, any>>(
      "POST",
      "/api/v1/risk/score",
      body,
    );
    return {
      transactionId: d.transaction_id,
      amount: d.amount,
      customerId: d.customer_id,
      merchantId: d.merchant_id,
      riskScore: d.risk_score,
      riskBand: d.risk_band,
      decision: d.decision,
      mode: d.mode,
      modelId: d.model_id,
      modelVersion: d.model_version,
      path: d.path,
      reviewThreshold: d.review_threshold,
      blockThreshold: d.block_threshold,
      latencyMs: d.latency_ms,
      reasons: d.reasons ?? [],
      notes: d.notes ?? [],
      raw: d,
    };
  }
}
