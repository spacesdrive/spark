/**
 * The shapes the API returns.
 *
 * These mirror `api/validators/` and the controller responses. When a backend field
 * can genuinely be absent, it is optional here too, so the UI has to decide
 * what to show rather than rendering `undefined`.
 */

export type Decision = "APPROVE" | "REVIEW" | "BLOCK";
export type RiskBand = "LOW" | "MEDIUM" | "HIGH";

export interface ApiErrorBody {
  message: string;
  reason?: string;
  fix?: string;
  fields?: { field: string; problem: string }[];
  issues?: DatasetIssue[];
  allowed?: string[];
  detail?: string;
  retry_after_seconds?: number;
  checks_passed?: string[];
}

export interface Health {
  status: "ok" | "degraded";
  environment: string;
  api_version: string;
  auth_configured: boolean;
  model: {
    loaded: boolean;
    available: boolean;
    error: string | null;
    load_seconds: number | null;
    model_version: string | null;
    trained_at: string | null;
  };
  database: { ok: boolean; engine?: string; error?: string };
}

export interface PublicConfig {
  environment: string;
  supabase_url: string;
  supabase_anon_key: string;
  auth_configured: boolean;
  public_domain: string;
  docs_url: string;
  github_repo: string;
  limits: Limits;
}

export interface Limits {
  max_upload_bytes: number;
  max_test_rows: number;
  max_training_rows: number;
  min_training_rows: number;
  max_files_per_upload: number;
  max_training_seconds: number;
  max_concurrent_jobs: number;
  max_jobs_per_org_per_day: number;
  dataset_retention_hours: number;
  accepted_formats: string[];
}

export interface ModelInfo {
  id: string;
  name: string;
  version: string;
  kind: "builtin" | "custom";
  status: string;
  icon: string;
  description: string | null;
  components: string[];
  supports_transaction: boolean;
  supports_dataset: boolean;
  supports_custom: boolean;
  input_format: string;
  modes: string[];
  trained_at: string | null;
  training_rows?: number | null;
  held_out_pr_auc?: number | null;
  metrics?: Record<string, unknown>;
  is_active?: boolean;
  is_production?: boolean;
  promoted_at?: string | null;
  dataset_id?: string | null;
  base_model?: string | null;
  organization_id?: string | null;
  owner: string;
}

export interface ModelList {
  models: ModelInfo[];
  default_model_id: string | null;
  model_available: boolean;
}

export interface Reason {
  text: string;
  direction: "increases" | "decreases";
  contribution: number;
  feature: string;
}

export interface GraphLink {
  transaction_id: string;
  time: number;
  amount: number;
  source: string;
  target: string;
  relation: string;
  outcome: "fraud" | "legitimate" | null;
}

export interface ProcessingStage {
  name: string;
  ms: number;
}

export interface RingSummary {
  cluster_id: string;
  n_accounts: number;
  n_transactions: number;
  total_value: number;
  merchants: string[];
  channels: string[];
  locations: string[];
  risk_score: number;
  confidence: number;
  reasons: string[];
  first_seen: number;
  last_seen: number;
  fan_in: number;
  median_amount: number;
  matched_on?: string;
  precision?: number;
}

export interface ScoreResult {
  transaction_id: string;
  amount: number;
  customer_id: string;
  merchant_id: string;
  location: string;
  payment_type: string;
  risk_score: number;
  risk_band: RiskBand;
  decision: Decision;
  mode: string;
  model_id: string;
  model_version: string;
  path: "MODEL" | "COLD_START";
  review_threshold: number;
  block_threshold: number;
  channel_scores: Record<string, number>;
  channel_attribution: Record<string, number>;
  reasons: Reason[];
  entity_risk: Record<string, number>;
  entity_history: Record<
    string,
    { role: string; prior_transactions: number; is_new: boolean }
  >;
  graph_evidence: Record<string, GraphLink[]>;
  related_ring: RingSummary | null;
  stages: ProcessingStage[];
  latency_ms: number;
  notes: string[];
}

export interface TransactionInput {
  transaction_id?: string;
  amount: number;
  customer_id: string;
  merchant_id: string;
  location?: string;
  payment_type?: string;
  mode?: string;
  explain?: boolean;
}

export interface MetricCard {
  key: string;
  label: string;
  value: number;
  format: "ratio" | "count" | "ms";
  source: string;
  help: string;
}

