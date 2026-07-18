# Zest-Agent Project Overview

> Zest-Agent is a **distributed AI Agent application platform** re-architected on top of [OpenHands](https://github.com/All-Hands-AI/OpenHands).
> The goal is not to build yet another single-box Agent, but to decompose the Agent runtime, memory system, and scheduling capabilities into an extensible, schedulable, evolvable engineering platform.
> This doc targets developers and architects who want a quick but thorough understanding of the project's scope, module boundaries, and design philosophy.

---

## 1. Project Overview

### 1.1 One-liner

**Zest-Agent = a control-plane / execution-plane separated distributed Agent platform, with multi-layer memory, real-time event streams, and multi-Agent evolution.**

### 1.2 Origin and Background

Zest-Agent is a **distributed intelligent-agent application platform designed and implemented from the ground up**. Only a small number of OpenHands components are reused as building blocks; the core runtime (AgentRunner scheduling layer, Agent startup and scheduling model, breakpoint recovery, data storage abstraction, sandbox isolation mechanism, event model, and state machine) is fully self-developed.

- **Self-developed**: AgentRunner scheduling skeleton (elegantly supporting multi-Agent collaboration within a single conversation), control-plane/execution-plane scheduling model, three-layer persistence + checkpoint-based breakpoint recovery, unified pluggable storage abstraction and query facade, fully designed and implemented sandbox isolation (file/network/process three-layer isolation), self-developed eventCenter pub-sub event model, multi-layer memory system.
- **Reused**: only a few OpenHands tool implementations and data-model fragments as building blocks.
- **Compliance**: OpenHands' original MIT notice is retained in `NOTICE.md` as required by MIT. Zest-Agent as a whole is licensed under Apache License 2.0.

### 1.3 Core Value Proposition

| Dimension | Typical single-box Agent | Zest-Agent |
|---|---|---|
| Architecture | single process, single repo | frontend / control / execution / shared four-layer separation |
| Scaling | vertical | horizontal (execution plane multi-replica) |
| Memory | single dump | basic + experience layers, ES retrieval |
| Interaction | HTTP polling / one-way stream | WebSocket bidirectional event stream, observable & replayable |
| Multi-Agent | not supported | scheduling-layer abstraction, in-session Main-Sub Agent |
| Engineering | hobby-Demo friendly | task scheduling, health check, breakpoint recovery, observability |

### 1.4 Use Cases

- Enterprise-grade Agent application platform: multiple business units share one execution pool, isolated by conversation.
- Multi-Agent collaboration: a main Agent decomposes complex tasks, sub-Agents execute by role.
- Long-term-memory assistant: accumulates user profile and "problem-solution-execution-trajectory" experience across sessions.
- Observable Agent: requires seeing every thought, tool call, and state change.
- Secondary development and teaching: a reference implementation of an engineering-grade Agent platform.

### 1.5 Tech Stack

| Layer | Stack |
|---|---|
| Frontend | React 18 + Vite 5 + TypeScript + Zustand + react-markdown |
| Control / Execution plane | Python 3.12 + FastAPI + Uvicorn + WebSocket (wsproto) |
| SDK | Python + Litellm + Pydantic + Langfuse + FastMCP |
| Tools | Python + Libtmux + Bashlex + browser-use |
| Shared | Python + Pydantic + cachetools + filelock |
| Storage | MySQL (default) / local files / MongoDB (optional) / Elasticsearch (optional) |
| Registry & heartbeat | Redis |
| Tooling | uv workspace + pnpm + pre-commit + ruff + pytest |

---

## 2. Overall Architecture

### 2.1 Four-Layer Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Interaction  zest-web  (React + Vite, WebSocket event stream)│
│  ─ conversation view, event rendering, state visualization     │
└──────────────┬───────────────────────────────────────────────┘
               │ HTTP (session CRUD) + WebSocket (event stream)
┌──────────────┴───────────────────────────────────────────────┐
│  Control  zest-app-server  (FastAPI, port 9000)                │
│  ─ session entry, task scheduling, AgentServer registry, LB    │
└──────────────┬───────────────────────────────────────────────┘
               │ internal HTTP / WebSocket + Redis registry
┌──────────────┴───────────────────────────────────────────────┐
│  Execution  zest-agent-server/zest-service  (FastAPI, port 8001)│
│  ─ real Agent conversation lifecycle, WebSocket event subscribe│
│  ─ tool sandbox, skills, breakpoint recovery                   │
└──────────────┬───────────────────────────────────────────────┘
               │ shared SDK / tools / abstractions
┌──────────────┴───────────────────────────────────────────────┐
│  Shared capabilities                                            │
│  zest-sdk      ─ Agent build core, LLM, memory, skills, events │
│  zest-tools    ─ runtime tools (bash / file_editor / browser)   │
│  zest-common   ─ event log, state, memory, query facade, obs.   │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow (one full conversation)

1. User creates a conversation in `zest-web` → HTTP POST to `zest-app-server`.
2. `zest-app-server` creates the application-side conversation record, selects a `zest-service` execution node via the scheduler, and writes task info into the Redis registry.
3. The selected `zest-service` spins up the Agent runtime, subscribes to conversation messages, and starts the LLM + tool loop.
4. During execution, thoughts, tool calls, and state changes are pushed to `zest-web` via WebSocket in real time; the frontend subscribes to eventCenter's `uiEvents` topic for rendering, while ops and replay consume the `events` topic.
5. State, events, basic memory, and experience memory are persisted through the shared storage abstractions in `zest-common`; reads go through `conversation_read_facade`.
6. Users can send new messages, pause, or terminate via WebSocket at any time. Conversation state is persisted and supports breakpoint recovery.

### 2.3 Relation to OpenHands

Zest-Agent is **not** a wrapper or modified version of OpenHands. It is an independent, self-developed distributed Agent application platform. OpenHands plays the role of one of several **basic-component providers** in this project.

**Fully self-developed**: AgentRunner scheduling layer, Agent startup and scheduling model, breakpoint recovery, data storage abstraction, sandbox isolation mechanism, event model and state machine, multi-layer memory system, WebSocket real-time channel.

**Reused from OpenHands**: only some tool implementations and data-model fragments.

| Dimension | OpenHands | Zest-Agent |
|---|---|---|
| Repo shape | monorepo | uv workspace, multi-package, separated front/back |
| Runtime model | single-process single-Agent | self-developed AgentRunner, supports in-session multi-Agent collaboration |
| Scheduling model | local direct call | self-developed control/execution split + Redis registry + load balancing |
| Persistence | mostly files | self-developed three-layer persistence + pluggable backends |
| Breakpoint recovery | none | self-developed checkpoint + startup scan and resume |
| Sandbox isolation | simple container isolation | self-developed three-layer isolation + sandbox lifecycle management |
| Memory | single store | self-developed basic + experience layering + ES retrieval |
| Event model | single track | self-developed eventCenter pub-sub (events + uiEvents dual topics) |
| Frontend | OpenHands V1 | aligned with V1 style + eventCenter topic adaptation |
| Registry | none | Redis heartbeat + health check |
| Target | personal Agent experience | team / enterprise Agent platform |

Compliance: Zest-Agent is licensed under Apache License 2.0. Portions derived from OpenHands (MIT License) retain the original MIT copyright and permission notice in `NOTICE.md` as required by the MIT license. MIT permits derivative works to be relicensed under Apache 2.0.

---

## 3. Core Feature Design

### 3.1 Control Plane / Execution Plane Separation

The most important design decision. Splits "who schedules" from "who executes":

- **Control plane `zest-app-server`**: unified session entry, auth, session CRUD, task routing, node selection, load balancing. It does NOT run the Agent itself.
- **Execution plane `zest-service`**: the actual Agent runtime process. Registers itself to Redis and executes sessions assigned by the control plane.

**Benefits**:
- Execution plane scales horizontally; control plane is stateless.
- Single-point failure isolation: an execution node going down does not block new sessions.
- Naturally supports multi-tenant shared execution pools.

### 3.2 Distributed Agent Scheduling

- **Service registry**: execution nodes register to Redis under `agent_registry`, including `host:port`, `server_id`, `tags`, health, load.
- **Heartbeat**: default 10s interval, 30s TTL; considered offline if not renewed for 3 intervals.
- **Load balancing**: default `session_affinity` (sticky session to the first-hit node). Extensible to least-connection, tag routing, affinity/anti-affinity.
- **Node discovery**: control plane subscribes to registry changes and syncs the available-node view.

### 3.3 Multi-Layer Memory

Splits "memory" from "one store" into "two purpose-defined layers":

- **Basic Memory**: long-term user info — profile, preferences, recent context. Small volume, high hit rate.
- **Experience Memory**: "problem-solution-execution-trajectory-feedback" accumulation. Supports ES-based semantic retrieval. Large volume, evolvable.

**Unified storage abstraction**: `zest-common` consolidates storage config and factory. Business code only sees `MemoryStore` / `EventStore` / `StateStore` interfaces.

**Query facade aggregation**: `conversation_read_facade` aggregates "state + events + basic memory + experience memory" into a unified runtime view, consumed by the frontend, ops, and downstream analysis.

### 3.4 Real-Time Event-Driven

The frontend no longer polls HTTP. Instead, a WebSocket-based chain: "open conversation → connect → receive events → send messages → render".

- **Self-developed eventCenter pub-sub model**: all runtime components publish events to eventCenter as producers; subscribers subscribe to either the `events` topic (full raw events for replay and debugging) or the `uiEvents` topic (folded UI-friendly stream). Producers and consumers are decoupled; multiple subscribers consume in parallel; the frontend subscribes only to `uiEvents` to avoid rendering pressure.
- **Observable**: Agent thoughts, tool calls, state changes, errors all surface as events, with event log + state snapshots for visualization.
- **Replayable**: conversation event stream is persisted and can be replayed by timeline.

### 3.5 Multi-Agent Evolution (Self-Developed AgentRunner)

Through the self-developed **AgentRunner scheduling layer**, "who executes this step" is decoupled from "how the conversation flows". The Runner layer is the unified entry point: it manages multiple Agent instances below, and presents a unified interface to the conversation above, **elegantly supporting multi-Agent interaction within a single conversation**:

- **Main Agent**: the session primary Agent; decomposes tasks, dispatches sub-tasks, integrates results.
- **Sub Agent**: sub-Agents by tool capability or role, invoked by Main Agent.
- **Shared context**: Main and Sub share the same Conversation context — no serialization needed.
- **Failure isolation**: Sub Agent failure does not block the Main Agent.
- **Observable**: all Agent output flows through Runner into the event stream.
- **Capability reuse**: Sub-Agents share tools and memory.

Multi-Agent capability is still being polished, but the skeleton is in place for complex task decomposition, role division, and Agent collaboration.

### 3.6 Session Persistence and Breakpoint Recovery (Self-Developed)

Zest-Agent's self-developed breakpoint recovery ensures long tasks survive restarts:

- **Three-layer persistence**: state storage + event log + message history — for fast resume, replay/audit, and LLM context reconstruction respectively.
- **Checkpoint mechanism**: AgentRunner auto-writes a checkpoint every N steps (event `CheckpointWritten`); strategy is configurable.
- **Startup scan and resume**: on restart, scan unfinished conversations, replay events after the latest checkpoint to rebuild context — frontend reconnects without noticing.
- **Node-loss migration**: when a node goes offline, conversations are routed to other healthy nodes, which read the checkpoint and event log from storage to rebuild context.
- **Sandbox-crash recovery**: when a sandbox container OOMs, the sandbox manager restarts it; the conversation resumes from the latest checkpoint.

File-type tool outputs local to the sandbox may be lost (sandbox-local storage), but state and memory are preserved.

### 3.7 Service Registry and Health Check

- Execution nodes self-register to Redis with `server_id`, `host:port`, `tags`, `heartbeat_at`.
- The control plane periodically scans the registry and evicts unresponsive nodes from routing.
- Recovered nodes re-register and re-join scheduling automatically.

### 3.8 Load Balancing Strategies

Default `session_affinity` keeps WebSocket long connections stable. Interface reserved for future strategies:

- `least_connection`: route to the node with the fewest active sessions.
- `tag_routing`: route by node tags (e.g., GPU nodes for heavy LLM tasks).
- `affinity` / `anti_affinity`: per-conversation or per-user affinity rules.

### 3.9 Observability

- **Structured logs**: all modules route through `zest-common`'s logger; JSON output for aggregation.
- **Langfuse integration**: zest-sdk integrates Langfuse for LLM call chain, token usage, latency.
- **Event log + state snapshot**: per-conversation replay and audit.
- **Health endpoints**: both `zest-app-server` and `zest-service` expose `/health` for orchestrators.

### 3.10 Sandbox Isolation Mechanism (Fully Self-Developed)

Zest-Agent fully designed and implemented its own sandbox isolation mechanism, providing a security boundary when the Agent executes high-privilege tools (bash, file operations, browser, etc.):

- **Three-layer isolation**: filesystem isolation (sandbox-private mount + working-dir isolation), network isolation (Docker network namespace + egress allowlist), process isolation (independent PID namespace + resource limits).
- **Sandbox manager**: `zest-tools/tools/sandbox/`, unified lifecycle management.
- **Libtmux session terminal**: bash commands run in an independent tmux session to avoid shell-state pollution, with detach/reattach for long commands.
- **Docker sandbox**: each conversation is bound to an independent container with filesystem isolation; optional VSCode Server / VNC mounts.
- **Sandbox lifecycle**: sandbox is created with the conversation and auto-cleaned when the conversation ends / times out / disconnects.
- **Security policy**: default deny, egress allowlist, file-path validation, resource caps, audit log.

See [docs/architecture.md](architecture.md) Section 9 for details.

---

## 4. Module Detail

### 4.1 `zest-web` — Interaction Layer

| Item | Content |
|---|---|
| Path | `zest-web/` |
| Stack | React 18 + Vite 5 + TypeScript + Zustand + react-markdown |
| Default port | 5173 (dev) / custom (production) |
| Entry | `src/main.tsx` → App |

**Responsibilities**
- Full frontend: conversation creation, message sending, event rendering, state visualization.
- Receive real-time event streams over WebSocket; subscribe to eventCenter's `uiEvents` topic for rendering.
- Config center, conversation list, Agent detail panels.

**Key Design**
- **State management**: Zustand lightweight stores, split by domain (auth, event, conversation) to avoid giant reducers.
- **Event assembly**: `utils/buildEventGraph.ts`, `utils/runtimeEventAssembler.ts` assemble raw event streams into rendered messages, tool cards, and state items.
- **Config-driven**: `VITE_APP_API_BASE` and other build-time injected env vars support multi-environment deployment.

### 4.2 `zest-app-server` — Control Plane

| Item | Content |
|---|---|
| Path | `zest-app-server/` |
| Stack | Python 3.12 + FastAPI + Uvicorn + Pydantic Settings |
| Default port | 9000 |
| Entry | `app/main.py` → `app.main:app` |

**Responsibilities**
- Unified session entry: session create / query / pause / terminate.
- Task scheduling: pick the right execution node for each session.
- Service registry hub: maintain the available execution-node view; evict unhealthy nodes.
- Auth and config: basic auth, config center, user and Agent Profile management.

**Key routes** (`app/api/`)
- `app_conversation_route`: session CRUD.
- `app_conversation_query_route`: aggregated session query view.
- `agentservers`: execution-node registry, discovery, health.
- `agent_profile_route`: Agent roles and config.
- `auth_route`: basic auth.
- `health`: health check.

**Key config** (`app/config/settings.py`)
- `storage_mode`: `mysql` | `local`
- `registry_mode`: `redis`
- `lb_strategy`: `session_affinity` (default)
- `heartbeat_interval` / `heartbeat_timeout`: 10s / 30s
- `agent_service_*`: protocol and endpoints for the execution plane

**Load balancing**: default session affinity, pinning a conversation to the first-hit node for stable WebSocket long connections.

### 4.3 `zest-agent-server/zest-service` — Execution Plane

| Item | Content |
|---|---|
| Path | `zest-agent-server/zest-service/` |
| Stack | Python 3.12 + FastAPI + Uvicorn + WebSocket (wsproto) |
| Default port | 8001 |
| Entry | `server/__main__.py` → `server.api:api` |

**Responsibilities**
- Real Agent session lifecycle: message loop, tool invocation, state progression.
- WebSocket event channel: clients subscribe and receive the event stream during execution.
- Event replay, message sending, pause / resume / terminate.
- Tool sandbox integration, skill loading, optional VSCode / VNC remote dev.

**Key routes** (`server/`)
- `sockets_router`: WebSocket event subscribe and message push.
- `conversation_router`: session CRUD and runtime control.
- `event_router`: event query and replay.
- `file_router`: file operations.
- `tool_router` / `skills_router`: tool and skill discovery.
- `server_details_router`: node info reporting.

**Registry reporting**: writes `server_id`, `host:port`, `tags`, `heartbeat_at` to Redis `agent_registry`; periodic renewal.

**Key capabilities**
- **Breakpoint recovery**: conversation state persisted; unfinished sessions resume on restart.
- **Crash diagnostics**: `server/__main__.py` enables `faulthandler` and `atexit` for crash stack and exit logging.
- **Observable**: structured JSON logs; DEBUG mode emits stack traces.

### 4.4 `zest-agent-server/zest-sdk` — SDK Layer

| Item | Content |
|---|---|
| Path | `zest-agent-server/zest-sdk/` |
| Stack | Python + Litellm + Pydantic + Langfuse + FastMCP |
| Version | 1.10.0 |

**Responsibilities**
- Agent build core: `Agent` abstraction, `AgentRunner` scheduling skeleton, `Conversation` abstraction.
- LLM abstraction: Litellm-based unified multi-vendor access, function-call conversion, streaming.
- Skills: `sdk/context/skills/` skill loading and execution framework.
- Event and state: event bus, state machine, context management.
- Security: `sdk/secret/` secret registry and redaction.

**Key modules**
- `sdk/agent/agent.py`, `sdk/agent/agent_runner.py`: Agent core.
- `sdk/llm/llm.py`, `sdk/llm/mixins/fn_call_converter.py`: LLM call and function-call adaptation.
- `sdk/conversation/impl/conversation_impl.py`: conversation implementation.
- `sdk/context/skills/skill.py`: skill framework.
- `sdk/secret/`: secret management.

**Multi-Agent**: `AgentRunner` abstracts the entry for in-session Main-Sub Agent collaboration.

### 4.5 `zest-agent-server/zest-tools` — Tools Layer

| Item | Content |
|---|---|
| Path | `zest-agent-server/zest-tools/` |
| Stack | Python + Bashlex + Libtmux + browser-use |
| Version | 1.10.0 |

**Responsibilities**
- Toolset callable by the Agent at runtime: bash, file editor, browser, custom tools.
- Sandbox and runtime isolation: Libtmux manages session terminals; Docker sandbox (`server/docker/Dockerfile`) provides secure execution.
- Tool preload: configured tools are preloaded at startup to reduce first-call latency.

**Key modules**
- `tools/file_editor/editor.py`: file editor (string replace, snippet ops).
- `tools/sandbox/`: sandbox execution environment and config.
- `tools/preset/default.py`: default toolset preset.
- `tools/` subdirs: organized by tool type.

**Custom tools**: developers implement the SDK tool interface and mount to the execution plane.

### 4.6 `zest-common` — Shared Capabilities

| Item | Content |
|---|---|
| Path | `zest-common/` |
| Stack | Python + Pydantic + cachetools + filelock |
| Version | 0.2.0 |

**Responsibilities**
- Event log: unified event structure, write, query.
- State storage: unified abstraction for conversation state and runtime state.
- Memory storage: basic + experience memory storage interfaces with multi-backend implementations (MySQL / Mongo / ES / local).
- Query facade: `conversation_read_facade` aggregates state, events, memory into a unified read entry.
- Observability: structured logger, debug tools.
- Security: secrets and encryption (`common/security/`, `common/utils/pydantic_secrets.py`).

**Key modules**
- `common/chain/`: chained call and pipeline.
- `common/event/`: event structure and log.
- `common/logger/`: structured logging.
- `common/models/`: shared data models.
- `common/observability/`: observability.
- `common/query/`: query facade.
- `common/security/`: security and encryption.
- `common/storage/`: storage abstraction and multi-backend implementations.
- `common/utils/`: common utilities.

**Optional deps**: `pyproject.toml` optional-dependencies selectively include `pymongo`, `elasticsearch`, `boto3`, avoiding forced install of unused backends.

---

## 5. Typical Use Cases

### Use case 1: Enterprise Agent application platform
Multiple business units share one execution pool, isolated by conversation. The control plane provides unified auth and quota; the execution plane routes by business tags; memory is partitioned by tenant.

### Use case 2: Multi-Agent collaboration
The main Agent decomposes complex tasks; sub-Agents execute by tool or role. Example: research Agent gathers materials → coding Agent implements → test Agent validates → main Agent integrates.

### Use case 3: Long-term-memory assistant
Cross-session accumulation of user preferences (basic) and "problem-solution-execution-feedback" trajectories (experience). On similar future tasks, ES retrieval recalls experience to improve response quality.

### Use case 4: Observable Agent ops
Session-level event stream + state snapshots + Langfuse LLM tracing give both ops and product teams visibility into every thought, tool call, and state change.

### Use case 5: Secondary development and teaching
A clean four-layer architecture and replaceable storage backends make Zest-Agent a reference implementation of an engineering-grade Agent platform. Swap LLMs, swap storage, add tools, extend scheduling — all without touching the core.

---

## 6. Roadmap

The following is a preliminary plan; order and timing may shift based on community feedback.

- **v0.1** (initial release): stable four-layer architecture; single-node execution plane runs full conversations end-to-end; basic + experience memory skeleton; real-time event stream; Docker Compose one-shot startup.
- **v0.2**: multi-replica execution-plane horizontal scale validation; complete load-balancing strategies (least-connection, tag routing); enhanced breakpoint recovery.
- **v0.3**: stabilize multi-Agent collaboration; Main-Sub Agent orchestration DSL; cross-Agent memory sharing.
- **v0.4**: observability enhancements; ops dashboard; session replay UI; performance tuning and load testing.
- **v0.5**: plugin tool marketplace; skill template library; multi-LLM routing strategies.

See GitHub Projects for issues and milestones.

---

## 7. Acknowledgements and Open-Source Statement

Zest-Agent is an architecture-level re-architecture and extension based on [OpenHands](https://github.com/All-Hands-AI/OpenHands) (All Hands AI, MIT License). We thank the OpenHands team for their outstanding contributions to the open-source Agent ecosystem.

- License: Apache-2.0 (see `LICENSE`); derived from OpenHands (MIT), original MIT notice retained in `NOTICE.md`
- Attribution and third-party deps: see `NOTICE.md`
- Contribution guide: see `CONTRIBUTING.md`
- Security disclosure: see `SECURITY.md`

We welcome community contributions — issue feedback, PR fixes, doc improvements, or scenario sharing all mean a lot to us.
