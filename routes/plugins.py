import json
import uuid
import os
from datetime import datetime, timezone

from flask import (Blueprint, request, redirect, url_for,
                   render_template, session, send_from_directory)

from config import PLUGINS_DIR, IP
from database import get_db
from middleware.auth import require_token

plugins_bp = Blueprint("plugins", __name__)


@plugins_bp.route("/plugins/")
@require_token(role="admin")
def plugins_list():
    if "username" not in session:
        return redirect(url_for("auth.login"))
    plugins = [f for f in os.listdir(PLUGINS_DIR) if f.endswith(".py")]
    return render_template("plugins.html", plugins=plugins)


@plugins_bp.route("/plugins/<filename>")
@require_token(role="admin")
def serve_plugin(filename):
    if not filename.endswith(".py"):
        return "Invalid file", 400
    return send_from_directory(PLUGINS_DIR, filename)


@plugins_bp.route("/plugins/run", methods=["POST"])
def run_plugin():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    agent_id    = request.form.get("agent_id")
    plugin_name = request.form.get("plugin_name")
    if not agent_id or not plugin_name:
        return "Missing parameters", 400

    plugin_url = f"https://{IP}/plugins/{plugin_name}"
    task_uuid  = str(uuid.uuid4())
    db         = get_db()
    current_time = datetime.now(timezone.utc)

    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at)
        VALUES (?, ?, ?, NULL, ?)
    """, (task_uuid, agent_id, json.dumps({"type": "download", "url": plugin_url}), current_time))

    db.execute(
        "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), current_time, "administrator",
         f"Executed plugin: {plugin_name}", "Info", task_uuid)
    )
    db.commit()

    return redirect(url_for("plugins.plugins_list"))