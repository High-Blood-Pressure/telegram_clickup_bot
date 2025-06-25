from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.user_manager import get_user_context, update_user_context, user_logging_state
from services import clickup, database, get_sprint_tasks_summary, get_all_tasks_in_sprint, cache_task, \
    get_user_sprint_statistics
from utils.formatting import format_workspaces, format_sprints, format_members, format_tasks
from utils.logger import logger
from handlers import show_current_context, show_menu


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "change_workspace":
        await change_workspace(update, context)
    elif data == "change_sprint":
        await change_sprint(update, context)
    elif data == "change_user":
        await change_user(update, context)
    elif data == "log_my_time":
        await log_my_time(update, context)
    elif data == "show_stats":
        await show_statistics(update, context)
    elif data == "show_all_tasks":
        await show_all_tasks(update, context)
    elif data == "refresh_tasks":
        await refresh_tasks(update, context)
        await show_menu(update, context)
    elif data == "current_context":
        await show_current_context(update, context)
    elif data == "show_menu":
        await show_menu(update, context)
    elif data == "show_tasks_without_estimate":
        await show_tasks_without_estimate(update, context)
    elif data == "change_task_estimate":
        await change_task_estimate(update, context)

    elif data.startswith("ws_"):
        workspace_id = data.split("_", 1)[1]
        update_user_context(user_id, "current_workspace", workspace_id)
        update_user_context(user_id, "current_sprint", None)
        update_user_context(user_id, "current_user", None)
        update_user_context(user_id, "current_workspace_data", None)
        update_user_context(user_id, "current_sprint_data", None)
        update_user_context(user_id, "current_user_name", None)
        await query.edit_message_text(f"✅ Workspace установлен\n")
        await show_current_context(update, context)

    elif data.startswith("sprint_"):
        sprint_id = data.split("_", 1)[1]
        update_user_context(user_id, "current_sprint", sprint_id)
        update_user_context(user_id, "current_user", None)
        update_user_context(user_id, "current_sprint_data", None)
        update_user_context(user_id, "current_user_name", None)
        await query.edit_message_text(f"✅ Спринт установлен\n")
        await show_current_context(update, context)

    elif data.startswith("user_"):
        parts = data.split("_", 2)
        user_id_str = parts[1]
        user_name = parts[2] if len(parts) > 2 else f"User {user_id_str}"
        update_user_context(user_id, "current_user", user_id_str)
        update_user_context(user_id, "current_user_name", user_name)
        await query.edit_message_text(f"✅ Пользователь установлен: {user_name}\n")
        await show_current_context(update, context)

    elif data.startswith("task_"):
        task_id = data.split("_", 1)[1]
        if user_id in user_logging_state:
            user_logging_state[user_id]["task_id"] = task_id

            task_name = next((t["name"] for t in user_logging_state[user_id]["tasks"]
                              if t["id"] == task_id), "Задача")

            estimated = next((t["estimated_minutes"] for t in user_logging_state[user_id]["tasks"]
                              if t["id"] == task_id), "Оценка")

            estimated_hrs = int(estimated) / 60 if estimated else 0
            logged_minutes = database.get_task_time_for_user(task_id, user_logging_state[user_id]["clickup_user_id"])
            logged_hours = logged_minutes / 60.0

            await query.edit_message_text(
                f"Выбрана задача: {task_name}\n\n"
                f"Оценка задачи (в часах): {estimated_hrs:.1f}\n"
                f"Залогированное время (в часах): {logged_hours:.1f}\n\n"
                "Введите время в формате:\n"
                "• 1.5h - полтора часа\n"
                "• 90m - 90 минут\n"
                "• 2h30m - 2 часа 30 минут\n\n"
                "Или просто число (в минутах): 150"
            )

    elif data.startswith("estimate_task_"):
        task_id = data.split('_', 2)[2]
        await handle_estimate_task(update, context, task_id)

    elif data == "cancel_estimate":
        if user_id in user_logging_state:
            del user_logging_state[user_id]
        await query.edit_message_text("❌ Изменение оценки отменено")

    elif data == "log_cancel":
        if user_id in user_logging_state:
            del user_logging_state[user_id]
        await query.edit_message_text("❌ Логирование времени отменено")


