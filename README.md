# 🛰️ Remote Agent Control Server  
A Flask‑based command‑and‑control style server for managing remote agents, dispatching tasks, receiving results, and monitoring agent status.  
This project is intended for **educational**, **research**, and **automation** scenarios where a central server coordinates lightweight remote clients.

---

## 🚀 Features

### 🔐 Encrypted Communication  
- Agents send encrypted JSON payloads using Fernet symmetric encryption  
- Server decrypts beacons and results  
- API key required for creating tasks

### 🗄️ SQLite Database Integration  
- Persistent storage for:
  - Agents  
  - Tasks  
  - Users  
- Survives server restarts  
- Simple schema, easy to extend

### 📡 Live Agent Monitoring  
- Tracks:
  - Hostname  
  - OS  
  - Username  
  - IP address  
  - Last seen timestamp  
- Online/offline detection with configurable timeout

### 📁 File Upload Support  
- Upload files to the server  
- Agents can download them when needed

### 🔑 Dual Login System  
- **Dashboard login** for administrators  
- **Agent login** for remote clients (token‑based)



## 📦 Project Structure

```
project/
│
├── app.py                 # Main Flask server
├── database.db            # SQLite database
├── upload/                # Uploaded files
├── templates/             # HTML templates for dashboard
└── static/                # CSS/JS assets
```



## ⚙️ How It Works

### 1. Agent Login  
Agents authenticate using JSON credentials.  
On success, the server:

- Registers the agent  
- Issues a session token  
- Stores metadata in SQLite  

### 2. Beaconing  
Agents periodically POST encrypted JSON to `/beacon`.  
The server:

- Updates `last_seen`  
- Returns the next pending task (if any)

### 3. Task Execution  
Tasks are stored in SQLite and delivered to agents when they beacon.

### 4. Result Submission  
Agents POST encrypted results to `/result`.  
The server updates the task entry with the output.

### 5. Dashboard  
Admins can:

- View agents  
- View tasks  
- Upload files  
- Delete tasks  
- Monitor online/offline status  

---

## 🔧 Running the Server

### Install dependencies

```
pip install -r requirements.txt
```

### Set environment variables

```
API_KEY=your_api_key_here
```

### Start the server

```
python app.py
```

Server runs on:

```
http://0.0.0.0:5000
```

---

## 🧪 Example Agent Beacon Payload

Encrypted JSON (after decryption):

```json
{
  "id": "agent1",
  "hostname": "DESKTOP-123",
  "user": "john",
  "os": "Windows 10"
}
```

---

## 📬 Task Format

Tasks are simple JSON objects:

```json
{
  "type": "shell",
  "command": "whoami"
}
```

---

## 🛡️ Security Notes

- All agent communication is encrypted using Fernet  
- API key required for task creation  
- Consider hashing dashboard passwords in production  

---




