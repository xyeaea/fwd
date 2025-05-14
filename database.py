# database.py
import logging
from typing import Dict, Any, List, AsyncGenerator, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from config import Config

logger = logging.getLogger(__name__)

class Database:
    """Async MongoDB database interface for the bot."""

    def __init__(self, uri: str):
        """Initialize the database client.

        Args:
            uri: MongoDB connection URI.

        Raises:
            PyMongoError: If connection fails.
        """
        try:
            self.client = AsyncIOMotorClient(uri)
            self.db: AsyncIOMotorDatabase = self.client["ForwardBot"]
            logger.info("Connected to MongoDB")
        except PyMongoError as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    async def add_bot(self, details: Dict[str, Any]) -> None:
        """Add bot or userbot details to the database.

        Args:
            details: Dictionary with bot/userbot info (id, is_bot, user_id, etc.).

        Raises:
            PyMongoError: If insertion fails.
        """
        try:
            await self.db.bots.insert_one(details)
            logger.info(f"Added bot/userbot {details['id']} for user {details['user_id']}")
        except PyMongoError as e:
            logger.error(f"Failed to add bot {details['id']}: {e}")
            raise

    async def get_bot(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve bot/userbot details for a user.

        Args:
            user_id: The user ID.

        Returns:
            Optional[Dict[str, Any]]: Bot/userbot details or None if not found.

        Raises:
            PyMongoError: If query fails.
        """
        try:
            return await self.db.bots.find_one({"user_id": user_id})
        except PyMongoError as e:
            logger.error(f"Failed to get bot for user {user_id}: {e}")
            raise

    async def get_configs(self, user_id: str) -> Dict[str, Any]:
        """Retrieve user configurations.

        Args:
            user_id: The user ID (string for default configs, e.g., '01').

        Returns:
            Dict[str, Any]: User configurations (defaults to empty dict if not found).

        Raises:
            PyMongoError: If query fails.
        """
        try:
            configs = await self.db.configs.find_one({"user_id": user_id})
            return configs or {"user_id": user_id, "filters": {}}
        except PyMongoError as e:
            logger.error(f"Failed to get configs for {user_id}: {e}")
            raise

    async def update_configs(self, user_id: int, config: Dict[str, Any]) -> None:
        """Update user configurations.

        Args:
            user_id: The user ID.
            config: The updated configuration.

        Raises:
            PyMongoError: If update fails.
        """
        try:
            await self.db.configs.update_one(
                {"user_id": user_id},
                {"$set": config},
                upsert=True
            )
            logger.info(f"Updated configs for user {user_id}")
        except PyMongoError as e:
            logger.error(f"Failed to update configs for user {user_id}: {e}")
            raise

    async def get_filters(self, user_id: int) -> Dict[str, Any]:
        """Retrieve user filters.

        Args:
            user_id: The user ID.

        Returns:
            Dict[str, Any]: User filters (defaults to empty dict).

        Raises:
            PyMongoError: If query fails.
        """
        try:
            configs = await self.db.configs.find_one({"user_id": user_id})
            return configs.get("filters", {}) if configs else {}
        except PyMongoError as e:
            logger.error(f"Failed to get filters for user {user_id}: {e}")
            raise

    async def get_all_forwards(self) -> List[Dict[str, Any]]:
        """Retrieve all users in the forward list.

        Returns:
            List[Dict[str, Any]]: List of forward entries.

        Raises:
            PyMongoError: If query fails.
        """
        try:
            return await self.db.forwards.find().to_list(None)
        except PyMongoError as e:
            logger.error(f"Failed to get all forwards: {e}")
            raise

    async def remove_forward(self, all_users: bool = False) -> None:
        """Remove users from the forward list.

        Args:
            all_users: If True, clear all forwards.

        Raises:
            PyMongoError: If deletion fails.
        """
        try:
            if all_users:
                await self.db.forwards.delete_many({})
                logger.info("Cleared all forwards")
        except PyMongoError as e:
            logger.error(f"Failed to remove forwards: {e}")
            raise

    async def get_all_users(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Retrieve all users (for resetall).

        Yields:
            Dict[str, Any]: User document.

        Raises:
            PyMongoError: If query fails.
        """
        try:
            async for user in self.db.configs.find():
                yield user
        except PyMongoError as e:
            logger.error(f"Failed to get all users: {e}")
            raise

# Initialize database with Config.MONGODB_URI
db = Database(Config().MONGODB_URI)
