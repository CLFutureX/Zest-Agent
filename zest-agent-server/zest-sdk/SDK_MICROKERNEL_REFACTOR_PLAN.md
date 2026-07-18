# SDK 微内核重构方案

## 背景
基于现有 `SDK_ARCHITECTURE_ANALYSIS.md` 的分析，`zest-sdk/sdk` 已经具备完整智能体运行时平台的形态，但核心复杂度正持续向少数大类聚集，尤其集中在 `LocalConversation`、`RemoteConversation`、`ConversationState`、`AgentState` 等编排核心中。

当前架构的主要问题并不是“模块太多”，而是“运行时内核边界不清晰”：

1. 会话编排承担了过多能力装配职责；
2. 状态模型同时承担状态定义、持久化、恢复相关职责；
3. 本地/远程执行不仅是运行环境差异，还混入了较多业务语义；
4. 工具、MCP、插件、Hook、安全、观测等能力扩展缺少统一装配协议；
5. 新功能继续叠加时，系统更容易演化为几个巨型核心对象，而不是围绕稳定内核生长的插件式系统。

因此，若希望在不牺牲现有能力的前提下降低复杂度，最合理的演进方向不是简单删模块，而是将 SDK 重构为 `微内核（Microkernel） + 插件（Plugins） + 适配器（Adapters） + 策略（Policies）` 的运行时架构。

## 为什么采用微内核
微内核架构的核心价值，不是“更轻”，而是“把稳定能力与变化能力分离”。

对于当前 SDK 来说：

- `稳定能力` 是：会话生命周期、状态机、事件总线、扩展注册协议、持久化契约、调度接口；
- `变化能力` 是：LLM 接入方式、Tool 体系、MCP 集成、Workspace 实现、安全策略、可观测性、Hook、Skills、Memory、Critic。

现状中，很多变化能力仍然直接依附在核心编排类上，导致核心变厚。微内核重构的目标，是把这些变化能力从“写死在内核类中的实现细节”改造成“围绕稳定内核接入的可插拔扩展”。

对你们这套 SDK 来说，微内核改造能带来四个直接收益：

1. **降低核心类复杂度**：把 `LocalConversation` / `RemoteConversation` 从大总控类降为门面；
2. **提高模块可替换性**：LLM、Workspace、MCP、Security 等能力可独立替换；
3. **统一扩展模型**：不再让插件、Hook、Tool、MCP 以多种风格散落在运行时主链路；
4. **提升后续演化稳定性**：新能力优先作为插件接入，而不是继续侵入核心会话类。

## 目标架构
建议将目标架构调整为四层：

```text
Microkernel Core
├── Conversation State Machine
├── Event Bus
├── Capability Registry
├── Extension Lifecycle
├── Scheduling / Execution Contracts
└── Persistence Contracts

Policy Layer
├── Security Policy
├── Confirmation Policy
├── Scheduling Policy
├── Recovery Policy
└── Extension Resolution Policy

Plugin Layer
├── LLM Plugin
├── Tool Plugin
├── MCP Plugin
├── Workspace Plugin
├── Hooks Plugin
├── Observability Plugin
├── Memory / Skills Plugin
└── Critic Plugin

Adapter Layer
├── Local Runtime Adapter
├── Remote Runtime Adapter
├── LiteLLM Adapter
├── HTTP / WebSocket Adapter
├── Local FS / Git Adapter
└── External MCP Adapter
```

这个结构中：

- `Core` 只保留最小运行时闭环；
- `Policy` 负责内核执行时的规则选择；
- `Plugin` 提供运行时能力；
- `Adapter` 负责与外部具体实现、协议、基础设施打交道。

## 内核边界设计
### 内核应该保留什么
微内核应当只保留“没有这些就无法运行”的最小抽象：

1. `Conversation State Machine`
   - 会话生命周期
   - 运行状态迁移
   - 事件驱动状态推进

2. `Event Bus`
   - 统一事件发布与订阅
   - 支持本地消费者、远端同步、持久化消费者、调试消费者

3. `Capability Registry`
   - 内核只知道“系统当前有哪些能力”
   - 但不知道这些能力由 Tool、MCP 还是 Plugin 提供

4. `Extension Lifecycle`
   - discover
   - resolve
   - merge
   - activate
   - deactivate

5. `Execution Contracts`
   - 消息如何进入执行循环
   - 执行器如何消费上下文和能力
   - 执行结果如何回写状态

6. `Persistence Contracts`
   - 状态快照接口
   - 事件存储接口
   - 恢复接口

### 内核不应该保留什么
以下内容不应继续直接嵌在内核主类中：

- LiteLLM 具体调用实现
- Tool 的具体发现与实例化策略
- MCP client 连接管理
- 本地命令执行与 Git 操作细节
- WebSocket / HTTP 远程同步细节
- 安全分析器具体实现
- Hook 配置解释与执行器具体逻辑
- Observability / logger 的具体接入实现

