# Deployment Guide

> This document targets ops and platform engineers deploying Zest-Agent to production.
> Prerequisite: walk through [quickstart.md](quickstart.md) once locally first.

---

## 1. Production Prerequisites

### 1.1 Hardware Baseline

| Role | CPU | RAM | Disk | Notes |
|---|---|---|---|---|
| Frontend (static hosting for zest-web) | 1 core | 512 MB | 1 GB | Nginx hosting is enough |
| Control plane (zest-app-server) | 2 cores | 2 GB | 5 GB | Single instance to start; 2 instances for HA recommended |
| Execution plane (zest-service) | 4 cores | 4 GB | 10 GB | Scale by concurrency; 2 nodes minimum |
| Redis | 1 core | 1 GB | 5 GB | Registry + heartbeat; standalone or managed |
| MySQL | 2 cores | 4 GB | 50 GB+ | Depends on conversation volume and memory size |
| Elasticsearch (optional) | 2 cores | 4 GB | 50 GB+ | Only needed for experience-memory retrieval |
| MongoDB (optional) | 2 cores | 2 GB | 20 GB | Only if using Mongo for memory |

### 1.2 Operating System

- Linux: Ubuntu 22.04 LTS / Debian 12 / CentOS Stream 9 / RHEL 9
- Kernel: 5.15+
- Arch: x86_64 (recommended) / arm64

### 1.3 Network

- Frontend public: 80 / 443 (HTTP/HTTPS)
- Control plane: 9000 (internal, not exposed directly)
- Execution plane: 8001 (internal, not exposed directly)
- Redis: 6379 (internal)
- MySQL: 3306 (internal)
- Elasticsearch: 9200 (internal)
- Outbound: LLM API (e.g., `api.openai.com`)

### 1.4 External Services

- **LLM API**: an accessible LLM service (OpenAI / Anthropic / Tongyi / Zhipu / self-hosted OpenAI-compatible gateway).
- **TLS certificate**: Let's Encrypt or self-signed CA.
- **DNS**: resolves the public domain.
- **SMTP** (optional): for alerting.

---

## 2. Single-Node Production Deployment (All-in-One)

For small-scale pilots (< 50 concurrent conversations). Three services + Redis + MySQL on the same machine.

### 2.1 System Prep

```bash
sudo apt update && sudo apt install -y curl git build-essential

# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node 20 + pnpm
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs
sudo npm install -g pnpm
```

### 2.2 Pull Code and Configure

```bash
git clone https://github.com/CLFutureX/Zest-Agent.git
cd Zest-Agent

# Copy .env
cp .env.example                                          .env
cp zest-app-server/.env.example                          zest-app-server/.env
cp zest-agent-server/zest-service/server/.env.example    zest-agent-server/zest-service/server/.env
cp zest-web/.env.example                                 zest-web/.env
```

**Production must-change items**:

```dotenv
# .env
MYSQL_ROOT_PASSWORD=<strong-password>
ZEST_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
LLM_API_KEY=<your-key>
LLM_BASE_URL=<your-llm-endpoint>
LLM_MODEL=<your-model>
LOG_LEVEL=INFO
```

```dotenv
# zest-app-server/.env
DEBUG=false
WORKERS=4
STORAGE_MODE=mysql
MYSQL_URL=mysql+aiomysql://zest_prod:<strong-password>@localhost:3306/zest_agent
REDIS_URL=redis://localhost:6379/0
# Restrict CORS
# ALLOW_CORS_ORIGINS=["https://your-domain.com"]
```

```dotenv
# zest-agent-server/zest-service/server/.env
ZEST_REGISTRY_ENABLED=true
ZEST_REGISTRY_REDIS_URL=redis://localhost:6379/0
ZEST_SESSION_API_KEYS=<random-strong-key>
ZEST_SECRET_KEY=<same-as-root>
```

### 2.3 Start Infrastructure

```bash
docker compose up -d redis mysql
```

Create database and least-privilege user:
```bash
docker exec -it zest-mysql mysql -uroot -p
```
```sql
CREATE DATABASE zest_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'zest_prod'@'%' IDENTIFIED BY '<strong-password>';
GRANT ALL PRIVILEGES ON zest_agent.* TO 'zest_prod'@'%';
FLUSH PRIVILEGES;
```

### 2.4 Install and Build

```bash
# Backend deps
uv sync

# Frontend production build
cd zest-web
pnpm install --frozen-lockfile
pnpm build
cd ..
```

### 2.5 systemd Deployment

Create `/etc/systemd/system/zest-web.service`:

