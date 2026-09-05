# Operations

Everything needed to provision, configure, release and check Spark. Scripts are
grouped by the system they touch, and every Python script is run as a module
from the project root so they can share `ops/paths.py`.

Every provisioning script plans by default and only writes when passed
`--apply`, so running one to see what it would do is always safe.

## Layout

| Folder | What lives there |
| --- | --- |
| `aws/` | The EC2 origin, its Elastic IP and its security group |
| `cloudflare/` | DNS records for the Spark hostnames |
| `supabase/` | The database schema, the dedicated role, and the auth settings |
| `server/` | What runs on the host: bootstrap, TLS, and the environment file |
| `site/` | Building the static documentation site from `docs/` |
| `checks/` | Guards that run before a release |

## Common tasks

Release the current checkout to the origin:

```bash
export SPARK_KEY=path/to/key.pem
bash ops/deploy.sh
```

Build the documentation site into `web/docs-dist/`:

```bash
python -m ops.site.build_docs
```

Check that no secret is about to be committed:

```bash
python -m ops.checks.secret_scan
```

Plan the AWS resources, then create them:

```bash
python -m ops.aws.provision
python -m ops.aws.provision --apply
```

Point DNS at the origin:

```bash
python -m ops.cloudflare.dns <origin-ip> --apply
```

Full first-time setup, in order, is in
[docs/operations/deployment.md](../docs/operations/deployment.md).

## Credentials

Scripts read tokens from the gitignored key directories in the project root
(`.aws-keys`, `.cloudflare-keys`, `.supabase-keys`). Nothing here prints a
credential, writes one into a tracked file, or copies one to the server; the
host keeps its own `.env`, written once by `ops/server/env.py`.
