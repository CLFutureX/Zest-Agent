# Zest-Agent 快速开始 (Quick Start)

> 本文档面向首次接触 Zest-Agent 的开发者，覆盖本地开发模式（推荐）与 Docker Compose 一键模式两种部署路径。
> 默认存储模式：**MySQL**。注册中心：**Redis**（必选）。
> 操作系统：Windows 11 / macOS / Linux 均可。命令示例同时给出 PowerShell 与 bash 两种形式。

---

## 1. 前置依赖

| 依赖 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.12 | 项目 `.python-version` 限定 |
| uv | 0.4+ | Python workspace 包管理器，[安装指南](https://docs.astral.sh/uv/) |
| Node.js | 20 LTS | 前端构建 |
| pnpm | 9+ | 前端包管理器，`npm i -g pnpm` |
| Docker | 24+ | 仅在使用 Docker Compose 模式时需要 |
| Redis | 7+ | 服务注册中心（必选，本地装或用 docker） |
| MySQL | 8.0+ | 默认存储后端 |

可选（仅在启用对应能力时需要）：
- **MongoDB 7+**：基础记忆 / 文件元数据存储
- **Elasticsearch 8.8.2**：经验记忆向量检索

### 1.1 安装 uv（如未安装）

PowerShell：
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

macOS / Linux：
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1.2 验证环境

```powershell
python --version    # >= 3.12
uv --version
node --version      # >= 20
pnpm --version
docker --version    # 仅 Docker 模式
```

---

## 2. 获取代码

```powershell
git clone https://github.com/CLFutureX/Zest-Agent.git
cd Zest-Agent
```

---

## 3. 路径 A：本地开发模式（推荐）

这是上手最快、最适合二次开发的方式。三个服务在本地以热重载模式运行，前端改动立即生效。

### 3.1 启动基础设施（Redis + MySQL）

最简单的做法是只用 docker 拉起 Redis 和 MySQL，三个业务服务留在本机跑：

```powershell
docker compose up -d
# 验证
docker compose ps
```

预期看到 `zest-redis` 与 `zest-mysql` 状态为 healthy。

如果不想用 docker，也可本机直接安装 Redis 和 MySQL，确保：
- Redis 监听 `127.0.0.1:6379`
- MySQL 监听 `127.0.0.1:3306`，root 密码 `root`，并执行 `CREATE DATABASE zest_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`

### 3.2 配置环境变量

项目根目录已提供三份 `.env.example`，复制为 `.env` 后按需修改：

```powershell
Copy-Item .env.example                                   .env
Copy-Item zest-app-server/.env.example                   zest-app-server/.env
Copy-Item zest-agent-server/zest-service/server/.env.example  zest-agent-server/zest-service/server/.env
Copy-Item zest-web/.env.example                          zest-web/.env
```

bash：
```bash
cp .env.example                                   .env
cp zest-app-server/.env.example                   zest-app-server/.env
cp zest-agent-server/zest-service/server/.env.example  zest-agent-server/zest-service/server/.env
cp zest-web/.env.example                          zest-web/.env
```

至少修改以下两处：

**`.env`（根目录，给 docker compose 与脚本用）**
```dotenv
MYSQL_ROOT_PASSWORD=root
ZEST_SECRET_KEY=<运行 python -c "import secrets; print(secrets.token_urlsafe(32))" 生成>
LLM_API_KEY=<你的 LLM API Key>
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

**`zest-app-server/.env`** 与 **`zest-service/server/.env`**：如果用了不同的 MySQL/Redis 密码，对应修改 `MYSQL_URL` 和 `REDIS_URL`。

### 3.3 安装依赖

```powershell
# 后端（uv workspace 一键安装所有子包）
uv sync

# 前端
cd zest-web
pnpm install
cd ..
```

### 3.4 启动三个服务

**方式一：使用脚本（推荐）**

Windows PowerShell：
```powershell
./scripts/start-dev.ps1
# 查看状态
./scripts/start-dev.ps1 -Status
# 停止
./scripts/start-dev.ps1 -Stop
```

macOS / Linux：
```bash
chmod +x scripts/start-dev.sh
./scripts/start-dev.sh start
./scripts/start-dev.sh status
./scripts/start-dev.sh stop
```

**方式二：使用 Make（如有 make）**
```bash
make dev       # 启动
make status    # 状态
make stop      # 停止
```

**方式三：手动三个终端（启动顺序：前端 → app-server → service）**

终端 1 — 前端（zest-web，端口 5173）：
```powershell
cd zest-web
pnpm dev
```

终端 2 — 控制面（app-server，端口 9000）：
```powershell
cd zest-app-server
uv run uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

终端 3 — 执行面（zest-service，端口 8001）：
```powershell
cd zest-agent-server/zest-service
uv run python -m server --host 0.0.0.0 --port 8001 --reload
```

### 3.5 验证启动

| 服务 | URL | 预期 |
|---|---|---|
| app-server | http://127.0.0.1:9000/ | 返回 `{"name":"zest-agent-appserver","status":"running"}` |
| app-server docs | http://127.0.0.1:9000/docs | Swagger UI |
| service | http://127.0.0.1:8001/docs | Swagger UI |
| web | http://127.0.0.1:5173 | 前端首页，自动连 WebSocket |

打开 http://127.0.0.1:5173，应能看到前端加载并连接到 app-server。新建一个会话发消息，确认 LLM 调用链路通畅。

---

## 4. 路径 B：Docker Compose 一键模式

适合演示、CI、或不希望污染本机环境的场景。

### 4.1 准备镜像

仓库暂未发布预构建镜像，需本地构建。`docker/` 目录已提供 `Dockerfile.app-server`、`Dockerfile.service`、`Dockerfile.web` 三份镜像构建脚本。可直接由 `docker compose` 自动构建，无需手动 `docker build`。

### 4.2 启动完整栈

```powershell
# 拉起 Redis + MySQL + 三个 Zest 服务（首次会自动构建镜像）
docker compose --profile app up -d --build

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f zest-app-server
```

### 4.3 可选存储后端

如需启用 MongoDB 或 Elasticsearch：
```powershell
docker compose --profile storage up -d mongo elasticsearch
```

并在对应 `.env` 中切换相关配置（详见各模块文档）。

### 4.4 停止与清理

```powershell
docker compose down                # 停止并删除容器（保留数据卷）
docker compose down -v             # 同时删除数据卷（清空数据，慎用）
```

---

## 5. 配置说明

### 5.1 三份 `.env` 的职责

| 文件 | 作用 | 关键变量 |
|---|---|---|
| `.env`（根） | docker compose 与启动脚本读取 | `MYSQL_ROOT_PASSWORD`、`ZEST_SECRET_KEY`、`LLM_*` |
| `zest-app-server/.env` | 控制面配置（端口、存储、注册中心、负载均衡） | `STORAGE_MODE`、`MYSQL_URL`、`REDIS_URL`、`REGISTRY_MODE` |
| `zest-agent-server/zest-service/server/.env` | 执行面配置（运行身份、注册心跳、安全） | `ZEST_AGENT_SERVER_PORT`、`ZEST_REGISTRY_*`、`ZEST_SECRET_KEY` |
| `zest-web/.env` | 前端构建期变量 | `VITE_APP_API_BASE`、`VITE_WS_*` |

### 5.2 切换存储模式

默认 `STORAGE_MODE=mysql`。若要切到本地文件存储（无需 MySQL）：
```dotenv
# zest-app-server/.env
STORAGE_MODE=local
LOCAL_DATA_DIR=./.data
```
> 注意：local 模式仅适合开发，不可用于多节点部署。

### 5.3 LLM 配置

zest-sdk 基于 [litellm](https://github.com/BerriAI/litellm)，支持 OpenAI、Anthropic、Azure、通义、智谱等多家。最简形式：
```dotenv
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```
国内可用兼容 OpenAI 协议的网关（如通义、智谱、Moonshot），改 `LLM_BASE_URL` 与 `LLM_MODEL` 即可。

### 5.4 安全提示

- **`ZEST_SECRET_KEY` 在生产环境必须替换为强随机值**，否则敏感字段加密形同虚设。
- 开发模式下 `ZEST_SESSION_API_KEYS` 留空表示执行面不鉴权；生产必须设置。
- `DEBUG=true` 会输出详细堆栈，生产请关闭。

---

## 6. 常见问题

### Q1：启动报 `Connection refused redis://localhost:6379`
Redis 未启动。运行 `docker compose up -d redis` 或检查本机 Redis 服务。

### Q2：app-server 报 `Authentication failed for mysql`
密码或地址不对。检查 `zest-app-server/.env` 的 `MYSQL_URL` 与 docker compose 中的 `MYSQL_ROOT_PASSWORD` 是否一致。

### Q3：前端页面空白、WebSocket 连不上
1. 确认 `zest-web/.env` 的 `VITE_APP_API_BASE` 指向 app-server（默认 `http://127.0.0.1:9000/api/v1`）。
2. 浏览器控制台查看具体错误。CORS 默认放行所有源，开发期无需特殊配置。

### Q4：zest-service 启动后立刻退出
检查 `ZEST_REGISTRY_REDIS_URL` 是否能连上 Redis。`ZEST_REGISTRY_ENABLED=true` 时必须能连。

### Q5：Windows 下 `./scripts/start-dev.sh` 无法运行
Windows 上用 `./scripts/start-dev.ps1`；如需在 WSL/git-bash 跑 `.sh`，先 `dos2unix scripts/start-dev.sh` 或在 git-bash 中执行。

### Q6：如何切换 Python 版本
修改根目录 `.python-version` 文件，然后 `uv sync` 会自动安装并使用。

---

## 7. 下一步

- 阅读 `docs/architecture.md` 了解四层架构设计
- 阅读 `CONTRIBUTING.md` 参与贡献
- 阅读 `docs/deployment.md` 了解生产部署（systemd / nginx / TLS / 多节点）

如遇问题，先在 [GitHub Discussions](https://github.com/CLFutureX/Zest-Agent/discussions) 提问；如确认是 bug，请按 `SECURITY.md` 与 Issue 模板提交。
