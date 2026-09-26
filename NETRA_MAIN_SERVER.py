import socket
import threading
import json
import os
import base64
import hashlib
import secrets
import uuid
import time
import re
from datetime import datetime, timezone

HOST = "0.0.0.0"
PORT = 12145
VOICE_PORT = 12146
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "netra_main_accounts.json")
SERVERS_FILE = os.path.join(BASE_DIR, "netra_servers.json")
CHAT_LOG_FILE = os.path.join(BASE_DIR, "netra_chat_log.json")
MAX_HISTORY = 200
TEXT_CHANNELS = ["general-chat", "random"]

lock = threading.RLock()
accounts = {}
username_map = {}
servers = {}
clients = {}              # username -> socket
clients_lock = threading.RLock()
voice_users = set()
voice_lock = threading.RLock()
# UDP voice relay: client UDP address -> username. Audio is never stored.
voice_peers = {}
voice_udp_lock = threading.RLock()
chat_log = {"general-chat": [], "random": [], "dms": {}}
chat_lock = threading.RLock()


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
        return value
    except Exception:
        return default


def load():
    global accounts, username_map, servers, chat_log
    raw = load_json(ACCOUNTS_FILE, {})
    accounts = raw if isinstance(raw, dict) else {}
    username_map = {
        str(v.get("username_normalized", v.get("username", "")).casefold()): k
        for k, v in accounts.items()
        if isinstance(v, dict) and v.get("username")
    }
    raw_servers = load_json(SERVERS_FILE, {})
    servers = raw_servers if isinstance(raw_servers, dict) else {}
    raw_chat = load_json(CHAT_LOG_FILE, {})
    if isinstance(raw_chat, dict):
        chat_log = raw_chat
    else:
        chat_log = {}
    for channel in TEXT_CHANNELS:
        if not isinstance(chat_log.get(channel), list):
            chat_log[channel] = []
    if not isinstance(chat_log.get("dms"), dict):
        chat_log["dms"] = {}


def save_accounts():
    tmp = ACCOUNTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ACCOUNTS_FILE)


def save_servers():
    tmp = SERVERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(servers, f, indent=2)
    os.replace(tmp, SERVERS_FILE)


def save_chat():
    tmp = CHAT_LOG_FILE + ".tmp"
    with chat_lock:
        data = {
            "general-chat": chat_log.get("general-chat", [])[-MAX_HISTORY:],
            "random": chat_log.get("random", [])[-MAX_HISTORY:],
            "dms": {k: v[-MAX_HISTORY:] for k, v in chat_log.get("dms", {}).items()},
        }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CHAT_LOG_FILE)


def valid_name(n):
    return 2 <= len(n) <= 24 and n == n.strip() and bool(re.fullmatch(r"[A-Za-z0-9_\- ]+", n))


def pw_hash(password, salt=None):
    salt = base64.b64decode(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180000)
    return base64.b64encode(salt).decode(), base64.b64encode(digest).decode()


def auth(action, name, password):
    norm = name.casefold()
    if not valid_name(name):
        return None, "Username must be 2-24 characters using letters, numbers, spaces, _ or -"
    if not 6 <= len(password) <= 128:
        return None, "Password must be 6-128 characters"
    with lock:
        aid = username_map.get(norm)
        if action == "REGISTER":
            if aid:
                return None, "That username is already registered"
            aid = uuid.uuid4().hex
            salt, digest = pw_hash(password)
            accounts[aid] = {
                "username": name,
                "username_normalized": norm,
                "password_salt": salt,
                "password_hash": digest,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "Online",
                "custom_status": "",
                "pfp": "",
            }
            username_map[norm] = aid
            save_accounts()
            return aid, None
        if not aid:
            return None, "No account exists with that username"
        rec = accounts[aid]
        _, digest = pw_hash(password, rec.get("password_salt"))
        if not secrets.compare_digest(digest, rec.get("password_hash", "")):
            return None, "Incorrect password"
        return aid, None


