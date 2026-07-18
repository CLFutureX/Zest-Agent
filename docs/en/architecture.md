# Architecture

> This document complements the [Project Overview](overview.md) by going deeper into Zest-Agent's internal mechanisms, component interactions, protocols, and design tradeoffs.
> Prerequisite: read [overview.md](overview.md) first for the four-layer architecture and module boundaries.

---

## 1. Design Principles

Zest-Agent is a **distributed intelligent-agent application platform designed and implemented from the ground up**. In terms of engineering, it only reuses a small number of OpenHands components as building blocks. The core Agent runtime, scheduling model, breakpoint recovery, data storage abstraction, sandbox isolation mechanism, event model, and state machine are all newly designed and implemented by the Zest-Agent team.

1. **Self-developed core, component reuse as supplement** — the core runtime (AgentRunner, scheduling, persistence, isolation, event stream) is 100% self-developed; only a few OpenHands tool implementations and data-model fragments are reused as building blocks, to ease community migration and ecosystem integration.
2. **Control plane / Execution plane separation** — decouple scheduling from execution, enabling horizontal scaling and single-point failure isolation.
3. **Shared abstractions first** — event, state, memory, and query capabilities sink into `zest-common` to avoid duplication across business layers.
4. **Observability first** — every key decision and state change produces an event; events are subscribable, persistable, and replayable.
5. **Replaceable backends** — storage backends (MySQL / Mongo / ES / local) swap through an abstraction layer; business code is unaware.
6. **Gradual evolution** — multi-Agent, scheduling strategies, and load balancing reserve interfaces and are polished progressively based on community feedback.

---

## 2. Relationship to OpenHands (Clear Boundary)

Zest-Agent is **not** a "wrapper" or "modified version" of OpenHands. It is an independent distributed Agent application platform. OpenHands plays the role of one of several **basic-component providers** in this project.

### 2.1 Fully Self-Developed Parts

| Module | Description |
|---|---|
| **AgentRunner scheduling layer** | Self-designed Agent scheduling skeleton that manages Agent lifecycle, state transitions, and event dispatch; supports multi-Agent collaboration within a single conversation |
| **Agent startup and scheduling model** | Control plane / execution plane separation, Redis-based service discovery, session-affinity load balancing, task dispatch |
| **Breakpoint recovery mechanism** | Three-layer persistence (state + events + messages) + checkpoints + startup-time scan and resume |
| **Data storage abstraction** | Unified StateStore / EventStore / MemoryStore interfaces, pluggable multi-backend, factory instantiation, query facade aggregation |
| **Sandbox isolation mechanism** | Fully designed and implemented tool sandbox: Libtmux session terminals + Docker sandbox + file/network/process three-layer isolation + sandbox lifecycle bound to the conversation |
| **Event model and state machine** | self-developed eventCenter pub-sub hub (events + uiEvents dual topics), event folder, conversation state machine (created/running/paused/error/finished) |
| **Multi-layer memory system** | Basic memory + experience memory layering, ES semantic retrieval, unified query facade |
| **WebSocket real-time channel** | Self-developed bidirectional event stream protocol, connection management, message dispatch |

### 2.2 Parts Reused from OpenHands

- **Some tool implementations**: as basic tool building blocks (e.g., parts of bash parsing and the file editor)
- **Some data-model fragments**: message format, tool-call schema, etc.

> Reused parts retain their original MIT copyright and permission notice in [NOTICE.md](../NOTICE.md) as required by MIT. Zest-Agent as a whole is licensed under Apache License 2.0.

### 2.3 Comparison with OpenHands

| Dimension | OpenHands | Zest-Agent |
|---|---|---|
| Runtime model | single-process single-Agent | self-developed AgentRunner, supports in-session multi-Agent collaboration |
| Scheduling model | local direct call | self-developed control/execution split + Redis registry + load balancing |
| Persistence | mostly files | self-developed three-layer persistence + pluggable backends |
| Breakpoint recovery | none | self-developed checkpoint + startup scan and resume |
| Sandbox isolation | simple container isolation | self-developed three-layer isolation (file/network/process) + sandbox lifecycle management |
| Memory system | single store | self-developed basic + experience layering + ES retrieval |
| Event model | single track | self-developed eventCenter pub-sub (events + uiEvents dual topics) |
| Frontend | OpenHands V1 | aligned with V1 style + eventCenter topic adaptation |
| Target | personal Agent experience | team / enterprise Agent platform |

