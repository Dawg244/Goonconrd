import socket
import threading
import os
import json

HOST = "0.0.0.0"
PORT = 12145
VOICE_PORT = 12146

LOG_FILE = "chat_log.json"
MAX_HISTORY_PER_CHANNEL = 200

clients = {}        # username -> connection
clients_pfp = {}     # username -> base64 png string (last known pfp)
server_icon_b64 = None  # base64 png string for the shared "server" icon, or None
clients_lock = threading.Lock()

# "Who's in voice" for display purposes - driven over TCP so it doesn't
# depend on UDP port forwarding being set up correctly.
voice_presence_users = set()
presence_lock = threading.Lock()

# Actual audio relay bookkeeping (UDP) - separate from the display list above.
voice_clients = {}   # addr -> username
voice_lock = threading.Lock()

log_lock = threading.Lock()
save_timer = None
save_timer_lock = threading.Lock()


def schedule_log_save():
    global save_timer
    with save_timer_lock:
        if save_timer is not None and save_timer.is_alive():
            return
        save_timer = threading.Timer(0.75, save_message_log)
        save_timer.daemon = True
        save_timer.start()


def load_message_log():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("global", [])
                data.setdefault("dms", {})
                return data
        except Exception as e:
            print(f"[WARN] Could not read {LOG_FILE}: {e}")
    return {"global": [], "dms": {}}


message_log = load_message_log()


def save_message_log():
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(message_log, f)
    except Exception as e:
        print(f"[ERROR] Could not save chat log: {e}")


def dm_key(user_a, user_b):
    return "|".join(sorted([user_a, user_b]))


# ---------------- Text / chat TCP server ----------------

def handle_client(connection, address):
    username = None
    buffer = ""  # accumulates partial data between recv() calls
    try:
        while True:
            data = connection.recv(65536)
            if not data:
                break

            buffer += data.decode('utf-8')

            # A recv() can contain 0, 1, or several complete lines.
            # Process every complete line (ending in \n) and keep any
            # trailing partial line in the buffer for next time.
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line:
                    continue
                username = process_line(line, username, connection, address)

    except Exception as e:
        print(f"[ERROR] Exception with client {username or address}: {e}")
    finally:
        if username:
            with clients_lock:
                if username in clients:
                    del clients[username]
            print(f"[DISCONNECT] {username} left.")
            broadcast_user_list()

            # Clean up voice presence / stale audio registration for this user
            removed_presence = False
            with presence_lock:
                if username in voice_presence_users:
                    voice_presence_users.discard(username)
                    removed_presence = True
            if removed_presence:
                broadcast_voice_user_list()

            with voice_lock:
                stale_addrs = [a for a, u in voice_clients.items() if u == username]
                for a in stale_addrs:
                    del voice_clients[a]
        connection.close()