```ini
[Unit]
Description=Zest-Agent Web (Vite preview / static)
After=network.target
Wants=network.target

[Service]
Type=simple
User=zest
WorkingDirectory=/opt/Zest-Agent/zest-web
ExecStart=/home/zest/.local/share/pnpm/vite preview --host 0.0.0.0 --port 5173
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/zest-app-server.service`:

```ini
[Unit]
Description=Zest-Agent App Server
After=network.target docker.service zest-web.service
Wants=network.target

[Service]
Type=simple
User=zest
WorkingDirectory=/opt/Zest-Agent/zest-app-server
EnvironmentFile=/opt/Zest-Agent/zest-app-server/.env
ExecStart=/home/zest/.local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 9000 --workers 4
Restart=always
RestartSec=5
StandardOutput=append:/var/log/zest/app-server.log
StandardError=append:/var/log/zest/app-server.err.log

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/zest-service.service`:

```ini
[Unit]
Description=Zest-Agent Service (Execution Plane)
After=network.target docker.service zest-app-server.service
Wants=network.target

[Service]
Type=simple
User=zest
WorkingDirectory=/opt/Zest-Agent/zest-agent-server/zest-service
EnvironmentFile=/opt/Zest-Agent/zest-agent-server/zest-service/server/.env
ExecStart=/home/zest/.local/bin/uv run python -m server --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5
StandardOutput=append:/var/log/zest/service.log
StandardError=append:/var/log/zest/service.err.log

[Install]
WantedBy=multi-user.target
```

The `After=` ordering reflects the recommended startup sequence: **frontend → app-server → service**. Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zest-web
sudo systemctl enable --now zest-app-server
sudo systemctl enable --now zest-service
sudo systemctl status zest-web zest-app-server zest-service
```

### 2.6 Nginx Reverse Proxy + TLS

`/etc/nginx/sites-available/zest-agent.conf`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Frontend static assets
    root /opt/Zest-Agent/zest-web/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Control plane API
    location /api/ {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Execution plane WebSocket (optional, frontend direct connect)
    location /sockets/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # Health check
    location /health {
        proxy_pass http://127.0.0.1:9000/health;
    }
}
```

Enable TLS:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
sudo nginx -t && sudo systemctl reload nginx
```

### 2.7 Verify

```bash
curl https://your-domain.com/health
curl https://your-domain.com/api/v1/health
```

Open https://your-domain.com in the browser; it should work end to end.

---

## 3. Multi-Node Distributed Deployment

For mid-to-large production (> 50 concurrent conversations, HA and horizontal scaling required).

### 3.1 Topology

```
                        ┌────────────────┐
                        │  Nginx / LB    │
                        └────────┬───────┘
                                 │
              ┌──────────────────┴──────────────────┐
              │                                     │
     ┌────────┴────────┐                  ┌────────┴────────┐
     │  app-server #1   │                  │  app-server #2  │
     └────────┬────────┘                  └────────┬────────┘
              │                                     │
              └────────────────┬───────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                 │                 │
       ┌──────┴─────┐    ┌─────┴──────┐    ┌─────┴──────┐
       │ service #1 │    │ service #2 │    │ service #N │
       └────────────┘    └────────────┘    └────────────┘

           Redis Cluster            MySQL Master + Replica (HA)