async def change_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.callback_query.edit_message_text("🔄 Загружаю список workspace...")
        workspaces = await clickup.get_clickup_teams()

        if not workspaces:
            await update.callback_query.edit_message_text("❌ Не удалось получить список workspace")
            return

        formatted_ws = format_workspaces(workspaces)
        keyboard = [
            [InlineKeyboardButton(ws["name"], callback_data=f"ws_{ws['id']}")]
            for ws in formatted_ws
        ]

        await update.callback_query.edit_message_text(
            "🏢 Выберите workspace:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Workspace change error: {e}")
        await update.callback_query.edit_message_text("⚠️ Ошибка при загрузке workspace")


async def change_sprint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.callback_query.edit_message_text("🔄 Загружаю список спринтов...")
        user_id = update.effective_user.id
        context_data = get_user_context(user_id)

        if not context_data.get("current_workspace"):
            await update.callback_query.edit_message_text("❌ Сначала выберите workspace")
            return

        sprints = await clickup.get_clickup_sprints(context_data["current_workspace"])

        if not sprints:
            await update.callback_query.edit_message_text("❌ Не удалось найти спринты")
            return

        formatted_sprints = format_sprints(sprints)
        keyboard = [
            [InlineKeyboardButton(sprint["name"], callback_data=f"sprint_{sprint['id']}")]
            for sprint in formatted_sprints
        ]

        await update.callback_query.edit_message_text(
            "⏳ Выберите спринт:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Sprint change error: {e}")
        await update.callback_query.edit_message_text("⚠️ Ошибка при загрузке спринтов")


async def change_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.callback_query.edit_message_text("🔄 Загружаю список пользователей...")
        user_id = update.effective_user.id
        context_data = get_user_context(user_id)

        if not context_data.get("current_sprint"):
            await update.callback_query.edit_message_text("❌ Сначала выберите спринт")
            return

        members = await clickup.get_clickup_list_members(context_data["current_sprint"])

        if not members:
            await update.callback_query.edit_message_text("❌ Не удалось получить пользователей")
            return

        formatted_members = format_members(members)
        keyboard = [
            [InlineKeyboardButton(
                f"{member['username']} ({member['email']})" if member['email'] else member['username'],
                callback_data=f"user_{member['id']}_{member['username']}"
            )]
            for member in formatted_members
        ]

        await update.callback_query.edit_message_text(
            "👤 Выберите пользователя:",
            reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.error(f"User change error: {e}")
        await update.callback_query.edit_message_text("⚠️ Ошибка при загрузке пользователей")


async def log_my_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.callback_query.edit_message_text("🔄 Загружаю список задач...")
        user_id = update.effective_user.id
        context_data = get_user_context(user_id)

        required = ["current_workspace", "current_sprint", "current_user"]
        if not all(context_data.get(key) for key in required):
            await update.callback_query.edit_message_text("❌ Конфигурация не завершена!")
            return

        tasks = await clickup.get_all_user_tasks_in_sprint(
            context_data["current_sprint"],
            context_data["current_user"]
        )

        if not tasks:
            await update.callback_query.edit_message_text("❌ У пользователя нет задач в спринте")
            return

        for task in tasks:
            estimated_ms = task.get("time_estimate")
            estimated_minutes = estimated_ms / 60000.0 if estimated_ms else 0
            sprint_id = context_data["current_sprint"]
            status = task.get("status", {}).get("status", "unknown")

            database.cache_task({
                "id": task["id"],
                "name": task.get("name", ""),
                "url": task.get("url", ""),
                "status": status,
                "workspace_id": context_data["current_workspace"],
                "sprint_id": sprint_id,
                "estimated_minutes": estimated_minutes
            })

        tasks_in_progress = [task for task in tasks
                             if task.get("status", {}).get("status", "").lower() == "in progress"]

        if not tasks_in_progress:
            await update.callback_query.edit_message_text(
                "❌ Нет задач в работе. Все задачи завершены или еще не начаты.")
            return

        formatted_tasks = format_tasks(tasks)
        user_logging_state[user_id] = {
            "tasks": formatted_tasks,
            "workspace_id": context_data["current_workspace"],
            "clickup_user_id": context_data["current_user"]
        }

        keyboard = [
            [InlineKeyboardButton(
                task["name"][:47] + "..." if len(task["name"]) > 50 else task["name"],
                callback_data=f"task_{task['id']}"
            )]
            for task in formatted_tasks
        ]
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="log_cancel")])

        await update.callback_query.edit_message_text(
            "✅ Выберите задачу для логирования времени:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Log time init error: {e}")
        await update.callback_query.edit_message_text("⚠️ Ошибка при загрузке задач")


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    context_data = get_user_context(user_id)

    required = ["current_workspace", "current_sprint", "current_user"]
    if not all(context_data.get(key) for key in required):
        await query.edit_message_text("❌ Конфигурация не завершена!")
        return

    sprint_id = context_data["current_sprint"]
    user_id_str = context_data["current_user"]

    try:
        tasks = get_user_sprint_statistics(sprint_id, user_id_str)

        if not tasks:
            await query.edit_message_text("❌ У вас нет задач в этом спринте.")
            return

        message = "📊 <b>Статистика пользователя:</b>\n\n"

        total_estimated = 0.0
        total_logged = 0.0

        for task in tasks:
            estimated_minutes = task['estimated_minutes']
            logged_minutes = task['logged_minutes']

            estimated_hours = estimated_minutes / 60 if estimated_minutes else 0
            logged_hours = logged_minutes / 60

            total_estimated += estimated_hours
            total_logged += logged_hours

            task_name = task['name']
            if len(task_name) > 50:
                task_name = task_name[:47] + "..."

            message += f"🔹 <a href='{task['url']}'>{task_name}</a>\n"
            message += f"   Статус: {task['status']}\n"
            message += f"   {logged_hours:.1f}h"

            if estimated_minutes:
                message += f" / {estimated_hours:.1f}h\n"
            else:
                message += " / NOT ESTIMATED\n"

            message += "────────────────\n"

        message += f"\n<b>Итого:</b> {total_logged:.1f}h"
        if total_estimated:
            message += f" / {total_estimated:.1f}h"

        keyboard = [[InlineKeyboardButton("Вернуться в меню", callback_data="show_menu")]]
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await query.edit_message_text("❌ Ошибка при загрузке статистики")


