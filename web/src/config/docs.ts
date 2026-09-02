/**
 * Documentation links and the short definitions the hover previews show.
 *
 * Every href points at a page that ops/site/build_docs.py actually generates
 * from a file in docs/. A test walks this table and fails on any link whose
 * page is not built, so a definition can never quietly point at a 404.
 *
 * The wording is deliberately plain. These appear next to a number for someone
 * deciding whether to trust it, not in a paper.
 */

const BASE = "https://docs-spark.spacesdrive.cc";

export interface DocEntry {
  href: string;
  text: string;
}

export const DOCS = {
  howItWorks: `${BASE}/project.html`,
  evaluation: `${BASE}/evaluation.html`,
  dataset: `${BASE}/dataset.html`,
  training: `${BASE}/training.html`,
  models: `${BASE}/model.html`,
  api: `${BASE}/api.html`,
  sdk: `${BASE}/sdk.html`,
  auth: `${BASE}/auth.html`,

  precision: {
    href: `${BASE}/evaluation.html`,
    text: "Of the transactions Spark flagged, the share that really were fraud. Low precision means people waste time on false alarms.",
  },
  recall: {
    href: `${BASE}/evaluation.html`,
    text: "Of the fraud that actually happened, the share Spark caught. Low recall means losses get through.",
  },
  prAuc: {
    href: `${BASE}/evaluation.html`,
    text: "How well the model ranks risky transactions above safe ones, across every threshold. It depends on how common fraud is, so it cannot be compared between datasets.",
  },
  rocAuc: {
    href: `${BASE}/evaluation.html`,
    text: "Similar to PR-AUC, but it stays flattering when fraud is rare. PR-AUC is the more honest number here.",
  },
  latency: {
    href: `${BASE}/evaluation.html`,
    text: "Nineteen out of twenty transactions are scored faster than this, measured on one CPU core.",
  },
  riskScore: {
    href: `${BASE}/model.html`,
    text: "A score from 0 to 1. It is calibrated, but it is only a probability of fraud if your traffic resembles the training data. Compare it against the thresholds instead.",
  },
  fpr: {
    href: `${BASE}/evaluation.html`,
    text: "The share of legitimate transactions that were wrongly flagged. This is what your customers feel.",
  },
  fnr: {
    href: `${BASE}/evaluation.html`,
    text: "The share of real fraud that was missed. This is what it costs you.",
  },
  distributionShift: {
    href: `${BASE}/evaluation.html`,
    text: "Whether later traffic looks different from the traffic the thresholds were chosen on. A large shift means the thresholds need refreshing before they are trusted.",
  },
  dataCoverage: {
    href: `${BASE}/dataset.html`,
    text: "How much of your file Spark could actually use, and how many rows had no history to score against.",
  },
  abuseRing: {
    href: `${BASE}/model.html`,
    text: "A group of accounts and merchants that transact together in a pattern one account alone would not produce.",
  },
  modelVersion: {
    href: `${BASE}/model.html`,
    text: "Which trained model produced this result. Custom models are named by your organization; the built-in one is Hybrid V1.",
  },
  coldStart: {
    href: `${BASE}/model.html`,
    text: "Nothing was known about any party to this transaction, so Spark raised the score to a floor. A block here means unknown, not necessarily risky.",
  },
  heldOut: {
    href: `${BASE}/evaluation.html`,
    text: "A slice of data kept aside and read once, after every weight and threshold was already fixed. It is the only honest estimate of new-data behaviour.",
  },
} as const;
