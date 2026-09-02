/**
 * The measured results for a model, wherever they happen to live.
 *
 * Custom models carry their own `metrics` blob. The built-in model does not:
 * its evaluation lives in the pipeline report behind `/api/metrics/overview`,
 * and only `held_out_pr_auc` is repeated on the model record itself.
 *
 * That difference caused the same bug twice. Both the model drawer and the
 * training page read `model.metrics` directly, so for the built-in model every
 * field except PR-AUC fell through to "not measured" while the real numbers sat
 * on another endpoint. Fixing it in one of those two places left the other
 * wrong, so the lookup lives here now and both call it.
 */

import { useMemo } from "react";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import type { CustomModelMetrics, ModelInfo } from "@/types";

export interface ModelEvaluation {
  test: Partial<NonNullable<CustomModelMetrics["test"]>>;
  balanced: Partial<NonNullable<CustomModelMetrics["balanced"]>>;
  metrics: CustomModelMetrics;
  /** Rows the model was fitted on, from whichever field carries it. */
  rows: number | null;
  loading: boolean;
}

export function useModelEvaluation(model: ModelInfo | null): ModelEvaluation {
  // Only the built-in model needs the pipeline report; a custom model already
  // carries everything it was measured on.
  const builtin = model?.kind === "builtin";
  const report = useAsync(
    () => (builtin ? api.metrics.overview() : Promise.resolve(null)),
    [builtin]
  );

  return useMemo(() => {
    const metrics = (model?.metrics ?? {}) as CustomModelMetrics;
    const split = report.data?.splits.find((s) => s.split === "test");
    const point =
      report.data?.operating_points.find((o) => o.mode === "balanced") ??
      report.data?.operating_points[0];

    return {
      metrics,
      // The model's own numbers win; the report fills the gaps behind them.
      test: {
        ...(split ? { pr_auc: split.pr_auc, roc_auc: split.roc_auc, n: split.n } : {}),
        ...(metrics.test ?? {}),
        ...(model?.held_out_pr_auc != null && !metrics.test?.pr_auc
          ? { pr_auc: model.held_out_pr_auc }
          : {}),
      },
      balanced: {
        ...(point
          ? {
              precision: point.precision,
              recall: point.recall,
              f1: point.f1,
              fpr: point.fpr,
            }
          : {}),
        ...(metrics.balanced ?? {}),
      },
      rows: metrics.n_labeled ?? model?.training_rows ?? null,
      loading: report.loading,
    };
  }, [model, report.data, report.loading]);
}
