import json
import os
import hashlib
import logging
import time
import threading
import httpx
import asyncio
from typing import Dict, Any, Set, List, Optional
from dotenv import load_dotenv

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
DATA_FILE = "user_contexts.json"
CLICKUP_API_TOKEN = os.getenv('CLICKUP_API_TOKEN')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_SALT = os.getenv('ADMIN_SALT', 'default_secret_salt')
user_data: Dict[int, Dict[str, Any]]
user_logging_state = {}
application = None
shutting_down = False
user_data_dirty = False
data_lock = threading.RLock()


def set_application(app):
    global application
    application = app


def get_application():
    return application


def get_shutting_down() -> bool:
    return shutting_down


def set_shutting_down(value: bool):
    global shutting_down
    shutting_down = value


def load_admin_hashes() -> Set[str]:
    admin_ids = os.getenv('ADMIN_IDS', '').split(',')
    return {
        hashlib.sha256(f"{ADMIN_SALT}{admin_id.strip()}".encode()).hexdigest()
        for admin_id in admin_ids if admin_id.strip()
    }


ADMIN_HASHES = load_admin_hashes()


def is_admin(user_id: int) -> bool:
    user_hash = hashlib.sha256(f"{ADMIN_SALT}{user_id}".encode()).hexdigest()
    return user_hash in ADMIN_HASHES


def load_user_data() -> Dict[int, Dict[str, Any]]:
    """Загружает данные пользователей из файла"""
    if not os.path.exists(DATA_FILE):
        return {}

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Преобразуем строковые ключи в целые числа
            return {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return {}


# Инициализация данных
user_data = load_user_data()
logger.info(f"Загружены данные для {len(user_data)} пользователей")


def save_user_data():
    global user_data_dirty
    try:
        with data_lock:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, indent=2, ensure_ascii=False)
            user_data_dirty = False
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")


def save_user_data_if_dirty():
    global user_data_dirty
    if user_data_dirty:
        save_user_data()


def update_user_context(user_id: int, key: str, value: Any) -> None:
    """Обновляет контекст пользователя"""
    global user_data, user_data_dirty

    with data_lock:
        context = get_user_context(user_id)

        if context.get(key) != value:
            context[key] = value
            user_data[user_id] = context
            user_data_dirty = True
            logger.debug(f"Обновлен контекст для {user_id}: {key} = {value}")


async def get_clickup_teams() -> List[Dict]:
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API токен не настроен!")
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.clickup.com/api/v2/team",
                headers={"Authorization": CLICKUP_API_TOKEN}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("teams", [])
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка HTTP при получении workspace: {e.response.status_code}")
    except Exception as e:
        logger.exception(f"Ошибка при получении workspace: {e}")
    return []


async def stop_application() -> None:
    """Корректное завершение работы приложения"""
    app = get_application()
    if not app:
        logger.error("Приложение не доступно для остановки")
        return

    logger.info("Останавливаю прием новых обновлений...")
    try:
        await app.stop()
        await asyncio.sleep(1)

        if app.running:
            logger.warning("Принудительное завершение работы...")
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Ошибка при остановке приложения: {e}")
    finally:
        logger.info("Приложение остановлено")
        os._exit(0)


def get_user_context(user_id: int) -> Dict[str, Any]:
    """Возвращает контекст пользователя"""
    with data_lock:
        if user_id not in user_data:
            user_data[user_id] = {
                "current_workspace": None,
                "current_sprint": None,
                "current_user": None
            }
            global user_data_dirty
            user_data_dirty = True
            logger.info(f"Создан новый контекст для пользователя {user_id}")

        return user_data[user_id]


def is_context_ready(user_id: int) -> bool:
    """Проверяет, установлены ли все необходимые параметры контекста"""
    context = get_user_context(user_id)
    return all([
        context.get("current_workspace"),
        context.get("current_sprint"),
        context.get("current_user")
    ])


def get_current_workspace_id(user_id: int) -> Optional[str]:
    """Возвращает ID текущего workspace пользователя"""
    context = get_user_context(user_id)
    return context.get("current_workspace")


async def get_clickup_sprints(workspace_id: str) -> List[Dict]:
    """Получает список спринтов из папки 'Sprint' в workspace"""
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API токен не настроен!")
        return []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Получаем все папки в workspace
            folders_response = await client.get(
                f"https://api.clickup.com/api/v2/team/{workspace_id}/folder?archived=false",
                headers={"Authorization": CLICKUP_API_TOKEN}
            )
            folders_response.raise_for_status()
            folders = folders_response.json().get("folders", [])

            # Ищем папку с названием, начинающимся на "Sprint"
            sprint_folder = None
            for folder in folders:
                if folder.get("name", "").lower().startswith("sprint"):
                    sprint_folder = folder
                    break

            if not sprint_folder:
                logger.error(f"Не найдена папка 'Sprint' в workspace {workspace_id}")
                return []

            # Получаем списки из папки спринтов
            lists_response = await client.get(
                f"https://api.clickup.com/api/v2/folder/{sprint_folder['id']}/list?archived=false",
                headers={"Authorization": CLICKUP_API_TOKEN}
            )
            lists_response.raise_for_status()
            sprint_lists = lists_response.json().get("lists", [])

            # Формируем список спринтов
            sprints = []
            for list_item in sprint_lists:
                sprints.append({
                    "id": list_item["id"],
                    "name": list_item.get("name", f"Sprint {list_item['id']}"),
                    "folder_id": sprint_folder['id'],
                    "folder_name": sprint_folder['name']
                })

            return sprints
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка HTTP при получении спринтов: {e.response.status_code}")
    except Exception as e:
        logger.exception(f"Ошибка при получении спринтов: {e}")
    return []


