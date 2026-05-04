import secrets
import bcrypt
from datetime import datetime, timezone, timedelta

from flask import (Blueprint, request, jsonify, render_template,
                   session, redirect, url_for, flash)

from database import get_db
from config import MAX_ATTEMPTS

register_bp = Blueprint("register", __name__)


# ── Routes ────────────────────────────────────────────────────────────────────

@register_bp.route("/admin_register", methods=["GET", "POST"])
def admin_register():
    db = get_db()

    # Check if any admin already exists
    existing_admin = db.execute(
        "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
    ).fetchone()

    if existing_admin:
        return redirect(url_for("auth.login"))

    # ── GET ───────────────────────────────────────────────────────────────────
    if request.method == "GET":
        return render_template("admin_register.html")

    # ── POST ──────────────────────────────────────────────────────────────────
    username = request.form.get("username")
    password = request.form.get("password")
    confirm_password = request.form.get("confirm_password")

    # Basic validation
    if not username or not password or not confirm_password:
        flash("All fields are required.", "error")
        return render_template("admin_register.html", error="All fields are required.")

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return render_template("admin_register.html", error="Passwords do not match.")

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    db.execute(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
        (username, hashed, "admin")
    )
    db.commit()

    return redirect(url_for("auth.login"))  # Replace 'auth_bp.login' with your login route