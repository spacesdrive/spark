#!/usr/bin/env bash
#
# Put a real certificate on the origin so Cloudflare can reach it over TLS.
#
# The DNS-01 challenge is used rather than HTTP-01 because port 80 is open only
# to Cloudflare's ranges, so Let's Encrypt could never complete an HTTP
# challenge against this host. DNS-01 needs no inbound access at all.
#
# The Cloudflare credentials file is written by the caller over stdin, never by
# this script and never as an argument.
set -euo pipefail

DOMAINS="-d spark.spacesdrive.cc -d docs-spark.spacesdrive.cc"
EMAIL="${CERT_EMAIL:-admin@spacesdrive.cc}"

echo "== certbot =="
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  certbot python3-certbot-dns-cloudflare >/dev/null

test -f /etc/letsencrypt/cloudflare.ini || { echo "missing credentials file"; exit 1; }
sudo chmod 600 /etc/letsencrypt/cloudflare.ini

echo "== certificate =="
sudo certbot certonly --non-interactive --agree-tos --email "$EMAIL" \
  --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  --dns-cloudflare-propagation-seconds 30 \
  $DOMAINS --cert-name spark

echo "== nginx tls =="
sudo tee /etc/nginx/sites-available/spark >/dev/null <<'NGINX'
# Port 80 exists only to redirect. Cloudflare is configured to reach the origin
# over TLS, so nothing should be arriving here in the clear.
server {
    listen 80 default_server;
    server_name spark.spacesdrive.cc docs-spark.spacesdrive.cc;
    return 301 https://$host$request_uri;
}

# The documentation site. Its own static build, generated from the Markdown in
# docs/ by ops/site/build_docs.py, so it is a real documentation site rather than a
# redirect into the dashboard.
server {
    listen 443 ssl http2;
    server_name docs-spark.spacesdrive.cc;

    ssl_certificate     /etc/letsencrypt/live/spark/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/spark/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    real_ip_header CF-Connecting-IP;

    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    root /opt/spark/web/docs-dist;
    index index.html;

    # Static pages only. The documentation host has no reason to reach the API,
    # so it does not proxy to it.
    location / {
        try_files $uri $uri.html $uri/ /index.html;
    }
}

server {
    # This nginx does not accept the newer "http2 on" directive.
    listen 443 ssl http2 default_server;
    server_name spark.spacesdrive.cc;

    ssl_certificate     /etc/letsencrypt/live/spark/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/spark/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 30m;
    real_ip_header CF-Connecting-IP;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    root /opt/spark/web/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 300s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX

sudo nginx -t
sudo systemctl reload nginx
sudo systemctl enable -q certbot.timer
echo "== done =="
