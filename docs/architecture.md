# 架构详解 (Architecture)

> 本文深入说明 Zest-Agent 的内部机制、组件交互、协议与设计取舍。
> 阅读前置：建议先看 [overview.md](overview.md) 了解四层架构与模块边界。

---

## 一、设计原则

Zest-Agent 是一个**从底层到设计完全自研**的分布式智能体应用平台。在工程实现上仅复用了 OpenHands 的少量组件作为基础积木，核心 Agent 运行时、调度模型、断点恢复、数据存储抽象、沙箱隔离机制、事件模型与状态机均为重新设计与实现。

1. **自研为核心，组件复用为辅助** — 核心运行时（AgentRunner、调度、持久化、隔离、事件流）100% 自研；仅复用 OpenHands 的部分工具实现与数据模型片段作为基础积木，便于社区迁移与生态对接。
2. **控制面 / 执行面分离** — 调度与执行解耦，便于水平扩容与单点故障隔离。
3. **共享抽象优先** — 事件、状态、记忆、查询等通用能力下沉到 `zest-common`，避免业务层重复实现。
4. **可观察优先** — 任何关键决策与状态变化都产生事件，事件可订阅、可持久化、可回放。
5. **可替换后端** — 存储后端（MySQL / Mongo / ES / 本地）通过抽象层切换，业务层无感知。
6. **渐进演化** — 多 Agent、调度策略、负载均衡等能力预留接口，按社区反馈渐进打磨。

---

## 二、与 OpenHands 的关系（明确边界）

Zest-Agent 不再是 OpenHands 的"封装"或"改造版"，而是一个独立的分布式 Agent 应用平台。OpenHands 在本项目中扮演的角色是*基础组件提供者*。

### 2.1 完全自研的部分

| 模块 | 说明 |
|---|---|
| **AgentRunner 调度层** | 自研的 Agent 调度骨架，统一管理 Agent 生命周期、状态流转、事件分发，支持同一会话内多 Agent 协同 |
| **Agent 启动与调度模型** | 控制面/执行面分离、Redis 注册发现、会话粘性负载均衡、任务派发机制 |
| **断点恢复机制** | 三层持久化（状态 + 事件 + 消息）+ 检查点 + 启动时扫描恢复 |
| **数据存储抽象** | 统一的 StateStore / EventStore / MemoryStore 接口、多后端可插拔、工厂模式实例化、查询门面聚合 |
| **沙箱隔离机制** | 完整设计并实现的工具沙箱：Libtmux 会话终端 + Docker 沙箱 + 文件/网络/进程三层隔离 + 沙箱生命周期与会话绑定 |
| **事件模型与状态机** | 自研 eventCenter 发布-订阅中心（events + uiEvents 双主题）、事件折叠器、会话状态机（created/running/paused/error/finished） |
| **多层记忆体系** | 基础记忆 + 经验记忆分层、ES 语义检索、统一查询门面 |

### 2.2 复用 OpenHands 的部分

- **部分工具实现**：作为基础工具积木（如 bash 解析、文件编辑器的部分逻辑）
- **部分数据模型片段**：消息格式、工具调用 schema 等

> 复用的部分均按 MIT 要求在 [NOTICE.md](../NOTICE.md) 中保留原始版权与许可声明。Zest-Agent 整体采用 Apache License 2.0。

### 2.3 与 OpenHands 的对照

| 维度 | OpenHands | Zest-Agent |
|---|---|---|
| 运行时模型 | 单进程单 Agent | 自研 AgentRunner，支持会话内多 Agent 协同 |
| 调度模型 | 本地直接调用 | 自研控制面/执行面分离 + Redis 注册 + 负载均衡 |
| 持久化 | 文件为主 | 自研三层持久化 + 多后端可插拔 |
| 断点恢复 | 无 | 自研检查点 + 启动扫描恢复 |
| 沙箱隔离 | 简单容器隔离 | 自研三层隔离（文件/网络/进程）+ 沙箱生命周期管理 |
| 记忆体系 | 单一存储 | 自研基础 + 经验分层 + ES 检索 |
| 事件模型 | 单轨 | 自研 eventCenter 发布-订阅（events + uiEvents 双主题） |
| 前端 | OpenHands V1 | 对齐 V1 风格 + eventCenter 主题适配 |
| 适用场景 | 个人 Agent 体验 | 团队 / 企业级 Agent 平台 |

