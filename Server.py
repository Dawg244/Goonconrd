import socket
import threading
import os
import json
import hashlib
import secrets
import uuid
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = "0.0.0.0"
PORT = int(os.getenv("NETRA_SERVER_PORT", "12155"))
VOICE_PORT = int(os.getenv("NETRA_VOICE_PORT", "12156"))
MAIN_HOST = os.getenv("NETRA_MAIN_HOST", "108.221.36.120")
MAIN_PORT = int(os.getenv("NETRA_MAIN_PORT", "12145"))
SERVER_ID = os.getenv("NETRA_SERVER_ID", uuid.uuid4().hex)
SERVER_NAME = os.getenv("NETRA_SERVER_NAME", "NETRA Community Server")

LOG_FILE = os.path.join(BASE_DIR, "chat_log.json")
USERS_FILE = os.path.join(BASE_DIR, "netra_users.json")
ACCOUNTS_FILE = os.path.join(BASE_DIR, "netra_accounts.json")
MAX_HISTORY_PER_CHANNEL = 200
TEXT_CHANNELS = ["general-chat", "random"]

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

accounts_lock = threading.RLock()
accounts = {}              # account_id -> account record
username_to_account = {}   # normalized username -> account_id


def normalize_username(name):
    return name.strip().casefold()


def valid_username(name):
    if not 2 <= len(name) <= 24:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_\- ]+", name)) and name.strip() == name


def password_hash(password, salt_hex=None):
    if salt_hex is None:
        salt = secrets.token_bytes(16)
        salt_hex = salt.hex()
    else:
        salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180000)
    return salt_hex, digest.hex()


def load_accounts():
    global accounts, username_to_account
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                accounts = data.get("accounts", {}) if isinstance(data.get("accounts", {}), dict) else {}
        except Exception as e:
            print(f"[WARN] Could not read {ACCOUNTS_FILE}: {e}")

    # Migrate the old username-only user database. Existing names keep their
    # old chat identity and can set a password the first time they register.
    old_users = set()
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                old = json.load(f)
            if isinstance(old, list):
                old_users = {str(x).strip() for x in old if str(x).strip()}
            elif isinstance(old, dict):
                old_users = {str(x).strip() for x in old.keys() if str(x).strip()}
        except Exception:
            pass

    for old_name in old_users:
        norm = normalize_username(old_name)
        if norm not in username_to_account:
            aid = uuid.uuid4().hex
            accounts[aid] = {
                "username": old_name,
                "username_normalized": norm,
                "password_salt": "",
                "password_hash": "",
                "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "legacy": True,
            }

    username_to_account = {}
    for aid, rec in accounts.items():
        name = str(rec.get("username", "")).strip()
        if name:
            rec["username_normalized"] = normalize_username(name)
            username_to_account[rec["username_normalized"]] = aid


def save_accounts():
    tmp = ACCOUNTS_FILE + ".tmp"
    try:
        with accounts_lock:
            payload = {"accounts": accounts}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ACCOUNTS_FILE)
    except Exception as e:
        print(f"[ERROR] Could not save {ACCOUNTS_FILE}: {e}")


def account_for_username(name):
    return username_to_account.get(normalize_username(name))


load_accounts()


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
                data.setdefault("general-chat", data.pop("global", []))
                data.setdefault("random", [])
                data.setdefault("dms", {})
                return data
        except Exception as e:
            print(f"[WARN] Could not read {LOG_FILE}: {e}")
    return {"general-chat": [], "random": [], "dms": {}}


message_log = load_message_log()
# The old NETRA global chat is now the persistent #general-chat channel.
if "general" in message_log and "general-chat" not in message_log:
    message_log["general-chat"] = message_log.pop("general")
if "global" in message_log:
    if message_log["global"] and "general-chat" not in message_log:
        message_log["general-chat"] = message_log.pop("global")
    else:
        message_log.pop("global", None)
message_log.setdefault("general-chat", [])
message_log.setdefault("random", [])


