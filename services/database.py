import sqlite3
import threading
import time
from typing import List, Dict, Optional
from utils.config import DB_FILE
from utils.logger import logger

db_lock = threading.RLock()


def init_db() -> None:
    try:
        with db_lock, sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS tasks
                           (
                               task_id
                               TEXT
                               PRIMARY
                               KEY,
                               name
                               TEXT
                               NOT
                               NULL,
                               url
                               TEXT,
                               status
                               TEXT,
                               workspace_id
                               TEXT,
                               sprint_id
                               TEXT,
                               estimated_minutes
                               REAL,
                               last_updated
                               REAL
                           )
                           """)

            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS task_time
                           (
                               task_id
                               TEXT
                               NOT
                               NULL,
                               user_id
                               TEXT
                               NOT
                               NULL,
                               user_name
                               TEXT,
                               total_minutes
                               REAL
                               NOT
                               NULL
                               DEFAULT
                               0,
                               PRIMARY
                               KEY
                           (
                               task_id,
                               user_id
                           ),
                               FOREIGN KEY
                           (
                               task_id
                           ) REFERENCES tasks
                           (
                               task_id
                           )
                               )
                           """)

            conn.commit()
            logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")


def log_time_locally(task_id: str, user_id: str, user_name: str, duration_minutes: float) -> bool:
    try:
        with db_lock, sqlite3.connect(DB_FILE) as conn:
            conn.execute("""
                         INSERT INTO task_time (task_id, user_id, user_name, total_minutes)
                         VALUES (?, ?, ?, ?) ON CONFLICT(task_id, user_id) DO
                         UPDATE SET
                             total_minutes = total_minutes + excluded.total_minutes,
                             user_name = excluded.user_name
                         """, (task_id, user_id, user_name, duration_minutes))
            conn.commit()
            return True
    except sqlite3.Error as e:
        logger.error(f"Error logging time: {e}")
        return False


def get_task_time_for_user(task_id: str, user_id: str) -> float:
    try:
        with db_lock, sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT total_minutes
                           FROM task_time
                           WHERE task_id = ?
                             AND user_id = ?
                           """, (task_id, user_id))
            result = cursor.fetchone()
            return result[0] if result else 0.0
    except sqlite3.Error as e:
        logger.error(f"Error fetching task time: {e}")
        return 0.0


def cache_task(task_data: dict) -> None:
    try:
        with db_lock, sqlite3.connect(DB_FILE) as conn:
            conn.execute("""
            INSERT OR REPLACE INTO tasks (
                task_id, name, url, status, 
                workspace_id, sprint_id, 
                estimated_minutes, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_data["id"],
                task_data.get("name", ""),
                task_data.get("url", ""),
                task_data.get("status", "unknown"),
                task_data.get("workspace_id"),
                task_data.get("sprint_id"),
                task_data.get("estimated_minutes", 0),
                time.time()
            ))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error caching task: {e}")


def get_sprint_tasks_from_cache(sprint_id: str) -> List[Dict]:
    try:
        with db_lock, sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT task_id,
                                  name,
                                  url,
                                  status,
                                  estimated_minutes
                           FROM tasks
                           WHERE sprint_id = ?
                           """, (sprint_id,))

            return [{
                "id": row[0],
                "name": row[1],
                "url": row[2],
                "status": row[3],
                "estimated_minutes": row[4]
            } for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Error fetching sprint tasks: {e}")
        return []


def get_all_tasks_in_sprint_with_time(sprint_id: str) -> List[Dict]:
    try:
        with db_lock, sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT t.task_id,
                                  t.name,
                                  t.url,
                                  t.status,
                                  t.estimated_minutes
                           FROM tasks t
                           WHERE t.sprint_id = ?
                           """, (sprint_id,))

            tasks = []
            for row in cursor.fetchall():
                task = {
                    "id": row[0],
                    "name": row[1],
                    "url": row[2],
                    "status": row[3],
                    "estimated_minutes": row[4]
                }

                cursor.execute("""
                               SELECT user_id,
                                      user_name,
                                      total_minutes
                               FROM task_time
                               WHERE task_id = ?
                               """, (row[0],))

                task["assignees"] = [{
                    "user_id": a_row[0],
                    "user_name": a_row[1],
                    "minutes": a_row[2]
                } for a_row in cursor.fetchall()]

                tasks.append(task)

            return tasks
    except sqlite3.Error as e:
        logger.error(f"Error fetching sprint tasks with time: {e}")
        return []


def get_sprint_tasks_summary(sprint_id: str) -> List[Dict]:
    try:
        with db_lock, sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT t.task_id,
                                  t.name,
                                  t.url,
                                  t.status,
                                  t.estimated_minutes,
                                  tt.user_id,
                                  tt.user_name,
                                  tt.total_minutes
                           FROM tasks t
                                    LEFT JOIN task_time tt ON t.task_id = tt.task_id
                           WHERE t.sprint_id = ?
                           ORDER BY t.task_id
                           """, (sprint_id,))

            tasks_map = {}
            for row in cursor.fetchall():
                task_id = row["task_id"]

                if task_id not in tasks_map:
                    tasks_map[task_id] = {
                        "id": task_id,
                        "name": row["name"],
                        "url": row["url"],
                        "status": row["status"],
                        "estimated_minutes": row["estimated_minutes"],
                        "assignees": []
                    }

                if row["user_id"]:
                    tasks_map[task_id]["assignees"].append({
                        "user_id": row["user_id"],
                        "user_name": row["user_name"],
                        "minutes": row["total_minutes"]
                    })

            return list(tasks_map.values())
    except sqlite3.Error as e:
        logger.error(f"Error fetching sprint summary: {e}")
        return []
