import asyncio
import time
import datetime
import logging
from typing import List, Dict, Any, Tuple, Optional
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, ChatWriteForbidden, RPCError
from pymongo.errors import PyMongoError

from database import db
from config import Config, Temp
from translation import Translation

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("broadcast") & filters.user(Config.BOT_OWNER_ID) & filters.reply)
async def broadcast(bot: Client, message: Message, temp: Temp = Temp()) -> None:
    """Broadcast a replied message to all users in the database.

    Args:
        bot: The Pyrogram Client instance.
        message: The message containing the /broadcast command and reply.
        temp: Temporary data for tracking broadcast operations.

    Example:
        Reply to a message and send /broadcast to send it to all users.
    """
    replied_message = message.reply_to_message
    chat_id = message.chat.id

    # Initialize lock and check for cancellation
    async with temp.lock.setdefault(chat_id, asyncio.Lock()):
        if temp.cancel.get(chat_id, False):
            await message.reply_text(Translation.CANCEL, parse_mode="html")
            temp.cancel[chat_id] = False
            return

        status_message = await message.reply_text(
            text="Broadcasting your messages...", parse_mode="html"
        )
        start_time = time.time()
        try:
            total_users, _ = await db.total_users_bots_count()
        except PyMongoError as e:
            logger.error(f"Failed to get total users: {e}")
            await status_message.edit_text(
                "Failed to access database. Broadcast aborted.", parse_mode="html"
            )
            return

        done = 0
        success = 0
        blocked = 0
        deleted = 0
        failed = 0

        try:
            users = await db.get_all_users()
            if not isinstance(users, (list, asyncio.Iterable)):
                logger.error("get_all_users returned invalid data: not an iterable")
                await status_message.edit_text(
                    "Invalid user data from database. Broadcast aborted.", parse_mode="html"
                )
                return

            async for user in users:
                if temp.cancel.get(chat_id, False):
                    await status_message.edit_text(
                        Translation.CANCEL, parse_mode="html"
                    )
                    temp.cancel[chat_id] = False
                    break

                user_id = user.get('id')
                if not isinstance(user_id, int):
                    logger.warning(f"Invalid user_id: {user_id}")
                    failed += 1
                    done += 1
                    continue

                is_success, status = await broadcast_messages(user_id, replied_message)
                if is_success:
                    success += 1
                    await asyncio.sleep(2)  # Avoid rate limits
                elif status == "Blocked":
                    blocked += 1
                elif status == "Deleted":
                    deleted += 1
                elif status == "Error":
                    failed += 1

                done += 1
                if done % 100 == 0:  # Configurable update frequency
                    await status_message.edit_text(
                        f"<b>Broadcast in progress:</b>\n\n"
                        f"Total Users: {total_users}\n"
                        f"Completed: {done} / {total_users}\n"
                        f"Success: {success}\n"
                        f"Blocked: {blocked}\n"
                        f"Deleted: {deleted}\n"
                        f"Failed: {failed}",
                        parse_mode="html"
                    )

            time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
            await status_message.edit_text(
                f"<b>Broadcast Completed:</b>\n"
                f"Completed in {time_taken} seconds.\n\n"
                f"Total Users: {total_users}\n"
                f"Completed: {done} / {total_users}\n"
                f"Success: {success}\n"
                f"Blocked: {blocked}\n"
                f"Deleted: {deleted}\n"
                f"Failed: {failed}",
                parse_mode="html"
            )
        except Exception as e:
            logger.error(f"Broadcast failed: {e}")
            await status_message.edit_text(
                f"Broadcast failed due to error: {str(e)}", parse_mode="html"
            )

async def broadcast_messages(user_id: int, message: Message) -> Tuple[bool, str]:
    """Send a message to a single user with error handling.

    Args:
        user_id: The ID of the user to send the message to.
        message: The message to copy to the user.

    Returns:
        Tuple[bool, str]: (Success status, Status message).

    Example:
        success, status = await broadcast_messages(123456, message)
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            await message.copy(chat_id=user_id)
            return True, "Success"
        except FloodWait as e:
            logger.warning(f"FloodWait for user {user_id}: Sleeping for {e.value} seconds (attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(e.value + 1)
        except InputUserDeactivated:
            try:
                await db.delete_user(user_id)
                logger.info(f"User {user_id} removed from database (deactivated account)")
            except PyMongoError as e:
                logger.error(f"Failed to delete user {user_id}: {e}")
            return False, "Deleted"
        except UserIsBlocked:
            logger.info(f"User {user_id} blocked the bot")
            return False, "Blocked"
        except (ChatWriteForbidden, RPCError) as e:
            logger.error(f"Failed to send message to {user_id}: {e}")
            return False, "Error"
    logger.error(f"Failed to send message to {user_id} after {max_attempts} attempts")
    return False, "Error"
