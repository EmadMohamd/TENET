from datetime import datetime, timezone
import requests as http_requests

from config import BOT_TOKEN, CHAT_ID
from database import get_db

TELEGRAM_MAX_LENGTH = 4000  # Kept under 4096 to account for headers/formatting


def send_telegram_logs():
    """
    Sends all unsent logs to the configured Telegram bot in chunks,
    then marks sent logs as sent in the DB.
    """
    db = get_db()
    rows = db.execute("SELECT * FROM logs WHERE sent = 0").fetchall()

    if not rows:
        return

    logs = [dict(row) for row in rows]
    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = f"LOGS FOR {current_time}:\n"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    current_chunk = header
    current_ids = []

    for log in logs:
        log_line = f"[{log.get('timestamp', '')}] {log.get('log_message', '')}\n"

        # If adding this line exceeds the limit, send the current chunk first
        if len(current_chunk) + len(log_line) > TELEGRAM_MAX_LENGTH:
            if current_ids:
                _send_chunk(db, url, current_chunk, current_ids)
            # Reset for next batch
            current_chunk = header + log_line
            current_ids = [log["log_id"]]
        else:
            current_chunk += log_line
            current_ids.append(log["log_id"])

    # Send any remaining logs
    if current_ids:
        _send_chunk(db, url, current_chunk, current_ids)


def _send_chunk(db, url, text, ids_to_update):
    payload = {"chat_id": CHAT_ID, "text": text}
    resp = http_requests.post(url, data=payload)

    if resp.status_code == 200:
        placeholders = ", ".join(["?"] * len(ids_to_update))
        db.execute(
            f"UPDATE logs SET sent = 1 WHERE log_id IN ({placeholders})",
            ids_to_update
        )
        db.commit()
        print(f"[telegram] Batch of {len(ids_to_update)} logs sent.")
    else:
        print(f"[telegram] Failed to send batch: {resp.text}")


