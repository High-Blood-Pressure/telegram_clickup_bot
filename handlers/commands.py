from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.user_manager import get_user_context, is_admin, get_shutting_down, set_shutting_down, save_user_data
from services import clickup, stop_application, update_user_context
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
    save_user_data()
    set_shutting_down(True)

    asyncio.create_task(stop_application())
    await update.message.reply_text("🛑 Выключаю бота...")
    await context.bot.send_photo(
        chat_id=user_id,
        photo="https://pic.rutubelist.ru/video/34/2d/342d3b1c217ef31a5e990934b99bd37b.jpg",
        caption="Нижний текст"
    )


async def show_current_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        context_data = get_user_context(user_id)
        text = await current_context_text(context_data, user_id)

        keyboard = [
            [InlineKeyboardButton("Изменить workspace", callback_data="change_workspace")],
            [InlineKeyboardButton("Изменить спринт", callback_data="change_sprint")],
            [InlineKeyboardButton("Изменить юзера", callback_data="change_user")]
        ]

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка в current_context: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при отображении контекста. Попробуйте позже.")


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        context_data = get_user_context(user_id)
        text = await current_context_text(context_data, user_id)

        keyboard = [
            [InlineKeyboardButton("🔄 Обновить задачи спринта", callback_data="refresh_tasks")],
            [InlineKeyboardButton("Залогировать время юзеру", callback_data="log_my_time")],
            [InlineKeyboardButton("Изменить оценку задачи в спринте", callback_data="change_task_estimate")],
            [InlineKeyboardButton("📊 Статистика задач юзера", callback_data="show_stats")],
            [InlineKeyboardButton("📋 Показать все задачи спринта", callback_data="show_all_tasks")],
            [InlineKeyboardButton("📋 Показать задачи спринта без оценки", callback_data="show_tasks_without_estimate")]
        ]

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка в show_menu: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при отображении меню. Попробуйте позже.")



async def current_context_text(context_data, user_id):
    text = "⚙️ <b>Текущие настройки контекста</b>\n\n"
    workspace_id = context_data.get("current_workspace")
    if workspace_id:
        workspace = context_data.get("current_workspace_data")
        if not workspace:
            workspaces = await clickup.get_clickup_teams()
            workspace = next((ws for ws in format_workspaces(workspaces)
                              if ws["id"] == workspace_id), None)
            update_user_context(user_id, "current_workspace_data", workspace)

        text += f"🏢 <b>Workspace:</b> {workspace['name'] if workspace else f'ID {workspace_id}'}\n"
    else:
        text += "🏢 <b>Workspace:</b> не выбран\n"
    text += "────────────────\n"
    sprint_id = context_data.get("current_sprint")
    if sprint_id:
        if workspace_id:
            sprint = context_data.get("current_sprint_data")
            if not sprint:
                sprints = await clickup.get_clickup_sprints(workspace_id)
                sprint = next((s for s in format_sprints(sprints) if s["id"] == sprint_id), None)
                update_user_context(user_id, "current_sprint_data", sprint)

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
            user_name = context_data.get("current_user_name")
            if user_name:
                text += f"👤 <b>Пользователь:</b> {user_name}\n"
                text += f"   <i>ID:</i> {user_id_str}\n"
            else:
                text += f"👤 <b>Пользователь:</b> ID {user_id_str}\n"
        else:
            text += f"👤 <b>Пользователь:</b> ID {user_id_str} (спринт не выбран)\n"
    else:
        text += "👤 <b>Пользователь:</b> не выбран\n"
    text += "────────────────\n"
    return text