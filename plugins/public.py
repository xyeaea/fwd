import re
import asyncio
from .utils import STS
from database import db
from config import temp
from translation import Translation
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions import not_acceptable_406, bad_request_400
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

#===================Run Function===================#

@Client.on_message(filters.private & filters.command(["fwd", "forward"]))
async def run(bot, message):
    user_id = message.from_user.id
    _bot = await db.get_bot(user_id)

    if not _bot:
        return await message.reply("<code>You didn't add any bot. Please add a bot using /settings!</code>")

    channels = await db.get_user_channels(user_id)
    if not channels:
        return await message.reply_text("Please set a 'to' channel in /settings before forwarding.")

    if len(channels) > 1:
        buttons = [
            [KeyboardButton(channel['title'])] for channel in channels
        ]
        buttons.append([KeyboardButton("cancel")])
        btn_data = {channel['title']: channel['chat_id'] for channel in channels}

        ask_channel = await bot.ask(
            message.chat.id,
            Translation.TO_MSG.format(_bot['name'], _bot['username']),
            reply_markup=ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
        )

        if ask_channel.text.startswith(('/', 'cancel')):
            return await message.reply_text(Translation.CANCEL, reply_markup=ReplyKeyboardRemove())

        toid = btn_data.get(ask_channel.text)
        if not toid:
            return await message.reply_text("Wrong channel chosen!", reply_markup=ReplyKeyboardRemove())
        to_title = ask_channel.text
    else:
        toid = channels[0]['chat_id']
        to_title = channels[0]['title']

    ask_source = await bot.ask(message.chat.id, Translation.FROM_MSG, reply_markup=ReplyKeyboardRemove())

    if ask_source.text and ask_source.text.startswith('/'):
        return await message.reply(Translation.CANCEL)

    chat_id, last_msg_id = None, None

    if ask_source.text and not ask_source.forward_date:
        regex = re.compile(r"(https://)?(t\.me|telegram\.me|telegram\.dog)/(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)")
        match = regex.match(ask_source.text.replace("?single", ""))
        if not match:
            return await message.reply('Invalid link.')
        
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))

        if chat_id.isdigit():
            chat_id = int("-100" + chat_id)

    elif ask_source.forward_from_chat and ask_source.forward_from_chat.type == enums.ChatType.CHANNEL:
        chat_id = ask_source.forward_from_chat.username or ask_source.forward_from_chat.id
        last_msg_id = ask_source.forward_from_message_id

        if last_msg_id is None:
            return await message.reply_text("This might be a forwarded message from a group sent by an anonymous admin. Please send the last message link instead.")
    else:
        return await message.reply_text("Invalid input!")

    # Try to get chat title
    try:
        title = (await bot.get_chat(chat_id)).title
    except (not_acceptable_406.ChannelPrivate, not_acceptable_406.ChannelPrivate, bad_request_400.ChannelInvalid):
        title = ask_source.forward_from_chat.title if ask_source.forward_from_chat else "Private"
    except (bad_request_400.UsernameInvalid, bad_request_400.UsernameNotModified):
        return await message.reply('Invalid link specified.')
    except Exception as e:
        return await message.reply(f"Error: {e}")

    skipno = await bot.ask(message.chat.id, Translation.SKIP_MSG)

    if skipno.text.startswith('/'):
        return await message.reply(Translation.CANCEL)

    forward_id = f"{user_id}-{skipno.id}"
    buttons = [[
        InlineKeyboardButton('Yes', callback_data=f"start_public_{forward_id}"),
        InlineKeyboardButton('No', callback_data="close_btn")
    ]]

    await message.reply_text(
        text=Translation.DOUBLE_CHECK.format(
            botname=_bot['name'],
            botuname=_bot['username'],
            from_chat=title,
            to_chat=to_title,
            skip=skipno.text
        ),
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    # Save session temporary
    STS(forward_id).store(chat_id, toid, int(skipno.text), int(last_msg_id))
