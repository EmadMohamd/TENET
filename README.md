# 🛰️ Remote Agent Control Server  
A Flask‑based command‑and‑control style server for managing remote agents, dispatching tasks, receiving results, and monitoring agent status.  
This project is intended for **educational**, **research**, and **automation** scenarios where a central server coordinates lightweight remote clients.

---

## 🚀 Features

### 🔐 Encrypted Communication
- Agents send **encrypted JSON payloads** using Fernet symmetric encryption.
- Server decrypts beacons and results securely.
- **API key** required for creating tasks.

### 🗄️ SQLite Database Integration
- Persistent storage for:
  - Agents
  - Tasks
  - Users
- Survives server restarts.
- Simple schema, easy to extend.

### 📡 Live Agent Monitoring
- Tracks:
  - Hostname
  - OS
  - Username
  - IP address
  - Last seen timestamp
- Online/offline detection with configurable timeout.

### 📁 File Upload Support
- Upload files to the server.
- Agents can download them when needed.

### 🔑 Dual Login System
- **Dashboard login** for administrators.
- **Agent login** for remote clients (token-based).

### 🧩 Plugin Support
- Dynamically load Python modules on agents.
- Agents execute plugins in-memory when received from the server.
- Ideal for extending functionality without redeploying agents.

---

## 📦 Project Structure


project/
│
├── app.py # Main Flask server
├── database.db # SQLite database
├── upload/ # Uploaded files
├── plugins/ # Server-side plugin directory
├── templates/ # HTML templates for dashboard
└── static/ # CSS/JS assets


---

## ⚙️ How It Works

### 1️⃣ Agent Login
- Agents authenticate using JSON credentials.
- On success, the server:
  - Registers the agent
  - Issues a session token
  - Stores metadata in SQLite

### 2️⃣ Beaconing
- Agents periodically POST encrypted JSON to `/beacon`.
- The server:
  - Updates `last_seen`
  - Returns the next pending task (if any)

### 3️⃣ Task Execution
- Tasks are stored in SQLite and delivered to agents when they beacon.
- Types include: `shell`, `download`, `upload`, `sleep`, and plugin execution.

### 4️⃣ Result Submission
- Agents POST encrypted results to `/result`.
- Server updates the task entry with the output.

### 5️⃣ Dashboard
Admins can:
- View live agents
- View all tasks
- Upload files
- Launch plugins
- Monitor online/offline status

---

## 🔧 Running the Server

1. **Install dependencies**

```bash
pip install -r requirements.txt
Set environment variables
export API_KEY="your_api_key_here"
Start the server
python app.py
Server runs on: http://0.0.0.0:5000
🧪 Example Agent Beacon Payload

Encrypted JSON (after decryption):

{
  "id": "agent1",
  "hostname": "DESKTOP-123",
  "user": "john",
  "os": "Windows 10"
}
📬 Task Format

Tasks are simple JSON objects:

{
  "type": "shell",
  "command": "whoami"
}

For plugins:

{
  "type": "download",
  "url": "http://server:5000/plugins/test_plugin.py"
}
🛡️ Security Notes
All agent communication is encrypted using Fernet.
API key required for task creation.
Consider hashing dashboard passwords in production.
Limit plugin access to trusted operators only.
🔗 Links
Dashboard
Live Agents
Tasks
Uploaded Files
Plugins Directory