换句话说，内核应只拥有“协议”和“生命周期”，不拥有大量“具体实现细节”。

## 插件层与适配层边界
### 应作为插件接入的模块
以下模块建议重构为标准化插件能力：

1. `LLM`
   - 当前是重要核心模块，但在微内核视角下，它应该是 `ReasoningCapabilityPlugin`
   - 内核只关心“是否存在推理能力”，不关心底层是不是 LiteLLM

2. `Tool`
   - 工具系统保留协议，但具体工具集合、内置工具、注册工具、MCP工具都应统一映射为 capability provider

3. `MCP`
   - 当前建议视为外部能力插件，而不是会话编排默认内建逻辑

4. `Hooks`
   - Hook 本质是生命周期扩展器，天然适合作为插件

5. `Security`
   - 安全分析、确认策略、风险评估都应属于策略插件或治理插件

6. `Observability`
   - 埋点、span、trace、运行日志增强应是可选插件，而不是内核必带实现

7. `Memory / Skills / Critic`
   - 本质都是对推理流程进行补充或约束的扩展能力，适合统一纳入扩展模型

### 应作为适配器下沉的模块
以下模块建议从主业务编排中下沉为 adapter：

1. `LocalConversation` 相关本地运行细节
2. `RemoteConversation` 相关远程通信细节
3. `workspace.local` / `workspace.remote`
4. HTTP / WebSocket 连接层
5. LiteLLM provider 层
6. Local FS / Git / IO 具体实现

本地与远程不应被视为“两套主要业务类”，而应被视为“同一内核的两种运行时适配方式”。

## 模块迁移映射建议
建议按照下表理解现有模块的未来归宿：

| 当前模块 | 当前角色 | 目标归属 |
| --- | --- | --- |
| `conversation.base` | 会话抽象 | 保留在 Kernel Contracts |
| `conversation.conversation` | 会话工厂门面 | 保留为 Facade |
| `conversation.impl.local_conversation` | 本地运行总控 | 拆为 Facade + Local Runtime Adapter + Bootstrapper | 
| `conversation.state` | 状态中心 + 持久化行为 | 拆为 State Model + Persistence Adapter |
| `context.agent_state` | 配置快照 + 执行态 + 元数据 | 拆为 AgentSnapshot + AgentRuntimeState |
| `agent.base` | Agent 配置中心 | 收敛为 Agent Descriptor / Agent Definition |
| `tool.*` | 工具协议与实现 | 协议保留，具体能力插件化 |
| `mcp.*` | 外部工具桥接 | MCP Plugin + MCP Adapter |
| `workspace.*` | 环境抽象与实现 | 协议保留，具体实现适配器化 |
| `security.*` | 安全治理 | Policy Plugin |
| `observability.*` | 可观测增强 | Observability Plugin |
| `hooks.*` | 生命周期扩展 | Hook Plugin |
| `plugin.*` | 扩展装配 | 升级为统一 Extension System |

## 优先级建议
### P0：必须优先做，收益最大
#### 1. 瘦身 `LocalConversation`
这是重构的第一优先级。

目标：让 `LocalConversation` 仅保留外部 API 门面职责，不再直接承担状态创建、事件消费者注册、插件加载、执行引擎装配、持久化绑定等大量内部装配逻辑。

建议拆出：
- `ConversationBootstrapper`
- `RuntimeAssembly`
- `PluginLifecycleManager`
- `ConversationExecutionEngine`

原因：
- 当前最大复杂度集中点就在这里；
- 如果不先瘦身，本地模式会持续成为所有新能力的堆放点；
- 这是后续微内核抽象最重要的突破口。

#### 2. 建立统一扩展协议
这是第二优先级。

目标：定义统一的 `Extension` / `CapabilityProvider` 接口，把 Tool、MCP、Hook、Security、Observability 等能力接入方式先统一起来。

先统一接口，不要求第一阶段彻底改完所有实现。

原因：
- 微内核架构最怕“内核提出了口号，但周边扩展仍各走各路”；
- 先收敛扩展协议，后续迁移才不会碎片化。

#### 3. 状态模型与持久化剥离
目标：让 `ConversationState` 回归纯状态中心，不再承担过多保存/恢复实现逻辑。

建议新增：
- `ConversationStateRepository`
- `EventStoreAdapter`
- `SnapshotSerializer`

原因：
- 这是建立稳定内核边界的必要条件；
- 状态模型不纯，后面插件化和执行器抽象都会被拖住。

### P1：第二阶段，解决复杂度扩散
#### 4. 拆分 `RemoteConversation`
目标：把当前远程会话分拆为：
- `RemoteRuntimeAdapter`
- `RemoteApiClient`
- `RemoteEventStreamClient`
- `RemoteStateMirror`

原因：
- 当前远程模式把 conversation semantics 和 transport details 混在一起；
- 不拆开，远程能力扩展和问题定位都会越来越困难。

