# Evaluation

## Why evaluation matters

A model always looks good on data it has already seen. It can memorise instead
of learning.

So the data is split three ways:

| Split | Used for |
| ----- | -------- |
| Train | Fitting the models |
| Validation | Choosing weights, calibration, and thresholds |
| Test | The final check, read once |

The test split is read in exactly one file, after everything else is frozen.
Nothing is retrained or re-tuned against it.

If you tune against the test data, the test score stops predicting how the
system will behave on new data. It just describes your tuning.

## Metrics

Say the system flagged 100 transactions and 63 were really fraud, while 20 real
frauds slipped through.

**Precision.** Of the transactions we flagged, how many were really fraud.
Higher precision means fewer annoyed real customers.

**Recall.** Of all the fraud, how much we caught. Higher recall means less
money lost.

These two fight each other. Flag everything and recall is perfect but precision
is terrible. Flag nothing and the reverse.

**F1.** One number balancing precision and recall.

**False positive.** A normal transaction we wrongly flagged. Costs a sale and a
customer's goodwill.

**False negative.** Real fraud we missed. Costs the money.

**FPR (false positive rate).** Out of all the normal transactions, what share
did we wrongly flag.

**FNR (false negative rate).** Out of all the fraud, what share did we miss.

**PR-AUC.** How well the model sorts fraud above normal, measured across every
possible threshold. Good when fraud is rare, because it ignores the large
number of easy normal cases.

**ROC-AUC.** How well the model separates the two classes overall. Easier to
score well on than PR-AUC when classes are imbalanced.

**Brier score.** How close the predicted probabilities are to reality. Lower is
better.

**Expected cost.** What running the system would cost in money, adding up
wrong blocks, missed fraud, and review time.

## The cost model

Accuracy alone does not tell you whether a fraud system is worth running. The
cost model does.

```
false positive   25.0 for each good order wrongly blocked
missed fraud     the full transaction amount, plus 15.0
manual review    3.0 each, and it catches 80% of the fraud sent to it
```

Two choices worth explaining:

**Missed fraud scales with the amount.** Losing a 5,000 payment costs far more
than losing a 50 one. Treating them the same, which is the common shortcut,
picks the wrong threshold.

**Review is neither free nor perfect.** It costs money, and 20% of the fraud
sent to review still gets through. Counting review as a save is the easiest way
to make these numbers look better than they are.

Change the costs with environment variables and retrain:

```bash
MS_FALSE_POSITIVE_COST=50 python -m ml.training.train
```

## Results

Held-out test split. 5,100 labeled transactions, 43.9% fraud.

### By split

| Split | Rows | Fraud rate | PR-AUC | ROC-AUC | Brier |
| ----- | ---- | ---------- | ------ | ------- | ----- |
| Train | 20,806 | 0.1237 | 0.6359 | 0.9395 | 0.0670 |
| Validation | 3,737 | 0.1191 | 0.5213 | 0.8823 | 0.0736 |
| Test | 5,100 | 0.4388 | 0.9151 | 0.9473 | 0.1834 |

The test split has a much higher fraud rate because the ring operates there.
That is why its PR-AUC looks higher: PR-AUC depends on how common fraud is, so
these numbers are not directly comparable across splits.

### By model

| Model | Train PR-AUC | Validation PR-AUC | Test PR-AUC |
| ----- | ------------ | ----------------- | ----------- |
| Tree | 0.9140 | 0.4578 | 0.7042 |
| Graph | 0.5036 | 0.5195 | 0.9380 |
| Behavioural | 0.1731 | 0.2028 | 0.7398 |
| Velocity | 0.1843 | 0.1871 | 0.8618 |
| Combined | 0.6359 | 0.5213 | 0.9151 |

The tree model looks best during training and is the weaker of the two learned
models on the held-out test. If I had reported training performance, I would
have drawn the opposite conclusion.

### Threshold settings, on test

| Setting | Block at | Precision | Recall | F1 | FPR | Works on test |
| ------- | -------- | --------- | ------ | -- | --- | ------------- |
| balanced | 0.1402 | 0.6299 | 0.9911 | 0.7703 | 0.4553 | yes |
| high_precision | 0.5135 | 0.3333 | 0.0004 | 0.0009 | 0.0007 | no |
| high_recall | 0.1402 | 0.6299 | 0.9911 | 0.7703 | 0.4553 | yes |

The high precision setting does not work here. Its threshold was chosen
correctly on the validation data, but almost nothing in the test window scores
that high, so it fires on 3 out of 5,100 transactions. The evaluation prints
this as a failure instead of reporting precision on an almost empty set.

### Confusion matrix, balanced setting

| | Predicted fraud | Predicted normal |
| --- | --- | --- |
| **Actually fraud** | 2,218 | 20 |
| **Actually normal** | 1,303 | 1,559 |

### Cost, balanced setting

| | Value |
| --- | --- |
| Loss if there were no system | 55,778.38 |
| Prevented loss | 54,170.31 |
| Loss still getting through | 1,608.07 |
| Total cost of running the system | 34,468.07 |
| Cost per 1,000 transactions | 6,758.45 |
| Net benefit | 21,310.31 |

### Ring detection

Ring detection uses no fraud labels. The alert threshold was chosen on
validation. Precision is checked against the real labels afterwards.

| | Value |
| --- | --- |
| Precision | 0.9189 |
| Recall of test fraud | 0.8963 |
| Lift over base rate | 2.09x |
| Rings alerted | 3 |
| Confirmed transactions covered | 2,183 |

### Stress test: new merchants

| Slice | Rows | Fraud rate | PR-AUC | Precision | Recall |
| ----- | ---- | ---------- | ------ | --------- | ------ |
| Merchants barely seen | 341 | 0.2287 | 0.6091 | 0.2885 | 0.9359 |
| Familiar merchants | 4,759 | 0.4539 | 0.9248 | 0.6564 | 0.9931 |

This is the honest stress test. History features cannot help on a merchant the
system has not seen before, and the gap shows exactly how much the system leans
on knowing an entity already.

### Score drift

PSI between validation and test scores: **0.855**, which counts as a real
shift.

PSI compares two score distributions. Below 0.10 is stable, 0.10 to 0.25 is
worth watching, above 0.25 means it moved.

This is why the high precision setting failed to carry over. In real use you
would recalibrate when this number rises.

## Reproducing

```bash
python -m ml.training.train
python -m ml.evaluation.evaluate
```

Results are also written to `reports/evaluation.json`.

The graph model uses CPU float maths that is not perfectly repeatable, so these
numbers move by about 0.001 between retrains. Everything else is exact.

## Guard against cheating

There is a test that fails the build if the held-out PR-AUC goes above 0.999.

On messy, drifting real data, a near perfect score almost always means a bug:
something is leaking future information into the features. Better to fail
loudly than to publish it.