---

## 3. Component Interaction

### 3.1 Static Dependencies

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

### 3.2 Sequence of One Full Conversation

```
Browser       zest-web    app-server    service      Redis       Storage
  │              │            │            │           │            │
  │─create conv──▶│            │            │           │            │
  │              │─POST /conv▶│            │           │            │
  │              │            │─pick node──▶│           │            │
  │              │            │  (registry)│           │            │
  │              │            │◀─node list─│           │            │
  │              │            │─dispatch (HTTP)───────▶│            │
  │              │            │            │─heartbeat─▶│            │
  │              │            │            │           │            │
  │              │◀─conv ID──│            │           │            │
  │◀─conv ID──────│            │            │           │            │
  │              │            │            │           │            │
  │─WebSocket connect──────────────────────────▶│            │            │
  │              │            │            │           │            │
  │─send msg (WS)──────────────────────────▶│           │            │
  │              │            │            │─AgentRunner loop          │
  │              │            │            │  Main / Sub Agent collaborate│
  │              │            │            │  LLM + tools (inside sandbox)│
  │              │            │            │─write event/state/memory───▶│
  │              │            │            │─checkpoint snapshot─────────▶│
  │◀─event stream (WS)────────────────────────│            │            │
  │              │            │            │           │            │
  │              │            │            │─renew HB──▶│            │
```

---

## 4. Event Model (Self-Developed Pub-Sub eventCenter)

Zest-Agent's self-developed **eventCenter** is the core event-dispatch hub. It uses a publish-subscribe (pub-sub) model to uniformly manage the production, flow, and consumption of all runtime events. All runtime components (AgentRunner, Agent, tool calls, LLM calls, state machine, sandbox manager, memory subsystem, etc.) are producers of eventCenter; persistence subscribers, WebSocket-push subscribers, observability subscribers, and frontend-UI subscribers are subscribers of eventCenter.

### 4.1 eventCenter and Dual-Topic Design

eventCenter exposes two core topics, each serving different consumers:

| Topic | Content | Persisted | Main Subscribers |
|---|---|---|---|
| `events` | **full raw events** for replay, audit, debugging | yes | event log (persisted) + observability + WebSocket (on demand) |
| `uiEvents` | **folded UI-friendly event stream** for frontend rendering | no (on demand) | WebSocket → frontend render |

`uiEvents` is a folded view of `events`, produced by eventCenter's internal event folder from the raw stream according to folding rules. The two topics are delivered independently; subscribers subscribe on demand.

### 4.2 Why Pub-Sub + Dual-Topic

**Why publish-subscribe**:
- **Multi-subscriber decoupling**: a single event can be consumed by multiple subscribers (persistence, push, observability, UI rendering); producers are unaware of consumers.
- **Extensible**: new topics (e.g., `metricsStream`, `auditStream`) can be added later without affecting producers.
- **Backpressure control**: subscribers consume at their own rate; slow consumers don't block fast ones.
- **Replayable**: subscribers can replay the event stream from any offset (relies on `events` topic persistence).

**Why dual-topic**:
- `events` must be complete, rigorous, and replayable, so it contains heavy internal details (state machine changes, error stacks, debug info, sub-Agent dispatch, checkpoint writes).
- If the frontend subscribed to `events` directly, it would be overloaded and laggy — a single conversation may produce thousands of internal events.
- `uiEvents` is the folded view: folds "AgentThinking → ToolCallStarted → ToolCallFinished" into a single tool card; folds 100 internal state changes into 1 "running" indicator.
- The frontend only subscribes to `uiEvents`; ops debugging and replay go through `events`.

