# Append MongoUserStorage to mongodb.py
with open(r'd:/spacex/Zest-Agent/zest-app-server/app/core/storage/mongodb.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix trailing junk
content = content.rstrip()
# Remove trailing "" if present
if content.endswith('""'):
    content = content[:-2].rstrip()

content += """


class MongoUserStorage(UserStorage):
    \"\"\"MongoDB 用户配置存储\"\"\"

    def __init__(self, mongo_client, db_name: str = "zest_agent"):
        self.db = mongo_client[db_name]
        self.collection = self.db["users"]

    async def ensure_indexes(self):
        await self.collection.create_index("user_id", unique=True)

    async def save_user(self, user: UserInfo) -> bool:
        try:
            doc = user.dict()
            for key, value in doc.items():
                if isinstance(value, datetime):
                    doc[key] = value.isoformat()
            result = await self.collection.replace_one(
                {"user_id": user.user_id}, doc, upsert=True
            )
            return True
        except Exception:
            return False

    async def get_user(self, user_id: str):
        doc = await self.collection.find_one({"user_id": user_id})
        if not doc:
            return None
        return UserInfo(**doc)

    async def delete_user(self, user_id: str) -> bool:
        try:
            result = await self.collection.delete_one({"user_id": user_id})
            return result.deleted_count > 0
        except Exception:
            return False
"""

with open(r'd:/spacex/Zest-Agent/zest-app-server/app/core/storage/mongodb.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
