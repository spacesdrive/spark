/**
 * The only place that talks to the API.
 *
 * Every call goes through `request`, so timeouts, credentials, the CSRF header
 * and error shaping are handled once. Components never call `fetch`.
 *
 * Errors become an `ApiError` carrying the message the backend wrote. That
 * message is written for people, so the UI can show it directly instead of
 * inventing its own wording.
 */

import type {
  PromoteResult,
  RollbackResult,
  TrainingStarted,
  ApiErrorBody,
  ApiKey,
  ApiKeyCreated,
  CurrentUser,
  DatasetFormat,
  DatasetRecord,
  DatasetValidation,
  ExampleDataset,
  Health,
  Job,
  JobResult,
  Limitation,
  MetricsCharts,
  MetricsOverview,
  ModelList,
  ModelInfo,
  Organization,
  OrganizationDetail,
  PublicConfig,
  RingReport,
  ScoreResult,
  ThresholdRow,
  TrainingLimits,
  TransactionInput,
  UsageReport,
} from "@/types";

const BASE = "/api";
const DEFAULT_TIMEOUT_MS = 30_000;
/** Scoring a dataset can take a while, and the poll should not give up early. */
const LONG_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  status: number;
  body: ApiErrorBody;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }

  get reason(): string | undefined {
    return this.body.reason;
  }

  /** True when signing in would fix this. */
  get needsSignIn(): boolean {
    return this.status === 401 || this.reason === "authentication_required";
  }

  /** True when the feature exists in the plan but is not built yet. */
  get isUpcoming(): boolean {
    return this.status === 501 || this.reason === "upcoming";
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&")}=([^;]*)`)
  );
  return match ? decodeURIComponent(match[1]) : null;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  timeoutMs?: number;
  signal?: AbortSignal;
  raw?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = "GET",
    body,
    formData,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    signal,
    raw = false,
  } = options;

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  if (signal) signal.addEventListener("abort", () => controller.abort());

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";

  // The double-submit CSRF token. Cookie authentication needs it on every
  // unsafe method; the backend ignores it for API-key callers.
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = readCookie("spark_csrf");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal: controller.signal,
    });
  } catch (err) {
    window.clearTimeout(timer);
    if ((err as Error).name === "AbortError") {
      throw new ApiError(408, {
        message: "That request took too long and was stopped.",
        reason: "timeout",
      });
    }
    throw new ApiError(0, {
      message: "Could not reach the Spark server. Is it running?",
      reason: "network",
    });
  }
  window.clearTimeout(timer);

  if (raw) {
    if (!response.ok) throw await toApiError(response);
    return (await response.text()) as T;
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = {
    message: `Spark returned an error (${response.status}).`,
  };
  try {
    const parsed = await response.json();
    const detail = parsed?.detail;
    if (typeof detail === "string") body = { message: detail };
    else if (detail && typeof detail === "object") body = detail as ApiErrorBody;
    else if (parsed?.message) body = parsed as ApiErrorBody;
  } catch {
    // A non-JSON error body means something upstream failed, not the app.
    body = {
      message:
        response.status >= 500
          ? "Spark could not process this request. Check the server logs."
          : `Spark returned an error (${response.status}).`,
    };
  }
  return new ApiError(response.status, body);
}