def send_line(conn, line):
    try:
        conn.sendall((line.rstrip("\n") + "\n").encode("utf-8"))
        return True
    except Exception:
        return False


def broadcast(line):
    encoded = (line.rstrip("\n") + "\n").encode("utf-8")
    with clients_lock:
        targets = list(clients.values())
    dead = []
    for conn in targets:
        try:
            conn.sendall(encoded)
        except Exception:
            dead.append(conn)
    return dead


def dm_key(a, b):
    return "|".join(sorted([a, b], key=str.casefold))


def send_presence_lists():
    with lock:
        all_names = sorted([str(v.get("username", "")) for v in accounts.values() if v.get("username")], key=str.lower)
    with clients_lock:
        online_names = sorted(clients.keys(), key=str.lower)
    broadcast("USERS:" + ",".join(all_names))
    broadcast("ONLINE:" + ",".join(online_names))


def send_voice_list():
    with voice_lock:
        names = sorted(voice_users, key=str.lower)
    broadcast("VOICEUSERS:" + ",".join(names))



def voice_udp_loop():
    """Relay raw 16 kHz PCM packets between clients in the voice channel."""
    global voice_peers
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.bind((HOST, VOICE_PORT))
    udp.settimeout(1.0)
    print(f"NETRA VOICE UDP listening on {HOST}:{VOICE_PORT}")

    while True:
        try:
            data, addr = udp.recvfrom(65535)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"VOICE UDP receive error: {e}")
            continue

        if not data:
            continue

        # Control packets are tiny UTF-8 messages; all other packets are PCM.
        if data.startswith(b"REGISTER:"):
            try:
                username = data.split(b":", 1)[1].decode("utf-8", "strict").strip()
            except Exception:
                continue
            if username:
                with voice_udp_lock:
                    # Remove an old endpoint for the same username.
                    for old_addr, old_user in list(voice_peers.items()):
                        if old_user == username and old_addr != addr:
                            voice_peers.pop(old_addr, None)
                    voice_peers[addr] = username
            continue

        if data.startswith(b"UNREGISTER:"):
            try:
                username = data.split(b":", 1)[1].decode("utf-8", "strict").strip()
            except Exception:
                username = ""
            with voice_udp_lock:
                if username:
                    for peer_addr, peer_user in list(voice_peers.items()):
                        if peer_user == username:
                            voice_peers.pop(peer_addr, None)
                else:
                    voice_peers.pop(addr, None)
            continue

        # Any normal packet proves the client's UDP mapping is still alive.
        with voice_udp_lock:
            sender = voice_peers.get(addr)
            if sender is None:
                continue
            targets = [peer_addr for peer_addr, peer_user in voice_peers.items()
                       if peer_user != sender]

        for peer_addr in targets:
            try:
                udp.sendto(data, peer_addr)
            except OSError:
                pass



def send_history(conn, username):
    with chat_lock:
        for channel in TEXT_CHANNELS:
            for entry in chat_log.get(channel, [])[-MAX_HISTORY:]:
                send_line(conn, f"HIST_CHANNEL:{channel}:{entry.get('sender','')}:{entry.get('text','')}")
        for key, entries in chat_log.get("dms", {}).items():
            if username not in key.split("|"):
                continue
            parts = key.split("|", 1)
            if len(parts) != 2:
                continue
            partner = parts[0] if parts[1] == username else parts[1]
            for entry in entries[-MAX_HISTORY:]:
                send_line(conn, f"HIST_DM:{partner}:{entry.get('sender','')}:{entry.get('text','')}")


def send_all_pfps(conn):
    with lock:
        pfps = [(str(v.get("username", "")), v.get("pfp", "")) for v in accounts.values() if v.get("username") and v.get("pfp")]
    for name, b64 in pfps:
        send_line(conn, f"PFP:{name}:{b64}")


