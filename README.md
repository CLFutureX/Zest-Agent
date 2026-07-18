# Zest-Agent

> **分布式智能体应用平台** —— 自研 AgentRunner 调度层、控制面/执行面分离、多层记忆、实时事件流、自研沙箱隔离。
> Designed and implemented from the ground up; only a few OpenHands components are reused as building blocks (OpenHands is MIT). Zest-Agent is licensed under Apache 2.0.

![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![Node](https://img.shields.io/badge/node-20+-green)
![Status](https://img.shields.io/badge/status-alpha-orange)

Zest-Agent 是一个**从底层设计到核心实现自研**的分布式智能体应用平台。仅复用 OpenHands 的少量组件作为基础积木，核心运行时（AgentRunner 调度层、Agent 启动调度模型、断点恢复、数据存储抽象、沙箱隔离机制、事件模型与状态机）均为自研设计。

- **自研 AgentRunner**：优雅支持同一会话内多 Agent 协同（Main + Sub Agent）
- **自研调度模型**：控制面 / 执行面分离 + Redis / 本地注册 + 会话粘性负载均衡
- **自研断点恢复**：三层持久化 + 检查点 + 启动扫描恢复
- **自研存储抽象**：统一接口 + 多后端可插拔（MySQL / Mongo / ES / 本地）
- **自研沙箱隔离**：文件 / 网络 / 进程三层隔离 + 沙箱生命周期管理
- **自研事件模型**：自研 eventCenter 发布-订阅模型（events + uiEvents 双主题），可观察、可回放
- **复用 OpenHands**：仅复用部分工具实现与数据模型片段

目标不是再造一个能聊天的 Agent，而是把 Agent 的运行时、记忆体系、调度能力拆解成一个可扩展、可调度、可持久演进的工程化平台。

---

## 核心特性

- **控制面 / 执行面分离** — `zest-app-server` 负责调度，`zest-service` 负责执行，可水平扩容。
- **分布式 Agent 调度** — Redis 服务注册 + 心跳 + 健康检查 + 会话粘性负载均衡。
- **多层记忆体系** — 基础记忆（用户画像、偏好、上下文）+ 经验记忆（问题—方案—执行轨迹），支持 Elasticsearch 检索。
- **实时事件驱动** — WebSocket 双向事件流，自研 eventCenter 发布-订阅模型（`events` + `uiEvents` 双主题），可观察、可回放。
- **多 Agent 演进** — `AgentRunner` 调度骨架，支持会话内 Main-Sub Agent 协同。
- **工程化能力** — 断点恢复、会话持久化、结构化日志、Langfuse 集成、健康接口。

---

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│  交互层  zest-web        (React + Vite, WebSocket 事件流)     │
├──────────────────────────────────────────────────────────────┤
│  控制面  zest-app-server  (FastAPI, port 9000)                │
├──────────────────────────────────────────────────────────────┤
│  执行面  zest-agent-server/zest-service  (FastAPI, port 8001)│
├──────────────────────────────────────────────────────────────┤
│  共享层  zest-sdk · zest-tools · zest-common                  │
└──────────────────────────────────────────────────────────────┘
```

详见 [docs/architecture.md](docs/architecture.md)。

---

## 快速开始

### 前置依赖

Python 3.12+、uv、Node 20+、pnpm 9+、Redis 7+、MySQL 8.0+。可选：Docker、MongoDB 7+、Elasticsearch 8.8.2。

### 方式一：本地原生（推荐，无 Docker）

适合二次开发，三个服务在本地热重载运行。

```bash
# 1. 克隆并安装
git clone https://github.com/CLFutureX/Zest-Agent.git
cd Zest-Agent
uv sync
cd zest-web && pnpm install && cd ..

# 2. 启动 Redis 与 MySQL（本机原生安装或用 docker 单独拉起）
#    原生：本机安装 redis-server 与 mysql-server，确保监听 127.0.0.1:6379 / 3306
#    或仅用 docker 拉起依赖（无需 Docker 跑业务服务）：
docker compose up -d redis mysql

# 3. 复制配置
cp .env.example                                          .env
cp zest-app-server/.env.example                          zest-app-server/.env
cp zest-agent-server/zest-service/server/.env.example   zest-agent-server/zest-service/server/.env
cp zest-web/.env.example                                 zest-web/.env
# 编辑 .env，至少设置 ZEST_SECRET_KEY 与 LLM_API_KEY

# 4. 启动三服务（顺序：前端 → app-server → service）
./scripts/start-dev.sh start        # Linux / macOS
./scripts/start-dev.ps1             # Windows
# 或 make dev
```

也可手动三个终端（保持相同启动顺序）：

```bash
# 终端 1：前端
cd zest-web && pnpm dev

# 终端 2：控制面（app-server，端口 9000）
cd zest-app-server && uv run uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload

# 终端 3：执行面（service，端口 8001）
cd zest-agent-server/zest-service && uv run python -m server --host 0.0.0.0 --port 8001 --reload
```

### 方式二：Docker Compose 一键

适合演示 / CI / 不希望污染本机环境。第一次运行会自动构建三个镜像（`zest-web` / `zest-app-server` / `zest-service`）。

```bash
git clone https://github.com/CLFutureX/Zest-Agent.git
cd Zest-Agent
cp .env.example .env  # 编辑 .env
docker compose --profile app up -d --build
```

访问 http://127.0.0.1:5173 即可使用。完整步骤见 [docs/quickstart.md](docs/quickstart.md)。

---

## 模块组成

| 模块 | 路径 | 职责 |
|---|---|---|
| 交互层 | `zest-web/` | React 前端，WebSocket 事件流驱动 |
| 控制面 | `zest-app-server/` | 会话入口、任务调度、AgentServer 注册发现 |
| 执行面 | `zest-agent-server/zest-service/` | Agent 会话生命周期、WebSocket 事件订阅 |
| SDK | `zest-agent-server/zest-sdk/` | Agent 构建核心、LLM、记忆、技能、事件 |
| 工具 | `zest-agent-server/zest-tools/` | Runtime 工具集（bash、file_editor、browser） |
| 共享 | `zest-common/` | 事件日志、状态、记忆、查询门面、可观测性 |

模块详解见 [docs/overview.md](docs/overview.md)。

---

## 路线图

- **v0.1** 首发：四层架构稳定，单节点可跑通完整会话
- **v0.2** 执行面多副本横向扩展，负载均衡策略补齐
- **v0.3** 多 Agent 协同稳定化，Main-Sub Agent 任务编排 DSL
- **v0.4** 可观测性增强，运维面板，会话回放 UI
- **v0.5** 插件化工具市场，技能模板库，多 LLM 路由

---

## 文档

- [docs/overview.md](docs/overview.md) — 完整项目介绍
- [docs/quickstart.md](docs/quickstart.md) — 快速开始（中文）
- [docs/en/quickstart.md](docs/en/quickstart.md) — Quick Start (EN)
- [docs/architecture.md](docs/architecture.md) — 架构详解
- [docs/deployment.md](docs/deployment.md) — 生产部署

---

## 参与贡献

欢迎参与！请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。行为准则见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。安全漏洞请按 [SECURITY.md](SECURITY.md) 报告，**不要**在公开 issue 中讨论。

---

## License

[Apache License 2.0](LICENSE) © 2026 CLFutureX

本项目基于 [OpenHands](https://github.com/All-Hands-AI/OpenHands)（Copyright © 2025 All Hands AI，MIT License）进行架构级重构与扩展。OpenHands 原始 MIT 许可声明按 MIT 要求保留在 [NOTICE.md](NOTICE.md) 中。
