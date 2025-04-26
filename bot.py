import asyncio
import logging
import logging.config

from pyrogram import Client, __version__
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

from database import db
from config import Config
from pyrogram.raw.all import layer

# Setup Logging
logging.config.fileConfig('logging.conf')
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.ERROR)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name=Config.BOT_SESSION,
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins={"root": "plugins"},
            workers=50
        )
        self.logger = logger
        self.id = None
        self.username = None
        self.first_name = None

    async def start(self):
        await super().start()
        me = await self.get_me()

        self.id = me.id
        self.username = me.username
        self.first_name = me.first_name

        self.set_parse_mode(ParseMode.DEFAULT)
        self.logger.info(
            f"{self.first_name} started with Pyrogram v{__version__} (Layer {layer}) as @{self.username}"
        )

        await self.notify_restart()

    async def notify_restart(self):
        text = "**๏[-ิ_•ิ]๏ Bot restarted successfully!**"
        success, failed = 0, 0

        # Await the coroutine before iterating
        forwards = await db.get_all_forwards()  # Await the coroutine here

        for user in forwards:  # Now use normal for loop
            chat_id = user.get('user_id')
            if not chat_id:
                continue

            try:
                await self.safe_send_message(chat_id, text)
                success += 1
            except Exception as e:
                self.logger.error(f"Failed to send message to {chat_id}: {e}")
                failed += 1

        if success + failed > 0:
            await db.remove_forward(all_users=True)  # Assuming this is the correct function to clear data
            self.logger.info(f"Restart notifications: Success = {success}, Failed = {failed}")

    async def safe_send_message(self, chat_id, text):
        """Helper untuk kirim pesan dengan handle FloodWait otomatis"""
        try:
            await self.send_message(chat_id, text)
        except FloodWait as e:
            self.logger.warning(f"FloodWait: Sleeping for {e.value} seconds.")
            await asyncio.sleep(e.value + 1)
            await self.send_message(chat_id, text)

    async def stop(self, *args):
        await super().stop()
        self.logger.info(f"@{self.username} has been stopped. Goodbye!")
