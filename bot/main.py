import signal
import asyncio
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from bot.error_handler import error_handler
from handlers.commands import start, shutdown, current_context
from handlers.buttons import button_handler
from handlers.messages import handle_message
from utils.config import TELEGRAM_BOT_TOKEN
from utils.logger import logger
from services.tasks import auto_save_task
from services.user_manager import save_user_data_if_dirty, load_initial_user_data, set_application
from services.database import init_db


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Токен Telegram бота не найден в .env файле!")
        return

    logger.info("Инициализация систем...")

    init_db()
    logger.info("База данных инициализирована")

    user_data = load_initial_user_data()
    logger.info(f"Загружены данные для {len(user_data)} пользователей")

    try:
        application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        logger.info("Приложение Telegram создано")
    except Exception as e:
        logger.error(f"Ошибка создания приложения: {e}")
        return

    set_application(application)
    handlers = [
        CommandHandler("start", start),
        CommandHandler("shutdown", shutdown),
        CommandHandler("context", current_context),
        CallbackQueryHandler(button_handler),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    ]
    application.add_handlers(handlers)
    logger.info(f"Зарегистрировано {len(handlers)} обработчиков")

    application.job_queue.run_repeating(
        callback=auto_save_task,
        interval=300,
        first=10
    )
    logger.info("Фоновая задача автосохранения запущена")

    application.add_error_handler(error_handler)
    logger.info("Обработчик ошибок зарегистрирован")

    def signal_handler(signum, frame):
        logger.info(f"Получен сигнал {signum}, инициирую выключение...")
        save_user_data_if_dirty()
        asyncio.create_task(application.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logger.info("Обработчики сигналов настроены")

    try:
        logger.info("Запуск бота...")
        application.run_polling()
        logger.info("Бот успешно остановлен")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
    finally:
        logger.info("Работа бота завершена")


if __name__ == "__main__":
    main()