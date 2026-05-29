# services/stager_token.py
"""
One-time token management for stager downloads.
"""

import secrets, time, threading
from datetime import datetime, timezone, timedelta
from database import get_db


def generate(agent_id, valid_for_minutes=60):
    """
    Generate a one-time token for an agent.

    Args:
        agent_id: The agent to generate token for
        valid_for_minutes: How long token is valid (default 1 hour)

    Returns:
        token string
    """
    token = secrets.token_urlsafe(32)

    db = get_db()
    db.execute("""
        INSERT INTO stager_tokens (token, agent_id, expires_at, used)
        VALUES (?, ?, ?, 0)
    """, (
        token,
        agent_id,
        (datetime.now(timezone.utc) + timedelta(minutes=valid_for_minutes)).isoformat()
    ))
    db.commit()

    print(f"[STAGER] Generated token for {agent_id}: {token[:10]}...")
    return token


def verify(token):
    """
    Verify token is valid (not used, not expired).

    Returns:
        agent_id if valid, None if invalid
    """
    db = get_db()

    row = db.execute("""
        SELECT agent_id, expires_at, used
        FROM stager_tokens
        WHERE token = ?
    """, (token,)).fetchone()

    if not row:
        return None

    agent_id, expires_at, used = row

    # Check if already used
    if used:
        return None

    # Check if expired
    expiry = datetime.fromisoformat(expires_at)
    if datetime.now(timezone.utc) > expiry:
        return None

    return agent_id


def consume(token):
    """
    Mark token as used (can only be called once per token).

    Returns:
        agent_id if successful, None if token invalid
    """
    agent_id = verify(token)

    if not agent_id:
        return None

    db = get_db()
    db.execute("""
        UPDATE stager_tokens
        SET used = 1
        WHERE token = ?
    """, (token,))
    db.commit()

    print(f"[STAGER] Token consumed for {agent_id}")
    return agent_id


def cleanup_expired():
    """Delete expired tokens (cleanup)."""
    db = get_db()

    db.execute("""
        DELETE FROM stager_tokens
        WHERE expires_at < ?
    """, (datetime.now(timezone.utc).isoformat(),))

    db.commit()


def start_periodic_cleanup(app, interval_seconds=3600):
    """Runs a continuous loop in the background to clean up expired tokens."""

    def cleanup_loop():
        while True:
            try:
                print("[CLEANUP] Running expired token cleanup...")
                # Establish application context so database connections work inside the thread
                with app.app_context():
                    cleanup_expired()
            except Exception as e:
                print(f"[CLEANUP] Error during token cleanup: {e}")

            # Wait for the specified interval (e.g., 1 hour) before running again
            time.sleep(interval_seconds)

    # daemon=True ensures the thread exits when the main application stops
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()