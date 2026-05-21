# 🛰️ Remote Agent Control Server

A **Flask-based command-and-control style server** designed for managing remote agents, dispatching tasks, collecting results, and monitoring system activity in real time.

> ⚠️ Intended strictly for **educational, research, and controlled automation environments only**

---

## ⚙️ Setup Instructions

This project requires additional configuration (database, environment variables, and mTLS setup).

➡️ Please follow the full setup guide in [SETUP.md](./SETUP.md)

---

# 🚀 Features

## 🔐 Secure Communication

* All agent communication is encrypted using **Fernet symmetric encryption**
* Acts as an additional obfuscation layer on top of HTTPS — even if an attacker
  manages to inspect TLS traffic through a misconfigured proxy or compromised
  intermediary, the payload remains opaque without the Fernet key
* Protects:

  * Beacon data
  * Tasking instructions
  * Execution results
* Sensitive operations require an **API key**
* All traffic is served over **HTTPS** — Nginx redirects any HTTP request to HTTPS automatically
* Agent-to-server communication is additionally secured with **Mutual TLS (mTLS)** — see the mTLS section below

---

## 🆙 Agent Updates

Agents can be updated automatically with periodic checks for new versions.

### How It Works

* Agents periodically check the `/api/agent_update` endpoint for available updates
* Update checks happen on a **configurable interval** (default: 2 hours)
* Server compares agent's current version against the available version
* If an update is available, agent downloads, verifies hash, and restarts with new version
* Server-side outages don't crash agents — they continue operating and retry later

### Update Flow

```
Agent (v1.0.0)                    Server
    │                                │
    ├─ POST /api/agent_update ─────>│
    │  (version: 1.0.0)             │
    │                               │
    │<─ {update: false} ────────────┤  (no update available)
    │                               │
    │ [continue beaconing]           │
    │                               │
    │ [2 hours later]                │
    │                               │
    ├─ POST /api/agent_update ─────>│
    │  (version: 1.0.0)             │
    │                               │
    │<─ {update: true,             ──┤  (update available!)
    │    download_url: "...",        │
    │    sha256: "abc123..."}        │
    │                               │
    ├─ GET /api/agent_update/agent.py─>│
    │                               │
    │<───── [binary file] ──────────┤
    │                               │
    ├─ Verify hash ✓                │
    │ Launch updater                │
    │ Restart with v1.0.1           │
```

### Update Security

* **Hash Verification** — SHA256 hash verified on client side before installation
* **Token Authentication** — Update endpoints require valid API token
* **Graceful Degradation** — Server outages don't crash agents; they continue operating
* **Automatic Retry** — Failed updates are retried on the next scheduled check interval


## 👤 Agent Management

* Create and manage agents directly from the dashboard
* Required fields:

  * Agent ID
  * Username
  * Password
  * AGENT_VERSION (current version of the agent)
* Optional:

  * **Agent Group**
* Agents are:

  * Stored in SQLite
  * Assigned a default role (`agent`)
  * Can be logically grouped using `agent_group`
  * **Automatically issued a unique mTLS certificate at creation time**
* Passwords are **hashed with bcrypt** before storage — plaintext credentials are never written to the database
* Enables structured and controlled onboarding

---

## 📄 Agent Configuration File

When an agent is created via the dashboard, the server automatically generates a configuration file containing the agent's credentials and group assignment.

### Config File Format

**Filename:** `Agent{agent_id}.conf`

**Example:** `Agent1.conf`


## 🔒 Mutual TLS (mTLS)

Mutual TLS extends standard HTTPS so that **both the server and the agent prove their identity** during the TLS handshake. An agent without a valid, CA-signed certificate cannot establish a connection at all — the request is rejected at the network layer before reaching Flask.

### How It Works

```
Agent                                    Nginx (Server)
  |                                           |
  |──── ClientHello ─────────────────────────►|
  |◄─── ServerHello + server.crt ────────────|
  |◄─── CertificateRequest ──────────────────|   ← mTLS step
  |──── agent-001.crt ───────────────────────►|   ← agent proves identity
  |──── CertificateVerify (signature) ───────►|   ← proves it owns the key
  |                                           |
  |       TLS session established             |
  |──── POST /beacon (encrypted) ────────────►|
  |                                           |
  |                               Nginx forwards to Flask
  |                               with headers:
  |                               X-Client-Cert-CN: agent-001
  |                               X-SSL-Verified: SUCCESS
```