---

## 三、组件交互图

### 3.1 静态依赖关系

```
zest-web (React)
   │
   │ HTTP/WebSocket
   ▼
zest-app-server ──(import)──▶ zest-common
   │                          ▲
   │ HTTP/WebSocket           │
   ▼                          │
zest-service ──(import)──▶ zest-sdk ──(import)──▶ zest-tools
   │                              │
   │ Redis (registry/heartbeat)   │
   ▼                              ▼
Redis                          MySQL / Mongo / ES
```

### 3.2 一次完整会话时序

```
浏览器        zest-web    app-server    service      Redis       Storage
  │              │            │            │           │            │
  │─创建会话────▶│            │            │           │            │
  │              │─POST /conv▶│            │           │            │
  │              │            │─选节点─────▶│           │            │
  │              │            │  (查注册表)│           │            │
  │              │            │◀─节点列表─│           │            │
  │              │            │─派发任务 (HTTP)────────▶│            │
  │              │            │            │─注册心跳─▶│            │
  │              │            │            │           │            │
  │              │◀─会话ID───│            │           │            │
  │◀─会话ID──────│            │            │           │            │
  │              │            │            │           │            │
  │─WebSocket连接──────────────────────────▶│            │            │
  │              │            │            │           │            │
  │─发送消息 (WS)──────────────────────────▶│           │            │
  │              │            │            │─AgentRunner 循环         │
  │              │            │            │  Main / Sub Agent 协同   │
  │              │            │            │  LLM + 工具（沙箱内）    │
  │              │            │            │─写事件/状态/记忆─────────▶│
  │              │            │            │─检查点 snapshot──────────▶│
  │◀─事件流 (WS)───────────────────────────│            │            │
  │              │            │            │           │            │
  │              │            │            │─续心跳─────▶│            │
```

---

## 四、事件模型（自研发布-订阅模型 eventCenter）

Zest-Agent 自研的 **eventCenter** 是核心事件分发中心，采用发布-订阅（pub-sub）模型统一管理所有运行时事件的产生、流转与消费。所有运行时组件（AgentRunner、Agent、工具调用、LLM 调用、状态机、沙箱管理器、记忆子系统等）都是 eventCenter 的生产者；持久化订阅器、WebSocket 推送订阅器、可观测性订阅器、前端 UI 订阅器等都是 eventCenter 的订阅者。

### 4.1 eventCenter 与双主题设计

eventCenter 提供两个核心主题（topic），分别面向不同消费者：

| 主题 | 内容 | 持久化 | 主要订阅者 |
|---|---|---|---|
| `events` | **完整原始事件**，供回放、审计、调试 | 是 | 事件日志（持久化）+ 可观测性 + WebSocket（按需） |
| `uiEvents` | **折叠后的 UI 友好事件流**，专门给前端渲染 | 否（按需） | WebSocket → 前端渲染 |

`uiEvents` 是 `events` 的折叠视图，由 eventCenter 内部的事件折叠器（event folder）从原始事件流按规则转换而来。两个主题独立投递，订阅者按需订阅。

### 4.2 为什么采用发布-订阅 + 双主题

**为什么用发布-订阅模型**：
- **多订阅者解耦**：一次事件产生可被多个订阅者消费（持久化、推送、可观测、UI 渲染），生产者无需感知消费者
- **可扩展**：未来可加新主题（如 metricsStream、auditStream）而不影响生产者
- **背压控制**：订阅者可按自身速率消费，慢消费者不阻塞快消费者
- **可重放**：订阅者可从任意 offset 重放事件流（依赖 `events` 主题持久化）

**为什么需要双主题**：
- `events` 必须完整、严谨、可重放，因此包含大量内部细节（状态机变更、错误堆栈、调试信息、子 Agent 派发、检查点写入）。
- 前端若直接订阅 `events` 会信息过载、渲染卡顿——一个会话可能产生数千个内部事件。
- `uiEvents` 是折叠视图：把"AgentThinking → ToolCallStarted → ToolCallFinished"折叠成一张工具卡片，把 100 个内部状态变更折叠成 1 个"运行中"指示器。
- 前端只订阅 `uiEvents`，运维排查与回放走 `events`。