### 4.3 eventCenter Architecture and Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│  Producers                                                   │
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
              │  eventCenter (self-dev) │
              │  ┌──────────────────┐  │
              │  │ event router      │  │
              │  ├──────────────────┤  │
              │  │ event folder      │  │
              │  │ (events→uiEvents)│  │
              │  ├──────────────────┤  │
              │  │ topic manager     │  │
              │  └──────────────────┘  │
              └─────┬──────────────┬───┘
                    │              │
            subscribe(events)  subscribe(uiEvents)
                    │              │
                    ▼              ▼
   ┌────────────────────┐   ┌────────────────────┐
   │ Sub A: persistence │   │ Sub B: WebSocket   │
   │ write to event log │   │ push to frontend  │
   └────────────────────┘   └────────────────────┘
   ┌────────────────────┐   ┌────────────────────┐
   │ Sub C: observability│   │ Sub D: audit       │
   │ Langfuse / metrics  │   │ security audit log│
   └────────────────────┘   └────────────────────┘
```

### 4.4 Event Types (partial)

| Event | When | Key fields |
|---|---|---|
| `ConversationStarted` | conversation begins | `conversation_id`, `user_id` |
| `MessageReceived` | user message arrives | `conversation_id`, `content` |
| `AgentThinking` | agent is thinking | `thought`, `step_id` |
| `ToolCallStarted` | tool call starts | `tool_name`, `args` |
| `ToolCallFinished` | tool call ends | `result`, `duration_ms` |
| `SubAgentDispatched` | Main Agent dispatches a Sub Agent | `parent_step_id`, `sub_agent_id` |
| `SubAgentReturned` | Sub Agent returns | `sub_agent_id`, `result` |
| `LLMCallStarted` | LLM call starts | `model`, `messages_count` |
| `LLMCallFinished` | LLM call ends | `tokens`, `latency_ms` |
| `StateChanged` | state machine transition | `from`, `to` |
| `CheckpointWritten` | checkpoint written | `step_id`, `snapshot_id` |
| `MemoryWritten` | memory write | `category`, `key` |
| `MemoryRetrieved` | memory retrieve | `query`, `hits` |
| `ErrorOccurred` | error | `type`, `message`, `traceback` |
| `ConversationFinished` | conversation ends | `conversation_id`, `reason` |

### 4.5 WebSocket Protocol

**Connect**: `ws(s)://<host>:8001/sockets?conversation_id=<id>`

**Message directions**:
- client → server: `send_message`, `pause`, `resume`, `terminate`
- server → client: event stream (above event types)

**Message format** (JSON):
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

## 5. Agent Runtime (Self-Developed AgentRunner)

### 5.1 Motivation for AgentRunner

The traditional single-process single-Agent model struggles in scenarios like:
- A single conversation requires multiple Agent roles (planning Agent + execution Agent + review Agent)
- Sub-tasks need parallel or async execution
- Agent failure should trigger a role switch, not whole-conversation failure

Zest-Agent designed **AgentRunner** from scratch as the scheduling skeleton, decoupling "who executes this step" from "how the conversation flows". The Runner layer is the unified entry point: it manages multiple Agent instances below, and presents a unified interface to the conversation above.

### 5.2 Core Abstractions

```
┌──────────────────────────────────────────────────────┐
│  AgentRunner (self-developed scheduling skeleton)    │
│   ├─ Conversation-level routing: pick Agent by step  │
│   ├─ Main Agent: session primary, decomposes + integrates│
│   ├─ Sub Agent pool: sub-Agents by tool or role       │
│   ├─ Lifecycle management: Agent create / reuse / release│
│   ├─ Event dispatch: all Agent output flows through Runner│
│   └─ State sharing: via Conversation context          │
└──────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│  Conversation (session context)                     │
│   ├─ LLM (litellm abstraction)                       │
│   ├─ Tools (from zest-tools, executed in sandbox)    │
│   ├─ Skills (from zest-sdk/context/skills)           │
│   └─ Memory (from zest-common, basic + experience)   │
└──────────────────────────────────────────────────────┘
```

### 5.3 Multi-Agent Interaction Within One Conversation

Through the Runner layer, **a single conversation** can host multiple Agent roles:

```
user message → Main Agent decomposes the task
   ├─ Sub Agent A (search) → returns results
   ├─ Sub Agent B (code)   → returns code
   └─ Sub Agent C (review) → returns review
       ↓
   Main Agent integrates → final reply
```

**Why this is elegant**:
- Main and Sub share the same Conversation context — no serialization needed
- Sub Agent output flows naturally as part of the event stream — observable on the frontend
- Sub Agent failure does not block the Main Agent
- Future evolution: DSL-based task orchestration

