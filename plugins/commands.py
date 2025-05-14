import os
import sys
import asyncio
import logging
from typing import Optional
from pymongo.errors import PyMongoError
from platform import python_version

from database import db, mongodb_version
from config import Config, Temp
from translation import Translation
from pyrogram import Client, filters, enums
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, RPCError

logger = logging.getLogger(__name__)

# Define main buttons as a constant
MAIN_BUTTONS = [
    [InlineKeyboardButton("Main Channel", url="https://t.me/dev_gagan")],
    [
        InlineKeyboardButton("📜 Support Group", url="https://t.me/dev_gagan_support"),
        InlineKeyboardButton("🤖 Update Channel", url="https://t.me/dev_gagan_updates")
    ],
    [
        InlineKeyboardButton("🙋‍♂️ Help", callback_data="help"),
        InlineKeyboardButton("💁‍♂️ About", callback_data="about")
    ],
    [InlineKeyboardButton("⚙️ Settings", callback_data="settings#main")]
]

async def safe_send_message(bot: Client, chat_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """Send a message with FloodWait handling.

    Args:
        bot: The Pyrogram Client instance.
        chat_id: The chat ID to send the message to.
        text: The message text.
        reply_markup: Optional inline keyboard markup.

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

@Client.on_message(filters.private & filters.command("start"))
async def start(bot: Client, message: Message, temp: Temp = Temp()) -> None:
    """Handle the /start command in private chats.

    Adds the user to the database if not present and sends a welcome message with main buttons.

    Args:
        bot: The Pyrogram Client instance.
        message: The message containing the /start command.
        temp: Temporary data for runtime state.
    """
    user = message.from_user
    try:
        if not await db.is_user_exist(user.id):
            await db.add_user(user.id, user.first_name)
            logger.info(f"Added new user: {user.id} ({user.first_name})")
    except PyMongoError as e:
        logger.error(f"Failed to add user {user.id}: {e}")
        await safe_send_message(
            bot, message.chat.id,
            "Failed to access database. Please try again later."
        )
        return

    if user.id in temp.banned_users:
        await safe_send_message(
            bot, message.chat.id,
            "You are banned from using this bot."
        )
        return

    await safe_send_message(
        bot, message.chat.id,
        Translation.START_TXT.format(user.first_name),
        InlineKeyboardMarkup(MAIN_BUTTONS)
    )

@Client.on_message(filters.private & filters.command("restart") & filters.user(Config.BOT_OWNER_ID))
async def restart(bot: Client, message: Message) -> None:
    """Restart the bot (owner-only).

    Sends a restarting message, waits, confirms, and restarts the process.

    Args:
        bot: The Pyrogram Client instance.
        message: The message containing the /restart command.
    """
    msg = await safe_send_message(bot, message.chat.id, "<i>Restarting server...</i>")
    await asyncio.sleep(5)
    await msg.edit_text("<i>Server restarted successfully ✅</i>", parse_mode=enums.ParseMode.HTML)
    try:
        await db.close()  # Close database connections
    except PyMongoError as e:
        logger.error(f"Failed to close database: {e}")
    os.execl(sys.executable, sys.executable, *sys.argv)

@Client.on_callback_query(filters.regex(r"^help"))
async def helpcb(bot: Client, query: CallbackQuery) -> None:
    """Handle the 'help' callback query.

    Shows help text with navigation buttons.

    Args:
        bot: The Pyrogram Client instance.
        query: The callback query.
    """
    await query.message.edit_text(
        text=Translation.HELP_TXT,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("How to Use ❓", callback_data="how_to_use")],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="settings#main"),
                InlineKeyboardButton("📜 Status", callback_data="status")
            ],
            [InlineKeyboardButton("↩ Back", callback_data="back")]
        ]),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )
    await query.answer()

@Client.on_callback_query(filters.regex(r"^how_to_use"))
async def how_to_use(bot: Client, query: CallbackQuery) -> None:
    """Handle the 'how_to_use' callback query.

    Shows instructions for using the bot.

    Args:
        bot: The Pyrogram Client instance.
        query: The callback query.
    """
    await query.message.edit_text(
        text=Translation.HOW_USE_TXT,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="help")]]),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )
    await query.answer()

@Client.on_callback_query(filters.regex(r"^back"))
async def back(bot: Client, query: CallbackQuery) -> None:
    """Handle the 'back' callback query.

    Returns to the start message with main buttons.

    Args:
        bot: The Pyrogram Client instance.
        query: The callback query.
    """
    await query.message.edit_text(
        text=Translation.START_TXT.format(query.from_user.first_name),
        reply_markup=InlineKeyboardMarkup(MAIN_BUTTONS),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )
    await query.answer()

@Client.on_callback_query(filters.regex(r"^about"))
async def about(bot: Client, query: CallbackQuery) -> None:
    """Handle the 'about' callback query.

    Shows bot information with versions.

    Args:
        bot: The Pyrogram Client instance.
        query: The callback query.
    """
    try:
        mongo_version = await mongodb_version()
    except PyMongoError as e:
        logger.error(f"Failed to get MongoDB version: {e}")
        mongo_version = "Unknown"

    await query.message.edit_text(
        text=Translation.ABOUT_TXT.format(
            my_name=bot.first_name or "Dev Gagan Bot",
            python_version=python_version(),
            pyrogram_version=pyrogram_version,
            mongodb_version=mongo_version
        ),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="back")]]),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )
    await query.answer()

@Client.on_callback_query(filters.regex(r"^status"))
async def status(bot: Client, query: CallbackQuery) -> None:
    """Handle the 'status' callback query.

    Shows bot status with user, bot, forwarding, channel, and banned user counts.

    Args:
        bot: The Pyrogram Client instance.
        query: The callback query.
    """
    try:
        users_count, bots_count = await db.total_users_bots_count()
        total_channels = await db.total_channels()
    except PyMongoError as e:
        logger.error(f"Failed to get status data: {e}")
        await query.message.edit_text(
            text="Failed to access database. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="help")]]),
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        await query.answer()
        return

    await query.message.edit_text(
        text=Translation.STATUS_TXT.format(
            users_count, bots_count, temp.forwardings, total_channels, len(temp.banned_users)
        ),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="help")]]),
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )
    await query.answer()
