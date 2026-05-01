from collections import Counter
from datetime import datetime, timezone

import requests as http_requests

from config import AGENT_ONLINE_TIMEOUT
from database import get_db


def get_location(ip: str):
    """
    Returns (lat, lon, city, country) for an IP, or None on failure.
    Uses ip-api.com (free, no key needed).
    """
    try:
        resp = http_requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        data = resp.json()
        if data["status"] == "success":
            return data["lat"], data["lon"], data["city"], data["country"]
    except Exception:
        pass
    return None


def get_online_offline_counts() -> dict:
    """Returns {"online": N, "offline": N} for all agents in the DB."""
    db       = get_db()
    rows     = db.execute("SELECT id, last_seen FROM agents").fetchall()
    now      = datetime.now(timezone.utc)
    statuses = []

    for row in rows:
        ts_str = row[1]
        if not ts_str:
            statuses.append("offline")
            continue
        try:
            last = datetime.fromisoformat(ts_str)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            statuses.append(
                "online" if (now - last).total_seconds() <= AGENT_ONLINE_TIMEOUT
                else "offline"
            )
        except ValueError:
            statuses.append("offline")

    counts = Counter(statuses)
    return {"online": counts.get("online", 0), "offline": counts.get("offline", 0)}