def finish_auth(conn, username, aid):
    # Replace an older connection for the same account safely.
    old_conn = None
    with clients_lock:
        old_conn = clients.get(username)
        clients[username] = conn
    if old_conn is not None and old_conn is not conn:
        try:
            old_conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            old_conn.close()
        except Exception:
            pass

    with lock:
        accounts[aid]["status"] = "Online"

    send_line(conn, f"AUTH_OK:{aid}:{username}")
    send_history(conn, username)
    send_line(conn, "READY")
    send_all_pfps(conn)
    send_presence_lists()
    send_voice_list()
    return username


def handle_line(conn, username, line):
    if line.startswith("LOGIN:") or line.startswith("REGISTER:"):
        parts = line.split(":", 2)
        if len(parts) != 3:
            send_line(conn, "AUTH_FAIL:Invalid authentication request")
            return username
        try:
            password = base64.b64decode(parts[2]).decode("utf-8")
        except Exception:
            send_line(conn, "AUTH_FAIL:Invalid password data")
            return username
        aid, err = auth(parts[0], parts[1].strip(), password)
        if not aid:
            send_line(conn, "AUTH_FAIL:" + err)
            return username
        username = accounts[aid]["username"]
        return finish_auth(conn, username, aid)

    if not username:
        directory_response = process_directory_command(line)
        if directory_response is not None:
            send_line(conn, directory_response)
        return username

    if line.startswith("PFP:"):
        b64 = line.split(":", 1)[1].strip()
        # Basic sanity check; reject absurdly large payloads.
        if len(b64) <= 2_000_000:
            with lock:
                aid = username_map.get(username.casefold())
                if aid in accounts:
                    accounts[aid]["pfp"] = b64
                    save_accounts()
            broadcast(f"PFP:{username}:{b64}")
        return username

    if line.startswith("GLOBAL:"):
        text = line.split(":", 1)[1]
        with chat_lock:
            chat_log.setdefault("general-chat", []).append({"sender": username, "text": text})
            chat_log["general-chat"] = chat_log["general-chat"][-MAX_HISTORY:]
            save_chat()
        broadcast(f"GLOBAL:{username}:{text}")
        return username

    if line.startswith("CHANNEL:"):
        parts = line.split(":", 2)
        if len(parts) == 3:
            channel, text = parts[1].strip(), parts[2]
            if channel not in TEXT_CHANNELS:
                send_line(conn, "ERROR:That text channel does not exist")
                return username
            with chat_lock:
                chat_log.setdefault(channel, []).append({"sender": username, "text": text})
                chat_log[channel] = chat_log[channel][-MAX_HISTORY:]
                save_chat()
            broadcast(f"CHANNEL:{channel}:{username}:{text}")
        return username

    if line.startswith("DM:"):
        parts = line.split(":", 2)
        if len(parts) == 3:
            target, text = parts[1], parts[2]
            key = dm_key(username, target)
            with chat_lock:
                chat_log["dms"].setdefault(key, []).append({"sender": username, "text": text})
                chat_log["dms"][key] = chat_log["dms"][key][-MAX_HISTORY:]
                save_chat()
            with clients_lock:
                target_conn = clients.get(target)
                own_conn = clients.get(username)
            if target_conn:
                send_line(target_conn, f"DM:{username}:{username}:{text}")
            if own_conn:
                send_line(own_conn, f"DM:{target}:{username}:{text}")
        return username

    if line.startswith("VOICEJOIN:"):
        with voice_lock:
            voice_users.add(username)
        send_voice_list()
        return username

    if line.startswith("VOICELEAVE:"):
        with voice_lock:
            voice_users.discard(username)
        send_voice_list()
        return username

    if line.startswith("RENAME:"):
        new_name = line.split(":", 1)[1].strip()
        with lock:
            aid = username_map.get(username.casefold())
            if not aid:
                send_line(conn, "RENAME_FAIL:Account not found")
                return username
            if not valid_name(new_name):
                send_line(conn, "RENAME_FAIL:Invalid username")
                return username
            norm = new_name.casefold()
            other = username_map.get(norm)
            if other and other != aid:
                send_line(conn, "RENAME_FAIL:That username is already taken")
                return username
            old = username
            username_map.pop(old.casefold(), None)
            username_map[norm] = aid
            accounts[aid]["username"] = new_name
            accounts[aid]["username_normalized"] = norm
            save_accounts()
        with clients_lock:
            if clients.get(old) is conn:
                clients.pop(old, None)
                clients[new_name] = conn
        with voice_lock:
            if old in voice_users:
                voice_users.discard(old)
                voice_users.add(new_name)
        send_line(conn, f"RENAME_OK:{old}:{new_name}")
        broadcast(f"USER_RENAMED:{old}:{new_name}")
        send_presence_lists()
        send_voice_list()
        return new_name

    if line.startswith("SETSTATUS:"):
        parts = line.split(":", 3)
        if len(parts) >= 3:
            with lock:
                aid = username_map.get(username.casefold())
                if aid in accounts:
                    accounts[aid]["status"] = parts[1]
                    accounts[aid]["custom_status"] = parts[2] if len(parts) > 2 else ""
                    save_accounts()
        return username

    return username


