# SDKs

Two clients, one API contract. Neither contains any risk logic: they send the
request and report what Spark answered, so an SDK can never disagree with the
model.

| SDK | Status | Location |
| --- | --- | --- |
| Python | Available | `sdk/python` |
| Node and TypeScript | Available | `sdk/node` |
| Go, Ruby, PHP, Java | Upcoming | not started |

Both are tested. The Python tests drive the SDK against the real running API;
the Node tests drive the real SDK source with a stubbed transport.

## A note on the import name

The Python package imports as `spark_sdk`, not `spark`. This repository already
ships a `spark` package containing the model training code, and two packages
with the same name would shadow each other.

## Python

### Install

```bash
pip install -e sdk/python
```

### Use

```python
import os
from spark_sdk import Spark

client = Spark(api_key=os.environ["SPARK_TEST_API_KEY"])

result = client.risk.score(
    transaction_id="txn_123",
    amount=1499,
    customer_id="customer_42",
    merchant_id="merchant_7",
)

print(result.decision)      # APPROVE, REVIEW or BLOCK
print(result.risk_score)    # 0.0 to 1.0
print(result.risk_band)     # LOW, MEDIUM or HIGH
```

The key is read from `SPARK_API_KEY` when you do not pass one, so it never has
to appear in your source.

### Errors

Every failure has its own type, and each carries the machine readable `reason`
the API returned, so you branch on that rather than on English text.

```python
from spark_sdk import (
    SparkAuthError, SparkRequestError, SparkRateLimitError,
    SparkNotAvailableError, SparkServerError, SparkError,
)

try:
    result = client.risk.score(amount=1499, customer_id="c", merchant_id="m")
except SparkRequestError as exc:
    for field in exc.fields:
        print(field["field"], field["problem"])
except SparkRateLimitError as exc:
    time.sleep(exc.retry_after_seconds or 1)
except SparkAuthError:
    ...   # key missing, revoked or not allowed here
except SparkError:
    ...   # catches everything above
```

| Status | Exception |
| --- | --- |
| 401, 403 | `SparkAuthError` |
| 400, 422 | `SparkRequestError` |
| 429 | `SparkRateLimitError` |
| 501 | `SparkNotAvailableError` |
| 500 and above | `SparkServerError` |

### Retries and timeouts

Connection failures, 429 and 5xx are retried with exponential backoff and
jitter. A rejected request is never retried, because sending it again cannot
change the answer.

```python
client = Spark(api_key=..., timeout=10.0, max_retries=3)
```

### Reading the result

```python
result.decision                  # APPROVE, REVIEW or BLOCK
result.is_blocked                # decision == "BLOCK"
result.needs_review              # decision == "REVIEW"
result.scored_without_history    # nothing was known about any party
result.reasons                   # what moved the score, in words
result.review_threshold          # the cut this decision was made against
result.block_threshold
result.raw                       # everything the server sent
```

`scored_without_history` matters. When nothing is known about the customer, the
merchant or the payment type, Spark raises the score to a floor. That floor is
above the block threshold in the balanced setting, so a `BLOCK` on such a
transaction means *unknown*, not *risky*. Treat those differently if you can.

## Node and TypeScript

### Use

```typescript
import { Spark } from "@spark-ai/sdk";

const client = new Spark({ apiKey: process.env.SPARK_API_KEY });

const result = await client.risk.score({
  transactionId: "txn_123",
  amount: 1499,
  customerId: "customer_42",
  merchantId: "merchant_7",
});

console.log(result.decision, result.riskScore);
```

The surface is camelCase; the wire format stays snake_case. The SDK converts
between them so you never have to.

### Errors

```typescript
import { SparkRequestError, SparkRateLimitError } from "@spark-ai/sdk";

try {
  await client.risk.score({ amount: 1499, customerId: "c", merchantId: "m" });
} catch (err) {
  if (err instanceof SparkRequestError) {
    for (const f of err.fields) console.log(f.field, f.problem);
  } else if (err instanceof SparkRateLimitError) {
    await new Promise((r) => setTimeout(r, (err.retryAfterSeconds ?? 1) * 1000));
  }
}
```

The same status to type mapping applies as in Python.

## Fields the SDKs do not have

There is no `currency` parameter and no `timestamp` parameter in either SDK.

The model was fitted on the amount, the parties involved, the payment type and
the location. It has no currency feature and no wall clock feature. Accepting
those values would suggest Spark does something with them, and it would not.
Convert to a single currency before you call, and Spark orders transactions by
arrival.

## Test keys and live keys

```python
client.is_test_mode      # Python
client.isTestMode        # Node
```

A key starting `sk_test_` is a test key. Test keys always resolve to the
built-in model and never touch production state. A live key resolves to the
model your organization approved for production; until one is approved, the
built-in model is used, and the response says so through `model_id`.

## Keeping the key out of your logs

Neither client will print the key. The Python `repr` and the Node `toJSON`
deliberately omit it, so logging a client object cannot leak the credential.
This is covered by a test in both SDKs.

Never put a live key in browser code. Anything shipped to a browser is
readable by anyone who opens it.
