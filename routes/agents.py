import uuid
import subprocess
import bcrypt
from datetime import datetime, timezone
import os
import hashlib

from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, send_file

from config import CERT_DIR, AGENT_ONLINE_TIMEOUT, API_KEY , FERNET_KEY
from database import get_db
from middleware.auth import require_token
from services.crypto import decrypt_data
from services.stager_token import generate

agents_bp = Blueprint("agents", __name__)


# ── Agent list page ───────────────────────────────────────────────────────────

@agents_bp.route("/agents/")
@require_token(role="admin")
def agents_list():
    if "username" not in session:
        return redirect(url_for("auth.login"))
    return render_template("agents.html")


# ── Agent detail page ─────────────────────────────────────────────────────────

@agents_bp.route("/agents/<agent_id>")
@require_token(role="admin")
def agent_detail(agent_id):
    if "username" not in session:
        return redirect(url_for("auth.login"))

    db    = get_db()
    tasks = db.execute("""
        SELECT uuid, task_json, output
        FROM tasks WHERE agent_id = ?
        ORDER BY rowid DESC
    """, (agent_id,)).fetchall()

    import json
    task_rows = [
        {"uuid": t["uuid"], "task": json.loads(t["task_json"]), "output": t["output"]}
        for t in tasks
    ]
    return render_template("agent_detail.html", agent_id=agent_id, tasks=task_rows)


# ── Agents data API ───────────────────────────────────────────────────────────

@agents_bp.route("/agents-data")
@require_token(role="admin")
def agents_data():
    now = datetime.now(timezone.utc)
    db  = get_db()

    data = []
    for row in db.execute("SELECT * FROM agents").fetchall():
        last_seen = datetime.fromisoformat(row["last_seen"])
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        online        = (now - last_seen).total_seconds() <= AGENT_ONLINE_TIMEOUT
        pending_tasks = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE agent_id = ? AND status = 'pending'",
            (row["id"],)
        ).fetchone()[0]

        data.append({
            "id":            row["id"],
            "hostname":      row["hostname"],
            "user":          row["user"],
            "os":            row["os"],
            "ip":            row["ip"],
            "last_seen":     last_seen.timestamp(),
            "online":        online,
            "pending_tasks": pending_tasks,
        })

    return jsonify(data)


# ── Agent creation ────────────────────────────────────────────────────────────

@agents_bp.route("/agent-create", methods=["POST"])
@require_token(role="admin")
def agent_create():
    username    = request.json.get("username")
    password    = request.json.get("password")
    id_number   = request.json.get("id")
    agent_group = request.json.get("group")

    db = get_db()

    if db.execute("SELECT 1 FROM USERS WHERE username = ?", (username,)).fetchone():
        return {"error": "Username already exists"}, 400
    if db.execute("SELECT 1 FROM AGENTS WHERE ID = ?", (id_number,)).fetchone():
        return {"error": "AgentID already exists"}, 400

    task_uuid = str(uuid.uuid4())
    hashed    = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    db.execute(
        "INSERT INTO USERS (username, password, role) VALUES (?, ?, ?)",
        (username, hashed, "agent")
    )
    db.commit()

    # ── Write agent python file ──────────────────────────────────────────────────────
    with open("Agent.py", "r") as f_in, open(f"Agent{id_number}.py", "w") as f_out:
        lines = f_in.readlines()
        f_out.writelines(lines)

    # ── Write agent conf file ──────────────────────────────────────────────────────
    file_name = f"Agent{id_number}.conf"

    # Open the file in 'w' (write) mode, which creates it if it doesn't exist
    with open(file_name, "w") as file:
        file.write(f"username = \"{username}\"\n")
        file.write(f"password = \"{password}\"\n")
        file.write(f"AGENT_ID = \"{id_number}\"\n")
        file.write(f"AGENT_GROUP = \"{agent_group}\"\n")
        file.write(f"FERNET_KEY = \"{FERNET_KEY}\"\n")
    # ── Generate mTLS certificate ─────────────────────────────────────────────
    key = CERT_DIR / f"agent{id_number}.key"
    csr = CERT_DIR / f"agent{id_number}.csr"
    crt = CERT_DIR / f"agent{id_number}.crt"

    subprocess.run([
        "openssl", "genpkey",
        "-algorithm", "RSA",
        "-pkeyopt", "rsa_keygen_bits:2048",
        "-out", str(key)
    ], check=True)

    subprocess.run([
        "openssl", "req", "-new",
        "-key", str(key),
        "-out", str(csr),
        "-subj", f"/C=US/ST=CA/O=TENET/CN={id_number}",
        "-addext", f"subjectAltName=DNS:{id_number}"
    ], check=True)

    subprocess.run([
        "openssl", "x509", "-req",
        "-in",  str(csr),
        "-CA",  str(CERT_DIR / "ca.crt"),
        "-CAkey", str(CERT_DIR / "ca.key"),
        "-CAcreateserial",
        "-out", str(crt),
        "-days", "365",
        "-sha256"
    ], check=True)

    # ── Audit log ─────────────────────────────────────────────────────────────
    db.execute(
        "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), datetime.now(timezone.utc),
         "administrator", f"Created a new agent: {id_number}", "Info", task_uuid)
    )
    db.commit()

    return {"status": "created"}, 200

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Parent directory where agent_1.0.3.py is stored
AGENT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

AVAILABLE_AGENT = {
    "version": "1.0.3",
    "filename": "Agent.py"
}

def calculate_sha256(file_path):
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()




@agents_bp.route("/agent_update", methods=["POST"])
def agent_update_endpoint():
    data = request.get_json()
    agent_version = data.get("version")
    agent_id = data.get("id")

    if not agent_version or not agent_id:
        return jsonify({"error": "Missing version or id"}), 400

    # Compare versions
    if agent_version == AVAILABLE_AGENT["version"]:
        return jsonify({"update": False})

    # Construct download URL
    download_file_path = os.path.join(AGENT_DIR, AVAILABLE_AGENT["filename"])
    if not os.path.exists(download_file_path):
        return jsonify({"error": "Update file not found"}), 500

    # Calculate SHA256
    file_hash = calculate_sha256(download_file_path)

    return jsonify({
        "update": True,
        "download_url": f"/agent_update/{AVAILABLE_AGENT['filename']}",  # another endpoint for downloading
        "sha256": file_hash
    })


# Optional: endpoint to serve the actual file
@agents_bp.route("/agent_update/<filename>", methods=["GET"])
def download_agent(filename):
    file_path = os.path.join(AGENT_DIR, filename)
    print(file_path)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True)


@agents_bp.route("/admin/generate-stager", methods=["POST"])
@require_token(role="admin")
def generate_stager_command():
    """
    Generate stager command for deployment.
    Operators use this to get the stager command.
    """
    if "username" not in session:
        return redirect(url_for("auth.login"))

    agent_id = request.json.get("agent_id")

    try:
        # Generate token (valid for 1 hour)
        token = generate(agent_id, valid_for_minutes=60)

        # Build command for operator
        stager_command = f"python stager.py {token}"

        return jsonify({
            "status": "ok",
            "agent_id": agent_id,
            "token": token,
            "stager_command": stager_command,
            "instructions": [
                "1. Download stager.py",
                "2. Copy stager.py to target",
                "3. Run the command below:",
                f"   {stager_command}",
                "4. Agent will download and execute"
            ]
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500