Nginx handles all certificate verification. Flask receives only already-verified requests, with the agent's identity injected as a request header (`X-Client-Cert-CN`).

---

### Certificate Hierarchy (PKI)

```
Root CA  (ca.crt / ca.key)         ← lives on the server only
├── server.crt                     ← proves server identity to agents
├── agent-001.crt                  ← proves agent-001's identity to server
└── agent-002.crt                  ← each agent gets its own unique cert
```

* The CA **public** certificate (`ca.crt`) is distributed to agents so they can verify the server's identity during the TLS handshake
* The CA **private** key (`ca.key`) never leaves the server and is never needed by agents — it is only used server-side to sign new certificates
* All certificates trace back to this single root of trust

---

### Agent Certificate Generation (Automatic)

When an agent is created via the dashboard, the server **automatically generates a certificate** for that agent. No manual OpenSSL commands are needed.

The creation flow:

1. Admin fills in Agent ID, username, password, agent version, and group in the dashboard
2. Password is immediately hashed with bcrypt — plaintext is never stored
3. Server generates:
   * `agent{id}.key` — RSA 2048-bit private key
   * `agent{id}.csr` — Certificate Signing Request (deleted after signing)
   * `agent{id}.crt` — Certificate signed by the CA (stored in `./keys/`)
4. Config file `Agent{id}.conf` is created with all credentials
6. The agent file, config file, cert, and key are deployed together onto the agent machine
7. The full mTLS bundle (agent file + config file + cert + key + CA public cert) must be present on the agent machine for it to operate — possession of the agent file alone is not sufficient to connect

The CN (Common Name) in each agent certificate is set to the Agent ID. Nginx extracts this and forwards it to Flask as `X-Client-Cert-CN`, which is how the server identifies which agent is communicating.

---

### Certificate Storage Layout

```
keys/
├── ca.crt              ← CA public cert  (distributed to agents)
├── ca.key              ← CA private key  (server only, never shared)
├── ca.srl              ← Serial number tracking
├── server.crt          ← Server TLS certificate
├── server.key          ← Server private key
├── agent1.crt        ← Per-agent certificate (auto-generated at creation)
├── agent1.key        ← Per-agent private key
├── agent2.crt
├── agent2.key
└── ...
```

---

### Nginx Configuration

Nginx sits in front of Flask and handles all TLS. Flask only binds to `127.0.0.1:5000` (loopback) and is unreachable directly from the network.

```
Internet / Agents / Admins
         ↓
   [Nginx :443]   ← mTLS enforcement, cert verification, identity extraction
         ↓
   [Flask :5000]  ← receives only verified requests with identity in headers
```

Key Nginx directives:

