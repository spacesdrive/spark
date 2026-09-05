# Tests

Grouped by what is under test, so the folder tells you what a failure touches.

| Folder | Covers |
| --- | --- |
| `api/` | HTTP behaviour: endpoints, the model registry, webhooks, insert ordering |
| `ml/` | The pipeline: features, graph, metrics, serving, explanations |
| `sdk/` | The published Python client, driven against the real app |
| `project/` | Repository guards, such as documentation links that must resolve |

## Running them

```bash
python -m pytest                 # everything
python -m pytest tests/api       # one area
python -m pytest -m "not slow"   # skip anything needing artifacts or the raw data
```

Tests marked `slow` need the real dataset or a trained model on disk and skip
themselves when neither is present, so a fresh checkout runs green.

## Fixtures

`conftest.py` holds what more than one area needs: a small hand-checkable
transaction frame containing a deliberate ring, the loaded scoring engine, and
the flags that say whether the raw data and the trained artifacts are present.

It also sets the test environment before any API module is imported. Settings
are read at import time, so that has to happen in `conftest.py` rather than in
the test files.
