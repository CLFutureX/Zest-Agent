"""MongoDB经验数据存储模块"""

import logging
from datetime import datetime
from typing import Any


logger = logging.getLogger(__name__)


class MongoDBExperienceStore:
    """MongoDB经验数据存储"""

    def __init__(self, mongodb_url: str, db_name: str = "agent_memory"):
        """
        初始化MongoDB存储

        Args:
            mongodb_url: MongoDB连接URL
            db_name: 数据库名称
        """
        try:
            from pymongo import MongoClient

            self.client = MongoClient(mongodb_url)
            self.db = self.client[db_name]
            self.collection = self.db.agent_experiences
            self._create_indexes()
            logger.info(f"MongoDB连接成功: {mongodb_url}")
        except Exception as e:
            logger.error(f"MongoDB连接失败: {e}")
            raise

    def save_experience(
        self,
        content: str,
        keywords: list[str],
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        保存经验数据

        Args:
            content: 经验内容
            keywords: 关键字列表
            description: 描述
            metadata: 元数据

        Returns:
            经验ID
        """
        doc = {
            "content": content,
            "keywords": keywords,
            "description": description,
            "metadata": metadata or {},
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "is_active": True,
        }

        try:
            result = self.collection.insert_one(doc)
            experience_id = str(result.inserted_id)
            logger.info(f"经验数据已保存: {experience_id}")
            return experience_id
        except Exception as e:
            logger.error(f"保存经验数据失败: {e}")
            raise

    def retrieve_experience(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        检索经验数据

        Args:
            query: 查询字符串
            limit: 返回数量限制

        Returns:
            经验数据列表
        """
        try:
            results = list(
                self.collection.find(
                    {
                        "$or": [
                            {"keywords": {"$regex": query, "$options": "i"}},
                            {"content": {"$regex": query, "$options": "i"}},
                            {"description": {"$regex": query, "$options": "i"}},
                        ],
                        "is_active": True,
                    }
                )
                .limit(limit)
                .sort("created_at", -1)
            )

            logger.info(f"检索到 {len(results)} 条经验数据")
            return results
        except Exception as e:
            logger.error(f"检索经验数据失败: {e}")
            return []

    def get_experience_by_id(self, experience_id: str) -> dict[str, Any] | None:
        """
        根据ID获取经验数据

        Args:
            experience_id: 经验ID

        Returns:
            经验数据，如果不存在返回None
        """
        try:
            from bson import ObjectId

            result = self.collection.find_one({"_id": ObjectId(experience_id)})
            return result
        except Exception as e:
            logger.error(f"获取经验数据失败: {e}")
            return None

    def update_experience(
        self,
        experience_id: str,
        content: str | None = None,
        keywords: list[str] | None = None,
        description: str | None = None,
    ) -> bool:
        """
        更新经验数据

        Args:
            experience_id: 经验ID
            content: 新的内容
            keywords: 新的关键字
            description: 新的描述

        Returns:
            是否更新成功
        """
        try:
            from bson import ObjectId

            update_data = {"updated_at": datetime.now()}
            if content is not None:
                update_data["content"] = content
            if keywords is not None:
                update_data["keywords"] = keywords
            if description is not None:
                update_data["description"] = description

            result = self.collection.update_one(
                {"_id": ObjectId(experience_id)}, {"$set": update_data}
            )

            if result.modified_count > 0:
                logger.info(f"经验数据已更新: {experience_id}")
                return True
            else:
                logger.warning(f"经验数据未找到: {experience_id}")
                return False
        except Exception as e:
            logger.error(f"更新经验数据失败: {e}")
            return False

    def delete_experience(self, experience_id: str) -> bool:
        """
        删除经验数据（软删除）

        Args:
            experience_id: 经验ID

        Returns:
            是否删除成功
        """
        try:
            from bson import ObjectId

            result = self.collection.update_one(
                {"_id": ObjectId(experience_id)},
                {"$set": {"is_active": False, "updated_at": datetime.now()}},
            )

            if result.modified_count > 0:
                logger.info(f"经验数据已删除: {experience_id}")
                return True
            else:
                logger.warning(f"经验数据未找到: {experience_id}")
                return False
        except Exception as e:
            logger.error(f"删除经验数据失败: {e}")
            return False

    def get_all_experiences(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        获取所有活跃的经验数据

        Args:
            limit: 返回数量限制

        Returns:
            经验数据列表
        """
        try:
            results = list(
                self.collection.find({"is_active": True})
                .limit(limit)
                .sort("created_at", -1)
            )

            logger.info(f"获取到 {len(results)} 条经验数据")
            return results
        except Exception as e:
            logger.error(f"获取经验数据失败: {e}")
            return []

    def _create_indexes(self):
        """创建索引"""
        try:
            self.collection.create_index("keywords")
            self.collection.create_index([("created_at", -1)])
            self.collection.create_index([("content", "text")])
            logger.info("MongoDB索引已创建")
        except Exception as e:
            logger.warning(f"创建索引失败: {e}")
