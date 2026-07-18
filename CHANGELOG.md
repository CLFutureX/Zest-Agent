# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- 完整开源治理文件（CONTRIBUTING / CODE_OF_CONDUCT / SECURITY / NOTICE / CHANGELOG）
- `docker-compose.yml`：默认拉起 Redis + MySQL，可选 mongo / elasticsearch
- `docker/Dockerfile.web` / `Dockerfile.app-server` / `Dockerfile.service`：三服务镜像构建脚本，`docker compose --profile app up -d --build` 一键起完整栈
- `.dockerignore`：避免 `.git` / `node_modules` / `.venv` / `tmp/` 等进入构建上下文
- 三份 `.env.example`：根目录 / zest-app-server / zest-service
- `scripts/start-dev.ps1` 与 `scripts/start-dev.sh`：一键启动三服务
- `Makefile`：install / dev / stop / infra / up / lint / test / web-build
- `docs/overview.md`：完整项目介绍
- `docs/quickstart.md`（中）与 `docs/en/quickstart.md`（英）：快速开始
- `docs/architecture.md`：架构详解
- `docs/deployment.md`：生产部署
- `.github/`：CI workflows 与 Issue / PR 模板（待补齐）

### Changed
- `README.md` 从 0 字节空文件重写为完整门面文档
- `.gitignore` 重写，移除 `*.ps1` / `*.cmd` 等过宽规则，新增运行时产物忽略

### Removed
- 从 git 跟踪中移除：`dump.rdb`、`main.py`（根目录临时脚本）、`restore_web.py`、`temp_rewrite.py`、`REFACTOR_PLAN.md`、`PROJECT_COMPETITION_ANALYSIS.md`、`tmp/`、`.agents/`、`.workspace/`、`code_index/`、`code_wiki/`、`wiki_md/`、`.zest_hook/`
- 移除 `zest-web/package-lock.json`，收敛为 pnpm 单一 lockfile

---

## [0.1.0] - 2026-07-12

### Added
- 四层架构稳定：交互层 `zest-web`、控制面 `zest-app-server`、执行面 `zest-agent-server/zest-service`、共享层 `zest-sdk` / `zest-tools` / `zest-common`
- 控制面 / 执行面分离：`zest-app-server` 负责会话入口与调度，`zest-service` 负责真实执行
- Redis 服务注册 + 心跳 + 健康检查 + 会话粘性负载均衡
- 多层记忆体系：基础记忆（用户画像、偏好、上下文）+ 经验记忆（问题—方案—执行轨迹）
- `zest-common` 收敛存储抽象，支持 MySQL / Mongo / ES / 本地文件多后端
- `conversation_read_facade` 统一查询门面，聚合状态、事件、记忆
- WebSocket 双向事件流，自研 eventCenter 发布-订阅模型（`events` + `uiEvents` 双主题）
- `AgentRunner` 调度骨架，预留 Main-Sub Agent 协同
- 会话状态持久化与断点恢复
- 结构化 JSON 日志 + Langfuse 集成
- 前端 `zest-web` 对齐 OpenHands V1 风格，订阅 eventCenter 的 `uiEvents` 主题渲染
- Python 3.12 + uv workspace 多包管理
- pre-commit 钩子配置
- Apache License 2.0，致敬 OpenHands（衍生自 MIT，原 MIT 声明保留在 NOTICE）

### Known Limitations
- 多 Agent 协同仍在打磨，骨架已就绪
- 执行面多副本横向扩展尚未在真实环境验证
- 负载均衡策略仅有 `session_affinity`，未实现 `least_connection` / `tag_routing`
- 未发布预构建 Docker 镜像
- 前端单元测试框架未引入

---

## Versioning

- 主版本号 (major)：不兼容的 API 变更
- 次版本号 (minor)：向后兼容的功能新增
- 修订号 (patch)：向后兼容的 Bug 修复

预发布版本会在版本号后加 `-alpha` / `-beta` / `-rc` 后缀，例如 `0.2.0-alpha.1`。
