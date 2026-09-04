# API

Everything Spark exposes over HTTP.

A generated reference lives at `/api/docs` when the server is running. This page
adds what a generated reference cannot: why each endpoint exists and what its
answers mean.

## Two ways in

| Prefix | For | Authentication |
| ------ | --- | -------------- |
| `/api/...` | The dashboard | A session cookie, or nothing at all |
| `/api/v1/...` | Your servers | `Authorization: Bearer sk_test_...` |

Both call the same engine, so what a developer sees in the sandbox is what
their server gets.

## Scoring one transaction

```bash
curl -X POST https://spark.spacesdrive.cc/api/v1/risk/score \
  -H "Authorization: Bearer sk_test_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "txn_000123",
    "amount": 4.5,
    "customer_id": "cust_8813",
    "merchant_id": "merch_204",
    "location": "IN-KA",
    "payment_type": "upi"
  }'
```

### Request

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `amount` | yes | The transaction value. Must not be negative |
| `customer_id` | yes | Who paid |
| `merchant_id` | yes | Who was paid |
| `transaction_id` | no | Your reference. Generated if omitted |
| `location` | no | Recorded as `unknown` if omitted |
| `payment_type` | no | Recorded as `unknown` if omitted |
| `mode` | no | `balanced`, `high_precision` or `high_recall`. Default `balanced` |
| `explain` | no | Include the explanation. Default `true` |

There is no field for a device fingerprint, an IP address or a card number. The
data the model was trained on has none of them, so accepting them would mean
collecting information the model cannot use.

### Response

```json
{
  "transaction_id": "txn_000123",
  "risk_score": 0.2143,
  "risk_band": "HIGH",
  "decision": "BLOCK",
  "mode": "balanced",
  "model_id": "hybrid-v1",
  "model_version": "spark-hybrid-v1",
  "path": "MODEL",
  "review_threshold": 0.0771,
  "block_threshold": 0.1402,
  "channel_scores": {
    "tabular": 0.0392,
    "graph": 0.8789,
    "behavioral": 0.4252,
    "velocity": 0.0603
  },
  "channel_attribution": { "tabular": 0.02, "graph": 0.96, "behavioral": 0.0, "velocity": 0.02 },
  "reasons": [
    {
      "text": "account has 2 prior transactions",
      "direction": "increases",
      "contribution": 0.571,
      "feature": "Source_txn_count"
    }
  ],
  "entity_history": {
    "Source": { "role": "customer account", "prior_transactions": 2, "is_new": false }
  },
  "graph_evidence": {
    "Target": [
      {
        "transaction_id": "txn_071557",
        "time": 71557,
        "amount": 7.0,
        "source": "S38165",
        "target": "T1822",
        "relation": "Same merchant",
        "outcome": "fraud"
      }
    ]
  },
  "related_ring": null,
  "stages": [{ "name": "Building features", "ms": 2.02 }],
  "latency_ms": 20.6,
  "notes": []
}
```

Fields worth explaining:

**`risk_score`** is calibrated, so it is meant to track the real chance of fraud
rather than just being a ranking.

**`path`** is `MODEL` or `COLD_START`. `COLD_START` means the customer, the
merchant and the channel all had almost no history, so the score was raised to a
minimum instead of trusting a confident model output on no evidence.

**`channel_attribution`** is weight times score, normalised. It says what moved
the final number, which is not always what moved the tree model.

**`reasons`** come from SHAP over the tree model. They are worded as
contribution, never as cause, because a declined customer may challenge the
decision.

**`graph_evidence`** lists real earlier transactions. Every one is older than the
transaction being scored, because the graph only builds backward edges. An empty
object means nothing earlier shared any detail, which is normal for a new
customer.

**`related_ring`** is not ring membership. The ring detector runs over completed
time windows, so a transaction that has just arrived was in none of them. What
this says is that the merchant or channel appears in a group already flagged.

**`stages`** are the steps the server actually ran, with real timings.

**`notes`** explain what a missing optional field did.

## Endpoints

### Public

| Method | Path | What it does |
| ------ | ---- | ------------ |
| GET | `/api/health` | Whether the API, the model and the database are working |
| GET | `/api/config` | What the browser needs to start. No private credentials |
| POST | `/api/risk/score` | Score one transaction. Rate limited, no key |
| GET | `/api/risk/thresholds` | The three settings, and whether each still works |
| GET | `/api/models` | Models available to the caller |
| GET | `/api/models/{id}` | One model, with its weights and thresholds |
| GET | `/api/metrics/overview` | Measured results, each labelled with its split |
| GET | `/api/metrics/charts` | The same numbers shaped for charts |
| GET | `/api/metrics/limitations` | What those numbers do not cover |
| GET | `/api/metrics/rings` | Abuse-ring detection results |
| GET | `/api/datasets/format` | Which columns Spark needs |
| GET | `/api/datasets/example` | Details of the built-in example dataset |
| POST | `/api/datasets/upload` | Upload a CSV, get the validation result |
| GET | `/api/datasets/{id}` | One dataset you uploaded |
| GET | `/api/datasets/{id}/preview` | The first rows, as the server parsed them |
| POST | `/api/datasets/{id}/validate` | Re-check, optionally with your own mapping |
| POST | `/api/datasets/score` | Queue scoring. Returns a job |
| DELETE | `/api/datasets/{id}` | Delete an upload now |
| GET | `/api/jobs/{id}` | How far a job has got |
| GET | `/api/jobs/{id}/result` | The finished result, rows paged |
| GET | `/api/jobs/{id}/download` | The scored rows as CSV |
| GET | `/api/training/limits` | The training limits this server enforces |

