import string
import difflib

from flask import Blueprint, request, jsonify, render_template, session

from database import get_db
from services.ai import ask_ai, build_context

ai_bp = Blueprint("ai", __name__)

FAQ = {
    "What is the TENET?":
        "TENET is a Flask-based command-and-control style server for managing remote agents, dispatching tasks, receiving results, and monitoring agents in real time. Intended for educational and controlled automation environments only.",
    "How does encrypted communication work?":
        "Agents communicate using Fernet symmetric encryption to securely transmit beacons and task results. An API key is required for privileged operations.",
    "What kind of agents can I create?":
        "Agents can be created directly from the dashboard, requiring an ID, username, and password. They are stored in SQLite and assigned a default role 'agent'.",
    "How are agents stored and managed?":
        "Agents are stored in an SQLite database with persistent information, and can be monitored and updated via the dashboard.",
    "Which database does the server use?":
        "The server uses SQLite to store agents, tasks, users, and related data. It is lightweight and survives server restarts.",
    "Can I monitor agents in real time?":
        "Yes, the dashboard displays all connected agents with hostname, OS, username, IP, and last seen timestamp. Online/offline status is updated automatically.",
    "How do I upload files to agents?":
        "Files can be uploaded from the dashboard. Agents can download, store, or execute these files locally.",
    "How does the dual authentication system work?":
        "Admins use username/password to access the dashboard. Agents use token-based authentication issued after login for secure communication.",
    "How are plugins loaded and executed?":
        "Python modules can be dynamically loaded and executed in-memory on agents, without redeployment, allowing modular and rapid operations.",
    "What is the folder structure of the project?":
        "The project includes app.py (server), c2.db (SQLite), upload/ (files), plugins/ (modules), templates/ (HTML), and static/ (CSS/JS).",
    "What is beaconing and how does it work?":
        "Agents periodically send encrypted POST requests to /beacon. The server decrypts the payload, updates last_seen, marks them online, and returns pending tasks.",
    "How are tasks dispatched to agents?":
        "Tasks are stored in SQLite and delivered to agents when they beacon. Agents receive and execute tasks as soon as they check in.",
    "What types of tasks are supported?":
        "Supported task types include 'shell', 'download', 'upload', 'sleep', and 'plugin' execution.",
    "How do agents submit task results?":
        "Agents POST encrypted results to /result. The server decrypts the data, stores output in the database, and marks the task as completed.",
    "What can I do from the admin dashboard?":
        "Admins can view live agents, manage tasks, upload/download files, execute plugins, create new agents, and monitor activity in real time.",
    "Are there future improvements planned for the project?":
        "Potential improvements include role-based access control, agent grouping, WebSocket live updates, audit logs, a payload builder, and Docker deployment.",
}


def _normalize(text: str) -> str:
    return text.lower().translate(str.maketrans("", "", string.punctuation)).strip()


# ── FAQ chatbot ───────────────────────────────────────────────────────────────

@ai_bp.route("/chat", methods=["POST"])
def chat():
    user_message = (request.json.get("message") or "").strip()
    if not user_message:
        return jsonify({"reply": "Please ask a question."})

    normalized_input = _normalize(user_message)
    normalized_faq   = {_normalize(k): v for k, v in FAQ.items()}

    answer = normalized_faq.get(normalized_input)
    if not answer:
        matches = difflib.get_close_matches(
            normalized_input, list(normalized_faq.keys()), n=1, cutoff=0.6
        )
        if matches:
            answer = normalized_faq[matches[0]]

    if not answer:
        answer = "Sorry, I don't have an answer for that. Please check our FAQ page."

    conversation = session.get("conversation", [])
    conversation.append({"role": "user",      "content": user_message})
    conversation.append({"role": "assistant", "content": answer})
    session["conversation"] = conversation

    return jsonify({"reply": answer})


# ── Gemini AI chat ────────────────────────────────────────────────────────────

@ai_bp.route("/ai/chat", methods=["POST"])
def ai_chat():
    data         = request.get_json()
    user_message = data.get("message")
    if not user_message:
        return jsonify({"error": "Missing message"}), 400

    db = get_db()
    try:
        context     = build_context(db)
        ai_response = ask_ai(user_message, context)
        suggestion  = ai_response if "suggestion" in ai_response else None
        return jsonify({"reply": ai_response, "suggestion": suggestion})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Chat page ─────────────────────────────────────────────────────────────────

@ai_bp.route("/chat")
def chat_page():
    return render_template("chat.html")