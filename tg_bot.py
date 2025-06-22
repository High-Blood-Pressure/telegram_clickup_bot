import signal
import asyncio

from telegram import Update

import helpers
import handlers
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters, ContextTypes
)


async def auto_save_task():
    """Фоновая задача для автоматического сохранения данных"""
    while True:
        await asyncio.sleep(300)  # Сохраняем каждые 5 минут
        helpers.save_user_data()


def main():
    if not helpers.TELEGRAM_BOT_TOKEN:
        helpers.logger.error("Токен Telegram бота не найден в .env файле!")
        return

    # Создаем приложение
    application = ApplicationBuilder().token(helpers.TELEGRAM_BOT_TOKEN).build()

    # Сохраняем приложение в helpers
    helpers.set_application(application)

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("shutdown", handlers.shutdown))
    application.add_handler(CommandHandler("context", handlers.current_context))

    # Регистрация обработчиков кнопок и сообщений
    application.add_handler(CallbackQueryHandler(handlers.button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))

    # Создаем фоновую задачу на сохранение
    application.job_queue.run_repeating(
        lambda ctx: helpers.save_user_data(),
        interval=300,  # 5 минут
        first=10
    )

    application.add_error_handler(error_handler)

    # Обработка сигналов
    def signal_handler(signum, frame):
        helpers.logger.info(f"Получен сигнал {signum}, инициирую выключение...")
        helpers.save_user_data()  # Сохраняем данные перед выключением
        asyncio.create_task(helpers.stop_application())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        helpers.logger.info("Запуск бота...")
        application.run_polling()
        helpers.logger.info("Бот завершил работу")
    except Exception as e:
        helpers.logger.exception(f"Критическая ошибка: {e}")
    finally:
        helpers.logger.info("Работа бота завершена")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ошибки в обработчиках."""
    helpers.logger.error(msg="Исключение при обработке обновления:", exc_info=context.error)

    # Логируем дополнительную информацию
    if update:
        helpers.logger.error(f"Ошибка в обновлении: {update}")

    # Отправляем сообщение об ошибке пользователю
    if update and isinstance(update, Update) and update.effective_chat:
        try:
            # Формируем сообщение об ошибке
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
            helpers.logger.error(f"Ошибка при отправке сообщения об ошибке: {e}")



if __name__ == "__main__":
    main()

