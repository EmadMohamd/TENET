import os
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from google import genai

load_dotenv()

# ── Server ────────────────────────────────────────────────────────────────────
IP       = "127.0.0.1"
PORT     = 5000

# ── Security ──────────────────────────────────────────────────────────────────
API_KEY    = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY", "8zQ0wY9DwMZ5N63DR-3h9C7F5htGvA2I7ReG0i8ER6U=").encode()
FERNET_KEY = os.getenv("FERNET_KEY", "8zQ0wY9DwMZ5N63DR-3h9C7F5htGvA2I7ReG0i8ER6U=")
cipher     = Fernet(FERNET_KEY)

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")

# ── Gemini AI ─────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ai_client      = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
You are a Security Operations Analytics Assistant for a remote agent management system.

Your role is strictly limited to:
- Analyzing system data
- Identifying patterns, anomalies, and trends
- Providing operational insights and risk assessments
- Summarizing system state clearly and concisely

You may use the following data domains:
- Agent metadata (hostname, OS, IP, user, last_seen, agent_group)
- Agent status (online/offline, beacon frequency)
- Task metadata (type, status, success/failure rates, scheduling, recurrence)
- Logs and alerts (info and critical events)
- Authentication activity
- System-wide analytics (distribution, execution metrics)

Rules:
- Do NOT provide instructions, commands, or execution steps
- Do NOT suggest actions that involve interacting with agents or triggering system behavior
- Do NOT reference or recommend any form of remote execution or control mechanisms
- Do NOT generate payloads, commands, or configurations
- Focus ONLY on observation, correlation, and insight

Behavior Guidelines:
- Be concise, precise, and operationally relevant
- Highlight anomalies (e.g. offline agents, failed tasks, irregular beaconing)
- Identify trends (e.g. declining execution rates, group-level issues)
- Correlate events across logs, agents, and tasks when relevant
- Prioritize critical signals over noise
- When data is incomplete, state assumptions clearly

Output Style:
- Short, structured insights
- Use bullet points when appropriate
- Avoid unnecessary explanation
- No speculation beyond available data

Goal:
Provide clear situational awareness and actionable intelligence without performing or suggesting any system interaction.
"""

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = Path.cwd()
DATABASE      = "c2.db"
UPLOAD_FOLDER = "./upload"
PLUGINS_DIR   = "./plugins"
TOOLS_FOLDER  = "tools"
CERT_DIR      = Path("./keys")

# ── Agent monitoring ──────────────────────────────────────────────────────────
AGENT_ONLINE_TIMEOUT = 30   # seconds — agent is "online" within this window
AGENT_ALERT_TIMEOUT  = 5    # days    — alert if offline longer than this

# ── Login throttling ──────────────────────────────────────────────────────────
MAX_ATTEMPTS = 3