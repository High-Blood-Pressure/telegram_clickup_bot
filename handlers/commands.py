from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.user_manager import get_user_context, is_admin, get_shutting_down, set_shutting_down
from services import clickup, stop_application
from utils.formatting import format_workspaces, format_sprints, format_members
from utils.logger import logger
import asyncio


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    get_user_context(user_id)  # Инициализация контекста

    text = (
        "🚀 Добро пожаловать в TimeLoggerBot!\n\n"
        "🛠️ Перед началом работы настройте контекст /context.\n"
        "📊 Основные команды:\n"
        "/context - Показать текущий контекст\n\n"
        "⚙️ Для администраторов:\n"
        "/shutdown - Выключить бота"
    )

    await update.message.reply_text(text)


async def shutdown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if get_shutting_down():
        await update.message.reply_text("🔄 Бот уже выключается...")
        return

    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав на эту команду")
        logger.warning(f"Неавторизованная попытка выключения от {user_id}")
        return

    logger.info(f"Инициировано выключение администратором {user_id}")
    set_shutting_down(True)

    asyncio.create_task(stop_application())
    await update.message.reply_text("🛑 Выключаю бота...")


async def current_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        context_data = get_user_context(user_id)
        text = "⚙️ <b>Текущие настройки контекста</b>\n\n"

        workspace_id = context_data.get("current_workspace")
        if workspace_id:
            workspaces = await clickup.get_clickup_teams()
            workspace = next((ws for ws in format_workspaces(workspaces)
                              if ws["id"] == workspace_id), None)
            text += f"🏢 <b>Workspace:</b> {workspace['name'] if workspace else f'ID {workspace_id}'}\n"
        else:
            text += "🏢 <b>Workspace:</b> не выбран\n"

        text += "────────────────\n"

        sprint_id = context_data.get("current_sprint")
        if sprint_id:
            if workspace_id:
                sprints = await clickup.get_clickup_sprints(workspace_id)
                sprint = next((s for s in format_sprints(sprints) if s["id"] == sprint_id), None)
                if sprint:
                    text += f"⏳ <b>Спринт:</b> {sprint['name']}\n"
                    text += f"   <i>Папка:</i> {sprint.get('folder_name', 'Sprint')}\n"
                else:
                    text += f"⏳ <b>Спринт:</b> ID {sprint_id}\n"
            else:
                text += f"⏳ <b>Спринт:</b> ID {sprint_id} (workspace не выбран)\n"
        else:
            text += "⏳ <b>Спринт:</b> не выбран\n"

        text += "────────────────\n"

        user_id_str = context_data.get("current_user")
        if user_id_str:
            if sprint_id:
                members = await clickup.get_clickup_list_members(sprint_id)
                member = next((m for m in format_members(members)
                               if str(m["id"]) == str(user_id_str)), None)
                if member:
                    text += f"👤 <b>Пользователь:</b> {member['username']}\n"
                    text += f"   <i>ID:</i> {member['id']}\n"
                    if member['email']:
                        text += f"   <i>Email:</i> {member['email']}\n"
                else:
                    text += f"👤 <b>Пользователь:</b> ID {user_id_str}\n"
            else:
                text += f"👤 <b>Пользователь:</b> ID {user_id_str} (спринт не выбран)\n"
        else:
            text += "👤 <b>Пользователь:</b> не выбран\n"

        text += "────────────────\n"

        keyboard = [
            [InlineKeyboardButton("Изменить workspace", callback_data="change_workspace")],
            [InlineKeyboardButton("Изменить спринт", callback_data="change_sprint")],
            [InlineKeyboardButton("Изменить пользователя", callback_data="change_user")],
            [InlineKeyboardButton("Залогировать время", callback_data="log_my_time")],
            [InlineKeyboardButton("📊 Статистика задач", callback_data="show_stats")],
            [InlineKeyboardButton("🔄 Обновить задачи", callback_data="refresh_tasks")],
            [InlineKeyboardButton("📋 Все задачи спринта", callback_data="show_all_tasks")]
        ]

        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Ошибка в current_context: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при отображении контекста. Попробуйте позже.")