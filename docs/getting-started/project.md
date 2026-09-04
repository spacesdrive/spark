# How the project works

The whole system, start to finish.

```
Data
  |
Cleaning
  |
Features
  |
Graph
  |
Model
  |
Risk score
  |
Decision
  |
Evaluation
```

## Data

The input is one CSV file with 77,881 payment transactions.

Each row has: when it happened, which customer paid, which merchant received,
how much, where, which payment channel, and whether it was fraud.

38% of rows have a fraud label. The rest are unknown. That is normal: a real
merchant only ever confirms a fraction of its traffic.

Code: `ml/data/loader.py`

## Cleaning

Before anything else, the file is checked:

- Are all the columns there?
- Are the types right?
- Any missing values?
- Are the labels only 0, 1, or 2?
- Any negative amounts?
- Is the time column sorted?

Problems that make the results meaningless stop the run. Problems the pipeline
can handle print a warning. For example, 6,812 rows have an amount of zero.
Those are kept, with a warning.

Rows are then sorted by time and split:

- First 70% for training.
- Next 15% for validation.
- Last 15% for the final test.

The split is by time, never random. Random splitting would let the model learn
from transactions that happen after the ones it is being tested on.

Code: `ml/data/loader.py`

## Features

The system turns 6 raw columns into about 144 values.

It walks through the transactions in time order. For each one it writes the
features first, then adds that transaction to the running totals. So a
transaction is described only by what came before it.

Two groups come out:

**Base features** use no fraud labels. Amounts, counts in recent windows, how
long since this account was last active, how many different merchants it
touched, how unusual the amount is for this customer.

**Risk features** use fraud labels, but only outcomes that were already
confirmed. For example, how often this merchant has been confirmed as fraud so
far.

The risk features also wait. A fraud label only becomes usable after a delay,
because in real life a chargeback arrives weeks after the payment.

Code: `ml/features/causal.py`

## Graph

Each transaction is a point in a graph. Two points are connected if they share
a customer, a merchant, a location, or a payment channel.

```
Transaction 1
     |
     |  same merchant
     |
Transaction 2
     |
     |  same customer
     |
Transaction 3
```

Two rules:

1. Connections only point from older to newer. A transaction sees its past,
   never its future.
2. Very common values do not create connections. One location appears in
   16,912 transactions. Connecting all of them would add millions of useless
   links.

The result is 278,251 connections across 77,881 points.

Code: `ml/graph/build.py`

## Model

Four scores are produced for every transaction.

**Tree model.** LightGBM on the base features. Fast, good on table data, and it
can explain itself.

**Graph model.** A small neural network. For each transaction it averages its
neighbours' features and mixes that with its own. It sees the base features,
the risk features, and counts of confirmed fraud nearby.

**Behavioural score.** How unusual this is for this account. No labels used.

**Velocity score.** How fast and how concentrated the activity is. No labels
used.

The last two exist because the first two need history. When fraud labels arrive
late, these keep working.

Code: `ml/models/`

## Risk score

The four scores are combined with weights:

```
risk = 0.267 * tree + 0.561 * graph + 0.000 * behavioural + 0.172 * velocity
```

Those weights were searched on the validation data. 400 combinations were
tried, and the best one was kept. They are not hand-picked.

The combined number is then calibrated. Calibration bends the score so that it
lines up with the real chance of fraud. Without it, a 0.7 is just "higher than
0.6" and does not mean 70%.

Code: `ml/calibration/fuse.py`

## Ring detection

This runs separately and uses no fraud labels at all.

A cell is one combination of merchant, payment channel, and location inside a
time window. If many different accounts use the same cell in a short burst,
that is a candidate ring.

Cells that share a lot of accounts get merged into one ring.

Each ring gets a score from five things that were measured to separate fraud
from normal traffic in this data:

| Signal | Fraud-heavy typical | Normal typical |
| ------ | ------------------- | -------------- |
| Accounts per transaction | 0.84 | 0.38 |
| How tightly packed in time | 0.029 | 0.008 |
| Number of accounts | 58 | 13 |
| How similar the amounts are | more similar | more varied |
| Average amount | 4.67 | 59.81 |

The last two together are the sign of card testing: lots of small, nearly
identical payments to check whether stolen card details work.

Code: `ml/graph/rings.py`

## Decision

The risk score becomes one of three actions:

```
score < review threshold                     APPROVE
review threshold <= score < block threshold  REVIEW
score >= block threshold                     BLOCK
```

The thresholds are chosen by cost, on the validation data. The system tries
many cut-off points and picks the one where the total expected cost is lowest.

Cost includes:

- Blocking a good customer: 25.0
- Missing fraud: the full amount, plus 15.0
- A human review: 3.0, and it catches 80% of the fraud sent to it

Three settings are produced: balanced, high precision, and high recall. All
three are picked on validation and then applied to the test data unchanged.

Code: `ml/evaluation/metrics.py`

## Evaluation

The test data is read in exactly one file, after everything else is frozen.

It reports:

- Scores on train, validation, and test, so you can see the drop.
- Each of the four models separately.
- All three threshold settings.
- What it would cost in money.
- Whether the calibrated scores match reality.
- Whether the score distribution has moved.
- How it does on merchants it barely knew.
- Ring detection results.

There is also a safety test that fails the build if the test score is above
0.999. On messy real data, a near perfect score means a bug, not success.

Code: `ml/evaluation/evaluate.py`

## Where things are saved

```
data/raw/         the downloaded CSV
data/processed/   cached features
artifacts/        trained models, thresholds, rings, metadata
reports/          evaluation results, timings, decision log
```
