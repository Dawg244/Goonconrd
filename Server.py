import socket
import threading

HOST = "0.0.0.0"
PORT = 12145
VOICE_PORT = 12146

clients = {}        # username -> connection
clients_pfp = {}     # username -> base64 png string (last known pfp)
server_icon_b64 = None  # base64 png string for the shared "server" icon, or None
clients_lock = threading.Lock()

voice_clients = {}   # addr -> username
voice_lock = threading.Lock()


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
        connection.close()


def process_line(message, username, connection, address):
    global server_icon_b64

    if message.startswith("AUTH:"):
        username = message.split(":", 1)[1].strip()
        with clients_lock:
            clients[username] = connection
            existing_pfps = dict(clients_pfp)
            current_server_icon = server_icon_b64
        print(f"[AUTH] {username} connected from {address}")

        # Catch the new client up on everyone's current pfp...
        for other_user, b64 in existing_pfps.items():
            try:
                connection.sendall(f"PFP:{other_user}:{b64}\n".encode('utf-8'))
            except Exception:
                pass
        # ...and the current shared server icon, if one has been set.
        if current_server_icon:
            try:
                connection.sendall(f"SERVERPFP:{current_server_icon}\n".encode('utf-8'))
            except Exception:
                pass

        broadcast_user_list()

    elif message.startswith("GLOBAL:"):
        payload = message.split(":", 1)[1]
        broadcast(f"GLOBAL:{username}:{payload}\n")

    elif message.startswith("DM:"):
        parts = message.split(":", 2)
        if len(parts) == 3:
            target_user = parts[1]
            payload = parts[2]
            with clients_lock:
                target_conn = clients.get(target_user)
                self_conn = clients.get(username)
            if target_conn:
                try:
                    target_conn.sendall(f"DM:{username}:{payload}\n".encode('utf-8'))
                except Exception:
                    pass
            if self_conn:
                try:
                    self_conn.sendall(f"DM:{target_user}:{payload}\n".encode('utf-8'))
                except Exception:
                    pass

    elif message.startswith("PFP:"):
        # Client is uploading/updating their own profile picture.
        b64_payload = message.split(":", 1)[1]
        if username:
            with clients_lock:
                clients_pfp[username] = b64_payload
            broadcast(f"PFP:{username}:{b64_payload}\n")

    elif message.startswith("SERVERPFP:"):
        # Client is uploading/updating the shared server icon.
        b64_payload = message.split(":", 1)[1]
        with clients_lock:
            server_icon_b64 = b64_payload
        broadcast(f"SERVERPFP:{b64_payload}\n")

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
    user_list_str = "USERS:" + ",".join(names) + "\n"
    broadcast(user_list_str)


# ---------------- Voice UDP relay ----------------
# Very small "everyone hears everyone" relay: clients REGISTER their
# address, then any audio packet coming from a known address gets
# forwarded to every other known address. No mixing, no encoding.

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
            print(f"[VOICE] {username} joined voice from {addr}")
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