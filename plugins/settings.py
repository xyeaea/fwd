import asyncio
import logging
from typing import List, Optional, Dict, Any, Tuple
from pymongo.errors import PyMongoError
from pyrogram import Client, filters, enums
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, RPCError, ChatWriteForbidden

from database import db
from config import Temp
from translation import Translation
from .test import get_configs, update_configs, CLIENT, parse_buttons

logger = logging.getLogger(__name__)
CLIENT = CLIENT()

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

def main_buttons() -> InlineKeyboardMarkup:
    """Generate the main settings menu buttons.

    Returns:
        InlineKeyboardMarkup: The main settings menu.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Bots 🤖", callback_data="settings#bots"),
            InlineKeyboardButton("Channels 🏷", callback_data="settings#channels")
        ],
        [
            InlineKeyboardButton("Caption 🖋️", callback_data="settings#caption"),
            InlineKeyboardButton("MongoDB 🗃", callback_data="settings#database")
        ],
        [
            InlineKeyboardButton("Filters 🕵️‍♀️", callback_data="settings#filters"),
            InlineKeyboardButton("Button ⏹", callback_data="settings#button")
        ],
        [
            InlineKeyboardButton("Extra Settings 🧪", callback_data="settings#nextfilters")
        ],
        [
            InlineKeyboardButton("Back ↩", callback_data="back")
        ]
    ])

def size_limit(limit: Optional[str]) -> Tuple[Optional[bool], str]:
    """Convert size limit setting to human-readable format.

    Args:
        limit: The size limit setting ("None", "True", "False").

    Returns:
        Tuple[Optional[bool], str]: The limit value and description.
    """
    if limit == "None":
        return None, ""
    elif limit == "True":
        return True, "more than"
    return False, "less than"

def extract_btn(datas: Optional[List[str]]) -> List[List[InlineKeyboardButton]]:
    """Create buttons for extensions or keywords.

    Args:
        datas: List of extensions or keywords.

    Returns:
        List[List[InlineKeyboardButton]]: Button rows.
    """
    btn = []
    if datas:
        for i, data in enumerate(datas):
            if i % 5 == 0:
                btn.append([InlineKeyboardButton(data, f"settings#alert_{data}")])
            else:
                btn[-1].append(InlineKeyboardButton(data, f"settings#alert_{data}"))
    return btn

def size_button(size: int) -> InlineKeyboardMarkup:
    """Generate buttons for adjusting file size limits.

    Args:
        size: Current file size limit in MB.

    Returns:
        InlineKeyboardMarkup: Buttons for size adjustments.
    """
    buttons = [
        [
            InlineKeyboardButton("+", callback_data=f"settings#update_size-{size + 10}"),
            InlineKeyboardButton("-", callback_data=f"settings#update_size-{max(0, size - 10)}")
        ],
        [
            InlineKeyboardButton("No Limit", callback_data=f"settings#update_limit-None-{size}"),
            InlineKeyboardButton("More Than", callback_data=f"settings#update_limit-True-{size}"),
            InlineKeyboardButton("Less Than", callback_data=f"settings#update_limit-False-{size}")
        ],
        [
            InlineKeyboardButton("Back ↩", callback_data="settings#filters")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

async def filters_buttons(user_id: int) -> InlineKeyboardMarkup:
    """Generate buttons for main filters.

    Args:
        user_id: The user ID.

    Returns:
        InlineKeyboardMarkup: Filter buttons.
    """
    settings = await get_configs(user_id)
    buttons = [
        [
            InlineKeyboardButton(
                f"Documents {'✅' if settings.get('document', False) else '❌'}",
                callback_data=f"settings#updatefilter-document-{settings.get('document', False)}"
            ),
            InlineKeyboardButton(
                f"Videos {'✅' if settings.get('video', False) else '❌'}",
                callback_data=f"settings#updatefilter-video-{settings.get('video', False)}"
            )
        ],
        [
            InlineKeyboardButton(
                f"Photos {'✅' if settings.get('photo', False) else '❌'}",
                callback_data=f"settings#updatefilter-photo-{settings.get('photo', False)}"
            ),
            InlineKeyboardButton(
                f"Audio {'✅' if settings.get('audio', False) else '❌'}",
                callback_data=f"settings#updatefilter-audio-{settings.get('audio', False)}"
            )
        ],
        [
            InlineKeyboardButton(
                f"Size Limit ({settings.get('file_size', 0)} MB)",
                callback_data="settings#file_size"
            )
        ],
        [
            InlineKeyboardButton("Extensions", callback_data="settings#get_extension"),
            InlineKeyboardButton("Keywords", callback_data="settings#get_keyword")
        ],
        [
            InlineKeyboardButton("More Filters ➡️", callback_data="settings#nextfilters"),
            InlineKeyboardButton("Back ↩", callback_data="settings#main")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

async def next_filters_buttons(user_id: int) -> InlineKeyboardMarkup:
    """Generate buttons for additional filters.

    Args:
        user_id: The user ID.

    Returns:
        InlineKeyboardMarkup: Additional filter buttons.
    """
    settings = await get_configs(user_id)
    buttons = [
        [
            InlineKeyboardButton(
                f"Polls {'✅' if settings.get('poll', False) else '❌'}",
                callback_data=f"settings#updatefilter-poll-{settings.get('poll', False)}"
            ),
            InlineKeyboardButton(
                f"Protected Content {'✅' if settings.get('protect', False) else '❌'}",
                callback_data=f"settings#updatefilter-protect-{settings.get('protect', False)}"
            )
        ],
        [
            InlineKeyboardButton("⬅️ Back to Filters", callback_data="settings#filters"),
            InlineKeyboardButton("Back ↩", callback_data="settings#main")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

@Client.on_message(filters.command("settings") & filters.private)
async def settings(bot: Client, message: Message, temp: Temp = Temp()) -> None:
    """Handle the /settings command to display the settings menu.

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
            await message.delete()
            await safe_send_message(
                bot, user_id, "<b>Change your settings as you wish</b>", main_buttons()
            )
        except RPCError as e:
            logger.error(f"Failed to send settings menu for user {user_id}: {e}")
            await safe_send_message(bot, user_id, "Failed to display settings.")