#### 5. 拆分 `AgentState`
目标：将其拆为：
- `AgentSnapshot`
- `AgentRuntimeState`
- 可选 `AgentHierarchyMetadata`

原因：
- 当前它混合了配置快照、执行态、调度信息、阻塞动作、扩展元数据；
- 对恢复与执行都不够友好。

#### 6. 建立统一能力装配流水线
建议显式定义：
- `discover`
- `resolve`
- `merge`
- `activate`

并定义明确优先级：
- built-in
- project/plugin
- runtime override
- user override

原因：
- 当前扩展能力很多，但装配顺序和优先级心智模型不够统一；
- 微内核要成立，扩展加载过程必须制度化。

### P2：第三阶段，完成微内核化
#### 7. 将 LLM / Workspace / Security 完全插件化
这一步不一定最先做，但它是形成真正微内核架构的重要标志。

目标：
- 内核只关心 capability contracts
- 具体实现通过插件和适配器注入

#### 8. 标准化事件驱动执行引擎
把当前执行链抽象成可替换执行引擎：
- 单 Agent 引擎
- 多 Agent 协作引擎
- 远程代理引擎

#### 9. 输出稳定 Kernel API
当内核边界稳定后，再正式整理稳定对外 API：
- `ConversationKernel`
- `RuntimeBuilder`
- `ExtensionManager`
- `CapabilityRegistry`

## 推荐迁移路径
### Phase A：抽象先行，不改外部行为
目标：先抽接口，不大改使用方式。

行动：
- 新增 Kernel Contracts
- 给现有实现加适配层
- 保持原有 `Conversation(...)` 创建方式不变

这是风险最低的切入点。

### Phase B：内部替换
目标：逐步把大类内部逻辑迁移到协作对象。

行动：
- `LocalConversation` -> facade + bootstrapper + engine
- `RemoteConversation` -> facade + remote adapter + stream client + state mirror
- `ConversationState` -> state + repository

### Phase C：能力插件化
目标：把外围能力从“内嵌逻辑”改为“标准扩展”。

行动：
- Tool、MCP、Security、Hooks、Observability、Memory、Critic 逐步迁移到统一扩展协议
- 保留兼容层，避免一次性破坏旧调用方式

### Phase D：清理历史耦合
目标：等新架构稳定后，清理旧式耦合实现。

行动：
- 移除会话类中的历史装配残留
- 删除重复扩展接入逻辑
- 收敛公共概念模型与对外 API

## 建议新增的核心抽象
为了支撑微内核演进，建议新增以下核心接口：

1. `KernelRuntime`
   - 管理内核生命周期
   - 持有 event bus / registry / state machine

2. `CapabilityProvider`
   - 统一提供 Tool、LLM、MCP、Workspace 等能力

3. `Extension`
   - 支持 discover / activate / deactivate

4. `RuntimeAdapter`
   - 用于区分 local / remote 等运行模式

5. `StateRepository`
   - 管理状态快照与恢复

6. `ExecutionEngine`
   - 封装执行循环

7. `PolicyResolver`
   - 决定安全、调度、恢复、扩展优先级规则

这些接口未必要一步到位完成全部落地，但需要尽快在设计上固定下来，避免后续再次把新能力塞回会话类。

## 风险与兼容性
### 主要风险
1. **抽象过度风险**：如果一开始引入太多接口，反而会让代码更重；
2. **迁移期双轨并存风险**：旧实现与新内核并存一段时间，会增加短期维护成本；
3. **插件边界过宽风险**：如果 capability 定义不清，插件化会沦为另一种耦合；
4. **过早完全插件化风险**：LLM、Workspace 等基础能力若过早彻底插件化，可能增加调试复杂度。

### 控制建议
1. 先做 `P0`，只抽最必要接口；
2. 第一阶段只要求“内核边界更清楚”，不追求“一次完成所有插件化”；
3. 保留兼容门面层，避免破坏现有业务使用方式；
4. 用文档明确 extension priority 和 activation lifecycle，避免新系统再次野生扩张。

## 最终建议
如果目标是“基于微内核架构进行简化”，我建议你们不要把重心放在删功能，而要放在 `重新划定稳定内核与变化能力的边界`。

最值得优先投入的三件事是：

1. **先瘦身 `LocalConversation`**：这是复杂度最高、收益最大的切口；
2. **建立统一扩展协议**：这是微内核真正成立的前提；
3. **剥离状态与持久化逻辑**：这是让内核变稳的基础工程。

在此基础上，再逐步拆 `RemoteConversation`、拆 `AgentState`、统一能力装配流水线，最后把 LLM / Workspace / Security 等外围能力彻底转成标准插件与适配器。

一句话总结：

> 当前 SDK 的最佳简化方向，不是把系统做薄，而是把系统做“有中心、可插拔、边界清晰”。

这正是微内核架构最适合当前项目的原因。