### 4.3 eventCenter 架构与数据流

```
┌──────────────────────────────────────────────────────────────┐
│  生产者（Producers）                                           │
│  ┌─────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ AgentRunner │  │ Agent    │  │ Tools    │  │ LLM Call │  │
│  └─────────────┘  └──────────┘  └──────────┘  └──────────┘  │
│  ┌─────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ StateMachine│  │ Sandbox  │  │ Memory   │  │  ...     │  │
│  └─────────────┘  └──────────┘  └──────────┘  └──────────┘  │
└────────────────────────┬─────────────────────────────────────┘
                         │ publish(event)
                         ▼
              ┌────────────────────────┐
              │   eventCenter（自研）    │
              │  ┌──────────────────┐  │
              │  │ 事件路由 & 分发    │  │
              │  ├──────────────────┤  │
              │  │ 事件折叠器        │  │
              │  │ (events→uiEvents)│  │
              │  ├──────────────────┤  │
              │  │ 主题管理          │  │
              │  └──────────────────┘  │
              └─────┬──────────────┬───┘
                    │              │
            subscribe(events)  subscribe(uiEvents)
                    │              │
                    ▼              ▼
   ┌────────────────────┐   ┌────────────────────┐
   │ 订阅者 A：持久化     │   │ 订阅者 B：WebSocket │
   │ 写入事件日志/存储    │   │ 推送给前端          │
   └────────────────────┘   └────────────────────┘
   ┌────────────────────┐   ┌────────────────────┐
   │ 订阅者 C：可观测性   │   │ 订阅者 D：审计      │
   │ Langfuse / metrics  │   │ 安全审计日志        │
   └────────────────────┘   └────────────────────┘
```

### 4.4 事件类型（部分）

| 事件类型 | 触发时机 | 关键字段 |
|---|---|---|
| `ConversationStarted` | 会话开始 | `conversation_id`, `user_id` |
| `MessageReceived` | 用户消息到达 | `conversation_id`, `content` |
| `AgentThinking` | Agent 思考中 | `thought`, `step_id` |
| `ToolCallStarted` | 工具调用开始 | `tool_name`, `args` |
| `ToolCallFinished` | 工具调用结束 | `result`, `duration_ms` |
| `SubAgentDispatched` | Main Agent 派发子 Agent | `parent_step_id`, `sub_agent_id` |
| `SubAgentReturned` | 子 Agent 返回 | `sub_agent_id`, `result` |
| `LLMCallStarted` | LLM 调用开始 | `model`, `messages_count` |
| `LLMCallFinished` | LLM 调用结束 | `tokens`, `latency_ms` |
| `StateChanged` | 状态机变更 | `from`, `to` |
| `CheckpointWritten` | 检查点写入完成 | `step_id`, `snapshot_id` |
| `MemoryWritten` | 记忆写入 | `category`, `key` |
| `MemoryRetrieved` | 记忆检索 | `query`, `hits` |
| `ErrorOccurred` | 错误发生 | `type`, `message`, `traceback` |
| `ConversationFinished` | 会话结束 | `conversation_id`, `reason` |

### 4.5 WebSocket 协议

**连接**：`ws(s)://<host>:8001/sockets?conversation_id=<id>`

**消息方向**：
- 客户端 → 服务端：`send_message`、`pause`、`resume`、`terminate`
- 服务端 → 客户端：事件流（上述事件类型）

**消息格式**（JSON）：
```json
{
  "type": "ToolCallStarted",
  "conversation_id": "conv_abc123",
  "step_id": "step_001",
  "timestamp": "2026-07-12T10:00:00.000Z",
  "payload": {
    "tool_name": "bash",
    "args": { "command": "ls -la" }
  }
}
```

---

## 五、Agent 运行时（自研 AgentRunner）

### 5.1 AgentRunner 设计动机

传统单进程单 Agent 模型在以下场景下捉襟见肘：
- 同一会话内需要多个 Agent 角色分工（如规划 Agent + 执行 Agent + 审查 Agent）
- 子任务需要并行或异步执行
- Agent 失败需要切换备用角色而非整会话失败