### 5.4 Agent Loop (ReAct style, self-developed)

```
1. Receive user message or restored context
2. AgentRunner selects the Agent that should execute now
3. Selected Agent runs its loop:
   a. Thinking: LLM decides the next action
   b. Action: call a tool / LLM / write memory
   c. Observation: feed result back to LLM
   d. Decide whether to end (done / error / need to switch Agent)
4. AgentRunner receives Agent output, decides:
   - continue with the current Agent
   - switch to another Agent
   - dispatch a Sub Agent
   - terminate the conversation
5. Produce event stream throughout, write to event log, periodically checkpoint
```

### 5.5 Conversation State Machine

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

State changes trigger `StateChanged` events and are persisted to the state store — the foundation of breakpoint recovery.

---

## 6. Self-Developed Session Scheduling and Lifecycle

### 6.1 Control-Plane Dispatch

When `zest-app-server` receives a conversation creation request:
1. Create the application-side conversation record
2. Query the Redis registry to find available execution nodes
3. Pick a target node using the load-balancing strategy (default `session_affinity`)
4. Dispatch the task to the node via HTTP
5. Return the conversation ID to the frontend

### 6.2 Service Registry Protocol

`zest-service` writes a registry entry to Redis at startup:

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

Renewed every 10 seconds; considered offline after 3 missed renewals (30s).

### 6.3 Load-Balancing Strategies

| Strategy | Behavior | Current |
|---|---|:---:|
| `session_affinity` | pin a conversation to the first-hit node | :white_check_mark: |
| `least_connection` | pick the node with the fewest active sessions | :construction: planned |
| `tag_routing` | route by node tags (e.g., GPU nodes) | :construction: planned |
| `affinity` / `anti_affinity` | per-conversation or per-user affinity rules | :construction: planned |

---

## 7. Self-Developed Breakpoint Recovery Mechanism

Zest-Agent's breakpoint recovery is one of the core self-developed capabilities, ensuring long tasks survive service restarts and node loss.

### 7.1 Three-Layer Persistence

| Layer | Content | Use |
|---|---|---|
| State storage | current state machine state, runtime params | fast resume to the latest state |
| Event log | full event stream (time-ordered) | replay, audit, debug |
| Message history | user-Agent message sequence | LLM context reconstruction |

### 7.2 Checkpoint Mechanism

- AgentRunner auto-writes a checkpoint every N steps (event `CheckpointWritten`)
- A checkpoint contains: conversation state snapshot + current step ID + key runtime params
- Write strategy is configurable (every step / every 5 steps / every 30s)

### 7.3 Recovery Procedure

```
zest-service starts
   │
   ▼
scan unfinished conversations (state == running / paused)
   │
   ▼
for each unfinished conversation:
   1. read the latest checkpoint
   2. replay events after the checkpoint (rebuild Agent context)
   3. re-register to Redis
   4. wait for the frontend WebSocket to reconnect
   5. continue the Agent loop from the breakpoint
```

**Transparency**: users don't notice. After the frontend reconnects, it keeps receiving the event stream, including the replayed part.

### 7.4 Conversation Migration on Node Loss

- When the control plane detects a node offline (heartbeat timeout), it marks the conversations on that node as "pending recovery"
- The orphaned conversations are routed to other healthy nodes
- The new node reads the conversation's checkpoint and event log from storage, rebuilds context
- File-type tool outputs local to the lost node are gone (sandbox local storage), but state and memory are preserved

---

## 8. Self-Developed Data Storage Abstraction

### 8.1 Backend Matrix

| Use | MySQL | Mongo | ES (8.8.2) | Local files |
|---|:---:|:---:|:---:|:---:|
| State storage | :white_check_mark: | :white_check_mark: | :x: | :white_check_mark: |
| Event log | :white_check_mark: | :white_check_mark: | :x: | :white_check_mark: |
| Basic memory | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Experience memory | :x: | :white_check_mark: | :white_check_mark: | :x: |

> Default: MySQL (state + events + basic memory), ES optional (experience memory retrieval).

### 8.2 Abstraction Layer

