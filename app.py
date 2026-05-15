import logging
import sys
import os

from flask import Flask ,request, redirect, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import database
from database import get_db
from config import SECRET_KEY, UPLOAD_FOLDER, PLUGINS_DIR, PORT
from services.scheduler import restart_recurring_tasks

from routes.auth      import auth_bp
from routes.agents    import agents_bp
from routes.beacon    import beacon_bp
from routes.tasks     import tasks_bp
from routes.files     import files_bp
from routes.plugins   import plugins_bp
from routes.dashboard import dashboard_bp
from routes.ai        import ai_bp
from routes.revshell  import revshell_bp
from routes.register import register_bp

# ── Terminal colour formatting ────────────────────────────────────────────────

G = "\033[92m"   # green  (2xx)
B = "\033[94m"   # blue   (3xx)
R = "\033[91m"   # red    (4xx / 5xx)
W = "\033[0m"    # reset


class StatusFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        if   " 200 " in msg or " 201 " in msg:                         return f"{G}{msg}{W}"
        elif any(c in msg for c in [" 301 ", " 302 ", " 304 "]):       return f"{B}{msg}{W}"
        elif any(c in msg for c in [" 400 ", " 404 ", " 500 ", " 503 "]): return f"{R}{msg}{W}"
        return msg


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(StatusFormatter())
werk_log = logging.getLogger("werkzeug")
werk_log.setLevel(logging.INFO)
werk_log.handlers   = [handler]
werk_log.propagate  = False


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key            = SECRET_KEY
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["TOOLS_FOLDER"]  = "tools"

    # Ensure runtime directories exist
    os.makedirs(PLUGINS_DIR,   exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Database teardown
    database.init_app(app)

    @app.before_request
    def check_access():
        db = get_db()

        # Always allow static files
        if request.endpoint == "static":
            return

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
        if request.endpoint not in allowed_endpoints:
            if "username" not in session:
                return redirect("/login")

    # Rate limiter (applied per-route via @limiter.limit)
    limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day"])

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

    return app


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_app()
    restart_recurring_tasks(app)
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)