# 生产部署指南 (Deployment)

> 本文面向把 Zest-Agent 部署到生产环境的运维与平台工程师。
> 阅读前置：建议先看 [quickstart.md](quickstart.md) 在本地跑通一遍。

---

## 一、生产部署前提

### 1.1 硬件基线

| 角色 | CPU | 内存 | 磁盘 | 备注 |
|---|---|---|---|---|
| 前端（zest-web 静态托管） | 1 核 | 512 MB | 1 GB | Nginx 托管即可 |
| 控制面（zest-app-server） | 2 核 | 2 GB | 5 GB | 单实例可起步，建议 2 实例 HA |
| 执行面（zest-service） | 4 核 | 4 GB | 10 GB | 按并发扩缩，2 节点起步 |
| Redis | 1 核 | 1 GB | 5 GB | 注册中心 + 心跳，可独立部署或托管 |
| MySQL | 2 核 | 4 GB | 50 GB+ | 视会话量与记忆体量 |
| Elasticsearch（可选） | 2 核 | 4 GB | 50 GB+ | 经验记忆检索才需要 |
| MongoDB（可选） | 2 核 | 2 GB | 20 GB | 用 Mongo 存记忆才需要 |

### 1.2 操作系统

- Linux：Ubuntu 22.04 LTS / Debian 12 / CentOS Stream 9 / RHEL 9
- 内核：5.15+
- 架构：x86_64（推荐）/ arm64

### 1.3 网络

- 前端对外：80 / 443（HTTP/HTTPS）
- 控制面：9000（内部，不直接暴露公网）
- 执行面：8001（内部，不直接暴露公网）
- Redis：6379（内部）
- MySQL：3306（内部）
- Elasticsearch：9200（内部）
- 出站：LLM API（如 `api.openai.com`）

### 1.4 外部服务

- **LLM API**：可访问的 LLM 服务（OpenAI / Anthropic / 通义 / 智谱 / 自建 OpenAI 兼容网关）。
- **TLS 证书**：Let's Encrypt 或自签 CA。
- **DNS**：解析对外域名。
- **SMTP**（可选）：用于告警通知。

---

## 二、单节点生产部署（All-in-One）

适合小规模试用（< 50 并发会话）。三服务 + Redis + MySQL 部署在同一台机器。

### 2.1 系统准备

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

### 2.2 拉取代码与配置

```bash
git clone https://github.com/CLFutureX/Zest-Agent.git
cd Zest-Agent

# 复制 .env
cp .env.example                                          .env
cp zest-app-server/.env.example                          zest-app-server/.env
cp zest-agent-server/zest-service/server/.env.example    zest-agent-server/zest-service/server/.env
cp zest-web/.env.example                                 zest-web/.env
```

**生产必改项**：

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
# 限制 CORS
# ALLOW_CORS_ORIGINS=["https://your-domain.com"]
```

```dotenv
# zest-agent-server/zest-service/server/.env
ZEST_REGISTRY_ENABLED=true
ZEST_REGISTRY_REDIS_URL=redis://localhost:6379/0
ZEST_SESSION_API_KEYS=<random-strong-key>
ZEST_SECRET_KEY=<same-as-root>
```

### 2.3 启动基础设施

```bash
docker compose up -d redis mysql
```

创建数据库与最小权限用户：
```bash
docker exec -it zest-mysql mysql -uroot -p
```
```sql
CREATE DATABASE zest_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'zest_prod'@'%' IDENTIFIED BY '<strong-password>';
GRANT ALL PRIVILEGES ON zest_agent.* TO 'zest_prod'@'%';
FLUSH PRIVILEGES;
```

### 2.4 安装与构建

```bash
# 后端依赖
uv sync

# 前端生产构建
cd zest-web
pnpm install --frozen-lockfile
pnpm build
cd ..
```

### 2.5 systemd 部署

创建 `/etc/systemd/system/zest-app-server.service`：

```ini
[Unit]
Description=Zest-Agent App Server
After=network.target docker.service
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

创建 `/etc/systemd/system/zest-service.service`：

```ini
[Unit]
Description=Zest-Agent Service (Execution Plane)
After=network.target docker.service
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

启用并启动：
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zest-app-server
sudo systemctl enable --now zest-service
sudo systemctl status zest-app-server zest-service
```

### 2.6 Nginx 反向代理 + TLS

