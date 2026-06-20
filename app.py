import logging
import sys
import os

from flask import Flask, request, redirect, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import database
from database import get_db
from config import FERNET_KEY, UPLOAD_FOLDER, PLUGINS_DIR, PORT
from services.scheduler import restart_recurring_tasks
from services.stager_token import start_periodic_cleanup

from routes.auth import auth_bp
from routes.agents import agents_bp
from routes.beacon import beacon_bp
from routes.tasks import tasks_bp
from routes.files import files_bp
from routes.plugins import plugins_bp
from routes.dashboard import dashboard_bp
from routes.ai import ai_bp
from routes.revshell import revshell_bp
from routes.register import register_bp
from routes.stager import stager_bp

# ── Terminal colour formatting ────────────────────────────────────────────────

G = "\033[92m"  # green  (2xx)
B = "\033[94m"  # blue   (3xx)
R = "\033[91m"  # red    (4xx / 5xx)
W = "\033[0m"  # reset


class StatusFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        if " 200 " in msg or " 201 " in msg:
            return f"{G}{msg}{W}"
        elif any(c in msg for c in [" 301 ", " 302 ", " 304 "]):
            return f"{B}{msg}{W}"
        elif any(c in msg for c in [" 400 ", " 404 ", " 500 ", " 503 "]):
            return f"{R}{msg}{W}"
        return msg


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(StatusFormatter())
werk_log = logging.getLogger("werkzeug")
werk_log.setLevel(logging.INFO)
werk_log.handlers = [handler]
werk_log.propagate = False


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = FERNET_KEY
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["TOOLS_FOLDER"] = "tools"

    # Ensure runtime directories exist
    os.makedirs(PLUGINS_DIR, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Database teardown
    database.init_app(app)

    @app.before_request
    def check_access():
        path = request.path
        db = get_db()

        # Always allow static files
        if request.endpoint == "static":
            return

        # PUBLIC EXEMPTIONS (ADD STAGER HERE)
        if request.path.startswith("/stager/"):
            return

        if request.path.startswith("/upload"):
            return

        if request.path.startswith("/tools/"):
            return

        if path.startswith("/plugins/"):
            # Check if user has valid session (admin accessing /plugins/)
            if "username" in session:
                return  # Allow session-based access

            # Check if agent has valid TOKEN (downloading /plugins/<filename>)
            token = request.headers.get("TOKEN")
            if token:
                token_exists = db.execute(
                    "SELECT agent_id FROM tokens WHERE token = ?",
                    (token,)
                ).fetchone()
                if token_exists:
                    return  # Allow token-based access

            # Neither session nor token
            if request.is_json:
                return {"error": "Missing TOKEN or session"}, 401
            return redirect("/login")

        agent_paths = [
            "/stager/",
            "/beacon",
            "/result",
            "/plugins/",
            "/api/agent_update",
        ]

        if any(path.startswith(p) for p in agent_paths):
            # Require TOKEN header for agent endpoints
            token = request.headers.get("TOKEN")
            if not token:
                return {"error": "Missing TOKEN"}, 401

            # Verify token exists in database
            db = get_db()
            token_exists = db.execute(
                "SELECT agent_id FROM tokens WHERE token = ?",
                (token,)
            ).fetchone()

            if not token_exists:
                return {"error": "Invalid TOKEN"}, 401

            return  # Allow request

        # Public endpoints
        allowed_endpoints = [
            "auth.login",
            "auth.logout",
            "register.admin_register",
            "static"
        ]

        # Check if admin exists
        admin_exists = db.execute(
            "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
        ).fetchone()

        # No admin exists → force admin registration
        if not admin_exists:
            if request.endpoint != "register.admin_register":
                return redirect("/admin_register")
            return

        # Prevent accessing admin_register after setup
        if admin_exists and request.endpoint == "register.admin_register":
            return redirect("/login")

        # Require login
        if request.is_json:
            return

        # Require web session login
        if request.endpoint not in allowed_endpoints:
            if "username" not in session:
                return redirect("/login")

    # Rate limiter (applied per-route via @limiter.limit)
    limiter = Limiter(get_remote_address, app=app, default_limits=["20000 per day"])

    # Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(beacon_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(plugins_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(revshell_bp)
    app.register_blueprint(register_bp)
    app.register_blueprint(stager_bp)

    return app


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_app()
    restart_recurring_tasks(app)
    start_periodic_cleanup(app, interval_seconds=3600)
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)