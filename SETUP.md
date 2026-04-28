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
	"id"	TEXT,
	"hostname"	TEXT,
	"user"	TEXT,
	"os"	TEXT,
	"ip"	TEXT,
	"last_seen"	TEXT,
	"agent_group"	TEXT DEFAULT 'none',
	PRIMARY KEY("id")
);

CREATE TABLE "logs" (
	"log_id"	TEXT,
	"timestamp"	TEXT DEFAULT CURRENT_TIMESTAMP,
	"role"	TEXT NOT NULL DEFAULT 'administrator',
	"log_message"	TEXT NOT NULL,
	"alert_level"	TEXT,
	"task_id"	TEXT,
	"sent"	INTEGER DEFAULT 0,
	PRIMARY KEY("log_id")
);

CREATE TABLE "login_attempts" (
	"ip"	TEXT,
	"attempts"	INTEGER DEFAULT 0,
	"last_attempt"	TIMESTAMP
);

CREATE TABLE tasks (
    uuid TEXT PRIMARY KEY,
    agent_id TEXT,
    task_json TEXT,
    output TEXT
, executed_at TEXT, scheduled_at TEXT, recurring_every TEXT, status TEXT GENERATED ALWAYS AS (
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
    expiry TEXT, username TEXT,
    FOREIGN KEY(agent_id) REFERENCES agents(id)
);

CREATE TABLE "users" (
	"username"	TEXT,
	"password"	TEXT, role TEXT DEFAULT 'agent',
	PRIMARY KEY("username")
);

```


# 👤 5. Create Admin User

Add Username/Password to the "users" TABLE and set the role to be "admin"
Generate a bcrypt hash:

```bash
python3
```

```python
import bcrypt
print(bcrypt.hashpw(b"yourpassword", bcrypt.gensalt()).decode())
```

Insert into DB:

```bash
sqlite3 database.db
```

```sql
INSERT INTO users (username, password, role)
VALUES ('admin', '<PASTE_HASH_HERE>', 'admin');
```

---

# 🔐 6. Generate mTLS Certificates

Create CA:

```bash
mkdir -p keys
cd keys

openssl genrsa -out ca.key 4096
openssl req -x509 -new -key ca.key -out ca.crt -days 365
```

Create server certificate:

```bash
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr

openssl x509 -req -in server.csr \
    -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 365
```

---

# 🌐 7. Configure Nginx

Edit your Nginx config:

and copy the Nginx_Config file 
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

Flask must bind to:

```
127.0.0.1:5000
```

---

# 🤖 9. Create Your First Agent

1. Log into the dashboard
2. Go to **Create Agent**
3. Fill in:

   * Agent ID
   * Username / Password
   * Optional group

✔️ The system will automatically:

* Generate agent certificate
* Generate private key
* Create agent file

---

# 📦 10. Deploy Agent

Copy to agent machine:

* Agent file (`Agent{id}.py`)
* `agent-{id}.crt`
* `agent-{id}.key`
* `ca.crt`

---

# ✅ 11. Verify mTLS

Test connection:

```bash
curl https://your-server \
  --cert agent-001.crt \
  --key agent-001.key \
  --cacert ca.crt
```

---

# ⚠️ Important Notes

* Never expose Flask directly (only via Nginx)
* Never commit:

  * `.env`
  * `ca.key`
  * agent private keys
* Ensure port 5000 is not publicly accessible

---

