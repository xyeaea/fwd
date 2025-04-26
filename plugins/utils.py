import time
from typing import Optional, Union
from database import db
from .test import parse_buttons

# Global status storage
STATUS = {}

class STS:
    def __init__(self, task_id: str):
        self.id = task_id
        self.data = STATUS

    def verify(self) -> bool:
        """Verify if the task exists."""
        return self.id in self.data

    def store(self, source_chat: Union[int, str], target_chat: Union[int, str], skip: int, limit: int) -> "STS":
        """Store a new forwarding task status."""
        self.data[self.id] = {
            "FROM": source_chat,
            "TO": target_chat,
            "total_files": 0,
            "skip": skip,
            "limit": limit,
            "fetched": skip,
            "filtered": 0,
            "deleted": 0,
            "duplicate": 0,
            "total": limit,
            "start": 0
        }
        self.get(full=True)
        return self

    def get(self, key: Optional[str] = None, full: bool = False):
        """Get value or full object."""
        values = self.data.get(self.id)
        if not values:
            return None
        if full:
            for attr, value in values.items():
                setattr(self, attr, value)
            return self
        return values.get(key)

    def add(self, key: Optional[str] = None, value: int = 1, is_time: bool = False):
        """Add or update a value."""
        if is_time:
            self.data[self.id]['start'] = time.time()
        elif key:
            current = self.get(key) or 0
            self.data[self.id][key] = current + value

    @staticmethod
    def divide(no: int, by: int) -> float:
        """Safe division."""
        return no / (by if by != 0 else 1)

    async def get_data(self, user_id: int):
        """Aggregate all configs and settings needed for forwarding."""
        bot = await db.get_bot(user_id)
        filters = await db.get_filters(user_id)
        configs = await db.get_configs(user_id)

        duplicate = [configs['db_uri'], self.TO] if configs.get('duplicate') else False
        button = parse_buttons(configs.get('button') or '')
        media_size = None

        if configs.get('file_size', 0) != 0:
            media_size = [configs['file_size'], configs['size_limit']]

        task_data = {
            'chat_id': self.FROM,
            'limit': self.limit,
            'offset': self.skip,
            'filters': filters,
            'keywords': configs.get('keywords'),
            'media_size': media_size,
            'extensions': configs.get('extension'),
            'skip_duplicate': duplicate
        }

        return bot, configs.get('caption'), configs.get('forward_tag'), task_data, configs.get('protect'), button
