from telegram import Update
from telegram.ext import ContextTypes

from handlers import show_menu
from services.user_manager import get_user_context, user_logging_state
from services.time_utils import parse_time_input
from services.clickup import get_clickup_list_members, put_new_task_estimate
from services.database import log_time_locally, get_task_time_for_user, change_task_estimate
from handlers.buttons import show_current_context
from utils.logger import log_exceptions
from utils import format_members

@log_exceptions
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text

    if user_id in user_logging_state and user_logging_state[user_id].get("action") == "estimate_edit":
        duration_ms = parse_time_input(message_text)
        if not duration_ms or duration_ms <= 0:
            await update.message.reply_text("❌ Неверный формат времени!")
            return

        new_estimate_minutes = duration_ms / 60000.0
        task_id = user_logging_state[user_id]["task_id"]

        loading_msg = await update.message.reply_text("⏳ Обновляю оценку...")
        success = await put_new_task_estimate(task_id, new_estimate_minutes)
        if success:
            change_task_estimate(task_id, new_estimate_minutes)

        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=loading_msg.message_id
        )

        if success:
            await update.message.reply_text(f"✅ Оценка обновлена: {new_estimate_minutes:.1f} минут")
        else:
            await update.message.reply_text("❌ Ошибка при обновлении оценки")

        del user_logging_state[user_id]
        return

    if user_id in user_logging_state and "task_id" in user_logging_state[user_id]:
        duration_ms = parse_time_input(message_text)
        if not duration_ms or duration_ms <= 0:
            await update.message.reply_text(
                "❌ Неверный формат времени. Используйте:\n"
                "• 1.5h - полтора часа\n"
                "• 90m - 90 минут\n"
                "• 2h30m - 2 часа 30 минут"
            )
            return

        task_id = user_logging_state[user_id]["task_id"]
        clickup_user_id = user_logging_state[user_id]["clickup_user_id"]

        task_exists = any(task["id"] == task_id
                          for task in user_logging_state[user_id]["tasks"])

        if not task_exists:
            await update.message.reply_text("❌ Ошибка: задача не найдена")
            del user_logging_state[user_id]
            return

        user_name = "Unknown"
        context_data = get_user_context(user_id)
        if context_data.get("current_user_name"):
            user_name = context_data["current_user_name"]
        else:
            sprint_id = context_data.get("current_sprint")
            if sprint_id:
                members = await get_clickup_list_members(sprint_id)
                member = next(
                    (m for m in format_members(members)
                     if str(m["id"]) == clickup_user_id),
                    None
                )
                if member:
                    user_name = member["username"]
                    context_data["current_user_name"] = user_name

        loading_msg = await update.message.reply_text("⏳ Сохраняю время...")

        duration_minutes = duration_ms / 60000.0
        success = log_time_locally(
            task_id,
            clickup_user_id,
            user_name,
            duration_minutes
        )

        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=loading_msg.message_id
        )

        if success:
            total_minutes = get_task_time_for_user(task_id, clickup_user_id)
            total_hours = total_minutes / 60.0

            if total_hours >= 1:
                time_str = f"{total_hours:.1f} ч"
            else:
                time_str = f"{total_minutes:.0f} мин"

            task_name = next((t["name"] for t in user_logging_state[user_id]["tasks"]
                              if t["id"] == task_id), "Задача")

            await update.message.reply_text(
                f"✅ Время успешно сохранено!\n"
                f"• Затрачено: {duration_minutes:.1f} мин\n"
                f"• Всего по задаче: {time_str}\n"
                f"• Задача: {task_name}")

            loading_msg = await update.message.reply_text("⏳ Загружаю меню..")
            await show_menu(update, context)
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=loading_msg.message_id
            )
        else:
            await update.message.reply_text("❌ Ошибка при сохранении времени. Попробуйте позже.")

        del user_logging_state[user_id]
        return

    else:
        await update.message.reply_text("ℹ️ Используйте команды меню для работы с ботом")