```
common/storage/
├── state/         ─ state storage abstraction + impls
├── event/         ─ event log abstraction + impls
├── memory/
│   ├── basic/     ─ basic memory abstraction + impls
│   ├── experience/─ experience memory abstraction + impls
│   └── embedding/ ─ vector embedding abstraction
└── factory.py     ─ backend factory, instantiated by config
```

### 8.3 Factory Instantiation

Business code only sees `StateStore` / `EventStore` / `MemoryStore` interfaces. The backend is instantiated at startup by a factory based on config (`.env` `STORAGE_MODE` / `MEMORY_BACKEND`, etc.). Switching backends requires no business-code change.

### 8.4 Query Facade

`zest-common/common/query/conversation_read_facade.py` aggregates:

```
conversation_read_facade.get(conversation_id) -> {
  "state": ...,
  "events": [...],
  "basic_memory": {...},
  "experience_memory": [...]
}
```

Business code, frontend, ops, and downstream analysis all read through this facade, avoiding direct coupling to underlying storage.

---

## 9. Self-Developed Sandbox Isolation Mechanism (Fully Designed and Implemented)

Zest-Agent **fully designed and implemented** its own sandbox isolation mechanism, used when the Agent executes tools (especially high-privilege tools like bash, file operations, and browser) to provide a security boundary.

### 9.1 Three-Layer Isolation

| Layer | Mechanism | Protection |
|---|---|---|
| **Filesystem isolation** | sandbox-private mount + read-only critical dirs + working dir isolation | prevent unauthorized host-file access |
| **Network isolation** | Docker network namespace + optional egress allowlist | prevent unauthorized intranet access |
| **Process isolation** | independent PID namespace + resource limits (CPU / memory) | prevent malicious process escape and resource exhaustion |

### 9.2 Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Conversation                                           │
│   └─ AgentRunner                                         │
│        └─ Tool Call (e.g., bash, file_editor, browser)   │
│             │                                            │
│             ▼                                            │
│  Sandbox Manager (zest-tools/tools/sandbox/, self-dev)   │
│   ├─ Libtmux session terminal: bash runs in a tmux session│
│   ├─ Docker container: one container per conversation    │
│   ├─ Resource limits: cgroup-backed CPU/memory limits    │
│   └─ Lifecycle: sandbox created with conversation,        │
│       auto-cleaned when conversation ends                  │
└─────────────────────────────────────────────────────────┘
```

### 9.3 Libtmux Session Terminal

- Each Agent conversation is bound to an independent tmux session
- bash tool calls execute inside the tmux session, avoiding shell-state pollution
- Supports detach / reattach for long-running commands
- Command output is streamed back via the event stream

### 9.4 Docker Sandbox

- Sandbox image: `zest-agent-server/zest-service/server/docker/Dockerfile`
- One independent container per conversation, with filesystem isolation
- Optional VSCode Server / VNC mounts for remote-development scenarios
- Tool calls inside the sandbox stream results back over WebSocket

### 9.5 Sandbox Lifecycle

```
conversation created
   │
   ▼
sandbox manager starts container + tmux session
   │
   ▼
Agent runs tools → executed inside sandbox → results streamed back
   │
   ▼
conversation ends / timeout / disconnect
   │
   ▼
