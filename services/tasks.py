from telegram.ext import ContextTypes
from services.user_manager import save_user_data_if_dirty

async def auto_save_task(ctx: ContextTypes.DEFAULT_TYPE):
    save_user_data_if_dirty()