@Client.on_callback_query(filters.regex(r"^settings"))
async def settings_query(bot: Client, query: CallbackQuery, temp: Temp = Temp()) -> None:
    """Handle settings callback queries to navigate and update user settings.

    Args:
        bot: The Pyrogram Client instance.
        query: The callback query.
        temp: Temporary data for runtime state.
    """
    user_id = query.from_user.id
    async with temp.lock.setdefault(user_id, asyncio.Lock()):
        if user_id in temp.banned_users:
            await query.answer("You are banned from using this bot.", show_alert=True)
            return

        try:
            _, action = query.data.split("#")
        except ValueError:
            await query.answer("Invalid callback data.", show_alert=True)
            return

        back_button = [[InlineKeyboardButton("Back ↩", callback_data="settings#main")]]

        if action == "main":
            await safe_edit_message(
                query.message, "<b>Change your settings as you wish</b>", main_buttons()
            )

        elif action == "bots":
            try:
                bot_data = await db.get_bot(user_id)
                buttons = [
                    [InlineKeyboardButton(bot_data['name'], callback_data="settings#editbot")]
                    if bot_data else
                    [
                        InlineKeyboardButton("Add Bot ✚", callback_data="settings#addbot"),
                        InlineKeyboardButton("Add Userbot ✚", callback_data="settings#adduserbot")
                    ],
                    [InlineKeyboardButton("Back ↩", callback_data="settings#main")]
                ]
                await safe_edit_message(
                    query.message,
                    "<b><u>My Bots</u></b>\n\n<b>You can manage your bots here</b>",
                    InlineKeyboardMarkup(buttons)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get bot for user {user_id}: {e}")
                await safe_edit_message(query.message, "Failed to access database.")

        elif action == "addbot":
            await query.message.delete()
            try:
                result = await CLIENT.add_bot(bot, query)
                if result is True:
                    await safe_send_message(
                        bot, user_id, "<b>Bot token successfully added to database</b>",
                        InlineKeyboardMarkup(back_button)
                    )
                else:
                    await safe_send_message(bot, user_id, "<b>Failed to add bot</b>")
            except Exception as e:
                logger.error(f"Failed to add bot for user {user_id}: {e}")
                await safe_send_message(bot, user_id, f"<b>Error: {str(e)}</b>")

        elif action == "adduserbot":
            await query.message.delete()
            try:
                result = await CLIENT.add_session(bot, query)
                if result is True:
                    await safe_send_message(
                        bot, user_id, "<b>Session successfully added to database</b>",
                        InlineKeyboardMarkup(back_button)
                    )
                else:
                    await safe_send_message(bot, user_id, "<b>Failed to add userbot</b>")
            except Exception as e:
                logger.error(f"Failed to add userbot for user {user_id}: {e}")
                await safe_send_message(bot, user_id, f"<b>Error: {str(e)}</b>")

        elif action == "channels":
            try:
                channels = await db.get_user_channels(user_id)
                buttons = [
                    [InlineKeyboardButton(channel['title'], callback_data=f"settings#editchannels_{channel['chat_id']}")]
                    for channel in channels
                ]
                buttons.extend([
                    [InlineKeyboardButton("Add Channel ✚", callback_data="settings#addchannel")],
                    [InlineKeyboardButton("Back ↩", callback_data="settings#main")]
                ])
                await safe_edit_message(
                    query.message,
                    "<b><u>My Channels</u></b>\n\n<b>You can manage your target chats here</b>",
                    InlineKeyboardMarkup(buttons)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get channels for user {user_id}: {e}")
                await safe_edit_message(query.message, "Failed to access database.")

        elif action == "addchannel":
            await query.message.delete()
            try:
                text_msg = await safe_send_message(
                    bot, user_id,
                    "<b>❪ SET TARGET CHAT ❫</b>\n\nForward a message from your target chat\n<code>/cancel</code> - cancel this process"
                )
                if not text_msg:
                    return

                chat_response = await bot.listen(chat_id=user_id, timeout=120)
                if chat_response.text == "/cancel" or temp.cancel.get(user_id, False):
                    temp.cancel[user_id] = False
                    await chat_response.delete()
                    await safe_edit_message(text_msg, Translation.CANCEL, InlineKeyboardMarkup(back_button))
                    return
                elif not chat_response.forward_date:
                    await chat_response.delete()
                    await safe_edit_message(text_msg, "<b>This is not a forwarded message</b>")
                    return

                chat_id = chat_response.forward_from_chat.id
                title = chat_response.forward_from_chat.title
                username = chat_response.forward_from_chat.username or "private"
                username = f"@{username}" if username else username

                try:
                    chat_added = await db.add_channel(user_id, chat_id, title, username)
                    await chat_response.delete()
                    await safe_edit_message(
                        text_msg,
                        "<b>Successfully updated</b>" if chat_added else "<b>This channel is already added</b>",
                        InlineKeyboardMarkup(back_button)
                    )
                except PyMongoError as e:
                    logger.error(f"Failed to add channel for user {user_id}: {e}")
                    await safe_edit_message(text_msg, "<b>Failed to add channel</b>")
            except asyncio.TimeoutError:
                await safe_edit_message(text_msg, Translation.CANCEL, InlineKeyboardMarkup(back_button))

        elif action == "editbot":
            try:
                bot_data = await db.get_bot(user_id)
                if not bot_data:
                    await safe_edit_message(query.message, "<b>No bot found</b>")
                    return
                text = Translation.BOT_DETAILS if bot_data['is_bot'] else Translation.USER_DETAILS
                buttons = [
                    [InlineKeyboardButton("Remove ❌", callback_data="settings#removebot")],
                    [InlineKeyboardButton("Back ↩", callback_data="settings#bots")]
                ]
                await safe_edit_message(
                    query.message,
                    text.format(bot_data['name'], bot_data['id'], bot_data['username']),
                    InlineKeyboardMarkup(buttons)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get bot details for user {user_id}: {e}")
                await safe_edit_message(query.message, "Failed to access database.")

        elif action == "removebot":
            try:
                await db.remove_bot(user_id)
                await safe_edit_message(
                    query.message, "<b>Successfully removed bot</b>", InlineKeyboardMarkup(back_button)
                )
            except PyMongoError as e:
                logger.error(f"Failed to remove bot for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to remove bot</b>")

        elif action.startswith("editchannels_"):
            chat_id = action.split("_")[1]
            try:
                chat = await db.get_channel_details(user_id, chat_id)
                buttons = [
                    [InlineKeyboardButton("Remove ❌", callback_data=f"settings#removechannel_{chat_id}")],
                    [InlineKeyboardButton("Back ↩", callback_data="settings#channels")]
                ]
                await safe_edit_message(
                    query.message,
                    f"<b><u>📄 CHANNEL DETAILS</u></b>\n\n"
                    f"<b>Title:</b> <code>{chat['title']}</code>\n"
                    f"<b>Channel ID:</b> <code>{chat['chat_id']}</code>\n"
                    f"<b>Username:</b> {chat['username']}",
                    InlineKeyboardMarkup(buttons)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get channel details for user {user_id}: {e}")
                await safe_edit_message(query.message, "Failed to access database.")

        elif action.startswith("removechannel_"):
            chat_id = action.split("_")[1]
            try:
                await db.remove_channel(user_id, chat_id)
                await safe_edit_message(
                    query.message, "<b>Successfully removed channel</b>", InlineKeyboardMarkup(back_button)
                )
            except PyMongoError as e:
                logger.error(f"Failed to remove channel for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to remove channel</b>")

        elif action == "caption":
            try:
                data = await get_configs(user_id)
                caption = data.get('caption')
                buttons = [
                    [
                        InlineKeyboardButton("Add Caption ✚", callback_data="settings#addcaption")
                        if caption is None else
                        InlineKeyboardButton("See Caption", callback_data="settings#seecaption"),
                        InlineKeyboardButton("Delete Caption 🗑️", callback_data="settings#deletecaption")
                        if caption is not None else None
                    ],
                    [InlineKeyboardButton("Back ↩", callback_data="settings#main")]
                ]
                buttons = [[b for b in row if b] for row in buttons]  # Remove None
                await safe_edit_message(
                    query.message,
                    "<b><u>Custom Caption</u></b>\n\n"
                    "<b>You can set a custom caption for videos and documents. Uses default caption if not set.</b>\n\n"
                    "<b><u>Available Fillings:</u></b>\n"
                    "- <code>{filename}</code>: Filename\n"
                    "- <code>{size}</code>: File size\n"
                    "- <code>{caption}</code>: Default caption",
                    InlineKeyboardMarkup(buttons)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get configs for user {user_id}: {e}")
                await safe_edit_message(query.message, "Failed to access database.")

        elif action == "seecaption":
            try:
                data = await get_configs(user_id)
                buttons = [
                    [InlineKeyboardButton("Edit Caption 🖋️", callback_data="settings#addcaption")],
                    [InlineKeyboardButton("Back ↩", callback_data="settings#caption")]
                ]
                await safe_edit_message(
                    query.message,
                    f"<b><u>Your Custom Caption</u></b>\n\n<code>{data['caption']}</code>",
                    InlineKeyboardMarkup(buttons)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get caption for user {user_id}: {e}")
                await safe_edit_message(query.message, "Failed to access database.")

        elif action == "deletecaption":
            try:
                await update_configs(user_id, 'caption', None)
                await safe_edit_message(
                    query.message, "<b>Successfully deleted caption</b>", InlineKeyboardMarkup(back_button)
                )
            except PyMongoError as e:
                logger.error(f"Failed to delete caption for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to delete caption</b>")

        elif action == "addcaption":
            await query.message.delete()
            try:
                text_msg = await safe_send_message(
                    bot, user_id,
                    "<b>Send your custom caption</b>\n<code>/cancel</code> - cancel this process"
                )
                if not text_msg:
                    return

                caption_response = await bot.listen(chat_id=user_id, timeout=120)
                if caption_response.text == "/cancel" or temp.cancel.get(user_id, False):
                    temp.cancel[user_id] = False
                    await caption_response.delete()
                    await safe_edit_message(text_msg, Translation.CANCEL, InlineKeyboardMarkup(back_button))
                    return

                try:
                    caption_response.text.format(filename='', size='', caption='')
                except KeyError as e:
                    await caption_response.delete()
                    await safe_edit_message(
                        text_msg, f"<b>Wrong filling {e} used in your caption. Change it.</b>",
                        InlineKeyboardMarkup(back_button)
                    )
                    return

                await update_configs(user_id, 'caption', caption_response.text)
                await caption_response.delete()
                await safe_edit_message(
                    text_msg, "<b>Successfully updated caption</b>", InlineKeyboardMarkup(back_button)
                )
            except asyncio.TimeoutError:
                await safe_edit_message(text_msg, Translation.CANCEL, InlineKeyboardMarkup(back_button))

        elif action == "button":
            try:
                data = await get_configs(user_id)
                button = data.get('button')
                buttons = [
                    [
                        InlineKeyboardButton("Add Button ✚", callback_data="settings#addbutton")
                        if button is None else
                        InlineKeyboardButton("See Button", callback_data="settings#seebutton"),
                        InlineKeyboardButton("Remove Button 🗑️", callback_data="settings#deletebutton")
                        if button is not None else None
                    ],
                    [InlineKeyboardButton("Back ↩", callback_data="settings#main")]
                ]
                buttons = [[b for b in row if b] for row in buttons]
                await safe_edit_message(
                    query.message,
                    "<b><u>Custom Button</u></b>\n\n"
                    "<b>You can set an inline button for messages.</b>\n\n"
                    "<b><u>Format:</u></b>\n<code>[Forward Bot][buttonurl:https://t.me/devgaganbot]</code>",
                    InlineKeyboardMarkup(buttons)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get button for user {user_id}: {e}")
                await safe_edit_message(query.message, "Failed to access database.")

        elif action == "addbutton":
            await query.message.delete()
            try:
                text_msg = await safe_send_message(
                    bot, user_id,
                    "<b>Send your custom button</b>\n\n"
                    "<b>Format:</b>\n<code>[Forward Bot][buttonurl:https://t.me/devgaganbot]</code>\n"
                    "<code>/cancel</code> - cancel this process"
                )
                if not text_msg:
                    return

                button_response = await bot.listen(chat_id=user_id, timeout=120)
                if button_response.text == "/cancel" or temp.cancel.get(user_id, False):
                    temp.cancel[user_id] = False
                    await button_response.delete()
                    await safe_edit_message(text_msg, Translation.CANCEL, InlineKeyboardMarkup(back_button))
                    return

                parsed_button = parse_buttons(button_response.text)
                if not parsed_button:
                    await button_response.delete()
                    await safe_edit_message(text_msg, "<b>Invalid button format</b>")
                    return

                await update_configs(user_id, 'button', button_response.text)
                await button_response.delete()
                await safe_edit_message(
                    text_msg, "<b>Successfully added button</b>", InlineKeyboardMarkup(back_button)
                )
            except asyncio.TimeoutError:
                await safe_edit_message(text_msg, Translation.CANCEL, InlineKeyboardMarkup(back_button))

        elif action == "seebutton":
            try:
                data = await get_configs(user_id)
                button = parse_buttons(data['button'], markup=False)
                button.append([InlineKeyboardButton("Back ↩", callback_data="settings#button")])
                await safe_edit_message(
                    query.message, "<b><u>Your Custom Button</u></b>", InlineKeyboardMarkup(button)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get button for user {user_id}: {e}")
                await safe_edit_message(query.message, "Failed to access database.")

        elif action == "deletebutton":
            try:
                await update_configs(user_id, 'button', None)
                await safe_edit_message(
                    query.message, "<b>Successfully deleted button</b>", InlineKeyboardMarkup(back_button)
                )
            except PyMongoError as e:
                logger.error(f"Failed to delete button for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to delete button</b>")

        elif action == "database":
            try:
                data = await get_configs(user_id)
                db_uri = data.get('db_uri')
                buttons = [
                    [
                        InlineKeyboardButton("Add URL ✚", callback_data="settings#addurl")
                        if db_uri is None else
                        InlineKeyboardButton("See URL", callback_data="settings#seeurl"),
                        InlineKeyboardButton("Remove URL 🗑️", callback_data="settings#deleteurl")
                        if db_uri is not None else None
                    ],
                    [InlineKeyboardButton("Back ↩", callback_data="settings#main")]
                ]
                buttons = [[b for b in row if b] for row in buttons]
                await safe_edit_message(
                    query.message,
                    "<b><u>Database</u></b>\n\n"
                    "<b>Database is required to store your duplicate messages permanently. "
                    "Otherwise, stored duplicate media may disappear after bot restart.</b>",
                    InlineKeyboardMarkup(buttons)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get database config for user {user_id}: {e}")
                await safe_edit_message(query.message, "Failed to access database.")

        elif action == "addurl":
            await query.message.delete()
            try:
                text_msg = await bot.ask(
                    user_id,
                    "<b>Please send your MongoDB URL.</b>\n\n"
                    "<i>Get your MongoDB URL from <a href='https://mongodb.com'>here</a></i>\n"
                    "<code>/cancel</code> - cancel this process",
                    disable_web_page_preview=True,
                    timeout=120
                )
                if text_msg.text == "/cancel" or temp.cancel.get(user_id, False):
                    temp.cancel[user_id] = False
                    await safe_send_message(
                        bot, user_id, Translation.CANCEL, InlineKeyboardMarkup(back_button)
                    )
                    return

                if not text_msg.text.startswith("mongodb+srv://") or not text_msg.text.endswith("majority"):
                    await safe_send_message(
                        bot, user_id, "<b>Invalid MongoDB URL</b>", InlineKeyboardMarkup(back_button)
                    )
                    return

                await update_configs(user_id, 'db_uri', text_msg.text)
                await safe_send_message(
                    bot, user_id, "<b>Successfully added database URL</b>", InlineKeyboardMarkup(back_button)
                )
            except asyncio.TimeoutError:
                await safe_send_message(
                    bot, user_id, Translation.CANCEL, InlineKeyboardMarkup(back_button)
                )

        elif action == "seeurl":
            try:
                data = await get_configs(user_id)
                await query.answer("Database URL is set (not shown for security).", show_alert=True)
            except PyMongoError as e:
                logger.error(f"Failed to get database URL for user {user_id}: {e}")
                await query.answer("Failed to access database.", show_alert=True)

        elif action == "deleteurl":
            try:
                await update_configs(user_id, 'db_uri', None)
                await safe_edit_message(
                    query.message, "<b>Successfully deleted database URL</b>", InlineKeyboardMarkup(back_button)
                )
            except PyMongoError as e:
                logger.error(f"Failed to delete database URL for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to delete database URL</b>")

        elif action == "filters":
            await safe_edit_message(
                query.message,
                "<b><u>💠 Custom Filters 💠</u></b>\n\n"
                "<b>Configure the type of messages you want to forward</b>",
                await filters_buttons(user_id)
            )

        elif action == "nextfilters":
            await safe_edit_message(query.message, query.message.text, await next_filters_buttons(user_id))

        elif action.startswith("updatefilter-"):
            try:
                _, key, value = action.split("-")
                new_value = not (value == "True")
                await update_configs(user_id, key, new_value)
                reply_markup = (
                    await next_filters_buttons(user_id)
                    if key in ['poll', 'protect']
                    else await filters_buttons(user_id)
                )
                await safe_edit_message(query.message, query.message.text, reply_markup)
            except PyMongoError as e:
                logger.error(f"Failed to update filter {key} for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to update filter</b>")

        elif action == "file_size":
            try:
                settings = await get_configs(user_id)
                size = settings.get('file_size', 0)
                _, limit = size_limit(settings.get('size_limit'))
                await safe_edit_message(
                    query.message,
                    f"<b><u>Size Limit</u></b>\n\n"
                    f"<b>You can set a file size limit for forwarding</b>\n\n"
                    f"<b>Status:</b> Files with {limit} <code>{size} MB</code> will forward",
                    size_button(size)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get size limit for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to access database</b>")

        elif action.startswith("update_size-"):
            try:
                size = int(action.split("-")[1])
                if size < 0 or size > 2000:
                    await query.answer("Size limit must be between 0 and 2000 MB.", show_alert=True)
                    return
                await update_configs(user_id, 'file_size', size)
                settings = await get_configs(user_id)
                _, limit = size_limit(settings.get('size_limit'))
                await safe_edit_message(
                    query.message,
                    f"<b><u>Size Limit</u></b>\n\n"
                    f"<b>You can set a file size limit for forwarding</b>\n\n"
                    f"<b>Status:</b> Files with {limit} <code>{size} MB</code> will forward",
                    size_button(size)
                )
            except PyMongoError as e:
                logger.error(f"Failed to update size limit for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to update size limit</b>")

        elif action.startswith("update_limit-"):
            try:
                _, limit, size = action.split("-")
                limit, sts = size_limit(limit)
                await update_configs(user_id, 'size_limit', limit)
                await safe_edit_message(
                    query.message,
                    f"<b><u>Size Limit</u></b>\n\n"
                    f"<b>You can set a file size limit for forwarding</b>\n\n"
                    f"<b>Status:</b> Files with {sts} <code>{size} MB</code> will forward",
                    size_button(int(size))
                )
            except PyMongoError as e:
                logger.error(f"Failed to update size limit for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to update size limit</b>")

        elif action == "add_extension":
            await query.message.delete()
            try:
                text_msg = await bot.ask(
                    user_id,
                    "<b>Please send your extensions (separated by space)</b>\n"
                    "<code>/cancel</code> - cancel this process",
                    timeout=120
                )
                if text_msg.text == "/cancel" or temp.cancel.get(user_id, False):
                    temp.cancel[user_id] = False
                    await safe_send_message(
                        bot, user_id, Translation.CANCEL, InlineKeyboardMarkup(back_button)
                    )
                    return
               keywords = text_msg.text.split()
                current_keywords = (await get_configs(user_id)).get('keywords', [])
                updated_keywords = list(set(current_keywords + keywords))
                await update_configs(user_id, 'keywords', updated_keywords or None)
                await safe_send_message(
                    bot, user_id, "<b>Successfully updated keywords</b>", InlineKeyboardMarkup(back_button)
                )
            except asyncio.TimeoutError:
                await safe_send_message(
                    bot, user_id, Translation.CANCEL, InlineKeyboardMarkup(back_button)
                )

        elif action == "get_keyword":
            try:
                keywords = (await get_configs(user_id)).get('keywords', [])
                btn = extract_btn(keywords)
                btn.extend([
                    [InlineKeyboardButton("Add ✚", callback_data="settings#add_keyword")],
                    [InlineKeyboardButton("Remove All 🗑️", callback_data="settings#rmve_all_keyword")],
                    [InlineKeyboardButton("Back ↩", callback_data="settings#main")]
                ])
                await safe_edit_message(
                    query.message,
                    "<b><u>Keywords</u></b>\n\n"
                    "<b>Files with these keywords in the filename will be forwarded</b>",
                    InlineKeyboardMarkup(btn)
                )
            except PyMongoError as e:
                logger.error(f"Failed to get keywords for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to access database</b>")

        elif action == "rmve_all_keyword":
            try:
                await update_configs(user_id, 'keywords', None)
                await safe_edit_message(
                    query.message, "<b>Successfully deleted all keywords</b>", InlineKeyboardMarkup(back_button)
                )
            except PyMongoError as e:
                logger.error(f"Failed to delete keywords for user {user_id}: {e}")
                await safe_edit_message(query.message, "<b>Failed to delete keywords</b>")

        elif action.startswith("alert_"):
            alert = action.split("_")[1]
            await query.answer(f"Item: {alert}", show_alert=True)

        await query.answer()
