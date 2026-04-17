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
* Optional:

  * **Agent Group**
* Agents are:

  * Stored in SQLite
  * Assigned a default role (`agent`)
  * Can be logically grouped using `agent_group`
* Enables structured and controlled onboarding

---

## 🗄️ Database (SQLite)

* Lightweight, persistent storage
* Stores:

  * Agents
  * Tasks
  * Users
  * Scheduled & recurring task metadata

### 🆕 Agents Table Update

The `agents` table includes:

* `id`
* `hostname`
* `user`
* `os`
* `ip`
* `last_seen`
* `agent_group` ✅ *(NEW)*

This enables tasking and filtering based on logical groupings.

---

## 📡 Real-Time Agent Monitoring

Track all active agents with:

* Hostname
* Operating system
* Username
* IP address
* Last seen timestamp
* Agent group

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

## 🤖 AI Security Operations Analytics Assistant 

* AI-driven Analytics Assistant designed to act as a virtual SOC analyst. It parses complex database strings into actionable security intelligence.

🧠 Core Capabilities:

* The assistant acts as a Security Operations Analytics Assistant, interfacing directly with the SQLite database to:
* Identify Anomalies: Detect agents beaconing from unexpected IPs or outside expected intervals.
* Health Audits: Summarize which agent groups are underperforming or facing high task failure rates.
* Incident Summarization: Convert raw logs into high-level security briefings.
* Contextual Queries: Answer natural language questions like "Which agents in the 'test' group are currently online?"

📥 Dual-Interface Access:

* Dedicated Analytics Page (/chat): A full-screen workspace for deep-dive investigations and historical data analysis.
* Global Security Widget: A persistent, floating interface available on every dashboard page for real-time queries without leaving the current view.

---

## 🖥️ Dashboard Enhancements (`/dashboard`)

### ⚡ Task Creation

* Create and assign tasks to agents

### 🎯 Targeting Modes (NEW)

Tasks can now be dispatched using **one of two targeting methods**:

* **By Agent ID**
* **By Agent Group**

⚠️ **Mutual Exclusivity Rule**

* You must provide **either**:

  * `agent_id`
  * **OR** `agent_group`
* Providing both is **not allowed**
* Providing neither is **not allowed**

This ensures clear and predictable task routing.

---

### 📦 Supported Task Types

* `shell`
* `download`
* `upload`
* `sleep`
* `plugin`
* `revshell`

---

### 👥 Group-Based Tasking (NEW)

* Tasks can be assigned to all agents within a specific `agent_group`
* Enables:

  * Bulk operations
  * Segmented tasking
  * Role-based execution patterns

#### Example

```json
{
  "type": "shell",
  "command": "whoami",
  "agent_group": "red_team"
}
```

✔️ Automatically dispatched to **all agents** in that group upon beacon

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

Works with:

* Agent ID targeting
* ✅ Agent Group targeting *(NEW)*

---

### 🔁 Recurring Tasks

* Automate repeated execution
* Supported intervals:

  * Minutes
  * Hourly
  * Daily
  * Custom intervals

✔️ Fully compatible with **group-based targeting**

---

### ⚙️ Scheduling Behavior

* Tasks stored in database
* Executed when agents beacon after scheduled time
* Recurring tasks automatically re-queued
* Fully integrated with task dispatch system

---

## 📡 Task Lifecycle

### 1️⃣ Agent Creation

* Admin creates agent
* Optionally assigns `agent_group`

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
* Dispatches:

  * Pending tasks
  * Scheduled tasks
  * ✅ Group-based tasks *(NEW)*

---

### 4️⃣ Task Dispatching

Tasks are:

* Stored in database
* Delivered on beacon

### 🎯 Targeting Logic (UPDATED)

* If `agent_id` is set → task sent to single agent
* If `agent_group` is set → task sent to all matching agents

---

#### Example (Single Agent)

```json
{
  "type": "shell",
  "command": "whoami",
  "agent_id": "agent1"
}
```

---

#### Example (Group Task)

```json
{
  "type": "shell",
  "command": "hostname",
  "agent_group": "blue_team"
}
```

---

#### Scheduled Task

```json
{
  "type": "shell",
  "command": "whoami",
  "execute_at": "2026-04-15T10:00:00",
  "agent_group": "ops"
}
```

---

#### Recurring Task

```json
{
  "type": "shell",
  "command": "whoami",
  "interval": "1h",
  "agent_group": "monitoring"
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
* Advanced agent grouping (multi-group tagging)
* WebSocket real-time updates
* Retry/failure handling
* Docker deployment