Zest-Agent 自研 **AgentRunner** 作为调度骨架，把"谁执行这个 step"从"会话怎么走"中解耦出来。Runner 层是统一入口，对下管理多个 Agent 实例，对上对会话呈现统一接口。

### 5.2 核心抽象

```
┌──────────────────────────────────────────────────────┐
│  AgentRunner (自研调度骨架)                            │
│   ├─ 会话级路由：根据 step 类型选择 Agent              │
│   ├─ Main Agent：会话主 Agent，负责任务拆解与整合      │
│   ├─ Sub Agent 池：按工具能力 / 角色分工的子 Agent     │
│   ├─ 生命周期管理：Agent 创建 / 复用 / 释放            │
│   ├─ 事件分发：所有 Agent 产出统一经 Runner 流出       │
│   └─ 状态共享：通过 Conversation 上下文共享记忆与状态   │
└──────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│  Conversation (会话上下文)                             │
│   ├─ LLM (litellm 抽象)                              │
│   ├─ Tools (来自 zest-tools，沙箱内执行)              │
│   ├─ Skills (来自 zest-sdk/context/skills)           │
│   └─ Memory (来自 zest-common，基础 + 经验分层)        │
└──────────────────────────────────────────────────────┘
```

### 5.3 同一会话内的多 Agent 交互

通过 Runner 层，**同一个会话**可以挂载多个 Agent 角色：

```
用户消息 → Main Agent 拆解任务
   ├─ Sub Agent A（搜索）→ 返回结果
   ├─ Sub Agent B（编码）→ 返回代码
   └─ Sub Agent C（审查）→ 返回审查意见
       ↓
   Main Agent 整合 → 输出最终回复
```

**优雅性体现**：
- Main 与 Sub 共享同一 Conversation 上下文，无需序列化传递
- Sub Agent 的产出自动作为事件流的一部分，前端可观察
- Sub Agent 失败不影响 Main Agent 继续推进
- 后续可演进为基于 DSL 的任务编排

### 5.4 Agent 循环（ReAct 风格，自研实现）

```
1. 接收用户消息或恢复的上下文
2. AgentRunner 选择当前应执行的 Agent
3. 选定 Agent 执行循环：
   a. Thinking：LLM 决定下一步动作
   b. Action：调用工具 / LLM / 写记忆
   c. Observation：结果反馈给 LLM
   d. 判断是否结束（完成 / 错误 / 需要切换 Agent）
4. AgentRunner 接收 Agent 产出，决定：
   - 继续由当前 Agent 推进
   - 切换到其他 Agent
   - 派发 Sub Agent
   - 终止会话
5. 全程产出事件流，写入事件日志，定期 checkpoint
```

### 5.5 会话状态机

```
              ┌──────────┐
              │ created  │
              └────┬─────┘
                   ▼
              ┌──────────┐
       ┌──────│ running  │──────┐
       │      └──────────┘      │
       ▼           ▲              ▼
  ┌──────────┐    │         ┌──────────┐
  │ paused   │────┘         │ error    │
  └──────────┘              └──────────┘
       │                          │
       │ resume                   │ retry
       └──────────────────────────┘
                   ▼
              ┌──────────┐
              │ finished │
              └──────────┘
```

状态变更触发 `StateChanged` 事件并持久化到状态存储，是断点恢复的基础。

---

## 六、自研的会话调度与生命周期

### 6.1 控制面派发

`zest-app-server` 收到会话创建请求后：
1. 创建应用侧会话记录
2. 查询 Redis 注册表，选择可用执行节点
3. 按负载均衡策略选目标节点（默认 `session_affinity`）
4. 通过 HTTP 把任务派发给执行节点
5. 返回会话 ID 给前端

### 6.2 服务注册协议

`zest-service` 启动时向 Redis 写入注册条目：

```
Key:   agent_registry:<server_id>
Value: {
  "server_id": "...",
  "host": "0.0.0.0",
  "port": 8001,
  "tags": ["default"],
  "heartbeat_at": 1730000000,
  "status": "healthy",
  "active_sessions": 0
}
TTL:   30s
```

