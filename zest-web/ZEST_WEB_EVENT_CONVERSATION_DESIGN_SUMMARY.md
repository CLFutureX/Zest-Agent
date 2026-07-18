# Zest Web 会话与事件设计总结



## 1. 目标

当前 `zest-web` 的会话与事件设计，主目标是向 Zest V1 前端靠拢：让前端围绕“打开会话、建立 WebSocket、接收事件、按事件渲染 UI”这一主链路工作，而不是继续依赖页面局部的 timeline 手工拼接。现阶段已经完成了从“timeline-only”向“事件驱动 + 派生渲染”的一轮收口。



## 2. 当前总体架构

当前结构可以概括为四层：



1. 会话接入层：由 `useWorkspaceRuntime` 负责打开会话、保存会话记录、触发发送消息。

2. WebSocket 通信层：由 `ConversationWebSocketProvider` 负责建立连接、重连、接收服务端事件、向上分发连接状态。

3. 事件存储层：由 `useEventStore` 维护 `events` 与 `uiEvents` 两套事件数组，其中 `events` 保存原始事件流，`uiEvents` 保存适合界面展示的事件流。

4. 渲染派生层：由 `useTimeline`、`ChatMessageList`、`ZestEventMessage` 及其子组件，将事件流映射成当前聊天区域的展示内容。



这意味着当前页面渲染已经不是直接绑定单一 timeline 数据源，而是以事件为源，以 timeline 和消息组件为派生结果。



## 3. 会话流转

当前会话流转大致如下：



1. 用户在工作区触发 `openConversation`。

2. `useWorkspaceRuntime` 调用 `openConversation` 接口，请求 `zest-app-server` 创建会话。

3. 当前端拿到 `ConversationResponse` 后：

   - 若 `error_message` 不为空，则直接记录错误，不建立 runtime 连接。

   - 若存在 `base_url`，则通过 `ConversationWebSocketProvider` 保存 `conversationRecord`，进一步生成 `ConversationAccessInfo`。

4. `ConversationWebSocketProvider` 监听会话对象变化并调用 `connectConversationSocket` 建立 WebSocket 连接。

5. 连接建立后，用户发送消息时不再走传统 HTTP 聊天接口，而是调用 `websocket.sendMessage(content)`，以会话上下文向 runtime 发送消息。



因此，当前的会话对象已经具备“驱动 WebSocket 生命周期”的角色，前端交互主线已变成：先拿到会话，再围绕会话进行实时通信。



## 4. 事件处理链路

当前事件处理链路是整个设计的核心，整体过程如下：



1. 服务端通过 WebSocket 推送原始 JSON 消息。

2. `ConversationWebSocketProvider` 中的 `handleSocketMessage` 先用 `isV1Event` 进行 V1 事件判断。

3. 通过校验的事件统一进入 `useEventStore.addEvent`。

4. `useEventStore` 同时维护两份数据：

   - `events`：完整原始事件流，用于日志、调试和保留全量上下文。

   - `uiEvents`：经过 `handleEventForUI` 处理后的展示事件流。

5. `handleEventForUI` 参考 Zest V1 的设计：如果收到 observation，并且能找到对应 action，则用 observation 替换该 action 在 `uiEvents` 中的位置；否则直接追加。这使得 UI 层能天然表现 action/observation 的配对折叠关系。

6. 同时，`ConversationWebSocketProvider` 还会根据事件类型触发上层回调，例如错误回调、状态更新回调、普通消息回调。



这说明当前前端已经拥有 Zest V1 风格的“双轨事件模型”：一份保留真实事件历史，一份服务界面展示。



## 5. 渲染层设计

当前渲染层也在朝 Zest V1 的结构收紧，主要分成两段：



### 5.1 Timeline 派生

`useTimeline` 不再主动 append 页面消息，而是从 `useEventStore` 读取 `uiEvents` 和 `events`：



- `uiEvents` 被映射为 `timeline`，用于当前工作区对话展示。

- `events` 被序列化为 `eventLogText`，用于完整事件日志输出。

