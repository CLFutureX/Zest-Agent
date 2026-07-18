# Zest-Agent 项目介绍

> Zest-Agent 是一个基于 OpenHands 架构级重构的**分布式智能体应用平台**。
> 目标不是再造一个单体 Agent，而是把 Agent 的运行时、记忆体系、调度能力拆解成一个**可扩展、可调度、可持久演进**的工程化平台。
> 本文档面向想快速了解项目全貌、模块边界与设计理念的开发者与架构师。

---

## 一、项目概览

### 1.1 一句话定位

**Zest-Agent = 控制面 + 执行面分离的分布式 Agent 平台，内置多层记忆、实时事件流与多 Agent 演进能力。**

### 1.2 项目背景与起源

Zest-Agent 是一个**从底层设计到核心实现完全自研**的分布式智能体应用平台。在工程上仅复用了 OpenHands 的少量组件作为基础积木，核心运行时（AgentRunner 调度层、Agent 启动调度模型、断点恢复、数据存储抽象、沙箱隔离机制、事件模型与状态机）均为自研设计。

- **自研**：AgentRunner 调度骨架（优雅支持同一会话内多 Agent 协同）、控制面/执行面分离的调度模型、三层持久化 + 检查点的断点恢复机制、统一可插拔的存储抽象与查询门面、完整设计与实现的沙箱隔离（文件/网络/进程三层隔离）、自研 eventCenter 发布-订阅事件模型、多层记忆体系。
- **复用**：仅复用 OpenHands 的部分工具实现与数据模型片段作为基础积木。
- **合规**：OpenHands 原始 MIT 许可声明按 MIT 要求保留在 `NOTICE.md` 中。Zest-Agent 整体采用 Apache License 2.0。

License 已在 Apache License 2.0 框架下声明 Copyright 2026 CLFutureX；OpenHands 的 MIT 声明作为衍生品合规保留在 `NOTICE.md` 中。

### 1.3 核心价值主张

| 维度 | 单体 Agent（典型） | Zest-Agent |
|---|---|---|
| 架构边界 | 单进程、单代码库 | 前端 / 控制面 / 执行面 / 共享能力四层分离 |
| 扩展方式 | 纵向加配 | 横向加节点（执行面可多副本） |
| 记忆 | 单一大杂烩 | 基础记忆 + 经验记忆分层，支持 ES 检索 |
| 交互 | HTTP 轮询 / 单向流 | WebSocket 双向事件流，可观察、可回放 |
| 多 Agent | 不支持 | 调度层抽象，支持会话内 Main-Sub Agent |
| 工程化 | 个人 Demo 友好 | 任务调度、健康检查、断点恢复、可观测性 |

### 1.4 适用场景

- 企业级 Agent 应用平台：多业务方共享一套执行面，按会话隔离。
- 多 Agent 协同：主 Agent 拆解复杂任务，子 Agent 分工执行。
- 长期记忆型助手：跨会话沉淀用户画像、偏好、问题—方案—执行轨迹。
- 可观测 Agent：需要看清楚每一步思考、工具调用、状态变化的场景。
- 二次开发与教学：理解 Agent 平台工程化落地的样板项目。

### 1.5 技术栈一览

| 层 | 技术选型 |
|---|---|
| 前端 | React 18 + Vite 5 + TypeScript + Zustand + react-markdown |
| 控制面 / 执行面 | Python 3.12 + FastAPI + Uvicorn + WebSocket（wsproto） |
| SDK | Python + Litellm + Pydantic + Langfuse + FastMCP |
| 工具层 | Python + Libtmux + Bashlex + browser-use |
| 共享层 | Python + Pydantic + cachetools + filelock |
| 存储 | MySQL（默认）/ 本地文件 / MongoDB（可选）/ Elasticsearch（可选） |
| 注册与心跳 | Redis |
| 工程链 | uv workspace + pnpm + pre-commit + ruff + pytest |

---

## 二、整体架构

### 2.1 四层架构

