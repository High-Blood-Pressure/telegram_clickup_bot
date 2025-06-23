from telegram import Update
from telegram.ext import ContextTypes
from utils.logger import logger

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)

    if update:
        logger.error(f"Error in update: {update}")

    if update and isinstance(update, Update) and update.effective_chat:
        try:
            error_text = (
                "⚠️ *Произошла ошибка*\n\n"
                "Пожалуйста, попробуйте повторить операцию позже. "
                "Если ошибка повторяется, сообщите администратору.\n\n"
                f"Ошибка: `{context.error.__class__.__name__}`"
            )

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=error_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error while sending error message: {e}")