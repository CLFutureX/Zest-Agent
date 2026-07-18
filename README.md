# Zest-Agent

> A distributed agent platform built from the ground up with **control-plane / execution-plane separation**, a **multi-layer architecture**, and a **distributed runtime** designed for horizontal scaling, persistent evolution, and real-time human-agent collaboration.

![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![Node](https://img.shields.io/badge/node-20+-green)
![Status](https://img.shields.io/badge/status-alpha-orange)

Zest-Agent 是一个**从底层设计到核心实现完全自研**的分布式智能体应用平台。采用**多层架构**（交互层 / 控制面 / 执行面 / 共享层）与**分布式调度**（服务注册 + 心跳 + 会话粘性负载均衡），基于控制面 / 执行面分离的调度模型构建；提供三层持久化 + 检查点断点恢复、可插拔存储抽象与查询门面、文件 / 网络 / 进程三层隔离沙箱、自研 eventCenter 发布-订阅事件模型、多层记忆体系与多 Agent 协同支持。目标不是再造一个能聊天的 Agent，而是把 Agent 的**运行时、记忆体系、调度能力**拆解成可扩展、可调度、可持久演进的工程化平台。

核心设计理念：

- **控制 / 计算分离** — 调度入口与执行运行时分属两个独立服务，互不耦合，各自水平扩容。
- **多层架构** — 交互层 / 控制面 / 执行面 / 共享层四层清晰分工，SDK 与工具链解耦。
- **分布式架构** — 服务注册 + 心跳 + 健康检查 + 会话粘性负载均衡，执行面多副本天然支持。

---

## 核心特性

- **控制 / 计算分离** — `zest-app-server` 只做调度与会话编排，`zest-service` 只做 Agent 执行；两进程独立部署，独立扩容。
- **多层架构** — 交互层（`zest-web`）→ 控制面（`zest-app-server`）→ 执行面（`zest-service`）→ 共享层（`zest-sdk` / `zest-tools` / `zest-common`），职责边界清晰。
- **分布式调度** — Redis 服务注册 + 心跳 + 健康检查 + 会话粘性负载均衡；也支持本地注册中心模式（单机开发免装 Redis）。
- **多层记忆体系** — 基础记忆（用户画像 / 偏好 / 上下文）+ 经验记忆（问题—方案—执行轨迹），Elasticsearch 检索。
- **实时事件流** — WebSocket 双向事件 + 自研 `eventCenter` 发布-订阅模型（`events` + `uiEvents` 双主题），可观察、可回放。
- **会话内多 Agent** — `AgentRunner` 调度骨架，Main Agent 可在同一会话内拉起 Sub Agent 协同。
- **工程化能力** — 三层持久化 + 检查点 + 启动扫描恢复；文件 / 网络 / 进程三层沙箱隔离；结构化日志 + Langfuse 集成。

---

## 架构总览

```
                        ┌──────────────────────────────────────────┐
   浏览器 / Client  ───► │  交互层  zest-web                         │
                        │  React + Vite + Zustand                  │
                        │  WebSocket 双向事件流驱动 UI 渲染          │
                        └──────────────────┬───────────────────────┘
                                           │  WebSocket / HTTP
                                           ▼
                        ┌──────────────────────────────────────────┐
                        │  控制面  zest-app-server (port 9000)      │
                        │  FastAPI · 会话编排 · 任务调度             │
                        │  AgentServer 注册发现 · 会话粘性路由       │
                        └──────────────────┬───────────────────────┘
                                           │  注册中心 + 路由
                                           ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │                    执行面 (可多副本水平扩展)                       │
   │  ┌─────────────────────────┐  ┌─────────────────────────┐       │
   │  │ zest-service :8001     │  │ zest-service :8001     │       │
   │  │ FastAPI + WebSocket    │  │ FastAPI + WebSocket    │       │
   │  │ Agent 会话生命周期      │  │ Agent 会话生命周期      │       │
   │  └──────┬──────────────────┘  └────────────────┬──────┘       │
   │         │  调用                          调用  │               │
   │         ▼                                     ▼               │
   │  zest-sdk  (Agent / LLM / Memory / Skill)  zest-tools        │
   │  zest-common (Event-Log / State / Observability)               │
   └──────────────────────────────────────────────────────────────────┘

           ↑ 注册 / 心跳 / 健康检查 ↑
   ┌──────────────────────────────────────────────────────────────────┐
   │  Redis 服务注册中心（可切本地内存模式）                            │
   │  MySQL（会话持久化） · MongoDB（事件日志） · Elasticsearch（记忆）│
   └──────────────────────────────────────────────────────────────────┘
```

更完整的架构说明见 [docs/architecture.md](docs/architecture.md)。

---

## 模块组成

| 层 | 模块 | 路径 | 职责 |
|---|---|---|---|
| 交互层 | `zest-web` | `zest-web/` | React 前端，WebSocket 事件流驱动 |
| 控制面 | `zest-app-server` | `zest-app-server/` | 会话入口、任务调度、AgentServer 注册发现、会话粘性路由 |
| 执行面 | `zest-service` | `zest-agent-server/zest-service/` | Agent 会话生命周期、WebSocket 事件订阅 |
| SDK 层 | `zest-sdk` | `zest-agent-server/zest-sdk/` | Agent 构建核心、LLM、记忆、技能、事件 |
| 工具层 | `zest-tools` | `zest-agent-server/zest-tools/` | Runtime 工具集（bash / file_editor / browser）+ 沙箱隔离 |
| 共享层 | `zest-common` | `zest-common/` | 事件日志、状态、记忆、查询门面、可观测性 |

---

## 为什么这样设计

- **为什么控制 / 计算分离**：把"决定跑哪个 Agent"和"真正跑 Agent"放在两个进程，可以独立扩容执行面，而不必把整个调度层也跟着复制一遍；故障域也更小——执行面 OOM 不会拖垮控制面。
- **为什么多层架构**：每一层只关心自己的事。前端不关心哪个 service 实例在跑；控制面不关心 LLM 怎么调；执行面不关心用户是谁。共享层把跨层共通的状态、事件、可观测性收敛到一处，避免散落各处。
- **为什么分布式架构**：单进程扛不住长会话 + 多并发 + 工具调用 IO 等待。把执行面做成可水平扩展的无状态服务（状态外置到 Redis / MySQL / Mongo / ES），靠会话粘性路由保证同一会话落到同一实例，避免状态迁移成本。

---

## 快速开始

### 前置依赖

Python 3.12+、uv、Node 20+、pnpm 9+、Redis 7+、MySQL 8.0+。可选：Docker、MongoDB 7+、Elasticsearch 8.8.2。

### 本地原生启动（推荐用于二次开发）

```bash
git clone https://github.com/CLFutureX/Zest-Agent.git
cd Zest-Agent

# 安装后端依赖
uv sync

# 安装前端依赖
cd zest-web && pnpm install && cd ..

# 启动依赖（任选其一）
docker compose up -d redis mysql          # 仅拉起依赖容器
# 或本机原生安装 redis-server / mysql-server

# 复制配置
cp .env.example                                            .env
cp zest-app-server/.env.example                            zest-app-server/.env
cp zest-agent-server/zest-service/server/.env.example     zest-agent-server/zest-service/server/.env
cp zest-web/.env.example                                   zest-web/.env
# 编辑 .env，至少设置 ZEST_SECRET_KEY 与 LLM_API_KEY

# 启动三服务
./scripts/start-dev.sh start    # Linux / macOS
./scripts/start-dev.ps1 start   # Windows
```

### Docker Compose 一键启动

```bash
git clone https://github.com/CLFutureX/Zest-Agent.git
cd Zest-Agent
cp .env.example .env  # 编辑 .env
docker compose --profile app up -d --build
```

访问 http://127.0.0.1:5173 。完整步骤见 [docs/quickstart.md](docs/quickstart.md)。

---

## 文档

- [docs/overview.md](docs/overview.md) — 完整项目介绍
- [docs/quickstart.md](docs/quickstart.md) — 快速开始
- [docs/architecture.md](docs/architecture.md) — 架构详解
- [docs/deployment.md](docs/deployment.md) — 生产部署
- 英文文档见 [docs/en/](docs/en/)

---

## 参与贡献

欢迎参与！请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。行为准则见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。安全漏洞请按 [SECURITY.md](SECURITY.md) 私密报告，**不要**在公开 issue 中讨论。

---

## License

[Apache License 2.0](LICENSE) © 2026 CLFutureX

本项目基于 [OpenHands](https://github.com/All-Hands-AI/OpenHands)（Copyright © 2025 All Hands AI，MIT License）进行架构级重构与扩展。OpenHands 原始 MIT 许可声明按 MIT 要求保留在 [NOTICE.md](NOTICE.md) 中。