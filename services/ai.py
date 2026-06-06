from config import ai_client, SYSTEM_PROMPT
from database import get_db


def build_context(db) -> dict:
    """Pulls a snapshot of agents, recent alerts, and recent tasks for the AI prompt."""
    agents = db.execute("""
        SELECT id, hostname, user, os, ip, last_seen, agent_group
        FROM agents LIMIT 20
    """).fetchall()

    alerts = db.execute("""
        SELECT log_id, timestamp, role, log_message, alert_level
        FROM logs ORDER BY timestamp DESC LIMIT 30
    """).fetchall()

    tasks = db.execute("""
        SELECT uuid, task_json, output, executed_at, scheduled_at, recurring_every, status
        FROM tasks ORDER BY scheduled_at DESC LIMIT 40
    """).fetchall()
    return {
        "agents":       [dict(r) for r in agents],
        "alerts":       [dict(r) for r in alerts],
        "recent_tasks": [dict(r) for r in tasks],
    }


def ask_ai(user_message: str, context: dict) -> str:
    """Sends the user message + DB context to Gemini and returns the response text."""
    prompt = f"""
{SYSTEM_PROMPT}

Context:
{context}

User:
{user_message}
"""
    response = ai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
    )
    return response.text