async def get_clickup_list_members(list_id: str) -> List[Dict]:
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API токен не настроен!")
        return []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.clickup.com/api/v2/list/{list_id}/member",
                headers={"Authorization": CLICKUP_API_TOKEN},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("members", [])
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка HTTP при получении участников: {e.response.status_code}")
        return []
    except httpx.RequestError as e:
        logger.error(f"Сетевая ошибка при получении участников: {e}")
        return []
    except Exception as e:
        logger.exception(f"Неизвестная ошибка при получении участников: {e}")
        return []


def format_members(members: List[Dict]) -> List[Dict]:
    """Форматирует список участников для отображения"""
    formatted = []
    for member in members:
        formatted.append({
            "id": member.get("id"),
            "username": member.get("username", "Unknown"),
            "email": member.get("email", ""),
            "initials": member.get("initials", "?"),
            "color": member.get("color", "#000000")
        })
    return formatted


def format_sprints(sprints: List[Dict]) -> List[Dict]:
    """Форматирует список спринтов для отображения"""
    return [
        {
            "id": sprint["id"],
            "name": sprint["name"],
            "folder_id": sprint["folder_id"],
            "folder_name": sprint["folder_name"]
        }
        for sprint in sprints
    ]


def format_workspaces(workspaces: List[Dict]) -> List[Dict]:
    return [
        {
            "id": ws["id"],
            "name": ws.get("name", f"Workspace {ws['id']}"),
            "color": ws.get("color", "#000000")
        }
        for ws in workspaces
    ]


async def get_user_tasks(sprint_id: str, user_id: str) -> List[Dict]:
    """Получает задачи пользователя в спринте со статусом 'in progress'"""
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API токен не настроен!")
        return []

    try:
        async with httpx.AsyncClient() as client:
            # Получаем задачи в спринте с фильтрами
            response = await client.get(
                f"https://api.clickup.com/api/v2/list/{sprint_id}/task",
                params={
                    "archived": "false",
                    "subtasks": "true",
                    "assignees[]": user_id,
                    "statuses[]": "in progress"
                },
                headers={"Authorization": CLICKUP_API_TOKEN},
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("tasks", [])
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка HTTP при получении задач: {e.response.status_code} - {e.response.text}")
        return []
    except httpx.RequestError as e:
        logger.error(f"Сетевая ошибка при получении задач: {e}")
        return []
    except Exception as e:
        logger.exception(f"Неизвестная ошибка при получении задач: {e}")
        return []


def format_tasks(tasks: List[Dict]) -> List[Dict]:
    """Форматирует список задач для отображения"""
    formatted = []
    for task in tasks:
        formatted.append({
            "id": task["id"],
            "name": task.get("name", f"Task {task['id']}"),
            "url": task.get("url", ""),
            "status": task.get("status", {}).get("status", "unknown")
        })
    return formatted


async def log_time_to_clickup(workspace_id: str, task_id: str, duration_ms: int, user_id: str) -> bool:
    """Логирует время в ClickUp"""
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API токен не настроен!")
        return False

    try:
        # Вычисляем начало задачи (текущее время минус длительность)
        end_time = int(time.time() * 1000)
        start_time = end_time - duration_ms

        payload = {
            "tid": task_id,
            "start": start_time,
            "duration": duration_ms,
            "assignee": int(user_id)
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.clickup.com/api/v2/team/{workspace_id}/time_entries",
                headers={
                    "Authorization": CLICKUP_API_TOKEN,
                    "Content-Type": "application/json"
                },
                json=payload
            )
            response.raise_for_status()
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"Ошибка HTTP при логировании времени: {e.response.status_code}")
    except Exception as e:
        logger.exception(f"Ошибка при логировании времени: {e}")
    return False


def parse_time_input(time_str: str) -> Optional[int]:
    """Преобразует строку времени в миллисекунды"""
    try:
        # Поддерживаемые форматы: 1.5h, 90m, 2h30m
        total_minutes = 0

        # Обработка часов
        if 'h' in time_str:
            hours_part = time_str.split('h')[0]
            hours = float(hours_part)
            total_minutes += hours * 60

        # Обработка минут
        if 'm' in time_str:
            minutes_part = time_str.split('m')[0]
            if 'h' in minutes_part:
                minutes_part = minutes_part.split('h')[-1]
            minutes = float(minutes_part)
            total_minutes += minutes

        # Если не указаны единицы измерения, считаем минутами
        if 'h' not in time_str and 'm' not in time_str:
            total_minutes = float(time_str)

        # Преобразуем минуты в миллисекунды
        return int(total_minutes * 60 * 1000)
    except ValueError:
        return None