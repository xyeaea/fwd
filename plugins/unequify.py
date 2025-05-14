import re
import asyncio
import logging
from typing import Dict, Any, Optional
from pymongo.errors import PyMongoError
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, RPCError, ChatWriteForbidden, ChatAdminRequired

from database import db
from config import Temp
from translation import Translation
from .test import CLIENT, start_clone_bot

logger = logging.getLogger(__name__)

# Constants
BATCH_SIZE = 100
PROGRESS_INTERVAL = 10000
LINK_REGEX = re.compile(r"(https?://)?(t\.me/|telegram\.(me|dog)/)(c/)?([a-zA-Z_0-9]+|\d+)/(\d+)$")

# Inline Keyboards
COMPLETED_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("Support ⚡", url="https://t.me/dev_gagan")],
    [InlineKeyboardButton("Updates 📢", url="https://t.me/dev_gagan_updates")],
    [InlineKeyboardButton("Back ↩", callback_data="back")]
])
CANCEL_BTN = InlineKeyboardMarkup([
    [InlineKeyboardButton("Cancel 🚫", callback_data="terminate_frwd")]
])

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

async def safe_edit_message(msg: Message, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> Optional[Message]:
    """Edit a message with FloodWait handling.

    Args:
        msg: The message to edit.
        text: The new text.
        reply_markup: Optional inline keyboard markup.

    Returns:
        Message | None: The edited message or None if failed.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            return await msg.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        except FloodWait as e:
            logger.warning(f"FloodWait: Sleeping for {e.value} seconds (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(e.value + 1)
        except RPCError as e:
            logger.error(f"Failed to edit message {msg.id}: {e}")
            return None
    return None

async def validate_target_input(client: Client, user_id: int, target: Message) -> Optional[tuple[str, int]]:
    """Validate the target chat input (link or forwarded message).

    Args:
        client: The Pyrogram Client instance.
        user_id: The user ID.
        target: The message containing the link or forwarded message.

    Returns:
        tuple[str, int] | None: The chat_id and last message ID, or None if invalid.
    """
    if target.text and target.text.startswith("/"):
        await safe_send_message(client, user_id, Translation.CANCEL)
        return None

    if target.text:
        match = LINK_REGEX.match(target.text.replace("?single", ""))
        if not match:
            await safe_send_message(client, user_id, "<b>Invalid link</b>")
            return None
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)
    elif target.forward_from_chat and target.forward_from_chat.type in (enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP):
        last_msg_id = target.forward_from_message_id
        chat_id = target.forward_from_chat.username or target.forward_from_chat.id
    else:
        await safe_send_message(client, user_id, "<b>Invalid input</b>")
        return None
    return chat_id, last_msg_id

async def verify_userbot_permissions(bot: Client, chat_id: str, user_id: int, bot_details: Dict[str, Any]) -> bool:
    """Verify if the userbot has admin permissions in the target chat.

    Args:
        bot: The userbot Client instance.
        chat_id: The target chat ID.
        user_id: The user ID.
        bot_details: The userbot details from the database.

    Returns:
        bool: True if permissions are sufficient, False otherwise.
    """
    try:
        test_msg = await bot.send_message(chat_id, "Testing permissions")
        await test_msg.delete()
        return True
    except (ChatWriteForbidden, ChatAdminRequired, RPCError) as e:
        logger.error(f"Userbot lacks permissions in {chat_id}: {e}")
        await safe_send_message(
            bot, user_id,
            "<b>Please make your userbot admin in the target chat with full permissions</b>",
            InlineKeyboardMarkup([[InlineKeyboardButton("Userbot", url=f"tg://user?id={bot_details['id']}")]])
        )
        return False

@Client.on_message(filters.command("unequify") & filters.private)
async def unequify(client: Client, message: Message, temp: Temp = Temp()) -> None:
    """Remove duplicate documents from a target chat using a userbot.

    The command prompts for a target chat (via forwarded message or link), confirms the action,
    and deletes duplicate documents based on file_unique_id.

    Args:
        client: The Pyrogram Client instance.
        message: The message containing the command.
        temp: Temporary data for runtime state.

    Example:
        /unequify
        -> Forward a message from the target chat
        -> /yes to confirm
        -> Deletes duplicates and reports progress
    """
    user_id = message.from_user.id
    async with temp.lock.setdefault(user_id, asyncio.Lock()):
        if user_id in temp.banned_users:
            await safe_send_message(client, user_id, "<b>You are banned from using this bot</b>")
            return

        if temp.lock.get(user_id, False):
            await safe_send_message(client, user_id, "<b>Please wait until the previous task completes</b>")
            return

        try:
            bot_details = await db.get_bot(user_id)
            if not bot_details or bot_details['is_bot']:
                await safe_send_message(
                    client, user_id,
                    "<b>A userbot is required for this process. Add one using /settings</b>"
                )
                return
        except PyMongoError as e:
            logger.error(f"Failed to get bot for user {user_id}: {e}")
            await safe_send_message(client, user_id, "<b>Failed to access database</b>")
            return

        temp.cancel[user_id] = False
        temp.lock[user_id] = True
        try:
            target = await client.ask(
                user_id,
                "<b>Forward the last message from the target chat or send its link</b>\n"
                "<code>/cancel</code> - cancel this process",
                timeout=120
            )
            target_info = await validate_target_input(client, user_id, target)
            if not target_info:
                temp.lock[user_id] = False
                return
            chat_id, _ = target_info

            confirm = await client.ask(
                user_id,
                "<b>Send /yes to start the process or /no to cancel</b>",
                timeout=60
            )
            if confirm.text.lower() != "/yes":
                await safe_send_message(client, user_id, Translation.CANCEL)
                temp.lock[user_id] = False
                return

            sts = await safe_send_message(client, user_id, "<b>Processing...</b>")
            if not sts:
                temp.lock[user_id] = False
                return

            try:
                bot = await start_clone_bot(CLIENT().client(bot_details))
            except RPCError as e:
                logger.error(f"Failed to start userbot for user {user_id}: {e}")
                await safe_edit_message(sts, f"<b>Error:</b> <code>{str(e)}</code>")
                temp.lock[user_id] = False
                return

            if not await verify_userbot_permissions(bot, chat_id, user_id, bot_details):
                await bot.stop()
                temp.lock[user_id] = False
                return

            messages = set()
            duplicates = []
            total = deleted = 0
            try:
                await safe_edit_message(
                    sts,
                    Translation.DUPLICATE_TEXT.format(total, deleted, "Processing"),
                    CANCEL_BTN
                )
                async for msg in bot.search_messages(chat_id=chat_id, filter=enums.MessagesFilter.DOCUMENT):
                    if temp.cancel.get(user_id, False):
                        await safe_edit_message(
                            sts,
                            Translation.DUPLICATE_TEXT.format(total, deleted, "Cancelled"),
                            COMPLETED_BTN
                        )
                        await bot.stop()
                        temp.lock[user_id] = False
                        return

                    file = msg.document
                    file_id = file.file_unique_id  # Use native file_unique_id
                    if file_id in messages:
                        duplicates.append(msg.id)
                    else:
                        messages.add(file_id)
                    total += 1

                    if total % PROGRESS_INTERVAL == 0:
                        await safe_edit_message(
                            sts,
                            Translation.DUPLICATE_TEXT.format(total, deleted, "Processing"),
                            CANCEL_BTN
                        )

                    if len(duplicates) >= BATCH_SIZE:
                        try:
                            await bot.delete_messages(chat_id, duplicates)
                            deleted += len(duplicates)
                            await safe_edit_message(
                                sts,
                                Translation.DUPLICATE_TEXT.format(total, deleted, "Processing"),
                                CANCEL_BTN
                            )
                            duplicates = []
                        except RPCError as e:
                            logger.error(f"Failed to delete messages in {chat_id}: {e}")
                            continue

                if duplicates:
                    try:
                        await bot.delete_messages(chat_id, duplicates)
                        deleted += len(duplicates)
                    except RPCError as e:
                        logger.error(f"Failed to delete final duplicates in {chat_id}: {e}")

                await safe_edit_message(
                    sts,
                    Translation.DUPLICATE_TEXT.format(total, deleted, "Completed"),
                    COMPLETED_BTN
                )
            except RPCError as e:
                logger.error(f"Error during unequify for user {user_id}: {e}")
                await safe_edit_message(sts, f"<b>Error:</b> <code>{str(e)}</code>")
            finally:
                await bot.stop()
                temp.lock[user_id] = False

        except asyncio.TimeoutError:
            await safe_send_message(client, user_id, Translation.CANCEL)
            temp.lock[user_id] = False

@Client.on_callback_query(filters.regex(r"^terminate_frwd"))
async def terminate_frwd(client: Client, query: CallbackQuery, temp: Temp = Temp()) -> None:
    """Handle the terminate_frwd callback to cancel the unequify process.

    Args:
        client: The Pyrogram Client instance.
        query: The callback query.
        temp: Temporary data for runtime state.
    """
    user_id = query.from_user.id
    async with temp.lock.setdefault(user_id, asyncio.Lock()):
        if user_id in temp.banned_users:
            await query.answer("You are banned from using this bot.", show_alert=True)
            return

        temp.cancel[user_id] = True
        await query.answer("Process cancellation requested.", show_alert=True)