`/etc/nginx/sites-available/zest-agent.conf`：

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

    # 前端静态资源
    root /opt/Zest-Agent/zest-web/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # 控制面 API
    location /api/ {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 执行面 WebSocket（可选，前端直连）
    location /sockets/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:9000/health;
    }
}
```

启用 TLS：
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
sudo nginx -t && sudo systemctl reload nginx
```

### 2.7 验证

```bash
curl https://your-domain.com/health
curl https://your-domain.com/api/v1/health
```

浏览器访问 https://your-domain.com，应能正常使用。

---

## 三、多节点分布式部署

适合中大规模生产（> 50 并发会话，需要 HA 与水平扩展）。

### 3.1 拓扑

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

### 3.2 Redis 部署

推荐两种方案：

**方案 A：Redis Sentinel（自建）**
- 3 节点：1 Master + 2 Replica + 3 Sentinel（可与 Master/Replica 共置）
- 故障自动切换

**方案 B：Redis Cluster（托管）**
- AWS ElastiCache / 阿里云 Tair / 腾讯云 Redis
- 适合大规模，运维成本低

配置 `REDIS_URL` 指向 Sentinel 或 Cluster 入口。

### 3.3 MySQL 部署

推荐方案：

**方案 A：MySQL 主从 + ProxySQL**
- 1 主 1 从，读写分离
- 故障切换通过 ProxySQL 或 MHA

**方案 B：托管 RDS**
- AWS RDS / 阿里云 RDS / 腾讯云 TDSQL
- 自动备份、HA、监控

```sql
-- 生产用户最小权限
CREATE USER 'zest_prod'@'%' IDENTIFIED BY '<strong-password>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP ON zest_agent.* TO 'zest_prod'@'%';
FLUSH PRIVILEGES;
```

### 3.4 控制面多实例

`zest-app-server` 无状态，直接多实例部署。Nginx 上游配置：

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

### 3.5 执行面多节点

`zest-service` 水平扩展，自注册到 Redis。控制面自动发现并调度：

1. 在多台机器上部署 `zest-service`，相同 `ZEST_REGISTRY_REDIS_URL`。
2. 启动后自动注册到 Redis 注册表。
3. 控制面 `zest-app-server` 订阅注册表，自动剔除失联节点。
4. 新会话按 `session_affinity` 策略选节点。

### 3.6 文件系统与会话粘性

会话粘性要求同一会话固定到同一执行节点。多节点环境下注意：

- 控制面在派发时记录会话—节点映射，存 Redis。
- 节点失联时，对应会话需迁移到其他节点（依赖断点恢复机制）。
- 文件类工具操作在沙箱本地，节点迁移会丢失临时文件。建议重要文件输出到共享存储（NFS / S3）。

---

## 四、Kubernetes 部署（参考）

> 以下为参考 manifest，需按实际环境调整。

### 4.1 Namespace 与 ConfigMap

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

### 4.3 Deployment（app-server）

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

### 4.4 Service 与 Ingress

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

## 五、备份与恢复

### 5.1 MySQL 备份

每日全量 + binlog 增量：

```bash
# 全量备份
mysqldump -h 127.0.0.1 -uroot -p zest_agent | gzip > /backup/zest_agent_$(date +%Y%m%d).sql.gz

# 自动化（crontab）
0 2 * * * /usr/bin/mysqldump -h 127.0.0.1 -uroot -p<password> zest_agent | gzip > /backup/zest_agent_$(date +\%Y\%m\%d).sql.gz

# 保留 30 天
find /backup -name "zest_agent_*.sql.gz" -mtime +30 -delete
```

恢复：
```bash
gunzip < /backup/zest_agent_20260712.sql.gz | mysql -uroot -p zest_agent
```

### 5.2 Redis 备份

注册中心数据是临时的，无需备份。若 Redis 也存了缓存类记忆，则按需 RDB / AOF 备份。

### 5.3 会话文件备份

若 `STORAGE_MODE=local` 或工具沙箱有本地文件输出，定期备份 `workspace/` 目录到对象存储。

### 5.4 配置与密钥备份

`.env` 文件、K8s Secret、TLS 证书统一备份到安全位置（如 Vault 或加密对象存储）。

---

## 六、监控与告警

### 6.1 指标采集

