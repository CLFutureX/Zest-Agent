"""
MySQL存储实现
使用aiomysql异步连接池存储会话、任务和AgentServer数据

与PostgreSQL的差异：
1. 使用 aiomysql 替代 asyncpg
2. 占位符使用 %s 而非 $1, $2
3. JSON 类型替代 JSONB（MySQL 5.7+ 支持）
4. DATETIME 替代 TIMESTAMPTZ
5. 索引创建需先检查是否存在
"""
from typing import List, Optional
from datetime import datetime

import aiomysql

from app.core.storage.base import AppConversationStorage, TaskStorage, AgentServerStorage, UserStorage
from app.core.models import AppConversationInfo, TaskInfo, AgentServerInfo, TaskStatus, ServerStatus, AuthUser


class _Mysqlconversation:
    """MySQL 连接池管理器"""

    def __init__(self):
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
    ):
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

    async def close(self):
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    @property
    def pool(self) -> aiomysql.Pool:
        if self._pool is None:
            raise RuntimeError("MySQL pool not initialized. Call init_pool first.")
        return self._pool


# 全局连接池单例
_mysql_conversation = _Mysqlconversation()


async def init_mysql_pool(url: str, minsize: int = 2, maxsize: int = 10):
    """初始化 MySQL 连接池，解析 URL 格式: mysql+aiomysql://user:pass@host:port/db"""
    from urllib.parse import urlparse

    parsed = urlparse(url.replace("mysql+aiomysql://", "mysql://"))
    await _mysql_conversation.init_pool(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=parsed.username or "root",
        password=parsed.password or "",
        db=parsed.path.lstrip("/"),
        minsize=minsize,
        maxsize=maxsize,
    )


async def close_mysql_pool():
    """关闭 MySQL 连接池"""
    await _mysql_conversation.close()

 


