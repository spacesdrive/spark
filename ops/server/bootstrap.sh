#!/usr/bin/env bash
#
# Prepare the Spark host. Runs on the server, as ubuntu, and is safe to rerun.
#
# Everything lives under /opt/spark. The service runs as its own unprivileged
# user with no shell, and nginx is the only thing listening on a public port.
set -euo pipefail

APP=/opt/spark
PY=$APP/.venv/bin/python

echo "== packages =="
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  python3-venv python3-pip nginx rsync ufw >/dev/null

echo "== swap =="
# 1.9 GB of RAM is not much once torch is resident. Swap keeps the first model
# load from being killed by the OOM reaper.
if [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "== service user =="
id spark >/dev/null 2>&1 || sudo useradd --system --home "$APP" --shell /usr/sbin/nologin spark

echo "== virtualenv =="
sudo mkdir -p "$APP"
sudo chown -R ubuntu:ubuntu "$APP"
[ -d "$APP/.venv" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip wheel

echo "== python dependencies =="
# The CPU wheel is a fraction of the default one and Spark never uses a GPU.
"$APP/.venv/bin/pip" install -q torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
"$APP/.venv/bin/pip" install -q -r "$APP/requirements-api.txt"

echo "== directories =="
mkdir -p "$APP/data/uploads" "$APP/data/user_models" "$APP/reports"

echo "== systemd =="
sudo tee /etc/systemd/system/spark-api.service >/dev/null <<UNIT
[Unit]
Description=Spark risk API
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=spark
Group=spark
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5
# The service needs nothing outside its own directory.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP/data $APP/reports

[Install]
WantedBy=multi-user.target
UNIT

sudo chown -R spark:spark "$APP/data" "$APP/reports"
sudo systemctl daemon-reload
sudo systemctl enable -q spark-api

echo "== nginx =="
# Once a certificate exists, ops/server/tls.sh owns this file. Rewriting the
# plain HTTP version here would silently drop the origin back to port 80 on
# every deploy, and Cloudflare would answer 521 because it is set to reach the
# origin over TLS.
# Tested through sudo: /etc/letsencrypt/live is mode 0700 and owned by root, so
# a plain directory test always reports false when running as ubuntu.
if sudo test -d /etc/letsencrypt/live/spark; then
  echo "           certificate present, leaving the TLS site file alone"
  sudo nginx -t
  sudo systemctl reload nginx
  echo "== done =="
  exit 0
fi

sudo tee /etc/nginx/sites-available/spark >/dev/null <<'NGINX'
server {
    listen 80 default_server;
    server_name spark.spacesdrive.cc docs.spark.spacesdrive.cc;

    client_max_body_size 30m;

    # The real client address arrives in a Cloudflare header.
    real_ip_header CF-Connecting-IP;

    root /opt/spark/web/dist;
    index index.html;

    # Named by content hash, so a new build is a new name and these can never
    # go stale.
    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        try_files $uri =404;
    }

    # The shell names the current bundle, so it must be revalidated every time.
    # Without this a browser guessed, and kept an old build for hours.
    location = /index.html {
        add_header Cache-Control "no-cache" always;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
    }

    # The dashboard is a single page application, so unknown paths are routes.
    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/spark /etc/nginx/sites-enabled/spark
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo "== done =="