- `buildTimelineEntryFromRuntimeEvent` 负责把事件转换成 `TimelineItem`。

- `mergePairedTimeline` 负责继续处理 action / observation 的配对合并展示。



换句话说，timeline 已经退化成一种“展示结果”，而不再是事件系统本身。



### 5.2 聊天消息组件分发

聊天区域目前由 `ChatWorkspace` -> `ChatMessageList` -> `ZestEventMessage` -> 子组件 这条链路组成：



- `ChatWorkspace` 负责容器与输入区组合。

- `ChatMessageList` 从 `TimelineItem.rawEvent` 中恢复 `ZestEvent`，并使用：

  - `isV1Event` 过滤非 V1 事件

  - `shouldRenderEvent` 过滤不应显示的事件

  - `hasObservationPair` 判断 action 是否已有 observation 配对

- `ZestEventMessage` 只负责事件分发，不直接承担全部渲染逻辑。

- 当前已经拆出的子组件包括：

  - `UserAssistantEventMessage`

  - `ObservationPairEventMessage`

  - `ErrorEventMessage`

  - `FinishEventMessage`

  - `GenericEventMessageWrapper`



这部分已经形成明显的 Zest V1 风格骨架：顶层路由事件类型，具体事件由子组件承接。



## 6. 关键文件清单

以下文件构成当前设计的主干：



- `src/hooks/useWorkspaceRuntime.ts`

  - 工作区运行时入口，负责打开会话、发送消息、维护错误与运行时元信息。

- `src/contexts/ConversationWebSocketContext.tsx`

  - WebSocket 上下文，负责连接、重连、事件接收、发送消息、连接状态维护。

- `src/stores/useEventStore.ts`

  - 事件 store，维护 `events` 与 `uiEvents` 双数组。

- `src/utils/handleEventForUI.ts`

  - 负责 observation 替换 action 的 UI 折叠逻辑。

- `src/hooks/useTimeline.ts`

  - 从事件 store 派生 timeline 与 eventLogText。

- `src/components/workspace/ZestEventHelpers.ts`

  - 提供 `shouldRenderEvent` 与 `parseMessageFromEvent` 等 Zest 风格辅助函数。

- `src/components/workspace/ChatMessageList.tsx`

  - 事件过滤、配对判断、消息列表遍历。

- `src/components/workspace/ZestEventMessage.tsx`

  - 顶层事件分发器。

- `src/components/workspace/event-message-components.tsx`

  - 具体事件消息子组件集合。



## 7. 当前与 Zest V1 对齐情况

当前对齐进度可以总结为“主链路已基本对齐，细节组件仍在继续收紧”：



### 已对齐的核心点

- 已切换到 WebSocket 驱动的实时消息发送与事件接收。

- 已引入 Zest V1 风格的事件类型守卫与事件中心处理方式。

- 已引入 `events` / `uiEvents` 双数组设计。

- 已实现 observation 替换 action 的 UI 处理逻辑。

- 已把 timeline 降级为派生展示层，而不是源数据层。

- 已将聊天消息渲染改为“事件分发 + 子组件承接”的结构。

- 已接入 `shouldRenderEvent`，开始按 Zest V1 规则控制事件是否显示。



### 仍未完全对齐的部分

- 当前事件子组件仍集中在一个文件中，尚未像 Zest V1 那样拆成独立目录与独立文件。

- `GenericEventMessageWrapper`、`FinishEventMessage` 等实现仍是当前项目语义下的轻量版本，还不是一比一复刻 Zest V1。

- 当前聊天区域样式和事件内容细节仍偏 Zest 自身风格，尚未完全复刻 Zest V1 的内容层次与交互细节。

- 还有部分 V1 细分能力未继续展开，例如更细粒度的事件内容 helper、更多专门事件组件、确认类交互等。



总体上，当前 `zest-web` 已经从旧的 timeline 主导模式，转到了更接近 Zest V1 的“会话对象驱动 + WebSocket 实时事件 + 双轨事件存储 + 事件分发渲染”设计；后续工作重点主要是继续细化组件拆分和事件展示细节，而不是再回到旧架构。