每 10 秒续约一次；连续 3 次未续约（30 秒）视为失联。

### 6.3 负载均衡策略

| 策略 | 行为 | 当前支持 |
|---|---|:---:|
| `session_affinity` | 同一会话固定到首次命中的节点 | :white_check_mark: |
| `least_connection` | 选活跃会话数最少的节点 | :construction: 计划中 |
| `tag_routing` | 按节点标签路由（如 GPU 节点） | :construction: 计划中 |
| `affinity` / `anti_affinity` | 会话或用户级亲和反亲和 | :construction: 计划中 |

---

## 七、自研的断点恢复机制

Zest-Agent 的断点恢复是核心自研能力之一，保障长任务在服务重启、节点失联后不丢失。

### 7.1 三层持久化

| 层 | 内容 | 用途 |
|---|---|---|
| 状态存储 | 会话状态机当前状态、运行参数 | 快速恢复到最近状态 |
| 事件日志 | 完整事件流（按时间序） | 重放、审计、调试 |
| 消息历史 | 用户与 Agent 的消息序列 | LLM 上下文重建 |

### 7.2 检查点机制

- AgentRunner 每 N 个 step 自动写入检查点（事件 `CheckpointWritten`）
- 检查点包含：会话状态快照 + 当前 step ID + 关键运行参数
- 写入策略可配（每步 / 每 5 步 / 每 30 秒）

### 7.3 恢复流程

```
zest-service 启动
   │
   ▼
扫描未完成会话（状态为 running / paused 的会话）
   │
   ▼
对每个未完成会话：
   1. 读取最近检查点
   2. 重放检查点之后的事件流（重建 Agent 上下文）
   3. 重新注册到 Redis
   4. 等待前端 WebSocket 重连
   5. 从断点继续 Agent 循环
```

**透明性**：用户无感知。前端断线重连后，会继续接收事件流，包括重放的部分。

### 7.4 节点失联下的会话迁移

- 控制面发现节点失联（心跳超时）后，把该节点上的会话标记为待恢复
- 失联节点的会话被路由到其他健康节点
- 新节点从存储层读取该会话的检查点与事件日志，重建上下文
- 文件类工具的本地输出会丢失（沙箱本地存储），但状态与记忆不丢

---

## 八、自研的数据存储抽象

### 8.1 后端矩阵

| 用途 | MySQL | Mongo | ES (8.8.2) | 本地文件 |
|---|:---:|:---:|:---:|:---:|
| 状态存储 | :white_check_mark: | :white_check_mark: | :x: | :white_check_mark: |
| 事件日志 | :white_check_mark: | :white_check_mark: | :x: | :white_check_mark: |
| 基础记忆 | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| 经验记忆 | :x: | :white_check_mark: | :white_check_mark: | :x: |

> 默认配置：MySQL（状态 + 事件 + 基础记忆），ES 可选（经验记忆检索）。

### 8.2 抽象层结构

```
common/storage/
├── state/         ─ 状态存储抽象 + 实现
├── event/         ─ 事件日志抽象 + 实现
├── memory/
│   ├── basic/     ─ 基础记忆抽象 + 实现
│   ├── experience/─ 经验记忆抽象 + 实现
│   └── embedding/ ─ 向量嵌入抽象
└── factory.py     ─ 后端工厂，按配置实例化
```

### 8.3 工厂模式实例化

业务层只面对 `StateStore` / `EventStore` / `MemoryStore` 接口，存储后端在启动时由工厂按配置（`.env` 中的 `STORAGE_MODE` / `MEMORY_BACKEND` 等）实例化。切换后端无需改业务代码。

### 8.4 查询门面

`zest-common/common/query/conversation_read_facade.py` 聚合：

```
conversation_read_facade.get(conversation_id) -> {
  "state": ...,
  "events": [...],
  "basic_memory": {...},
  "experience_memory": [...]
}
```

业务层、前端展示、运维排查、后续智能分析均从此门面读取，避免直接耦合到底层存储。

---

## 九、自研的沙箱隔离机制（完整设计与实现）

Zest-Agent **完整设计并实现了**自己的沙箱隔离机制，用于在 Agent 执行工具（特别是 bash、文件操作、浏览器等高权限工具）时提供安全边界。

