# CLI guide

Every command in the project, in the order you would run them.

## Installation

You need Python 3.10 or newer.

```bash
git clone https://github.com/spacesdrive/spark.git
cd spark
pip install -r requirements.txt
```

No GPU is needed. Everything runs on CPU.

## Get the data

```bash
python -m spark.data.fetch
```

Downloads the S-FFSD dataset and puts `S-FFSD.csv` in `data/raw/`. It is a
small public file and needs no login.

Options:

```bash
python -m spark.data.fetch --force     # download again even if the file exists
```

## Look at the data

```bash
python -m spark.data.inspect
```

Prints the columns, how many rows are labeled, the amount range, how many
distinct customers and merchants there are, and which useful fields are
missing. Also shows how the fraud rate changes over time.

Run this first if you want to understand the dataset before anything else.

## Prepare data

```bash
python -m spark.data.prepare
```

Loads the CSV, checks it, splits it by time, and builds all the features. The
result is cached, so running it again is fast.

Options:

```bash
python -m spark.data.prepare --no-cache    # rebuild from scratch
python -m spark.data.prepare --json        # machine readable output
```

## Build features

```bash
python -m spark.features.build
```

Shows what was built: how many features, which group each belongs to, and a
check that features only look at the past.

The check prints something like:

```
causality check
first row history features: 12 checked
non-zero among them:   0 (expected 0)
  PASS
```

The first transaction has no history, so every history feature must be zero.
If it is not, something is reading the future.

## Train

```bash
python -m spark.models.train
```

Runs the whole pipeline in order and saves everything to `artifacts/`:

1. Prepare the data.
2. Build the graph.
3. Train the tree model.
4. Train the graph model.
5. Fit the two simple scores.
6. Search the combining weights.
7. Calibrate.
8. Pick the thresholds.
9. Find rings.

Takes about 70 seconds. The test split is not touched here.

Options:

```bash
python -m spark.models.train --quiet
python -m spark.models.train --artifacts my_folder
```

## Evaluate

```bash
python -m spark.models.evaluate
```

Runs the held-out test. This is the only place the test data is read. Nothing
is retrained or re-tuned.

Prints:

- Scores for train, validation, and test.
- Each of the four models separately.
- Three operating points.
- The cost of running at each one.
- A calibration table.
- How much the score distribution moved.
- How it does on merchants it barely knew.
- Ring detection results.

Results are also saved to `reports/evaluation.json`.

## Score transactions

```bash
python -m spark.risk.score --split test --limit 5
```

Scores transactions and prints the decision, the reasons, and any ring they
belong to.

Options:

```bash
python -m spark.risk.score --txn txn_070123        # one transaction by id
python -m spark.risk.score --split test --summary  # totals for the whole split
python -m spark.risk.score --highest-risk          # riskiest first
python -m spark.risk.score --mode high_recall      # different threshold setting
python -m spark.risk.score --no-audit              # do not write to the log
```

Modes are `balanced`, `high_precision`, and `high_recall`.

Every decision is appended to `reports/decisions.jsonl` unless you pass
`--no-audit`.

## Detect risk clusters

```bash
python -m spark.clusters.detect --top 10
```

Finds groups of accounts that look coordinated. This uses no fraud labels.

Options:

```bash
python -m spark.clusters.detect --cluster ring_068000_916   # one ring in detail
python -m spark.clusters.detect --min-score 0.7             # only strong ones
python -m spark.clusters.detect --from-artifacts            # use saved results
python -m spark.clusters.detect --json                      # machine readable
```

## Run the demo

```bash
python -m spark.demo
```

Runs everything end to end and prints example decisions, the rings, the test
results, the cost, and the speed.

Options:

```bash
python -m spark.demo --examples 5     # show more worked examples
python -m spark.demo --bench 1000     # time more transactions
python -m spark.demo --skip-eval      # skip the held-out test, faster
```

Shortened example of the output:

```
SPARK  -  ABUSE-RING SENTINEL

1. loading trained model
model version:         spark-hybrid-v1
operating mode:        balanced  (review>=..., block>=...)

2. scoring the held-out test split
transactions scored:   5,100
  APPROVE   ...
  REVIEW    ...
  BLOCK     ...

3. worked examples
Transaction: txn_...
  Risk Score: 0.xxxx
  Decision:   BLOCK
  Contributing factors:
    + ...
  Risk Cluster: ring_...

HELD-OUT TEST RESULTS
Precision:             0.xxxx
Recall:                0.xxxx
PR-AUC:                0.xxxx
...
```

The real numbers are printed when you run it. See the README for the values
measured on this dataset.

## Test the delay assumption

```bash
python -m ml.evaluation.sensitivity
```

Retrains and re-tests the whole pipeline at several chargeback delays. Shows
how much of the result depends on assuming fraud is confirmed quickly.

Takes several minutes because it trains the pipeline once per setting.

## Run the tests

```bash
pytest                    # all 118 tests, about 90 seconds
pytest -m "not slow"      # unit tests only, about 5 seconds
```

The slow tests need the dataset and a trained model. They skip if those are
missing.

## Changing the cost model

Three environment variables change how thresholds are chosen:

```bash
MS_FALSE_POSITIVE_COST=50 python -m spark.models.train
MS_FALSE_NEGATIVE_COST=25 python -m spark.models.train
MS_MANUAL_REVIEW_COST=5 python -m spark.models.train
```

Retrain after changing them, because thresholds are picked during training.

Every other setting lives in `ml/config.py`.

## Typical first run

```bash
pip install -r requirements.txt
python -m spark.data.fetch
python -m spark.data.inspect
python -m ml.training.train
python -m spark.demo
```
