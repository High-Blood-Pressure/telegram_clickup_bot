from typing import List, Dict

def format_members(members: List[Dict]) -> List[Dict]:
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


def format_tasks(tasks: List[Dict]) -> List[Dict]:
    formatted = []
    for task in tasks:
        estimated_ms = task.get("time_estimate")
        estimated_minutes = estimated_ms / 60000.0 if estimated_ms else 0

        formatted.append({
            "id": task["id"],
            "name": task.get("name", f"Task {task['id']}"),
            "url": task.get("url", ""),
            "status": task.get("status", {}).get("status", "unknown"),
            "estimated_minutes": estimated_minutes
        })
    return formatted