async def show_all_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    context_data = get_user_context(user_id)

    if not context_data.get("current_sprint"):
        await query.edit_message_text("❌ Спринт не выбран!")
        return

    sprint_id = context_data["current_sprint"]

    await query.edit_message_text("🔄 Загружаю задачи...")

    try:
        tasks = get_sprint_tasks_summary(sprint_id)

        if not tasks:
            await query.edit_message_text("❌ В спринте нет задач")
            return

        message = "📋 <b>Все задачи спринта:</b>\n\n"

        for task in tasks:
            task_name = task['name']
            if len(task_name) > 50:
                task_name = task_name[:47] + "..."

            message += f"🔹 <a href='{task['url']}'>{task_name}</a>\n"
            message += f"   Статус: {task['status']}\n"

            total_minutes = sum(a['minutes'] for a in task['assignees'])
            total_hours = total_minutes / 60
            message += f"   {total_hours:.1f}h /"

            if task['estimated_minutes']:
                est_hours = task['estimated_minutes'] / 60
                message += f" {est_hours}h\n"
            else:
                message += " NOT ESTIMATED\n"

            if task['assignees']:
                for assignee in task['assignees']:
                    user_name = assignee['user_name'] or f"User {assignee['user_id']}"
                    user_time = assignee['minutes'] / 60
                    message += f"   👤 {user_name}: {user_time:.1f}h\n"
            else:
                message += "   Информации о логировании нет\n"

            message += "────────────────\n"

        keyboard = [[InlineKeyboardButton("Вернуться в меню", callback_data="show_menu")]]
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Ошибка при показе задач: {e}")
        await query.edit_message_text("❌ Ошибка при загрузке задач")


