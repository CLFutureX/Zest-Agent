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

from app.core.storage.base import (
    AppConversationStorage,
    TaskStorage,
    UserStorage,
    UserLlmConfigStorage,
    SkillProfileStorage,
    PromptConfigStorage,
    SubAgentConfigStorage,
)
from app.core.models import (
    AppConversationInfo,
    TaskInfo,
    AgentServerInfo,
    TaskStatus,
    ServerStatus,
    AuthUser,
    UserLlmConfig,
    SkillProfile,
    PromptConfig,
    SubAgentConfig,
)
from app.config.settings import get_cipher


def _cipher_ctx() -> dict:
    cipher = get_cipher()
    return {"cipher": cipher} if cipher is not None else {}


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
                            id, user_id,
                            created_at, updated_at, started_at, metadata, error_message
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
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


class MysqlUserStorage(UserStorage):
    """MySQL user storage for authentication"""

    async def ensure_indexes(self) -> None:
        # Step 1: create table (plain cursor is fine for DDL)
        async with _mysql_conversation.pool.acquire() as conn:
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
        async with _mysql_conversation.pool.acquire() as conn:
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
            async with _mysql_conversation.pool.acquire() as conn:
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
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    'SELECT * FROM users WHERE user_id = %s LIMIT 1', (user_id,)
                )
                row = await cur.fetchone()
        return await self._row_to_user(row) if row else None

    async def get_user_by_username(self, username: str):
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    'SELECT * FROM users WHERE username = %s LIMIT 1', (username,)
                )
                row = await cur.fetchone()
        return await self._row_to_user(row) if row else None

    async def get_user_by_email(self, email: str):
        async with _mysql_conversation.pool.acquire() as conn:
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
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f'UPDATE users SET {set_clause} WHERE user_id = %s',
                    values,
                )
                return cur.rowcount > 0


class MysqlUserLlmConfigStorage(UserLlmConfigStorage):
    """MySQL 用户 LLM 配置存储。api_key 通过 cipher 加密后存为 VARCHAR。"""

    async def ensure_indexes(self) -> None:
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_llm_configs (
                        id VARCHAR(128) PRIMARY KEY,
                        user_id VARCHAR(128) NOT NULL,
                        usage_id VARCHAR(128) NOT NULL,
                        model VARCHAR(256) NOT NULL,
                        api_key VARCHAR(1024) NOT NULL,
                        base_url VARCHAR(512) NULL,
                        INDEX idx_user_llm_configs_user_id (user_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    async def create_llm_config(self, config: UserLlmConfig) -> bool:
        try:
            dumped = config.model_dump(context=_cipher_ctx())
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO user_llm_configs
                            (id, user_id, usage_id, model, api_key, base_url)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            user_id = VALUES(user_id),
                            usage_id = VALUES(usage_id),
                            model = VALUES(model),
                            api_key = VALUES(api_key),
                            base_url = VALUES(base_url)
                        """,
                        (
                            dumped["id"],
                            dumped["user_id"],
                            dumped["usage_id"],
                            dumped["model"],
                            dumped["api_key"],
                            dumped.get("base_url"),
                        ),
                    )
            return True
        except Exception:
            return False

    async def get_llm_config(self, config_id: str) -> Optional[UserLlmConfig]:
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, user_id, usage_id, model, api_key, base_url "
                    "FROM user_llm_configs WHERE id = %s LIMIT 1",
                    (config_id,),
                )
                row = await cur.fetchone()
        if not row:
            return None
        return UserLlmConfig.model_validate(dict(row), context=_cipher_ctx())

    async def list_llm_configs_by_user(self, user_id: str) -> List[UserLlmConfig]:
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, user_id, usage_id, model, api_key, base_url "
                    "FROM user_llm_configs WHERE user_id = %s",
                    (user_id,),
                )
                rows = await cur.fetchall()
        return [
            UserLlmConfig.model_validate(dict(r), context=_cipher_ctx()) for r in rows
        ]


class MysqlSkillProfileStorage(SkillProfileStorage):
    """MySQL 技能定义存储。"""

    async def ensure_indexes(self) -> None:
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS skill_profiles (
                        id VARCHAR(128) PRIMARY KEY,
                        user_id VARCHAR(128) NOT NULL,
                        name VARCHAR(256) NOT NULL,
                        content TEXT NOT NULL,
                        description TEXT NULL,
                        source VARCHAR(256) NULL,
                        trigger_config JSON NULL,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        INDEX idx_skill_profiles_user_id (user_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    async def create_skill(self, skill: SkillProfile) -> bool:
        try:
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO skill_profiles
                            (id, user_id, name, content, description, source, trigger_config, enabled)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            user_id = VALUES(user_id),
                            name = VALUES(name),
                            content = VALUES(content),
                            description = VALUES(description),
                            source = VALUES(source),
                            trigger_config = VALUES(trigger_config),
                            enabled = VALUES(enabled)
                        """,
                        (
                            skill.id,
                            skill.user_id,
                            skill.name,
                            skill.content,
                            skill.description,
                            skill.source,
                            _ensure_json(skill.trigger) if skill.trigger else None,
                            int(skill.enabled),
                        ),
                    )
            return True
        except Exception:
            return False

    async def get_skill(self, skill_id: str) -> Optional[SkillProfile]:
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, user_id, name, content, description, source, trigger_config, enabled "
                    "FROM skill_profiles WHERE id = %s LIMIT 1",
                    (skill_id,),
                )
                row = await cur.fetchone()
        if not row:
            return None
        data = dict(row)
        if isinstance(data.get("trigger_config"), str):
            import json as _json
            data["trigger_config"] = _json.loads(data["trigger_config"])
        data["trigger"] = data.pop("trigger_config")
        data["enabled"] = bool(data["enabled"])
        return SkillProfile(**data)

    async def update_skill(self, skill_id: str, updates: dict) -> bool:
        if not updates:
            return False
        if "trigger" in updates and not isinstance(updates["trigger"], str):
            updates = {**updates, "trigger_config": _ensure_json(updates["trigger"])}
            updates.pop("trigger", None)
        if "enabled" in updates:
            updates["enabled"] = int(bool(updates["enabled"]))
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [skill_id]
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"UPDATE skill_profiles SET {set_clause} WHERE id = %s",
                    values,
                )
                return cur.rowcount > 0

    async def list_skills_by_user(
        self, user_id: str, enabled: Optional[bool] = None
    ) -> List[SkillProfile]:
        query = (
            "SELECT id, user_id, name, content, description, source, trigger_config, enabled "
            "FROM skill_profiles WHERE user_id = %s"
        )
        params: list = [user_id]
        if enabled is not None:
            query += " AND enabled = %s"
            params.append(int(enabled))
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
        results = []
        for r in rows:
            data = dict(r)
            if isinstance(data.get("trigger_config"), str):
                import json as _json
                data["trigger_config"] = _json.loads(data["trigger_config"])
            data["trigger"] = data.pop("trigger_config")
            data["enabled"] = bool(data["enabled"])
            results.append(SkillProfile(**data))
        return results