def process_line(message, username, connection, address):
    global server_icon_b64

    if message.startswith("AUTH:"):
        username = message.split(":", 1)[1].strip()
        with clients_lock:
            clients[username] = connection
            existing_pfps = dict(clients_pfp)
            current_server_icon = server_icon_b64
        with presence_lock:
            current_voice_names = list(voice_presence_users)
        with log_lock:
            global_hist = list(message_log["global"])
            dm_hist_items = [(k, list(v)) for k, v in message_log["dms"].items() if username in k.split("|")]

        print(f"[AUTH] {username} connected from {address}")

        # Replay chat history first...
        for entry in global_hist:
            try:
                connection.sendall(f"HIST_GLOBAL:{entry['sender']}:{entry['text']}\n".encode('utf-8'))
            except Exception:
                pass
        for key, entries in dm_hist_items:
            parts = key.split("|")
            partner = parts[0] if parts[1] == username else parts[1]
            for entry in entries:
                try:
                    connection.sendall(f"HIST_DM:{partner}:{entry['sender']}:{entry['text']}\n".encode('utf-8'))
                except Exception:
                    pass

        # Signal that history is complete. The client waits for this before
        # building hundreds of GUI widgets, which keeps login/startup responsive.
        try:
            connection.sendall(b"READY\n")
        except Exception:
            pass

        # ...then catch the new client up on everyone's current pfp...
        for other_user, b64 in existing_pfps.items():
            try:
                connection.sendall(f"PFP:{other_user}:{b64}\n".encode('utf-8'))
            except Exception:
                pass
        # ...the shared server icon, if set...
        if current_server_icon:
            try:
                connection.sendall(f"SERVERPFP:{current_server_icon}\n".encode('utf-8'))
            except Exception:
                pass
        # ...and who's currently in voice.
        try:
            connection.sendall(("VOICEUSERS:" + ",".join(current_voice_names) + "\n").encode('utf-8'))
        except Exception:
            pass

        broadcast_user_list()

    elif message.startswith("GLOBAL:"):
        payload = message.split(":", 1)[1]
        with log_lock:
            message_log["global"].append({"sender": username, "text": payload})
            message_log["global"] = message_log["global"][-MAX_HISTORY_PER_CHANNEL:]
            schedule_log_save()
        broadcast(f"GLOBAL:{username}:{payload}\n")

    elif message.startswith("DM:"):
        parts = message.split(":", 2)
        if len(parts) == 3:
            target_user = parts[1]
            payload = parts[2]

            with log_lock:
                key = dm_key(username, target_user)
                message_log["dms"].setdefault(key, []).append({"sender": username, "text": payload})
                message_log["dms"][key] = message_log["dms"][key][-MAX_HISTORY_PER_CHANNEL:]
                schedule_log_save()

            with clients_lock:
                target_conn = clients.get(target_user)
                self_conn = clients.get(username)
            if target_conn:
                try:
                    target_conn.sendall(f"DM:{username}:{username}:{payload}\n".encode('utf-8'))
                except Exception:
                    pass
            if self_conn:
                try:
                    self_conn.sendall(f"DM:{target_user}:{username}:{payload}\n".encode('utf-8'))
                except Exception:
                    pass

    elif message.startswith("PFP:"):
        b64_payload = message.split(":", 1)[1]
        if username:
            with clients_lock:
                clients_pfp[username] = b64_payload
            broadcast(f"PFP:{username}:{b64_payload}\n")

    elif message.startswith("SERVERPFP:"):
        b64_payload = message.split(":", 1)[1]
        with clients_lock:
            server_icon_b64 = b64_payload
        broadcast(f"SERVERPFP:{b64_payload}\n")

    elif message.startswith("VOICEJOIN:"):
        if username:
            with presence_lock:
                voice_presence_users.add(username)
            broadcast_voice_user_list()

    elif message.startswith("VOICELEAVE:"):
        if username:
            with presence_lock:
                voice_presence_users.discard(username)
            broadcast_voice_user_list()

    return username


def broadcast(message_str):
    """message_str must already end with \\n."""
    encoded = message_str.encode('utf-8')
    with clients_lock:
        targets = list(clients.values())
    for conn in targets:
        try:
            conn.sendall(encoded)
        except Exception:
            pass


def broadcast_user_list():
    with clients_lock:
        names = list(clients.keys())
    user_list_str = "USERS:" + ",".join(sorted(names)) + "\n"
    broadcast(user_list_str)


def broadcast_voice_user_list():
    with presence_lock:
        names = list(voice_presence_users)
    voice_list_str = "VOICEUSERS:" + ",".join(sorted(names)) + "\n"
    broadcast(voice_list_str)


# ---------------- Voice UDP relay (audio only, not presence) ----------------

def voice_relay():
    voice_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    voice_sock.bind((HOST, VOICE_PORT))
    print(f"[*] Voice relay listening on {HOST}:{VOICE_PORT}")
    while True:
        try:
            data, addr = voice_sock.recvfrom(4096)
        except Exception:
            continue

        if data.startswith(b"REGISTER:"):
            username = data.split(b":", 1)[1].decode('utf-8', errors='ignore')
            with voice_lock:
                voice_clients[addr] = username
            print(f"[VOICE] {username} audio-registered from {addr}")
            continue

        if data.startswith(b"UNREGISTER:"):
            with voice_lock:
                voice_clients.pop(addr, None)
            continue

        with voice_lock:
            targets = [a for a in voice_clients if a != addr]
        for target_addr in targets:
            try:
                voice_sock.sendto(data, target_addr)
            except Exception:
                pass


def start_server():
    threading.Thread(target=voice_relay, daemon=True).start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen()
        print(f"[*] Server listening on {HOST}:{PORT}")

        while True:
            connection, address = server_socket.accept()
            threading.Thread(target=handle_client, args=(connection, address), daemon=True).start()


if __name__ == "__main__":
    start_server()