export interface SplitRow {
  split: string;
  n: number;
  n_positive: number;
  base_rate: number;
  pr_auc: number;
  roc_auc: number;
  brier: number;
  lift_over_base?: number;
}

export interface ChannelRow {
  channel: string;
  train_pr_auc: number;
  val_pr_auc: number;
  test_pr_auc: number;
}

export interface OperatingPoint {
  mode: string;
  selected_on: string;
  rationale: string;
  review_threshold: number;
  block_threshold: number;
  precision: number;
  recall: number;
  f1: number;
  fpr: number;
  fnr: number;
  tp: number;
  fp: number;
  tn: number;
  fn: number;
  n_approve: number;
  n_review: number;
  n_block: number;
  n_predicted_positive: number;
  expected_cost: number;
  net_benefit: number;
  prevented_loss: number;
  transfers: boolean;
  transfer_note: string;
}

export interface MetricsOverview {
  model_version: string;
  cards: MetricCard[];
  splits: SplitRow[];
  channels: ChannelRow[];
  operating_points: OperatingPoint[];
  drift: {
    reference: string;
    current: string;
    psi: number;
    status: string;
    implication: string;
    reference_mean: number;
    current_mean: number;
  };
  cost: Record<string, number | null>;
  glossary: Record<string, string>;
  measured_on: string;
}

export interface MetricsCharts {
  decision_distribution: { decision: string; count: number }[];
  model_performance: { metric: string; value: number }[];
  channel_performance: ChannelRow[];
  calibration: {
    bin: string;
    n: number;
    mean_predicted: number;
    observed_rate: number;
    gap: number;
  }[];
  cost_sweep: Record<string, number>[];
  stress_slices: Record<string, number | string>[];
  radar: { axis: string; value: number; measured: string }[];
  radar_note: string;
  latency: {
    per_transaction: Record<string, number>;
    with_explanation: Record<string, number>;
    batch_throughput_per_s: number;
  } | null;
}

export interface Limitation {
  title: string;
  detail: string;
  value?: number;
}

export interface RingReport {
  n_candidate_rings: number;
  threshold_selected_on_validation: number;
  validation_sweep: Record<string, number>[];
  test: {
    rings_alerted: number;
    confirmed_transactions_covered: number;
    confirmed_fraud_captured: number;
    precision: number;
    recall_of_test_fraud: number;
    test_base_rate: number;
    lift_over_base: number;
  };
  top_rings: RingSummary[];
  how_it_works: string;
}

export interface DatasetIssue {
  column: string;
  problem: string;
  fix: string;
  severity: "error" | "warning";
  examples: string[];
}

export interface DatasetValidation {
  ok: boolean;
  n_rows: number;
  columns: string[];
  mapping: Record<string, string>;
  missing_required: string[];
  missing_recommended: string[];
  has_labels: boolean;
  label_counts: Record<string, number>;
  issues: DatasetIssue[];
  preview: Record<string, string>[];
  time_kind: string;
  notes: string[];
}

export interface DatasetRecord {
  id: string;
  original_name: string;
  kind: "test" | "training";
  size_bytes: number;
  n_rows: number;
  columns: string[];
  has_labels: boolean;
  status: string;
  created_at: string;
  expires_at: string | null;
  validation: DatasetValidation;
}

export interface ColumnReference {
  column: string;
  label: string;
  requirement: "required" | "recommended" | "optional";
  why: string;
  example: string;
  accepted_names: string[];
}

export interface DatasetFormat {
  accepted_formats: string[];
  encoding: string;
  columns: ColumnReference[];
  limits: Limits;
  label_meaning: Record<string, string>;
  example_csv: string;
  notes: string[];
}

export interface ExampleDataset {
  id: string;
  name: string;
  description: string;
  caution: string;
  source: string;
  simulated: boolean;
  rows: number;
  labeled: number;
  splits: Record<string, number | string>[];
  columns: ColumnReference[];
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string;
  progress: number;
  dataset_id: string | null;
  model_id: string | null;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  elapsed_seconds: number | null;
  has_result: boolean;
}

export interface ScoredRow {
  transaction_id: string;
  amount: number;
  customer_id: string;
  merchant_id: string;
  risk_score: number;
  risk_band: RiskBand;
  decision: Decision;
  path: string;
  model_version: string;
  score_tabular: number;
  score_graph: number;
  score_behavioral: number;
  score_velocity: number;
  label: number | null;
}

