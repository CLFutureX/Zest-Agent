"""
统一序列化层
- 所有 storage backend 共用同一序列化接口，确保 cipher context 在 Local/MySQL 两种模式下行为一致。
- PydanticJsonSerializer 用于 LocalFile（文件内是 JSON 文本）。
- MysqlRowSerializer 用于 MySQL（行字典 + JSON 列解析）。

cipher 来自 settings.get_cipher()；若未配置 ZEST_SECRET_KEY 返回 None，
此时 SecretStr 字段以明文存储，与原行为一致。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from app.config.settings import get_cipher
from common.utils.cipher import Cipher

T = TypeVar("T", bound=BaseModel)


def _cipher() -> Optional[Cipher]:
    return get_cipher()


class ResourceSerializer:
    """资源序列化器基类。子类按存储格式实现 to_store / from_store。"""

    def to_store(self, item: BaseModel) -> Any:
        raise NotImplementedError

    def from_store(self, raw: Any, model_cls: Type[T]) -> Optional[T]:
        raise NotImplementedError


class PydanticJsonSerializer(ResourceSerializer):
    """Local 文件用：JSON 文本。cipher context 走 model_dump_json/model_validate。"""

    def to_store(self, item: BaseModel) -> str:
        return item.model_dump_json(context={"cipher": _cipher()})

    def from_store(self, raw: Any, model_cls: Type[T]) -> Optional[T]:
        if not raw:
            return None
        if isinstance(raw, str):
            data = json.loads(raw)
        elif isinstance(raw, dict):
            data = raw
        else:
            return None
        return model_cls.model_validate(data, context={"cipher": _cipher()})


class MysqlRowSerializer(ResourceSerializer):
    """MySQL 用：行字典，JSON 列字段会被驱动自动解析为 dict。

    子类可通过 ``JSON_FIELDS`` 声明需要 json.loads 兜底的列名。
    """

    JSON_FIELDS: set[str] = set()

    def to_store(self, item: BaseModel) -> dict:
        return item.model_dump(context={"cipher": _cipher()})

    def from_store(self, raw: Any, model_cls: Type[T]) -> Optional[T]:
        if not raw or not isinstance(raw, dict):
            return None
        for field in self.JSON_FIELDS:
            val = raw.get(field)
            if isinstance(val, str) and val:
                try:
                    raw[field] = json.loads(val)
                except (ValueError, TypeError):
                    pass
        return model_cls.model_validate(raw, context={"cipher": _cipher()})


def json_default(obj: Any) -> Any:
    """JSON 序列化兜底：datetime 等。"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
