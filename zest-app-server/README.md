# Zest-Agent AppServer

Zest-Agent AppServer 是 Zest-Agent 架构的**控制面**，负责会话管理、服务注册发现、负载均衡和任务管理。

## 项目概述

AppServer 提供以下核心功能：
- 会话管理（创建、查询、取消、恢复）
- 任务管理（创建、查询、更新、进度跟踪）
- AgentServer 管理（注册、心跳、健康检查）
- 存储层抽象（运行时数据 + 资源数据统一由 STORAGE_MODE 控制）
- 服务注册发现（redis / local）
- 负载均衡（会话亲和性、权重轮询、随机）

## 存储架构

AppServer 把数据分为两类，由同一个 backend 统一承载：

| 类别 | 数据 | local 模式 | mysql 模式 |
|------|------|-----------|-----------|
| 运行时数据 | 会话 / 任务 / AgentServer / 用户 | JSON 文件 | MySQL 表 |
| 资源数据 | LLM 配置 / 技能 / 提示词 / 子 Agent | JSON 文件 | MySQL 表 |

通过单一 `STORAGE_MODE` 环境变量控制（`local` / `mysql`）。存储入口统一由 `storage_registry.backend` 提供。

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境

```bash
cp .env.example .env
# 编辑 .env，配置 STORAGE_MODE
```

### 3. 运行应用

```bash
python -m app.main
# 或
uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

### 4. 访问 API 文档

- Swagger UI: http://localhost:9000/docs
- ReDoc: http://localhost:9000/redoc

## API 接口

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/conversations` | 创建新会话 |
| GET | `/api/v1/conversations/{id}` | 获取会话详情 |
| GET | `/api/v1/conversations/users/{user_id}` | 获取用户会话列表 |
| DELETE | `/api/v1/conversations/{id}` | 删除会话 |
| POST | `/api/v1/conversations/{id}/respond_to_confirmation` | 响应 agent 确认请求 |

### 会话查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/conversations/{id}/events` | 事件流 |
| GET | `/api/v1/conversations/{id}/memories/base` | 基础记忆 |
| GET | `/api/v1/conversations/{id}/memories/experience` | 经验记忆 |
| GET | `/api/v1/conversations/{id}/state` | 会话状态视图 |

### 资源管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/v1/agent-config/llm-configs` | LLM 配置列表/创建 |
| GET/POST/PUT | `/api/v1/agent-config/skills` | 技能列表/创建/更新 |
| GET/POST/PUT | `/api/v1/agent-config/prompts` | 提示词列表/创建/更新 |
| GET/POST/PUT | `/api/v1/agent-config/subagent-configs` | 子 Agent 配置 |

### AgentServer 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/agentservers` | 服务列表 |
| GET | `/api/v1/agentservers/healthy` | 健康服务列表 |
| GET | `/api/v1/agentservers/{server_id}` | 服务详情 |
| POST | `/api/v1/agentservers/health-check` | 执行健康检查 |

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/auth/session` | 当前登录态 |
| POST | `/api/v1/auth/login/password` | 密码登录 |
| POST | `/api/v1/auth/logout` | 登出 |
| POST | `/api/v1/auth/register` | 注册 |

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/health/status` | 服务健康状态 |
| GET | `/registry/status` | 注册中心状态 |
| GET | `/metrics` | 系统指标 |

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `STORAGE_MODE` | 存储模式 (local/mysql) | local |
| `MYSQL_URL` | MySQL 连接 URL | mysql+aiomysql://root:root@localhost:3306/zest_agent |
| `LOCAL_DATA_DIR` | 本地数据目录 | ./.data |
| `REGISTRY_MODE` | 注册模式 (redis/local) | redis |
| `REDIS_URL` | Redis 连接 URL | redis://localhost:6379/0 |
| `HOST` | 监听地址 | 0.0.0.0 |
| `PORT` | 监听端口 | 9000 |
| `DEBUG` | 调试模式 | true |
| `ZEST_SECRET_KEY` | SecretStr 字段加解密密钥 | - |

## 开发指南

### 运行测试

```bash
pytest tests/ -v
```

### 代码格式化

```bash
black app/
flake8 app/
```

### 查看日志

```bash
tail -f .data/logs/appserver.log
```

## 技术栈

- Web 框架: FastAPI
- 存储: LocalFile / MySQL
- 服务注册: Redis / Local
- API 文档: Swagger/OpenAPI
- 部署: Docker

## 许可证

MIT License
