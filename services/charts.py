from collections import Counter
from database import get_db


def tasks_execution_timestamps(agent_id: str) -> dict:
    """
    Returns {date_str: count} of executed tasks for one agent.
    Used by the bar chart endpoint.
    """
    db         = get_db()
    rows       = db.execute(
        "SELECT executed_at FROM tasks WHERE agent_id = ?", (agent_id,)
    ).fetchall()

    timestamps = [row[0] for row in rows if row[0] is not None]
    dates      = [ts.split(" ")[0] for ts in timestamps]
    return dict(Counter(dates))


def task_success_rate(agent_id: str) -> dict:
    """
    Returns {status: count} for one agent.
    Used by the task success rate pie chart.
    """
    db       = get_db()
    rows     = db.execute(
        "SELECT status FROM tasks WHERE agent_id = ?", (agent_id,)
    ).fetchall()
    statuses = [row[0] for row in rows]
    return dict(Counter(statuses))