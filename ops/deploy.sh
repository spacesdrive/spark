#!/usr/bin/env bash
#
# Copy Spark to the server and restart it. Run from the project root.
#
# Secrets are never copied. The server keeps its own .env, written once by
# ops/server/env.py, and this script leaves it alone.
set -euo pipefail

HOST=${SPARK_HOST:-13.232.127.102}
KEY=${SPARK_KEY:?set SPARK_KEY to the private key path}
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30"

echo "== building the dashboard locally =="
(cd web && npm run build >/dev/null)

echo "== building the documentation site =="
python -m ops.site.build_docs >/dev/null

echo "== packing =="
TAR=$(mktemp -t spark-XXXX.tar.gz)
tar czf "$TAR" \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' \
  --exclude='web/node_modules' --exclude='data/processed' --exclude='data/uploads' \
  --exclude='data/spark.db' --exclude='.env' --exclude='.venv' \
  --exclude='.aws-keys' --exclude='.cloudflare-keys' --exclude='.supabase-keys' \
  --exclude='reports/decisions.jsonl' \
  api ml spark ops sdk tests artifacts reports data/raw web/dist web/docs-dist \
  requirements.txt requirements-api.txt requirements-ops.txt pyproject.toml README.md docs assets

echo "== uploading $(du -h "$TAR" | cut -f1) =="
$SSH ubuntu@"$HOST" 'sudo mkdir -p /opt/spark && sudo chown -R ubuntu:ubuntu /opt/spark'
cat "$TAR" | $SSH ubuntu@"$HOST" 'tar xzf - -C /opt/spark'
rm -f "$TAR"

echo "== bootstrap =="
$SSH ubuntu@"$HOST" 'bash /opt/spark/ops/server/bootstrap.sh'

echo "== restart =="
# The upload step chowns the tree to ubuntu so tar can write into it. That also
# strips the spark group from .env, and the service then cannot read its own
# environment file, so ownership is put back before the restart.
$SSH ubuntu@"$HOST" 'sudo chown -R spark:spark /opt/spark/data /opt/spark/reports; sudo chown ubuntu:spark /opt/spark/.env; sudo chmod 640 /opt/spark/.env; sudo systemctl restart spark-api; sleep 8; systemctl is-active spark-api'
echo "== health =="
$SSH ubuntu@"$HOST" 'curl -s -m 30 http://127.0.0.1:8000/api/health | head -c 400; echo'
