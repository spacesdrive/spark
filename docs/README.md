# Spark documentation

These pages are the source for the documentation site at
[docs-spark.spacesdrive.cc](https://docs-spark.spacesdrive.cc). The folders
match the navigation groups on that site, so a new page appears in the right
place by being saved in the right folder.

The published URL of a page comes from its filename alone, not its folder, so
moving a page between groups never breaks a link.

## Getting started

| Page | What it covers |
| --- | --- |
| [What Spark is](getting-started/project.md) | The problem, the approach, and what was measured |
| [The dashboard](getting-started/dashboard.md) | Every screen, and what each number means |
| [Command line](getting-started/cli.md) | Running the pipeline end to end |

## Using Spark

| Page | What it covers |
| --- | --- |
| [Your data](using-spark/dataset.md) | Required columns, formats, limits and validation |
| [Training your own model](using-spark/training.md) | Training on your own transactions |
| [The models](using-spark/model.md) | The four channels and how they are fused |
| [Results and limits](using-spark/evaluation.md) | Measured performance, and where it does not hold |

## Developers

| Page | What it covers |
| --- | --- |
| [REST API](developers/api.md) | Every endpoint, with request and response shapes |
| [Python and Node SDKs](developers/sdk.md) | The typed clients |
| [Sign in](developers/auth.md) | Sessions, CSRF and API keys |

## Running it

| Page | What it covers |
| --- | --- |
| [Deployment](operations/deployment.md) | The origin, DNS, TLS and first-time setup |
| [Releases and CI](operations/ci.md) | The GitHub Actions pipeline, and what it needs |

## Building the site

```bash
python ops/site/build_docs.py
```

The result is written to `web/docs-dist/`.
