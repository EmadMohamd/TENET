import requests
from PIL import ImageGrab
import uuid
from datetime import datetime
SERVER_URL = "http://localhost:5000"
UPLOAD_ENDPOINT = "/upload"
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
            response = requests.post(SERVER_URL + UPLOAD_ENDPOINT, files=files)
            print(response.status_code, response.text)

    except Exception as e:
        print(f"[!] Upload error: {e}")