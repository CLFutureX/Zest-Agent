"""
MySQL 资源 storage 泛型实现
4 个资源（llm_config / skill / prompt / subagent）共用一份代码。

设计要点：
- 复用全局 _mysql_pool（与运行时 storage 同库同连接池）。
- 表 schema 由 _ensure_table 在 ensure_indexes 时按 model_cls 选择创建。
- create 用 INSERT ... ON DUPLICATE KEY UPDATE 实现 upsert 语义（与原 Mongo $setOnInsert 行为一致）。
- update 字段做白名单（model_cls 字段名）+ 过滤不可改字段（id / user_id）。
- JSON 列字段在 aiomysql + autocommit 下通常已自动解析，但保留 json.loads 兜底。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

import aiomysql
from pydantic import BaseModel

from app.core.storage.base import ResourceStorage
from app.core.storage.mysql import _ensure_index, _index_exists, _json_default, _maybe_loads, _mysql_pool
from app.core.storage.serializer import MysqlRowSerializer
import json

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# 各资源表 schema 声明（model_cls → (table, columns, json_fields, unique_idx)）
# columns: dict[field_name, SQL DDL] —— 字段顺序与 create INSERT 顺序一致
_RESOURCE_SCHEMAS: Dict[Type[Any], Dict[str, Any]] = {}


def register_resource_schema(
    model_cls: Type[Any],
    table: str,
    columns: Dict[str, str],
    json_fields: set[str],
    extra_indexes: Optional[List[tuple]] = None,
) -> None:
    """声明某资源模型的 MySQL 表结构。

    extra_indexes: [(idx_name, column, desc?), ...]
    """
    _RESOURCE_SCHEMAS[model_cls] = {
        "table": table,
        "columns": columns,
        "json_fields": json_fields,
        "extra_indexes": extra_indexes or [],
    }


def _ensure_json_str(value: Any) -> Any:
    """把 dict/list 序列化为 JSON 字符串以便存入 JSON 列；其它类型原样返回。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, default=_json_default, ensure_ascii=False)


class MysqlResourceSerializer(MysqlRowSerializer):
    """按 model_cls 声明的 JSON_FIELDS 解析行字典。"""

    def __init__(self, json_fields: set[str]) -> None:
        self.JSON_FIELDS = json_fields


class MysqlResourceStorage(ResourceStorage[T], Generic[T]):
    """MySQL 资源 storage 泛型实现。"""

    def __init__(self, model_cls: Type[T], collection: str) -> None:
        self.model_cls = model_cls
        self.collection = collection  # 即表名
        schema = _RESOURCE_SCHEMAS.get(model_cls)
        if schema is None:
            raise ValueError(f"No schema registered for {model_cls.__name__}")
        if schema["table"] != collection:
            raise ValueError(
                f"Collection name mismatch: {collection} vs registered {schema['table']}"
            )
        self._columns: Dict[str, str] = schema["columns"]
        self._json_fields: set[str] = schema["json_fields"]
        self._extra_indexes: List[tuple] = schema["extra_indexes"]
        self._serializer = MysqlResourceSerializer(self._json_fields)

    @property
    def _column_names(self) -> List[str]:
        return list(self._columns.keys())

    async def ensure_indexes(self) -> None:
        col_defs = ", ".join(f"{name} {ddl}" for name, ddl in self._columns.items())
        table = self.collection
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} ({col_defs}) "
                    f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                )
                await self._ensure_columns(cur, table)
                for idx_name, column, *rest in self._extra_indexes:
                    desc = bool(rest and rest[0])
                    await _ensure_index(cur, table, idx_name, column, desc=desc)

    async def _ensure_columns(self, cur, table: str) -> None:
        """自愈迁移：CREATE TABLE IF NOT EXISTS 不会给存量表加新列。
        对照声明的 columns，缺失的用 ALTER TABLE ADD COLUMN 补齐（幂等）。"""
        await cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            (table,),
        )
        existing = {row[0] for row in await cur.fetchall()}
        for name, ddl in self._columns.items():
            if name not in existing:
                await cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    async def create(self, item: T) -> bool:
        cols = self._column_names
        doc = self._serializer.to_store(item)
        values = []
        for col in cols:
            v = doc.get(col)
            if col in self._json_fields and not isinstance(v, str) and v is not None:
                v = _ensure_json_str(v)
            values.append(v)
        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(cols)
        # upsert：主键冲突时更新非主键字段
        update_cols = [c for c in cols if c not in (self.id_field,)]
        update_clause = ", ".join(f"{c}=VALUES({c})" for c in update_cols)
        query = (
            f"INSERT INTO {self.collection} ({col_list}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_clause}"
        )
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, values)
                    return True
        except Exception:
            logger.exception("create %s failed", self.collection)
            return False

    async def get(self, item_id: str) -> Optional[T]:
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"SELECT * FROM {self.collection} WHERE {self.id_field} = %s LIMIT 1",
                    (item_id,),
                )
                row = await cur.fetchone()
        if not row:
            return None
        return self._serializer.from_store(row, self.model_cls)

    async def update(self, item_id: str, updates: dict) -> bool:
        # 白名单：只允许更新 model_cls 中声明且非主键的字段
        allowed = {c for c in self._column_names if c not in (self.id_field, self.user_field)}
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return False
        filtered.setdefault("updated_at", datetime.utcnow())
        set_clauses = []
        values = []
        for key, value in filtered.items():
            if key in self._json_fields and not isinstance(value, str) and value is not None:
                value = _ensure_json_str(value)
            set_clauses.append(f"{key} = %s")
            values.append(value)
        values.append(item_id)
        query = f"UPDATE {self.collection} SET {', '.join(set_clauses)} WHERE {self.id_field} = %s"
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, values)
                    return cur.rowcount > 0
        except Exception:
            logger.exception("update %s failed", self.collection)
            return False

    async def delete(self, item_id: str) -> bool:
        try:
            async with _mysql_pool.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"DELETE FROM {self.collection} WHERE {self.id_field} = %s",
                        (item_id,),
                    )
                    return cur.rowcount > 0
        except Exception:
            logger.exception("delete %s failed", self.collection)
            return False

    async def list_by_user(
        self,
        user_id: str,
        filters: Optional[Dict] = None,
    ) -> List[T]:
        where = [f"{self.user_field} = %s"]
        values: List[Any] = [user_id]
        if filters:
            for k, v in filters.items():
                if k not in self._column_names:
                    continue
                where.append(f"{k} = %s")
                values.append(v)
        sql = f"SELECT * FROM {self.collection} WHERE {' AND '.join(where)} ORDER BY created_at DESC"
        async with _mysql_pool.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, values)
                rows = await cur.fetchall()
        return [self._serializer.from_store(r, self.model_cls) for r in rows if r]


