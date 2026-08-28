"""
MySQL 存储实现
使用 aiomysql 异步连接池存储会话、任务、AgentServer、用户数据。

注意：
1. Pool 没有 execute() 方法，必须 acquire() 后用 cursor 操作。
2. SQL 中 JSON 列字段在 aiomysql 中根据 autocommit/charset 自动解析为 str，需手动 json.loads。
3. update 字段名做白名单过滤，避免 SQL 注入。
4. register_server / create_user 等 upsert 语义使用 INSERT ... ON DUPLICATE KEY UPDATE。
5. Schema 与 app.core.models 中的 pydantic 模型严格对齐：
   - conversations 表无 agent_server_id 列（AppConversationInfo 无此字段）
   - tasks 表无 id/title/description 列（TaskInfo 无这些字段），改用 conversation_id 列
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

import aiomysql

from app.core.models import (
    AgentServerInfo,
    AppConversationInfo,
    AuthUser,
    ServerStatus,
    TaskInfo,
    TaskStatus,
)
from app.core.storage.base import (
    AgentServerStorage,
    AppConversationStorage,
    TaskStorage,
    UserStorage,
)
from app.core.storage.serializer import _cipher

logger = logging.getLogger(__name__)


# ==============================
# 连接池管理
# ==============================
class _MysqlPoolManager:
    def __init__(self) -> None:
        self._pool: Optional[aiomysql.Pool] = None

    async def init_pool(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        db: str,
        minsize: int = 2,
        maxsize: int = 10,
    ) -> None:
        if self._pool is None:
            self._pool = await aiomysql.create_pool(
                host=host,
                port=port,
                user=user,
                password=password,
                db=db,
                autocommit=True,
                minsize=minsize,
                maxsize=maxsize,
                charset="utf8mb4",
            )

    async def close(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    @property
    def pool(self) -> aiomysql.Pool:
        if self._pool is None:
            raise RuntimeError("MySQL pool not initialized. Call init_mysql_pool first.")
        return self._pool


_mysql_pool = _MysqlPoolManager()


async def init_mysql_pool(url: str, minsize: int = 2, maxsize: int = 10) -> None:
    parsed = urlparse(url.replace("mysql+aiomysql://", "mysql://"))
    await _mysql_pool.init_pool(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=parsed.username or "root",
        password=parsed.password or "",
        db=parsed.path.lstrip("/"),
        minsize=minsize,
        maxsize=maxsize,
    )


async def close_mysql_pool() -> None:
    await _mysql_pool.close()


# ==============================
# 通用辅助
# ==============================
def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _ensure_json(obj) -> str:
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, default=_json_default, ensure_ascii=False)


def _maybe_loads(val):
    if isinstance(val, str) and val:
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            pass
    return val


async def _index_exists(cur, table: str, idx_name: str) -> bool:
    await cur.execute(
        "SELECT 1 FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() "
        "AND table_name = %s AND index_name = %s",
        (table, idx_name),
    )
    return await cur.fetchone() is not None


async def _ensure_index(cur, table: str, idx_name: str, column: str, desc: bool = False) -> None:
    if await _index_exists(cur, table, idx_name):
        return
    order = "DESC" if desc else ""
    await cur.execute(f"CREATE INDEX {idx_name} ON {table}({column}) {order}".strip())


# ==============================
# 会话存储
# ==============================
class MysqlAppConversationStorage(AppConversationStorage):
    """MySQL 会话存储。

    表结构与 AppConversationInfo 模型对齐：无 agent_server_id 列（运行时归属由 TaskInfo.agent_server_id 维护）。
    """

    _ALLOWED_UPDATE_FIELDS = {
        "user_id", "model", "llm_config_id", "skill_ids", "prompt_ids",
        "selected_tool_names", "initial_message", "started_at",
        "metadata", "error_message", "updated_at",
    }

    async def ensure_indexes(self) -> None:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id VARCHAR(128) PRIMARY KEY,
                        user_id VARCHAR(128) NOT NULL,
                        model VARCHAR(128) NULL,
                        llm_config_id VARCHAR(128) NULL,
                        skill_ids JSON DEFAULT '[]',
                        prompt_ids JSON DEFAULT '[]',
                        selected_tool_names JSON DEFAULT '[]',
                        initial_message TEXT NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        started_at DATETIME NULL,
                        metadata JSON DEFAULT '{}',
                        error_message TEXT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await _ensure_index(cur, "conversations", "idx_conversations_user_id", "user_id")
                await _ensure_index(cur, "conversations", "idx_conversations_created_at", "created_at", desc=True)

    async def create_app_conversation(self, conversation: AppConversationInfo) -> bool:
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO conversations (
                            id, user_id, model, llm_config_id, skill_ids, prompt_ids,
                            selected_tool_names, initial_message, created_at, updated_at,
                            started_at, metadata, error_message
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            conversation.id,
                            conversation.user_id,
                            conversation.model,
                            conversation.llm_config_id,
                            _ensure_json(conversation.skill_ids),
                            _ensure_json(conversation.prompt_ids),
                            _ensure_json(conversation.selected_tool_names),
                            conversation.initial_message,
                            conversation.created_at,
                            conversation.updated_at,
                            conversation.started_at,
                            _ensure_json(conversation.metadata),
                            conversation.error_message,
                        ),
                    )
                    return True
        except Exception:
            logger.exception("create_app_conversation failed")
            return False

    async def get_app_conversation(self, id: str) -> Optional[AppConversationInfo]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM conversations WHERE id = %s", (id,))
                row = await cur.fetchone()
        if not row:
            return None
        return self._row_to_model(row)

    async def update_app_conversation(self, id: str, updates: dict) -> bool:
        filtered = {
            k: v for k, v in updates.items() if k in self._ALLOWED_UPDATE_FIELDS
        }
        if not filtered:
            return False
        filtered["updated_at"] = datetime.utcnow()

        set_clauses = []
        values = []
        for key, value in filtered.items():
            if key in ("skill_ids", "prompt_ids", "selected_tool_names", "metadata") and not isinstance(value, str):
                value = _ensure_json(value)
            set_clauses.append(f"{key} = %s")
            values.append(value)
        values.append(id)
        query = f"UPDATE conversations SET {', '.join(set_clauses)} WHERE id = %s"
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, values)
                    return cur.rowcount > 0
        except Exception:
            logger.exception("update_app_conversation failed")
            return False

    async def delete_app_conversation(self, session_id: str) -> bool:
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM conversations WHERE id = %s", (session_id,))
                    return cur.rowcount > 0
        except Exception:
            logger.exception("delete_app_conversation failed")
            return False

    async def list_app_conversations_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AppConversationInfo]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # status 字段当前会话表没有，仅按 user_id 过滤；保留参数以兼容接口。
                await cur.execute(
                    """
                    SELECT * FROM conversations
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset),
                )
                rows = await cur.fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: dict) -> AppConversationInfo:
        return AppConversationInfo(
            id=row["id"],
            user_id=row["user_id"],
            model=row.get("model"),
            llm_config_id=row.get("llm_config_id"),
            skill_ids=_maybe_loads(row.get("skill_ids")) or [],
            prompt_ids=_maybe_loads(row.get("prompt_ids")) or [],
            selected_tool_names=_maybe_loads(row.get("selected_tool_names")) or [],
            initial_message=row.get("initial_message"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row.get("started_at"),
            metadata=_maybe_loads(row.get("metadata")) or {},
            error_message=row.get("error_message"),
        )


# ==============================
# 任务存储
# ==============================
class MysqlTaskStorage(TaskStorage):
    """MySQL 任务存储。表结构与 TaskInfo 模型对齐：使用 conversation_id 列。"""

    _ALLOWED_UPDATE_FIELDS = {
        "status", "dispatch_attempt", "remote_conversation_id", "updated_at",
        "result", "error_message", "metadata", "agent_server_id",
        "base_url", "events_url", "websocket_url", "session_api_key",
        "conversation_id", "user_id",
    }

    async def ensure_indexes(self) -> None:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id VARCHAR(128) PRIMARY KEY,
                        conversation_id VARCHAR(128) NOT NULL,
                        user_id VARCHAR(128) NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        dispatch_attempt INT NOT NULL DEFAULT 0,
                        remote_conversation_id VARCHAR(128) NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NULL,
                        result JSON NULL,
                        error_message TEXT NULL,
                        metadata JSON DEFAULT '{}',
                        agent_server_id VARCHAR(128) NULL,
                        base_url VARCHAR(256) NULL,
                        events_url VARCHAR(256) NULL,
                        websocket_url VARCHAR(256) NULL,
                        session_api_key VARCHAR(256) NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await _ensure_index(cur, "tasks", "idx_tasks_conversation_id", "conversation_id")
                await _ensure_index(cur, "tasks", "idx_tasks_user_id", "user_id")
                await _ensure_index(cur, "tasks", "idx_tasks_status", "status")
                await _ensure_index(cur, "tasks", "idx_tasks_created_at", "created_at", desc=True)

    async def save_task(self, task: TaskInfo) -> bool:
        existing = await self.get_task(task.task_id)
        if existing is None:
            return await self.create_task(task)
        return await self.update_task(task.task_id, task.model_dump(exclude_unset=True))

    async def create_task(self, task: TaskInfo) -> bool:
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO tasks (
                            task_id, conversation_id, user_id, status, dispatch_attempt,
                            remote_conversation_id, created_at, updated_at, result,
                            error_message, metadata, agent_server_id, base_url,
                            events_url, websocket_url, session_api_key
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            task.task_id,
                            task.conversation_id,
                            task.user_id,
                            task.status.value,
                            task.dispatch_attempt,
                            task.remote_conversation_id,
                            task.created_at,
                            task.updated_at,
                            _ensure_json(task.result) if task.result else None,
                            task.error_message,
                            _ensure_json(task.metadata),
                            task.agent_server_id,
                            task.base_url,
                            task.events_url,
                            task.websocket_url,
                            task.session_api_key,
                        ),
                    )
                    return True
        except Exception:
            logger.exception("create_task failed")
            return False

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
                row = await cur.fetchone()
        if not row:
            return None
        return self._row_to_model(row)

    async def update_task(self, task_id: str, updates: dict) -> bool:
        filtered = {
            k: v for k, v in updates.items() if k in self._ALLOWED_UPDATE_FIELDS
        }
        if not filtered:
            return False
        filtered["updated_at"] = datetime.utcnow()

        set_clauses = []
        values = []
        for key, value in filtered.items():
            if key in ("result", "metadata") and not isinstance(value, str):
                value = _ensure_json(value)
            set_clauses.append(f"{key} = %s")
            values.append(value)
        values.append(task_id)
        query = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE task_id = %s"
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, values)
                    return cur.rowcount > 0
        except Exception:
            logger.exception("update_task failed")
            return False

    async def delete_task(self, task_id: str) -> bool:
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM tasks WHERE task_id = %s", (task_id,))
                    return cur.rowcount > 0
        except Exception:
            logger.exception("delete_task failed")
            return False

    async def list_tasks_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TaskInfo]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if status:
                    await cur.execute(
                        """
                        SELECT * FROM tasks
                        WHERE user_id = %s AND status = %s
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (user_id, status, limit, offset),
                    )
                else:
                    await cur.execute(
                        """
                        SELECT * FROM tasks
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (user_id, limit, offset),
                    )
                rows = await cur.fetchall()
        return [self._row_to_model(r) for r in rows]

    async def list_tasks_by_app_conversation(self, session_id: str) -> List[TaskInfo]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM tasks WHERE conversation_id = %s ORDER BY created_at DESC",
                    (session_id,),
                )
                rows = await cur.fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: dict) -> TaskInfo:
        return TaskInfo(
            task_id=row["task_id"],
            conversation_id=row["conversation_id"],
            user_id=row["user_id"],
            status=TaskStatus(row["status"]),
            dispatch_attempt=row.get("dispatch_attempt", 0),
            remote_conversation_id=row.get("remote_conversation_id"),
            created_at=row["created_at"],
            updated_at=row.get("updated_at"),
            result=_maybe_loads(row.get("result")),
            error_message=row.get("error_message"),
            metadata=_maybe_loads(row.get("metadata")) or {},
            agent_server_id=row.get("agent_server_id"),
            base_url=row.get("base_url"),
            events_url=row.get("events_url"),
            websocket_url=row.get("websocket_url"),
            session_api_key=row.get("session_api_key"),
        )