class MysqlPromptConfigStorage(PromptConfigStorage):
    """MySQL 提示词配置存储。"""

    async def ensure_indexes(self) -> None:
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS prompt_configs (
                        id VARCHAR(128) PRIMARY KEY,
                        user_id VARCHAR(128) NOT NULL,
                        name VARCHAR(256) NOT NULL,
                        content TEXT NOT NULL,
                        description TEXT NULL,
                        source VARCHAR(256) NULL,
                        trigger_config JSON NULL,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        INDEX idx_prompt_configs_user_id (user_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    async def create_prompt(self, prompt: PromptConfig) -> bool:
        try:
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO prompt_configs
                            (id, user_id, name, content, description, source, trigger_config, enabled)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            user_id = VALUES(user_id),
                            name = VALUES(name),
                            content = VALUES(content),
                            description = VALUES(description),
                            source = VALUES(source),
                            trigger_config = VALUES(trigger_config),
                            enabled = VALUES(enabled)
                        """,
                        (
                            prompt.id,
                            prompt.user_id,
                            prompt.name,
                            prompt.content,
                            prompt.description,
                            prompt.source,
                            _ensure_json(prompt.trigger) if prompt.trigger else None,
                            int(prompt.enabled),
                        ),
                    )
            return True
        except Exception:
            return False

    async def get_prompt(self, prompt_id: str) -> Optional[PromptConfig]:
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, user_id, name, content, description, source, trigger_config, enabled "
                    "FROM prompt_configs WHERE id = %s LIMIT 1",
                    (prompt_id,),
                )
                row = await cur.fetchone()
        if not row:
            return None
        data = dict(row)
        if isinstance(data.get("trigger_config"), str):
            import json as _json
            data["trigger_config"] = _json.loads(data["trigger_config"])
        data["trigger"] = data.pop("trigger_config")
        data["enabled"] = bool(data["enabled"])
        return PromptConfig(**data)

    async def update_prompt(self, prompt_id: str, updates: dict) -> bool:
        if not updates:
            return False
        if "trigger" in updates and not isinstance(updates["trigger"], str):
            updates = {**updates, "trigger_config": _ensure_json(updates["trigger"])}
            updates.pop("trigger", None)
        if "enabled" in updates:
            updates["enabled"] = int(bool(updates["enabled"]))
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [prompt_id]
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"UPDATE prompt_configs SET {set_clause} WHERE id = %s",
                    values,
                )
                return cur.rowcount > 0

    async def list_prompts_by_user(
        self, user_id: str, enabled: Optional[bool] = None
    ) -> List[PromptConfig]:
        query = (
            "SELECT id, user_id, name, content, description, source, trigger_config, enabled "
            "FROM prompt_configs WHERE user_id = %s"
        )
        params: list = [user_id]
        if enabled is not None:
            query += " AND enabled = %s"
            params.append(int(enabled))
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
        results = []
        for r in rows:
            data = dict(r)
            if isinstance(data.get("trigger_config"), str):
                import json as _json
                data["trigger_config"] = _json.loads(data["trigger_config"])
            data["trigger"] = data.pop("trigger_config")
            data["enabled"] = bool(data["enabled"])
            results.append(PromptConfig(**data))
        return results


class MysqlSubAgentConfigStorage(SubAgentConfigStorage):
    """MySQL 子 Agent 配置存储。"""

    async def ensure_indexes(self) -> None:
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS subagent_configs (
                        id VARCHAR(128) PRIMARY KEY,
                        user_id VARCHAR(128) NOT NULL,
                        name VARCHAR(256) NOT NULL,
                        model VARCHAR(256) NULL,
                        selected_tool_names JSON NULL,
                        description TEXT NULL,
                        custom_system_prompt TEXT NULL,
                        system_prompt_filename VARCHAR(512) NULL,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        config JSON NULL,
                        INDEX idx_subagent_configs_user_id (user_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    async def create_subagent_config(self, config: SubAgentConfig) -> bool:
        try:
            async with _mysql_conversation.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO subagent_configs
                            (id, user_id, name, model, selected_tool_names,
                             description, custom_system_prompt, system_prompt_filename,
                             enabled, config)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            user_id = VALUES(user_id),
                            name = VALUES(name),
                            model = VALUES(model),
                            selected_tool_names = VALUES(selected_tool_names),
                            description = VALUES(description),
                            custom_system_prompt = VALUES(custom_system_prompt),
                            system_prompt_filename = VALUES(system_prompt_filename),
                            enabled = VALUES(enabled),
                            config = VALUES(config)
                        """,
                        (
                            config.id,
                            config.user_id,
                            config.name,
                            config.model,
                            _ensure_json(config.selected_tool_names),
                            config.description,
                            config.custom_system_prompt,
                            config.system_prompt_filename,
                            int(config.enabled),
                            _ensure_json(config.config),
                        ),
                    )
            return True
        except Exception:
            return False

    async def get_subagent_config(self, config_id: str) -> Optional[SubAgentConfig]:
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, user_id, name, model, selected_tool_names, description, "
                    "custom_system_prompt, system_prompt_filename, enabled, config "
                    "FROM subagent_configs WHERE id = %s LIMIT 1",
                    (config_id,),
                )
                row = await cur.fetchone()
        if not row:
            return None
        data = dict(row)
        for k in ("selected_tool_names", "config"):
            if isinstance(data.get(k), str):
                import json as _json
                data[k] = _json.loads(data[k])
        data["enabled"] = bool(data["enabled"])
        return SubAgentConfig(**data)

    async def update_subagent_config(self, config_id: str, updates: dict) -> bool:
        if not updates:
            return False
        for k in ("selected_tool_names", "config"):
            if k in updates and not isinstance(updates[k], str):
                updates[k] = _ensure_json(updates[k])
        if "enabled" in updates:
            updates["enabled"] = int(bool(updates["enabled"]))
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [config_id]
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"UPDATE subagent_configs SET {set_clause} WHERE id = %s",
                    values,
                )
                return cur.rowcount > 0

    async def list_subagent_configs_by_user(
        self, user_id: str, enabled: Optional[bool] = None
    ) -> List[SubAgentConfig]:
        query = (
            "SELECT id, user_id, name, model, selected_tool_names, description, "
            "custom_system_prompt, system_prompt_filename, enabled, config "
            "FROM subagent_configs WHERE user_id = %s"
        )
        params: list = [user_id]
        if enabled is not None:
            query += " AND enabled = %s"
            params.append(int(enabled))
        async with _mysql_conversation.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
        results = []
        for r in rows:
            data = dict(r)
            for k in ("selected_tool_names", "config"):
                if isinstance(data.get(k), str):
                    import json as _json
                    data[k] = _json.loads(data[k])
            data["enabled"] = bool(data["enabled"])
            results.append(SubAgentConfig(**data))
        return results
