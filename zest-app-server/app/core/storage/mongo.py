"""Mongo storage implementations for agent config resources."""

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.settings import settings, get_cipher
from app.core.models import PromptConfig, SkillProfile, SubAgentConfig, UserLlmConfig
from app.core.storage.base import (
    PromptConfigStorage,
    SkillProfileStorage,
    SubAgentConfigStorage,
    UserLlmConfigStorage,
)
from common.storage.event_log.event_store import get_motor_client
from common.utils.cipher import Cipher


class _MongoConfigStorage:
    """motor 配置类存储基类：复用模块级 AsyncIOMotorClient 单例，避免每次创建新连接池。"""

    def __init__(self, database: Optional[AsyncIOMotorDatabase] = None):
        self._database = database

    @property
    def database(self) -> AsyncIOMotorDatabase:
        if self._database is None:
            client = get_motor_client(settings.mongo_url, namespace="app-config")
            self._database = client[settings.mongo_database]
        return self._database


class MongoUserLlmConfigStorage(_MongoConfigStorage, UserLlmConfigStorage):
    COLLECTION = "user_llm_configs"

    async def ensure_indexes(self) -> None:
        await self.database[self.COLLECTION].create_index([("user_id", 1)])

    async def create_llm_config(self, config: UserLlmConfig) -> bool:
        result = await self.database[self.COLLECTION].update_one(
            {"id": config.id},
            {"$setOnInsert": config.model_dump(context={"cipher": get_cipher()})},
            upsert=True,
        )
        return bool(result.upserted_id) or result.matched_count > 0

    async def get_llm_config(self, config_id: str) -> Optional[UserLlmConfig]:
        doc = await self.database[self.COLLECTION].find_one({"id": config_id}, {"_id": 0})
        return UserLlmConfig.model_validate(doc, context={"cipher": get_cipher()}) if doc else None

    async def list_llm_configs_by_user(self, user_id: str) -> list[UserLlmConfig]:
        cursor = self.database[self.COLLECTION].find({"user_id": user_id}, {"_id": 0})
        return [UserLlmConfig.model_validate(doc, context={"cipher": get_cipher()}) async for doc in cursor]


class MongoSkillProfileStorage(_MongoConfigStorage, SkillProfileStorage):
    COLLECTION = "skill_definitions"

    async def ensure_indexes(self) -> None:
        await self.database[self.COLLECTION].create_index([("user_id", 1)])

    async def create_skill(self, skill: SkillProfile) -> bool:
        result = await self.database[self.COLLECTION].update_one(
            {"id": skill.id},
            {"$setOnInsert": skill.model_dump()},
            upsert=True,
        )
        return bool(result.upserted_id) or result.matched_count > 0

    async def get_skill(self, skill_id: str) -> Optional[SkillProfile]:

        doc = await self.database[self.COLLECTION].find_one({"id": skill_id}, {"_id": 0})

        return SkillProfile(**doc) if doc else None



    async def update_skill(self, skill_id: str, updates: dict) -> bool:

        result = await self.database[self.COLLECTION].update_one(
            {"id": skill_id},
            {"$set": updates},
        )

        return result.modified_count > 0 or result.matched_count > 0



    async def list_skills_by_user(self, user_id: str, enabled: Optional[bool] = None) -> list[SkillProfile]:

        query: dict[str, object] = {"user_id": user_id}

        if enabled is not None:

            query["enabled"] = enabled

        cursor = self.database[self.COLLECTION].find(query, {"_id": 0})

        return [SkillProfile(**doc) async for doc in cursor]





class MongoPromptConfigStorage(_MongoConfigStorage, PromptConfigStorage):

    COLLECTION = "prompt_configs"



    async def ensure_indexes(self) -> None:

        await self.database[self.COLLECTION].create_index([("user_id", 1)])



    async def create_prompt(self, prompt: PromptConfig) -> bool:

        result = await self.database[self.COLLECTION].update_one(

            {"id": prompt.id},

            {"$setOnInsert": prompt.model_dump()},

            upsert=True,

        )

        return bool(result.upserted_id) or result.matched_count > 0



    async def get_prompt(self, prompt_id: str) -> Optional[PromptConfig]:

        doc = await self.database[self.COLLECTION].find_one({"id": prompt_id}, {"_id": 0})

        return PromptConfig(**doc) if doc else None



    async def update_prompt(self, prompt_id: str, updates: dict) -> bool:

        result = await self.database[self.COLLECTION].update_one(
            {"id": prompt_id},
            {"$set": updates},
        )

        return result.modified_count > 0 or result.matched_count > 0



    async def list_prompts_by_user(self, user_id: str, enabled: Optional[bool] = None) -> list[PromptConfig]:

        query: dict[str, object] = {"user_id": user_id}

        if enabled is not None:

            query["enabled"] = enabled

        cursor = self.database[self.COLLECTION].find(query, {"_id": 0})

        return [PromptConfig(**doc) async for doc in cursor]


class MongoSubAgentConfigStorage(_MongoConfigStorage, SubAgentConfigStorage):
    COLLECTION = "subagent_configs"

    async def ensure_indexes(self) -> None:
        await self.database[self.COLLECTION].create_index([("user_id", 1)])

    async def create_subagent_config(self, config: SubAgentConfig) -> bool:
        result = await self.database[self.COLLECTION].update_one(
            {"id": config.id},
            {"$setOnInsert": config.model_dump()},
            upsert=True,
        )
        return bool(result.upserted_id) or result.matched_count > 0

    async def get_subagent_config(self, config_id: str) -> Optional[SubAgentConfig]:

        doc = await self.database[self.COLLECTION].find_one({"id": config_id}, {"_id": 0})

        return SubAgentConfig(**doc) if doc else None



    async def update_subagent_config(self, config_id: str, updates: dict) -> bool:

        result = await self.database[self.COLLECTION].update_one(
            {"id": config_id},
            {"$set": updates},
        )

        return result.modified_count > 0 or result.matched_count > 0



    async def list_subagent_configs_by_user(

        self,

        user_id: str,

        enabled: Optional[bool] = None,

    ) -> list[SubAgentConfig]:

        query: dict[str, object] = {"user_id": user_id}

        if enabled is not None:

            query["enabled"] = enabled

        cursor = self.database[self.COLLECTION].find(query, {"_id": 0})

        return [SubAgentConfig(**doc) async for doc in cursor]
