import os
from typing import List

class Config:
    API_ID: int = int(os.getenv("API_ID", "22412440"))
    API_HASH: str = os.getenv("API_HASH", "211165a095cd129a58bc1d23515c01ef")
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "7806753719:AAEOfuW5rGfeVCe8H9SNz8uVmvKkGuWXd1c")
    BOT_SESSION: str = os.getenv("BOT_SESSION", "bot")
    DATABASE_URI: str = os.getenv("DATABASE", "mongodb+srv://ackbot:ackbot@bot.uthcly0.mongodb.net/?retryWrites=true&w=majority&appName=bot")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "forward-bot")
    
    BOT_OWNER_ID: List[int] = [int(x) for x in os.getenv("BOT_OWNER_ID", "5643219124").split()]

class Temp:
    lock: dict = {}
    cancel: dict = {}
    forwardings: int = 0
    banned_users: List[int] = []
    is_frwd_chat: List[int] = []
