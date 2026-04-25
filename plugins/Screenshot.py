import requests
from PIL import ImageGrab
from datetime import datetime
from pathlib import Path
SERVER_URL = "https://127.0.0.1"
BASE_DIR = Path.cwd()
UPLOAD_ENDPOINT = "/upload"
CLIENT_CRT = BASE_DIR / "keys" / "agent1.crt"
CLIENT_KEY = BASE_DIR / "keys" / "agent1.key"
CA_CERT = BASE_DIR / "keys" / "ca.crt"
now = datetime.now()
# Format: YYYY-MM-DD_HH-MM-SS
filename = now.strftime("%Y-%m-%d_%H-%M-%S") + ".png"


def run():
    # Take screenshot
    screenshot = ImageGrab.grab()
    screenshot.save(filename)
    screenshot.close()

    # Upload screenshot
    try:
        with open(filename, "rb") as file:
            files = {"file": file}
            response = requests.post(SERVER_URL + UPLOAD_ENDPOINT, files=files,cert=(CLIENT_CRT,CLIENT_KEY), verify=CA_CERT)
            print(response.status_code, response.text)

    except Exception as e:
        print(f"[!] Upload error: {e}")