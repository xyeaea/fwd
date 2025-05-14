import re
import asyncio
import logging
from typing import Union, Optional, AsyncGenerator, Dict, Any, List
from pymongo.errors import PyMongoError
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, RPCError, AccessTokenExpired, AccessTokenInvalid, ChatWriteForbidden

from database import db
from config import Config, Temp
from translation import Translation

logger = logging.getLogger(__name__)

BTN_URL_REGEX = re.compile(r"(\[([^\[]+?)]\[buttonurl:/{0,2}(.+?)(:same)?])")
BOT_TOKEN_TEXT = (
    "<b>1) Create a bot using @BotFather</b>\n"
    "<b>2) Forward the message containing the bot token to me</b>\n"
    "<code>/cancel</code> - cancel this process"
)
SESSION_STRING_SIZE = 351
BOT_TOKEN_REGEX = re.compile(r"^\d{8,10}:[0-9A-Za-z_-]{35}$")

async def safe_send_message(bot: Client, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> Optional[Message]:
    """Send a message with FloodWait handling.

    Args:
        bot: The Pyrogram Client instance.
        chat_id: The chat ID to send the message to.
        text: The message text.
        reply_markup: Optional inline keyboard markup.

    Returns:
        Message | None: The sent message or None if failed.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        except FloodWait as e:
            logger.warning(f"FloodWait: Sleeping for {e.value} seconds (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(e.value + 1)
        except RPCError as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            return None
    return None

async def iter_messages(
    client: Client,
    chat_id: Union[int, str],
    limit: int,
    offset: int = 0,
    search: Optional[str] = None,
    filter: Optional[Any] = None
) -> Optional[AsyncGenerator[Message, None]]:
    """Iterate through a chat's messages sequentially.

    Args:
        client: The Pyrogram Client instance.
        chat_id: Unique identifier (int) or username (str) of the target chat.
        limit: Maximum number of messages to return.
        offset: Identifier of the first message to return (default: 0).
        search: Optional search query (not implemented).
        filter: Optional message filter (not implemented).

    Yields:
        Message: A Pyrogram Message object.

    Example:
        async for message in iter_messages(client, "pyrogram", 100, 0):
            print(message.text)
    """
    current = offset
    while True:
        batch_size = min(200, limit - current)
        if batch_size <= 0:
            return
        try:
            messages = await client.get_messages(chat_id, list(range(current, current + batch_size + 1)))
            for message in messages:
                yield message
                current += 1
        except RPCError as e:
            logger.error(f"Failed to fetch messages from {chat_id}: {e}")
            return

async def start_clone_bot(client: Client, data: Optional[Any] = None) -> Client:
    """Start a Pyrogram client and patch it with iter_messages.

    Args:
        client: The Pyrogram Client instance to start.
        data: Optional data (not used).

    Returns:
        Client: The started client with patched iter_messages.

    Raises:
        RPCError: If the client fails to start.
    """
    try:
        await client.start()
        client.iter_messages = lambda *args, **kwargs: iter_messages(client, *args, **kwargs)
        return client
    except RPCError as e:
        logger.error(f"Failed to start client: {e}")
        raise

class CLIENT:
    def __init__(self, config: Config = Config()):
        """Initialize the CLIENT with API credentials.

        Args:
            config: Configuration object with API_ID and API_HASH.
        """
        self.api_id = config.API_ID
        self.api_hash = config.API_HASH

    def client(self, data: Dict[str, Any], user: Optional[bool] = None) -> Client:
        """Create a Pyrogram Client for a bot or userbot.

        Args:
            data: Dictionary with bot token or session string, or raw token/session string.
            user: True for session string, False for bot token, None for auto-detection.

        Returns:
            Client: A Pyrogram Client instance.
        """
        if user is None and data.get('is_bot') is False:
            return Client("USERBOT", self.api_id, self.api_hash, session_string=data.get('session'))
        elif user is True:
            return Client("USERBOT", self.api_id, self.api_hash, session_string=data)
        elif user is not False:
            return Client("BOT", self.api_id, self.api_hash, bot_token=data.get('token'), in_memory=True)
        return Client("BOT", self.api_id, self.api_hash, bot_token=data, in_memory=True)

    async def add_bot(self, bot: Client, message: CallbackQuery) -> bool:
        """Add a bot token to the database after validation.

        Args:
            bot: The Pyrogram Client instance.
            message: The callback query containing the user response.

        Returns:
            bool: True if the bot was added successfully, False otherwise.
        """
        user_id = message.from_user.id
        try:
            msg = await bot.ask(
                chat_id=user_id,
                text=BOT_TOKEN_TEXT,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True,
                timeout=120
            )
        except asyncio.TimeoutError:
            await safe_send_message(bot, user_id, Translation.CANCEL)
            return False

        async with Temp().lock.setdefault(user_id, asyncio.Lock()):
            if msg.text == "/cancel" or Temp().cancel.get(user_id, False):
                Temp().cancel[user_id] = False
                await safe_send_message(bot, user_id, Translation.CANCEL)
                return False
            elif not msg.forward_date:
                await safe_send_message(bot, user_id, "<b>This is not a forwarded message</b>")
                return False
            elif str(msg.forward_from.id) != "93372553":
                await safe_send_message(bot, user_id, "<b>This message was not forwarded from BotFather</b>")
                return False

            bot_token = BOT_TOKEN_REGEX.search(msg.text)
            if not bot_token:
                await safe_send_message(bot, user_id, "<b>No valid bot token found in the message</b>")
                return False

            bot_token = bot_token.group(0)
            try:
                client = await start_clone_bot(self.client(bot_token, False))
                bot_info = client.me
                details = {
                    'id': bot_info.id,
                    'is_bot': True,
                    'user_id': user_id,
                    'name': bot_info.first_name,
                    'token': bot_token,
                    'username': f"@{bot_info.username}" if bot_info.username else None
                }
                await db.add_bot(details)
                return True
            except (AccessTokenExpired, AccessTokenInvalid, RPCError) as e:
                logger.error(f"Failed to validate bot token for user {user_id}: {e}")
                await safe_send_message(bot, user_id, f"<b>Bot Error:</b> <code>{str(e)}</code>")
                return False
            except PyMongoError as e:
                logger.error(f"Failed to save bot details for user {user_id}: {e}")
                await safe_send_message(bot, user_id, "<b>Failed to save bot to database</b>")
                return False

    async def add_session(self, bot: Client, message: CallbackQuery) -> bool:
        """Add a userbot session string to the database after validation.

        Args:
            bot: The Pyrogram Client instance.
            message: The callback query containing the user response.

        Returns:
            bool: True if the session was added successfully, False otherwise.
        """
        user_id = message.from_user.id
        disclaimer = (
            "<b>⚠️ DISCLAIMER ⚠️</b>\n\n"
            "<code>Using a userbot session allows forwarding messages from private chats. "
            "Add your Pyrogram session at your own risk. Your account may be banned, and the developer "
            "is not responsible for any consequences.</code>"
        )
        await safe_send_message(bot, user_id, disclaimer)

        try:
            msg = await bot.ask(
                chat_id=user_id,
                text=(
                    "<b>Send your Pyrogram session string</b>\n"
                    "<i>Get it from trusted sources</i>\n"
                    "<code>/cancel</code> - cancel this process"
                ),
                parse_mode=enums.ParseMode.HTML,
                timeout=120
            )
        except asyncio.TimeoutError:
            await safe_send_message(bot, user_id, Translation.CANCEL)
            return False

        async with Temp().lock.setdefault(user_id, asyncio.Lock()):
            if msg.text == "/cancel" or Temp().cancel.get(user_id, False):
                Temp().cancel[user_id] = False
                await safe_send_message(bot, user_id, Translation.CANCEL)
                return False
            elif len(msg.text) < SESSION_STRING_SIZE:
                await safe_send_message(bot, user_id, "<b>Invalid session string</b>")
                return False

            try:
                client = await start_clone_bot(self.client(msg.text, True))
                user_info = client.me
                details = {
                    'id': user_info.id,
                    'is_bot': False,
                    'user_id': user_id,
                    'name': user_info.first_name,
                    'session': msg.text,
                    'username': f"@{user_info.username}" if user_info.username else None
                }
                await db.add_bot(details)
                return True
            except RPCError as e:
                logger.error(f"Failed to validate session string for user {user_id}: {e}")
                await safe_send_message(bot, user_id, f"<b>Userbot Error:</b> <code>{str(e)}</code>")
                return False
            except PyMongoError as e:
                logger.error(f"Failed to save userbot details for user {user_id}: {e}")
                await safe_send_message(bot, user_id, "<b>Failed to save userbot to database</b>")
                return False

@Client.on_message(filters.private & filters.command("reset"))
async def reset(bot: Client, message: Message, temp: Temp = Temp()) -> None:
    """Reset a user's settings to default.

    Args:
        bot: The Pyrogram Client instance.
        message: The message containing the command.
        temp: Temporary data for runtime state.
    """
    user_id = message.from_user.id
    async with temp.lock.setdefault(user_id, asyncio.Lock()):
        if user_id in temp.banned_users:
            await safe_send_message(bot, user_id, "You are banned from using this bot.")
            return

        try:
            default = await db.get_configs("01")  # Default config
            temp.configs[user_id] = default
            await db.update_configs(user_id, default)
            await safe_send_message(bot, user_id, "Successfully reset settings ✔️")
        except PyMongoError as e:
            logger.error(f"Failed to reset settings for user {user_id}: {e}")
            await safe_send_message(bot, user_id, "<b>Failed to reset settings</b>")

@Client.on_message(filters.command("resetall") & filters.user(Config.BOT_OWNER_ID))
async def reset_all(bot: Client, message: Message, temp: Temp = Temp()) -> None:
    """Reset all users' settings to default.

    Args:
        bot: The Pyrogram Client instance.
        message: The message containing the command.
        temp: Temporary data for runtime state.
    """
    user_id = message.from_user.id
    async with temp.lock.setdefault(user_id, asyncio.Lock()):
        try:
            sts = await safe_send_message(bot, user_id, "<b>Processing...</b>")
            if not sts:
                return

            users = await db.get_all_users()
            total = success = failed = 0
            errors: List[str] = []
            async for user in users:
                user_id = user['id']
                total += 1
                try:
                    default = await db.get_configs(user_id)
                    default['db_uri'] = None  # Preserve db_uri if needed
                    await db.update_configs(user_id, default)
                    temp.configs[user_id] = default
                    success += 1
                except PyMongoError as e:
                    logger.error(f"Failed to reset settings for user {user_id}: {e}")
                    errors.append(str(e))
                    failed += 1

                if total % 10 == 0:
                    await safe_edit_message(
                        sts,
                        f"<b>Progress:</b>\nTotal: {total}\nSuccess: {success}\nFailed: {failed}",
                        parse_mode=enums.ParseMode.HTML
                    )

            error_text = f"<b>Errors:</b>\n<code>{' | '.join(errors[:10])}</code>" if errors else ""
            await safe_edit_message(
                sts,
                f"<b>Completed:</b>\nTotal: {total}\nSuccess: {success}\nFailed: {failed}\n{error_text}",
                parse_mode=enums.ParseMode.HTML
            )
        except PyMongoError as e:
            logger.error(f"Failed to get users for reset_all: {e}")
            await safe_send_message(bot, user_id, "<b>Failed to access database</b>")

async def safe_edit_message(msg: Message, text: str, parse_mode: Optional[enums.ParseMode] = enums.ParseMode.HTML) -> Optional[Message]:
    """Edit a message with FloodWait handling.

    Args:
        msg: The message to edit.
        text: The new text.
        parse_mode: The parse mode (default: HTML).

    Returns:
        Message | None: The edited message or None if failed.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            return await msg.edit_text(text=text, parse_mode=parse_mode)
        except FloodWait as e:
            logger.warning(f"FloodWait: Sleeping for {e.value} seconds (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(e.value + 1)
        except RPCError as e:
            logger.error(f"Failed to edit message {msg.id}: {e}")
            return None
    return None

async def get_configs(user_id: Union[int, str]) -> Dict[str, Any]:
    """Retrieve user configurations from the database.

    Args:
        user_id: The user ID or identifier.

    Returns:
        Dict[str, Any]: The user's configuration.

    Raises:
        PyMongoError: If database access fails.
    """
    async with Temp().lock.setdefault(user_id, asyncio.Lock()):
        configs = Temp().configs.get(user_id)
        if not configs:
            configs = await db.get_configs(user_id)
            Temp().configs[user_id] = configs
        return configs

async def update_configs(user_id: Union[int, str], key: str, value: Any) -> None:
    """Update a user's configuration in the database.

    Args:
        user_id: The user ID or identifier.
        key: The configuration key to update.
        value: The new value.

    Raises:
        PyMongoError: If database update fails.
    """
    async with Temp().lock.setdefault(user_id, asyncio.Lock()):
        current = await db.get_configs(user_id)
        if key in ['caption', 'duplicate', 'db_uri', 'forward_tag', 'protect', 'file_size', 'size_limit', 'extension', 'keywords', 'button']:
            current[key] = value
        else:
            current.setdefault('filters', {})[key] = value
        Temp().configs[user_id] = current
        await db.update_configs(user_id, current)

def parse_buttons(text: str, markup: bool = True) -> Optional[Union[InlineKeyboardMarkup, List[List[InlineKeyboardButton]]]]:
    """Parse markdown button text into InlineKeyboardMarkup.

    Args:
        text: The markdown text containing buttons (e.g., [text][buttonurl:link]).
        markup: If True, return InlineKeyboardMarkup; else, return button list.

    Returns:
        InlineKeyboardMarkup | List[List[InlineKeyboardButton]] | None: Parsed buttons or None if invalid.

    Example:
        >>> parse_buttons("[Forward Bot][buttonurl:https://t.me/devgaganbot]")
        InlineKeyboardMarkup([[InlineKeyboardButton("Forward Bot", url="https://t.me/devgaganbot")]])
    """
    buttons = []
    try:
        for match in BTN_URL_REGEX.finditer(text):
            n_escapes = sum(1 for i in range(match.start(1) - 1, -1, -1) if text[i] == "\\")
            if n_escapes % 2 == 0:
                url = match.group(3).replace(" ", "")
                if not url.startswith(("http://", "https://", "tg://")):
                    return None
                button = InlineKeyboardButton(text=match.group(2), url=url)
                if match.group(4) and buttons:
                    buttons[-1].append(button)
                else:
                    buttons.append([button])
        if not buttons:
            return None
        return InlineKeyboardMarkup(buttons) if markup else buttons
    except Exception as e:
        logger.error(f"Failed to parse buttons: {e}")
        return None