def load_registered_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {str(x) for x in data if str(x).strip()}
            if isinstance(data, dict):
                return {str(x) for x in data.keys() if str(x).strip()}
        except Exception as e:
            print(f"[WARN] Could not read {USERS_FILE}: {e}")
    # Recover names from existing chat history so upgrading does not lose users.
    found = set()
    for entry in message_log.get("general-chat", []):
        if entry.get("sender"):
            found.add(str(entry["sender"]))
    for key, entries in message_log.get("dms", {}).items():
        found.update(x for x in key.split("|") if x)
        for entry in entries:
            if entry.get("sender"):
                found.add(str(entry["sender"]))
    return found


registered_users = load_registered_users()
registered_users_lock = threading.Lock()


def save_registered_users():
    tmp = USERS_FILE + ".tmp"
    try:
        with registered_users_lock:
            data = sorted(registered_users, key=str.lower)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, USERS_FILE)
    except Exception as e:
        print(f"[ERROR] Could not save {USERS_FILE}: {e}")



def save_message_log():
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(message_log, f)
    except Exception as e:
        print(f"[ERROR] Could not save chat log: {e}")


def dm_key(user_a, user_b):
    return "|".join(sorted([user_a, user_b]))



def main_request(line, timeout=8):
    try:
        with socket.create_connection((MAIN_HOST, MAIN_PORT), timeout=timeout) as s:
            s.sendall((line+'\n').encode('utf-8'))
            buf=b''
            while b'\n' not in buf:
                part=s.recv(65536)
                if not part: break
                buf+=part
            return buf.decode('utf-8').strip()
    except Exception as e:
        return f"AUTH_FAIL:Main server unavailable: {e}"

def register_with_main():
    hostport=f"{os.getenv('NETRA_PUBLIC_HOST', MAIN_HOST)}:{PORT}"
    r=main_request(f"SERVER_REGISTER:{SERVER_ID}:{SERVER_NAME}:{hostport}")
    print('[MAIN]',r)

