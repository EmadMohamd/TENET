# routes/stager.py
"""
Stager endpoints - one-time token protected downloads.
"""

import json
import logging

from flask import Blueprint, jsonify, request, session
from cryptography.fernet import Fernet

from config import FERNET_KEY
from database import get_db
from services.stager_token import (
    generate,
    verify,
    consume,
)

logger = logging.getLogger(__name__)

stager_bp = Blueprint("stager", __name__)

cipher = Fernet(FERNET_KEY)


@stager_bp.route("/stager/agent", methods=["GET"])
def download_agent():
    """
    Download agent code using one-time token.

    Usage:
        curl "https://server.com/stager/agent?token=xxxxx"
    """
    token = request.args.get("token")
    if not token:
        return jsonify({"error": "Missing token"}), 400

    # Verify and consume token
    agent_id = verify(token)

    if not agent_id:
        logger.warning(f"[STAGER] Invalid/expired token: {token[:10]}")
        return jsonify({"error": "Invalid or expired token"}), 401

    try:
        with open(f"Agent{agent_id}.py", "r") as f:
            agent_code = f.read()

        logger.info(f"[STAGER] Downloaded agent for {agent_id}")

        return jsonify({
            "status": "ok",
            "agent_id": agent_id,
            "agent": agent_code
        }), 200

    except FileNotFoundError:
        logger.error(f"[STAGER] Agent file not found: {agent_id}")
        return jsonify({"error": "Agent not found"}), 404

    except Exception as e:
        logger.error(f"[STAGER] Error: {e}")
        return jsonify({"error": str(e)}), 500


@stager_bp.route("/stager/config", methods=["GET"])
def download_config():
    """
    Download agent configuration using one-time token.

    Usage:
        curl "https://server.com/stager/config?token=xxxxx"
    """
    token = request.args.get("token")

    if not token:
        return jsonify({"error": "Missing token"}), 400

    # Verify token (but don't consume)
    agent_id = verify(token)

    if not agent_id:
        logger.warning(f"[STAGER] Invalid/expired token: {token[:10]}")
        return jsonify({"error": "Invalid or expired token"}), 401

    logger.info(f"[STAGER] Downloaded config for {agent_id}")
    try:
        with open(f"Agent{agent_id}.conf", "r") as f:
            agent_conf = f.read()

        return jsonify({

            "agent_conf": agent_conf
        })


    except Exception as e:
        logger.error(f"[STAGER] Error: {e}")
        return jsonify({"error": str(e)}), 500


@stager_bp.route("/stager/certs", methods=["GET"])
def download_certs():
    """
    Download mTLS certificates using one-time token.

    Usage:
        curl "https://server.com/stager/certs?token=xxxxx"
    """
    token = request.args.get("token")

    if not token:
        return jsonify({"error": "Missing token"}), 400

    # Verify token
    agent_id = verify(token)
    agent_id = consume(token)

    if not agent_id:
        logger.warning(f"[STAGER] Invalid/expired token: {token[:10]}")
        return jsonify({"error": "Invalid or expired token"}), 401

    try:
        with open(f"keys/agent{agent_id}.crt", "r") as f:
            crt = f.read()

        with open(f"keys/agent{agent_id}.key", "r") as f:
            key = f.read()

        with open("keys/ca.crt", "r") as f:
            ca_crt = f.read()

        logger.info(f"[STAGER] Downloaded certs for {agent_id}")

        return jsonify({
            "status": "ok",
            "agent_id": agent_id,
            "crt": crt,
            "key": key,
            "ca_crt": ca_crt
        }), 200

    except FileNotFoundError as e:
        logger.error(f"[STAGER] Certificate not found: {e}")
        return jsonify({"error": "Certificates not found"}), 404

    except Exception as e:
        logger.error(f"[STAGER] Error: {e}")
        return jsonify({"error": str(e)}), 500


@stager_bp.route("/stager/generate-token", methods=["POST"])
def generate_stager_token():
    """
    Generate one-time token for stager deployment.
    Requires admin authentication.

    Usage:
        POST /stager/generate-token
        {
            "agent_id": "agent-001",
            "valid_for_minutes": 60
        }
    """
    from middleware.auth import require_token

    # Check admin authentication
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.json

    agent_id = data.get("agent_id")
    valid_for_minutes = data.get("valid_for_minutes", 60)

    if not agent_id:
        return jsonify({"error": "Missing agent_id"}), 400

    try:
        token = generate(agent_id, valid_for_minutes)

        logger.info(f"[STAGER] Admin generated token for {agent_id}")

        return jsonify({
            "status": "ok",
            "agent_id": agent_id,
            "token": token,
            "expires_in_minutes": valid_for_minutes,
            "stager_command": f"python stager.py {token}"
        }), 200

    except Exception as e:
        logger.error(f"[STAGER] Error generating token: {e}")
        return jsonify({"error": str(e)}), 500