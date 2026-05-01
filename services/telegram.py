from datetime import datetime, timezone
import requests as http_requests

from config import BOT_TOKEN, CHAT_ID
from database import get_db


def send_telegram_logs():
    """
    Sends all unsent logs to the configured Telegram bot,
    then marks them as sent in the DB.
    """
    db   = get_db()
    rows = db.execute("SELECT * FROM logs WHERE sent = 0").fetchall()

    if not rows:
        return

    logs           = [dict(row) for row in rows]
    ids_to_update  = [log["log_id"] for log in logs]

    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = (
        f"LOGS FOR {current_time}:\n"
        + "\n".join(
            f"[{log.get('timestamp', '')}] {log.get('log_message', '')}"
            for log in logs
        )
    )

    url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    resp    = http_requests.post(url, data=payload)

    if resp.status_code == 200:
        placeholders = ", ".join(["?"] * len(ids_to_update))
        db.execute(
            f"UPDATE logs SET sent = 1 WHERE log_id IN ({placeholders})",
            ids_to_update
        )
        db.commit()
        print("[telegram] Logs sent.")
    else:
        print(f"[telegram] Failed to send: {resp.text}")