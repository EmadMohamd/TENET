import json
import uuid
import threading
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for

from config import API_KEY
from database import get_db
from middleware.auth import require_token
from services.scheduler import recurring_scheduler

tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.route("/tasks/")
@require_token(role="admin")
def tasks_list():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    db   = get_db()
    rows = db.execute("""
        SELECT uuid, agent_id, task_json, output
        FROM tasks ORDER BY rowid DESC
    """).fetchall()

    tasks_str = {
        str(t["uuid"]): {
            "agent_id": t["agent_id"],
            "task":     json.loads(t["task_json"]),
            "output":   t["output"],
        }
        for t in rows
    }
    return render_template("tasks.html", tasks=tasks_str, api_key=API_KEY)


@tasks_bp.route("/tasks-data")
@require_token(role="admin")
def tasks_data():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    db   = get_db()
    rows = db.execute("""
        SELECT uuid, agent_id, task_json, output, executed_at,
               scheduled_at, recurring_every, status
        FROM tasks ORDER BY rowid DESC
    """).fetchall()

    tasks_dict = {}
    for t in rows:
        # Format scheduled_at
        if t["scheduled_at"] is None:
            formatted_date = "N/A"
        else:
            iso_str        = str(t["scheduled_at"]).replace("Z", "+00:00")
            dt_obj         = datetime.fromisoformat(iso_str)
            formatted_date = dt_obj.strftime("%#m/%#d/%Y, %#I:%M:%S %p")

        tasks_dict[str(t["uuid"])] = {
            "agent_id":       t["agent_id"],
            "task":           json.loads(t["task_json"]),
            "output":         t["output"],
            "executed_at":    t["executed_at"],
            "scheduled_at":   formatted_date,
            "recurring_every": t["recurring_every"] or "N/A",
            "status":         t["status"],
        }

    return jsonify(tasks_dict)


@tasks_bp.route("/task", methods=["POST"])
@require_token(role="admin")
def add_task():
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    data            = request.get_json()
    agent_id        = data.get("id")
    command         = data.get("task")
    scheduled_at    = data.get("scheduled_at")
    recurring_every = data.get("recurring_every") or "N/A"
    agent_group     = data.get("agent_group")
    task_uuid       = str(uuid.uuid4())

    db = get_db()

    if not agent_group:
        db.execute("""
            INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
            VALUES (?, ?, ?, NULL, ?, ?)
        """, (task_uuid, agent_id, json.dumps(command), scheduled_at, recurring_every))
        db.commit()

    if agent_group:
        agents_in_group = db.execute(
            "SELECT id FROM agents WHERE agent_group = ?", (agent_group,)
        ).fetchall()
        for row in agents_in_group:
            db.execute("""
                INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
                VALUES (?, ?, ?, NULL, ?, ?)
            """, (str(uuid.uuid4()), row[0], json.dumps(command), scheduled_at, recurring_every))
        db.commit()

    if not agent_id and agent_group is None:
        return jsonify({"status": "Error No Agent ID or GROUP set"}), 500

    if recurring_every and recurring_every != "N/A":
        thread = threading.Thread(
            target=recurring_scheduler,
            args=(task_uuid, recurring_every, agent_id, command),
            daemon=True
        )
        thread.start()

    # Audit log
    db.execute(
        "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), datetime.now(timezone.utc),
         "administrator", "Created a new task", "Info", task_uuid)
    )
    db.commit()

    return jsonify({"status": "accepted", "uuid": task_uuid})


@tasks_bp.route("/tasks/<task_uuid>", methods=["DELETE"])
@require_token(role="admin")
def delete_task(task_uuid):
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    db.execute("DELETE FROM tasks WHERE uuid = ?", (task_uuid,))
    db.commit()
    return jsonify({"status": "deleted"})