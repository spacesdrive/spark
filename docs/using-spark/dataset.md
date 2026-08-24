# Dataset

## Name and source

**S-FFSD**, the Simulated Financial Fraud Semi-supervised Dataset.

It ships inside the [AI4Risk/antifraud](https://github.com/AI4Risk/antifraud)
research repository.

Download it with:

```bash
python -m spark.data.fetch
```

## Why I chose it

- It has payment transactions with fraud labels.
- It has customer, merchant, location, and payment channel IDs, so a graph can
  be built from real connections in the data.
- Transactions are in time order, so I can train on early data and test on
  later data.
- It downloads without an account or a login, so anyone can run this project.
- It actually contains a fraud ring. I checked before building anything.

## Fields

| Field | Meaning |
| ----- | ------- |
| Time | Position in the transaction sequence, 0 to 77,880 |
| Source | Customer account paying |
| Target | Merchant receiving |
| Amount | Transaction amount |
| Location | Where the transaction happened |
| Type | Payment channel or instrument class |
| Labels | 0 normal, 1 fraud, 2 unknown |

## What the fraud label means

| Value | Meaning |
| ----- | ------- |
| 0 | Confirmed normal |
| 1 | Confirmed fraud |
| 2 | Never confirmed either way |

Counts:

| Label | Rows | Share |
| ----- | ---- | ----- |
| 0 normal | 24,387 | 31.3% |
| 1 fraud | 5,256 | 6.7% |
| 2 unknown | 48,238 | 61.9% |

Among labeled rows, 17.7% are fraud.

The unknown rows are not thrown away. They are real traffic, so they still
count towards velocity and still appear in the graph. They are only left out of
model fitting and out of every reported number.

## Size

| | |
| --- | --- |
| Transactions | 77,881 |
| Customer accounts | 30,346 |
| Merchants | 886 |
| Locations | 296 |
| Payment channels | 166 |

## Splits

Split by time, never shuffled.

| Split | Rows | Time range | Labeled | Fraud | Fraud rate |
| ----- | ---- | ---------- | ------- | ----- | ---------- |
| Train | 54,516 | 0 to 54,515 | 20,806 | 2,573 | 0.1237 |
| Validation | 11,682 | 54,516 to 66,197 | 3,737 | 445 | 0.1191 |
| Test | 11,683 | 66,198 to 77,880 | 5,100 | 2,238 | 0.4388 |

### Why the test data is kept separate

If you pick your settings by looking at the test data, the test score stops
meaning anything. It becomes a description of tuning, not a prediction of how
the system will behave on new data.

So:

- Models are fitted on train.
- Weights, calibration, and thresholds are chosen on validation.
- Test is read once, in one file, after everything is frozen.

### Why split by time and not randomly

The fraud rate in this file more than triples from start to end:

| Part of the file | Fraud rate |
| ---------------- | ---------- |
| First tenth | 0.1290 |
| Last tenth | 0.4244 |

A random split would spread the fraud ring across train and test. The model
would then see part of the ring during training and score the rest easily. That
looks great and means nothing.

Splitting by time keeps the ring where it actually happened. It makes the test
harder and honest.

## The ring in this data

Merchant `T1822`:

| | |
| --- | --- |
| Transactions | 1,433 |
| Different accounts | 1,411 |
| Payment channels used | 1 |
| Locations used | 1 |
| Time span | one burst |
| Confirmed fraud | 98.6% |

Almost every transaction comes from a different account. That is the shape of a
ring using throwaway accounts, not a shop with repeat customers.

The same channel `TP110` also carries merchant `T1015` at 82.6% fraud.

## What is missing

The dataset does not have:

| Field | Status |
| ----- | ------ |
| Device ID | Not available |
| IP address | Not available |
| Email or domain | Not available |
| Card number | Not available |
| Real timestamps | Not available, Time is a sequence position |

The system does not invent these. Run `python -m spark.data.inspect` and it
prints a table marking each one.

Device and IP are two of the strongest ring signals in real fraud work.
Without them, this project uses merchant, payment channel, and location
instead.

## Limitations

- **It is simulated.** The generator is not published, so the exact scores
  describe this file, not real payments. The method and the way it is tested
  are what carry over.
- **Time is a sequence position, not a clock.** So "velocity" means
  transactions elapsed, not seconds elapsed.
- **Most rows are unlabeled.** 61.9% never get a confirmed outcome, which
  limits how much can be measured.
- **Amounts are extreme.** Median is 16.61, maximum is 800,000, and 6,812 rows
  are exactly zero.
- **No device or IP**, as above.

## Other datasets I looked at

| Dataset | Why I did not use it |
| ------- | -------------------- |
| IEEE-CIS Fraud Detection | Needs a Kaggle account, and 339 of its columns are anonymised, so explanations would read like "V257 raised the score", which nobody can act on |
| PaySim | The balance columns give away the answer, because fraudulent transfers are cancelled in the simulation |
| YelpChi | Review spam, not payments. No amount, no merchant loss |
| Amazon | Fake reviewer accounts, not payments. The label is a proxy, not confirmed fraud |
| Sparkov, BankSim | Fraud is generated one account at a time, so there are no coordinated groups to find |