def authenticate_via_main(action, raw_username, encoded_password):
    r=main_request(f"{action}:{raw_username}:{encoded_password}")
    if r.startswith('AUTH_OK:'):
        p=r.split(':',2)
        return True,p[1],p[2],''
    return False,'','',r.split(':',1)[1] if ':' in r else r

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

    # -------- Central account registration / login --------
    if message.startswith("REGISTER:") or message.startswith("LOGIN:"):
        parts = message.split(":", 2)
        if len(parts) != 3:
            connection.sendall(b"AUTH_FAIL:Invalid authentication request\n"); return username
        action, raw_username, encoded_password = parts
        ok, aid, central_name, reason = authenticate_via_main(action, raw_username.strip(), encoded_password)
        if not ok:
            connection.sendall(f"AUTH_FAIL:{reason}\n".encode('utf-8')); return username
        username=central_name
        with accounts_lock:
            accounts.setdefault(aid,{"username":username,"username_normalized":normalize_username(username)})
            username_to_account[normalize_username(username)]=aid
        with clients_lock:
            old_conn=clients.get(username); clients[username]=connection
            existing_pfps=dict(clients_pfp); current_server_icon=server_icon_b64
            online_names=sorted(clients.keys(),key=str.lower)
        if old_conn is not None and old_conn is not connection:
            try: old_conn.shutdown(socket.SHUT_RDWR); old_conn.close()
            except Exception: pass
        with registered_users_lock: registered_users.add(username)
        save_registered_users()
        with presence_lock: current_voice_names=list(voice_presence_users)
        with log_lock:
            channel_histories={ch:list(message_log.get(ch,[])) for ch in TEXT_CHANNELS}
            dm_hist_items=[(k,list(v)) for k,v in message_log['dms'].items() if username in k.split('|')]
        connection.sendall(f"AUTH_OK:{aid}:{username}\n".encode())
        for channel,entries in channel_histories.items():
            for entry in entries:
                connection.sendall(f"HIST_CHANNEL:{channel}:{entry.get('sender','')}:{entry.get('text','')}\n".encode())
        for key,entries in dm_hist_items:
            pp=key.split('|')
            if len(pp)!=2: continue
            partner=pp[0] if pp[1]==username else pp[1]
            for entry in entries:
                connection.sendall(f"HIST_DM:{partner}:{entry.get('sender','')}:{entry.get('text','')}\n".encode())
        connection.sendall(b"READY\n")
        for other_user,b64 in existing_pfps.items():
            try: connection.sendall(f"PFP:{other_user}:{b64}\n".encode())
            except Exception: pass
        if current_server_icon: connection.sendall(f"SERVERPFP:{current_server_icon}\n".encode())
        central_users=main_request("USER_LIST")
        if central_users.startswith("USERS:"):
            all_user_names=[u for u in central_users.split(":",1)[1].split(",") if u]
        else:
            with registered_users_lock: all_user_names=sorted(registered_users,key=str.lower)
        connection.sendall(("USERS:"+",".join(all_user_names)+"\n").encode())
        connection.sendall(("ONLINE:"+",".join(online_names)+"\n").encode())
        connection.sendall(("VOICEUSERS:"+",".join(current_voice_names)+"\n").encode())
        broadcast_user_list(); return username

    if message.startswith("RENAME:"):
        if not username: return username
        new_name=message.split(':',1)[1].strip()
        with accounts_lock:
            aid=account_for_username(username)
        if not aid:
            connection.sendall(b"RENAME_FAIL:Account not found\n"); return username
        resp=main_request(f"RENAME:{aid}:{new_name}")
        if not resp.startswith('RENAME_OK:'):
            connection.sendall((resp+'\n').encode()); return username
        _,old_name,new_name=resp.split(':',2)
        with log_lock:
            old_keys=[k for k in list(message_log['dms'].keys()) if old_name in k.split('|')]
            for old_key in old_keys:
                pp=old_key.split('|')
                if len(pp)!=2: continue
                other=pp[0] if pp[1]==old_name else pp[1]
                nk=dm_key(new_name,other); message_log['dms'].setdefault(nk,[]).extend(message_log['dms'].pop(old_key)); message_log['dms'][nk]=message_log['dms'][nk][-MAX_HISTORY_PER_CHANNEL:]
            schedule_log_save()
        with clients_lock:
            clients.pop(old_name,None); clients[new_name]=connection
            if old_name in clients_pfp: clients_pfp[new_name]=clients_pfp.pop(old_name)
        with registered_users_lock: registered_users.discard(old_name); registered_users.add(new_name)
        with presence_lock:
            if old_name in voice_presence_users: voice_presence_users.discard(old_name); voice_presence_users.add(new_name)
        with voice_lock:
            for addr,who in list(voice_clients.items()):
                if who==old_name: voice_clients[addr]=new_name
        connection.sendall(f"RENAME_OK:{old_name}:{new_name}\n".encode()); broadcast(f"USER_RENAMED:{old_name}:{new_name}\n"); broadcast_user_list(); return new_name

    if not username:
        return username

    if message.startswith("CHANNEL:"):
        parts = message.split(":", 2)
        if len(parts) == 3:
            channel = parts[1].strip()
            payload = parts[2]
            if channel not in TEXT_CHANNELS:
                connection.sendall(b"ERROR:That text channel does not exist\n")
                return username
            with log_lock:
                message_log.setdefault(channel, []).append({"sender": username, "text": payload})
                message_log[channel] = message_log[channel][-MAX_HISTORY_PER_CHANNEL:]
                schedule_log_save()
            broadcast(f"CHANNEL:{channel}:{username}:{payload}\n")

    elif message.startswith("GLOBAL:"):
        # Backwards compatibility with older NETRA clients: route old global
        # messages into #general-chat.
        payload = message.split(":", 1)[1]
        with log_lock:
            message_log.setdefault("general-chat", []).append({"sender": username, "text": payload})
            message_log["general-chat"] = message_log["general-chat"][-MAX_HISTORY_PER_CHANNEL:]
            schedule_log_save()
        broadcast(f"CHANNEL:general-chat:{username}:{payload}\n")

    elif message.startswith("DM:"):
        parts = message.split(":", 2)
        if len(parts) == 3:
            target_user = parts[1]
            payload = parts[2]
            with accounts_lock:
                target_aid = account_for_username(target_user)
            if not target_aid:
                connection.sendall(b"ERROR:That user does not exist\n")
                return username
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

    elif message.startswith("STATUS:"):
        payload=message.split(':',1)[1]
        bits=payload.split(':',1); status=bits[0]; custom=bits[1] if len(bits)>1 else ''
        with clients_lock: 
            targets=list(clients.values())
        # Persist centrally when possible.
        with accounts_lock: aid=account_for_username(username)
        if aid: main_request(f"SETSTATUS:{aid}:{status}:{custom}")
        broadcast(f"STATUS:{username}:{status}:{custom}\n")

    elif message.startswith("TYPING:"):
        room=message.split(':',1)[1]
        broadcast(f"TYPING:{username}:{room}\n")

    elif message.startswith("SEARCH:"):
        q=message.split(':',1)[1].strip().casefold(); results=[]
        with log_lock:
            for ch in TEXT_CHANNELS:
                for e in message_log.get(ch,[]):
                    if q in str(e.get('text','')).casefold(): results.append((ch,e.get('sender',''),e.get('text','')))
            for key,arr in message_log.get('dms',{}).items():
                if username in key.split('|'):
                    for e in arr:
                        if q in str(e.get('text','')).casefold(): results.append((key,e.get('sender',''),e.get('text','')))
        for ch,sender,text in results[-100:]: connection.sendall(f"SEARCH_RESULT:{ch}:{sender}:{text}\n".encode())
        connection.sendall(b"SEARCH_DONE\n")

    elif message.startswith("REACT:"):
        p=message.split(':',3)
        if len(p)==4:
            room,msg_key,emoji=p[1],p[2],p[3]
            broadcast(f"REACTION:{room}:{msg_key}:{username}:{emoji}\n")

    elif message.startswith("EDIT:"):
        p=message.split(':',3)
        if len(p)==4:
            room,msg_key,newtext=p[1],p[2],p[3]
            broadcast(f"EDITED:{room}:{msg_key}:{username}:{newtext}\n")

    elif message.startswith("DELETE:"):
        p=message.split(':',2)
        if len(p)==3: broadcast(f"DELETED:{p[1]}:{p[2]}:{username}\n")

    elif message.startswith("PIN:"):
        p=message.split(':',2)
        if len(p)==3: broadcast(f"PINNED:{p[1]}:{p[2]}:{username}\n")

    elif message.startswith("FILE:"):
        p=message.split(':',3)
        if len(p)==4 and len(p[3])<=8_000_000:
            broadcast(f"FILE:{p[1]}:{username}:{p[2]}:{p[3]}\n")

    elif message.startswith("PROFILE:"):
        with accounts_lock: aid=account_for_username(username)
        if aid:
            r=main_request(f"PROFILE:{aid}");
            if r.startswith('PROFILE:'): connection.sendall((r+'\n').encode())

    elif message.startswith("PFP:"):
        b64_payload = message.split(":", 1)[1]
        with clients_lock:
            clients_pfp[username] = b64_payload
        broadcast(f"PFP:{username}:{b64_payload}\n")

    elif message.startswith("SERVERPFP:"):
        b64_payload = message.split(":", 1)[1]
        with clients_lock:
            server_icon_b64 = b64_payload
        broadcast(f"SERVERPFP:{b64_payload}\n")

    elif message.startswith("VOICEJOIN:"):
        with presence_lock:
            voice_presence_users.add(username)
        broadcast_voice_user_list()

    elif message.startswith("VOICELEAVE:"):
        with presence_lock:
            voice_presence_users.discard(username)
        broadcast_voice_user_list()


    elif message.startswith("CREATE_CHANNEL:"):
        name=message.split(':',1)[1].strip().lower().replace(' ','-')
        if name and re.fullmatch(r'[a-z0-9_-]{1,32}',name) and name not in TEXT_CHANNELS:
            TEXT_CHANNELS.append(name); message_log.setdefault(name,[]); schedule_log_save(); broadcast('CHANNEL_LIST:'+','.join(TEXT_CHANNELS)+'\n')

    elif message.startswith("DELETE_CHANNEL:"):
        name=message.split(':',1)[1].strip()
        if name in TEXT_CHANNELS and len(TEXT_CHANNELS)>1:
            TEXT_CHANNELS.remove(name); message_log.pop(name,None); schedule_log_save(); broadcast('CHANNEL_LIST:'+','.join(TEXT_CHANNELS)+'\n')
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
    with registered_users_lock:
        all_names = sorted(registered_users, key=str.lower)
    with clients_lock:
        online_names = sorted(clients.keys(), key=str.lower)
    broadcast("USERS:" + ",".join(all_names) + "\n")
    broadcast("ONLINE:" + ",".join(online_names) + "\n")


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