### Signed in

| Method | Path | What it does |
| ------ | ---- | ------------ |
| POST | `/api/auth/session` | Exchange a Supabase token for a session cookie |
| POST | `/api/auth/logout` | End the session on the server |
| GET | `/api/auth/me` | Who the caller is. Guests get `authenticated: false` |
| GET | `/api/organizations` | Organizations you belong to |
| POST | `/api/organizations` | Create one. You become its owner |
| GET | `/api/organizations/{id}` | One organization, with members and stage |
| GET | `/api/organizations/{id}/api-keys` | Your keys, masked |
| POST | `/api/organizations/{id}/api-keys` | Create a key. Secret returned once |
| POST | `/api/api-keys/{id}/rotate` | New secret, old one stops immediately |
| POST | `/api/api-keys/{id}/revoke` | Turn a key off permanently |
| GET | `/api/organizations/{id}/usage` | What your keys have been doing |
| GET | `/api/organizations/{id}/datasets` | Datasets owned by that organization |
| GET | `/api/jobs?organization_id=` | Jobs for one organization |
| POST | `/api/models/{id}/activate` | Use a custom model |
| POST | `/api/models/{id}/deactivate` | Stop using it |
| POST | `/api/training/jobs` | Runs the real checks, then returns 501 |

### With an API key

| Method | Path | What it does |
| ------ | ---- | ------------ |
| POST | `/api/v1/risk/score` | Score one transaction, recorded against your usage |

## Jobs

Scoring a large file takes longer than a request should, so it becomes a job.

```bash
JOB=$(curl -s -X POST http://localhost:8000/api/datasets/score \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"ds_...","mode":"balanced"}' | jq -r .id)

curl -s "http://localhost:8000/api/jobs/$JOB"
```

```json
{
  "id": "job_...",
  "status": "running",
  "stage": "Running the graph model",
  "progress": 0.62,
  "elapsed_seconds": 3.4
}
```

`status` moves through `queued`, `running`, then `succeeded` or `failed`.
`stage` is whatever the work reported. When a step cannot say how far through it
is, the stage changes and the number stays where it was. A bar that climbs on a
timer while the work has stalled is worse than no bar.

A failed job carries the reason in `error`.

## Errors

Every error body has a `message` written for a person and a `reason` your code
can switch on.

```json
{
  "detail": {
    "message": "The amount column contains text that is not a number.",
    "reason": "validation_failed",
    "fix": "Remove currency symbols and thousands separators."
  }
}
```

| Status | Means |
| ------ | ----- |
| 400 | Understood but cannot be done. The body says why |
| 401 | No key, an invalid key, or a revoked one |
| 403 | Signed in but not allowed |
| 404 | Not found, or not yours. Spark does not say which |
| 409 | The job has not finished |
| 410 | The file expired and was deleted |
| 422 | A field was the wrong shape. The body lists which |
| 429 | Too many requests. The body says how long to wait |
| 500 | Something broke. Details go to the server log, not to you |
| 501 | Not built yet |
| 503 | No model loaded, or the evaluation has not been run |

Stack traces are never returned.

## Limits

Set through environment variables, and reported by `GET /api/config` so the
numbers shown in the dashboard are the ones being enforced.

| Limit | Default |
| ----- | ------- |
| Upload size | 25 MB |
| Rows in a test dataset | 100,000 |
| Rows in a training dataset | 200,000 |
| Jobs running at once | 2 |
| Jobs per organization per day | 20 |
| Uploads kept for | 24 hours |
| Scoring requests per minute | 120 |
| Uploads per minute | 10 |

Rate limiting is a fixed window held in memory. That is right for a single API
process, and it is honest about its limits: it does not survive a restart and it
does not coordinate between processes. Running more than one process means
moving it to Redis.

## Security

- Uploaded files are never executed, never unpickled, and stored under a random
  name rather than the one you chose.
- Downloads escape any value a spreadsheet would run as a formula.
- Path traversal is refused even though stored names always come from the
  database.
- API keys are stored as a hash, so a copy of the database does not hand anyone
  a working key.
- Session cookies are `HttpOnly`, and unsafe methods need a matching CSRF
  header.
- No response ever contains a server path, a stack trace or another
  organization's data.