### 9.1 三层隔离

| 隔离层 | 机制 | 防护目标 |
|---|---|---|
| **文件系统隔离** | 沙箱独立挂载 + 只读关键目录 + 工作目录隔离 | 防止越权读写宿主文件 |
| **网络隔离** | Docker 网络命名空间 + 可选出站白名单 | 防止 Agent 越权访问内网 |
| **进程隔离** | 独立 PID 命名空间 + 资源限制（CPU / 内存） | 防止恶意进程逃逸与资源耗尽 |

### 9.2 架构组成

```
┌─────────────────────────────────────────────────────────┐
│  Conversation 会话                                       │
│   └─ AgentRunner                                         │
│        └─ Tool Call（如 bash, file_editor, browser）     │
│             │                                            │
│             ▼                                            │
│  沙箱管理器（zest-tools/tools/sandbox/，自研）            │
│   ├─ Libtmux 会话终端：bash 命令在独立 tmux session 执行  │
│   ├─ Docker 容器：每个会话绑定一个容器实例                │
│   ├─ 资源限制：cgroup-backed CPU/内存限制                │
│   └─ 生命周期：沙箱随会话创建，会话结束自动清理           │
└─────────────────────────────────────────────────────────┘
```

### 9.3 Libtmux 会话终端

- 每个 Agent 会话绑定一个独立 tmux session
- bash 工具调用在 tmux session 内执行，避免 shell 状态污染
- 支持长时命令的 detach / reattach
- 命令输出通过事件流回传给前端

### 9.4 Docker 沙箱

- 沙箱镜像见 `zest-agent-server/zest-service/server/docker/Dockerfile`
- 每个会话启动独立容器，文件系统隔离
- 可选挂载 VSCode Server / VNC，支持远程开发场景
- 沙箱内的工具调用结果通过 WebSocket 流回

### 9.5 沙箱生命周期

```
会话创建
   │
   ▼
沙箱管理器启动容器 + tmux session
   │
   ▼
Agent 执行工具 → 沙箱内执行 → 结果流回
   │
   ▼
会话结束 / 超时 / 失联
   │
   ▼
沙箱管理器清理容器 + tmux session
```

### 9.6 安全策略

- 默认拒绝：未在策略中显式允许的操作一律拒绝
- 出站白名单：网络出站默认仅允许 LLM API 域名
- 文件路径校验：工具调用前校验路径在沙箱工作目录内
- 资源上限：单会话 CPU / 内存 / 执行时长可配
- 审计日志：所有沙箱操作写入事件日志

---

## 十、记忆子系统

### 10.1 基础记忆（Basic Memory）

- **存什么**：用户画像、偏好、近期上下文摘要。
- **特点**：体量小、命中频次高、按分类读写。
- **后端**：MySQL / Mongo / 本地文件均可，开发友好。

### 10.2 经验记忆（Experience Memory）

- **存什么**：问题—方案—执行轨迹—反馈。
- **特点**：体量大、需语义检索、可演进。
- **后端**：ES（语义检索）或 Mongo（带向量索引时）。
- **写入时机**：会话结束时由 AgentRunner 决定是否沉淀经验。
- **召回方式**：基于当前问题的语义相似度检索 Top-K 经验，注入到 LLM 上下文。

### 10.3 记忆分层收益

| 维度 | 单一大杂烩 | Zest-Agent 分层 |
|---|---|---|
| 命中效率 | 全量扫描 | 分类直接命中（基础）+ 索引召回（经验） |
| 可解释 | 难以区分 | 基础 / 经验职责清晰 |
| 演进性 | 难 | 经验可独立优化、迁移、版本化 |
| 成本 | 全部走语义检索 | 高频走基础、低频走经验，成本可控 |

---

## 十一、可观测性

### 11.1 三层可观察

| 层 | 机制 | 用途 |
|---|---|---|
| 进程层 | `faulthandler` + `atexit` | 崩溃栈与正常退出日志 |
| 应用层 | 结构化 JSON 日志（`zest-common/common/logger/`） | 运行时排查 |
| 业务层 | 事件流 + Langfuse | 会话级回放与 LLM 链路追踪 |

