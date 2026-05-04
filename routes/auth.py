import secrets
import bcrypt
from datetime import datetime, timezone, timedelta

from flask import (Blueprint, request, jsonify, render_template,
                   session, redirect, url_for)

from database import get_db
from config import MAX_ATTEMPTS

auth_bp = Blueprint("auth", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_client_ip() -> str:
    return request.remote_addr


def update_attempts(db, ip: str, success: bool):
    """Increment or clear failed login attempts for an IP."""
    if success:
        db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
        return

    record = db.execute(
        "SELECT attempts FROM login_attempts WHERE ip = ?", (ip,)
    ).fetchone()

    if record:
        db.execute("""
            UPDATE login_attempts
            SET attempts = attempts + 1, last_attempt = ?
            WHERE ip = ?
        """, (datetime.now().isoformat(), ip))
    else:
        db.execute("""
            INSERT INTO login_attempts (ip, attempts, last_attempt)
            VALUES (?, 1, ?)
        """, (ip, datetime.now().isoformat()))


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    ip = get_client_ip()

    # Clean expired tokens
    db.execute(
        "DELETE FROM tokens WHERE expiry < ?",
        (datetime.now(timezone.utc).isoformat(),)
    )
    db.commit()

    # Check / reset lockout
    record    = db.execute(
        "SELECT attempts, last_attempt FROM login_attempts WHERE ip = ?", (ip,)
    ).fetchone()
    LOCK_TIME = timedelta(minutes=1)

    if record:
        last = datetime.fromisoformat(record["last_attempt"])
        if datetime.now() - last > LOCK_TIME:
            db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))
            db.commit()

    if record and record["attempts"] >= MAX_ATTEMPTS:
        import uuid as _uuid
        log_uuid     = str(_uuid.uuid4())
        current_time = datetime.now(timezone.utc)
        db.execute(
            "INSERT INTO logs (log_id, timestamp, role, log_message, alert_level, task_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (log_uuid, current_time, "None",
             f"Failed Login 3 Times, IP: {ip}", "Critical", "None")
        )
        db.commit()
        return "Too many attempts from this IP"

    # ── GET ───────────────────────────────────────────────────────────────────
    if request.method == "GET":
        return render_template("login.html")

    # ── POST ──────────────────────────────────────────────────────────────────
    if request.is_json:
        data      = request.get_json(silent=True) or {}
        username  = data.get("username")
        password  = data.get("password")
        agent_id  = data.get("agent_id")
        is_api    = True
    else:
        username  = request.form.get("username")
        password  = request.form.get("password")
        agent_id  = None
        is_api    = False

    row = db.execute(
        "SELECT password, role FROM users WHERE username = ?", (username,)
    ).fetchone()

    if not row or not bcrypt.checkpw(password.encode("utf-8"), row["password"]):
        update_attempts(db, ip, success=False)
        db.commit()
        if is_api:
            return jsonify({"error": "Unauthorized"}), 401
        return render_template("login.html", error="Invalid credentials")

    role = row["role"]

    # ── Web (admin) login ─────────────────────────────────────────────────────
    if not is_api:
        if role != "admin":
            update_attempts(db, ip, success=False)
            db.commit()
            return render_template("login.html", error="Access denied")

        session["username"] = username
        session["role"]     = role
        update_attempts(db, ip, success=True)
        db.commit()
        return redirect(url_for("dashboard.dashboard"))

    # ── API (agent) login ─────────────────────────────────────────────────────
    token  = secrets.token_hex(32)
    expiry = datetime.utcnow() + timedelta(days=7)

    if agent_id:
        db.execute("DELETE FROM tokens WHERE agent_id = ?", (agent_id,))

        agent = db.execute(
            "SELECT id FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()

        if not agent:
            db.execute("""
                INSERT INTO agents (id, hostname, user, os, ip, last_seen, agent_group)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                agent_id, data.get("hostname"), data.get("user"),
                data.get("os"), request.remote_addr,
                datetime.utcnow().isoformat(), data.get("agent_group")
            ))
        else:
            db.execute("""
                UPDATE agents SET last_seen = ?, ip = ? WHERE id = ?
            """, (datetime.utcnow().isoformat(), request.remote_addr, agent_id))

    db.execute("""
        INSERT INTO tokens (token, agent_id, expiry, username)
        VALUES (?, ?, ?, ?)
    """, (token, agent_id, expiry.isoformat(), username))

    update_attempts(db, ip, success=True)
    db.commit()

    return jsonify({
        "status":  "ok",
        "token":   token,
        "role":    role,
        "expires": expiry.isoformat()
    }), 200


@auth_bp.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("auth.login"))