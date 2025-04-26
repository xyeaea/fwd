from typing import Any, Dict, List, Optional
from config import Config
import motor.motor_asyncio
from pymongo import MongoClient

# Cek versi MongoDB
async def mongodb_version() -> str:
    client = MongoClient(Config.DATABASE_URI)
    return client.server_info()['version']

class Database:
    def __init__(self, uri: str, database_name: str):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.bot = self.db.bots
        self.users = self.db.users
        self.notify = self.db.notify
        self.channels = self.db.channels

    @staticmethod
    def _new_user(user_id: int, name: str) -> Dict[str, Any]:
        return {
            "id": user_id,
            "name": name,
            "ban_status": {
                "is_banned": False,
                "ban_reason": ""
            }
        }

    async def add_user(self, user_id: int, name: str) -> None:
        if not await self.is_user_exist(user_id):
            user = self._new_user(user_id, name)
            await self.users.insert_one(user)

    async def is_user_exist(self, user_id: int) -> bool:
        return await self.users.find_one({'id': user_id}) is not None

    async def total_users_bots_count(self) -> tuple[int, int]:
        users_count = await self.users.count_documents({})
        bots_count = await self.bot.count_documents({})
        return users_count, bots_count

    async def total_channels(self) -> int:
        return await self.channels.count_documents({})

    async def ban_user(self, user_id: int, reason: str = "No Reason") -> None:
        await self.users.update_one(
            {'id': user_id},
            {'$set': {'ban_status': {'is_banned': True, 'ban_reason': reason}}}
        )

    async def remove_ban(self, user_id: int) -> None:
        await self.users.update_one(
            {'id': user_id},
            {'$set': {'ban_status': {'is_banned': False, 'ban_reason': ''}}}
        )

    async def get_ban_status(self, user_id: int) -> Dict[str, Any]:
        user = await self.users.find_one({'id': user_id}, {'ban_status': 1})
        return user.get('ban_status', {'is_banned': False, 'ban_reason': ''}) if user else {'is_banned': False, 'ban_reason': ''}

    async def delete_user(self, user_id: int) -> None:
        await self.users.delete_many({'id': user_id})

    async def get_all_users(self):
        return self.users.find({})

    async def get_banned_users(self) -> List[int]:
        cursor = self.users.find({'ban_status.is_banned': True}, {'id': 1})
        return [doc['id'] async for doc in cursor]

    async def update_configs(self, user_id: int, configs: Dict[str, Any]) -> None:
        await self.users.update_one({'id': user_id}, {'$set': {'configs': configs}})

    async def get_configs(self, user_id: int) -> Dict[str, Any]:
        default_configs = {
            'caption': None,
            'duplicate': True,
            'forward_tag': False,
            'file_size': 0,
            'size_limit': None,
            'extension': None,
            'keywords': None,
            'protect': None,
            'button': None,
            'db_uri': None,
            'filters': {
                'poll': True,
                'text': True,
                'audio': True,
                'voice': True,
                'video': True,
                'photo': True,
                'document': True,
                'animation': True,
                'sticker': True
            }
        }
        user = await self.users.find_one({'id': user_id}, {'configs': 1})
        return user.get('configs', default_configs) if user else default_configs

    async def add_bot(self, bot_data: Dict[str, Any]) -> None:
        if not await self.is_bot_exist(bot_data['user_id']):
            await self.bot.insert_one(bot_data)

    async def remove_bot(self, user_id: int) -> None:
        await self.bot.delete_many({'user_id': user_id})

    async def get_bot(self, user_id: int) -> Optional[Dict[str, Any]]:
        return await self.bot.find_one({'user_id': user_id})

    async def is_bot_exist(self, user_id: int) -> bool:
        return await self.bot.find_one({'user_id': user_id}) is not None

    async def in_channel(self, user_id: int, chat_id: int) -> bool:
        return await self.channels.find_one({'user_id': user_id, 'chat_id': chat_id}) is not None

    async def add_channel(self, user_id: int, chat_id: int, title: str, username: Optional[str]) -> bool:
        if await self.in_channel(user_id, chat_id):
            return False
        await self.channels.insert_one({'user_id': user_id, 'chat_id': chat_id, 'title': title, 'username': username})
        return True

    async def remove_channel(self, user_id: int, chat_id: int) -> bool:
        if not await self.in_channel(user_id, chat_id):
            return False
        await self.channels.delete_many({'user_id': user_id, 'chat_id': chat_id})
        return True

    async def get_channel_details(self, user_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
        return await self.channels.find_one({'user_id': user_id, 'chat_id': chat_id})

    async def get_user_channels(self, user_id: int) -> List[Dict[str, Any]]:
        cursor = self.channels.find({'user_id': user_id})
        return [doc async for doc in cursor]

    async def get_filters(self, user_id: int) -> List[str]:
        configs = await self.get_configs(user_id)
        return [k for k, v in configs.get('filters', {}).items() if not v]

    async def add_forward(self, user_id: int) -> None:
        await self.notify.insert_one({'user_id': user_id})

    async def remove_forward(self, user_id: Optional[int] = None, all_users: bool = False) -> None:
        filter_query = {} if all_users else {'user_id': user_id}
        await self.notify.delete_many(filter_query)

    async def get_all_forwards(self):
        return self.notify.find({})

# Initialize Database
db = Database(Config.DATABASE_URI, Config.DATABASE_NAME)
