# 🛰️ Remote Agent Control Server

A **Flask-based command-and-control style server** designed for managing remote agents, dispatching tasks, collecting results, and monitoring system activity in real time.

> ⚠️ Intended strictly for **educational, research, and controlled automation environments only**

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
  * **Automatically issued a unique mTLS certificate at creation time**
* Passwords are **hashed with bcrypt** before storage — plaintext credentials are never written to the database
* Enables structured and controlled onboarding

---

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
├── agent-002.crt                  ← each agent gets its own unique cert
└── admin-alice.crt                ← admin browser certificates (.p12 format)
```

* The CA **public** certificate (`ca.crt`) is distributed to agents so they can verify the server's identity during the TLS handshake
* The CA **private** key (`ca.key`) never leaves the server and is never needed by agents — it is only used server-side to sign new certificates
* All certificates trace back to this single root of trust

---

### Agent Certificate Generation (Automatic)

When an agent is created via the dashboard, the server **automatically generates a certificate** for that agent. No manual OpenSSL commands are needed.

The creation flow:

1. Admin fills in Agent ID, username, password, and group in the dashboard
2. Password is immediately hashed with bcrypt — plaintext is never stored
3. Server generates:
   * `agent-{id}.key` — RSA 2048-bit private key
   * `agent-{id}.csr` — Certificate Signing Request (deleted after signing)
   * `agent-{id}.crt` — Certificate signed by the CA (stored in `./certs/agents/`)
4. The certificate and key paths are written into the agent file (`Agent{id}.py`)
5. The agent file, cert, and key are deployed together onto the agent machine
6. The full mTLS bundle (agent file + cert + key + CA public cert) must be present on the agent machine for it to operate — possession of the agent file alone is not sufficient to connect

The CN (Common Name) in each agent certificate is set to the Agent ID. Nginx extracts this and forwards it to Flask as `X-Client-Cert-CN`, which is how the server identifies which agent is communicating.

---

### Certificate Storage Layout

```
certs/
├── ca.crt               ← CA public cert  (distributed to agents)
├── ca.key               ← CA private key  (server only, never shared)
├── ca.srl               ← Serial number tracking
├── server.crt           ← Server TLS certificate
├── server.key           ← Server private key
├── agents/
│   ├── agent-001.crt    ← Per-agent certificates
│   ├── agent-001.key
│   ├── agent-002.crt
│   └── ...
├── admins/
│   ├── alice.crt        ← Admin certificates (server-side copy)
│   ├── alice.key
│   ├── alice.p12        ← .p12 file imported into admin browser
│   └── ...

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
ssl_client_certificate /path/to/certs/ca.crt;
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
### Certificate Management

#### Revoking an Agent

When an agent is decommissioned or compromised, its certificate is revoked:

#### Renewing a Certificate

Certificates are valid for 365 days by default. To renew, revoke the old agent and recreate it via the dashboard — a new certificate is generated automatically.

#### Verifying the Certificate Chain

```bash
# Confirm a cert was signed by your CA
openssl verify -CAfile certs/ca.crt certs/agents/agent-001.crt
# Output: certs/agents/agent-001.crt: OK
```

---

### Security Notes for mTLS

* **`ca.key` is the most critical secret** — it never leaves the server and agents have no need for it. Only the CA public cert (`ca.crt`) is distributed to agents for server verification.
* **Each agent has a unique key pair** — revoking one agent does not affect others.
* **The full mTLS bundle must be present on the agent machine** — the agent file alone is not sufficient; the cert and key must accompany it for any connection to succeed.
* **Flask binds to loopback only** (`127.0.0.1:5000`) — direct access bypasses Nginx and mTLS entirely. Never bind Flask to `0.0.0.0`.
* **Admin certs use `O=Admin`** in the DN — Flask checks this field to prevent agents from accessing admin-only routes even if they hold a valid cert.

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

* mTLS certificate issued at agent creation — must be present on the agent machine alongside the agent file
* Credentials (username and password) hashed with bcrypt before storage — never stored in plaintext
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

### 🎯 Targeting Modes

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

### 👥 Group-Based Tasking

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

* Admin creates agent via dashboard
* Password hashed with bcrypt before storage — plaintext never persisted
* Server automatically generates mTLS certificate for the agent
* Agent file (`Agent{id}.py`) written with cert paths embedded
* Agent optionally assigned an `agent_group`

---

### 2️⃣ Agent Login

* Agent presents mTLS certificate during TLS handshake (verified by Nginx)
* Agent sends credentials — server validates against bcrypt hash in DB
* Server:

  * Registers/updates agent record
  * Returns auth token for the session

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

* Verifies mTLS certificate (Nginx layer)
* Decrypts Fernet payload
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
  "recurring_at": "60min",
  "agent_group": "monitoring"
}
```

---

### 5️⃣ Result Submission (`/result`)

* Agent presents mTLS certificate (Nginx verifies)
* Agent sends Fernet-encrypted results
* Server:

  * Decrypts data
  * Stores output
  * Marks task completed

---

## 📦 Project Structure

```
TENET/
│
├── app.py              # Main Flask server
├── database.db         # SQLite database
├── upload/             # Uploaded files
├── plugins/            # Server-side plugins
├── tools/               # Helper tools & plugin resources
├── templates/          # HTML dashboard
├── static/             # CSS / JS assets
└── certs/
    ├── ca.crt          # CA public certificate
    ├── ca.key          # CA private key
    ├── server.crt      # Server TLS certificate
    ├── server.key      # Server private key
    ├── agents/         # Per-agent certificates
    ├── admins/         # Admin .p12 bundles
    ├── metadata/       # Certificate metadata (JSON)
    └── revoked/        # Revoked certificates
```

---

## 🛡️ Security Notes

* 🔒 Encrypted communication (Fernet) — obfuscates payload on top of TLS as an additional layer
* 🔑 API key protection for sensitive routes
* 🔒 mTLS enforced on all agent and admin routes via Nginx
* 🔒 HTTP automatically redirected to HTTPS
* 🔒 All passwords (operators and agents) hashed with bcrypt — never stored in plaintext
* 🔒 Each agent holds a unique certificate — revocation is per-agent and does not affect others
* 🔒 Admin dashboard requires both login credentials and a browser-imported certificate
* 🔒 CA public cert distributed to agents for server verification; CA private key stays server-side only
* ⚠️ Flask must bind to `127.0.0.1` only — never `0.0.0.0`
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
* OCSP/CRL-based real-time certificate revocation
* HSM integration for CA key storage