# ==============================
# AgentServer 存储
# ==============================
class MysqlAgentServerStorage(AgentServerStorage):
    _ALLOWED_UPDATE_FIELDS = {
        "host", "port", "status", "capabilities", "metrics",
        "last_heartbeat", "registered_at", "version", "tags",
    }

    async def ensure_indexes(self) -> None:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_servers (
                        server_id VARCHAR(128) PRIMARY KEY,
                        host VARCHAR(256) NOT NULL,
                        port INT NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'healthy',
                        capabilities JSON DEFAULT '{}',
                        metrics JSON DEFAULT '{}',
                        last_heartbeat DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        registered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        version VARCHAR(64) NULL,
                        tags JSON DEFAULT '[]'
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await _ensure_index(cur, "agent_servers", "idx_agent_servers_status", "status")
                await _ensure_index(cur, "agent_servers", "idx_agent_servers_registered_at", "registered_at")

    async def register_server(self, server: AgentServerInfo) -> bool:
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO agent_servers (
                            server_id, host, port, status, capabilities, metrics,
                            last_heartbeat, registered_at, version, tags
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            host=VALUES(host), port=VALUES(port), status=VALUES(status),
                            capabilities=VALUES(capabilities), metrics=VALUES(metrics),
                            last_heartbeat=VALUES(last_heartbeat), version=VALUES(version),
                            tags=VALUES(tags)
                        """,
                        (
                            server.server_id,
                            server.host,
                            server.port,
                            server.status.value,
                            _ensure_json(server.capabilities),
                            _ensure_json(server.metrics),
                            server.last_heartbeat,
                            server.registered_at,
                            server.version,
                            _ensure_json(server.tags),
                        ),
                    )
                    return True
        except Exception:
            logger.exception("register_server failed")
            return False

    async def deregister_server(self, server_id: str) -> bool:
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("DELETE FROM agent_servers WHERE server_id = %s", (server_id,))
                    return cur.rowcount > 0
        except Exception:
            logger.exception("deregister_server failed")
            return False

    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM agent_servers WHERE server_id = %s", (server_id,))
                row = await cur.fetchone()
        if not row:
            return None
        return self._row_to_model(row)

    async def update_server(self, server_id: str, updates: dict) -> bool:
        filtered = {
            k: v for k, v in updates.items() if k in self._ALLOWED_UPDATE_FIELDS
        }
        if not filtered:
            return False
        set_clauses = []
        values = []
        for key, value in filtered.items():
            if key in ("capabilities", "metrics", "tags") and not isinstance(value, str):
                value = _ensure_json(value)
            set_clauses.append(f"{key} = %s")
            values.append(value)
        values.append(server_id)
        query = f"UPDATE agent_servers SET {', '.join(set_clauses)} WHERE server_id = %s"
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, values)
                    return cur.rowcount > 0
        except Exception:
            logger.exception("update_server failed")
            return False

    async def list_healthy_servers(self) -> List[AgentServerInfo]:
        return await self._fetch_servers("status = 'healthy'")

    async def list_all_servers(self) -> List[AgentServerInfo]:
        return await self._fetch_servers("1=1")

    async def _fetch_servers(self, where_clause: str) -> List[AgentServerInfo]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"SELECT * FROM agent_servers WHERE {where_clause} ORDER BY registered_at ASC"
                )
                rows = await cur.fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: dict) -> AgentServerInfo:
        return AgentServerInfo(
            server_id=row["server_id"],
            host=row["host"],
            port=row["port"],
            status=ServerStatus(row["status"]),
            capabilities=_maybe_loads(row.get("capabilities")) or {},
            metrics=_maybe_loads(row.get("metrics")) or {},
            last_heartbeat=row["last_heartbeat"],
            registered_at=row["registered_at"],
            version=row.get("version"),
            tags=_maybe_loads(row.get("tags")) or [],
        )


# ==============================
# 用户存储
# ==============================
class MysqlUserStorage(UserStorage):
    _ALLOWED_UPDATE_FIELDS = {
        "username", "email", "password_hash", "is_active", "updated_at",
    }

    async def ensure_indexes(self) -> None:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id       VARCHAR(128)  NOT NULL PRIMARY KEY,
                        username      VARCHAR(128)  NOT NULL,
                        email         VARCHAR(256)  NOT NULL,
                        password_hash VARCHAR(512)  NOT NULL,
                        is_active     TINYINT(1)    NOT NULL DEFAULT 1,
                        created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                      ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await _ensure_index(cur, "users", "idx_users_username", "username")
                await _ensure_index(cur, "users", "idx_users_email", "email")

    async def create_user(self, user: AuthUser) -> bool:
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO users
                            (user_id, username, email, password_hash, is_active, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            username=VALUES(username), email=VALUES(email),
                            password_hash=VALUES(password_hash), is_active=VALUES(is_active),
                            updated_at=VALUES(updated_at)
                        """,
                        (
                            user.user_id, user.username, user.email,
                            user.password_hash, int(user.is_active),
                            user.created_at, user.updated_at,
                        ),
                    )
                    return True
        except Exception:
            logger.exception("create_user failed")
            return False

    @staticmethod
    def _row_to_user(row: dict) -> AuthUser:
        return AuthUser(
            user_id=row["user_id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            is_active=bool(row.get("is_active")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM users WHERE user_id = %s LIMIT 1", (user_id,))
                row = await cur.fetchone()
        return self._row_to_user(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[AuthUser]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM users WHERE username = %s LIMIT 1", (username,))
                row = await cur.fetchone()
        return self._row_to_user(row) if row else None

    async def get_user_by_email(self, email: str) -> Optional[AuthUser]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM users WHERE email = %s LIMIT 1", (email,))
                row = await cur.fetchone()
        return self._row_to_user(row) if row else None

    async def update_user(self, user_id: str, updates: dict) -> bool:
        filtered = {
            k: v for k, v in updates.items() if k in self._ALLOWED_UPDATE_FIELDS
        }
        if not filtered:
            return False
        filtered.setdefault("updated_at", datetime.utcnow())
        if "is_active" in filtered:
            filtered["is_active"] = int(bool(filtered["is_active"]))
        set_clause = ", ".join(f"{k} = %s" for k in filtered)
        values = list(filtered.values()) + [user_id]
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"UPDATE users SET {set_clause} WHERE user_id = %s",
                        values,
                    )
                    return cur.rowcount > 0
        except Exception:
            logger.exception("update_user failed")
            return False
