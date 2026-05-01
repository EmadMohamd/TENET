import functools
from datetime import datetime
from flask import request, jsonify, session, redirect, url_for, abort
from database import get_db


def require_mtls(f):
    """
    Decorator: require mTLS authentication.
    Nginx sets X-SSL-Verified and X-Client-Cert-CN after a successful
    TLS handshake. Flask trusts these headers because Flask is only
    reachable via Nginx (bound to 127.0.0.1).
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        verified   = request.headers.get("X-SSL-Verified")
        agent_cert = request.headers.get("X-Client-Cert-CN")

        if verified != "SUCCESS":
            abort(403, "Client certificate verification failed")
        if not agent_cert:
            abort(403, "No client certificate identity")

        request.agent_cert        = agent_cert
        request.agent_dn          = request.headers.get("X-Client-Cert-DN")
        request.agent_fingerprint = request.headers.get("X-Client-Fingerprint")

        return f(*args, **kwargs)
    return wrapper


def require_token(role=None):
    """
    Decorator: validate bearer token from the TOKEN header.
    If role="admin" is passed, the token check is skipped entirely
    (session-based admin auth applies instead).
    """
    def wrapper(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            # Admin routes are protected by session, not token
            if role == "admin":
                request.agent_id = None
                request.role     = "admin"
                return f(*args, **kwargs)

            token = request.headers.get("TOKEN")
            if not token:
                return jsonify({"error": "Missing token"}), 401

            db  = get_db()
            row = db.execute("""
                SELECT t.agent_id, t.expiry, u.role
                FROM tokens t
                JOIN users u ON t.username = u.username
                WHERE t.token = ?
            """, (token,)).fetchone()

            if not row:
                return jsonify({"error": "Invalid token"}), 403
            if datetime.fromisoformat(row["expiry"]) < datetime.utcnow():
                return jsonify({"error": "Token expired"}), 403
            if role and row["role"] != role:
                return jsonify({"error": "Forbidden"}), 403

            request.agent_id = row["agent_id"]
            request.role     = row["role"]

            return f(*args, **kwargs)
        return decorated
    return wrapper