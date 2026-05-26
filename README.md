# 🛰️TENET: Remote Agent Control Server

A **Flask-based command-and-control style server** for managing remote agents, dispatching tasks, collecting results, and monitoring activity in real time.

> ⚠️ Intended strictly for **educational, research, and controlled automation environments only**

---

# 📚 Table of Contents

* [Overview](#-overview)
* [Setup](#️-setup)
* [Core Features](#-core-features)
* [Security Architecture](#-security-architecture)
* [Authentication & Access Control](#-authentication--access-control)
* [Agent Lifecycle](#-agent-lifecycle)
* [Tasking System](#-tasking-system)
* [Monitoring & Analytics](#-monitoring--analytics)
* [Plugin System](#-plugin-system)
* [AI Security Operations Assistant](#-ai-security-operations-analytics-assistant)
* [Database](#️-database-sqlite)
* [Project Structure](#-project-structure)
* [Security Notes](#️-security-notes)
* [Dashboard Sections](#-dashboard-sections)
* [Future Improvements](#-future-improvements)
* [Suggested Enhancements](#-suggested-enhancements)

---

# 🔍 Overview

The platform provides:

* Secure remote agent communication
* Real-time monitoring and analytics
* Task scheduling and recurring execution
* Group-based agent management
* Automatic agent updates
* Plugin-based extensibility
* AI-assisted security analytics
* mTLS-based authentication and identity verification

---

# ⚙️ Setup

This project requires additional configuration:

* Database initialization
* Environment variables
* HTTPS + Nginx configuration
* mTLS certificate setup

➡️ Follow the full setup guide in `SETUP.md`

---

# 🚀 Core Features

## 🔐 Secure Communication

All agent communication is encrypted using **Fernet symmetric encryption**.

This acts as an additional obfuscation layer on top of HTTPS. Even if TLS traffic is inspected through a compromised intermediary or misconfigured proxy, the payload remains unreadable without the Fernet key.

### Protected Data

* Beacon data
* Task instructions
* Execution results

### Additional Security Layers

* HTTPS enforced through Nginx
* Automatic HTTP → HTTPS redirection
* API key protection for sensitive routes
* Mutual TLS (mTLS) for agent-server communication

---

## 👤 Agent Management

Create and manage agents directly from the dashboard.

### Required Fields

* Agent ID
* Username
* Password
* `AGENT_VERSION`

### Optional Fields

* `agent_group`

### Agent Capabilities

Agents are:

* Stored in SQLite
* Assigned a default role (`agent`)
* Logically grouped using `agent_group`
* Automatically issued a unique mTLS certificate during creation

### Password Security

Passwords are:

* Hashed with bcrypt before storage
* Never stored in plaintext
* Never written unencrypted to the database

---

## 📄 Agent Configuration Files

When an agent is created, the server automatically generates a configuration file containing:

* Credentials
* Group assignment
* Version information
* Certificate paths

### Naming Convention

```text
Agent{agent_id}.conf
```

Example:

```text
Agent1.conf
```

---

## 🆙 Automatic Agent Updates

Agents can automatically update themselves through periodic version checks.

### Update Flow

```text
Agent (v1.0.0)                    Server

    │                               │
    ├─ POST /api/agent_update ─────>│
    │  (version: 1.0.0)             │
    │                               │
    │<─ {update: false} ────────────┤
    │                               │
    │ [continue beaconing]          │
    │                               │
    │ [2 hours later]               │
    │                               │
    ├─ POST /api/agent_update ─────>│
    │  (version: 1.0.0)             │
    │                               │
    │<─ {update: true,             ─┤
    │    download_url: "...",       │
    │    sha256: "abc123..."}       │
    │                               │
    ├─ GET /api/agent_update/... ──>│
    │                               │
    │<────── [binary file] ─────────┤
    │                               │
    ├─ Verify hash ✓                │
    │ Launch updater                │
    │ Restart with v1.0.1           │
```

### Update Features

* Configurable update interval (default: 2 hours)
* SHA256 verification before installation
* Token-authenticated update endpoints
* Graceful handling of server outages
* Automatic retry on failed updates

---

# 🔒 Security Architecture

## 🔒 Mutual TLS (mTLS)

Mutual TLS ensures that both the server and the agent authenticate each other during the TLS handshake.

Agents without valid CA-signed certificates are rejected before requests ever reach Flask.

---

## 🧱 mTLS Handshake Flow

```text
Agent                                    Nginx (Server)

  |                                           |
  |──── ClientHello ─────────────────────────►|
  |◄─── ServerHello + server.crt ────────────|
  |◄─── CertificateRequest ──────────────────| ← mTLS
  |──── agent-001.crt ───────────────────────►|
  |──── CertificateVerify ───────────────────►|
  |                                           |
  |       TLS session established             |
  |──── POST /beacon ────────────────────────►|
  |                                           |
  |                         Nginx forwards verified
  |                         requests to Flask with:
  |
  |                         X-Client-Cert-CN
  |                         X-SSL-Verified
```

Nginx performs certificate verification and forwards verified identity headers to Flask.

---

## 🏗️ Certificate Hierarchy (PKI)

```text
Root CA (ca.crt / ca.key)
├── server.crt
├── agent-001.crt
└── agent-002.crt
```

### PKI Notes

* `ca.crt` is distributed to agents
* `ca.key` never leaves the server
* Each agent receives a unique certificate
* All trust chains originate from the Root CA

---

## ⚙️ Automatic Certificate Generation

When an agent is created:

1. Admin enters agent details in dashboard
2. Password is bcrypt-hashed immediately
3. Server generates:

   * `agent{id}.key`
   * `agent{id}.csr`
   * `agent{id}.crt`
4. Configuration file is generated
5. Agent package is deployed

### Deployment Bundle

Each agent requires:

* Agent executable/script
* Config file
* Agent certificate
* Agent private key
* CA public certificate

Possession of the agent file alone is insufficient for authentication.

---

## 📂 Certificate Storage Layout

```text
keys/

├── ca.crt
├── ca.key
├── ca.srl
├── server.crt
├── server.key
├── agent1.crt
├── agent1.key
├── agent2.crt
├── agent2.key
└── ...
```

---

## 🌐 Nginx TLS Architecture

```text
Internet / Agents / Admins
           ↓
     [ Nginx :443 ]
           ↓
     [ Flask :5000 ]
```

### Responsibilities

#### Nginx

* HTTPS termination
* mTLS enforcement
* Certificate validation
* Identity extraction
* HTTP → HTTPS redirect

#### Flask

* Application logic
* Receives verified requests only
* Bound to loopback (`127.0.0.1`) only

### Example Nginx Configuration

```nginx
ssl_client_certificate /path/to/keys/ca.crt;
ssl_verify_client required;

proxy_set_header X-Client-Cert-CN $ssl_client_s_dn_cn;
proxy_set_header X-SSL-Verified $ssl_client_verify;
proxy_set_header X-Client-Cert-DN $ssl_client_s_dn;

server {
    listen 80;
    return 301 https://$host$request_uri;
}
```

---

# 🔑 Authentication & Access Control

## 👨‍💼 Initial Admin Bootstrap

On first startup:

* If no admins exist:

  * One-time admin registration is enabled
  * First account becomes administrator

* After first admin creation:

  * Public registration is permanently disabled
  * Only admins can create additional users/admins

---

## 🧑‍💻 Dashboard Authentication

Operators authenticate using:

* Username/password login
* bcrypt password validation
* Session-based authentication

Passwords are never stored in plaintext.

---

## 🔒 Admin mTLS Certificates

Administrators are also issued browser certificates (`.p12`).

### Benefits

* TLS-layer identity verification
* Browser automatically presents cert
* Dashboard access requires:

  * Valid login credentials
  * Valid admin certificate

---

## 🤖 Agent Authentication

Agents authenticate using:

* mTLS certificates
* Username/password validation
* Token-based authenticated sessions

### Authentication Flow

1. Agent presents certificate
2. Nginx validates mTLS
3. Agent sends credentials
4. Server validates bcrypt hash
5. Auth token issued
6. Token used for subsequent API requests

---

# 📡 Agent Lifecycle

## 1️⃣ Agent Creation

Admin creates agent with:

* Agent ID
* Username
* Password
* Agent version
* Optional group

### Server Actions

* Hash password with bcrypt
* Generate mTLS certificates
* Generate config file
* Embed paths into agent file
* Store metadata in database

### Deployment Files

```text
Agent{id}.py
Agent{id}.conf
agent{id}.crt
agent{id}.key
ca.crt
```

---

## 2️⃣ Agent Login

Agent:

* Loads credentials from config
* Performs mTLS handshake
* Authenticates with credentials
* Receives auth token

Server:

* Registers/updates metadata
* Stores version info
* Tracks agent status

---

## 3️⃣ Beaconing (`/beacon`)

Agents periodically send encrypted metadata.

Example:

```json
{
  "id": "agent1",
  "hostname": "DESKTOP-123",
  "user": "john",
  "os": "Windows 10"
}
```

Server:

* Verifies mTLS identity
* Decrypts Fernet payload
* Updates `last_seen`
* Marks agent online
* Dispatches queued tasks

---

## 4️⃣ Result Submission (`/result`)

Agents submit encrypted task results.

Server:

* Verifies certificate
* Decrypts payload
* Stores results
* Marks task complete

---

# 🖥️ Tasking System

## ⚡ Task Creation

Tasks can target:

* A specific `agent_id`
* An `agent_group`

### Mutual Exclusivity Rule

You must provide:

* `agent_id` **OR**
* `agent_group`

Not both.

---

## 📦 Supported Task Types

* `shell`
* `download`
* `upload`
* `sleep`
* `plugin`
* `revshell`

---

## 👥 Group-Based Tasking

Tasks may target all agents in a group.

Example:

```json
{
  "type": "shell",
  "command": "whoami",
  "agent_group": "red_team"
}
```

---

## 🔌 Reverse Shell Support

* Launch reverse shell tasks from dashboard
* Specify:

  * Target agent
  * Listening port

---

## ⏱️ Scheduled Tasks

Execute tasks at a future time.

Example:

```json
{
  "type": "shell",
  "command": "whoami",
  "execute_at": "2026-04-15T10:00:00",
  "agent_group": "ops"
}
```

---

## 🔁 Recurring Tasks

Automate repeated execution.

Example:

```json
{
  "type": "shell",
  "command": "whoami",
  "recurring_at": "60min",
  "agent_group": "monitoring"
}
```

### Scheduling Behavior

* Stored in database
* Triggered on beacon
* Automatically re-queued

---

# 📡 Monitoring & Analytics

## 📡 Real-Time Agent Monitoring

Track:

* Hostname
* OS
* Username
* IP address
* Last seen
* Agent group

### Monitoring Features

* Online/offline detection
* Real-time status updates
* Beacon-based health visibility

---

## 🚨 Alerts & Logging (`/alerts`)

Centralized logging system.

### Info Logs

* Task creation
* Agent creation
* Plugin execution

### Critical Alerts

* Reverse shell creation
* Low task execution rates
* Offline agents
* Failed login attempts

---

## 📬 Telegram Integration

Daily summaries sent to Telegram bot.

### Included Data

* Security alerts
* Agent health
* System activity

---

## 📊 Analytics Dashboard (`/info`)

### 🌍 Agent Geolocation Map

Displays IP-based agent geolocation.

### 📈 Task Charts

* Task execution frequency
* Success/failure distribution

### 🥧 Pie Charts

* Online vs offline distribution
* Success rate per agent

---

# 📁 File Management

Operators can upload files through the dashboard.

Agents can:

* Download files
* Execute files
* Store files locally

---

# 🧩 Plugin System

Supports dynamically loaded Python modules.

### Features

* In-memory execution on agents
* No redeployment required
* Modular architecture

### Use Cases

* Rapid experimentation
* Feature extensions
* Operational tooling

---

# 🤖 AI Security Operations Analytics Assistant

AI-powered analytics assistant acting as a virtual SOC analyst.

## 🧠 Capabilities

### Identify Anomalies

* Unexpected IP beaconing
* Irregular beacon intervals

### Health Audits

* Underperforming groups
* High task failure rates

### Incident Summaries

* Convert raw logs into high-level reports

### Contextual Queries

Example:

> "Which agents in the `test` group are online?"

---

## 📥 Access Interfaces

### Dedicated Analytics Workspace (`/chat`)

Full-screen investigation interface.

### Global Security Widget

Persistent dashboard assistant for quick analysis.

---

# 🗄️ Database (SQLite)

SQLite provides lightweight persistent storage.

## Stores

* Agents
* Tasks
* Users
* Scheduled task metadata
* Recurring task metadata

---

## Agents Table

Includes:

* `id`
* `hostname`
* `user`
* `os`
* `ip`
* `last_seen`
* `agent_group`

---

# 📦 Project Structure

```text
TENET/

├── app.py
├── config.py
├── database.py
│
├── middleware/
│   ├── __init__.py
│   └── auth.py
│
├── routes/
│   ├── auth.py
│   ├── agents.py
│   ├── beacon.py
│   ├── tasks.py
│   ├── files.py
│   ├── plugins.py
│   ├── dashboard.py
│   ├── ai.py
│   └── revshell.py
│
├── services/
│   ├── crypto.py
│   ├── scheduler.py
│   ├── telegram.py
│   ├── geo.py
│   ├── charts.py
│   ├── alerts.py
│   └── ai.py
│
├── keys/
│   ├── ca.crt
│   ├── ca.key
│   ├── server.crt
│   ├── server.key
│   ├── agent1.crt
│   └── agent1.key
│
├── upload/
├── plugins/
├── tools/
├── templates/
└── static/
```

---

# 🛡️ Security Notes

* Fernet encryption layered on top of TLS
* API key protection for sensitive routes
* mTLS enforced through Nginx
* Automatic HTTP → HTTPS redirect
* bcrypt password hashing
* Unique certificate per agent
* Admin dashboard protected with browser certificates
* Token-authenticated update endpoints
* SHA256 verification for updates
* Flask bound to `127.0.0.1` only
* CA private key never distributed
* Agent configs should use `chmod 600`
* Restrict plugin execution to trusted operators
* Monitor reverse shell usage carefully
* Secure Telegram bot tokens

---

# 🔗 Dashboard Sections

* Live Agents
* Tasks
* Uploaded Files
* Plugins
* Create Agent
* Alerts & Logs (`/alerts`)
* Analytics (`/info`)

---

# 🚧 Future Improvements

* Role-Based Access Control (RBAC)
* Advanced multi-group tagging
* WebSocket real-time updates
* Retry/failure handling
* Docker deployment
* Automatic certificate renewal
* Agent health auto-remediation
* Differential updates
* Update rollback support

---

# 💡 Suggested Enhancements

Here are additional improvements worth considering:

## 🔐 Security Enhancements

* Certificate Revocation List (CRL) support
* OCSP validation
* Per-agent API scopes/permissions
* Hardware-backed key storage (TPM/YubiKey)
* Signed plugin verification
* Audit trail immutability

---

## 📈 Scalability Improvements

* PostgreSQL support
* Redis-backed task queue
* Horizontal worker scaling
* Multi-server agent routing
* WebSocket/SSE live dashboards

---

## 🤖 Agent Improvements

* Agent self-healing/recovery
* Agent integrity verification
* Offline task caching
* Adaptive beacon intervals
* Bandwidth-aware update delivery

---

## 🧠 AI / Analytics Enhancements

* Threat scoring system
* MITRE ATT&CK mapping
* Behavioral baselining
* Automated incident timelines
* AI-generated remediation suggestions

---

## 🛠️ Operational Improvements

* Docker Compose deployment
* Kubernetes support
* CI/CD pipelines
* Backup/restore tooling
* One-click certificate rotation
* Admin activity auditing

---

## 📊 Dashboard Enhancements

* Live WebSocket updates
* Dark/light theme toggle
* Advanced filtering/search
* Exportable reports
* Real-time notification center
* Interactive task timelines
