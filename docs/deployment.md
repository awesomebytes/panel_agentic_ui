# Panel Agentic UI — Deployment Guide

**Stack:** Python 3.11 · Panel/Bokeh · FastAPI/uvicorn · Nginx · systemd · Pixi  
**Design:** Single-user, single-session. All FastAPI backends bind to `127.0.0.1` only and are never exposed directly.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Environment Variables](#3-environment-variables)
4. [systemd Service Files](#4-systemd-service-files)
5. [Nginx Reverse Proxy](#5-nginx-reverse-proxy)
6. [go2rtc — RTSP Camera Streams](#6-go2rtc--rtsp-camera-streams)
7. [Prometheus Integration](#7-prometheus-integration)
8. [Grafana Embedding](#8-grafana-embedding)
9. [Backup Strategy](#9-backup-strategy)
10. [Security Notes](#10-security-notes)

---

## 1. Prerequisites

| Component | Minimum version | Notes |
|-----------|----------------|-------|
| Ubuntu/Debian | 22.04 LTS | Other systemd distros work with minor changes |
| Python | 3.11 | Managed by Pixi |
| Pixi | latest | `curl -fsSL https://pixi.sh/install.sh \| bash` |
| Nginx | 1.18+ | `apt install nginx` |
| Certbot | any | For Let's Encrypt TLS — `apt install certbot python3-certbot-nginx` |
| go2rtc | 1.9+ | Optional, only needed for RTSP cameras |

---

## 2. Installation

```bash
# Clone the repository
git clone https://github.com/your-org/panel-agentic-ui.git /opt/panel-agentic-ui
cd /opt/panel-agentic-ui

# Install all dependencies into the Pixi environment
pixi install

# Create a dedicated system user (no login shell, no home dir)
sudo useradd --system --no-create-home --shell /usr/sbin/nologin panel-agentic

# Hand ownership to the service user
sudo chown -R panel-agentic:panel-agentic /opt/panel-agentic-ui

# Create writable runtime directories
sudo -u panel-agentic mkdir -p /opt/panel-agentic-ui/widgets \
                                /opt/panel-agentic-ui/chats \
                                /opt/panel-agentic-ui/notes
```

---

## 3. Environment Variables

All settings are read via `pydantic-settings` using the `MONITOR_` prefix. Place them in `/etc/panel-agentic-ui/env` (restricted to `root:root 600`).

### Complete reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_PANEL_ADDRESS` | `127.0.0.1` | Address Panel/Bokeh server binds to. Keep at `127.0.0.1`; Nginx handles external traffic. |
| `MONITOR_PANEL_PORT` | `5006` | Port Panel/Bokeh server listens on. |
| `MONITOR_TELEMETRY_PORT` | `8001` | Port for the psutil telemetry backend. |
| `MONITOR_COMMANDS_PORT` | `8002` | Port for the allowlisted commands backend. |
| `MONITOR_DATA_PORT` | `8003` | Port for the historical data query backend. |
| `MONITOR_PROMETHEUS_PORT` | `8004` | Port for the PromQL proxy backend. |
| `MONITOR_PROMETHEUS_URL` | `http://localhost:9090` | Upstream Prometheus server URL. |
| `MONITOR_LLM_PROVIDER` | `anthropic` | LLM provider: `anthropic` or `openai`. |
| `MONITOR_LLM_MODEL` | `claude-sonnet-4-20250514` | Model name passed to the provider API. |
| `MONITOR_ANTHROPIC_API_KEY` | _(empty)_ | Anthropic API key. Required if `LLM_PROVIDER=anthropic`. |
| `MONITOR_OPENAI_API_KEY` | _(empty)_ | OpenAI API key. Required if `LLM_PROVIDER=openai`. |
| `MONITOR_GITHUB_TOKEN` | _(empty)_ | GitHub personal access token for the PR-creation workflow. |
| `MONITOR_GITHUB_REPO` | _(empty)_ | Target repo in `owner/name` format (e.g. `your-org/panel-agentic-ui`). |
| `MONITOR_BASE_DIR` | `.` | Project root. Set to `/opt/panel-agentic-ui` in production. |
| `MONITOR_WIDGETS_DIR` | `widgets` | Path (relative or absolute) where generated widget `.py` files are stored. |
| `MONITOR_CHATS_DIR` | `chats` | Path where chat session JSON files are stored. |
| `MONITOR_NOTES_DIR` | `notes` | Path where note widget content files are stored. |
| `MONITOR_LAYOUT_FILE` | `layout.json` | Path to the GoldenLayout state file. |
| `MONITOR_COOKIE_SECRET` | _(empty)_ | **Required in production.** Secret used by Panel to sign session cookies. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `MONITOR_TEST_MODE` | `false` | Set to `true` to enable test fixtures (e.g. static camera frame). |

### Example `/etc/panel-agentic-ui/env`

```bash
MONITOR_BASE_DIR=/opt/panel-agentic-ui
MONITOR_WIDGETS_DIR=/opt/panel-agentic-ui/widgets
MONITOR_CHATS_DIR=/opt/panel-agentic-ui/chats
MONITOR_NOTES_DIR=/opt/panel-agentic-ui/notes
MONITOR_LAYOUT_FILE=/opt/panel-agentic-ui/layout.json

MONITOR_COOKIE_SECRET=<64-hex-char secret>

MONITOR_LLM_PROVIDER=anthropic
MONITOR_LLM_MODEL=claude-sonnet-4-20250514
MONITOR_ANTHROPIC_API_KEY=sk-ant-...

MONITOR_GITHUB_TOKEN=ghp_...
MONITOR_GITHUB_REPO=your-org/panel-agentic-ui

MONITOR_PROMETHEUS_URL=http://localhost:9090
```

```bash
# Lock down the env file
sudo chmod 600 /etc/panel-agentic-ui/env
sudo chown root:root /etc/panel-agentic-ui/env
```

---

## 4. systemd Service Files

### 4.1 Panel server — `panel-agentic-ui.service`

```ini
# /etc/systemd/system/panel-agentic-ui.service
[Unit]
Description=Panel Agentic UI — GoldenLayout monitoring interface
Documentation=https://github.com/your-org/panel-agentic-ui
After=network.target panel-agentic-backends.target
Requires=panel-agentic-backends.target

[Service]
Type=simple
User=panel-agentic
Group=panel-agentic
WorkingDirectory=/opt/panel-agentic-ui
EnvironmentFile=/etc/panel-agentic-ui/env

ExecStart=/opt/panel-agentic-ui/.pixi/envs/default/bin/panel serve main.py \
    --address 127.0.0.1 \
    --port 5006 \
    --title "Panel Agentic UI" \
    --allow-websocket-origin monitor.internal \
    --num-procs 1 \
    --log-level info

Restart=on-failure
RestartSec=5s
TimeoutStopSec=30s

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/panel-agentic-ui/widgets \
               /opt/panel-agentic-ui/chats \
               /opt/panel-agentic-ui/notes \
               /opt/panel-agentic-ui/layout.json \
               /opt/panel-agentic-ui/__pycache__
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

> **`--allow-websocket-origin`** must match the `server_name` in your Nginx config exactly (no trailing slash, no protocol prefix). Add multiple `--allow-websocket-origin` flags if you serve under more than one hostname.

### 4.2 FastAPI backends — target unit

Group all backends under a single systemd target so the Panel service can declare a clean dependency.

```ini
# /etc/systemd/system/panel-agentic-backends.target
[Unit]
Description=Panel Agentic UI — FastAPI backends
After=network.target
```

### 4.3 Telemetry backend — `panel-agentic-telemetry.service`

```ini
# /etc/systemd/system/panel-agentic-telemetry.service
[Unit]
Description=Panel Agentic UI — Telemetry backend (psutil)
PartOf=panel-agentic-backends.target
After=panel-agentic-backends.target

[Service]
Type=simple
User=panel-agentic
Group=panel-agentic
WorkingDirectory=/opt/panel-agentic-ui
EnvironmentFile=/etc/panel-agentic-ui/env

ExecStart=/opt/panel-agentic-ui/.pixi/envs/default/bin/uvicorn \
    backends.telemetry:app \
    --host 127.0.0.1 \
    --port 8001 \
    --log-level info

Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=panel-agentic-backends.target
```

### 4.4 Commands backend — `panel-agentic-commands.service`

```ini
# /etc/systemd/system/panel-agentic-commands.service
[Unit]
Description=Panel Agentic UI — Commands backend (allowlisted teleoperation)
PartOf=panel-agentic-backends.target
After=panel-agentic-backends.target

[Service]
Type=simple
User=panel-agentic
Group=panel-agentic
WorkingDirectory=/opt/panel-agentic-ui
EnvironmentFile=/etc/panel-agentic-ui/env

ExecStart=/opt/panel-agentic-ui/.pixi/envs/default/bin/uvicorn \
    backends.commands:app \
    --host 127.0.0.1 \
    --port 8002 \
    --log-level info

Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=panel-agentic-backends.target
```

### 4.5 Data backend — `panel-agentic-data.service`

```ini
# /etc/systemd/system/panel-agentic-data.service
[Unit]
Description=Panel Agentic UI — Historical data backend
PartOf=panel-agentic-backends.target
After=panel-agentic-backends.target

[Service]
Type=simple
User=panel-agentic
Group=panel-agentic
WorkingDirectory=/opt/panel-agentic-ui
EnvironmentFile=/etc/panel-agentic-ui/env

ExecStart=/opt/panel-agentic-ui/.pixi/envs/default/bin/uvicorn \
    backends.data:app \
    --host 127.0.0.1 \
    --port 8003 \
    --log-level info

Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=panel-agentic-backends.target
```

### 4.6 Prometheus proxy — `panel-agentic-prometheus.service`

```ini
# /etc/systemd/system/panel-agentic-prometheus.service
[Unit]
Description=Panel Agentic UI — PromQL proxy backend
PartOf=panel-agentic-backends.target
After=panel-agentic-backends.target

[Service]
Type=simple
User=panel-agentic
Group=panel-agentic
WorkingDirectory=/opt/panel-agentic-ui
EnvironmentFile=/etc/panel-agentic-ui/env

ExecStart=/opt/panel-agentic-ui/.pixi/envs/default/bin/uvicorn \
    backends.prometheus:app \
    --host 127.0.0.1 \
    --port 8004 \
    --log-level info

Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=panel-agentic-backends.target
```

### 4.7 Enabling and starting all services

```bash
sudo systemctl daemon-reload

# Enable backends target and all individual backend services
sudo systemctl enable --now panel-agentic-backends.target
sudo systemctl enable --now panel-agentic-telemetry.service
sudo systemctl enable --now panel-agentic-commands.service
sudo systemctl enable --now panel-agentic-data.service
sudo systemctl enable --now panel-agentic-prometheus.service

# Enable and start the Panel server last
sudo systemctl enable --now panel-agentic-ui.service

# Check status
sudo systemctl status panel-agentic-ui.service
sudo journalctl -u panel-agentic-ui.service -f
```

### 4.8 Optional: nightly restart

Panel sessions can accumulate memory over long uptimes. A nightly restart during off-hours avoids this:

```ini
# /etc/systemd/system/panel-agentic-ui-restart.timer
[Unit]
Description=Nightly restart of Panel Agentic UI
Requires=panel-agentic-ui.service

[Timer]
OnCalendar=*-*-* 03:00:00
Unit=panel-agentic-ui.service
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now panel-agentic-ui-restart.timer
```

---

## 5. Nginx Reverse Proxy

### 5.1 TLS certificate

```bash
# Using Let's Encrypt (public domain)
sudo certbot --nginx -d monitor.internal

# Or for an internal CA, place your certificate and key at:
#   /etc/ssl/certs/monitor.crt
#   /etc/ssl/private/monitor.key
```

### 5.2 Complete server block

```nginx
# /etc/nginx/sites-available/panel-agentic-ui
# Rate limit zone — defined in http context (nginx.conf)
# limit_req_zone $binary_remote_addr zone=panel_agentic:10m rate=5r/s;

server {
    listen 80;
    server_name monitor.internal;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name monitor.internal;

    # --- TLS ---
    ssl_certificate     /etc/ssl/certs/monitor.crt;
    ssl_certificate_key /etc/ssl/private/monitor.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache   shared:SSL:10m;

    # --- Rate limiting ---
    limit_req zone=panel_agentic burst=20 nodelay;
    limit_req_status 429;

    # --- Security headers ---
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # --- Panel / Bokeh WebSocket + HTTP ---
    location / {
        proxy_pass         http://127.0.0.1:5006;
        proxy_http_version 1.1;

        # WebSocket upgrade — required for the Bokeh PATCH-DOC protocol
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";

        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Keep WebSocket connections alive during long sessions
        proxy_read_timeout  3600s;
        proxy_send_timeout  3600s;

        # Prevent Nginx from buffering large streaming responses
        proxy_buffering    off;
    }

    # --- go2rtc HLS endpoint (optional, only if go2rtc is running) ---
    location /hls/ {
        proxy_pass         http://127.0.0.1:1984/hls/;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;

        # HLS segments are short-lived; prevent stale cache
        add_header Cache-Control "no-cache, no-store";
    }

    # --- go2rtc WebRTC / API (optional) ---
    location /go2rtc/ {
        proxy_pass         http://127.0.0.1:1984/;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
    }

    # --- Static error pages ---
    error_page 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
        internal;
    }
}
```

Add the rate limit zone to `/etc/nginx/nginx.conf` inside the `http {}` block:

```nginx
http {
    # ...existing config...
    limit_req_zone $binary_remote_addr zone=panel_agentic:10m rate=5r/s;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/panel-agentic-ui /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5.3 WebSocket origin guard

Panel's Bokeh server rejects WebSocket upgrades from origins not in its allow-list. The `--allow-websocket-origin` flag in the systemd service must list every hostname the app is reachable at:

```ini
# In panel-agentic-ui.service ExecStart, add one flag per origin:
--allow-websocket-origin monitor.internal \
--allow-websocket-origin monitor.internal:443
```

If you serve on a non-standard port, add that variant too. Never use `--allow-websocket-origin "*"` in production.

---

## 6. go2rtc — RTSP Camera Streams

[go2rtc](https://github.com/AlexxIT/go2rtc) converts RTSP camera feeds to HLS, WebRTC, and MSE for browser playback.

### 6.1 Docker (recommended)

```bash
docker run -d \
  --name go2rtc \
  --restart unless-stopped \
  --network host \
  -v /opt/go2rtc/go2rtc.yaml:/config/go2rtc.yaml:ro \
  ghcr.io/alexxit/go2rtc:latest
```

### 6.2 go2rtc.yaml configuration

```yaml
# /opt/go2rtc/go2rtc.yaml

api:
  listen: "127.0.0.1:1984"   # API + HLS endpoint — localhost only
  origin: "*"                  # CORS handled upstream by Nginx

streams:
  front_camera: "rtsp://user:pass@192.168.1.100:554/stream1"
  rear_camera:  "rtsp://user:pass@192.168.1.101:554/stream1"

# Optional: transcode to H.264 for maximum browser compatibility
# ffmpeg:
#   front_camera: "-i {input} -c:v libx264 -preset ultrafast -tune zerolatency {output}"
```

### 6.3 HLS endpoint format

Once go2rtc is running and Nginx is proxying `/hls/`, streams are available at:

```
https://monitor.internal/hls/<stream_name>/index.m3u8
```

Example: `https://monitor.internal/hls/front_camera/index.m3u8`

Use this URL in the `example_video_hls.py` widget configuration:

```python
hls_url = "https://monitor.internal/hls/front_camera/index.m3u8"
```

### 6.4 Systemd alternative (no Docker)

```bash
# Download the go2rtc binary
curl -L https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_amd64 \
     -o /usr/local/bin/go2rtc
chmod +x /usr/local/bin/go2rtc
```

```ini
# /etc/systemd/system/go2rtc.service
[Unit]
Description=go2rtc — RTSP to HLS/WebRTC bridge
After=network.target

[Service]
Type=simple
User=go2rtc
ExecStart=/usr/local/bin/go2rtc -config /opt/go2rtc/go2rtc.yaml
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

---

## 7. Prometheus Integration

### 7.1 Scrape config

Add the following job to your Prometheus `prometheus.yml` to scrape the host running Panel Agentic UI. The telemetry backend does not expose a `/metrics` endpoint natively — install [node_exporter](https://github.com/prometheus/node_exporter) on the same host for system metrics.

```yaml
# prometheus.yml (on your Prometheus server)
scrape_configs:

  # Node exporter — host-level metrics (CPU, memory, disk, network)
  - job_name: "panel_agentic_host"
    static_configs:
      - targets: ["<host-ip>:9100"]
        labels:
          instance: "monitor-host"

  # Panel Agentic UI — application health (if you add a /metrics endpoint)
  # - job_name: "panel_agentic_app"
  #   static_configs:
  #     - targets: ["<host-ip>:5006"]
```

### 7.2 PromQL proxy backend

The PromQL proxy (`backends/prometheus.py`, port 8004) forwards requests to the Prometheus server configured via `MONITOR_PROMETHEUS_URL`. This keeps the Prometheus API off the public internet — widgets query the proxy, not Prometheus directly.

Example PromQL query via the proxy:

```bash
# From the Panel server (localhost only)
curl "http://127.0.0.1:8004/metrics/query?q=rate(node_cpu_seconds_total[5m])&start=now-1h&end=now&step=60"
```

The `example_prometheus.py` widget uses this endpoint. Set `MONITOR_PROMETHEUS_URL` to your Prometheus server's internal address (e.g. `http://10.0.0.5:9090`).

### 7.3 Alert routing (optional)

To receive Prometheus alerts in the Panel UI, configure Alertmanager to POST to a webhook widget endpoint (implement as a custom widget using FastAPI's `BackgroundTasks`).

---

## 8. Grafana Embedding

### 8.1 Grafana configuration

Edit `/etc/grafana/grafana.ini` (or `grafana.ini` in your Grafana deployment):

```ini
[security]
# Allow Grafana panels to be embedded in iframes served from the same origin
allow_embedding = true

[auth.anonymous]
# Enable anonymous read-only access so the Panel UI can show dashboards
# without a Grafana login prompt
enabled = true
org_name = Main Org.
org_role = Viewer

[server]
# Must be reachable from the browser — set to the public Grafana URL
root_url = https://grafana.internal
```

Restart Grafana after editing:

```bash
sudo systemctl restart grafana-server
```

### 8.2 Nginx proxy for Grafana (recommended)

Proxy Grafana through Nginx so it shares the same TLS certificate:

```nginx
# Add to the existing server block in /etc/nginx/sites-available/panel-agentic-ui
location /grafana/ {
    proxy_pass         http://127.0.0.1:3000/;
    proxy_http_version 1.1;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
}
```

Set Grafana's `root_url` to `https://monitor.internal/grafana/`.

### 8.3 Iframe URL format

```
https://grafana.internal/d/<dashboard-uid>/<dashboard-slug>?orgId=1&kiosk&theme=light&from=now-1h&to=now
```

| Parameter | Purpose |
|-----------|---------|
| `kiosk` | Hides the Grafana nav bar — use `kiosk=tv` for a fully borderless view |
| `theme=light` | Matches the Panel Agentic UI light theme |
| `from` / `to` | Time range (relative: `now-1h`, or absolute epoch ms) |
| `var-<name>=<value>` | Override template variables |
| `refresh=10s` | Auto-refresh interval |

Example for the `example_grafana_iframe.py` widget:

```python
grafana_url = (
    "https://monitor.internal/grafana/d/abc123/system-overview"
    "?orgId=1&kiosk&theme=light&from=now-6h&to=now&refresh=30s"
)
```

---

## 9. Backup Strategy

The entire application state fits in four locations. Back them up together for a consistent snapshot.

| Path | Content | Criticality |
|------|---------|-------------|
| `widgets/` | Generated widget `.py` files + `manifest.json` | High — widgets are not re-generatable without the original LLM session |
| `chats/` | Chat session JSON files (`<uuid>.json`) | Medium — conversation history |
| `notes/` | Note widget content files | Medium — user-authored notes |
| `layout.json` | GoldenLayout panel arrangement | Low — easy to recreate manually |

### 9.1 Daily rsync backup

```bash
#!/usr/bin/env bash
# /opt/panel-agentic-ui/scripts/backup.sh

set -euo pipefail

SRC=/opt/panel-agentic-ui
DEST=/backup/panel-agentic-ui/$(date +%Y-%m-%d)

mkdir -p "$DEST"

rsync -av --relative \
    "$SRC/widgets/" \
    "$SRC/chats/" \
    "$SRC/notes/" \
    "$SRC/layout.json" \
    "$DEST/"

# Keep 30 days of backups
find /backup/panel-agentic-ui -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +

echo "Backup complete: $DEST"
```

```ini
# /etc/systemd/system/panel-agentic-backup.timer
[Unit]
Description=Daily backup of Panel Agentic UI state

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/panel-agentic-backup.service
[Unit]
Description=Panel Agentic UI backup
After=local-fs.target

[Service]
Type=oneshot
User=root
ExecStart=/opt/panel-agentic-ui/scripts/backup.sh
```

```bash
sudo systemctl enable --now panel-agentic-backup.timer
```

### 9.2 Restore procedure

```bash
# Stop the Panel server before restoring
sudo systemctl stop panel-agentic-ui.service

BACKUP=/backup/panel-agentic-ui/2026-03-14

rsync -av "$BACKUP/widgets/"     /opt/panel-agentic-ui/widgets/
rsync -av "$BACKUP/chats/"       /opt/panel-agentic-ui/chats/
rsync -av "$BACKUP/notes/"       /opt/panel-agentic-ui/notes/
cp        "$BACKUP/layout.json"  /opt/panel-agentic-ui/layout.json

sudo chown -R panel-agentic:panel-agentic /opt/panel-agentic-ui/

sudo systemctl start panel-agentic-ui.service
```

---

## 10. Security Notes

### 10.1 Localhost-only backends

All FastAPI backends (`telemetry`, `commands`, `data`, `prometheus`) bind to `127.0.0.1` exclusively. They are never exposed through Nginx. The Panel server communicates with them via `httpx.AsyncClient` over the loopback interface.

**Do not change the bind address of any backend.** If remote access to backend APIs is required, add a separate authenticated Nginx location block with IP allowlisting, not by changing the bind address.

### 10.2 Cookie secret

`MONITOR_COOKIE_SECRET` must be set to a cryptographically random 32-byte hex string in production. Without it, Panel falls back to an insecure default.

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Rotate this secret by updating `/etc/panel-agentic-ui/env` and restarting the Panel service. Active browser sessions will be invalidated.

### 10.3 Single-user model

This application is designed for a single operator. There is no authentication layer built in — access control is delegated entirely to Nginx. Protect the application with one or more of:

- **Network-level restriction:** Serve only on a VPN or internal network interface.
- **HTTP Basic Auth in Nginx:**
  ```nginx
  auth_basic           "Panel Agentic UI";
  auth_basic_user_file /etc/nginx/.htpasswd;
  ```
  Generate: `sudo htpasswd -c /etc/nginx/.htpasswd operator`
- **mTLS client certificates:** For high-security environments.
- **Tailscale / WireGuard:** Recommended for remote access over the internet.

### 10.4 LLM-generated widget security

Generated widgets are validated before touching disk:

1. **AST static analysis** — rejects forbidden patterns (`requests`, `subprocess.run`, `os.system`, `time.sleep`, etc.)
2. **Subprocess dry-run** — executes the module in an isolated Python process with a 5-second timeout

Widgets run inside the Panel/Tornado process with the same OS privileges as the `panel-agentic` user. The systemd `ProtectSystem=strict` and `PrivateTmp=true` directives limit filesystem write access to the explicitly allowed paths.

### 10.5 Command backend allow-list

The commands backend (`port 8002`) only accepts the following actions: `set_speed`, `set_param`, `estop`, `resume`, `go_home`. All other actions return HTTP 403. Extend this allow-list in `backends/commands.py` only after review.

### 10.6 Secrets hygiene

- Never commit `/etc/panel-agentic-ui/env` to version control.
- API keys (`MONITOR_ANTHROPIC_API_KEY`, `MONITOR_GITHUB_TOKEN`) are loaded from the env file at service start — they are not visible in `systemctl status` output.
- Use a secrets manager (HashiCorp Vault, AWS Secrets Manager, etc.) for production deployments at scale.