```

### 3.2 Redis Deployment

Two recommended approaches:

**Option A: Redis Sentinel (self-hosted)**
- 3 nodes: 1 Master + 2 Replica + 3 Sentinel (can be co-located with Master/Replica)
- Automatic failover

**Option B: Redis Cluster (managed)**
- AWS ElastiCache / Aliyun Tair / Tencent Cloud Redis
- Better for large scale, lower ops cost

Configure `REDIS_URL` to point to the Sentinel or Cluster endpoint.

### 3.3 MySQL Deployment

Recommended approaches:

**Option A: MySQL primary-replica + ProxySQL**
- 1 primary + 1 replica, read/write splitting
- Failover through ProxySQL or MHA

**Option B: Managed RDS**
- AWS RDS / Aliyun RDS / Tencent Cloud TDSQL
- Automated backup, HA, monitoring

```sql
-- Production user with least privilege
CREATE USER 'zest_prod'@'%' IDENTIFIED BY '<strong-password>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP ON zest_agent.* TO 'zest_prod'@'%';
FLUSH PRIVILEGES;
```

### 3.4 Control Plane Multi-Instance

`zest-app-server` is stateless; deploy multiple instances directly. Nginx upstream config:

```nginx
upstream zest_app_servers {
    server 10.0.1.10:9000 max_fails=3 fail_timeout=30s;
    server 10.0.1.11:9000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

location /api/ {
    proxy_pass http://zest_app_servers;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
}
```

### 3.5 Execution Plane Multi-Node

`zest-service` scales horizontally and self-registers to Redis. The control plane auto-discovers and schedules:

1. Deploy `zest-service` on multiple machines with the same `ZEST_REGISTRY_REDIS_URL`.
2. After startup, each node auto-registers to the Redis registry.
3. `zest-app-server` subscribes to the registry and auto-evicts unresponsive nodes.
4. New conversations pick a node by `session_affinity`.

### 3.6 File System and Session Affinity

Session affinity pins a conversation to one execution node. In multi-node setups, note:

- The control plane records conversation→node mapping in Redis at dispatch time.
- When a node goes offline, affected conversations migrate to other nodes (relying on breakpoint recovery).
- File-type tool operations are local to the sandbox; node migration loses temp files. Important files should be output to shared storage (NFS / S3).

---

## 4. Kubernetes Deployment (Reference)

> The following manifests are references; adjust to your environment.

### 4.1 Namespace and ConfigMap

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: zest-agent
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: zest-config
  namespace: zest-agent
data:
  STORAGE_MODE: mysql
  REDIS_URL: redis://zest-redis:6379/0
  MYSQL_URL: mysql+aiomysql://zest_prod@zest-mysql:3306/zest_agent
  LOG_LEVEL: INFO
```

### 4.2 Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: zest-secret
  namespace: zest-agent
type: Opaque
stringData:
  ZEST_SECRET_KEY: <generate-strong-key>
  MYSQL_ROOT_PASSWORD: <strong-password>
  LLM_API_KEY: <your-key>
  ZEST_SESSION_API_KEYS: <random-strong-key>
```

### 4.3 Deployment (app-server)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: zest-app-server
  namespace: zest-agent
spec:
  replicas: 2
  selector:
    matchLabels:
      app: zest-app-server
  template:
    metadata:
      labels:
        app: zest-app-server
    spec:
      containers:
        - name: app-server
          image: zest-app-server:latest
          ports:
            - containerPort: 9000
          envFrom:
            - configMapRef:
                name: zest-config
            - secretRef:
                name: zest-secret
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: 2000m
              memory: 4Gi
          livenessProbe:
            httpGet:
              path: /health
              port: 9000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 9000
            initialDelaySeconds: 5
            periodSeconds: 5
```

### 4.4 Service and Ingress

```yaml
apiVersion: v1
kind: Service
metadata:
  name: zest-app-server
  namespace: zest-agent
spec:
  selector:
    app: zest-app-server
  ports:
    - port: 9000
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: zest-ingress
  namespace: zest-agent
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
spec:
  tls:
    - hosts: [your-domain.com]
      secretName: zest-tls
  rules:
    - host: your-domain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: zest-web
                port:
                  number: 80
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: zest-app-server
                port:
                  number: 9000
          - path: /sockets
            pathType: Prefix
            backend:
              service:
                name: zest-service
                port:
                  number: 8001
```

### 4.5 HPA

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: zest-service-hpa
  namespace: zest-agent
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: zest-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

---

## 5. Backup and Recovery

### 5.1 MySQL Backup

Daily full + binlog incremental:

```bash
# Full backup
mysqldump -h 127.0.0.1 -uroot -p zest_agent | gzip > /backup/zest_agent_$(date +%Y%m%d).sql.gz

# Automate (crontab)
0 2 * * * /usr/bin/mysqldump -h 127.0.0.1 -uroot -p<password> zest_agent | gzip > /backup/zest_agent_$(date +\%Y\%m\%d).sql.gz

# Retain 30 days
find /backup -name "zest_agent_*.sql.gz" -mtime +30 -delete
```

Recover:
```bash
gunzip < /backup/zest_agent_20260712.sql.gz | mysql -uroot -p zest_agent
```

### 5.2 Redis Backup

Registry data is ephemeral; no backup needed. If Redis also stores cached memory, do RDB / AOF backups as needed.

### 5.3 Conversation File Backup

If `STORAGE_MODE=local` or sandbox outputs are local, periodically back up the `workspace/` directory to object storage.

### 5.4 Config and Secret Backup

`.env` files, K8s Secrets, TLS certificates — back up to a secure location (e.g., Vault or encrypted object storage).

---

## 6. Monitoring and Alerting

### 6.1 Metrics Collection

| Metric | Source | Method |
|---|---|---|
| Process alive | systemd / K8s probe | built-in |
| HTTP 5xx rate | Nginx log | Prometheus + nginx_exporter |
| Conversations per node | app-server | custom metrics endpoint (planned) |
| LLM calls | zest-sdk | Langfuse |
| MySQL slow queries | MySQL slow log | mysqld_exporter |
| Redis slow commands | Redis | redis_exporter |
| System resources | node_exporter | Prometheus |

### 6.2 Example Alert Rules

```yaml
groups:
  - name: zest-agent
    rules:
      - alert: ZestAppServerDown
        expr: up{job="zest-app-server"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Zest app-server is down"

      - alert: ZestServiceNodeGone
        expr: zest_service_active_nodes < 1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "No zest-service nodes registered"

      - alert: HighLLMErrorRate
        expr: rate(zest_llm_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High LLM error rate"
```

### 6.3 Log Aggregation

Recommended: ELK / Loki + Grafana / Aliyun SLS. Aggregate the structured JSON logs from `zest-*.log`.

---

## 7. Performance Tuning

### 7.1 Application Layer

- `zest-app-server`: `WORKERS=4` (tune by CPU cores)
- `zest-service`: single instance `--workers 1` (limited by WebSocket long connections); scale horizontally
- DB connection pool: tune `MYSQL_URL` `pool_size` / `max_overflow`
- Redis connection pool: tune `REDIS_URL` `max_connections`

### 7.2 Database

```sql
-- innodb tuning
SET GLOBAL innodb_buffer_pool_size = 2147483648;  -- 2GB, tune by RAM
SET GLOBAL innodb_log_file_size = 268435456;       -- 256MB
SET GLOBAL innodb_flush_log_at_trx_commit = 1;
```

### 7.3 Frontend

- `pnpm build` produces optimized artifacts by default
- Serve static assets through a CDN
- Set WebSocket long-connection timeout to 3600s

---

## 8. Upgrade and Rollback

### 8.1 Upgrade Procedure

1. Back up database and config
2. Read `CHANGELOG.md` to assess breaking changes
3. Validate in staging first
4. Canary: upgrade one `zest-service` node, observe
5. Rolling upgrade of all `zest-service` nodes
6. Upgrade `zest-app-server`
7. Upgrade frontend (build artifacts)
8. If schema changed, run `alembic upgrade head`

### 8.2 Rollback

1. Switch back to the old image / old commit
2. If schema changed, run `alembic downgrade -1`
3. Restore DB from backup (only if data is corrupted)

### 8.3 Zero-Downtime Upgrade

- In multi-node setups, upgrade node by node, keeping at least one node serving at all times.
- WebSocket long connections need graceful shutdown: notify the frontend to reconnect to another node.

---

## 9. Security Hardening Checklist

- [ ] `ZEST_SECRET_KEY` replaced with a strong random value
- [ ] `DEBUG=false`
- [ ] `ZEST_SESSION_API_KEYS` set
- [ ] MySQL user with least privilege
- [ ] CORS allowlist configured by domain
- [ ] All public endpoints over HTTPS
- [ ] LLM API Key via secret manager
- [ ] `zest-service` port not exposed publicly
- [ ] Redis password set
- [ ] Regular DB backups verified restorable
- [ ] No sensitive info leakage in logs (redaction in place)
- [ ] System packages and dependencies updated regularly

See [SECURITY.md](../SECURITY.md) for details.

---

## 10. Troubleshooting

| Symptom | Direction |
|---|---|
| Frontend WebSocket cannot connect | Check Nginx `Upgrade` / `Connection` headers; check execution-plane port reachability |
| Session creation fails | app-server logs; MySQL reachability; Redis reachability |
| Agent not responding | zest-service logs; LLM API Key and network; Langfuse for LLM calls |
| Nodes frequently go offline | Network jitter; Redis latency; node resource exhaustion |
| Rising 5xx | Slow-query log; connection pool exhaustion; disk full |

Common diagnostic commands:
```bash
# Service status
sudo systemctl status zest-web zest-app-server zest-service

# Logs
sudo journalctl -u zest-web         -n 200 --no-pager
sudo journalctl -u zest-app-server  -n 200 --no-pager
sudo journalctl -u zest-service     -n 200 --no-pager

# Health
curl -s http://localhost:5173         # frontend
curl -s http://localhost:9000/health
curl -s http://localhost:8001/health

# Redis registry
redis-cli -h localhost -p 6379 KEYS "agent_registry:*"

# MySQL connection
mysql -h 127.0.0.1 -u zest_prod -p zest_agent -e "SHOW PROCESSLIST"
```
