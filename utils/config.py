import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CLICKUP_API_TOKEN = os.getenv('CLICKUP_API_TOKEN')
ADMIN_SALT = os.getenv('ADMIN_SALT', 'default_secret_salt')
DB_FILE = "timelogger.db"
DATA_FILE = "user_contexts.json"