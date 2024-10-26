from os import environ 

class Config:
    API_ID = environ.get("API_ID", "22412440")
    API_HASH = environ.get("API_HASH", "211165a095cd129a58bc1d23515c01ef")
    BOT_TOKEN = environ.get("BOT_TOKEN", "7578490063:AAHQDkFc_oBkTiAUlMVGcj4ferI0rb0DVrk") 
    BOT_SESSION = environ.get("BOT_SESSION", "bot") 
    DATABASE_URI = environ.get("DATABASE", "mongodb+srv://ackbot:ackbot@bot.uthcly0.mongodb.net/?retryWrites=true&w=majority&appName=bot")
    DATABASE_NAME = environ.get("DATABASE_NAME", "forward-bot")
    BOT_OWNER_ID = [int(id) for id in environ.get("BOT_OWNER_ID", '5505135072').split()]

class temp(object): 
    lock = {}
    CANCEL = {}
    forwardings = 0
    BANNED_USERS = []
    IS_FRWD_CHAT = []
    
