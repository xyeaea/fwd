import os
import sys
import math
import time
import asyncio
import logging
from .utils import STS
from database import db
from .test import CLIENT, start_clone_bot
from config import Config, temp
from translation import Translation
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified, RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message

CLIENT = CLIENT()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
TEXT = Translation.TEXT

@Client.on_callback_query(filters.regex(r'^start_public'))
async def pub_(bot, message):
    user_id = message.from_user.id
    temp.CANCEL[user_id] = False
    frwd_id = message.data.split("_")[2]

    if temp.lock.get(user_id) == "True":
        return await message.answer("Please wait until the previous task completes.", show_alert=True)

    sts = STS(frwd_id)
    if not sts.verify():
        await message.answer("You are clicking an old button.", show_alert=True)
        return await message.message.delete()

    i = sts.get(full=True)
    if i.TO in temp.IS_FRWD_CHAT:
        return await message.answer("Target chat has an active task. Please wait.", show_alert=True)

    m = await safe_edit(message.message, "<code>Verifying data, please wait...</code>")

    _bot, caption, forward_tag, data, protect, button = await sts.get_data(user_id)
    if not _bot:
        return await safe_edit(m, "<code>You haven't added a bot. Please add using /settings!</code>", wait=True)

    try:
        client = await start_clone_bot(CLIENT.client(_bot))
    except Exception as e:
        return await m.edit(str(e))

    await safe_edit(m, "<code>Processing...</code>")

    if not await can_access_chat(client, sts.get("FROM")):
        await safe_edit(m, f"**Source chat might be private or needs admin rights.**", retry_btn(frwd_id), True)
        return await stop(client, user_id)

    if not await can_access_chat(client, i.TO, check_send=True):
        await safe_edit(m, f"**Bot/Userbot needs admin rights in target channel.**", retry_btn(frwd_id), True)
        return await stop(client, user_id)

    temp.forwardings += 1
    await db.add_frwd(user_id)
    await send_message(client, user_id, "<b>Forwarding started! <a href='https://t.me/dev_gagan'>Support</a></b>")

    sts.add(time=True)
    temp.IS_FRWD_CHAT.append(i.TO)
    temp.lock[user_id] = True

    sleep_time = 5 if _bot['is_bot'] else 1
    m = await safe_edit(m, "<code>Starting...</code>")

    try:
        await forwarding_loop(client, user_id, m, sts, caption, forward_tag, button, protect, sleep_time)
    except Exception as e:
        logger.error(f"Error during forwarding: {e}")
        await safe_edit(m, f'<b>ERROR:</b>\n<code>{e}</code>', wait=True)
    finally:
        await finish_forwarding(client, user_id, sts, m)

async def forwarding_loop(client, user_id, m, sts, caption, forward_tag, button, protect, sleep_time):
    messages_batch = []
    progress_interval = 20
    counter = 0

    await edit_progress(m, "Progressing", 10, sts)
    logger.info(f"Starting forwarding... From: {sts.get('FROM')} To: {sts.get('TO')} Limit: {sts.get('limit')}")

    async for message in client.iter_messages(
        sts.get('FROM'),
        limit=int(sts.get('limit')),
        offset=int(sts.get('skip') or 0)
    ):
        if await is_cancelled(client, user_id, m, sts):
            return

        if counter % progress_interval == 0:
            await edit_progress(m, "Progressing", 10, sts)
        counter += 1
        sts.add('fetched')

        if message in ["DUPLICATE", "FILTERED"]:
            sts.add('duplicate' if message == "DUPLICATE" else 'filtered')
            continue

        if message.empty or message.service:
            sts.add('deleted')
            continue

        if forward_tag:
            messages_batch.append(message.id)
            if len(messages_batch) >= 100 or (sts.get('total') - sts.get('fetched')) <= 100:
                await forward_messages(client, messages_batch, m, sts, protect)
                messages_batch.clear()
                await asyncio.sleep(10)
        else:
            await copy_message(client, message, m, sts, caption, button, protect)
            await asyncio.sleep(sleep_time)

async def copy_message(bot, msg, m, sts, caption, button, protect):
    try:
        if msg.media and caption:
            await bot.send_cached_media(
                chat_id=sts.get('TO'),
                file_id=getattr(msg, msg.media.value),
                caption=caption,
                reply_markup=button,
                protect_content=protect
            )
        else:
            await bot.copy_message(
                chat_id=sts.get('TO'),
                from_chat_id=sts.get('FROM'),
                message_id=msg.id,
                caption=caption,
                reply_markup=button,
                protect_content=protect
            )
        sts.add('total_files')
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await copy_message(bot, msg, m, sts, caption, button, protect)
    except Exception as e:
        logger.error(f"Error copying message: {e}")
        sts.add('deleted')

async def forward_messages(bot, message_ids, m, sts, protect):
    try:
        await bot.forward_messages(
            chat_id=sts.get('TO'),
            from_chat_id=sts.get('FROM'),
            message_ids=message_ids,
            protect_content=protect
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await forward_messages(bot, message_ids, m, sts, protect)

async def can_access_chat(bot, chat_id, check_send=False):
    try:
        if check_send:
            msg = await bot.send_message(chat_id, "Testing")
            await msg.delete()
        else:
            await bot.get_chat(chat_id)
        return True
    except Exception:
        return False

async def safe_edit(msg, text, button=None, wait=False):
    try:
        return await msg.edit(text, reply_markup=button)
    except MessageNotModified:
        pass
    except FloodWait as e:
        if wait:
            await asyncio.sleep(e.value)
            return await safe_edit(msg, text, button, wait)

async def edit_progress(msg, title, status, sts):
    i = sts.get(full=True)
    percentage = "{:.0f}".format(float(i.fetched) * 100 / float(i.total))

    now = time.time()
    diff = int(now - i.start)
    speed = sts.divide(i.fetched, diff)
    remaining = sts.divide(i.total - i.fetched, speed)
    eta = TimeFormatter(milliseconds=(remaining * 1000))

    text = TEXT.format(i.fetched, i.total_files, i.duplicate, i.deleted, i.skip, title, percentage, eta, "◉" * int(percentage))
    button = [[InlineKeyboardButton(title, callback_data="fwrdstatus")], [InlineKeyboardButton("Cancel", callback_data="terminate_frwd")]]
    await safe_edit(msg, text, InlineKeyboardMarkup(button))

async def is_cancelled(client, user_id, msg, sts):
    if temp.CANCEL.get(user_id):
        temp.IS_FRWD_CHAT.remove(sts.TO)
        await edit_progress(msg, "Cancelled", "completed", sts)
        await send_message(client, user_id, "<b>❌ Forwarding Cancelled</b>")
        await stop(client, user_id)
        return True
    return False

async def stop(client, user_id):
    try:
        await client.stop()
    except Exception:
        pass
    await db.rmve_frwd(user_id)
    temp.forwardings -= 1
    temp.lock[user_id] = False

async def send_message(bot, user_id, text):
    try:
        await bot.send_message(user_id, text=text)
    except Exception:
        pass

async def finish_forwarding(client, user_id, sts, m):
    temp.IS_FRWD_CHAT.remove(sts.TO)
    await send_message(client, user_id, "<b>🎉 Forwarding Completed! <a href='https://t.me/dev_gagan'>Support</a></b>")
    await edit_progress(m, "Completed", "completed", sts)
    await stop(client, user_id)
