import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import helpers

# ======================
#  COMMANDS HANDLERS
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    helpers.get_user_context(user_id)

    text = (
        "🚀 Добро пожаловать в TimeLoggerBot!\n\n"
        "🛠️ Перед началом работы настройте контекст /context.\n"
        "📊 Основные команды:\n"
        "/context - Показать текущий контекст\n\n"
        "⚙️ Для администраторов:\n"
        "/shutdown - Выключить бота"
    )

    await update.message.reply_text(text)


async def change_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем список workspace
        workspaces = await helpers.get_clickup_teams()
        if not workspaces:
            await update.callback_query.edit_message_text("❌ Не удалось получить список workspace. Проверьте API токен ClickUp.")
            return

        # Форматируем workspace для отображения
        formatted_workspaces = helpers.format_workspaces(workspaces)

        # Создаем клавиатуру для выбора
        keyboard = []
        for ws in formatted_workspaces:
            keyboard.append([InlineKeyboardButton(ws["name"], callback_data=f"ws_{ws['id']}")])

        await update.callback_query.edit_message_text(
            "🏢 Выберите workspace:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        helpers.logger.error(f"Ошибка в change_workspace: {e}")
        await update.message.edit_text("⚠️ Произошла ошибка при загрузке workspace. Попробуйте позже.")


async def change_sprint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        context_data = helpers.get_user_context(user_id)

        workspace_id = context_data.get("current_workspace")
        if not workspace_id:
            await update.callback_query.edit_message_text(
                "❌ Сначала выберите workspace через /context"
            )
            return

        sprints = await helpers.get_clickup_sprints(workspace_id)
        if not sprints:
            await update.callback_query.edit_message_text(
                "❌ Не удалось найти папку 'Sprint' или спринты в ней. Убедитесь, что в workspace есть папка с названием, начинающимся на 'Sprint'."
            )
            return

        formatted_sprints = helpers.format_sprints(sprints)
        keyboard = []
        for sprint in formatted_sprints:
            keyboard.append([InlineKeyboardButton(
                sprint["name"],
                callback_data=f"sprint_{sprint['id']}"
            )])

        folder_name = formatted_sprints[0]["folder_name"] if formatted_sprints else "Sprint"

        await update.callback_query.edit_message_text(
            f"⏳ Выберите спринт из папки '{folder_name}':",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        helpers.logger.error(f"Ошибка в change_sprint: {e}")
        await update.message.edit_text("⚠️ Произошла ошибка при загрузке sprint. Попробуйте позже.")


async def change_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        context_data = helpers.get_user_context(user_id)

        # Проверяем, выбран ли workspace и спринт
        if not context_data.get("current_workspace"):
            await update.callback_query.edit_message_text(
                "❌ Сначала выберите workspace через /context"
            )
            return

        if not context_data.get("current_sprint"):
            await update.callback_query.edit_message_text(
                "❌ Сначала выберите спринт через /context"
            )
            return

        sprint_id = context_data["current_sprint"]
        members = await helpers.get_clickup_list_members(sprint_id)

        if not members:
            await update.callback_query.edit_message_text(
                "❌ Не удалось получить список пользователей для этого спринта."
            )
            return

        formatted_members = helpers.format_members(members)
        keyboard = []
        for member in formatted_members:
            # Используем username и email для отображения
            display_name = f"{member['username']}"
            if member['email']:
                display_name += f" ({member['email']})"

            keyboard.append([InlineKeyboardButton(
                display_name,
                callback_data=f"user_{member['id']}"
            )])

        await update.callback_query.edit_message_text(
            "👤 Выберите пользователя:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        helpers.logger.error(f"Ошибка в change_user: {e}")
        await update.message.edit_text("⚠️ Произошла ошибка при загрузке user. Попробуйте позже.")


async def log_my_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context_data = helpers.get_user_context(user_id)

    required = ["current_workspace", "current_sprint", "current_user"]
    if not all(context_data.get(key) for key in required):
        await update.callback_query.edit_message_text(
            "❌ Конфигурация не завершена!\n"
        )
        return

    sprint_id = context_data["current_sprint"]
    clickup_user_id = context_data["current_user"]
    tasks = await helpers.get_user_tasks(sprint_id, clickup_user_id)

    if not tasks:
        await update.callback_query.edit_message_text("❌ Нет задач в работе. Все задачи завершены или еще не начаты.")
        return

    # Кэшируем задачи
    for task in tasks:
        helpers.cache_task({
            "id": task["id"],
            "name": task.get("name", ""),
            "url": task.get("url", ""),
            "status": task.get("status", {}).get("status", "unknown"),
            "workspace_id": context_data["current_workspace"],
            "sprint_id": sprint_id
        })

    # Форматируем задачи для отображения
    formatted_tasks = helpers.format_tasks(tasks)

    # Сохраняем задачи в состоянии пользователя
    helpers.user_logging_state[user_id] = {
        "tasks": formatted_tasks,
        "workspace_id": context_data["current_workspace"],
        "clickup_user_id": clickup_user_id
    }

    # Создаем клавиатуру для выбора задачи
    keyboard = []
    for task in formatted_tasks:
        # Обрезаем длинные названия задач
        task_name = task["name"]
        if len(task_name) > 50:
            task_name = task_name[:47] + "..."

        keyboard.append([InlineKeyboardButton(
            task_name,
            callback_data=f"task_{task['id']}"
        )])

    # Добавляем кнопку отмены
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="log_cancel")])

    await update.callback_query.edit_message_text(
        "✅ Выберите задачу для логирования времени:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def shutdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выключение бота с проверкой прав администратора"""
    if helpers.get_shutting_down():
        await update.message.reply_text("🔄 Бот уже выключается...")
        return

    user_id = update.effective_user.id

    if not helpers.is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав на эту команду")
        helpers.logger.warning(f"Неавторизованная попытка выключения от {user_id}")
        return

    helpers.logger.info(f"Инициировано выключение администратором {user_id}")
    helpers.set_shutting_down(True)

    # Запускаем процесс выключения в фоне
    asyncio.create_task(helpers.stop_application())
    await update.message.reply_text("🛑 Выключаю бота...")


async def current_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущие настройки пользователя"""
    try:
        user_id = update.effective_user.id
        context_data = helpers.get_user_context(user_id)
        text = "⚙️ <b>Текущие настройки контекста</b>\n\n"

        # Информация о workspace
        workspace_id = context_data.get("current_workspace")
        if workspace_id:
            workspaces = await helpers.get_clickup_teams()
            workspace = next((ws for ws in helpers.format_workspaces(workspaces)
                              if ws["id"] == workspace_id), None)
            if workspace:
                text += f"🏢 <b>Workspace:</b> {workspace['name']} (ID: {workspace_id})\n"
            else:
                text += f"🏢 <b>Workspace:</b> ID {workspace_id} (информация недоступна)\n"
        else:
            text += "🏢 <b>Workspace:</b> не выбран\n"

        # Разделитель
        text += "────────────────\n"

        # Информация о спринте
        sprint_id = context_data.get("current_sprint")
        if sprint_id:
            if workspace_id:
                sprints = await helpers.get_clickup_sprints(workspace_id)
                sprint = next((s for s in helpers.format_sprints(sprints) if s["id"] == sprint_id), None)
                if sprint:
                    text += f"⏳ <b>Спринт:</b> {sprint['name']}\n"
                    text += f"   <i>Папка:</i> {sprint.get('folder_name', 'Sprint')}\n"
                else:
                    text += f"⏳ <b>Спринт:</b> ID {sprint_id} (информация недоступна)\n"
            else:
                text += f"⏳ <b>Спринт:</b> ID {sprint_id} (workspace не выбран)\n"
        else:
            text += "⏳ <b>Спринт:</b> не выбран\n"

        # Разделитель
        text += "────────────────\n"

        # Информация о пользователе
        user_id_str = context_data.get("current_user")
        if user_id_str:
            if sprint_id:
                members = await helpers.get_clickup_list_members(sprint_id)
                member = next((m for m in helpers.format_members(members)
                               if str(m["id"]) == str(user_id_str)), None)
                if member:
                    text += f"👤 <b>Пользователь:</b> {member['username']}\n"
                    text += f"   <i>ID:</i> {member['id']}\n"
                    if member['email']:
                        text += f"   <i>Email:</i> {member['email']}\n"
                else:
                    text += f"👤 <b>Пользователь:</b> ID {user_id_str} (не найден в спринте)\n"
            else:
                text += f"👤 <b>Пользователь:</b> ID {user_id_str} (спринт не выбран)\n"
        else:
            text += "👤 <b>Пользователь:</b> не выбран\n"

        # Разделитель
        text += "────────────────\n"

        # Кнопки быстрого изменения
        keyboard = [
            [InlineKeyboardButton("Изменить workspace", callback_data="change_workspace")],
            [InlineKeyboardButton("Изменить спринт", callback_data="change_sprint")],
            [InlineKeyboardButton("Изменить пользователя", callback_data="change_user")],
            [InlineKeyboardButton("Залогировать время в задачу пользователя", callback_data="log_my_time")]
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
        helpers.logger.error(f"Ошибка в current_context: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка при отображении контекста. Попробуйте позже.")

# ======================
#  BUTTON HANDLERS
# ======================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на inline-кнопки"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # Обработка кнопок изменения контекста
    if data == "change_workspace":
        await query.edit_message_text("🔄 Загружаю список workspace...")
        await change_workspace(update, context)
        return
    elif data == "change_sprint":
        await query.edit_message_text("🔄 Загружаю список спринтов...")
        await change_sprint(update, context)
        return
    elif data == "change_user":
        await query.edit_message_text("🔄 Загружаю список пользователей...")
        await change_user(update, context)
        return
    elif data == "log_my_time":
        await query.edit_message_text("🔄 Загружаю список задач...")
        await log_my_time(update, context)
        return

    if data.startswith("ws_"):
        workspace_id = data.split("_", 1)[1]
        helpers.update_user_context(user_id, "current_workspace", workspace_id)
        helpers.update_user_context(user_id, "current_sprint", None)  # Сбрасываем спринт
        helpers.update_user_context(user_id, "current_user", None)  # Сбрасываем пользователя
        await query.edit_message_text(f"✅ Workspace установлен: ID {workspace_id}\n⏳ Загружаю контекстное меню..")
        await current_context(update, context)


    elif data.startswith("sprint_"):
        sprint_id = data.split("_", 1)[1]
        helpers.update_user_context(user_id, "current_sprint", sprint_id)
        helpers.update_user_context(user_id, "current_user", None)  # Сбрасываем пользователя
        workspace_id = helpers.get_user_context(user_id).get("current_workspace")
        sprints = await helpers.get_clickup_sprints(workspace_id)
        sprint_name = next((s["name"] for s in helpers.format_sprints(sprints) if s["id"] == sprint_id), sprint_id)
        await query.edit_message_text(f"✅ Спринт установлен: {sprint_name}\n⏳ Загружаю контекстное меню..")
        await current_context(update, context)


    elif data.startswith("user_"):
        user_id_str = data.split("_", 1)[1]
        helpers.update_user_context(user_id, "current_user", user_id_str)
        sprint_id = helpers.get_user_context(user_id).get("current_sprint")
        if sprint_id:
            members = await helpers.get_clickup_list_members(sprint_id)
            member_name = next(
                (m["username"] for m in helpers.format_members(members) if str(m["id"]) == user_id_str),
                user_id_str
            )
            await query.edit_message_text(f"✅ Пользователь установлен: {member_name}\n⏳ Загружаю контекстное меню..")
        else:
            await query.edit_message_text(f"✅ Пользователь установлен: ID {user_id_str}\n⏳ Загружаю контекстное меню..")

        await current_context(update, context)


    elif data.startswith("task_"):
        task_id = data.split("_", 1)[1]

        # Сохраняем выбранную задачу
        if user_id in helpers.user_logging_state:
            helpers.user_logging_state[user_id]["task_id"] = task_id

            # Находим имя задачи для отображения
            task_name = next((t["name"] for t in helpers.user_logging_state[user_id]["tasks"]
                              if t["id"] == task_id), "Задача")

            await query.edit_message_text(
                f"⏱ Выбрана задача: {task_name}\n\n"
                "Введите время в формате:\n"
                "• 1.5h - полтора часа\n"
                "• 90m - 90 минут\n"
                "• 2h30m - 2 часа 30 минут\n\n"
                "Или просто число (в минутах): 150"
            )

    # Обработка отмены логирования
    elif data == "log_cancel":
        if user_id in helpers.user_logging_state:
            del helpers.user_logging_state[user_id]
        await query.edit_message_text("❌ Логирование времени отменено")


# ======================
#  MESSAGE HANDLERS
# ======================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    message_text = update.message.text

    # Проверяем, находится ли пользователь в процессе логирования
    if user_id in helpers.user_logging_state and "task_id" in helpers.user_logging_state[user_id]:
        # Парсим введенное время
        duration_ms = helpers.parse_time_input(message_text)
        if not duration_ms or duration_ms <= 0:
            await update.message.reply_text(
                "❌ Неверный формат времени. Используйте:\n"
                "• 1.5h - полтора часа\n"
                "• 90m - 90 минут\n"
                "• 2h30m - 2 часа 30 минут"
            )
            return

        # Получаем данные для логирования
        task_id = helpers.user_logging_state[user_id]["task_id"]
        clickup_user_id = helpers.user_logging_state[user_id]["clickup_user_id"]

        # Проверим, что задача существует в состоянии пользователя
        task_exists = any(task["id"] == task_id
                          for task in helpers.user_logging_state[user_id]["tasks"])

        if not task_exists:
            await update.message.reply_text("❌ Ошибка: задача не найдена")
            del helpers.user_logging_state[user_id]
            return

        # Логируем время
        loading_msg = await update.message.reply_text("⏳ Сохраняю время...")

        # Сохраняем время локально
        duration_minutes = duration_ms / 60000.0  # Конвертируем в минуты
        success = helpers.log_time_locally(task_id, clickup_user_id, duration_minutes)

        # Удаляем сообщение о загрузке
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=loading_msg.message_id
        )

        # Обрабатываем результат
        if success:
            # Получаем общее время пользователя по этой задаче
            total_minutes = helpers.get_task_time_for_user(task_id, clickup_user_id)
            total_hours = total_minutes / 60.0

            # Форматируем вывод
            if total_hours >= 1:
                time_str = f"{total_hours:.1f} ч"
            else:
                time_str = f"{total_minutes:.0f} мин"

            task_name = next((t["name"] for t in helpers.user_logging_state[user_id]["tasks"]
                              if t["id"] == task_id), "Задача")

            await update.message.reply_text(
                f"✅ Время успешно сохранено!\n"
                f"• Затрачено: {duration_minutes:.1f} мин\n"
                f"• Всего по задаче: {time_str}\n"
                f"• Задача: {task_name}")

            loading_msg = await update.message.reply_text("⏳ Загружаю контекстное меню..")
            await current_context(update, context)
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=loading_msg.message_id
            )
        else:
            await update.message.reply_text("❌ Ошибка при сохранении времени. Попробуйте позже.")

        # Очищаем состояние
        del helpers.user_logging_state[user_id]
        return

    # Обработка других сообщений
    else:
        await update.message.reply_text("ℹ️ Используйте команды меню для работы с ботом")