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
client_send_locks = {}     # socket -> Lock, prevents line interleaving on shared TCP connections
clients_lock = threading.RLock()
voice_users = set()
voice_lock = threading.RLock()
file_catalog = {}       # file_id -> metadata, never persisted
file_routes = {}        # file_id -> set of requesting usernames
file_lock = threading.RLock()
MAX_FILE_SIZE = 50 * 1024 * 1024
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
        chat_log[channel] = [normalize_message(e) for e in chat_log[channel]][-MAX_HISTORY:]
    if not isinstance(chat_log.get("dms"), dict):
        chat_log["dms"] = {}
    for key, entries in list(chat_log["dms"].items()):
        if not isinstance(entries, list):
            chat_log["dms"][key] = []
        else:
            chat_log["dms"][key] = [normalize_message(e) for e in entries][-MAX_HISTORY:]

    # Rebuild in-memory file metadata from message history. The actual files are
    # never stored on the server; only metadata is retained in chat history.
    with file_lock:
        file_catalog.clear()
        for channel in TEXT_CHANNELS:
            for entry in chat_log.get(channel, []):
                meta = entry.get("file") if isinstance(entry, dict) else None
                if isinstance(meta, dict) and meta.get("file_id"):
                    file_catalog[meta["file_id"]] = dict(meta)
        for entries in chat_log.get("dms", {}).values():
            for entry in entries:
                meta = entry.get("file") if isinstance(entry, dict) else None
                if isinstance(meta, dict) and meta.get("file_id"):
                    file_catalog[meta["file_id"]] = dict(meta)


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
    data = (line.rstrip("\n") + "\n").encode("utf-8")
    try:
        with clients_lock:
            lock_for_conn = client_send_locks.get(conn)
        if lock_for_conn is None:
            conn.sendall(data)
        else:
            with lock_for_conn:
                conn.sendall(data)
        return True
    except Exception:
        return False


def broadcast(line):
    with clients_lock:
        targets = list(clients.values())
    dead = []
    for conn in targets:
        if not send_line(conn, line):
            dead.append(conn)
    return dead

def dm_key(a, b):
    return "|".join(sorted([a, b], key=str.casefold))


