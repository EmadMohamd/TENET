import requests
from PIL import ImageGrab

SERVER_URL = "http://localhost:5000"
UPLOAD_ENDPOINT = "/upload"

def run():
    # Take screenshot
    screenshot = ImageGrab.grab()
    screenshot.save("screenshot.png")
    screenshot.close()

    # Upload screenshot
    try:
        with open("screenshot.png", "rb") as file:
            files = {"file": file}
            response = requests.post(SERVER_URL + UPLOAD_ENDPOINT, files=files)
            print(response.status_code, response.text)

    except Exception as e:
        print(f"[!] Upload error: {e}")