```
┌──────────────────────────────────────────────────────────────┐
│  交互层  zest-web  (React + Vite, WebSocket 事件流驱动)        │
│  ─ 会话视图、事件渲染、状态可视化                              │
└──────────────┬───────────────────────────────────────────────┘
               │ HTTP（会话 CRUD）+ WebSocket（事件流）
┌──────────────┴───────────────────────────────────────────────┐
│  控制面  zest-app-server  (FastAPI, port 9000)                │
│  ─ 会话入口、任务调度、AgentServer 注册发现、负载均衡          │
└──────────────┬───────────────────────────────────────────────┘
               │ 内部 HTTP / WebSocket + Redis 注册表
┌──────────────┴───────────────────────────────────────────────┐
│  执行面  zest-agent-server/zest-service  (FastAPI, port 8001) │
│  ─ Agent 会话真实生命周期、WebSocket 事件订阅、事件回放        │
│  ─ 工具沙箱、技能加载、断点恢复                                │
└──────────────┬───────────────────────────────────────────────┘
               │ 共享 SDK / 工具 / 抽象
┌──────────────┴───────────────────────────────────────────────┐
│  共享能力层                                                   │
│  zest-sdk       ─ Agent 构建核心、LLM、记忆、技能、事件        │
│  zest-tools    ─ Runtime 工具集（bash / file_editor / browser）│
│  zest-common   ─ 事件日志、状态、记忆、查询门面、可观测性       │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 数据流（一次完整会话）

1. 用户在前端 `zest-web` 创建会话 → HTTP POST 到 `zest-app-server`。
2. `zest-app-server` 创建应用侧会话记录，通过调度器选择一个 `zest-service` 执行节点，并把任务信息写入 Redis 注册表。
3. 选中的 `zest-service` 拉起 Agent 运行时，订阅会话消息，开始按 LLM + 工具循环推进任务。
4. 执行过程中产生的思考、工具调用、状态变更通过 WebSocket 实时推送到 `zest-web`，前端订阅 eventCenter 的 `uiEvents` 主题渲染，运维与回放走 `events` 主题。
5. 会话产生的状态、事件、基础记忆、经验记忆分别落入共享层提供的存储抽象，由 `zest-common` 的查询门面统一读取。
6. 用户随时可通过 WebSocket 发送新消息、暂停、终止会话；会话状态持久化，支持断点恢复。

### 2.3 与 OpenHands 的关系

Zest-Agent 不是 OpenHands 的封装或改造版，而是独立自研的分布式 Agent 应用平台。OpenHands 在本项目中扮演**基础组件提供者**之一。

**核心自研**：AgentRunner 调度层、Agent 启动调度模型、断点恢复、数据存储抽象、沙箱隔离机制、事件模型与状态机、多层记忆体系。

**仅复用 OpenHands**：部分工具实现与数据模型片段。

| 维度 | OpenHands | Zest-Agent |
|---|---|---|
| 仓库形态 | 单体 | uv workspace 多包，前后端分离 |
| 运行时模型 | 单会话单 Agent | 自研 AgentRunner，支持会话内多 Agent 协同 |
| 调度模型 | 本地直接调用 | 自研控制面/执行面分离 + Redis 注册 + 负载均衡 |
| 持久化 | 文件为主 | 自研三层持久化 + 多后端可插拔 |
| 断点恢复 | 无 | 自研检查点 + 启动扫描恢复 |
| 沙箱隔离 | 简单容器隔离 | 自研三层隔离 + 沙箱生命周期管理 |
| 记忆 | 单一存储 | 自研基础 + 经验分层 + ES 检索 |
| 事件模型 | 单轨 | 自研 eventCenter 发布-订阅（events + uiEvents 双主题） |
| 前端 | OpenHands V1 | 对齐 V1 风格 + eventCenter 主题适配 |
| 注册 | 无 | Redis 心跳注册 + 健康检查 |
| 适用场景 | 个人 Agent 体验 | 团队 / 企业级 Agent 平台 |

合规性：Zest-Agent 整体采用 Apache License 2.0；衍生自 OpenHands（MIT License）的部分，其原始版权与许可声明按 MIT 要求保留在 `NOTICE.md` 中。MIT 允许衍生品再授权到 Apache 2.0。

---

## 三、核心特性设计

### 3.1 控制面 / 执行面分离

最核心的设计决策。把"谁来调度会话"和"谁来真正执行 Agent"拆开：

- **控制面 `zest-app-server`**：统一会话入口，负责鉴权、会话 CRUD、任务路由、节点选择、负载均衡。它本身不跑 Agent。
- **执行面 `zest-service`**：真实跑 Agent 的进程，通过 Redis 注册自己，按控制面分派的任务执行会话。

**收益**：
- 执行面可水平扩容（多副本），调度面无状态；
- 单点故障隔离，执行节点宕机不影响新会话；
- 天然支持多租户、多业务方共享同一执行池。

### 3.2 分布式 Agent 调度

- **服务注册**：执行节点启动后通过 `agent_registry` 写入 Redis，包含 `host:port`、`server_id`、`tags`、健康状态、负载情况。
- **心跳机制**：默认 10 秒一次心跳，30 秒未续约视为失联。
- **负载均衡**：默认 `session_affinity` 策略（同一会话粘到同一执行节点），未来可扩展最少连接、标签路由、亲和反亲和等策略。
- **节点发现**：控制面订阅注册表变化，定期同步可用节点视图。

### 3.3 多层记忆体系

把"记忆"从"一个存储"拆成"职责分明的两层"：

- **基础记忆（Basic Memory）**：面向用户长期信息，如用户画像、偏好、近期上下文。支持分类读写，体量小、命中频次高。
- **经验记忆（Experience Memory）**：面向"问题—方案—执行轨迹—反馈"沉淀。支持基于 Elasticsearch 的语义检索，体量大、可演进。

**统一存储抽象**：`zest-common` 收敛存储配置与工厂，业务层只面对 `MemoryStore` / `EventStore` / `StateStore` 等接口，不关心底层是 MySQL / Mongo / ES。

**查询门面聚合**：`conversation_read_facade` 聚合"状态 + 事件 + 基础记忆 + 经验记忆"，提供统一运行时视图，前端展示、运维排查、后续智能分析均从此读取。

### 3.4 实时事件驱动

前端不再依赖 HTTP 轮询，而是基于 WebSocket 建立"打开会话 → 建立连接 → 接收事件 → 发送消息 → 派生渲染"的实时主链路。

- **自研 eventCenter 发布-订阅模型**：所有运行时组件作为生产者发布事件到 eventCenter，订阅者按需订阅 `events` 主题（完整原始事件，供回放与排查）或 `uiEvents` 主题（折叠后适合 UI 展示的事件流）。生产者与消费者解耦，多订阅者可并行消费，前端只订阅 `uiEvents` 避免渲染压力。
- **可观察**：Agent 的思考、工具调用、状态变化、错误均以事件流呈现，配合事件日志与状态快照，具备较强的过程可视化能力。
- **可回放**：会话事件流持久化，可随时按时间轴重放。

### 3.5 多 Agent 演进（自研 AgentRunner）

通过自研 **AgentRunner 调度层**，把"谁执行这个 step"从"会话怎么走"中解耦出来。Runner 层是统一入口，对下管理多个 Agent 实例，对上对会话呈现统一接口，**优雅地支持同一会话内的多 Agent 交互**：

- **Main Agent**：会话主 Agent，负责任务拆解、子任务派发、结果整合。
- **Sub Agent**：按工具能力或角色分工的子 Agent，由 Main Agent 调用。
- **共享上下文**：Main 与 Sub 共享同一 Conversation 上下文，无需序列化传递。
- **失败隔离**：Sub Agent 失败不影响 Main Agent 继续推进。
- **可观察**：所有 Agent 产出统一经 Runner 流入事件流。
- **能力复用**：Sub Agent 可复用工具集与记忆体系。

当前多 Agent 能力仍在持续打磨，但骨架已搭好，为后续复杂任务分解、角色分工、Agent 协作预留了入口。

### 3.6 会话持久化与断点恢复（自研）

Zest-Agent 自研的断点恢复机制保障长任务不丢：

- **三层持久化**：状态存储 + 事件日志 + 消息历史，分别承担快速恢复、回放审计、LLM 上下文重建。
- **检查点机制**：AgentRunner 每 N 个 step 自动写入检查点（事件 `CheckpointWritten`），策略可配。
- **启动扫描恢复**：服务重启时扫描未完成会话，从最近检查点重放事件流重建上下文，前端无感重连。
- **节点失联迁移**：节点失联时，会话被路由到其他健康节点，从存储层读取检查点与事件日志重建上下文。
- **沙箱崩溃恢复**：沙箱容器 OOM 时，沙箱管理器重启容器，会话从最近检查点继续。

文件类工具的本地输出可能丢失（沙箱本地存储），但状态与记忆不丢。

### 3.7 服务注册与健康检查

- 执行节点自注册到 Redis，包含 `server_id`、`host:port`、`tags`、`heartbeat_at`。
- 控制面定期扫描注册表，自动剔除失联节点，路由层不再分派任务到不健康节点。
- 节点恢复后重新注册即可参与调度，无需手动介入。

### 3.8 负载均衡策略

当前默认 `session_affinity`（会话粘性），保障 WebSocket 长连接稳定。已为后续扩展预留接口：

- `least_connection`：最少活跃会话数优先。
- `tag_routing`：按节点标签路由（如 GPU 节点优先跑重 LLM 任务）。
- `affinity` / `anti_affinity`：会话或用户级亲和反亲和。

### 3.9 可观测性

- **结构化日志**：所有模块走 `zest-common` 的 logger，输出 JSON 结构化日志，便于聚合与检索。
- **Langfuse 集成**：zest-sdk 集成 Langfuse，可观察 LLM 调用链路、Token 消耗、延迟。
- **事件日志 + 状态快照**：会话级可回放、可审计。
- **健康接口**：`zest-app-server` 与 `zest-service` 均提供 `/health` 端点，便于编排系统探活。

### 3.10 沙箱隔离机制（完整自研设计）

Zest-Agent 完整设计并实现了自己的沙箱隔离机制，为 Agent 执行高权限工具（bash、文件操作、浏览器等）提供安全边界：

- **三层隔离**：文件系统隔离（沙箱独立挂载 + 工作目录隔离）、网络隔离（Docker 网络命名空间 + 出站白名单）、进程隔离（独立 PID 命名空间 + 资源限制）。
- **沙箱管理器**：`zest-tools/tools/sandbox/`，统一管理沙箱生命周期。
- **Libtmux 会话终端**：bash 命令在独立 tmux session 执行，避免 shell 状态污染，支持长命令 detach/reattach。
- **Docker 沙箱**：每个会话绑定独立容器，文件系统隔离，可选挂载 VSCode Server / VNC。
- **沙箱生命周期**：沙箱随会话创建，会话结束/超时/失联自动清理容器与 tmux session。
- **安全策略**：默认拒绝、出站白名单、文件路径校验、资源上限、审计日志。

详见 [docs/architecture.md](architecture.md) 第九节。

---

## 四、模块详细介绍

### 4.1 `zest-web` — 交互层

| 项目 | 内容 |
|---|---|
| 路径 | `zest-web/` |
| 技术栈 | React 18 + Vite 5 + TypeScript + Zustand + react-markdown |
| 默认端口 | 5173（dev）/ 自定义（生产构建） |
| 入口 | `src/main.tsx` → App |

**职责**
- 提供会话创建、消息发送、事件渲染、状态可视化的完整前端体验。
- 通过 WebSocket 订阅 eventCenter 的 `uiEvents` 主题渲染。
- 提供配置中心、会话列表、Agent 详情等管理面板。

**关键设计**
- **状态管理**：Zustand 轻量 store，按域拆分（auth、event、conversation 等），避免巨型 reducer。
- **事件组装**：`utils/buildEventGraph.ts`、`utils/runtimeEventAssembler.ts` 把原始事件流组装成可展示的对话消息、工具卡片、状态条目。
- **配置驱动**：`VITE_APP_API_BASE` 等环境变量在构建期注入，便于多环境部署。

### 4.2 `zest-app-server` — 控制面

| 项目 | 内容 |
|---|---|
| 路径 | `zest-app-server/` |
| 技术栈 | Python 3.12 + FastAPI + Uvicorn + Pydantic Settings |
| 默认端口 | 9000 |
| 入口 | `app/main.py` → `app.main:app` |

**职责**
- 统一会话入口：会话创建、查询、暂停、终止。
- 任务调度：为每个会话选择合适的执行节点。
- 服务注册中心：维护可用执行节点视图，剔除失联节点。
- 鉴权与配置：基础鉴权、配置中心、用户与 Agent Profile 管理。

**关键路由**（`app/api/`）
- `app_conversation_route`：会话 CRUD。
- `app_conversation_query_route`：会话查询（聚合视图）。
- `agentservers`：执行节点注册、发现、健康。
- `agent_profile_route`：Agent 角色与配置。
- `auth_route`：基础鉴权。
- `health`：健康检查。

**关键配置**（`app/config/settings.py`）
- `storage_mode`: `mysql` \| `local`
- `registry_mode`: `redis`
- `lb_strategy`: `session_affinity`（默认）
- `heartbeat_interval` / `heartbeat_timeout`: 10s / 30s
- `agent_service_*`: 连接执行面的协议与端点

**负载均衡**：默认会话粘性，把同一会话固定到首次命中的执行节点，保障 WebSocket 长连接稳定。

### 4.3 `zest-agent-server/zest-service` — 执行面

| 项目 | 内容 |
|---|---|
| 路径 | `zest-agent-server/zest-service/` |
| 技术栈 | Python 3.12 + FastAPI + Uvicorn + WebSocket（wsproto） |
| 默认端口 | 8001 |
| 入口 | `server/__main__.py` → `server.api:api` |

**职责**
- 真实跑 Agent 会话：会话生命周期管理、消息循环、工具调用、状态推进。
- 提供 WebSocket 事件通道：前端建立连接后接收会话执行中的事件流。
- 支持事件回放、消息发送、暂停 / 恢复 / 终止。
- 集成工具沙箱、技能加载、可选 VSCode / VNC 远程开发能力。

**关键路由**（`server/`）
- `sockets_router`：WebSocket 事件订阅与消息推送。
- `conversation_router`：会话 CRUD 与运行控制。
- `event_router`：事件查询与回放。
- `file_router`：文件操作。
- `tool_router` / `skills_router`：工具与技能发现。
- `server_details_router`：节点信息上报。

**注册上报**：启动后向 Redis `agent_registry` 写入 `server_id`、`host:port`、`tags`、`heartbeat_at`，定期续约。

**关键能力**
- **断点恢复**：会话状态持久化，重启后未完成会话可恢复。
- **崩溃诊断**：`server/__main__.py` 启用 `faulthacker` 与 `atexit`，崩溃时输出栈与正常退出日志。
- **可观测**：结构化 JSON 日志，支持 DEBUG 模式输出栈。

### 4.4 `zest-agent-server/zest-sdk` — SDK 层

| 项目 | 内容 |
|---|---|
| 路径 | `zest-agent-server/zest-sdk/` |
| 技术栈 | Python + Litellm + Pydantic + Langfuse + FastMCP |
| 版本 | 1.10.0 |

**职责**
- 提供 Agent 构建核心：`Agent` 抽象、`AgentRunner` 调度骨架、`Conversation` 抽象。
- LLM 抽象与调用：基于 Litellm 统一多家 LLM 厂商接入，含函数调用转换、流式处理。
- 技能体系：`sdk/context/skills/` 提供技能加载与执行框架。
- 事件与状态：事件总线、状态机、上下文管理。
- 安全与密钥：`sdk/secret/` 提供密钥注册与脱敏。

**关键模块**
- `sdk/agent/agent.py`、`sdk/agent/agent_runner.py`：Agent 核心。
- `sdk/llm/llm.py`、`sdk/llm/mixins/fn_call_converter.py`：LLM 调用与函数调用适配。
- `sdk/conversation/impl/conversation_impl.py`：会话实现。
- `sdk/context/skills/skill.py`：技能框架。
- `sdk/secret/`：密钥管理。

**与多 Agent 的关系**：`AgentRunner` 抽象为后续会话内 Main-Sub Agent 协同预留入口。

### 4.5 `zest-agent-server/zest-tools` — 工具层

| 项目 | 内容 |
|---|---|
| 路径 | `zest-agent-server/zest-tools/` |
| 技术栈 | Python + Bashlex + Libtmux + browser-use |
| 版本 | 1.10.0 |

**职责**
- 提供 Agent 运行时可调用的工具集：bash 执行、文件编辑、浏览器、自定义工具等。
- 沙箱与运行时隔离：基于 Libtmux 管理会话终端，配合 Docker 沙箱（`server/docker/Dockerfile`）实现安全执行。
- 工具预加载：启动时按配置预加载工具，降低首次调用延迟。

**关键模块**
- `tools/file_editor/editor.py`：文件编辑器（支持字符串替换、片段操作）。
- `tools/sandbox/`：沙箱执行环境与配置。
- `tools/preset/default.py`：默认工具集预设。
- `tools/` 各子目录：按工具类型组织。

**自定义工具**：开发者可按 SDK 接口实现自定义工具，挂载到执行面。

### 4.6 `zest-common` — 共享能力层

| 项目 | 内容 |
|---|---|
| 路径 | `zest-common/` |
| 技术栈 | Python + Pydantic + cachetools + filelock |
| 版本 | 0.2.0 |

**职责**
- 事件日志：统一事件结构、写入、查询。
- 状态存储：会话状态、运行时状态的统一抽象。
- 记忆存储：基础记忆 + 经验记忆的存储接口与多后端实现（MySQL / Mongo / ES / 本地文件）。
- 查询门面：`conversation_read_facade` 聚合状态、事件、记忆，提供统一读取入口。
- 可观测性：结构化 logger、调试工具。
- 安全：密钥与加密（`common/security/`、`common/utils/pydantic_secrets.py`）。

**关键模块**
- `common/chain/`：链式调用与流水线。
- `common/event/`：事件结构与日志。
- `common/logger/`：结构化日志。
- `common/models/`：共享数据模型。
- `common/observability/`：可观测性。
- `common/query/`：查询门面。
- `common/security/`：安全与加密。
- `common/storage/`：存储抽象与多后端实现。
- `common/utils/`：通用工具。

**可选依赖**：通过 `pyproject.toml` 的 optional-dependencies 按需引入 `pymongo`、`elasticsearch`、`boto3`，避免未使用后端也被强制安装。

---

## 五、典型使用场景

### 场景 1：企业级 Agent 应用平台
多业务方共享一套执行面，按会话隔离。控制面提供统一鉴权与配额，执行面按业务标签路由，记忆按租户分区。

### 场景 2：多 Agent 协同
主 Agent 拆解复杂任务，子 Agent 按工具能力或角色分工。例如：研究 Agent 收集资料 → 编码 Agent 实现 → 测试 Agent 验证 → 主 Agent 整合。

### 场景 3：长期记忆型助手
跨会话沉淀用户偏好（基础记忆）与"问题—方案—执行—反馈"轨迹（经验记忆）。下次相似任务时基于 ES 检索召回经验，提升响应质量。

### 场景 4：可观测 Agent 运维
会话级事件流 + 状态快照 + Langfuse LLM 链路追踪，运维与产品都能看清每一步思考、工具调用、状态变化、错误回溯。

### 场景 5：二次开发与教学
清晰的四层架构与可替换的存储后端，是理解 Agent 平台工程化落地的样板项目。可在不动核心的前提下替换 LLM、替换存储、增加工具、扩展调度策略。

---

## 六、路线图（Roadmap）

以下为初步规划，具体顺序与时间视社区反馈调整。

- **v0.1**（首发）：四层架构稳定，单节点执行面可跑通完整会话；基础记忆 + 经验记忆骨架；实时事件流；Docker Compose 一键启动。
- **v0.2**：执行面多副本横向扩展验证；负载均衡策略补齐（最少连接、标签路由）；断点恢复增强。
- **v0.3**：多 Agent 协同稳定化；Main-Sub Agent 任务编排 DSL；跨 Agent 记忆共享。
- **v0.4**：可观测性增强；运维面板；会话回放 UI；性能调优与压测。
- **v0.5**：插件化工具市场；技能模板库；多 LLM 路由策略。

详细 Issue 与里程碑见 GitHub Projects。

---

## 七、致谢与开源声明

Zest-Agent 基于 [OpenHands](https://github.com/All-Hands-AI/OpenHands)（All Hands AI，MIT License）进行架构级重构与扩展。我们感谢 OpenHands 团队为开源 Agent 生态做出的杰出贡献。

- License：Apache-2.0（详见 `LICENSE`）；衍生自 OpenHands（MIT），原 MIT 声明保留在 `NOTICE.md`
- 致敬与第三方依赖：详见 `NOTICE.md`
- 贡献指南：详见 `CONTRIBUTING.md`
- 安全披露：详见 `SECURITY.md`

本项目欢迎社区贡献，无论是 Issue 反馈、PR 修正、文档完善还是场景分享，都是对我们最大的支持。