export const api = {
  health: () => request<Health>("/health"),
  config: () => request<PublicConfig>("/config"),

  models: {
    list: (organizationId?: string) =>
      request<ModelList>(
        `/models${organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : ""}`
      ),
    get: (id: string) => request<ModelInfo>(`/models/${encodeURIComponent(id)}`),
    activate: (id: string) =>
      request<{ activated: boolean; model: ModelInfo }>(
        `/models/${encodeURIComponent(id)}/activate`,
        { method: "POST" }
      ),
    deactivate: (id: string) =>
      request<{ activated: boolean; model: ModelInfo }>(
        `/models/${encodeURIComponent(id)}/deactivate`,
        { method: "POST" }
      ),
    /** Approve for production. Live API keys resolve to this model afterwards. */
    promote: (id: string) =>
      request<PromoteResult>(`/models/${encodeURIComponent(id)}/promote`, {
        method: "POST",
      }),
    reject: (id: string) =>
      request<{ rejected: boolean; model: ModelInfo }>(
        `/models/${encodeURIComponent(id)}/reject`,
        { method: "POST" }
      ),
  },

  risk: {
    score: (payload: TransactionInput) =>
      request<ScoreResult>("/risk/score", { method: "POST", body: payload }),
    thresholds: () =>
      request<{ thresholds: ThresholdRow[] }>("/risk/thresholds"),
  },

  metrics: {
    overview: () => request<MetricsOverview>("/metrics/overview"),
    charts: () => request<MetricsCharts>("/metrics/charts"),
    limitations: () =>
      request<{ limitations: Limitation[] }>("/metrics/limitations"),
    rings: () => request<RingReport>("/metrics/rings"),
  },

  datasets: {
    format: () => request<DatasetFormat>("/datasets/format"),
    example: () => request<ExampleDataset>("/datasets/example"),
    upload: (file: File, kind: "test" | "training", organizationId?: string) => {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", kind);
      if (organizationId) form.append("organization_id", organizationId);
      return request<DatasetRecord>("/datasets/upload", {
        method: "POST",
        formData: form,
        timeoutMs: LONG_TIMEOUT_MS,
      });
    },
    get: (id: string) =>
      request<DatasetRecord>(`/datasets/${encodeURIComponent(id)}`),
    preview: (id: string, rows = 20) =>
      request<{
        columns: string[];
        rows: Record<string, string>[];
        total_rows: number;
      }>(`/datasets/${encodeURIComponent(id)}/preview?rows=${rows}`),
    validate: (id: string, mapping?: Record<string, string>) =>
      request<DatasetValidation>(
        `/datasets/${encodeURIComponent(id)}/validate`,
        { method: "POST", body: mapping ? { mapping } : {} }
      ),
    score: (datasetId: string, mode = "balanced", modelId = "hybrid-v1") =>
      request<Job>("/datasets/score", {
        method: "POST",
        body: { dataset_id: datasetId, mode, model_id: modelId },
      }),
    remove: (id: string) =>
      request<{ deleted: boolean; id: string }>(
        `/datasets/${encodeURIComponent(id)}`,
        { method: "DELETE" }
      ),
    forOrganization: (organizationId: string) =>
      request<DatasetRecord[]>(
        `/organizations/${encodeURIComponent(organizationId)}/datasets`
      ),
  },

  jobs: {
    get: (id: string) => request<Job>(`/jobs/${encodeURIComponent(id)}`),
    result: (id: string, offset = 0, limit = 100) =>
      request<JobResult>(
        `/jobs/${encodeURIComponent(id)}/result?offset=${offset}&limit=${limit}`,
        { timeoutMs: LONG_TIMEOUT_MS }
      ),
    downloadUrl: (id: string) =>
      `${BASE}/jobs/${encodeURIComponent(id)}/download`,
    list: (organizationId: string) =>
      request<{ jobs: Job[] }>(
        `/jobs?organization_id=${encodeURIComponent(organizationId)}`
      ),
  },

  auth: {
    me: () => request<CurrentUser>("/auth/me"),
    session: (accessToken: string) =>
      request<CurrentUser>("/auth/session", {
        method: "POST",
        body: { access_token: accessToken },
      }),
    logout: () =>
      request<{ authenticated: boolean }>("/auth/logout", { method: "POST" }),
  },

  organizations: {
    list: () => request<Organization[]>("/organizations"),
    create: (name: string) =>
      request<Organization>("/organizations", { method: "POST", body: { name } }),
    get: (id: string) =>
      request<OrganizationDetail>(`/organizations/${encodeURIComponent(id)}`),
    keys: (id: string) =>
      request<ApiKey[]>(`/organizations/${encodeURIComponent(id)}/api-keys`),
    createKey: (id: string, name: string, mode: "test" | "live") =>
      request<ApiKeyCreated>(
        `/organizations/${encodeURIComponent(id)}/api-keys`,
        { method: "POST", body: { name, mode } }
      ),
    rotateKey: (keyId: string) =>
      request<ApiKeyCreated>(`/api-keys/${encodeURIComponent(keyId)}/rotate`, {
        method: "POST",
      }),
    revokeKey: (keyId: string) =>
      request<ApiKey>(`/api-keys/${encodeURIComponent(keyId)}/revoke`, {
        method: "POST",
      }),
    usage: (id: string, mode?: string) =>
      request<UsageReport>(
        `/organizations/${encodeURIComponent(id)}/usage${mode ? `?mode=${mode}` : ""}`
      ),
    rollback: (id: string) =>
      request<RollbackResult>(
        `/organizations/${encodeURIComponent(id)}/rollback`,
        { method: "POST" }
      ),
  },


  training: {
    limits: () => request<TrainingLimits>("/training/limits"),
    createJob: (payload: {
      organization_id: string;
      dataset_id: string;
      name: string;
      base_model?: string;
    }) =>
      request<TrainingStarted>("/training/jobs", { method: "POST", body: payload }),
  },

  /** Send an arbitrary request. Used only by the developer sandbox. */
  sandbox: async (
    method: string,
    path: string,
    body: string | undefined,
    apiKey: string
  ): Promise<{ status: number; ms: number; body: unknown }> => {
    const started = performance.now();
    const headers: Record<string, string> = {
      Authorization: `Bearer ${apiKey}`,
    };
    if (body) headers["Content-Type"] = "application/json";
    const response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body || undefined,
    });
    const ms = performance.now() - started;
    let parsed: unknown;
    const text = await response.text();
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
    return { status: response.status, ms, body: parsed };
  },
};

/**
 * Poll a job until it finishes.
 *
 * The callback fires on every tick so the UI can show the real stage. Nothing
 * here estimates progress: it forwards what the backend reported.
 */
export async function pollJob(
  jobId: string,
  onTick: (job: Job) => void,
  options: { intervalMs?: number; timeoutMs?: number } = {}
): Promise<Job> {
  const interval = options.intervalMs ?? 700;
  const deadline = Date.now() + (options.timeoutMs ?? 10 * 60_000);

  for (;;) {
    const job = await api.jobs.get(jobId);
    onTick(job);
    if (job.status === "succeeded" || job.status === "failed") return job;
    if (Date.now() > deadline) {
      throw new ApiError(408, {
        message: "This job is taking longer than expected. It may still be "
          + "running on the server.",
        reason: "poll_timeout",
      });
    }
    await new Promise((resolve) => window.setTimeout(resolve, interval));
  }
}
