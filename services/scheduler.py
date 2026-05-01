import json
import sqlite3
import threading
import time
from datetime import datetime, timezone

from config import DATABASE


def recurring_scheduler(task_uuid, recurring_every, agent_id, command):
    """
    Background thread: re-inserts a recurring task every N minutes.
    Opens its own DB connection so it doesn't share Flask's per-request one.
    """
    minutes = int(recurring_every)
    seconds = minutes * 60
    time.sleep(seconds)

    while True:
        try:
            conn = sqlite3.connect(DATABASE)
            db   = conn.cursor()

            # Only re-queue if the original task still exists and has no output
            db.execute("""
                SELECT uuid FROM tasks
                WHERE recurring_every IS NOT NULL
                  AND recurring_every != 'N/A'
                  AND recurring_every > 0
                  AND output IS NULL
            """)
            task = db.fetchone()

            if task:
                import uuid as _uuid
                new_uuid     = str(_uuid.uuid4())
                current_time = datetime.now(timezone.utc)

                db.execute("""
                    INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
                    VALUES (?, ?, ?, NULL, ?, NULL)
                """, (new_uuid, agent_id, json.dumps(command), current_time))

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"[scheduler] Error in recurring loop: {e}")

        time.sleep(seconds)


def restart_recurring_tasks(app):
    """
    Called at startup — finds all recurring tasks in the DB and
    re-starts their background threads.
    """
    with app.app_context():
        try:
            conn = sqlite3.connect(DATABASE)
            db   = conn.cursor()

            db.execute("""
                SELECT uuid, agent_id, task_json, recurring_every, output
                FROM tasks
                WHERE recurring_every IS NOT NULL
                  AND recurring_every != 'N/A'
                  AND recurring_every > 0
                  AND output IS NULL
            """)
            tasks = db.fetchall()
            conn.close()

            for task in tasks:
                task_uuid, agent_id, task_json, recurring_every, _ = task
                command = json.loads(task_json)

                thread = threading.Thread(
                    target=recurring_scheduler,
                    args=(task_uuid, recurring_every, agent_id, command),
                    daemon=True
                )
                thread.start()

        except Exception as e:
            print(f"[scheduler] Error resuming tasks: {e}")