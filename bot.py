import asyncio
import logging
from typing import Optional
from pathlib import Path

from pyrogram import Client, __version__
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, RPCError
from pymongo.errors import ConnectionError as MongoConnectionError

from database import db
from config import Config, Temp
from translation import Translation  # Assume Translation class exists

# Fallback logging configuration if logging.conf is missing
if not Path("logging.conf").exists():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("bot.log")
        ]
    )
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

class Bot(Client):
    """Telegram bot client for auto-forwarding messages between channels."""

    def __init__(self, config: Config, temp: Temp):
        """Initialize the bot with configuration and temporary data.

        Args:
            config: Config object containing bot settings.
            temp: Temp object for managing runtime data.
        """
        super().__init__(
            name=config.BOT_SESSION,
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            plugins={"root": "plugins"},
            workers=50
        )
        self.config = config
        self.temp = temp
        self.logger = logger
        self.id: Optional[int] = None
        self.username: Optional[str] = None
        self.first_name: Optional[str] = None

    async def start(self) -> None:
        """Start the bot, initialize bot info, and send restart notifications.

        Raises:
            RPCError: If Pyrogram fails to connect to Telegram.
            MongoConnectionError: If database connection fails.
        """
        try:
            await super().start()
            me = await self.get_me()
            self.id = me.id
            self.username = me.username
            self.first_name = me.first_name

            self.set_parse_mode(ParseMode.HTML)  # Align with Translation class
            self.logger.info(
                f"{self.first_name} started with Pyrogram v{__version__} (Layer {self.raw.layer}) as @{self.username}"
            )

            await self.notify_restart()
        except RPCError as e:
            self.logger.error(f"Failed to start bot: {e}")
            raise
        except MongoConnectionError as e:
            self.logger.error(f"Database connection failed: {e}")
            raise

    async def notify_restart(self) -> None:
        """Send restart notifications to users in the forward list and clear it."""
        text = Translation.CANCEL.replace("Process Cancelled Successfully!", 
                                        "Bot restarted successfully!")
        success, failed = 0, 0

        try:
            forwards = await db.get_all_forwards()
            if not isinstance(forwards, list):
                self.logger.error("get_all_forwards returned invalid data: not a list")
                return

            for user in forwards:
                chat_id = user.get('user_id')
                if not isinstance(chat_id, int):
                    self.logger.warning(f"Invalid user_id in forwards: {chat_id}")
                    continue

                try:
                    await self.safe_send_message(chat_id, text)
                    success += 1
                except Exception as e:
                    self.logger.error(f"Failed to send message to {chat_id}: {e}")
                    failed += 1

            if success + failed > 0:
                await db.remove_forward(all_users=True)
                self.logger.info(f"Restart notifications: Success = {success}, Failed = {failed}")
        except Exception as e:
            self.logger.error(f"Error in notify_restart: {e}")

    async def safe_send_message(self, chat_id: int, text: str) -> None:
        """Send a message with automatic FloodWait handling.

        Args:
            chat_id: The ID of the chat to send the message to.
            text: The message text to send.

        Raises:
            RPCError: If sending the message fails after FloodWait retries.
        """
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                await self.send_message(chat_id, text, parse_mode=ParseMode.HTML)
                return
            except FloodWait as e:
                self.logger.warning(f"FloodWait: Sleeping for {e.value} seconds (attempt {attempt + 1}/{max_attempts})")
                await asyncio.sleep(e.value + 1)
            except RPCError as e:
                self.logger.error(f"Failed to send message to {chat_id}: {e}")
                if attempt == max_attempts - 1:
                    raise
        self.logger.error(f"Failed to send message to {chat_id} after {max_attempts} attempts")

    async def stop(self, *args) -> None:
        """Stop the bot and log shutdown."""
        await super().stop()
        self.logger.info(f"@{self.username} has been stopped. Goodbye!")