export interface DatasetEvaluation {
  n: number;
  n_fraud: number;
  base_rate: number;
  pr_auc: number | null;
  roc_auc: number | null;
  brier: number | null;
  precision: number;
  recall: number;
  f1: number;
  fpr: number;
  fnr: number;
  confusion: { tp: number; fp: number; tn: number; fn: number };
  cost: Record<string, number>;
}

export interface JobResult {
  mode: string;
  review_threshold: number;
  block_threshold: number;
  model_version: string;
  n_rows: number;
  n_labeled: number;
  rows: ScoredRow[];
  row_count: number;
  offset: number;
  limit: number;
  summary: {
    n: number;
    risk_bands: Record<RiskBand, number>;
    decisions: Record<Decision, number>;
    mean_risk: number;
    median_risk: number;
    histogram: { bucket: string; from: number; to: number; count: number }[];
  };
  evaluation: DatasetEvaluation | null;
  graph: { nodes: number; edges: number; by_relation: Record<string, number> };
  job: Job;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  role: "owner" | "admin" | "member";
  onboarding_stage: string;
  production_model_id: string | null;
  created_at: string;
}

export interface OrganizationDetail extends Organization {
  members: {
    user_id: string;
    email: string;
    display_name: string | null;
    avatar_url: string | null;
    role: string;
  }[];
  onboarding: { stages: string[]; current: string; current_index: number };
}

export interface ApiKey {
  id: string;
  name: string;
  mode: "test" | "live";
  masked: string;
  active: boolean;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  secret: string;
  warning: string;
}

export interface UsageReport {
  total_requests: number;
  /** Requests recorded before the scoring model was tracked. */
  unattributed_requests?: number;
  /** The model these counts were narrowed to, when one was asked for. */
  model_id?: string | null;
  window_requests: number;
  decisions: Record<Decision, number>;
  high_risk: number;
  blocked_amount: number;
  blocked_amount_note: string;
  recent: {
    id: string;
    endpoint: string;
    mode: string;
    decision: Decision | null;
    risk_score: number | null;
    amount: number | null;
    latency_ms: number | null;
    status_code: number;
    created_at: string;
  }[];
}

export interface CurrentUser {
  authenticated: boolean;
  user: {
    id: string;
    email: string;
    display_name: string | null;
    avatar_url: string | null;
    created_at?: string;
  } | null;
  organizations: Organization[];
  csrf_token: string | null;
}

/**
 * The training limits endpoint returns the shared limit set plus these extras.
 * Every field is optional because a server that does not send one should
 * degrade the panel, not crash the page.
 */
export interface TrainingLimits extends Partial<Limits> {
  max_model_bytes?: number;
  requires_labels: boolean;
  status: string;
  status_note: string;
}

export interface ThresholdRow {
  mode: string;
  review_threshold: number;
  block_threshold: number;
  selected_on: string;
  rationale: string;
  test_precision: number | null;
  test_recall: number | null;
  test_f1: number | null;
  test_alerts: number | null;
  transfers_to_test: boolean | null;
}

/** What POST /training/jobs returns once a real job has been queued. */
export interface TrainingStarted {
  job: Job;
  model_id: string;
  note: string;
}

/** What POST /models/{id}/promote returns. */
export interface PromoteResult {
  promoted: boolean;
  unchanged?: boolean;
  model: ModelInfo;
  previous_model_id?: string | null;
  note?: string;
}

/**
 * What POST /organizations/{id}/rollback returns.
 *
 * ``to_model_id`` is null when there was no earlier custom model, which means
 * production is back on the built-in model. That is a real outcome, not a
 * failure, and the note says so.
 */
export interface RollbackResult {
  rolled_back: boolean;
  from_model_id: string;
  to_model_id: string | null;
  note: string;
}

/** Held-out results recorded against a custom model when training finished. */
export interface CustomModelMetrics {
  measured_on?: string;
  n_rows?: number;
  n_labeled?: number;
  test?: {
    n?: number;
    n_positive?: number;
    base_rate?: number;
    pr_auc?: number;
    roc_auc?: number;
    brier?: number;
  };
  balanced?: {
    precision?: number;
    recall?: number;
    f1?: number;
    fpr?: number;
    fnr?: number;
    review_threshold?: number;
    block_threshold?: number;
  };
  trained_at?: string;
  model_version?: string;
  total_train_seconds?: number;
}