sandbox manager cleans up container + tmux session
```

### 9.6 Security Policy

- Default deny: any operation not explicitly allowed is denied
- Egress allowlist: by default only LLM API domains are reachable
- File-path validation: tool calls validate paths inside the sandbox working dir before execution
- Resource caps: per-conversation CPU / memory / execution time are configurable
- Audit log: all sandbox operations are written to the event log

---

## 10. Memory Subsystem

### 10.1 Basic Memory

- **What**: user profile, preferences, recent context summaries.
- **Traits**: small volume, high hit rate, read/write by category.
- **Backend**: MySQL / Mongo / local files — dev-friendly.

### 10.2 Experience Memory

- **What**: problem-solution-execution-trajectory-feedback.
- **Traits**: large volume, requires semantic retrieval, evolvable.
- **Backend**: ES (semantic retrieval) or Mongo (with vector index).
- **Write timing**: at conversation end, AgentRunner decides whether to sediment experience.
- **Recall**: semantic similarity retrieval Top-K experiences, injected into LLM context.

### 10.3 Benefits of Layered Memory

| Dimension | Single dump | Zest-Agent layered |
|---|---|---|
| Hit efficiency | full scan | category direct hit (basic) + indexed recall (experience) |
| Explainability | hard to distinguish | clear basic / experience responsibilities |
| Evolvability | hard | experience can be independently optimized, migrated, versioned |
| Cost | all semantic retrieval | high-freq basic, low-freq experience, controllable cost |

---

## 11. Observability

### 11.1 Three Layers of Observation

| Layer | Mechanism | Use |
|---|---|---|
| Process | `faulthandler` + `atexit` | crash stack and normal exit logs |
| Application | structured JSON logs (`zest-common/common/logger/`) | runtime debugging |
| Business | event stream + Langfuse | session replay and LLM tracing |

### 11.2 Log Structure

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

### 11.3 Health Endpoints

- `zest-app-server`: `GET /health` → process alive + Redis reachable + storage reachable
- `zest-service`: `GET /health` → process alive + Redis reachable

Useful for K8s / LB probes.

---

## 12. Failure and Recovery

### 12.1 Failure Modes

| Failure | Impact | Recovery |
|---|---|---|
| `zest-app-server` down | new sessions fail, existing WebSocket disconnect | stateless recovery on restart |
| `zest-service` down | that node's sessions break | control plane evicts the node; new sessions route elsewhere; persisted sessions resume from checkpoint (see Section 7) |
| Redis down | registry unavailable, existing connections don't immediately break | nodes re-register after Redis recovers |
| MySQL down | state writes fail | retry + degrade to read-only |
| LLM call fails | current step fails | retry / switch backup model / emit error event |
| Sandbox OOM | current tool call fails | sandbox manager restarts the container; conversation resumes from the latest checkpoint |

### 12.2 Recovery Capability Comparison

| Scenario | Without breakpoint recovery | Zest-Agent self-developed breakpoint recovery |
|---|---|---|
| Service restart | full conversation loss | resume from latest checkpoint; frontend reconnects without noticing |
| Node offline | full loss of conversations on that node | conversations migrate to another node, resume from checkpoint |
| Sandbox crash | tool call interrupted, conversation stuck | sandbox restarts, resume from breakpoint |
| Long task interrupted | full progress loss | progress persisted, continues after restart |

---

## 13. Security Model

### 13.1 Auth Layers

| Interface | Auth | Config |
|---|---|---|
| Frontend → app-server | application-layer auth (auth_route) | `AUTH_*` env vars |
| app-server → service | Session API Key | `ZEST_SESSION_API_KEYS` |
| Frontend → service (WebSocket) | Session API Key (passed through) | same as above |

### 13.2 Encryption

- `ZEST_SECRET_KEY` encrypts sensitive fields (e.g., privacy data in memory).
- `common/security/` provides encryption utilities.
- `pydantic_secrets.py` implements secret redaction to prevent log leakage.

### 13.3 Sandbox (see Section 9)

Zest-Agent's security model centers on the sandbox rather than just application-layer auth. All high-privilege tool calls are forced to execute inside the sandbox.

---

## 14. Extension Points

| Extension | Entry | Notes |
|---|---|---|
| New tool | `zest-agent-server/zest-tools/tools/` | implement Tool interface, register in preset or custom |
| New skill | `zest-agent-server/zest-sdk/sdk/context/skills/` | implement Skill interface |
| New LLM vendor | litellm already supports | change `.env` `LLM_BASE_URL` and `LLM_MODEL` |
| New storage backend | `zest-common/common/storage/<type>/` | implement StateStore / EventStore / MemoryStore |
| New scheduling strategy | `zest-app-server/app/core/services/` scheduler | implement Selector interface |
| New Agent role | `zest-sdk/sdk/agent/` | implement Agent interface, mount to AgentRunner |
| Custom sandbox policy | `zest-tools/tools/sandbox/config/` | modify resource limits, network allowlist, file-path validation rules |

---

## 15. To Be Continued

- Detailed sequence and orchestration DSL for multi-Agent collaboration
- Concrete implementations of scheduling strategies
- Semantic retrieval and recall algorithms for experience memory
- Deep validation of sandbox quotas and multi-tenant isolation
- Performance baselines and load-test results

Tell us what you most care about in GitHub Discussions; we will prioritize it.
