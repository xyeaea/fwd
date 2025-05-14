import os
import re
import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse
from asyncio import Lock

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class Config:
    """Configuration settings for the Telegram auto-forward bot."""

    _instance = None

    def __new__(cls):
        """Implement singleton pattern to ensure one Config instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize and validate configuration settings."""
        if not self._initialized:
            self._env_vars = {
                "API_ID": os.getenv("API_ID"),
                "API_HASH": os.getenv("API_HASH"),
                "BOT_TOKEN": os.getenv("BOT_TOKEN"),
                "BOT_SESSION": os.getenv("BOT_SESSION", "bot"),
                "DATABASE": os.getenv("DATABASE"),
                "DATABASE_NAME": os.getenv("DATABASE_NAME", "forward-bot"),
                "BOT_OWNER_ID": os.getenv("BOT_OWNER_ID", "")
            }
            self._owner_ids = None  # Cache for BOT_OWNER_ID
            self._validate_env_vars()
            self._initialized = True

    @property
    def API_ID(self) -> int:
        """Telegram API ID.

        Example: 1234567
        """
        return int(self._env_vars["API_ID"])

    @property
    def API_HASH(self) -> str:
        """Telegram API hash.

        Example: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'
        """
        return self._env_vars["API_HASH"]

    @property
    def BOT_TOKEN(self) -> str:
        """Telegram bot token.

        Example: '123456789:ABC-DEF1234...'
        """
        return self._env_vars["BOT_TOKEN"]

    @property
    def BOT_SESSION(self) -> str:
        """Bot session name, defaults to 'bot'.

        Example: 'my_bot_session'
        """
        return self._env_vars["BOT_SESSION"]

    @property
    def DATABASE_URI(self) -> str:
        """MongoDB connection URI.

        Example: 'mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true'
        """
        return self._env_vars["DATABASE"]

    @property
    def DATABASE_NAME(self) -> str:
        """MongoDB database name, defaults to 'forward-bot'.

        Example: 'my_forward_bot_db'
        """
        return self._env_vars["DATABASE_NAME"]

    @property
    def BOT_OWNER_ID(self) -> Optional[List[int]]:
        """List of bot owner IDs.

        Example: [123456789, 987654321]
        """
        if self._owner_ids is None:
            owner_ids = self._env_vars["BOT_OWNER_ID"].split()
            self._owner_ids = [int(x) for x in owner_ids if x.strip()] if owner_ids else []
        return self._owner_ids

    def _validate_env_vars(self) -> None:
        """Validate required environment variables and their formats."""
        required_vars = ["API_ID", "API_HASH", "BOT_TOKEN", "DATABASE"]
        for var in required_vars:
            if not self._env_vars[var]:
                logger.error(f"Missing required environment variable: {var}")
                raise EnvironmentError(f"Missing required environment variable: {var}")

        # Validate API_ID
        try:
            int(self._env_vars["API_ID"])
        except ValueError:
            logger.error("API_ID must be a valid integer")
            raise ValueError("API_ID must be a valid integer")

        # Validate BOT_TOKEN
        if not self._env_vars["BOT_TOKEN"]:
            logger.error("BOT_TOKEN cannot be empty")
            raise ValueError("BOT_TOKEN cannot be empty")
        token_pattern = r"^\d+:[A-Za-z0-9\-_]+$"
        if not re.match(token_pattern, self._env_vars["BOT_TOKEN"]):
            logger.error("BOT_TOKEN has an invalid format")
            raise ValueError("BOT_TOKEN has an invalid format")

        # Validate DATABASE_URI
        try:
            parsed = urlparse(self._env_vars["DATABASE"])
            if parsed.scheme not in ("mongodb", "mongodb+srv"):
                logger.error("DATABASE_URI must be a valid MongoDB URI (mongodb:// or mongodb+srv://)")
                raise ValueError("DATABASE_URI must be a valid MongoDB URI (mongodb:// or mongodb+srv://)")
        except Exception as e:
            logger.error(f"Invalid DATABASE_URI: {str(e)}")
            raise ValueError(f"Invalid DATABASE_URI: {str(e)}")

        # Validate BOT_SESSION and DATABASE_NAME
        for var, value in [("BOT_SESSION", self._env_vars["BOT_SESSION"]), 
                          ("DATABASE_NAME", self._env_vars["DATABASE_NAME"])]:
            if not re.match(r"^[a-zA-Z0-9_]+$", value):
                logger.error(f"{var} contains invalid characters; only alphanumeric and underscore allowed")
                raise ValueError(f"{var} contains invalid characters; only alphanumeric and underscore allowed")

        # Validate BOT_OWNER_ID
        for oid in self._env_vars["BOT_OWNER_ID"].split():
            if oid.strip():
                try:
                    int(oid)
                except ValueError:
                    logger.error(f"Invalid BOT_OWNER_ID: {oid} is not an integer")
                    raise ValueError(f"Invalid BOT_OWNER_ID: {oid} is not an integer")


class Temp:
    """Temporary runtime data for the Telegram auto-forward bot."""

    def __init__(self):
        """Initialize instance-level attributes to avoid shared state."""
        self.lock: Dict[int, Lock] = {}
        """Dictionary of asyncio.Lock objects for concurrent operations, keyed by chat/user ID."""
        
        self.cancel: Dict[int, bool] = {}
        """Dictionary to track cancellation requests, keyed by chat/user ID."""
        
        self.forwardings: int = 0
        """Counter for active forwarding operations."""
        
        self.banned_users: List[int] = []
        """List of user IDs banned from using the bot."""
        
        self.forward_chats: List[int] = []
        """List of chat IDs involved in forwarding operations."""

    def add_banned_user(self, user_id: int) -> bool:
        """Add a user to the banned list if not already banned.

        Args:
            user_id: The ID of the user to ban.

        Returns:
            bool: True if the user was added, False if already banned.
        """
        if user_id not in self.banned_users:
            self.banned_users.append(user_id)
            return True
        return False

    def remove_banned_user(self, user_id: int) -> bool:
        """Remove a user from the banned list if present.

        Args:
            user_id: The ID of the user to unban.

        Returns:
            bool: True if the user was removed, False if not banned.
        """
        if user_id in self.banned_users:
            self.banned_users.remove(user_id)
            return True
        return False

    def add_forward_chat(self, chat_id: int) -> bool:
        """Add a chat to the forwarding list if not already present.

        Args:
            chat_id: The ID of the chat to add.

        Returns:
            bool: True if the chat was added, False if already present.
        """
        if chat_id not in self.forward_chats:
            self.forward_chats.append(chat_id)
            return True
        return False

    def remove_forward_chat(self, chat_id: int) -> bool:
        """Remove a chat from the forwarding list if present.

        Args:
            chat_id: The ID of the chat to remove.

        Returns:
            bool: True if the chat was removed, False if not present.
        """
        if chat_id in self.forward_chats:
            self.forward_chats.remove(chat_id)
            return True
        return False
