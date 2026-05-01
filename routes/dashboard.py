import json
import os
from datetime import datetime, timezone

import folium
from flask import (Blueprint, jsonify, render_template,
                   session, redirect, url_for)

from config import UPLOAD_FOLDER, API_KEY, AGENT_ONLINE_TIMEOUT
from database import get_db
from middleware.auth import require_token
from services.alerts import gen_alerts
from services.telegram import send_telegram_logs
from services.geo import get_location, get_online_offline_counts
from services.charts import tasks_execution_timestamps, task_success_rate

dashboard_bp = Blueprint("dashboard", __name__)


# ── Main dashboard ────────────────────────────────────────────────────────────

@dashboard_bp.route("/dashboard")
@require_token(role="admin")
def dashboard():
    if "username" not in session:
        return redirect(url_for("auth.login"))

    db       = get_db()
    files    = os.listdir(UPLOAD_FOLDER)
    now      = datetime.now(timezone.utc)

    task_rows = db.execute("""
        SELECT uuid, agent_id, task_json, output
        FROM tasks ORDER BY rowid DESC
    """).fetchall()

    tasks_str = {
        str(t["uuid"]): {
            "agent_id": t["agent_id"],
            "task":     json.loads(t["task_json"]),
            "output":   t["output"],
        }
        for t in task_rows
    }

    agent_rows = []
    for agent in db.execute("SELECT * FROM agents").fetchall():
        last_seen_dt = datetime.fromisoformat(agent["last_seen"])
        if last_seen_dt.tzinfo is None:
            last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)

        online = (now - last_seen_dt).total_seconds() <= AGENT_ONLINE_TIMEOUT
        agent_rows.append({
            "id":        agent["id"],
            "hostname":  agent["hostname"],
            "user":      agent["user"],
            "os":        agent["os"],
            "ip":        agent["ip"],
            "last_seen": last_seen_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "status":    "online" if online else "offline",
        })

    return render_template(
        "dashboard.html",
        files=files,
        api_key=API_KEY,
        agents=agent_rows,
        tasks=tasks_str,
    )


# ── Analytics page ────────────────────────────────────────────────────────────

@dashboard_bp.route("/info")
@require_token(role="admin")
def info():
    if "username" not in session:
        return redirect(url_for("auth.login"))
    return render_template("info.html", map=_build_map())


# ── Alerts page ───────────────────────────────────────────────────────────────

@dashboard_bp.route("/alerts")
@require_token(role="admin")
def alerts():
    gen_alerts()
    send_telegram_logs()
    return render_template("alerts.html")


@dashboard_bp.route("/get_alerts")
@require_token(role="admin")
def get_alerts():
    db   = get_db()
    rows = db.execute("""
        SELECT log_id, timestamp, role, log_message, alert_level, task_id
        FROM logs ORDER BY timestamp DESC
    """).fetchall()

    return jsonify({
        str(t["log_id"]): {
            "log_id":      t["log_id"],
            "timestamp":   t["timestamp"],
            "role":        t["role"],
            "log_message": t["log_message"],
            "alert_level": t["alert_level"],
            "task_id":     t["task_id"],
        }
        for t in rows
    })


# ── Chart data endpoints ──────────────────────────────────────────────────────

@dashboard_bp.route("/get_bar_chart")
def get_bar_chart():
    db     = get_db()
    agents = [row[0] for row in db.execute("SELECT id FROM agents").fetchall()]

    all_dates_set    = set()
    agent_date_counts = {}
    for agent_id in agents:
        counts = tasks_execution_timestamps(agent_id)
        agent_date_counts[agent_id] = counts
        all_dates_set.update(counts.keys())

    return jsonify({"dates": sorted(all_dates_set), "agents": agent_date_counts})


@dashboard_bp.route("/get_pie_chart")
def get_pie_chart():
    return jsonify(get_online_offline_counts())


@dashboard_bp.route("/get_piechart_task_success_rate")
def get_piechart_task_success_rate():
    db     = get_db()
    agents = [row[0] for row in db.execute("SELECT id FROM agents").fetchall()]

    all_statuses_set   = set()
    agent_status_counts = {}
    for agent_id in agents:
        counts = task_success_rate(agent_id)
        agent_status_counts[agent_id] = counts
        all_statuses_set.update(counts.keys())

    return jsonify({"statuses": sorted(all_statuses_set), "agents": agent_status_counts})


@dashboard_bp.route("/get_map")
def get_map():
    return _build_map()


# ── Internal helper ───────────────────────────────────────────────────────────

def _build_map() -> str:
    db  = get_db()
    ips = ["8.8.8.8", "146.70.246.122", "104.66.142.148", "1.178.95.0"]
    ips += [row[0] for row in db.execute("SELECT ip FROM agents").fetchall()]

    m = folium.Map(location=[20, 0], zoom_start=1)
    for ip in ips:
        result = get_location(ip)
        if result:
            lat, lon, city, country = result
            folium.Marker(
                location=[lat, lon],
                popup=f"{ip} - {city}, {country}"
            ).add_to(m)

    return m._repr_html_()