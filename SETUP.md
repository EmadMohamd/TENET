# ⚙️ Setup Guide — Remote Agent Control Server

This guide walks through setting up the server from scratch, including database initialization, environment configuration, mTLS setup, and first-time access.

---

# 🧱 1. Prerequisites

* Python 3.10+
* pip
* SQLite
* OpenSSL
* Nginx

---

# 📦 2. Clone & Install

```bash
git clone <your-repo-url>
cd TENET

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

```

---

# ⚙️ 3. Environment Configuration

Copy the example file:

```bash
cp .env.example .env

```

### Generate a Fernet key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

```

---

# 🗄️ 4. Database Setup

Create the database:

```bash
sqlite3 database.db

```

Run the following schema:

```sql
CREATE TABLE "agents" (
    "id"   TEXT,
    "hostname" TEXT,
    "user" TEXT,
    "os"   TEXT,
    "ip"   TEXT,
    "last_seen"    TEXT,
    "agent_group"  TEXT DEFAULT 'none',
    PRIMARY KEY("id")
);

CREATE TABLE "logs" (
    "log_id"   TEXT,
    "timestamp"    TEXT DEFAULT CURRENT_TIMESTAMP,
    "role" TEXT NOT NULL DEFAULT 'administrator',
    "log_message"  TEXT NOT NULL,
    "alert_level"  TEXT,
    "task_id"  TEXT,
    "sent" INTEGER DEFAULT 0,
    PRIMARY KEY("log_id")
);

CREATE TABLE "login_attempts" (
    "ip"   TEXT,
    "attempts" INTEGER DEFAULT 0,
    "last_attempt" TIMESTAMP
);

CREATE TABLE tasks (
    uuid TEXT PRIMARY KEY,
    agent_id TEXT,
    task_json TEXT,
    output TEXT,
    executed_at TEXT, 
    scheduled_at TEXT, 
    recurring_every TEXT, 
    status TEXT GENERATED ALWAYS AS (
    CASE 
        WHEN executed_at IS NULL THEN 'pending'

        WHEN output LIKE '%[+]%' 
          OR output LIKE '%completed%' 
          OR output LIKE '%successful%' 
          OR output LIKE '%executed%' 
          OR output LIKE '%uploaded%'
          OR output LIKE '%downloaded%'  
        THEN 'success'
        
        WHEN output LIKE '%[!]%' 
          OR output LIKE '%failure%' 
          OR output LIKE '%failed%' 
          OR output LIKE '%aborted%' 
          OR output LIKE '%error%' 
        THEN 'failure'
        
        ELSE 'success'
    END
) VIRTUAL);

CREATE TABLE tokens (
    token TEXT PRIMARY KEY,
    agent_id TEXT,
    expiry TEXT, 
    username TEXT,
    FOREIGN KEY(agent_id) REFERENCES agents(id)
);

CREATE TABLE IF NOT EXISTS stager_tokens (
    token TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE INDEX idx_stager_token_used ON stager_tokens(used, expires_at);

CREATE TABLE "users" (
    "username" TEXT,
    "password" TEXT, 
    role TEXT DEFAULT 'agent',
    PRIMARY KEY("username")
);

```

---

# 👤 5. Create Admin User

Create an Admin user via the admin bootstrap registration panel at first startup.

---

# 🔐 6. Generate mTLS Certificates

**THE CERTIFICATE IS BUILT ON c2.local CHANGE IT TO YOUR REGISTERED DOMAIN NAME**

```bash
#!/bin/bash
set -e
```

##  GENERATE ROOT CA

### Generate CA Private Key
```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out ca.key
```

### Generate Root CA Certificate with critical CA extensions
```bash
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -out ca.crt \
  -subj "/C=US/ST=CA/O=TENET/CN=C2 Local Root CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"```

```

##  GENERATE SERVER CERTIFICATE

### Generate Server Private Key
```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out server.key
```
### Generate Server CSR
```bash
openssl req -new -key server.key -out server.csr \
    -subj "/C=US/ST=CA/O=TENET/CN=c2.local"
```

### Create Server Extension Config File
```
cat << 'EOF' > server_ext.cnf
authorityKeyIdentifier = keyid,issuer
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = c2.local
IP.1 = 127.0.0.1
EOF
```

### Sign Server Certificate using CA and Extension Config
```bash
openssl x509 -req -in server.csr \
    -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 365 -sha256 \
    -extfile server_ext.cnf
```



##  GENERATE ADMIN CLIENT CERTIFICATE & PKCS#12

### Generate Admin Private Key
```openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out admin.key```

### Generate Admin CSR
``` bash
openssl req -new -key admin.key -out admin.csr \
    -subj "/C=US/ST=CA/O=TENET/CN=admin"
```

### Create Admin Extension Config File (for mTLS clientAuth)
```
cat << 'EOF' > admin_ext.cnf
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = clientAuth
EOF
```

### Sign Admin Certificate using CA
```bash
openssl x509 -req -in admin.csr \
    -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out admin.crt -days 365 -sha256 \
    -extfile admin_ext.cnf
```

### Clean up temporary extension file
```rm -f admin_ext.cnf```

### Export to PKCS#12 (.p12) bundle for browser/client import
```bash
openssl pkcs12 -export -out admin.p12 \
    -inkey admin.key -in admin.crt \
    -certfile ca.crt
```

### TEST AND RELOAD NGINX

```
nginx -t && systemctl reload nginx
```
---

# 🌐  Configure Nginx

Edit your Nginx config and paste your server configuration template:

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

Restart Nginx:

```bash
sudo systemctl restart nginx

```

---

# 🚀 8. Run the Server

```bash
python app.py

```

> 💡 **Background Engine:** On initialization, a daemon thread begins running automatically in the background within the application context. This worker executes every hour (`interval_seconds=3600`) to continuously purge expired or unused stager deployment tokens from the SQLite database.

Flask must bind to:

```text
127.0.0.1:5000

```

---

# 🤖 9. Create Your First Agent & Generate Token

1. Log into the web dashboard interface.
2. Navigate to **Create Agent** and provision profile settings (ID, Group, Version, Credentials).
3. Select the target profile and invoke the **Stager Token Generator**.
4. The backend will invoke the administrative route `POST /agents/admin/generate-stager` to:
* Populate a cryptographically random token valid for exactly 60 minutes.
* Format a quick-start bootstrap string structure for operational use.



---

# 📦 10. Dynamic Deployment (Using the Stager)

Instead of manually dragging individual certificate bundles and configurations to your execution machines, copy only the initial lightweight footprint file (`stager.py`).

Run the deployment hook on the target node:

```bash
python stager.py <YOUR_GENERATED_TOKEN>

```

### The Automatic Execution Workflow

* The script calls endpoints via TLS (`/stager/agent`, `/stager/config`, `/stager/certs`).
* Dynamically fetches matching keys, application modules, and unique client properties.
* Saves configurations safely to disk (`chmod 600`).
* Signals the control server via `POST /stager/consume-token` to burn the operational session.
* Spawns the finalized application engine runtime loop to initiate encrypted mTLS beacons.

---

# ✅ 11. Verify mTLS Manually

Test manual certificate verification connections:

```bash
curl https://your-server \
  --cert agent-001.crt \
  --key agent-001.key \
  --cacert ca.crt

```

---

# ⚠️ Important Notes

* Never expose Flask directly (only proxy via Nginx).
* Background daemon threads manage database-dependent cleanup routines; ensure application context bindings remain unaltered if adjusting lifecycle loops.
* Active deployment tokens or active agent private keys.
* Ensure port 5000 is blocked completely from public edge routing access.