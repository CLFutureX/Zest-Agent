# Zest-Agent Quick Start

> This guide walks first-time contributors through two deployment paths: **Local Development Mode** (recommended) and **Docker Compose One-Shot Mode**.
> Default storage: **MySQL**. Service registry: **Redis** (required).
> OS: Windows 11 / macOS / Linux. Command examples are given in both PowerShell and bash.

---

## 1. Prerequisites

| Dependency | Min Version | Notes |
|---|---|---|
| Python | 3.12 | Pinned via `.python-version` |
| uv | 0.4+ | Python workspace manager — [install](https://docs.astral.sh/uv/) |
| Node.js | 20 LTS | Frontend build |
| pnpm | 9+ | Frontend package manager (`npm i -g pnpm`) |
| Docker | 24+ | Only for Docker Compose mode |
| Redis | 7+ | Service registry (required, local install or docker) |
| MySQL | 8.0+ | Default storage backend |

Optional (only if you enable the corresponding feature):
- **MongoDB 7+**: basic memory / file metadata storage
- **Elasticsearch 8.8.2**: experience-memory vector retrieval

### 1.1 Install uv (if missing)

PowerShell:
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

macOS / Linux:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1.2 Verify the environment

```powershell
python --version    # >= 3.12
uv --version
node --version      # >= 20
pnpm --version
docker --version    # Docker mode only
```

---

## 2. Get the code

```bash
git clone https://github.com/CLFutureX/Zest-Agent.git
cd Zest-Agent
```

---

## 3. Path A: Local Development Mode (Recommended)

Fastest path to a working setup. All three services run locally with hot reload; frontend changes apply instantly.

### 3.1 Start infrastructure (Redis + MySQL)

Easiest: use docker to bring up just Redis and MySQL, run the three Zest services natively:

```powershell
docker compose up -d
docker compose ps
```

You should see `zest-redis` and `zest-mysql` as healthy.

If you prefer installing Redis and MySQL natively, ensure:
- Redis listening on `127.0.0.1:6379`
- MySQL listening on `127.0.0.1:3306`, root password `root`, and run `CREATE DATABASE zest_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`

### 3.2 Configure environment variables

Three `.env.example` files are provided; copy each to `.env`:

```powershell
Copy-Item .env.example                                          .env
Copy-Item zest-app-server/.env.example                          zest-app-server/.env
Copy-Item zest-agent-server/zest-service/server/.env.example    zest-agent-server/zest-service/server/.env
Copy-Item zest-web/.env.example                                 zest-web/.env
```

bash:
```bash
cp .env.example                                          .env
cp zest-app-server/.env.example                          zest-app-server/.env
cp zest-agent-server/zest-service/server/.env.example    zest-agent-server/zest-service/server/.env
cp zest-web/.env.example                                 zest-web/.env
```

At minimum, edit these:

**`.env` (root, used by docker compose and scripts)**
```dotenv
MYSQL_ROOT_PASSWORD=root
ZEST_SECRET_KEY=<generate via python -c "import secrets; print(secrets.token_urlsafe(32))">
LLM_API_KEY=<your LLM API key>
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

**`zest-app-server/.env`** and **`zest-service/server/.env`**: if you used different MySQL/Redis credentials, update `MYSQL_URL` and `REDIS_URL`.

### 3.3 Install dependencies

```powershell
# Backend: uv workspace installs all sub-packages at once
uv sync

# Frontend
cd zest-web
pnpm install
cd ..
```

### 3.4 Start the three services

**Option 1: Use the launcher script (recommended)**

Windows PowerShell:
```powershell
./scripts/start-dev.ps1
./scripts/start-dev.ps1 -Status
./scripts/start-dev.ps1 -Stop
```

macOS / Linux:
```bash
chmod +x scripts/start-dev.sh
./scripts/start-dev.sh start
./scripts/start-dev.sh status
./scripts/start-dev.sh stop
```

**Option 2: Use Make (if available)**
```bash
make dev       # start
make status    # status
make stop      # stop
```

**Option 3: Three manual terminals (startup order: frontend → app-server → service)**

Terminal 1 — Frontend (zest-web, port 5173):
```powershell
cd zest-web
pnpm dev
```

Terminal 2 — Control plane (app-server, port 9000):
```powershell
cd zest-app-server
uv run uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

Terminal 3 — Execution plane (zest-service, port 8001):
```powershell
cd zest-agent-server/zest-service
uv run python -m server --host 0.0.0.0 --port 8001 --reload
```

### 3.5 Verify

| Service | URL | Expected |
|---|---|---|
| app-server | http://127.0.0.1:9000/ | `{"name":"zest-agent-appserver","status":"running"}` |
| app-server docs | http://127.0.0.1:9000/docs | Swagger UI |
| service | http://127.0.0.1:8001/docs | Swagger UI |
| web | http://127.0.0.1:5173 | Frontend home, auto-connects via WebSocket |

Open http://127.0.0.1:5173, create a conversation, send a message, and confirm the LLM call chain works end to end.

---

## 4. Path B: Docker Compose One-Shot Mode

Best for demos, CI, or keeping your host clean.

### 4.1 Build images

The repo does not yet publish prebuilt images. `docker/Dockerfile.app-server`, `Dockerfile.service`, and `Dockerfile.web` are provided in the `docker/` directory. `docker compose` builds them automatically on first run — no manual `docker build` needed.

### 4.2 Start the full stack

```powershell
docker compose --profile app up -d --build
docker compose ps
docker compose logs -f zest-app-server
```

### 4.3 Optional storage backends

To enable MongoDB or Elasticsearch:
```powershell
docker compose --profile storage up -d mongo elasticsearch
```
Then toggle the relevant settings in each module's `.env` (see module docs).

### 4.4 Stop and clean up

```powershell
docker compose down             # stop and remove containers (keeps volumes)
docker compose down -v          # also removes volumes — destroys data
```

---

## 5. Configuration

### 5.1 Responsibilities of the three `.env` files

| File | Purpose | Key vars |
|---|---|---|
| `.env` (root) | Read by docker compose and launcher scripts | `MYSQL_ROOT_PASSWORD`, `ZEST_SECRET_KEY`, `LLM_*` |
| `zest-app-server/.env` | Control plane (port, storage, registry, LB) | `STORAGE_MODE`, `MYSQL_URL`, `REDIS_URL`, `REGISTRY_MODE` |
| `zest-agent-server/zest-service/server/.env` | Execution plane (identity, heartbeat, security) | `ZEST_AGENT_SERVER_PORT`, `ZEST_REGISTRY_*`, `ZEST_SECRET_KEY` |
| `zest-web/.env` | Frontend build-time vars | `VITE_APP_API_BASE`, `VITE_WS_*` |

### 5.2 Switching storage mode

Default is `STORAGE_MODE=mysql`. To switch to local file storage (no MySQL needed):
```dotenv
# zest-app-server/.env
STORAGE_MODE=local
LOCAL_DATA_DIR=./.data
```
> Local mode is for development only; never use it in multi-node deployments.

### 5.3 LLM configuration

zest-sdk uses [litellm](https://github.com/BerriAI/litellm), supporting OpenAI, Anthropic, Azure, Tongyi, Zhipu, and more. Minimal form:
```dotenv
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```
For OpenAI-compatible gateways (Tongyi, Zhipu, Moonshot), change `LLM_BASE_URL` and `LLM_MODEL` accordingly.

### 5.4 Security notes

- **Replace `ZEST_SECRET_KEY` with a strong random value in production.** Otherwise encrypted fields are effectively unprotected.
- In dev mode, `ZEST_SESSION_API_KEYS` empty means the execution plane is unauthenticated; always set it in production.
- `DEBUG=true` emits verbose stack traces; turn it off in production.

---

## 6. Troubleshooting

### Q1: `Connection refused redis://localhost:6379`
Redis is not running. Run `docker compose up -d redis` or check your native Redis service.

### Q2: app-server reports `Authentication failed for mysql`
Wrong password or host. Verify `MYSQL_URL` in `zest-app-server/.env` matches `MYSQL_ROOT_PASSWORD` in docker compose.

### Q3: Frontend is blank / WebSocket cannot connect
1. Verify `VITE_APP_API_BASE` in `zest-web/.env` points to app-server (default `http://127.0.0.1:9000/api/v1`).
2. Check the browser console. CORS allows all origins in dev by default.

### Q4: zest-service exits immediately after start
Check that `ZEST_REGISTRY_REDIS_URL` is reachable. With `ZEST_REGISTRY_ENABLED=true`, Redis must be up.

### Q5: `./scripts/start-dev.sh` won't run on Windows
Use `./scripts/start-dev.ps1` on Windows. To run `.sh` under WSL/git-bash, first `dos2unix scripts/start-dev.sh` or execute inside git-bash.

### Q6: Switching Python version
Edit `.python-version` in the repo root, then `uv sync` will install and use it automatically.

---

## 7. Next steps

- Read `docs/architecture.md` for the four-layer architecture.
- Read `CONTRIBUTING.md` to start contributing.
- Read `docs/deployment.md` for production deployment (systemd / nginx / TLS / multi-node).

For questions, post in [GitHub Discussions](https://github.com/CLFutureX/Zest-Agent/discussions) first. If you confirm a bug, follow `SECURITY.md` and the issue template to file it.
