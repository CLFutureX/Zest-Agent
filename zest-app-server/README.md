# Zest-Agent AppServer

Zest-Agent AppServer 是 Zest-Agent 架构的**控制面**，负责会话管理、服务注册发现、负载均衡和任务管理。

## 项目概述

AppServer 提供以下核心功能：
- ✅ 会话管理（创建、查询、取消、恢复）
- ✅ 任务管理（创建、查询、更新、进度跟踪）
- ✅ AgentServer管理（注册、心跳、健康检查）
- ✅ 存储层抽象（支持LocalFile和MongoDB）
- ✅ 服务注册发现（支持redis）
- ✅ 负载均衡（会话亲和性、权重轮询）

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境

```bash
# 复制环境变量示例文件
cp .env.example .env

# 编辑 .env 文件，配置你的环境
```

### 3. 运行应用

```bash
# 开发模式
python -m app.main

# 或使用 uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 访问API文档

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

 

## API 接口

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/sessions` | 创建新会话 |
| GET | `/api/v1/sessions/{session_id}` | 获取会话详情 |
| GET | `/api/v1/users/{user_id}/sessions` | 获取用户会话列表 |
| POST | `/api/v1/sessions/{session_id}/cancel` | 取消会话 |
| POST | `/api/v1/sessions/{session_id}/resume` | 恢复会话 |

### 任务管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/sessions/{session_id}/tasks` | 创建任务 |
| GET | `/api/v1/tasks/{task_id}` | 获取任务详情 |
| PATCH | `/api/v1/tasks/{task_id}` | 更新任务状态 |
| GET | `/api/v1/users/{user_id}/tasks` | 获取用户任务列表 |
| GET | `/api/v1/sessions/{session_id}/tasks` | 获取会话任务列表 | 
| POST | `/api/v1/tasks/{task_id}/cancel` | 取消任务 |

### 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/metrics` | 系统指标 |

## 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `STORAGE_MODE` | 存储模式 (local/mongodb) | local |
| `REGISTRY_MODE` | 注册模式 (redis) | redis |
| `LOCAL_DATA_DIR` | 本地数据目录 | ./data |
| `HOST` | 监听地址 | 0.0.0.0 |
| `PORT` | 监听端口 | 8000 |
| `DEBUG` | 调试模式 | false |

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
tail -f logs/appserver.log
```

## 实施计划

- [x] **Phase 1: 基础框架** (当前)
  - [x] 项目结构搭建
  - [x] 配置管理
  - [x] 存储层抽象接口
  - [x] LocalFile 存储实现
  - [x] 基础 API 路由

- [ ] **Phase 2: 核心功能**
  - [ ] MongoDB 存储实现
  - [ ] 会话管理完整功能
  - [ ] 任务管理功能
  - [ ] AgentServer 注册与心跳
  - [ ] 负载均衡实现

- [ ] **Phase 3: 服务注册**
  - [ ] redsi 模式实现 
  - [ ] 健康检查机制

- [ ] **Phase 4: 增强功能**
  - [ ] JWT 认证
  - [ ] 请求限流
  - [ ] 日志与监控
  - [ ] 异常处理
  - [ ] 重试机制

- [ ] **Phase 5: 测试与优化**
  - [ ] 单元测试
  - [ ] 集成测试
  - [ ] 性能优化
  - [ ] 文档完善

- [ ] **Phase 6: 部署上线**
  - [ ] Docker 配置
  - [ ] CI/CD 流水线
  - [ ] 生产环境部署
  - [ ] 监控告警

## 技术栈

- **Web框架**: FastAPI
- **存储**: LocalFile / MongoDB
- **服务注册**: Local / etcd
- **API文档**: Swagger/OpenAPI
- **部署**: Docker

## 许可证

MIT License


