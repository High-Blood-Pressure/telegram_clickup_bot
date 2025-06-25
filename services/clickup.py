import httpx
import functools
from cachetools import TTLCache
from utils.config import CLICKUP_API_TOKEN
from utils.logger import logger
from typing import List, Dict

cache = TTLCache(maxsize=100, ttl=300)

def cache_async(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        key = (func.__name__, args, tuple(kwargs.items()))
        if key in cache:
            return cache[key]
        result = await func(*args, **kwargs)
        cache[key] = result
        return result
    return wrapper

@cache_async
async def get_clickup_teams() -> List[Dict]:
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API token not configured!")
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
        logger.error(f"HTTP error getting workspaces: {e.response.status_code}")
    except Exception as e:
        logger.exception(f"Error getting workspaces: {e}")
    return []

@cache_async
async def get_clickup_sprints(workspace_id: str) -> List[Dict]:
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API token not configured!")
        return []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            folders_response = await client.get(
                f"https://api.clickup.com/api/v2/team/{workspace_id}/folder?archived=false",
                headers={"Authorization": CLICKUP_API_TOKEN}
            )
            folders_response.raise_for_status()
            folders = folders_response.json().get("folders", [])

            sprint_folder = None
            for folder in folders:
                if folder.get("name", "").lower().startswith("sprint"):
                    sprint_folder = folder
                    break

            if not sprint_folder:
                logger.error(f"Sprint folder not found in workspace {workspace_id}")
                return []

            lists_response = await client.get(
                f"https://api.clickup.com/api/v2/folder/{sprint_folder['id']}/list?archived=false",
                headers={"Authorization": CLICKUP_API_TOKEN}
            )
            lists_response.raise_for_status()
            sprint_lists = lists_response.json().get("lists", [])

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
        logger.error(f"HTTP error getting sprints: {e.response.status_code}")
    except Exception as e:
        logger.exception(f"Error getting sprints: {e}")
    return []

@cache_async
async def get_clickup_list_members(list_id: str) -> List[Dict]:
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API token not configured!")
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
        logger.error(f"HTTP error getting members: {e.response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Network error getting members: {e}")
    except Exception as e:
        logger.exception(f"Unknown error getting members: {e}")
    return []

@cache_async
async def get_all_user_tasks_in_sprint(sprint_id: str, user_id: str) -> List[Dict]:
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API token not configured!")
        return []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.clickup.com/api/v2/list/{sprint_id}/task",
                params={
                    "include_closed": "true",
                    "subtasks": "true",
                    "assignees[]": user_id
                },
                headers={"Authorization": CLICKUP_API_TOKEN},
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("tasks", [])
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error getting tasks: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Network error getting tasks: {e}")
    except Exception as e:
        logger.exception(f"Unknown error getting tasks: {e}")
    return []

@cache_async
async def get_all_tasks_in_sprint(sprint_id: str) -> List[Dict]:
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API token not configured!")
        return []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.clickup.com/api/v2/list/{sprint_id}/task",
                params={
                    "include_closed": "true",
                    "subtasks": "true"
                },
                headers={"Authorization": CLICKUP_API_TOKEN},
                timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("tasks", [])
    except Exception as e:
        logger.exception(f"Error getting tasks: {e}")
    return []


async def put_new_task_estimate(task_id: str, estimate_minutes: float) -> bool:
    if not CLICKUP_API_TOKEN:
        logger.error("ClickUp API token not configured!")
        return False

    estimate_ms = int(estimate_minutes * 60 * 1000)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"https://api.clickup.com/api/v2/task/{task_id}",
                json={"time_estimate": estimate_ms},
                headers={"Authorization": CLICKUP_API_TOKEN},
                timeout=15.0
            )
            response.raise_for_status()

            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error updating task estimate: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.exception(f"Error updating task estimate: {e}")
    return False