| 指标 | 来源 | 采集方式 |
|---|---|---|
| 进程存活 | systemd / K8s probe | 内置 |
| HTTP 5xx 比例 | Nginx 日志 | Prometheus + nginx_exporter |
| 会话数 / 节点 | app-server | 自定义 metrics endpoint（计划中） |
| LLM 调用 | zest-sdk | Langfuse |
| MySQL 慢查询 | MySQL slow log | mysqld_exporter |
| Redis 慢命令 | Redis | redis_exporter |
| 系统资源 | node_exporter | Prometheus |

### 6.2 告警规则示例

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

### 6.3 日志聚合

推荐：ELK / Loki + Grafana / 阿里云 SLS。把 `zest-*.log` 的 JSON 结构化日志统一聚合。

---

## 七、性能调优

### 7.1 应用层

- `zest-app-server`：`WORKERS=4`（按 CPU 核数调整）
- `zest-service`：单实例 `--workers 1`（受限于 WebSocket 长连接），多副本横向扩展
- 数据库连接池：调整 `MYSQL_URL` 的 `pool_size` / `max_overflow`
- Redis 连接池：调整 `REDIS_URL` 的 `max_connections`

### 7.2 数据库

```sql
-- innodb 调优
SET GLOBAL innodb_buffer_pool_size = 2147483648;  -- 2GB，按内存调整
SET GLOBAL innodb_log_file_size = 268435456;       -- 256MB
SET GLOBAL innodb_flush_log_at_trx_commit = 1;
```

### 7.3 前端

- `pnpm build` 默认产生优化产物
- 静态资源走 CDN
- WebSocket 长连接超时调到 3600s

---

## 八、升级与回滚

### 8.1 升级流程

1. 备份数据库与配置
2. 阅读 `CHANGELOG.md` 评估 Breaking changes
3. 在 staging 环境验证
4. 灰度：先升级一个 `zest-service` 节点，观察
5. 滚动升级 `zest-service` 全部节点
6. 升级 `zest-app-server`
7. 升级前端（构建产物）
8. 如有 schema 变更，执行 `alembic upgrade head`

### 8.2 回滚

1. 切回旧镜像 / 旧 commit
2. 如有 schema 变更，执行 `alembic downgrade -1`
3. 从备份恢复数据库（仅当数据损坏时）

### 8.3 零停机升级

- 多节点环境下，逐节点升级，确保至少一个节点持续提供服务。
- WebSocket 长连接需优雅关闭：通知前端重连到其他节点。

---

## 九、安全加固清单

- [ ] `ZEST_SECRET_KEY` 已替换为强随机值
- [ ] `DEBUG=false`
- [ ] `ZEST_SESSION_API_KEYS` 已设置
- [ ] MySQL 用户最小权限
- [ ] CORS 白名单按域名配置
- [ ] 所有对外接口走 HTTPS
- [ ] LLM API Key 走 secret manager
- [ ] `zest-service` 端口不暴露公网
- [ ] Redis 已设置密码
- [ ] 定期数据库备份验证可恢复
- [ ] 日志中无敏感信息脱敏遗漏
- [ ] 系统包与依赖定期更新

详见 [SECURITY.md](../SECURITY.md)。

---

## 十、故障排查

| 症状 | 排查方向 |
|---|---|
| 前端 WebSocket 连不上 | Nginx `Upgrade` / `Connection` 头是否配置；执行面端口是否可达 |
| 会话创建失败 | app-server 日志；MySQL 连通性；Redis 连通性 |
| Agent 不响应 | zest-service 日志；LLM API Key 与网络；Langfuse 查看 LLM 调用 |
| 节点频繁失联 | 网络抖动；Redis 延迟；节点资源不足 |
| 5xx 上升 | 慢查询日志；连接池耗尽；磁盘满 |

通用排查命令：
```bash
# 服务状态
sudo systemctl status zest-app-server zest-service

# 日志
sudo journalctl -u zest-app-server -n 200 --no-pager
sudo journalctl -u zest-service  -n 200 --no-pager

# 健康
curl -s http://localhost:9000/health
curl -s http://localhost:8001/health

# Redis 注册表
redis-cli -h localhost -p 6379 KEYS "agent_registry:*"

# MySQL 连接
mysql -h 127.0.0.1 -u zest_prod -p zest_agent -e "SHOW PROCESSLIST"
```