def _json_default(obj):
    """JSON 序列化默认处理"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _ensure_json(obj):
    """确保对象可序列化"""
    import json

    if isinstance(obj, str):
        return obj
    return json.dumps(obj, default=_json_default, ensure_ascii=False)


class MysqlAppConversationStorage(AppConversationStorage):
    """MySQL 会话存储"""

    async def ensure_indexes(self):
        """创建表结构及索引"""
        pool = _mysql_conversation.pool

        await pool.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id VARCHAR(128) PRIMARY KEY,
                user_id VARCHAR(128) NOT NULL,
                agent_server_id VARCHAR(128) NOT NULL, 
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                started_at DATETIME NULL,
                metadata JSON DEFAULT '{}',
                error_message TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                indexes = [
                    ("idx_conversations_user_id", "conversations", "user_id"), 
                    ("idx_conversations_created_at", "conversations", "created_at"),
                ]
                for idx_name, table, column in indexes:
                    await cur.execute(
                        "SELECT 1 FROM information_schema.statistics "
                        "WHERE table_schema = DATABASE() "
                        "AND table_name = %s AND index_name = %s",
                        (table, idx_name),
                    )
                    if not await cur.fetchone():
                        order = "DESC" if column == "created_at" else ""
                        await cur.execute(
                            f"CREATE INDEX {idx_name} ON {table}({column}) {order}"
                        )

    async def create_conversation(self, conversation: AppConversationInfo) -> bool:
        try:
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO conversations (
                            id, user_id, agent_server_id, 
                            created_at, updated_at, started_at, metadata, error_message
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            conversation.id,
                            conversation.user_id, 
                            conversation.created_at,
                            conversation.updated_at,
                            conversation.started_at,
                            _ensure_json(conversation.metadata),
                            conversation.error_message,
                        ),
                    )
                    await conn.commit()
                    return True
        except Exception:
            return False

    async def get_conversation(self, id: str) -> Optional[AppConversationInfo]:
        import json

        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM conversations WHERE id = %s", (id,)
                )
                row = await cur.fetchone()
                if not row:
                    return None
                if row.get("metadata") and isinstance(row["metadata"], str):
                    row["metadata"] = json.loads(row["metadata"])
                return AppConversationInfo(
                    id=row["id"],
                    user_id=row["user_id"], 
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    started_at=row.get("started_at"),
                    metadata=row.get("metadata") or {},
                    error_message=row.get("error_message"),
                )

    async def update_conversation(self, id: str, updates: dict) -> bool:
        try:
            updates["updated_at"] = datetime.utcnow()

            set_clauses = []
            values = []
            for key, value in updates.items():
                if key in ("metadata",) and not isinstance(value, str):
                    value = _ensure_json(value)
                set_clauses.append(f"{key} = %s")
                values.append(value)

            values.append(id)

            query = f"""
                UPDATE conversations SET {', '.join(set_clauses)}
                WHERE id = %s
            """
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, values)
                    await conn.commit()
                    return cur.rowcount > 0
        except Exception:
            return False

    async def delete_conversation(self, id: str) -> bool:
        try:
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM conversations WHERE id = %s", (id,)
                    )
                    await conn.commit()
                    return cur.rowcount > 0
        except Exception:
            return False

    async def list_conversations_by_user(
        self,
        user_id: str, 
        limit: int = 50,
        offset: int = 0,
    ) -> List[AppConversationInfo]:
        import json

        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur: 
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

        results = []
        for r in rows:
            if r.get("metadata") and isinstance(r["metadata"], str):
                r["metadata"] = json.loads(r["metadata"])
            results.append(
                AppConversationInfo(
                    id=r["id"],
                    user_id=r["user_id"], 
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    started_at=r.get("started_at"),
                    metadata=r.get("metadata") or {},
                    error_message=r.get("error_message"),
                )
            )
        return results


class MysqlTaskStorage(TaskStorage):
    """MySQL 任务存储"""

    async def ensure_indexes(self):
        """创建表结构及索引"""
        pool = _mysql_conversation.pool

        await pool.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id VARCHAR(128) PRIMARY KEY,
                id VARCHAR(128) NOT NULL,
                user_id VARCHAR(128) NOT NULL,
                title VARCHAR(256) NOT NULL,
                description TEXT,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NULL,
                result JSON NULL,
                error_message TEXT,
                metadata JSON DEFAULT '{}'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                indexes = [
                    ("idx_tasks_id", "tasks", "id"),
                    ("idx_tasks_user_id", "tasks", "user_id"),
                    ("idx_tasks_status", "tasks", "status"),
                    ("idx_tasks_created_at", "tasks", "created_at"),
                ]
                for idx_name, table, column in indexes:
                    await cur.execute(
                        "SELECT 1 FROM information_schema.statistics "
                        "WHERE table_schema = DATABASE() "
                        "AND table_name = %s AND index_name = %s",
                        (table, idx_name),
                    )
                    if not await cur.fetchone():
                        order = "DESC" if column == "created_at" else ""
                        await cur.execute(
                            f"CREATE INDEX {idx_name} ON {table}({column}) {order}"
                        )

    async def save_task(self, task: TaskInfo) -> bool:
        """保存任务：不存在则创建，存在则更新"""
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT 1 FROM tasks WHERE task_id = %s", (task.task_id,)
                )
                existing = await cur.fetchone()

        if existing is None:
            return await self.create_task(task)
        else:
            return await self.update_task(task.task_id, task.dict())

    async def create_task(self, task: TaskInfo) -> bool:
        try:
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO tasks (
                            task_id, id, user_id, title, description,
                            status, created_at, updated_at, result, error_message, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            task.task_id,
                            task.id,
                            task.user_id,
                            task.title,
                            task.description,
                            task.status.value,
                            task.created_at,
                            task.updated_at,
                            _ensure_json(task.result) if task.result else None,
                            task.error_message,
                            _ensure_json(task.metadata),
                        ),
                    )
                    await conn.commit()
                    return True
        except Exception:
            return False

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        import json

        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM tasks WHERE task_id = %s", (task_id,)
                )
                row = await cur.fetchone()
                if not row:
                    return None
                for field in ("result", "metadata"):
                    if row.get(field) and isinstance(row[field], str):
                        row[field] = json.loads(row[field])
                return TaskInfo(
                    task_id=row["task_id"],
                    id=row["id"],
                    user_id=row["user_id"],
                    title=row["title"],
                    description=row.get("description"),
                    status=TaskStatus(row["status"]),
                    created_at=row["created_at"],
                    updated_at=row.get("updated_at"),
                    result=row.get("result"),
                    error_message=row.get("error_message"),
                    metadata=row.get("metadata") or {},
                )

    async def update_task(self, task_id: str, updates: dict) -> bool:
        try:
            set_clauses = []
            values = []
            for key, value in updates.items():
                if key in ("result", "metadata") and not isinstance(value, str):
                    value = _ensure_json(value)
                set_clauses.append(f"{key} = %s")
                values.append(value)

            values.append(task_id)

            query = f"""
                UPDATE tasks SET {', '.join(set_clauses)}
                WHERE task_id = %s
            """
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, values)
                    await conn.commit()
                    return cur.rowcount > 0
        except Exception:
            return False

    async def delete_task(self, task_id: str) -> bool:
        try:
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM tasks WHERE task_id = %s", (task_id,)
                    )
                    await conn.commit()
                    return cur.rowcount > 0
        except Exception:
            return False

    async def list_tasks_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TaskInfo]:
        return await self._fetch_tasks(
            "user", user_id, status, limit, offset
        )

    async def list_tasks_by_conversation(self, id: str) -> List[TaskInfo]:
        return await self._fetch_tasks("conversation", id)

    async def _fetch_tasks(self, by: str, value: str, status: Optional[str] = None, limit: int = 0, offset: int = 0) -> List[TaskInfo]:
        import json

        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if by == "user":
                    if status:
                        await cur.execute(
                            """
                            SELECT * FROM tasks
                            WHERE user_id = %s AND status = %s
                            ORDER BY created_at DESC
                            LIMIT %s OFFSET %s
                            """,
                            (value, status, limit, offset),
                        )
                    else:
                        await cur.execute(
                            """
                            SELECT * FROM tasks
                            WHERE user_id = %s
                            ORDER BY created_at DESC
                            LIMIT %s OFFSET %s
                            """,
                            (value, limit, offset),
                        )
                else:
                    await cur.execute(
                        """
                        SELECT * FROM tasks
                        WHERE id = %s
                        ORDER BY created_at DESC
                        """,
                        (value,),
                    )
                rows = await cur.fetchall()

        results = []
        for r in rows:
            for field in ("result", "metadata"):
                if r.get(field) and isinstance(r[field], str):
                    r[field] = json.loads(r[field])
            results.append(
                TaskInfo(
                    task_id=r["task_id"],
                    id=r["id"],
                    user_id=r["user_id"],
                    title=r["title"],
                    description=r.get("description"),
                    status=TaskStatus(r["status"]),
                    created_at=r["created_at"],
                    updated_at=r.get("updated_at"),
                    result=r.get("result"),
                    error_message=r.get("error_message"),
                    metadata=r.get("metadata") or {},
                )
            )
        return results


class MysqlAgentServerStorage(AgentServerStorage):
    """MySQL AgentServer 存储"""

    async def ensure_indexes(self):
        """创建表结构及索引"""
        pool = _mysql_conversation.pool

        await pool.execute("""
            CREATE TABLE IF NOT EXISTS agent_servers (
                server_id VARCHAR(128) PRIMARY KEY,
                host VARCHAR(256) NOT NULL,
                port INT NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'healthy',
                capabilities JSON DEFAULT '{}',
                metrics JSON DEFAULT '{}',
                last_heartbeat DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                registered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                version VARCHAR(64),
                tags JSON DEFAULT '[]'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                indexes = [
                    ("idx_agent_servers_status", "agent_servers", "status"),
                    ("idx_agent_servers_registered_at", "agent_servers", "registered_at"),
                ]
                for idx_name, table, column in indexes:
                    await cur.execute(
                        "SELECT 1 FROM information_schema.statistics "
                        "WHERE table_schema = DATABASE() "
                        "AND table_name = %s AND index_name = %s",
                        (table, idx_name),
                    )
                    if not await cur.fetchone():
                        await cur.execute(
                            f"CREATE INDEX {idx_name} ON {table}({column})"
                        )

    async def register_server(self, server: AgentServerInfo) -> bool:
        try:
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO agent_servers (
                            server_id, host, port, status, capabilities, metrics,
                            last_heartbeat, registered_at, version, tags
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    await conn.commit()
                    return True
        except Exception:
            return False

    async def deregister_server(self, server_id: str) -> bool:
        try:
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM agent_servers WHERE server_id = %s", (server_id,)
                    )
                    await conn.commit()
                    return cur.rowcount > 0
        except Exception:
            return False

    async def get_server(self, server_id: str) -> Optional[AgentServerInfo]:
        import json

        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM agent_servers WHERE server_id = %s", (server_id,)
                )
                row = await cur.fetchone()
                if not row:
                    return None
                for field in ("capabilities", "metrics", "tags"):
                    if row.get(field) and isinstance(row[field], str):
                        row[field] = json.loads(row[field])
                return AgentServerInfo(
                    server_id=row["server_id"],
                    host=row["host"],
                    port=row["port"],
                    status=ServerStatus(row["status"]),
                    capabilities=row.get("capabilities") or {},
                    metrics=row.get("metrics") or {},
                    last_heartbeat=row["last_heartbeat"],
                    registered_at=row["registered_at"],
                    version=row.get("version"),
                    tags=row.get("tags") or [],
                )

    async def update_server(self, server_id: str, updates: dict) -> bool:
        try:
            updates["last_heartbeat"] = datetime.utcnow()

            set_clauses = []
            values = []
            for key, value in updates.items():
                if key in ("capabilities", "metrics", "tags") and not isinstance(value, str):
                    value = _ensure_json(value)
                set_clauses.append(f"{key} = %s")
                values.append(value)

            values.append(server_id)

            query = f"""
                UPDATE agent_servers SET {', '.join(set_clauses)}
                WHERE server_id = %s
            """
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, values)
                    await conn.commit()
                    return cur.rowcount > 0
        except Exception:
            return False

    async def list_healthy_servers(self) -> List[AgentServerInfo]:
        return await self._fetch_servers("status = 'healthy'")

    async def list_all_servers(self) -> List[AgentServerInfo]:
        return await self._fetch_servers("1=1")

    async def _fetch_servers(self, where_clause: str) -> List[AgentServerInfo]:
        import json

        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"""
                    SELECT * FROM agent_servers
                    WHERE {where_clause}
                    ORDER BY registered_at ASC
                    """
                )
                rows = await cur.fetchall()

        results = []
        for r in rows:
            for field in ("capabilities", "metrics", "tags"):
                if r.get(field) and isinstance(r[field], str):
                    r[field] = json.loads(r[field])
            results.append(
                AgentServerInfo(
                    server_id=r["server_id"],
                    host=r["host"],
                    port=r["port"],
                    status=ServerStatus(r["status"]),
                    capabilities=r.get("capabilities") or {},
                    metrics=r.get("metrics") or {},
                    last_heartbeat=r["last_heartbeat"],
                    registered_at=r["registered_at"],
                    version=r.get("version"),
                    tags=r.get("tags") or [],
                )
            )
        return results


