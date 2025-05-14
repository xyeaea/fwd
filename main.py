# main.py
from bot import Bot
from config import Config, Temp
import sys

try:
    config = Config()
    temp = Temp()
except (EnvironmentError, ValueError) as e:
    print(f"Configuration error: {e}")
    sys.exit(1)

bot = Bot(config, temp)
bot.run()
