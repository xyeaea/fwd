import os
from config import Config

class Translation:
    """String templates for a Telegram auto-forward bot's user interface."""

    # Constant for repeated cancel command
    CANCEL_COMMAND = "/cancel - cancel this process"

    START_TXT = """<b>Hello {}</b>

<i>I'm a <b>powerful</b> auto-forward bot

I can forward all messages from one channel to another channel</i> <b>➜ with more features.
Click the help button to know more about me</b>"""
    
    HELP_TXT = """<b><u>🔆 HELP</u></b>

<u><b>📚 Available commands:</b></u>
<b>⏣ /start - Check if I'm alive
⏣ /forward - Forward messages
⏣ /unequify - Delete duplicate messages in channels
⏣ /settings - Configure your settings
⏣ /reset - Reset your settings</b>

<u><b>💢 Features:</b></u>
<b>► Forward messages from a public channel to your channel without admin permission. If the channel is private, admin permission is required.
► Forward messages from a private channel to your channel using a userbot (user must be a member).
► Custom captions
► Custom buttons
► Support for restricted chats
► Skip duplicate messages
► Filter types of messages
► Skip messages based on extensions, keywords, and size</b>"""

    HOW_USE_TXT = f"""<b><u>⚠️ Before Forwarding:</u></b>
<b>► Add a bot or userbot
► Add at least one target channel (your bot/userbot must be an admin there)
► Configure chats or bots using /settings
► If the source channel is private, your userbot must be a member, or your bot must have admin permission
► Then use /forward to forward messages</b>"""

    ABOUT_TXT = """<b>╭──────❰ 🤖 Bot Details ❱──────〄
│ 
│ 🤖 My Name: <a href=https://t.me/devganbot>Dev Gagan Bot</a>
│ 👨‍💻 Developer: <a href=https://t.me/dev_gagan>Team SPY</a>
│ 🤖 Updates: <a href=https://t.me/dev_gagan>devgagan</a>
│ 📡 Hosted on: <a href=https://devgagan.in/>Dev Gagan Host</a>
│ 🗣️ Language: Python 3 {python_version}
│ 📚 Library: Pyrogram
╰────────────────────⍟</b>"""

    STATUS_TXT = """<b>╭──────❪ 🤖 Bot Status ❫─────⍟
│
├👨 Users: {}
│
├🤖 Bots: {}
│
├📣 Channels: {}
╰───────────────────⍟</b>"""

    FROM_MSG = f"""<b>❪ SET SOURCE CHAT ❫</b>

Forward the last message or last message link of the source chat.
{CANCEL_COMMAND}"""

    TO_MSG = f"""<b>❪ CHOOSE TARGET CHAT ❫</b>

Choose your target chat from the given buttons.
{CANCEL_COMMAND}"""

    SKIP_MSG = f"""<b>❪ SET MESSAGE SKIPPING NUMBER ❫</b>

Skip as many messages as you enter, and the rest will be forwarded.
Default Skip Number = <code>0</code>
Example: Enter 0 = 0 messages skipped
         Enter 5 = 5 messages skipped
{CANCEL_COMMAND}"""

    CANCEL = "<b>Process Cancelled Successfully!</b>"

    BOT_DETAILS = """<b><u>📄 BOT DETAILS</u></b>

<b>➣ Name:</b> <code>{}</code>
<b>➣ Bot ID:</b> <code>{}</code>
<b>➣ Username:</b> @{}"""

    USER_DETAILS = """<b><u>📄 USERBOT DETAILS</u></b>

<b>➣ Name:</b> <code>{}</code>
<b>➣ User ID:</b> <code>{}</code>
<b>➣ Username:</b> @{}"""

    FORWARD_STATUS = """<b>╭─❰ <u>Forwarded Status</u> ❱─❍
┃
┣⊸🕵 Fetched Msg: <code>{}</code>
┣⊸✅ Successfully Fwd: <code>{}</code>
┣⊸👥 Duplicate Msg: <code>{}</code>
┣⊸🗑 Deleted Msg: <code>{}</code>
┣⊸🪆 Skipped: <code>{}</code>
┣⊸📊 Status: <code>{}</code>
┣⊸⏳ Progress: <code>{}</code> %
┣⊸⏰ ETA: <code>{}</code>
┃
╰─⌊ <b>{}</b> ⌉─❍</b>"""

    DUPLICATE_TEXT = """<b>╔════❰ Unequify Status ❱═❍⊱❁۪۪
║╭━━━━━━━━━━━━━━━➣
║┣⪼ Fetched Files: <code>{}</code>
║┃
║┣⪼ Duplicates Deleted: <code>{}</code>
║╰━━━━━━━━━━━━━━━➣
╚════❰ {} ❱══❍⊱❁۪۪</b>"""

    DOUBLE_CHECK = """<b><u>DOUBLE CHECKING ⚠️</u></b>

<code>Before forwarding messages, click the Yes button only after verifying the following:</code>

<b>★ Your Bot:</b> [{botname}](t.me/{botuname})
<b>★ From Channel:</b> <code>{from_chat}</code>
<b>★ To Channel:</b> <code>{to_chat}</code>
<b>★ Skip Messages:</b> <code>{skip}</code>

<i>° [{botname}](t.me/{botuname}) must be an admin in <b>TARGET CHAT</b> ({to_chat})</i>
<i>° If the <b>SOURCE CHAT</b> is private, your userbot must be a member, or your bot must have admin permission</i>

<b>If the above is verified, click the Yes button.</b>"""
