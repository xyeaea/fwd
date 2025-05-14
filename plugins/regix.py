import time
import asyncio
import logging
from typing import List, Optional, Dict, Any, Tuple
from pymongo.errors import PyMongoError
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, MessageNotModified, RPCError, ChatWriteForbidden, BadRequest

from database import db
from config import Temp
from translation import Translation
from .test import CLIENT, start_clone_bot

logger = logging.getLogger(__name__)

async def safe_send_message(bot: Client, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> Optional[Message]:
    """Send a message with FloodWait handling.

    Args:
        bot: The Pyrogram Client instance.
        chat_id: The chat ID to send the message to.
        text: The message text.
        reply_markup: Optional inline keyboard markup.

    Returns:
        Message | None: The sent message or None if failed.

    Raises:
        RPCError: If sending fails after retries.
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
            if attempt == max_attempts - 1:
                return None
    return None

async def safe_edit_message(msg: Message, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None, wait: bool = False) -> Optional[Message]:
    """Edit a message with FloodWait and MessageNotModified handling.

    Args:
        msg: The message to edit.
        text: The new text.
        reply_markup: Optional inline keyboard markup.
        wait: If True, retry on FloodWait.

    Returns:
        Message | None: The edited message or None if failed.
    """
    max_attempts = 3 if wait else 1
    for attempt in range(max_attempts):
        try:
            return await msg.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        except MessageNotModified:
            return msg
        except FloodWait as e:
            if not wait:
                return msg
            logger.warning(f"FloodWait: Sleeping for {e.value} seconds (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(e.value + 1)
        except RPCError as e:
            logger.error(f"Failed to edit message {msg.id}: {e}")
            return None
    return None

def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string (e.g., '1h 30m 45s').

    Args:
        seconds: Time in seconds.

    Returns:
        str: Formatted time string.
    """
    if seconds <= 0:
        return "0s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)

def retry_btn(forward_id: str) -> InlineKeyboardMarkup:
    """Create a retry button for the given forward ID.

    Args:
        forward_id: The forwarding session ID.

    Returns:
        InlineKeyboardMarkup: Markup with retry and close buttons.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Retry", callback_data=f"start_public_{forward_id}"),
            InlineKeyboardButton("Close", callback_data="close_btn")
        ]
    ])

@Client.on_callback_query(filters.regex(r"^start_public"))
async def start_public(bot: Client, query: CallbackQuery, temp: Temp = Temp()) -> None:
    """Handle the 'start_public_*' callback query to start forwarding messages.

    Verifies the session, starts the bot/userbot, and forwards messages from source to target channel.

    Args:
        bot: The Pyrogram Client instance.
        query: The callback query.
        temp: Temporary data for runtime state.

    Example:
        Click 'Yes' on a /fwd confirmation to trigger this callback.
    """
    user_id = query.from_user.id
    forward_id = query.data.split("_")[2]

    async with temp.lock.setdefault(user_id, asyncio.Lock()):
        temp.cancel[user_id] = False

        if temp.lock.get(user_id, False):
            await query.answer("Please wait until the previous task completes.", show_alert=True)
            return

        # Retrieve session data
        sessions = getattr(temp, "sessions", {})
        session = sessions.get(forward_id)
        if not session:
            await query.answer("You are clicking an old button.", show_alert=True)
            await query.message.delete()
            return

        status_message = await safe_edit_message(query.message, "<code>Verifying data, please wait...</code>")

        try:
            bot_data, caption, forward_tag, data, protect, button = await db.get_data(user_id)
            if not bot_data:
                await safe_edit_message(
                    status_message, "<code>You haven't added a bot. Please add using /settings!</code>", wait=True
                )
                return
        except PyMongoError as e:
            logger.error(f"Failed to get bot data for user {user_id}: {e}")
            await safe_edit_message(status_message, "Failed to access database.", wait=True)
            return

        try:
            client = await start_clone_bot(CLIENT.client(bot_data))
        except Exception as e:
            logger.error(f"Failed to start client for user {user_id}: {e}")
            await safe_edit_message(status_message, f"Error: {str(e)}", wait=True)
            return

        await safe_edit_message(status_message, "<code>Processing...</code>")

        source_chat_id = session["source_chat_id"]
        target_chat_id = session["target_chat_id"]
        if target_chat_id in temp.forward_chats:
            await query.answer("Target chat has an active task. Please wait.", show_alert=True)
            await safe_edit_message(status_message, "Target chat is busy.", wait=True)
            await stop(client, user_id)
            return

        if not await can_access_chat(client, source_chat_id):
            await safe_edit_message(
                status_message, "<b>Source chat might be private or needs admin rights.</b>",
                reply_markup=retry_btn(forward_id), wait=True
            )
            await stop(client, user_id)
            return

        if not await can_access_chat(client, target_chat_id, check_send=True):
            await safe_edit_message(
                status_message, "<b>Bot/Userbot needs admin rights in target channel.</b>",
                reply_markup=retry_btn(forward_id), wait=True
            )
            await stop(client, user_id)
            return

        try:
            await db.add_frwd(user_id)
            temp.forwardings += 1
            temp.forward_chats.append(target_chat_id)
            temp.lock[user_id] = True
        except PyMongoError as e:
            logger.error(f"Failed to add forwarding for user {user_id}: {e}")
            await safe_edit_message(status_message, "Failed to start forwarding.", wait=True)
            await stop(client, user_id)
            return

        await safe_send_message(
            client, user_id,
            "<b>Forwarding started! <a href='https://t.me/dev_gagan'>Support</a></b>"
        )
        await safe_edit_message(status_message, "<code>Starting...</code>")

        session["start_time"] = time.time()
        session["fetched"] = 0
        session["total_files"] = 0
        session["duplicate"] = 0
        session["deleted"] = 0
        session["total"] = session.get("last_msg_id", 1000)  # Estimate total messages
        session["skip"] = session.get("skip_count", 0)

        try:
            await forwarding_loop(
                client, user_id, status_message, session, caption, forward_tag, button, protect,
                sleep_time=5 if bot_data.get("is_bot", False) else 1
            )
        except Exception as e:
            logger.error(f"Error during forwarding for user {user_id}: {e}")
            await safe_edit_message(status_message, f"<b>ERROR:</b>\n<code>{str(e)}</code>", wait=True)
        finally:
            await finish_forwarding(client, user_id, session, status_message, temp)

async def forwarding_loop(
    client: Client, user_id: int, status_message: Message, session: Dict[str, Any],
    caption: Optional[str], forward_tag: bool, button: Optional[InlineKeyboardMarkup],
    protect: bool, sleep_time: float
) -> None:
    """Loop through messages and forward or copy them to the target channel.

    Args:
        client: The Pyrogram Client instance for forwarding.
        user_id: The user ID initiating the task.
        status_message: The message to update with progress.
        session: Session data with forwarding parameters.
        caption: Optional caption for copied messages.
        forward_tag: If True, forward messages in batches; else, copy individually.
        button: Optional inline keyboard markup.
        protect: If True, enable content protection.
        sleep_time: Delay between messages to avoid rate limits.
    """
    messages_batch: List[int] = []
    progress_interval = 100  # Update every 100 messages
    counter = 0

    await edit_progress(status_message, "Progressing", session)

    async for message in client.iter_messages(
        chat_id=session["source_chat_id"],
        limit=session["total"],
        offset=session["skip"]
    ):
        if await is_cancelled(client, user_id, status_message, session, temp):
            return

        counter += 1
        session["fetched"] += 1

        if message.empty or message.service:
            session["deleted"] += 1
            continue

        if counter % progress_interval == 0:
            await edit_progress(status_message, "Progressing", session)

        if forward_tag:
            messages_batch.append(message.id)
            if len(messages_batch) >= 100 or (session["total"] - session["fetched"]) <= 100:
                await forward_messages(client, messages_batch, session, protect)
                messages_batch.clear()
                await asyncio.sleep(10)
        else:
            await copy_message(client, message, session, caption, button, protect)
            session["total_files"] += 1
            await asyncio.sleep(sleep_time)

async def copy_message(
    client: Client, msg: Message, session: Dict[str, Any], caption: Optional[str],
    button: Optional[InlineKeyboardMarkup], protect: bool
) -> None:
    """Copy a single message to the target channel.

    Args:
        client: The Pyrogram Client instance.
        msg: The message to copy.
        session: Session data with target chat ID.
        caption: Optional caption for the message.
        button: Optional inline keyboard markup.
        protect: If True, enable content protection.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            if msg.media and caption:
                await client.send_cached_media(
                    chat_id=session["target_chat_id"],
                    file_id=getattr(msg, msg.media.value),
                    caption=caption,
                    reply_markup=button,
                    protect_content=protect
                )
            else:
                await client.copy_message(
                    chat_id=session["target_chat_id"],
                    from_chat_id=session["source_chat_id"],
                    message_id=msg.id,
                    caption=caption,
                    reply_markup=button,
                    protect_content=protect
                )
            return
        except FloodWait as e:
            logger.warning(f"FloodWait: Sleeping for {e.value} seconds (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(e.value + 1)
        except (ChatWriteForbidden, BadRequest, RPCError) as e:
            logger.error(f"Error copying message to {session['target_chat_id']}: {e}")
            session["deleted"] += 1
            return
    session["deleted"] += 1

async def forward_messages(client: Client, message_ids: List[int], session: Dict[str, Any], protect: bool) -> None:
    """Forward a batch of messages to the target channel.

    Args:
        client: The Pyrogram Client instance.
        message_ids: List of message IDs to forward.
        session: Session data with source and target chat IDs.
        protect: If True, enable content protection.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            await client.forward_messages(
                chat_id=session["target_chat_id"],
                from_chat_id=session["source_chat_id"],
                message_ids=message_ids,
                protect_content=protect
            )
            session["total_files"] += len(message_ids)
            return
        except FloodWait as e:
            logger.warning(f"FloodWait: Sleeping for {e.value} seconds (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(e.value + 1)
        except (ChatWriteForbidden, BadRequest, RPCError) as e:
            logger.error(f"Error forwarding messages to {session['target_chat_id']}: {e}")
            session["deleted"] += len(message_ids)
            return
    session["deleted"] += len(message_ids)

async def can_access_chat(bot: Client, chat_id: str | int, check_send: bool = False) -> bool:
    """Check if the bot can access a chat and optionally send messages.

    Args:
        bot: The Pyrogram Client instance.
        chat_id: The chat ID or username.
        check_send: If True, test sending a message.

    Returns:
        bool: True if accessible, False otherwise.
    """
    try:
        if check_send:
            msg = await bot.send_message(chat_id, "Testing")
            await msg.delete()
        else:
            await bot.get_chat(chat_id)
        return True
    except (ChatWriteForbidden, BadRequest, RPCError):
        return False

async def edit_progress(status_message: Message, title: str, session: Dict[str, Any]) -> None:
    """Update the progress message with percentage and ETA.

    Args:
        status_message: The message to update.
        title: The progress title (e.g., "Progressing").
        session: Session data with forwarding stats.
    """
    fetched = session["fetched"]
    total = session["total"]
    percentage = min(100, (fetched / max(total, 1)) * 100)

    now = time.time()
    diff = now - session["start_time"]
    speed = fetched / max(diff, 1)
    remaining = (total - fetched) / max(speed, 1)
    eta = format_time(remaining)

    text = Translation.TEXT.format(
        fetched=fetched,
        total_files=session["total_files"],
        duplicate=session["duplicate"],
        deleted=session["deleted"],
        skip=session["skip"],
        title=title,
        percentage=f"{percentage:.0f}%",
        eta=eta,
        progress_bar="◉" * int(percentage // 10)
    )
    button = InlineKeyboardMarkup([
        [InlineKeyboardButton(title, callback_data="fwrdstatus")],
        [InlineKeyboardButton("Cancel", callback_data="terminate_frwd")]
    ])
    await safe_edit_message(status_message, text, button)

async def is_cancelled(client: Client, user_id: int, status_message: Message, session: Dict[str, Any], temp: Temp) -> bool:
    """Check if the forwarding task is cancelled.

    Args:
        client: The Pyrogram Client instance.
        user_id: The user ID.
        status_message: The progress message.
        session: Session data.
        temp: Temporary data for runtime state.

    Returns:
        bool: True if cancelled, False otherwise.
    """
    if temp.cancel.get(user_id, False):
        if session["target_chat_id"] in temp.forward_chats:
            temp.forward_chats.remove(session["target_chat_id"])
        await edit_progress(status_message, "Cancelled", session)
        await safe_send_message(client, user_id, Translation.CANCEL)
        await stop(client, user_id, temp)
        return True
    return False

async def stop(client: Client, user_id: int, temp: Temp) -> None:
    """Stop the client and clean up forwarding task.

    Args:
        client: The Pyrogram Client instance.
        user_id: The user ID.
        temp: Temporary data for runtime state.
    """
    try:
        await client.stop()
    except Exception as e:
        logger.error(f"Failed to stop client for user {user_id}: {e}")
    
    try:
        await db.rmve_frwd(user_id)
    except PyMongoError as e:
        logger.error(f"Failed to remove forwarding for user {user_id}: {e}")
    
    temp.forwardings -= 1
    temp.lock[user_id] = False

async def finish_forwarding(client: Client, user_id: int, session: Dict[str, Any], status_message: Message, temp: Temp) -> None:
    """Complete the forwarding task and clean up.

    Args:
        client: The Pyrogram Client instance.
        user_id: The user ID.
        session: Session data.
        status_message: The progress message.
        temp: Temporary data for runtime state.
    """
    if session["target_chat_id"] in temp.forward_chats:
        temp.forward_chats.remove(session["target_chat_id"])
    await safe_send_message(
        client, user_id,
        "<b>🎉 Forwarding Completed! <a href='https://t.me/dev_gagan'>Support</a></b>"
    )
    await edit_progress(status_message, "Completed", session)
    await stop(client, user_id, temp)

    # Clean up session
    async with temp.lock.setdefault(user_id, asyncio.Lock()):
        if hasattr(temp, "sessions") and forward_id in temp.sessions:
            del temp.sessions[forward_id]