```nginx
# Require client certificates signed by the CA
ssl_client_certificate /path/to/keys/ca.crt;
ssl_verify_client      required;

# Forward verified identity to Flask
proxy_set_header X-Client-Cert-CN   $ssl_client_s_dn_cn;
proxy_set_header X-SSL-Verified     $ssl_client_verify;
proxy_set_header X-Client-Cert-DN   $ssl_client_s_dn;

# Redirect all HTTP to HTTPS
server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

---

### Certificate Management



### Security Notes for mTLS

* **`ca.key` is the most critical secret** — it never leaves the server and agents have no need for it. Only the CA public cert (`ca.crt`) is distributed to agents for server verification.
* **Each agent has a unique key pair** — revoking one agent does not affect others.
* **The full mTLS bundle must be present on the agent machine** — the agent file, config file, cert, and key must accompany each other for any connection to succeed.
* **Config files contain sensitive paths** — protect with `chmod 600` and restrict distribution to intended machines
* **Flask binds to loopback only** (`127.0.0.1:5000`) — direct access bypasses Nginx and mTLS entirely. Never bind Flask to `0.0.0.0`.

---

## 🗄️ Database (SQLite)

* Lightweight, persistent storage
* Stores:

  * Agents
  * Tasks
  * Users
  * Scheduled & recurring task metadata

### Agents Table

The `agents` table includes:

* `id`
* `hostname`
* `user`
* `os`
* `ip`
* `last_seen`
* `agent_group`

This enables tasking and filtering based on logical groupings, as well as automatic update distribution.

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

### 👨‍💼 First-Time Admin Initialization

When the server is started for the very first time, it supports a secure bootstrap process to create the initial administrator account.

⚙️ Initialization Behavior
* If the users table contains no existing accounts:
* The application enables a one-time admin registration
* The first user created is automatically assigned the admin role
* Once an admin account exists:
* Open registration is disabled permanently
* Additional users must be created through the dashboard by an admin

### 🧑‍💻 Operator Dashboard Login

* Operators access the dashboard via a **username and password login page**
* Credentials are validated against the `users` table
* Passwords are stored as **bcrypt hashes** — plaintext is never written to the database
* On successful login a session is established granting access to the dashboard
* Admin accounts are created with passwords hashed at account creation time — only the hash is stored

### 🔒 Admin mTLS (Dashboard Certificate)

* In addition to login credentials, administrators are issued a **browser certificate** (`.p12` format)
* The certificate is imported once into the browser and presented automatically on every subsequent visit
* Provides an additional layer of identity verification at the TLS layer — the session cannot be established without a valid admin certificate signed by the server's CA

### 🤖 Agent Authentication

* mTLS certificate issued at agent creation — must be present on the agent machine alongside the agent file and config file
* Credentials (username and password) stored as bcrypt hash in both database and config file — never stored in plaintext
* Token-based session returned after successful credential validation
* Token used for all subsequent API calls within the session

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

* Identify Anomalies: Detect agents beaconing from unexpected IPs or outside expected intervals
* Health Audits: Summarize which agent groups are underperforming or facing high task failure rates
* Incident Summarization: Convert raw logs into high-level security briefings
* Contextual Queries: Answer natural language questions like "Which agents in the 'test' group are currently online?"

📥 Dual-Interface Access:

* Dedicated Analytics Page (`/chat`): A full-screen workspace for deep-dive investigations and historical data analysis
* Global Security Widget: A persistent, floating interface available on every dashboard page for real-time queries without leaving the current view

---

## 🖥️ Dashboard (`/dashboard`)

### ⚡ Task Creation

* Create and assign tasks to agents

### 🎯 Targeting Modes

Tasks can be dispatched using **one of two targeting methods**:

* **By Agent ID**
* **By Agent Group**

⚠️ **Mutual Exclusivity Rule**

* You must provide **either** `agent_id` **OR** `agent_group`
* Providing both is **not allowed**
* Providing neither is **not allowed**

---

### 📦 Supported Task Types

* `shell`
* `download`
* `upload`
* `sleep`
* `plugin`
* `revshell`

---

### 👥 Group-Based Tasking

* Tasks can be assigned to all agents within a specific `agent_group`
* Enables bulk operations, segmented tasking, and role-based execution patterns

```json
{
  "type": "shell",
  "command": "whoami",
  "agent_group": "red_team"
}
```

---

### 🔌 Reverse Shell Support

* Launch reverse shell tasks directly from dashboard
* Specify target agent ID and listening port

---

### ⏱️ Task Scheduling

* Schedule tasks for future execution with an exact execution time
* Compatible with both Agent ID and Agent Group targeting

---

### 🔁 Recurring Tasks

* Automate repeated execution at defined intervals (minutes, hourly, daily, custom)
* Fully compatible with group-based targeting

---

### ⚙️ Scheduling Behavior

* Tasks stored in database and executed when agents beacon after scheduled time
* Recurring tasks automatically re-queued
* Fully integrated with task dispatch system

---

## 📡 Task Lifecycle

### 1️⃣ Agent Creation

* Admin creates agent via dashboard with:
  * Agent ID
  * Username
  * Password
  * AGENT_VERSION
  * Optional: Agent Group
* Password hashed with bcrypt before storage — plaintext never persisted
* Server automatically generates:
  * mTLS certificate for the agent
  * Configuration file (`Agent{id}.conf`) containing credentials, version, and group
* Agent file (`Agent{id}.py`) written with cert and config paths embedded
* Agent optionally assigned an `agent_group`

All files deployed together: `Agent{id}.py`, `Agent{id}.conf`, cert, key, and CA public cert

### 3️⃣ Agent Login

* Agent reads `Agent{id}.conf` to load credentials 
* Agent presents mTLS certificate during TLS handshake (verified by Nginx)
* Agent sends username and password — server validates against bcrypt hash
* Server registers/updates agent record, stores version from config, and returns auth token

### 4️⃣ Beaconing (`/beacon`)

Agents periodically send encrypted data:

```json
{
  "id": "agent1",
  "hostname": "DESKTOP-123",
  "user": "john",
  "os": "Windows 10"
}
```

Server verifies mTLS certificate (Nginx layer), decrypts Fernet payload, updates last seen, marks agent online, and dispatches pending tasks.

### 6️⃣ Task Dispatching

* If `agent_id` is set → task sent to single agent
* If `agent_group` is set → task sent to all agents matching the group from their config files

```json
{ "type": "shell", "command": "whoami", "agent_id": "agent1" }
```

```json
{ "type": "shell", "command": "hostname", "agent_group": "blue_team" }
```

```json
{ "type": "shell", "command": "whoami", "execute_at": "2026-04-15T10:00:00", "agent_group": "ops" }
```

```json
{ "type": "shell", "command": "whoami", "recurring_at": "60min", "agent_group": "monitoring" }
```

### 7️⃣ Result Submission (`/result`)

* Agent presents mTLS certificate (Nginx verifies)
* Agent sends Fernet-encrypted results with task ID
* Server decrypts, stores output, and marks task completed

---

## 📦 Project Structure

```
TENET/
│
├── app.py                  # Entry point — creates app, registers blueprints
├── config.py               # All constants and environment variables
├── database.py             # DB connection management (get_db, close_db)
│
├── middleware/
│   ├── __init__.py
│   └── auth.py             # require_token, require_mtls decorators
│
├── routes/
│   ├── __init__.py
│   ├── auth.py             # /login, /logout
│   ├── agents.py           # /agents/, /agents/<id>, /agents-data, /agent-create
│   ├── beacon.py           # /beacon, /result
│   ├── tasks.py            # /task, /tasks/, /tasks-data, /tasks/<uuid>
│   ├── files.py            # /upload, /uploads/, /uploads/<filename>, /files-data
│   ├── plugins.py          # /plugins/, /plugins/<filename>, /plugins/run
│   ├── dashboard.py        # /dashboard, /info, /alerts, /get_alerts, chart endpoints
│   ├── ai.py               # /chat (FAQ), /ai/chat (Gemini), /chat page
│   ├─ revshell.py         # /revshell, /tools/<filename>
│   
│
├── services/
│   ├── __init__.py
│   ├── crypto.py           # encrypt_data, decrypt_data (Fernet helpers)
│   ├── scheduler.py        # recurring_scheduler, restart_recurring_tasks
│   ├── telegram.py         # send_telegram_logs
│   ├── geo.py              # get_location, get_online_offline_counts
│   ├── charts.py           # tasks_execution_timestamps, task_success_rate
│   ├── alerts.py           # gen_alerts
│   └── ai.py               # ask_ai, build_context
│
├── keys/
│   ├── ca.crt              # CA public certificate
│   ├── ca.key              # CA private key ⚠️ never share
│   ├── ca.srl              # Serial number tracking
│   ├── server.crt          # Server TLS certificate
│   ├── server.key          # Server private key
│   ├── agent1.crt        # Per-agent certificates (auto-generated at creation)
│   ├── agent1.key        # Per-agent private keys
│   
│
│
│
├── upload/                 # Uploaded files
├── plugins/                # Server-side plugins
├── tools/                  # Helper tools (Netcat, etc.)
├── templates/              # HTML templates
└── static/                 # CSS / JS assets
```

---

## 🛡️ Security Notes

* 🔒 Encrypted communication (Fernet) — obfuscates payload on top of TLS as an additional layer
* 🔑 API key protection for sensitive routes
* 🔒 mTLS enforced on all agent routes via Nginx
* 🔒 HTTP automatically redirected to HTTPS
* 🔒 All passwords (operators and agents) hashed with bcrypt — never stored in plaintext
* 🔒 Agent config files contain hashed passwords protect with `chmod 600`
* 🔒 Each agent holds a unique certificate — revoking one does not affect others
* 🔒 Admin dashboard requires both login credentials and a browser-imported certificate
* 🔒 CA public cert distributed to agents for server verification; CA private key stays server-side only
* 🔒 Agent update endpoints require token authentication and hash verification
* ⚠️ Flask must bind to `127.0.0.1` only — never `0.0.0.0`
* ⚠️ Config files must be secured and only distributed to intended agent machines
* ⚠️ Restrict plugin execution to trusted users
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
* Automatic certificate renewal before expiry
* Agent health monitoring and auto-remediation
* Differential updates (only changed files)
* Update rollback functionality