# ==============================
# 4 个资源表 schema 注册
# ==============================
from app.core.models import (  # noqa: E402
    PromptConfig,
    SkillProfile,
    SubAgentConfig,
    UserLlmConfig,
    MemorySettings,
)

register_resource_schema(
    UserLlmConfig,
    table="user_llm_configs",
    columns={
        "id": "VARCHAR(128) NOT NULL PRIMARY KEY",
        "user_id": "VARCHAR(128) NOT NULL",
        "usage_id": "VARCHAR(128) NOT NULL",
        "model": "VARCHAR(128) NOT NULL",
        "api_key": "VARCHAR(512) NOT NULL",
        "base_url": "VARCHAR(256) NULL",
        "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    json_fields=set(),
    extra_indexes=[("idx_llm_user_id", "user_id", False)],
)

register_resource_schema(
    SkillProfile,
    table="skill_definitions",
    columns={
        "id": "VARCHAR(128) NOT NULL PRIMARY KEY",
        "user_id": "VARCHAR(128) NOT NULL",
        "name": "VARCHAR(256) NOT NULL",
        "content": "TEXT NOT NULL",
        "description": "TEXT NULL",
        "source": "VARCHAR(256) NULL",
        "trigger": "JSON NULL",
        "enabled": "TINYINT(1) NOT NULL DEFAULT 1",
        "bundle_type": "VARCHAR(16) NULL",
        "oss_key": "VARCHAR(512) NULL",
        "content_hash": "VARCHAR(64) NULL",
        "version": "VARCHAR(64) NULL",
        "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    json_fields={"trigger"},
    extra_indexes=[("idx_skill_user_id", "user_id", False)],
)

register_resource_schema(
    PromptConfig,
    table="prompt_configs",
    columns={
        "id": "VARCHAR(128) NOT NULL PRIMARY KEY",
        "user_id": "VARCHAR(128) NOT NULL",
        "name": "VARCHAR(256) NOT NULL",
        "content": "TEXT NOT NULL",
        "description": "TEXT NULL",
        "source": "VARCHAR(256) NULL",
        "trigger": "JSON NULL",
        "enabled": "TINYINT(1) NOT NULL DEFAULT 1",
        "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    json_fields={"trigger"},
    extra_indexes=[("idx_prompt_user_id", "user_id", False)],
)

register_resource_schema(
    SubAgentConfig,
    table="subagent_configs",
    columns={
        "id": "VARCHAR(128) NOT NULL PRIMARY KEY",
        "user_id": "VARCHAR(128) NOT NULL",
        "name": "VARCHAR(256) NOT NULL",
        "model": "VARCHAR(128) NULL",
        "selected_tool_names": "JSON DEFAULT '[]'",
        "description": "TEXT NULL",
        "custom_system_prompt": "TEXT NULL",
        "system_prompt_filename": "VARCHAR(256) NULL",
        "enabled": "TINYINT(1) NOT NULL DEFAULT 1",
        "config": "JSON DEFAULT '{}'",
        "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    json_fields={"selected_tool_names", "config"},
    extra_indexes=[("idx_subagent_user_id", "user_id", False)],
)
