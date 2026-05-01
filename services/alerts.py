import uuid
from datetime import datetime, timezone, timedelta

from config import AGENT_ALERT_TIMEOUT
from database import get_db
from services.charts import task_success_rate


def gen_alerts():
    """
    Checks two conditions and writes Critical logs if triggered:
      1. Agent offline longer than AGENT_ALERT_TIMEOUT days
      2. Agent task success rate below 15%
    De-duplicates: only one log per condition per day.
    """
    db           = get_db()
    current_time = datetime.now(timezone.utc)
    today_str    = current_time.strftime("%Y-%m-%d")

    # ── 1. Offline agents ────────────────────────────────────────────────────
    rows = db.execute("SELECT id, last_seen FROM agents").fetchall()

    for row in rows:
        try:
            last_seen = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except (ValueError, TypeError):
            continue

        if (current_time - last_seen) >= timedelta(days=AGENT_ALERT_TIMEOUT):
            log_message = (
                f"Agent {row[0]} been offline for more than {AGENT_ALERT_TIMEOUT} days"
            )
            exists = db.execute(
                "SELECT 1 FROM logs WHERE log_message = ? AND DATE(timestamp) = ?",
                (log_message, today_str),
            ).fetchone()

            if not exists:
                db.execute(
                    "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), current_time, "None", log_message, "Critical", "None"),
                )
                db.commit()

    # ── 2. Low success rate ──────────────────────────────────────────────────
    agents = db.execute("SELECT id FROM agents").fetchall()

    for agent_row in agents:
        agent_id = agent_row[0]
        stats    = task_success_rate(agent_id)

        success = stats.get("success", 0)
        failure = stats.get("failure", 0)
        pending = stats.get("pending", 0)
        total   = success + failure + pending
        rate    = int(success / total * 100) if total else 0

        if rate < 15:
            log_message = f"Low execution success rate for Agent {agent_id}"
            exists = db.execute(
                "SELECT 1 FROM logs WHERE log_message = ? AND DATE(timestamp) = ?",
                (log_message, today_str),
            ).fetchone()

            if not exists:
                db.execute(
                    "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), current_time, "None", log_message, "Critical", "None"),
                )
                db.commit()