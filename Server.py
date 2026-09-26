import socket
import threading

HOST = "0.0.0.0"
PORT = 12145

clients = {}       # username -> connection
clients_pfp = {}   # username -> base64 png string (last known pfp)
clients_lock = threading.Lock()


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
    if message.startswith("AUTH:"):
        username = message.split(":", 1)[1].strip()
        with clients_lock:
            clients[username] = connection
            existing_pfps = dict(clients_pfp)  # snapshot to send to the new client
        print(f"[AUTH] {username} connected from {address}")

        # Catch the new client up on everyone's current pfp
        for other_user, b64 in existing_pfps.items():
            try:
                connection.sendall(f"PFP:{other_user}:{b64}\n".encode('utf-8'))
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


def start_server():
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