class MysqlUserStorage(UserStorage):
    """MySQL user storage for authentication"""

    async def ensure_indexes(self) -> None:
        # Step 1: create table (plain cursor is fine for DDL)
        async with _pool.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    '''
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
                    '''
                )
        # Step 2: conditionally create indexes (DictCursor for row['cnt'])
        async with _pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                for idx_name, table, col in [
                    ('idx_users_username', 'users', 'username'),
                    ('idx_users_email',    'users', 'email'),
                ]:
                    await cur.execute(
                        f'''
                        SELECT COUNT(*) AS cnt
                        FROM information_schema.statistics
                        WHERE table_schema = DATABASE()
                          AND table_name = \'{table}\'
                          AND index_name = \'{idx_name}\'
                        '''
                    )
                    row = await cur.fetchone()
                    if row['cnt'] == 0:
                        await cur.execute(
                            f'CREATE INDEX {idx_name} ON {table} ({col})'
                        )

    async def create_user(self, user: AuthUser) -> bool:
        try:
            async with _pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        '''
                        INSERT INTO users
                            (user_id, username, email, password_hash, is_active, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''',
                        (
                            user.user_id, user.username, user.email,
                            user.password_hash, int(user.is_active),
                            user.created_at, user.updated_at,
                        ),
                    )
            return True
        except Exception:
            return False

    async def _row_to_user(self, row) -> AuthUser:
        return AuthUser(
            user_id=row['user_id'],
            username=row['username'],
            email=row['email'],
            password_hash=row['password_hash'],
            is_active=bool(row['is_active']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )

    async def get_user_by_id(self, user_id: str):
        async with _pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    'SELECT * FROM users WHERE user_id = %s LIMIT 1', (user_id,)
                )
                row = await cur.fetchone()
        return await self._row_to_user(row) if row else None

    async def get_user_by_username(self, username: str):
        async with _pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    'SELECT * FROM users WHERE username = %s LIMIT 1', (username,)
                )
                row = await cur.fetchone()
        return await self._row_to_user(row) if row else None

    async def get_user_by_email(self, email: str):
        async with _pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    'SELECT * FROM users WHERE email = %s LIMIT 1', (email,)
                )
                row = await cur.fetchone()
        return await self._row_to_user(row) if row else None

    async def update_user(self, user_id: str, updates: dict) -> bool:
        if not updates:
            return True
        allowed = {'username', 'email', 'password_hash', 'is_active', 'updated_at'}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return False
        set_clause = ', '.join(f'{k} = %s' for k in filtered)
        values = list(filtered.values()) + [user_id]
        async with _pool.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f'UPDATE users SET {set_clause} WHERE user_id = %s',
                    values,
                )
                return cur.rowcount > 0
