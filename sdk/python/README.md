# Spark Python SDK

A typed client for the Spark risk API. It performs no risk scoring of its own:
every decision comes from the service.

```bash
pip install -e .
```

```python
import os
from spark_sdk import Spark

client = Spark(api_key=os.environ["SPARK_TEST_API_KEY"])
result = client.risk.score(
    amount=1499, customer_id="customer_42", merchant_id="merchant_7",
)
print(result.decision, result.risk_score)
```

Full documentation, including error types and retry behaviour, is in
[docs/developers/sdk.md](../../docs/developers/sdk.md).
