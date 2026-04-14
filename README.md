# 🛰️ Remote Agent Control Server

A **Flask-based command-and-control style server** designed for managing remote agents, dispatching tasks, collecting results, and monitoring system activity in real time.

> ⚠️ Intended strictly for **educational, research, and controlled automation environments only**

---

# 🚀 Features

## 🔐 Secure Communication

* All agent communication is encrypted using **Fernet symmetric encryption**
* Protects:

  * Beacon data
  * Tasking instructions
  * Execution results
* Prevents plaintext interception
* Sensitive operations require an **API key**

---

## 👤 Agent Management

* Create and manage agents directly from the dashboard
* Required fields:

  * Agent ID
  * Username
  * Password
* Agents are:

  * Stored in SQLite
  * Assigned a default role (`agent`)
* Enables structured and controlled onboarding

---

## 🗄️ Database (SQLite)

* Lightweight, persistent storage
* Stores:

  * Agents
  * Tasks
  * Users
  * Scheduled & recurring task metadata
* Survives server restarts
* Easily extendable schema

---

## 📡 Real-Time Agent Monitoring

Track all active agents with:

* Hostname
* Operating system
* Username
* IP address
* Last seen timestamp

### ✅ Automatic Tracking

* Online/offline detection
* Status updates via beaconing
* Activity visibility in real time

---

## 🚨 Alerts & Logging (`/alerts`)

Centralized logging and alerting system.

### 📄 Info Logs

* Task creation
* Agent creation
* Plugin execution

### ❗ Critical Logs

* Reverse shell creation events
* Low task execution rates
* Agents offline beyond threshold
* Multiple failed login attempts

### 📬 Telegram Integration

* Logs are sent daily to a **Telegram bot**
* Admins receive summaries of:

  * System activity
  * Security alerts
  * Agent health

---

## 📊 Analytics Dashboard (`/info`)

Visual insights into system performance.

### 🌍 Agent Map

* Displays IP-based geolocation of agents

### 📈 Task Execution Chart

* Bar chart showing number of executed tasks over time

### 🥧 Pie Charts

* Execution success rate per agent
* Online vs offline agent distribution

---

## 📁 File Management

* Upload files via dashboard
* Agents can:

  * Download files
  * Execute them
  * Store locally

---

## 🔑 Authentication System

### 🧑‍💻 Admin Access

* Username/password login
* Full access to:

  * Agents
  * Tasks
  * Files
  * Plugins
  * Logs & analytics

### 🤖 Agent Authentication

* Token-based system
* Issued upon login
* Used for secure communication

---

## 🧩 Plugin System

* Dynamically load Python modules
* Executed **in-memory on agents**
* No redeployment required

💡 Use cases:

* Extending functionality
* Rapid experimentation
* Modular operations

---

## 🖥️ Dashboard Enhancements (`/dashboard`)

### ⚡ Task Creation

* Create and assign tasks to agents
* Supported types:

  * `shell`
  * `download`
  * `upload`
  * `sleep`
  * `plugin`
  * `revshell`

---

### 🔌 Reverse Shell Support

* Launch reverse shell tasks directly from dashboard
* Specify:

  * Target agent ID
  * Listening port

---

### ⏱️ Task Scheduling

* Schedule tasks for future execution
* Define exact execution time
* Ideal for:

  * Delayed operations
  * Coordinated workflows
  * Off-peak execution

---

### 🔁 Recurring Tasks

* Automate repeated execution
* Supported intervals:

  * Minutes
  * Hourly
  * Daily
  * Custom intervals

### ⚙️ Scheduling Behavior

* Tasks stored in database
* Executed when agents beacon after scheduled time
* Recurring tasks automatically re-queued
* Fully integrated with task dispatch system

---

## 📡 Task Lifecycle

### 1️⃣ Agent Creation

* Admin creates agent
* Stored with credentials and role

---

### 2️⃣ Agent Login

* Agent sends credentials (JSON)
* Server:

  * Validates
  * Registers/updates agent
  * Returns auth token

---

### 3️⃣ Beaconing (`/beacon`)

Agents periodically send encrypted data:

```json
{
  "id": "agent1",
  "hostname": "DESKTOP-123",
  "user": "john",
  "os": "Windows 10"
}
```

Server:

* Decrypts payload
* Updates last seen
* Marks agent online
* Dispatches pending/scheduled tasks

---

### 4️⃣ Task Dispatching

Tasks are:

* Stored in database
* Delivered on beacon

#### Example Task

```json
{
  "type": "shell",
  "command": "whoami"
}
```

#### Scheduled Task

```json
{
  "type": "shell",
  "command": "whoami",
  "execute_at": "2026-04-15T10:00:00"
}
```

#### Recurring Task

```json
{
  "type": "shell",
  "command": "whoami",
  "interval": "1h"
}
```

---

### 5️⃣ Result Submission (`/result`)

* Agents send encrypted results
* Server:

  * Decrypts data
  * Stores output
  * Marks task completed

---

## 📦 Project Structure

```
project/
│
├── app.py              # Main Flask server
├── database.db         # SQLite database
├── upload/             # Uploaded files
├── plugins/            # Server-side plugins
├── tool/               # Helper tools & plugin resources
├── templates/          # HTML dashboard
└── static/             # CSS / JS assets
```

---

## 🔧 Running the Server

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set API key

```bash
export API_KEY="your_api_key_here"
```

### 3. Start server

```bash
python app.py
```

Server runs on:

```
http://0.0.0.0:5000
```

---

## 🛡️ Security Notes

* 🔒 Encrypted communication (Fernet)
* 🔑 API key protection for sensitive routes
* ⚠️ Passwords should be **hashed in production**
* ⚠️ Restrict plugin execution to trusted users
* ⚠️ Use HTTPS in real deployments
* ⚠️ Monitor reverse shell usage carefully
* ⚠️ Secure Telegram bot tokens properly

---

## 🔗 Dashboard Sections

* Live Agents
* Tasks
* Uploaded Files
* Plugins
* Create Agent
* Alerts & Logs (`/alerts`)
* Analytics (`/info`)

---

## 💡 Future Improvements

* Role-Based Access Control (RBAC)
* Agent grouping/tagging
* WebSocket real-time updates
* Retry/failure handling
* Docker deployment