def event_encode(payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def event_decode(encoded):
    return json.loads(base64.b64decode(encoded).decode("utf-8"))


def normalize_message(entry, sender_fallback=""):
    if not isinstance(entry, dict):
        return {"id": uuid.uuid4().hex, "sender": sender_fallback, "text": str(entry), "reply_to": None, "reactions": {}}
    entry.setdefault("id", uuid.uuid4().hex)
    entry.setdefault("sender", sender_fallback)
    entry.setdefault("text", "")
    entry.setdefault("reply_to", None)
    reactions = entry.get("reactions")
    if not isinstance(reactions, dict):
        reactions = {}
    cleaned = {}
    for emoji, users in reactions.items():
        if isinstance(users, list):
            cleaned[str(emoji)] = sorted(set(str(u) for u in users))
    entry["reactions"] = cleaned
    return entry


def find_message(room, message_id, username=None):
    with chat_lock:
        if room in TEXT_CHANNELS:
            entries = chat_log.get(room, [])
        else:
            if not username:
                return None, None
            key = dm_key(username, room)
            entries = chat_log.get("dms", {}).get(key, [])
        for entry in entries:
            if entry.get("id") == message_id:
                return entry, entries
    return None, None


def send_private_event(room, username, line):
    if room in TEXT_CHANNELS:
        broadcast(line)
        return
    with clients_lock:
        targets = {clients.get(username)}
        target_conn = clients.get(room)
        if target_conn is not None:
            targets.add(target_conn)
    for conn in targets:
        if conn is not None:
            send_line(conn, line)


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




def send_history(conn, username):
    with chat_lock:
        for channel in TEXT_CHANNELS:
            for entry in chat_log.get(channel, [])[-MAX_HISTORY:]:
                payload = dict(normalize_message(entry))
                payload["room"] = channel
                send_line(conn, "HISTORY:" + event_encode(payload))
        for key, entries in chat_log.get("dms", {}).items():
            if username not in key.split("|"):
                continue
            parts = key.split("|", 1)
            if len(parts) != 2:
                continue
            partner = parts[0] if parts[1] == username else parts[1]
            for entry in entries[-MAX_HISTORY:]:
                payload = dict(normalize_message(entry))
                payload["room"] = partner
                send_line(conn, "HISTORY:" + event_encode(payload))


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


def route_file_chunk(line, sender_username):
    try:
        encoded = line.split(":", 1)[1]
        payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
        file_id = str(payload.get("file_id", ""))
        if not file_id:
            return
        with file_lock:
            meta = file_catalog.get(file_id)
            targets = list(file_routes.get(file_id, set()))
        if not meta or meta.get("sender") != sender_username:
            return
        for target_username in targets:
            with clients_lock:
                target = clients.get(target_username)
            if target is not None:
                send_line(target, line)
    except Exception:
        pass


def route_file_done(line, sender_username):
    try:
        encoded = line.split(":", 1)[1]
        payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
        file_id = str(payload.get("file_id", ""))
        with file_lock:
            meta = file_catalog.get(file_id)
            targets = list(file_routes.pop(file_id, set()))
        if not meta or meta.get("sender") != sender_username:
            return
        for target_username in targets:
            with clients_lock:
                target = clients.get(target_username)
            if target is not None:
                send_line(target, line)
    except Exception:
        pass


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

    if line.startswith("FILE_REQUEST:"):
        try:
            payload = event_decode(line.split(":", 1)[1])
            file_id = str(payload.get("file_id", ""))
            requested_sender = str(payload.get("sender", ""))
            with file_lock:
                meta = file_catalog.get(file_id)
                if not meta:
                    send_line(conn, "ERROR:That file is no longer available from its sender")
                    return username
                if requested_sender and meta.get("sender") != requested_sender:
                    send_line(conn, "ERROR:File sender mismatch")
                    return username
                file_routes.setdefault(file_id, set()).add(username)
                sender_username = meta.get("sender", "")
            with clients_lock:
                sender_conn = clients.get(sender_username)
            if sender_conn is not None:
                forward = dict(payload)
                forward["requester"] = username
                send_line(sender_conn, "FILE_REQUEST:" + event_encode(forward))
            else:
                with file_lock:
                    file_routes.get(file_id, set()).discard(username)
                send_line(conn, "ERROR:The sender is offline; the file can be downloaded once they reconnect")
        except Exception as exc:
            send_line(conn, "ERROR:Invalid file request")
            print("[FILE REQUEST ERROR]", username, exc)
        return username

    if line.startswith("FILE_CHUNK:"):
        route_file_chunk(line, username)
        return username

    if line.startswith("FILE_DONE:"):
        route_file_done(line, username)
        return username

    if line.startswith("VOICE:"):
        # Voice audio travels over the already-authenticated TCP connection.
        # Format from client: VOICE:<base64 PCM>
        # Server forwards it only to users currently in the same voice call.
        encoded_audio = line.split(":", 1)[1] if ":" in line else ""
        if not encoded_audio:
            return username
        if len(encoded_audio) > 20000:
            print(f"[VOICE] Dropped oversized packet from {username}")
            return username

        with voice_lock:
            voice_targets = set(voice_users)

        with clients_lock:
            targets = [(name, peer) for name, peer in clients.items()
                       if name != username and name in voice_targets]

        packet = f"VOICE:{username}:{encoded_audio}"
        for target_name, peer in targets:
            send_line(peer, packet)
        return username

    if line.startswith("MESSAGE:"):
        try:
            payload = event_decode(line.split(":", 1)[1])
            room = str(payload.get("room", "general-chat")).strip()
            text = str(payload.get("text", ""))[:4000]
            message_id = str(payload.get("id", "")).strip() or uuid.uuid4().hex
            reply_to = payload.get("reply_to") if isinstance(payload.get("reply_to"), dict) else None
            kind = str(payload.get("kind", "message"))
            file_meta = payload.get("file") if isinstance(payload.get("file"), dict) else None
            poll = payload.get("poll") if isinstance(payload.get("poll"), dict) else None
            if file_meta:
                try:
                    size = int(file_meta.get("size", 0))
                except Exception:
                    size = 0
                if size <= 0 or size > MAX_FILE_SIZE or not file_meta.get("file_id"):
                    send_line(conn, "ERROR:Invalid file metadata")
                    return username
                file_meta = dict(file_meta)
                file_meta["sender"] = username
                file_meta["room"] = room
                with file_lock:
                    file_catalog[file_meta["file_id"]] = dict(file_meta)
            if room in TEXT_CHANNELS:
                entry = {"id": message_id, "sender": username, "text": text, "reply_to": reply_to, "reactions": {}, "kind": kind}
                if file_meta:
                    entry["file"] = file_meta
                if poll:
                    entry["poll"] = poll
                with chat_lock:
                    if any(e.get("id") == message_id for e in chat_log.setdefault(room, [])):
                        message_id = uuid.uuid4().hex
                        entry["id"] = message_id
                    chat_log[room].append(entry)
                    chat_log[room] = chat_log[room][-MAX_HISTORY:]
                    save_chat()
                event = dict(entry)
                event["room"] = room
                broadcast("MESSAGE:" + event_encode(event))
                return username

            target = room
            if not target or target.casefold() == username.casefold():
                return username
            with lock:
                target_aid = username_map.get(target.casefold())
                if not target_aid:
                    send_line(conn, "ERROR:That user does not exist")
                    return username
                target = accounts[target_aid].get("username", target)
            key = dm_key(username, target)
            entry = {"id": message_id, "sender": username, "text": text, "reply_to": reply_to, "reactions": {}, "kind": kind}
            if file_meta:
                entry["file"] = file_meta
            if poll:
                entry["poll"] = poll
            with chat_lock:
                entries = chat_log.setdefault("dms", {}).setdefault(key, [])
                if any(e.get("id") == message_id for e in entries):
                    entry["id"] = uuid.uuid4().hex
                entries.append(entry)
                chat_log["dms"][key] = entries[-MAX_HISTORY:]
                save_chat()
            sender_event = dict(entry)
            sender_event["room"] = target
            recipient_event = dict(entry)
            recipient_event["room"] = username
            with clients_lock:
                sender_conn = clients.get(username)
                recipient_conn = clients.get(target)
            if sender_conn is not None:
                send_line(sender_conn, "MESSAGE:" + event_encode(sender_event))
            if recipient_conn is not None and recipient_conn is not sender_conn:
                send_line(recipient_conn, "MESSAGE:" + event_encode(recipient_event))
            return username
        except Exception as exc:
            send_line(conn, "ERROR:Invalid message payload")
            print("[MESSAGE ERROR]", username, exc)
            return username

    if line.startswith("POLL_CREATE:"):
        try:
            payload = event_decode(line.split(":", 1)[1])
            room = str(payload.get("room", "general-chat")).strip()
            poll = payload.get("poll") if isinstance(payload.get("poll"), dict) else None
            question = str(payload.get("text", "")).strip()[:240]
            options = list(poll.get("options", [])) if poll else []
            if len(options) < 2 or len(options) > 6 or not question:
                send_line(conn, "ERROR:Poll needs a question and 2-6 options")
                return username
            clean_options = [str(v).strip()[:120] for v in options if str(v).strip()]
            if len(clean_options) < 2:
                return username
            poll_obj = {"question": question, "options": clean_options, "votes": {str(i): [] for i in range(len(clean_options))}}
            message_id = str(payload.get("id", "")).strip() or uuid.uuid4().hex
            entry = {"id": message_id, "sender": username, "text": question, "reply_to": payload.get("reply_to"), "reactions": {}, "kind": "poll", "poll": poll_obj}
            if room in TEXT_CHANNELS:
                with chat_lock:
                    chat_log.setdefault(room, []).append(entry)
                    chat_log[room] = chat_log[room][-MAX_HISTORY:]
                    save_chat()
                event = dict(entry); event["room"] = room
                broadcast("POLL:" + event_encode(event))
            else:
                target = room
                with lock:
                    target_aid = username_map.get(target.casefold())
                    if not target_aid:
                        send_line(conn, "ERROR:That user does not exist")
                        return username
                    target = accounts[target_aid].get("username", target)
                key = dm_key(username, target)
                with chat_lock:
                    chat_log["dms"].setdefault(key, []).append(entry)
                    chat_log["dms"][key] = chat_log["dms"][key][-MAX_HISTORY:]
                    save_chat()
                event = dict(entry); event["room"] = target
                recip = dict(entry); recip["room"] = username
                with clients_lock:
                    sender_conn = clients.get(username); target_conn = clients.get(target)
                if sender_conn: send_line(sender_conn, "POLL:" + event_encode(event))
                if target_conn and target_conn is not sender_conn: send_line(target_conn, "POLL:" + event_encode(recip))
        except Exception as exc:
            print("[POLL CREATE ERROR]", username, exc)
        return username

    if line.startswith("POLL_VOTE:"):
        try:
            payload = event_decode(line.split(":", 1)[1])
            room = str(payload.get("room", "general-chat")).strip()
            mid = str(payload.get("message_id", "")).strip()
            option = int(payload.get("option", -1))
            entry, entries = find_message(room, mid, username)
            if entry is None or entry.get("kind") != "poll":
                return username
            poll = entry.get("poll") if isinstance(entry.get("poll"), dict) else None
            if not poll or option < 0 or option >= len(poll.get("options", [])):
                return username
            votes = poll.setdefault("votes", {})
            for users in votes.values():
                if username in users:
                    users.remove(username)
            votes.setdefault(str(option), []).append(username)
            with chat_lock:
                save_chat()
            event = {"room": room, "message_id": mid, "poll": poll}
            if room in TEXT_CHANNELS:
                broadcast("POLL_VOTE:" + event_encode(event))
            else:
                recip = dict(event); recip["room"] = username
                with clients_lock:
                    sender_conn = clients.get(username); target_conn = clients.get(room)
                if sender_conn: send_line(sender_conn, "POLL_VOTE:" + event_encode(event))
                if target_conn and target_conn is not sender_conn: send_line(target_conn, "POLL_VOTE:" + event_encode(recip))
        except Exception as exc:
            print("[POLL VOTE ERROR]", username, exc)
        return username

    if line.startswith("REACT:"):
        try:
            payload = event_decode(line.split(":", 1)[1])
            room = str(payload.get("room", "general-chat")).strip()
            message_id = str(payload.get("message_id", "")).strip()
            emoji = str(payload.get("emoji", ""))[:8]
            if not message_id or not emoji:
                return username
            entry, entries = find_message(room, message_id, username)
            if entry is None:
                return username
            reactions = entry.setdefault("reactions", {})
            users = reactions.setdefault(emoji, [])
            # Toggling the same reaction makes the button behave like a switch.
            if username in users:
                users.remove(username)
            else:
                users.append(username)
            if not users:
                reactions.pop(emoji, None)
            with chat_lock:
                save_chat()
            event_sender = {"room": room, "message_id": message_id, "emoji": emoji, "user": username, "active": username in reactions.get(emoji, [])}
            if room in TEXT_CHANNELS:
                broadcast("REACTION:" + event_encode(event_sender))
            else:
                partner = room
                event_recipient = dict(event_sender)
                event_recipient["room"] = username
                with clients_lock:
                    sender_conn = clients.get(username)
                    recipient_conn = clients.get(partner)
                if sender_conn is not None:
                    send_line(sender_conn, "REACTION:" + event_encode(event_sender))
                if recipient_conn is not None and recipient_conn is not sender_conn:
                    send_line(recipient_conn, "REACTION:" + event_encode(event_recipient))
            return username
        except Exception as exc:
            print("[REACTION ERROR]", username, exc)
            return username

    if line.startswith("DELETE:"):
        try:
            payload = event_decode(line.split(":", 1)[1])
            room = str(payload.get("room", "general-chat")).strip()
            message_id = str(payload.get("message_id", "")).strip()
            entry, entries = find_message(room, message_id, username)
            if entry is None:
                return username
            if entry.get("sender") != username:
                send_line(conn, "ERROR:You can only delete your own messages")
                return username
            with chat_lock:
                if room in TEXT_CHANNELS:
                    chat_log[room] = [e for e in chat_log.get(room, []) if e.get("id") != message_id]
                else:
                    key = dm_key(username, room)
                    chat_log.setdefault("dms", {})[key] = [e for e in chat_log.get("dms", {}).get(key, []) if e.get("id") != message_id]
                save_chat()
            event_sender = {"room": room, "message_id": message_id}
            if room in TEXT_CHANNELS:
                broadcast("MESSAGE_DELETED:" + event_encode(event_sender))
            else:
                partner = room
                event_recipient = {"room": username, "message_id": message_id}
                with clients_lock:
                    sender_conn = clients.get(username)
                    recipient_conn = clients.get(partner)
                if sender_conn is not None:
                    send_line(sender_conn, "MESSAGE_DELETED:" + event_encode(event_sender))
                if recipient_conn is not None and recipient_conn is not sender_conn:
                    send_line(recipient_conn, "MESSAGE_DELETED:" + event_encode(event_recipient))
            return username
        except Exception as exc:
            print("[DELETE ERROR]", username, exc)
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
        with clients_lock:
            client_send_locks.pop(conn, None)
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
print("NETRA VOICE: TCP audio relay enabled on the authenticated port 12145.")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(100)
    while True:
        conn, addr = server.accept()
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass
        with clients_lock:
            client_send_locks[conn] = threading.RLock()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()
