import re
import asyncio
import logging
from typing import Optional, Tuple, Dict, Any, List
from pymongo.errors import PyMongoError
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from pyrogram.errors import FloodWait, RPCError, not_acceptable_406, bad_request_400

from database import db
from config import Temp
from translation import Translation

logger = logging.getLogger(__name__)

async def safe_send_message(bot: Client, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup | ReplyKeyboardMarkup] = None) -> None:
    """Send a message with FloodWait handling.

    Args:
        bot: The Pyrogram Client instance.
        chat_id: The chat ID to send the message to.
        text: The message text.
        reply_markup: Optional inline or reply keyboard markup.

    Raises:
        RPCError: If sending fails after retries.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
            return
        except FloodWait as e:
            logger.warning(f"FloodWait: Sleeping for {e.value} seconds (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(e.value + 1)
        except RPCError as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            if attempt == max_attempts - 1:
                raise

async def parse_channel_link(link: str) -> Optional[Tuple[str | int, int]]:
    """Parse a Telegram channel link to extract chat ID and message ID.

    Args:
        link: The Telegram link (e.g., https://t.me/channel/123).

    Returns:
        Tuple[str | int, int] | None: (chat_id, message_id) or None if invalid.
    """
    regex = re.compile(
        r"(?:https?://)?(?:t\.me|telegram\.(?:me|dog))/(c/)?([a-zA-Z_0-9]+|\d+)/(\d+)(?:\?single)?",
        re.IGNORECASE
    )
    match = regex.match(link.strip())
    if not match:
        return None

    chat_id = match.group(2)
    message_id = int(match.group(3))
    if chat_id.isdigit():
        chat_id = int("-100" + chat_id)
    return chat_id, message_id

@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run(bot: Client, message: Message, temp: Temp = Temp()) -> None:
    """Handle /fwd or /forward to set up message forwarding from a source to a target channel.

    Guides the user through selecting a target channel, specifying a source channel, setting a skip count,
    and confirming the action.

    Args:
        bot: The Pyrogram Client instance.
        message: The message containing the command.
        temp: Temporary data for runtime state.

    Example:
        Send /fwd, select a target channel, provide a source link, set skip count, and confirm.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id

    async with temp.lock.setdefault(chat_id, asyncio.Lock()):
        if temp.cancel.get(chat_id, False):
            await safe_send_message(bot, chat_id, Translation.CANCEL)
            temp.cancel[chat_id] = False
            return

        if user_id in temp.banned_users:
            await safe_send_message(bot, chat_id, "You are banned from using this bot.")
            return

        try:
            _bot = await db.get_bot(user_id)
            if not _bot:
                await safe_send_message(
                    bot, chat_id,
                    "<code>You didn't add any bot. Please add a bot using /settings!</code>"
                )
                return
        except PyMongoError as e:
            logger.error(f"Failed to get bot for user {user_id}: {e}")
            await safe_send_message(bot, chat_id, "Failed to access database. Please try again later.")
            return

        try:
            channels = await db.get_user_channels(user_id)
            if not channels:
                await safe_send_message(
                    bot, chat_id,
                    "Please set a 'to' channel in /settings before forwarding."
                )
                return
        except PyMongoError as e:
            logger.error(f"Failed to get channels for user {user_id}: {e}")
            await safe_send_message(bot, chat_id, "Failed to access database. Please try again later.")
            return

        target_chat_id: int
        target_title: str
        if len(channels) > 1:
            buttons = [[KeyboardButton(channel['title'])] for channel in channels]
            buttons.append([KeyboardButton(Translation.CANCEL_COMMAND.split(" ")[0])])
            btn_data = {channel['title']: channel['chat_id'] for channel in channels}

            try:
                ask_channel = await bot.ask(
                    chat_id,
                    Translation.TO_MSG,
                    reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True),
                    timeout=300
                )
            except asyncio.TimeoutError:
                await safe_send_message(bot, chat_id, Translation.CANCEL)
                return

            if ask_channel.text.startswith(("/", Translation.CANCEL_COMMAND.split(" ")[0])):
                await safe_send_message(bot, chat_id, Translation.CANCEL, ReplyKeyboardRemove())
                return

            target_chat_id = btn_data.get(ask_channel.text)
            if not target_chat_id:
                await safe_send_message(
                    bot, chat_id, "Wrong channel chosen!", ReplyKeyboardRemove()
                )
                return
            target_title = ask_channel.text
        else:
            target_chat_id = channels[0]['chat_id']
            target_title = channels[0]['title']

        try:
            source_response = await bot.ask(chat_id, Translation.FROM_MSG, reply_markup=ReplyKeyboardRemove(), timeout=300)
        except asyncio.TimeoutError:
            await safe_send_message(bot, chat_id, Translation.CANCEL)
            return

        if source_response.text and source_response.text.startswith("/"):
            await safe_send_message(bot, chat_id, Translation.CANCEL)
            return

        source_chat_id: str | int
        last_msg_id: int
        if source_response.text and not source_response.forward_date:
            result = await parse_channel_link(source_response.text)
            if not result:
                await safe_send_message(bot, chat_id, "Invalid link.")
                return
            source_chat_id, last_msg_id = result
        elif source_response.forward_from_chat and source_response.forward_from_chat.type == enums.ChatType.CHANNEL:
            source_chat_id = source_response.forward_from_chat.username or source_response.forward_from_chat.id
            last_msg_id = source_response.forward_from_message_id
            if last_msg_id is None:
                await safe_send_message(
                    bot, chat_id,
                    "This might be a forwarded message from a group sent by an anonymous admin. Please send the last message link instead."
                )
                return
        else:
            await safe_send_message(bot, chat_id, "Invalid input!")
            return

        try:
            chat = await bot.get_chat(source_chat_id)
            source_title = chat.title
        except (not_acceptable_406.ChannelPrivate, bad_request_400.ChannelInvalid):
            source_title = source_response.forward_from_chat.title if source_response.forward_from_chat else "Private"
        except (bad_request_400.UsernameInvalid, bad_request_400.UsernameNotModified):
            await safe_send_message(bot, chat_id, "Invalid link specified.")
            return
        except RPCError as e:
            logger.error(f"Failed to get chat {source_chat_id}: {e}")
            await safe_send_message(bot, chat_id, f"Error: {str(e)}")
            return

        try:
            skip_response = await bot.ask(chat_id, Translation.SKIP_MSG, timeout=300)
        except asyncio.TimeoutError:
            await safe_send_message(bot, chat_id, Translation.CANCEL)
            return

        if skip_response.text and skip_response.text.startswith("/"):
            await safe_send_message(bot, chat_id, Translation.CANCEL)
            return

        try:
            skip_count = int(skip_response.text)
            if skip_count < 0:
                raise ValueError("Skip count cannot be negative")
        except ValueError:
            await safe_send_message(bot, chat_id, "Invalid skip number. Please enter a non-negative integer.")
            return

        forward_id = f"{user_id}-{skip_response.id}"
        buttons = [
            [
                InlineKeyboardButton("Yes", callback_data=f"start_public_{forward_id}"),
                InlineKeyboardButton("No", callback_data="close_btn")
            ]
        ]

        await safe_send_message(
            bot,
            chat_id,
            Translation.DOUBLE_CHECK.format(
                botname=_bot['name'],
                botuname=_bot['username'],
                from_chat=source_title,
                to_chat=target_title,
                skip=skip_count
            ),
            InlineKeyboardMarkup(buttons)
        )

        # Store session data in Temp
        async with temp.lock.setdefault(forward_id, asyncio.Lock()):
            temp.sessions = getattr(temp, "sessions", {})
            temp.sessions[forward_id] = {
                "source_chat_id": source_chat_id,
                "target_chat_id": target_chat_id,
                "skip_count": skip_count,
                "last_msg_id": last_msg_id
            }
            logger.info(f"Stored session {forward_id} for user {user_id}")