async def refresh_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    context_data = get_user_context(user_id)

    if not context_data.get("current_sprint"):
        await query.edit_message_text("❌ Спринт не выбран!")
        return

    sprint_id = context_data["current_sprint"]

    await query.edit_message_text("🔄 Обновление задач...")

    try:
        tasks = await get_all_tasks_in_sprint(sprint_id)

        if not tasks:
            await query.edit_message_text("❌ В спринте нет задач")
            return

        for task in tasks:
            estimated_ms = task.get("time_estimate")
            estimated_minutes = estimated_ms / 60000.0 if estimated_ms else 0

            cache_task({
                "id": task["id"],
                "name": task.get("name", ""),
                "url": task.get("url", ""),
                "status": task.get("status", {}).get("status", "unknown"),
                "workspace_id": context_data["current_workspace"],
                "sprint_id": sprint_id,
                "estimated_minutes": estimated_minutes
            })

        await query.edit_message_text("✅ Задачи успешно обновлены!")

    except Exception as e:
        logger.error(f"Ошибка при обновлении задач: {e}")
        await query.edit_message_text("❌ Ошибка при обновлении задач")


async def show_tasks_without_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    context_data = get_user_context(user_id)

    if not context_data.get("current_sprint"):
        await query.edit_message_text("❌ Спринт не выбран!")
        return

    sprint_id = context_data["current_sprint"]
    await query.edit_message_text("🔄 Загружаю задачи без оценки...")

    try:
        tasks = get_sprint_tasks_summary(sprint_id)
        if not tasks:
            await query.edit_message_text("❌ В спринте нет задач")
            return

        tasks_without_estimate = [
            task for task in tasks
            if not task.get('estimated_minutes') or task['estimated_minutes'] == 0
        ]

        if not tasks_without_estimate:
            await query.edit_message_text("✅ В спринте нет задач без оценки!")
            return

        message = "📋 <b>Задачи спринта без оценки:</b>\n\n"

        for task in tasks_without_estimate:
            task_name = task['name']
            if len(task_name) > 50:
                task_name = task_name[:47] + "..."

            message += f"🔹 <a href='{task['url']}'>{task_name}</a>\n"
            message += f"   Статус: {task['status']}\n"

            total_minutes = sum(a['minutes'] for a in task['assignees'])
            total_hours = total_minutes / 60
            message += f"   {total_hours:.1f}h / NOT ESTIMATED\n"

            if task['assignees']:
                for assignee in task['assignees']:
                    user_name = assignee['user_name'] or f"User {assignee['user_id']}"
                    user_time = assignee['minutes'] / 60
                    message += f"   👤 {user_name}: {user_time:.1f}ч\n"
            else:
                message += "   Информации о логировании нет\n"

            message += "────────────────\n"

        keyboard = [[InlineKeyboardButton("Вернуться в меню", callback_data="show_menu")]]
        await query.edit_message_text(
            message,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Ошибка при показе задач без оценки: {e}")
        await query.edit_message_text("❌ Ошибка при загрузке задач")


async def change_task_estimate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    context_data = get_user_context(user_id)

    if not context_data.get("current_sprint"):
        await query.edit_message_text("❌ Сначала выберите спринт!")
        return

    sprint_id = context_data["current_sprint"]
    await query.edit_message_text("🔄 Загружаю задачи спринта...")

    try:
        tasks = get_sprint_tasks_summary(sprint_id)
        if not tasks:
            await query.edit_message_text("❌ В спринте нет задач")
            return

        keyboard = []
        for task in tasks:
            task_name = task['name']
            if len(task_name) > 50:
                task_name = task_name[:47] + "..."

            estimated = task.get('estimated_minutes')
            status = f"{estimated / 60:.1f}h" if estimated and estimated > 0 else "NOT ESTIMATED"

            keyboard.append([
                InlineKeyboardButton(
                    f"{task_name} ({status})",
                    callback_data=f"estimate_task_{task['id']}"
                )
            ])

        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_estimate")])

        await query.edit_message_text(
            "📋 Выберите задачу для изменения оценки:",
            reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.error(f"Ошибка при загрузке задач: {e}")
        await query.edit_message_text("❌ Ошибка при загрузке задач")


async def handle_estimate_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    user_logging_state[user_id] = {
        "action": "estimate_edit",
        "task_id": task_id
    }

    await query.edit_message_text(
        "Введите новую оценку для задачи в формате:\n"
        "• 1.5h - полтора часа\n"
        "• 90m - 90 минут\n"
        "• 2h30m - 2 часа 30 минут\n\n"
        "Или просто число (в минутах): 150"
    )