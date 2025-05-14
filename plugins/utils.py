import time
import logging
from typing import Optional, Union, Dict, Any, Tuple
from pymongo.errors import PyMongoError
from pyrogram.types import InlineKeyboardMarkup

from database import db
from config import Temp
from .test import parse_buttons

logger = logging.getLogger(__name__)

class TaskStatus:
    """Manage the status of a message forwarding task and aggregate configuration data."""

    def __init__(self, task_id: str, temp: Temp = Temp()):
        """Initialize with a task ID and reference to Temp.status.

        Args:
            task_id: Unique identifier for the task.
            temp: Temporary data for runtime state.
        """
        self.id = task_id
        self.temp = temp
        self.data = temp.status

    def verify(self) -> bool:
        """Verify if the task exists in Temp.status.

        Returns:
            bool: True if the task exists, False otherwise.

        Example:
            >>> task = TaskStatus("task_123")
            >>> task.verify()
            False
        """
        return self.id in self.data

    def store(self, source_chat_id: Union[int, str], target_chat_id: Union[int, str], skip: int, limit: int) -> "TaskStatus":
        """Store a new forwarding task status.

        Args:
            source_chat_id: The source chat ID or username.
            target_chat_id: The target chat ID or username.
            skip: Number of messages to skip.
            limit: Maximum number of messages to process.

        Returns:
            TaskStatus: Self for method chaining.

        Example:
            >>> task = TaskStatus("task_123")
            >>> task.store(-100123456, -100654321, 10, 100)
        """
        async with self.temp.lock.setdefault(self.id, asyncio.Lock()):
            self.data[self.id] = {
                "FROM": source_chat_id,
                "TO": target_chat_id,
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

    def get(self, key: Optional[str] = None, full: bool = False) -> Optional[Union[Any, "TaskStatus"]]:
        """Retrieve a task value or the full task object.

        Args:
            key: The key to retrieve (e.g., 'fetched'). If None, returns None unless full=True.
            full: If True, sets attributes and returns self.

        Returns:
            Any | TaskStatus | None: The value, self, or None if the task doesn't exist.

        Example:
            >>> task.get("total_files")
            0
            >>> task.get(full=True).total
            100
        """
        async with self.temp.lock.setdefault(self.id, asyncio.Lock()):
            values = self.data.get(self.id)
            if not values:
                return None
            if full:
                for attr, value in values.items():
                    setattr(self, attr, value)
                return self
            return values.get(key)

    def add(self, key: Optional[str] = None, value: int = 1, is_time: bool = False) -> None:
        """Add or update a task value.

        Args:
            key: The key to update (e.g., 'fetched'). Ignored if is_time=True.
            value: The value to add (default: 1).
            is_time: If True, sets the 'start' time to current time.

        Example:
            >>> task.add("fetched", 5)
            >>> task.add(is_time=True)
        """
        async with self.temp.lock.setdefault(self.id, asyncio.Lock()):
            if self.id not in self.data:
                return
            if is_time:
                self.data[self.id]['start'] = time.time()
            elif key:
                current = self.get(key) or 0
                self.data[self.id][key] = current + value

    def delete(self) -> None:
        """Remove the task from Temp.status.

        Example:
            >>> task.delete()
        """
        async with self.temp.lock.setdefault(self.id, asyncio.Lock()):
            self.data.pop(self.id, None)

    @staticmethod
    def divide(numerator: int, denominator: int) -> float:
        """Perform safe division to avoid division by zero.

        Args:
            numerator: The numerator.
            denominator: The denominator.

        Returns:
            float: The result of numerator / denominator, or numerator if denominator is 0.

        Example:
            >>> TaskStatus.divide(10, 0)
            10.0
            >>> TaskStatus.divide(10, 2)
            5.0
        """
        return numerator / (denominator if denominator != 0 else 1)

    async def get_data(self, user_id: int) -> Optional[Tuple[Dict[str, Any], Optional[str], Optional[bool], Dict[str, Any], Optional[bool], Optional[InlineKeyboardMarkup]]]:
        """Aggregate configurations and settings for forwarding.

        Args:
            user_id: The user ID.

        Returns:
            Tuple | None: (bot, caption, forward_tag, task_data, protect, button) or None if failed.

        Raises:
            PyMongoError: If database access fails.

        Example:
            >>> task = TaskStatus("task_123")
            >>> await task.get_data(123456)
            ({'id': 789, 'is_bot': False, ...}, "Custom caption", False, {...}, True, InlineKeyboardMarkup(...))
        """
        async with self.temp.lock.setdefault(user_id, asyncio.Lock()):
            if user_id in self.temp.banned_users:
                logger.warning(f"Banned user {user_id} attempted to access get_data")
                return None

            try:
                bot = await db.get_bot(user_id)
                filters = await db.get_filters(user_id) or {}  # Fallback to empty dict
                configs = await db.get_configs(user_id)

                duplicate = [configs['db_uri'], self.TO] if configs.get('duplicate') else False
                button = parse_buttons(configs.get('button') or '') or None

                media_size = None
                if configs.get('file_size', 0) != 0:
                    media_size = {'size': configs['file_size'], 'limit': configs['size_limit']}

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

                return (
                    bot,
                    configs.get('caption'),
                    configs.get('forward_tag'),
                    task_data,
                    configs.get('protect'),
                    button
                )
            except PyMongoError as e:
                logger.error(f"Failed to get data for user {user_id}: {e}")
                return None
