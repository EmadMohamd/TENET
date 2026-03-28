# 🛰️ Remote Agent Control Server

A **Flask-based command-and-control style server** for managing remote agents, dispatching tasks, receiving results, and monitoring agent status in real time.

> ⚠️ Intended for **educational, research, and controlled automation environments only**.

---

# 🚀 Features

## 🔐 Encrypted Communication

* Agents communicate using **Fernet symmetric encryption**
* Secure transmission of:

  * Beacons
  * Task results
* Prevents plaintext interception
* **API key required** for privileged operations

---

## 👤 Agent Creation & Management

* Create agents directly from the dashboard
* Required fields:

  * Agent ID
  * Username
  * Password
* Agents are:

  * Stored in SQLite
  * Assigned a default role (`agent`)
* Enables controlled onboarding of new clients

---

## 🗄️ SQLite Database Integration

* Persistent storage for:

  * Agents
  * Tasks
  * Users
* Lightweight and easy to manage
* Survives server restarts
* Simple schema, easy to extend

---

## 📡 Live Agent Monitoring

Track all connected agents in real time:

* Hostname
* Operating system
* Username
* IP address
* Last seen timestamp

✅ Automatic:

* Online/offline detection
* Status updates via beaconing

---

## 📁 File Upload Support

* Upload files directly from dashboard
* Agents can:

  * Download files
  * Execute or store them locally

---

## 🔑 Dual Authentication System

### 🧑‍💻 Admin Dashboard

* Username/password login
* Full control over:

  * Agents
  * Tasks
  * Files
  * Plugins

### 🤖 Agent Authentication

* Token-based authentication
* Issued upon successful login
* Used for secure communication

---

## 🧩 Plugin System

* Dynamically load Python modules
* Executed **in-memory on agents**
* No redeployment required

💡 Ideal for:

* Extending functionality
* Rapid testing
* Modular operations

---

# 📦 Project Structure

```
project/
│
├── app.py              # Main Flask server
├── database.db        # SQLite database
├── upload/            # Uploaded files
├── plugins/           # Server-side plugins
├── templates/         # HTML dashboard
└── static/            # CSS / JS assets
```

---

# ⚙️ How It Works

## 1️⃣ Agent Creation

* Admin creates an agent via dashboard
* Stored in database with:

  * ID
  * Credentials
  * Default role (`agent`)

---

## 2️⃣ Agent Login

* Agent sends JSON credentials
* Server:

  * Validates credentials
  * Registers/updates agent
  * Returns authentication token

---

## 3️⃣ Beaconing

* Agents periodically POST encrypted data to `/beacon`

Server actions:

* Decrypt payload
* Update `last_seen`
* Mark agent as online
* Return pending task (if any)

---

## 4️⃣ Task Dispatching

* Tasks stored in SQLite
* Delivered when agent beacons

### Supported task types:

* `shell` → execute command
* `download` → fetch file
* `upload` → send file to server
* `sleep` → adjust beacon interval
* `plugin` → execute module

---

## 5️⃣ Result Submission

* Agents POST encrypted results to `/result`
* Server:

  * Decrypts data
  * Stores output in database
  * Marks task as completed

---

## 6️⃣ Admin Dashboard

Admins can:

* 👀 View live agents
* 📋 Manage tasks
* 📁 Upload/download files
* 🧩 Execute plugins
* ➕ Create new agents
* 📡 Monitor activity in real time

---

# 🧪 Example Payloads

## 📡 Agent Beacon

```json
{
  "id": "agent1",
  "hostname": "DESKTOP-123",
  "user": "john",
  "os": "Windows 10"
}
```

---

## 📬 Task Example

```json
{
  "type": "shell",
  "command": "whoami"
}
```

---

## 🧩 Plugin Task

```json
{
  "type": "download",
  "url": "http://server:5000/plugins/test_plugin.py"
}
```

---

# 🔧 Running the Server

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

## 2. Set environment variable

```bash
export API_KEY="your_api_key_here"
```

## 3. Start server

```bash
python app.py
```

Server runs on:

```
http://0.0.0.0:5000
```

---

# 🛡️ Security Notes

* 🔒 All agent communication is encrypted (Fernet)
* 🔑 API key required for sensitive actions
* ⚠️ Passwords should be **hashed in production**
* ⚠️ Restrict plugin execution to trusted users
* ⚠️ Use HTTPS in real deployments

---

# 🔗 Dashboard Sections

* **Live Agents**
* **Tasks**
* **Uploaded Files**
* **Plugins**
* **Create Agent**

---

# 💡 Future Improvements (Optional Ideas)

* Role-based access control (RBAC)
* Agent grouping/tagging
* WebSocket live updates (instead of polling)
* Audit logs for actions
* Payload builder for agents
* Docker deployment

---
