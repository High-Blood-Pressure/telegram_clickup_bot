import json
import os
import hashlib
import asyncio
import threading
from typing import Dict, Any, Set
from utils.config import DATA_FILE, ADMIN_SALT
from utils.logger import logger

application = None
shutting_down = False
user_data_dirty = False
user_logging_state = {}
data_lock = threading.RLock()
user_data = {}

def load_initial_user_data() -> Dict[int, Dict[str, Any]]:
    global user_data
    user_data = load_user_data()
    return user_data


def set_application(app) -> None:
    global application
    application = app


def get_application():
    return application


def set_shutting_down(value: bool) -> None:
    global shutting_down
    shutting_down = value


def get_shutting_down() -> bool:
    return shutting_down


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


def save_user_data() -> None:
    global user_data_dirty
    try:
        with data_lock:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, indent=2, ensure_ascii=False)
            user_data_dirty = False
    except Exception as e:
        logger.error(f"Error saving user data: {e}")


def save_user_data_if_dirty() -> None:
    global user_data_dirty
    if user_data_dirty:
        save_user_data()


def update_user_context(user_id: int, key: str, value: Any) -> None:
    global user_data, user_data_dirty

    with data_lock:
        context = get_user_context(user_id)
        if context.get(key) != value:
            context[key] = value
            user_data[user_id] = context
            user_data_dirty = True
            logger.debug(f"Updated context for {user_id}: {key} = {value}")


def get_user_context(user_id: int) -> Dict[str, Any]:
    with data_lock:
        if user_id not in user_data:
            user_data[user_id] = {
                "current_workspace": None,
                "current_sprint": None,
                "current_user": None,
                "current_user_name": None
            }
            global user_data_dirty
            user_data_dirty = True
            logger.info(f"Created new context for user {user_id}")

        return user_data[user_id]



def load_user_data() -> Dict[int, Dict[str, Any]]:
    if not os.path.exists(DATA_FILE):
        return {}

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return {}


async def stop_application() -> None:
    app = get_application()
    if not app:
        logger.error("Application not available for shutdown")
        return

    logger.info("Stopping new updates processing...")
    try:
        await app.stop()
        await asyncio.sleep(1)

        if app.running:
            logger.warning("Forcing shutdown...")
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Error stopping application: {e}")
    finally:
        logger.info("Application stopped")
        os._exit(0)