def handle(conn, addr):
    username = None
    buf = ""
    try:
        while True:
            data = conn.recv(65536)
            if not data:
                break
            buf += data.decode("utf-8")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if not line:
                    continue
                username = handle_line(conn, username, line)
    except Exception as e:
        print("[MAIN ERROR]", addr, username, e)
    finally:
        if username:
            removed = False
            with clients_lock:
                if clients.get(username) is conn:
                    clients.pop(username, None)
                    removed = True
            with voice_lock:
                was_voice = username in voice_users
                voice_users.discard(username)
            if removed:
                print(f"[DISCONNECT] {username} from {addr}")
                send_presence_lists()
            if was_voice:
                send_voice_list()
        try:
            conn.close()
        except Exception:
            pass


def process_directory_command(line):
    # Kept for NETRA_SERVER.py compatibility / server-directory clients.
    parts = line.split(":", 3)
    cmd = parts[0]
    if cmd == "USER_LIST":
        with lock:
            names = sorted([v.get("username", "") for v in accounts.values() if v.get("username")], key=str.lower)
        return "USERS:" + ",".join(names)
    if cmd == "SERVER_REGISTER" and len(parts) == 4:
        sid, name, hostport = parts[1], parts[2], parts[3]
        with lock:
            servers[sid] = {"name": name, "host": hostport, "last_seen": time.time()}
            save_servers()
        return "OK"
    if cmd == "SERVER_LIST":
        with lock:
            now = time.time()
            live = {k: v for k, v in servers.items() if now - v.get("last_seen", 0) < 120}
        return "SERVERS:" + json.dumps(live, separators=(",", ":"))
    if cmd == "PROFILE" and len(parts) == 2:
        aid = parts[1]
        with lock:
            if aid not in accounts:
                return "PROFILE_FAIL:unknown"
            r = accounts[aid]
            return "PROFILE:" + json.dumps({
                "username": r.get("username", ""),
                "status": r.get("status", "Online"),
                "custom_status": r.get("custom_status", ""),
                "created_at": r.get("created_at", ""),
            }, separators=(",", ":"))
    return None


# Directory requests are short-lived connections from other NETRA services.
def directory_handle(conn, addr, first_line):
    out = process_directory_command(first_line)
    if out is not None:
        send_line(conn, out)
        return True
    return False


load()
print(f"NETRA MAIN SERVER listening on {HOST}:{PORT}")
print("Central accounts + persistent chat + presence + PFP storage enabled.")
threading.Thread(target=voice_udp_loop, daemon=True).start()

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(100)
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()
