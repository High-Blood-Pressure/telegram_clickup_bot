from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.user_manager import get_user_context, update_user_context, user_logging_state
from services import clickup, database, get_sprint_tasks_summary, get_all_tasks_in_sprint, cache_task
from utils.formatting import format_workspaces, format_sprints, format_members, format_tasks
from utils.logger import logger
from handlers import current_context

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

    elif data.startswith("ws_"):
        workspace_id = data.split("_", 1)[1]
        update_user_context(user_id, "current_workspace", workspace_id)
        update_user_context(user_id, "current_sprint", None)
        update_user_context(user_id, "current_user", None)
        update_user_context(user_id, "current_workspace_name", None)
        update_user_context(user_id, "current_sprint_name", None)
        update_user_context(user_id, "current_user_name", None)
        await query.edit_message_text(f"✅ Workspace установлен\n⏳ Загружаю контекстное меню..")
        await current_context(update, context)

    elif data.startswith("sprint_"):
        sprint_id = data.split("_", 1)[1]
        update_user_context(user_id, "current_sprint", sprint_id)
        update_user_context(user_id, "current_user", None)
        update_user_context(user_id, "current_sprint_name", None)
        update_user_context(user_id, "current_user_name", None)
        await query.edit_message_text(f"✅ Спринт установлен\n⏳ Загружаю контекстное меню..")
        await current_context(update, context)

    elif data.startswith("user_"):
        parts = data.split("_", 2)
        user_id_str = parts[1]
        user_name = parts[2] if len(parts) > 2 else f"User {user_id_str}"
        update_user_context(user_id, "current_user", user_id_str)
        update_user_context(user_id, "current_user_name", user_name)
        await query.edit_message_text(f"✅ Пользователь установлен: {user_name}\n⏳ Загружаю контекстное меню..")
        await current_context(update, context)

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
        with database.db_lock:
            with database.sqlite3.connect(database.DB_FILE) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                               SELECT t.task_id,
                                      t.name,
                                      t.url,
                                      t.status,
                                      t.estimated_minutes,
                                      tt.total_minutes
                               FROM tasks t
                                        JOIN task_time tt ON t.task_id = tt.task_id
                               WHERE t.sprint_id = ?
                                 AND tt.user_id = ?
                               """, (sprint_id, user_id_str))

                tasks = []
                for row in cursor.fetchall():
                    tasks.append({
                        "id": row[0],
                        "name": row[1],
                        "url": row[2],
                        "status": row[3],
                        "estimated_minutes": row[4],
                        "logged_minutes": row[5] or 0
                    })

                if not tasks:
                    await query.edit_message_text("❌ У вас нет задач в этом спринте.")
                    return

                message = "📊 <b>Ваша статистика по задачам:</b>\n\n"
                message += "<pre>"
                message += "┌──────────────────────────────────────┬───────────┬───────────┬─────────────┐\n"
                message += "│ Задача                               │ Оценка (ч)│ Залог. (ч)│ Статус      │\n"
                message += "├──────────────────────────────────────┼───────────┼───────────┼─────────────┤\n"

                total_estimated = 0.0
                total_logged = 0.0

                for task in tasks:
                    estimated_hours = task['estimated_minutes'] / 60 if task.get('estimated_minutes') else 0
                    logged_hours = task['logged_minutes'] / 60

                    total_estimated += estimated_hours
                    total_logged += logged_hours

                    estimated_str = f"{estimated_hours:.1f}" if estimated_hours > 0 else "-"
                    logged_str = f"{logged_hours:.1f}" if logged_hours > 0 else "-"

                    task_name = task['name']
                    if len(task_name) > 30:
                        task_name = task_name[:27] + "..."

                    message += f"│ {task_name:<36} │ {estimated_str:>9} │ {logged_str:>9} │ {task['status']:<11} │\n"

                message += "├──────────────────────────────────────┼───────────┼───────────┼─────────────┤\n"
                message += f"│ {'Итого':<36} │ {total_estimated:>9.1f} │ {total_logged:>9.1f} │ {'':<11} │\n"
                message += "└──────────────────────────────────────┴───────────┴───────────┴─────────────┘\n"
                message += "</pre>\n\n"

                await query.edit_message_text(message, parse_mode="HTML")

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

            if task['estimated_minutes']:
                est_hours = task['estimated_minutes'] / 60
                message += f"   Оценка: {est_hours:.1f}ч | "

            total_minutes = sum(a['minutes'] for a in task['assignees'])
            total_hours = total_minutes / 60
            message += f"Залог.: {total_hours:.1f}ч\n"

            if task['assignees']:
                for assignee in task['assignees']:
                    user_name = assignee['user_name'] or f"User {assignee['user_id']}"
                    user_time = assignee['minutes'] / 60
                    message += f"   👤 {user_name}: {user_time:.1f}ч\n"
            else:
                message += "   👤 Нет данных\n"

            message += "────────────────\n"

        await query.edit_message_text(
            message,
            parse_mode="HTML",
            disable_web_page_preview=True
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