### 11.2 日志结构

```json
{
  "timestamp": "2026-07-12T10:00:00.000Z",
  "level": "INFO",
  "logger": "zest-service.conversation_service",
  "message": "Agent step completed",
  "conversation_id": "conv_abc123",
  "step_id": "step_001",
  "duration_ms": 1234
}
```

### 11.3 健康接口

- `zest-app-server`：`GET /health` → 进程存活 + Redis 连通 + 存储连通
- `zest-service`：`GET /health` → 进程存活 + Redis 连通

便于 K8s / 负载均衡探活。

---

## 十二、故障与恢复

### 12.1 失败模式

| 失败 | 影响 | 恢复 |
|---|---|---|
| `zest-app-server` 宕机 | 新会话无法创建，已有 WebSocket 断连 | 重启后无状态恢复 |
| `zest-service` 宕机 | 该节点会话中断 | 控制面剔除节点，新会话路由到其他节点；已持久化的会话从断点恢复（见第七节） |
| Redis 宕机 | 注册中心不可用，但已有连接不立即中断 | Redis 恢复后节点重新注册 |
| MySQL 宕机 | 状态写入失败 | 重试 + 降级到只读 |
| LLM 调用失败 | 当前步骤失败 | 重试 / 切换备用模型 / 上报错误事件 |
| 沙箱容器 OOM | 当前工具调用失败 | 沙箱管理器重启容器，会话从最近检查点恢复 |

### 12.2 恢复能力对照

| 场景 | 无断点恢复 | Zest-Agent 自研断点恢复 |
|---|---|---|
| 服务重启 | 会话全丢 | 从最近检查点恢复，前端无感重连 |
| 节点失联 | 节点上的会话全丢 | 会话迁移到其他节点，从检查点恢复 |
| 沙箱崩溃 | 工具调用中断，会话卡死 | 沙箱重启，从断点继续 |
| 长任务中断 | 进度全丢 | 进度持久化，重启后续跑 |

---

## 十三、安全模型

### 13.1 鉴权分层

| 接口 | 鉴权方式 | 配置 |
|---|---|---|
| 前端 → app-server | 应用层鉴权（auth_route） | `AUTH_*` 环境变量 |
| app-server → service | Session API Key | `ZEST_SESSION_API_KEYS` |
| 前端 → service（WebSocket） | Session API Key（透传） | 同上 |

### 13.2 加密

- `ZEST_SECRET_KEY` 用于加密敏感字段（如记忆中的隐私数据）。
- `common/security/` 提供加密工具。
- `pydantic_secrets.py` 实现密钥脱敏，避免日志泄漏。

### 13.3 沙箱（见第九节）

Zest-Agent 的安全模型以沙箱为核心，而非仅靠应用层鉴权。所有高权限工具调用都被强制在沙箱内执行。

---

## 十四、扩展点

| 扩展点 | 入口 | 说明 |
|---|---|---|
| 新增工具 | `zest-agent-server/zest-tools/tools/` | 实现 Tool 接口，注册到 preset 或自定义 |
| 新增技能 | `zest-agent-server/zest-sdk/sdk/context/skills/` | 实现 Skill 接口 |
| 新增 LLM 厂商 | litellm 已支持，无需改代码 | 改 `.env` 的 `LLM_BASE_URL` 与 `LLM_MODEL` |
| 新增存储后端 | `zest-common/common/storage/<type>/` | 实现 StateStore / EventStore / MemoryStore 接口 |
| 新增调度策略 | `zest-app-server/app/core/services/` 调度器 | 实现 Selector 接口 |
| 新增 Agent 角色 | `zest-sdk/sdk/agent/` | 实现 Agent 接口，挂到 AgentRunner |
| 自定义沙箱策略 | `zest-tools/tools/sandbox/config/` | 修改资源限制、网络白名单、文件路径校验规则 |

---

## 十五、未完待续

- 多 Agent 协同的详细时序与编排 DSL
- 调度策略的具体实现
- 经验记忆的语义检索召回算法
- 沙箱资源配额与多租户隔离的深度验证
- 性能基线与压测数据

欢迎在 GitHub Discussions 提出你最关心的部分，我们会优先补齐。
