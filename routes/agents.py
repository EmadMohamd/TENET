import uuid
import subprocess
import bcrypt
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for

from config import CERT_DIR, AGENT_ONLINE_TIMEOUT, API_KEY
from database import get_db
from middleware.auth import require_token

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

    # ── Write agent file ──────────────────────────────────────────────────────
    with open("Agent.py", "r") as f_in, open(f"Agent{id_number}.py", "w") as f_out:
        lines     = f_in.readlines()
        lines[24] = f'username = "{username}"\n'
        lines[25] = f'password = "{password}"\n'
        lines[30] = f'AGENT_ID = "{id_number}"\n'
        lines[31] = f'AGENT_GROUP = "{agent_group}"\n'
        f_out.writelines(lines)

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