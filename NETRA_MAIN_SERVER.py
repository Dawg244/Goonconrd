import array
import base64
import io
import json
import math
import hashlib
import mimetypes
import os
import queue
import socket
import struct
import sys
import tempfile
import threading
import time
import wave
import uuid
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv, set_key
from PIL import Image, ImageGrab

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    SOUNDDEVICE_AVAILABLE = False

try:
    from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, QSize
    from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPixmap, QCursor
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QMenu,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSplitter,
        QStackedWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise SystemExit(
        "PySide6 is required for NETRA. Install it with:\n"
        f"  {sys.executable} -m pip install PySide6\n\n"
        f"Import error: {exc}"
    )


# ---------------------------------------------------------------------------
# Paths / network
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR = BASE_DIR
try:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    test_path = os.path.join(CONFIG_DIR, ".netra_write_test")
    with open(test_path, "a", encoding="utf-8"):
        pass
    os.remove(test_path)
except Exception:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "NETRA")
    os.makedirs(CONFIG_DIR, exist_ok=True)

ENV_FILE = os.path.join(CONFIG_DIR, ".env")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
CHAT_CACHE_FILE = os.path.join(CONFIG_DIR, "chat_cache.json")
FILE_CACHE_DIR = os.path.join(CONFIG_DIR, "files")
os.makedirs(FILE_CACHE_DIR, exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024
FILE_CHUNK_SIZE = 24 * 1024
PROFILE_IMAGE_FILE = os.path.join(CONFIG_DIR, "profile.png")
ICON_DIR = os.path.join(BASE_DIR, "assets", "icons")
os.makedirs(ICON_DIR, exist_ok=True)
load_dotenv(ENV_FILE, override=True)

DEFAULT_HOST = "108.221.36.120"
PORT = 12145
SCREEN_PORT_DEFAULT = 12157
VOICE_RATE_DEFAULT = 32000
VOICE_CHANNELS = 1
VOICE_CHUNK = 1024


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------

THEMES = {
    "NETRA Terminal": {
        "root": "#050A05", "rail": "#020402", "panel": "#0A140A", "panel_alt": "#0E1C0E",
        "input": "#0C1A0C", "bright": "#33FF33", "dim": "#1E8C1E", "faint": "#145214",
        "border": "#123312", "button": "#0F1F0F", "hover": "#1B3D1B", "active": "#33FF33",
        "active_hover": "#29CC29", "error": "#FF5555", "icon": "netra_terminal.ico"
    },
    "Midnight": {
        "root": "#080B14", "rail": "#050711", "panel": "#0D1220", "panel_alt": "#12192A",
        "input": "#101729", "bright": "#62B0FF", "dim": "#3B78B5", "faint": "#29435F",
        "border": "#1E3550", "button": "#121D30", "hover": "#1B3150", "active": "#62B0FF",
        "active_hover": "#3D8FE0", "error": "#FF667A", "icon": "midnight.ico"
    },
    "Light": {
        "root": "#E9EDF2", "rail": "#D7DDE5", "panel": "#F6F8FA", "panel_alt": "#E1E6ED",
        "input": "#FFFFFF", "bright": "#146CDA", "dim": "#3D6F9F", "faint": "#718096",
        "border": "#B8C2CF", "button": "#DCE4ED", "hover": "#C9D8E8", "active": "#146CDA",
        "active_hover": "#0F5BB9", "error": "#C62828", "icon": "light.ico"
    },
    "CRT Amber": {
        "root": "#090704", "rail": "#050402", "panel": "#151008", "panel_alt": "#1C150B",
        "input": "#120D06", "bright": "#FFB000", "dim": "#A87300", "faint": "#664900",
        "border": "#4A3400", "button": "#1B1408", "hover": "#332308", "active": "#FFB000",
        "active_hover": "#D99300", "error": "#FF5F56", "icon": "crt_amber.ico"
    },
    "Violet": {
        "root": "#0B0710", "rail": "#06040A", "panel": "#140D1C", "panel_alt": "#1D1328",
        "input": "#160E20", "bright": "#D18BFF", "dim": "#8D5BB0", "faint": "#593A70",
        "border": "#412852", "button": "#1B1025", "hover": "#302044", "active": "#D18BFF",
        "active_hover": "#A962D5", "error": "#FF668F", "icon": "violet.ico"
    },
    "Ocean": {
        "root": "#061018", "rail": "#030A10", "panel": "#0A1822", "panel_alt": "#0E202C",
        "input": "#0B1B27", "bright": "#42D9FF", "dim": "#2D91AD", "faint": "#20566A",
        "border": "#164454", "button": "#0E2530", "hover": "#174353", "active": "#42D9FF",
        "active_hover": "#27B6D8", "error": "#FF6B7A", "icon": "ocean.ico"
    },
    "Dracula": {
        "root": "#282A36", "rail": "#191A21", "panel": "#21222C", "panel_alt": "#343746",
        "input": "#303241", "bright": "#BD93F9", "dim": "#8F78B3", "faint": "#625576",
        "border": "#4B4660", "button": "#343746", "hover": "#44475A", "active": "#BD93F9",
        "active_hover": "#A97DE0", "error": "#FF5555", "icon": "dracula.ico"
    },
    "Nord": {
        "root": "#2E3440", "rail": "#242933", "panel": "#3B4252", "panel_alt": "#434C5E",
        "input": "#2F3644", "bright": "#88C0D0", "dim": "#6A96A3", "faint": "#536B73",
        "border": "#4C566A", "button": "#3B4252", "hover": "#4C566A", "active": "#88C0D0",
        "active_hover": "#70A8BA", "error": "#BF616A", "icon": "nord.ico"
    },
    "Solarized": {
        "root": "#002B36", "rail": "#00232C", "panel": "#073642", "panel_alt": "#0A4150",
        "input": "#00333F", "bright": "#2AA198", "dim": "#3C8882", "faint": "#28615E",
        "border": "#174F58", "button": "#0A3B47", "hover": "#14525F", "active": "#2AA198",
        "active_hover": "#238C82", "error": "#DC322F", "icon": "solarized.ico"
    },
    "Sakura": {
        "root": "#210E17", "rail": "#180A11", "panel": "#321421", "panel_alt": "#421B2A",
        "input": "#2C101C", "bright": "#FF9FB8", "dim": "#B86F83", "faint": "#774755",
        "border": "#633244", "button": "#381826", "hover": "#502236", "active": "#FF9FB8",
        "active_hover": "#E9829C", "error": "#FF5F73", "icon": "sakura.ico"
    },
    "Mono": {
        "root": "#101010", "rail": "#080808", "panel": "#181818", "panel_alt": "#222222",
        "input": "#151515", "bright": "#F0F0F0", "dim": "#AAAAAA", "faint": "#666666",
        "border": "#3A3A3A", "button": "#232323", "hover": "#333333", "active": "#F0F0F0",
        "active_hover": "#CCCCCC", "error": "#FF6666", "icon": "mono.ico"
    },
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def resample_pcm16_mono(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    if not data or src_rate == dst_rate:
        return data
    sample_count = len(data) // 2
    if sample_count <= 1:
        return data
    src = struct.unpack("<%dh" % sample_count, data[:sample_count * 2])
    out_count = max(1, int(round(sample_count * dst_rate / src_rate)))
    out = bytearray(out_count * 2)
    ratio = src_rate / dst_rate
    for i in range(out_count):
        pos = i * ratio
        left = int(pos)
        frac = pos - left
        if left >= sample_count - 1:
            value = src[-1]
        else:
            value = int(src[left] + (src[left + 1] - src[left]) * frac)
        struct.pack_into("<h", out, i * 2, max(-32768, min(32767, value)))
    return bytes(out)


def format_file_size(size):
    size = float(size or 0)
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def local_file_path(file_id, filename):
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(filename or "file"))
    return os.path.join(FILE_CACHE_DIR, f"{file_id}_{safe}")


class StreamingPCMResampler:
    """Stateful mono PCM resampler that preserves phase across packets."""

    def __init__(self, src_rate: int, dst_rate: int):
        self.src_rate = int(src_rate)
        self.dst_rate = int(dst_rate)
        self.step = self.src_rate / self.dst_rate if self.dst_rate else 1.0
        self.samples = array.array("h")
        self.position = 0.0

    def process(self, data: bytes) -> bytes:
        if not data:
            return b""
        if self.src_rate == self.dst_rate:
            return data
        incoming = array.array("h")
        incoming.frombytes(data[:len(data) - (len(data) % 2)])
        if incoming:
            self.samples.extend(incoming)
        if len(self.samples) < 2:
            return b""
        out = array.array("h")
        while self.position + 1.0 < len(self.samples):
            left = int(self.position)
            frac = self.position - left
            value = int(self.samples[left] + (self.samples[left + 1] - self.samples[left]) * frac)
            out.append(max(-32768, min(32767, value)))
            self.position += self.step
        consume = min(max(0, int(self.position)), max(0, len(self.samples) - 1))
        if consume:
            del self.samples[:consume]
            self.position -= consume
        return out.tobytes()


def save_settings(data: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def load_settings() -> dict:
    defaults = {
        "theme": "NETRA Terminal",
        "server_host": "108.221.36.120",
        "server_port": 12145,
        "dm_sound_mode": "ping",
        "dm_sound_path": "",
        "voice_input_device": None,
        "voice_output_device": None,
        "voice_volume": 1.25,
        "voice_mic_gain": 1.0,
        "voice_quality": "High",
        "voice_profile": "Recording",
        "voice_noise_gate": True,
        "voice_agc": True,
        "voice_echo_guard": True,
        "voice_deafen": False,
        "voice_ptt": False,
        "voice_record": False,
        "voice_user_volumes": {},
        "voice_user_mutes": {},
    }
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                defaults.update(data)
    except Exception:
        pass
    return defaults


def generate_ping_wav(style: str = "ping") -> str:
    melodies = {
        "ping": [(659.25, 0.00, 0.11), (783.99, 0.09, 0.16), (1046.50, 0.18, 0.20)],
        "ping_2": [(523.25, 0.00, 0.12), (659.25, 0.10, 0.15), (783.99, 0.20, 0.19)],
        "ping_3": [(783.99, 0.00, 0.10), (987.77, 0.08, 0.13), (1174.66, 0.16, 0.18)],
        "ping_4": [(392.00, 0.00, 0.13), (523.25, 0.11, 0.16), (659.25, 0.22, 0.21)],
        "ping_5": [(587.33, 0.00, 0.10), (739.99, 0.08, 0.13), (880.00, 0.16, 0.18)],
    }
    melody = melodies.get(style, melodies["ping"])
    path = os.path.join(tempfile.gettempdir(), f"netra_{style}_qt.wav")
    if os.path.exists(path):
        return path
    rate = 44100
    total = max(start + duration for _, start, duration in melody) + 0.18
    frames = bytearray()
    for i in range(int(rate * total)):
        t = i / rate
        sample = 0.0
        for freq, start, duration in melody:
            local = t - start
            if 0 <= local < duration:
                attack = min(1.0, local / 0.018)
                release = min(1.0, (duration - local) / 0.055)
                env = attack * release
                sample += env * (
                    0.78 * math.sin(2 * math.pi * freq * local)
                    + 0.16 * math.sin(2 * math.pi * freq * 2 * local)
                    + 0.06 * math.sin(2 * math.pi * freq * 3 * local)
                )
        frames.extend(struct.pack("<h", int(max(-1, min(1, sample * 0.22)) * 32767)))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))
    return path


@dataclass
class ChatMessage:
    sender: str
    text: str
    msg_id: str = ""
    edited: bool = False


class NetraSignals(QObject):
    incoming_line = Signal(str)
    connection_lost = Signal()
    error = Signal(str)


class VoiceTestSignals(QObject):
    result = Signal(str, bool)


class NetworkWorker(QThread):
    line_received = Signal(str)
    disconnected = Signal()
    failed = Signal(str)

    def __init__(self, sock: socket.socket):
        super().__init__()
        self.sock = sock
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        buffer = ""
        try:
            while self._running:
                data = self.sock.recv(65536)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer and self._running:
                    line, buffer = buffer.split("\n", 1)
                    if line:
                        self.line_received.emit(line)
        except Exception as exc:
            if self._running:
                self.failed.emit(str(exc))
        finally:
            self.disconnected.emit()


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class ScreenReceiveWorker(QThread):
    frame_received = Signal(str, int, bytes)
    failed = Signal(str)
    disconnected = Signal()

    def __init__(self, sock):
        super().__init__()
        self.sock = sock
        self._running = True

    def stop(self):
        self._running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

    def run(self):
        try:
            self.sock.settimeout(5)
            hello = self._recv_line()
            if hello != "SCREEN_OK":
                raise RuntimeError(hello or "screen relay authentication failed")
            self.sock.settimeout(None)
            while self._running:
                header = self._recv_exact(4)
                if not header:
                    break
                length = struct.unpack("!I", header)[0]
                if length < 9 or length > 8_000_000:
                    raise RuntimeError("invalid screen frame size")
                payload = self._recv_exact(length)
                if not payload or payload[:1] != b"F" or len(payload) < 9:
                    continue
                seq = struct.unpack("!Q", payload[1:9])[0]
                sender = ""
                jpeg_start = 9
                # v2 metadata: username length + username + fps + width + height.
                if len(payload) >= 17:
                    try:
                        name_len = struct.unpack("!H", payload[9:11])[0]
                        meta_end = 11 + name_len + 6
                        if name_len <= 128 and meta_end <= len(payload):
                            sender_name = payload[11:11 + name_len].decode("utf-8", errors="replace")
                            fps, width, height = struct.unpack("!HHH", payload[11 + name_len:meta_end])
                            if sender_name:
                                sender = f"{sender_name}|{fps}|{width}|{height}"
                                jpeg_start = meta_end
                    except Exception:
                        pass
                self.frame_received.emit(sender, seq, payload[jpeg_start:])
        except Exception as exc:
            if self._running:
                self.failed.emit(str(exc))
        finally:
            self.disconnected.emit()

    def _recv_exact(self, size):
        data = bytearray()
        while self._running and len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    def _recv_line(self):
        data = bytearray()
        while self._running and len(data) < 1024:
            b = self.sock.recv(1)
            if not b:
                return ""
            if b == b"\n":
                return data.decode("utf-8", errors="ignore")
            data.extend(b)
        return ""


class AuthDialog(QDialog):
    authenticated = Signal(str, str, str)

    def __init__(self, parent, saved_username=""):
        super().__init__(parent)
        self.setWindowTitle("NETRA // ACCOUNT")
        self.setFixedSize(430, 520)
        self.setModal(True)
        self.setStyleSheet(parent.dialog_qss())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 28, 35, 28)
        layout.setSpacing(10)

        title = QLabel("NETRA // ACCOUNT")
        title.setProperty("role", "title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("LOGIN OR CREATE YOUR NETRA ACCOUNT")
        subtitle.setProperty("role", "muted")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(6)

        layout.addWidget(QLabel("SERVER ADDRESS"))
        self.server_host = QLineEdit(str(parent.server_host))
        self.server_host.setPlaceholderText("IP address or hostname")
        layout.addWidget(self.server_host)

        layout.addWidget(QLabel("SERVER PORT"))
        self.server_port = QLineEdit(str(parent.server_port))
        self.server_port.setPlaceholderText("12145")
        layout.addWidget(self.server_port)

        reset_ip = QPushButton("RESET SERVER IP")
        reset_ip.clicked.connect(self.reset_server_address)
        layout.addWidget(reset_ip)

        layout.addSpacing(4)
        layout.addWidget(QLabel("USERNAME"))
        self.username = QLineEdit(saved_username if saved_username and saved_username != "User" else "")
        self.username.setPlaceholderText("username")
        layout.addWidget(self.username)

        layout.addWidget(QLabel("PASSWORD"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("password")
        layout.addWidget(self.password)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setProperty("role", "error")
        layout.addWidget(self.status)
        layout.addSpacing(8)

        login = QPushButton("LOGIN")
        login.clicked.connect(lambda: self.submit("LOGIN"))
        layout.addWidget(login)

        register = QPushButton("CREATE ACCOUNT")
        register.clicked.connect(lambda: self.submit("REGISTER"))
        layout.addWidget(register)

        offline = QPushButton("CONTINUE OFFLINE")
        offline.clicked.connect(lambda: self.authenticated.emit("OFFLINE", username, ""))
        layout.addWidget(offline)

        footer = QLabel(
            "Use the server address above to connect.\n"
            "On the same LAN, use the server PC's local IPv4 address."
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setProperty("role", "muted")
        layout.addWidget(footer)

        self.password.returnPressed.connect(lambda: self.submit("LOGIN"))
        self.username.returnPressed.connect(self.password.setFocus)
        self.username.setFocus()

    def reset_server_address(self):
        """Restore the default NETRA server address and port."""
        default_host = DEFAULT_HOST
        default_port = str(PORT)

        self.server_host.setText(default_host)
        self.server_port.setText(default_port)

        self.parent().server_host = default_host
        self.parent().server_port = PORT
        self.parent().settings["server_host"] = default_host
        self.parent().settings["server_port"] = PORT
        save_settings(self.parent().settings)

        self.status.setProperty("role", "muted")
        self.style().unpolish(self.status)
        self.style().polish(self.status)
        self.status.setText(f"Server reset to {default_host}:{PORT}")

    def submit(self, mode):
        username = self.username.text().strip()
        password = self.password.text()
        host = self.server_host.text().strip()
        port_text = self.server_port.text().strip()
        if not host:
            self.status.setText("Enter a server address.")
            self.server_host.setFocus()
            return
        try:
            port = int(port_text)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.status.setText("Server port must be 1-65535.")
            self.server_port.setFocus()
            return
        if not username:
            self.status.setText("Enter a username.")
            self.username.setFocus()
            return
        if not password:
            self.status.setText("Enter a password.")
            self.password.setFocus()
            return
        self.parent().server_host = host
        self.parent().server_port = port
        self.parent().settings["server_host"] = host
        self.parent().settings["server_port"] = port
        save_settings(self.parent().settings)
        self.status.setProperty("role", "muted")
        self.style().unpolish(self.status)
        self.style().polish(self.status)
        self.status.setText("Connecting to NETRA...")
        self.authenticated.emit(mode, username, password)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class HoverMessageCard(QFrame):
    hovered = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("messageCard")
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)

    def enterEvent(self, event):
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered.emit(False)
        super().leaveEvent(event)


class FullDiscordClone(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.theme_name = self.settings.get("theme", "NETRA Terminal")
        if self.theme_name not in THEMES:
            self.theme_name = "NETRA Terminal"

        self.server_host = str(self.settings.get("server_host", DEFAULT_HOST)).strip() or DEFAULT_HOST
        try:
            self.server_port = int(self.settings.get("server_port", PORT))
        except (TypeError, ValueError):
            self.server_port = PORT
        if not 1 <= self.server_port <= 65535:
            self.server_port = PORT
        self.client_socket: Optional[socket.socket] = None
        self.screen_socket: Optional[socket.socket] = None
        self.screen_worker: Optional[ScreenReceiveWorker] = None
        self.screen_token = ""
        self.screen_port = SCREEN_PORT_DEFAULT
        self.screen_share_active = False
        self.screen_capture_thread = None
        self.screen_capture_stop = threading.Event()
        self.screen_sequence = 0
        self.screen_last_frame = None
        self.screen_last_frame_sender = ""
        self.screen_last_frame_time = 0.0
        self.screen_viewers = set()
        self._screen_send_lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.network_worker: Optional[NetworkWorker] = None
        self.authenticated = False
        self.server_protocol_version = 1
        self.server_capabilities = set()
        self.screen_share_status = {}
        self.screen_last_frame_meta = {}
        self.account_id = os.getenv("NETRA_ACCOUNT_ID", "")
        self.username = os.getenv("CHAT_USERNAME", "User")
        self.auth_dialog: Optional[AuthDialog] = None

        self.current_target = "general-chat"
        self.server_channels = ["general-chat", "random"]
        self.chat_history = {"general-chat": [], "random": []}
        self._load_chat_cache()
        self.dm_partners = []
        self.last_registered_users = []
        self.online_users = set()
        self.voice_users = []
        self.incoming_queue = queue.Queue()
        self.pending_local_messages = set()
        self.user_pfps = {}
        self.server_pfp = None
        self.pins = {}
        self.reactions = {}
        self.presence_status = {}
        self.custom_status = {}
        self.typing_users = {}
        self.pending_local_message_ids = set()
        self.reply_target = None
        self.message_card_widgets = {}
        self.voice_activity = {}
        self.voice_levels = {}
        self.voice_wave_labels = {}
        self.loading_history = False
        self._chat_cache_dirty = False
        self._render_generation = 0
        self.offline_mode = False
        self._last_password = ""
        self._last_auth_mode = "LOGIN"
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(3000)
        self._reconnect_timer.timeout.connect(self._attempt_smart_reconnect)
        self._reconnect_attempts = 0
        self._outbox = []
        self._pending_file_sends = {}
        self._incoming_file_transfers = {}
        self._file_send_lock = threading.Lock()
        self._file_receive_lock = threading.Lock()

        self.voice_muted = False
        self.in_voice_chat = False
        self.voice_input_stream = None
        self.voice_output_stream = None
        self.voice_input_rate = 48000
        self.voice_output_rate = 48000
        self.voice_play_queue = queue.Queue(maxsize=80)
        self.voice_resamplers = {}
        self.voice_send_resampler = None
        self.voice_prebuffer_packets = 3
        self.voice_deafened = bool(self.settings.get("voice_deafen", False))
        self.voice_ptt = bool(self.settings.get("voice_ptt", False))
        self.voice_ptt_down = False
        self.voice_recording = bool(self.settings.get("voice_record", False))
        self.voice_record_wave = None
        self.voice_record_file = ""
        self.voice_volume = float(self.settings.get("voice_volume", 1.25))
        self.voice_mic_gain = float(self.settings.get("voice_mic_gain", 1.0))
        self.voice_quality = str(self.settings.get("voice_quality", "High"))
        self.voice_noise_gate = bool(self.settings.get("voice_noise_gate", True))
        self.voice_agc = bool(self.settings.get("voice_agc", True))
        self.voice_echo_guard = bool(self.settings.get("voice_echo_guard", True))
        self.voice_user_volumes = dict(self.settings.get("voice_user_volumes", {}) or {})
        self.voice_user_mutes = dict(self.settings.get("voice_user_mutes", {}) or {})
        self.voice_packet_count = 0
        self.voice_bytes_received = 0
        self.voice_jitter_ms = 0.0
        self.voice_last_packet_time = 0.0
        self.voice_test_signals = VoiceTestSignals()
        self.voice_test_signals.result.connect(self._apply_voice_test_status)

        self.pil_profile = self._load_profile_image()

        self.setWindowTitle("NETRA // TERMINAL")
        self.resize(1200, 760)
        self.setMinimumSize(980, 640)
        self._install_icon()
        self._build_ui()
        self._apply_theme()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._process_incoming_queue)
        self.timer.start(15)

        self.voice_stats_timer = QTimer(self)
        self.voice_stats_timer.timeout.connect(self._update_voice_stats)
        self.voice_stats_timer.start(100)

        self._connect_after_start = QTimer(self)
        self._connect_after_start.setSingleShot(True)
        self._connect_after_start.timeout.connect(self.show_auth)
        self._connect_after_start.start(250)

    # ---------- styling ----------

    def palette_colors(self):
        return THEMES[self.theme_name]

    def dialog_qss(self):
        c = self.palette_colors()
        return self._stylesheet(c, dialog=True)

    def _stylesheet(self, c, dialog=False):
        return f"""
        QWidget {{
            color: {c['bright']};
            background: {c['root']};
            font-family: Consolas;
            font-size: 12px;
        }}
        QMainWindow {{ background: {c['root']}; }}
        QLabel {{ background: transparent; }}
        QLabel[role="title"] {{ font-size: 20px; font-weight: 700; }}
        QLabel[role="heading"] {{ color: {c['bright']}; font-size: 13px; font-weight: 700; }}
        QLabel[role="muted"] {{ color: {c['dim']}; }}
        QLabel[role="error"] {{ color: {c['error']}; }}

        QFrame#rail {{ background: {c['rail']}; border: none; }}
        QFrame#panel {{ background: {c['panel']}; border: none; }}
        QFrame#panelAlt {{ background: {c['panel_alt']}; border: none; }}
        QFrame#chat {{ background: {c['root']}; border: none; }}
        QFrame#serverBar {{ background: {c['panel']}; border: none; }}
        QFrame#messageCard {{ background: transparent; border: 1px solid transparent; border-radius: 2px; }}
        QFrame#messageCard:hover {{ background: {c['hover']}; border: 1px solid {c['border']}; }}
        QLabel[role="messageText"] {{ color: {c['dim']}; font-family: Consolas; font-size: 13px; }}
        QFrame#messageCard:hover QLabel[role="messageText"] {{ color: {c['bright']}; }}
        QLabel[role="replyPreview"] {{ color: {c['faint']}; font-family: Consolas; font-size: 10px; }}
        QLabel[role="reactionRow"] {{ color: {c['bright']}; font-family: Consolas; font-size: 11px; }}
        QPushButton#messageActionButton {{ background: {c['button']}; color: {c['dim']}; border: 1px solid {c['border']}; padding: 1px 4px; min-width: 48px; max-width: 68px; min-height: 22px; max-height: 22px; font-size: 9px; }}
        QPushButton#messageActionButton:hover {{ background: {c['hover']}; color: {c['bright']}; }}
        QFrame#settingsPanel {{ background: {c['root']}; border: 1px solid {c['border']}; }}
        QFrame#settingsSection {{ background: {c['panel']}; border: none; }}

        QLineEdit, QComboBox {{
            background: {c['input']};
            color: {c['bright']};
            border: 1px solid {c['border']};
            border-radius: 0px;
            padding: 6px 8px;
            selection-background-color: {c['active']};
            selection-color: {c['root']};
        }}
        QLineEdit:focus, QComboBox:focus {{ border: 1px solid {c['active']}; }}
        QComboBox QAbstractItemView {{
            background: {c['panel']};
            color: {c['bright']};
            border: 1px solid {c['border']};
            selection-background-color: {c['hover']};
        }}

        QPushButton, QToolButton {{
            background: {c['button']};
            color: {c['bright']};
            border: 1px solid {c['border']};
            border-radius: 0px;
            padding: 4px 6px;
            font-family: Consolas;
            font-size: 10px;
        }}
        QPushButton:hover, QToolButton:hover {{ background: {c['hover']}; }}
        QPushButton:pressed, QToolButton:pressed {{ background: {c['active']}; color: {c['root']}; }}
        QPushButton:checked {{ background: {c['hover']}; }}

        QListWidget {{
            background: {c['panel']};
            color: {c['bright']};
            border: none;
            outline: none;
        }}
        QListWidget::item {{ padding: 5px 6px; }}
        QListWidget::item:hover {{ background: {c['hover']}; }}
        QListWidget::item:selected {{ background: {c['hover']}; }}
        QLabel[role="memberName"] {{ color: {c['bright']}; font-family: Consolas; font-size: 11px; font-weight: 700; }}
        QLabel[role="heading"] {{ color: {c['bright']}; font-family: Consolas; font-size: 11px; font-weight: 700; }}

        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{ background: {c['panel']}; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 30px; }}
        QScrollBar::handle:vertical:hover {{ background: {c['hover']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: {c['panel']}; }}

        QCheckBox {{ spacing: 6px; color: {c['dim']}; }}
        QCheckBox::indicator {{ width: 14px; height: 14px; }}
        QSlider::groove:horizontal {{ background: {c['border']}; height: 5px; }}
        QSlider::handle:horizontal {{ background: {c['active']}; width: 13px; margin: -4px 0; }}
        QSplitter::handle {{ background: {c['border']}; }}
        """

    def _apply_theme(self):
        c = self.palette_colors()
        self.setStyleSheet(self._stylesheet(c))
        self._apply_widget_theme(c)
        self._install_icon()
        if hasattr(self, 'settings_overlay'):
            self.settings_overlay.setStyleSheet("background: rgba(0,0,0,210);")

    def _apply_widget_theme(self, c):
        if not hasattr(self, "server_title_label"):
            return
        self.server_title_label.setStyleSheet(f"color:{c['bright']}; font-size:14px; font-weight:700;")
        self.server_ip_label.setStyleSheet(f"color:{c['faint']}; font-size:9px;")
        self.server_status_label.setStyleSheet(f"color:{c['dim']}; font-size:9px;")
        self.chat_status_label.setStyleSheet(f"color:{c['dim']}; font-size:9px;")
        self.chat_title_label.setStyleSheet(f"color:{c['bright']}; font-size:14px; font-weight:700;")
        self.voice_header.setStyleSheet(f"color:{c['dim']}; font-size:10px; font-weight:700;")
        self.members_header.setStyleSheet(f"color:{c['dim']}; font-size:10px; font-weight:700;")
        self.username_label.setStyleSheet(f"color:{c['bright']}; font-size:11px; font-weight:700;")

    def _install_icon(self):
        icon_name = THEMES[self.theme_name].get("icon")
        if icon_name:
            path = os.path.join(ICON_DIR, icon_name)
            if os.path.exists(path):
                self.setWindowIcon(QIcon(path))

    # ---------- main UI ----------

    def _build_ui(self):
        self.resize(1000, 600)
        self.setMinimumSize(900, 560)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------------- server rail ----------------
        self.rail = QFrame(objectName="rail")
        self.rail.setFixedWidth(70)
        rail_layout = QVBoxLayout(self.rail)
        rail_layout.setContentsMargins(8, 12, 8, 12)
        rail_layout.setSpacing(4)

        self.server_button = QToolButton()
        self.server_button.setText("🏠")
        self.server_button.setFixedSize(48, 48)
        self.server_button.clicked.connect(self.show_server_view)
        rail_layout.addWidget(self.server_button, alignment=Qt.AlignHCenter)

        self.dm_button = QToolButton()
        self.dm_button.setText("💬")
        self.dm_button.setFixedSize(48, 40)
        self.dm_button.clicked.connect(self.show_dm_view)
        rail_layout.addWidget(self.dm_button, alignment=Qt.AlignHCenter)
        rail_layout.addStretch(1)

        self.fullscreen_button = QToolButton()
        self.fullscreen_button.setText("⛶")
        self.fullscreen_button.setFixedSize(48, 36)
        self.fullscreen_button.setToolTip("Toggle fullscreen (F11)")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        rail_layout.addWidget(self.fullscreen_button, alignment=Qt.AlignHCenter)
        root.addWidget(self.rail)

        # ---------------- left channel sidebar ----------------
        self.sidebar = QFrame(objectName="panel")
        self.sidebar.setFixedWidth(200)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(10, 12, 10, 8)
        side.setSpacing(4)

        self.server_title_label = QLabel("NETRA // SERVER")
        side.addWidget(self.server_title_label)
        self.server_ip_label = QLabel(f"{self.server_host}:{self.server_port}")
        side.addWidget(self.server_ip_label)

        self.channel_button = QPushButton("# general-chat")
        self.channel_button.setFixedHeight(32)
        self.channel_button.clicked.connect(lambda: self.select_channel("general-chat"))
        side.addWidget(self.channel_button)

        self.random_button = QPushButton("# random")
        self.random_button.setFixedHeight(32)
        self.random_button.clicked.connect(lambda: self.select_channel("random"))
        side.addWidget(self.random_button)

        self.voice_button = QPushButton("JOIN VOICE")
        self.voice_button.setFixedHeight(32)
        self.voice_button.clicked.connect(self.toggle_voice_chat)
        side.addWidget(self.voice_button)

        self.voice_mute_button = QPushButton("MUTE MIC")
        self.voice_mute_button.setFixedHeight(28)
        self.voice_mute_button.clicked.connect(self.toggle_voice_mute)
        side.addWidget(self.voice_mute_button)

        screen_options = QHBoxLayout()
        self.screen_monitor_combo = QComboBox()
        for idx, screen in enumerate(QApplication.screens()):
            g = screen.geometry()
            name = screen.name() or f"Monitor {idx + 1}"
            self.screen_monitor_combo.addItem(f"{name}  {g.width()}x{g.height()}", idx)
        if self.screen_monitor_combo.count() == 0:
            self.screen_monitor_combo.addItem("Primary monitor", 0)
        self.screen_fps_combo = QComboBox()
        for fps in (20, 30, 60):
            self.screen_fps_combo.addItem(f"{fps} FPS", fps)
        self.screen_fps_combo.setCurrentText("30 FPS")
        screen_options.addWidget(self.screen_monitor_combo, 1)
        screen_options.addWidget(self.screen_fps_combo)
        side.addLayout(screen_options)

        self.screen_share_button = QPushButton("SCREEN SHARE")
        self.screen_share_button.setFixedHeight(28)
        self.screen_share_button.clicked.connect(self.toggle_screen_share)
        side.addWidget(self.screen_share_button)

        self.screen_view_button = QPushButton("VIEW SHARED SCREEN")
        self.screen_view_button.setFixedHeight(28)
        self.screen_view_button.clicked.connect(self.open_screen_viewer)
        side.addWidget(self.screen_view_button)

        self.dm_label = QLabel("DIRECT MESSAGES")
        self.dm_label.setStyleSheet("color:#1E8C1E; font-size:10px; font-weight:700;")
        side.addWidget(self.dm_label)

        self.dm_list = QListWidget()
        self.dm_list.itemClicked.connect(self._dm_item_clicked)
        side.addWidget(self.dm_list, 1)

        profile = QFrame(objectName="panelAlt")
        profile_layout = QVBoxLayout(profile)
        profile_layout.setContentsMargins(8, 8, 8, 8)
        profile_layout.setSpacing(4)
        self.pfp_label = QLabel()
        self.pfp_label.setFixedSize(40, 40)
        self.pfp_label.setAlignment(Qt.AlignCenter)
        profile_layout.addWidget(self.pfp_label, alignment=Qt.AlignHCenter)
        self.username_label = QLabel(self.username)
        self.username_label.setAlignment(Qt.AlignCenter)
        profile_layout.addWidget(self.username_label)
        self.pfp_button = QPushButton("Upload PFP")
        self.pfp_button.setFixedHeight(20)
        self.pfp_button.clicked.connect(self.upload_pfp)
        profile_layout.addWidget(self.pfp_button)
        self.settings_button = QPushButton("⚙ SETTINGS")
        self.settings_button.setFixedHeight(24)
        self.settings_button.clicked.connect(self.open_settings)
        profile_layout.addWidget(self.settings_button)
        self.rename_button = QPushButton("CHANGE USERNAME")
        self.rename_button.setFixedHeight(22)
        self.rename_button.clicked.connect(self.rename_username)
        profile_layout.addWidget(self.rename_button)
        side.addWidget(profile)
        root.addWidget(self.sidebar)

        # ---------------- central chat ----------------
        self.chat_frame = QFrame(objectName="chat")
        chat_layout = QVBoxLayout(self.chat_frame)
        chat_layout.setContentsMargins(10, 8, 10, 10)
        chat_layout.setSpacing(5)

        # Server connection bar -- intentionally compact to match the original.
        self.server_bar = QFrame(objectName="serverBar")
        server_bar_layout = QHBoxLayout(self.server_bar)
        server_bar_layout.setContentsMargins(8, 7, 8, 7)
        server_bar_layout.setSpacing(5)
        server_label = QLabel("SERVER")
        server_label.setStyleSheet("color:#1E8C1E; font-size:10px; font-weight:700;")
        server_bar_layout.addWidget(server_label)
        self.server_ip_entry = QLineEdit(self.server_host)
        self.server_ip_entry.setFixedWidth(220)
        self.server_ip_entry.setFixedHeight(30)
        self.server_ip_entry.setPlaceholderText("IP address or hostname")
        server_bar_layout.addWidget(self.server_ip_entry)
        self.server_connect_btn = QPushButton("CONNECT")
        self.server_connect_btn.setFixedWidth(90)
        self.server_connect_btn.setFixedHeight(30)
        self.server_connect_btn.clicked.connect(self._manual_connect)
        server_bar_layout.addWidget(self.server_connect_btn)
        server_bar_layout.addStretch(1)
        self.server_status_label = QLabel("offline")
        server_bar_layout.addWidget(self.server_status_label)
        chat_layout.addWidget(self.server_bar)

        divider = QLabel("·" * 150)
        divider.setStyleSheet(f"color:{self.palette_colors()['border']}; font-family:Consolas; font-size:8px;")
        divider.setFixedHeight(10)
        chat_layout.addWidget(divider)

        header = QHBoxLayout()
        self.chat_title_label = QLabel("# general-chat")
        header.addWidget(self.chat_title_label)
        header.addStretch(1)
        self.chat_status_label = QLabel("offline")
        header.addWidget(self.chat_status_label)
        chat_layout.addLayout(header)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_content = QWidget()
        self.chat_content_layout = QVBoxLayout(self.chat_content)
        self.chat_content_layout.setContentsMargins(4, 4, 4, 4)
        self.chat_content_layout.setAlignment(Qt.AlignTop)
        self.chat_content_layout.setSpacing(2)
        self.chat_scroll.setWidget(self.chat_content)
        self._chat_wants_bottom = False
        self.chat_scroll.verticalScrollBar().rangeChanged.connect(
            self._on_chat_scroll_range_changed
        )
        chat_layout.addWidget(self.chat_scroll, 1)

        compose_wrap = QVBoxLayout()
        compose_wrap.setSpacing(4)

        self.reply_banner = QFrame(objectName="panelAlt")
        self.reply_banner.setVisible(False)
        reply_banner_layout = QHBoxLayout(self.reply_banner)
        reply_banner_layout.setContentsMargins(8, 4, 8, 4)
        reply_banner_layout.setSpacing(6)
        self.reply_banner_label = QLabel()
        self.reply_banner_label.setProperty("role", "muted")
        reply_banner_layout.addWidget(self.reply_banner_label, 1)
        self.reply_cancel_button = QPushButton("CANCEL")
        self.reply_cancel_button.setFixedSize(24, 20)
        self.reply_cancel_button.clicked.connect(self._clear_reply_target)
        reply_banner_layout.addWidget(self.reply_cancel_button)
        compose_wrap.addWidget(self.reply_banner)

        compose = QHBoxLayout()
        compose.setSpacing(6)
        self.message_entry = QLineEdit()
        self.message_entry.setPlaceholderText("Message #general-chat")
        self.message_entry.setFixedHeight(44)
        self.message_entry.returnPressed.connect(self.send_message)
        compose.addWidget(self.message_entry, 1)
        self.file_button = QPushButton("FILE")
        self.file_button.setFixedSize(58, 44)
        self.file_button.clicked.connect(self.choose_file_to_send)
        compose.addWidget(self.file_button)
        self.poll_button = QPushButton("POLL")
        self.poll_button.setFixedSize(58, 44)
        self.poll_button.clicked.connect(self.create_poll)
        compose.addWidget(self.poll_button)
        self.send_button = QPushButton("SEND")
        self.send_button.setFixedSize(80, 44)
        self.send_button.clicked.connect(self.send_message)
        compose.addWidget(self.send_button)
        compose_wrap.addLayout(compose)
        chat_layout.addLayout(compose_wrap)
        root.addWidget(self.chat_frame, 1)

        # ---------------- right member panel ----------------
        self.members = QFrame(objectName="panel")
        self.members.setFixedWidth(180)
        mem = QVBoxLayout(self.members)
        mem.setContentsMargins(10, 10, 10, 10)
        mem.setSpacing(5)
        self.voice_header = QLabel("IN VOICE")
        mem.addWidget(self.voice_header)
        self.voice_user_list = QListWidget()
        self.voice_user_list.setFixedHeight(125)
        mem.addWidget(self.voice_user_list)
        self.voice_radar_label = QLabel("VOICE RADAR\nno active speakers")
        self.voice_radar_label.setProperty("role", "muted")
        self.voice_radar_label.setWordWrap(True)
        self.voice_radar_label.setMinimumHeight(70)
        mem.addWidget(self.voice_radar_label)
        self.members_header = QLabel("MEMBERS")
        mem.addWidget(self.members_header)
        self.members_list = QListWidget()
        mem.addWidget(self.members_list, 1)
        root.addWidget(self.members)

        # ---------------- in-app settings overlay ----------------
        self.settings_overlay = QWidget(self)
        self.settings_overlay.hide()
        self.settings_overlay.setStyleSheet("background: rgba(0,0,0,210);")
        self.settings_overlay.raise_()

        self._refresh_profile_label()
        self._refresh_dm_list()
        self.reload_current_chat_view()
        self._build_settings_panel()
        self._apply_widget_theme(self.palette_colors())

    def _build_settings_panel(self):
        # Full in-app NETRA settings panel.  The content itself scrolls; the
        # bottom SAVE/CLOSE bar stays visible and no longer duplicates controls.
        self.settings_panel = QFrame(self.settings_overlay, objectName="settingsPanel")
        self.settings_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        outer = QVBoxLayout(self.settings_panel)
        outer.setContentsMargins(14, 12, 14, 10)
        outer.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("NETRA // SETTINGS")
        title.setProperty("role", "title")
        title_row.addWidget(title)
        title_row.addStretch(1)
        close = QPushButton("CLOSE")
        close.setFixedSize(90, 32)
        close.clicked.connect(self.close_settings)
        title_row.addWidget(close)
        outer.addLayout(title_row)

        saved_label = QLabel(f"Saved automatically to: {SETTINGS_FILE}")
        saved_label.setProperty("role", "muted")
        saved_label.setWordWrap(True)
        outer.addWidget(saved_label)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(scroll, 1)
        self.settings_scroll = scroll

        body = QWidget()
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 2, 0, 10)
        body_layout.setSpacing(10)
        scroll.setWidget(body)
        self.settings_body = body

        def section(title_text):
            frame = QFrame(objectName="settingsSection")
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(7)
            label = QLabel(title_text)
            label.setProperty("role", "heading")
            layout.addWidget(label)
            return frame, layout

        # ---- General ----
        general, gl = section("GENERAL")
        row = QHBoxLayout()
        row.addWidget(QLabel("Theme"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setCurrentText(self.theme_name)
        self.theme_combo.currentTextChanged.connect(self.change_theme)
        row.addWidget(self.theme_combo, 1)
        gl.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("DM notification"))
        self.sound_combo = QComboBox()
        self.sound_combo.addItems(["ping", "ping_2", "ping_3", "ping_4", "ping_5", "off"])
        self.sound_combo.setCurrentText(self.settings.get("dm_sound_mode", "ping"))
        row.addWidget(self.sound_combo, 1)
        gl.addLayout(row)
        body_layout.addWidget(general)

        # ---- Voice devices ----
        devices, vl = section("VOICE")
        row = QHBoxLayout()
        row.addWidget(QLabel("Microphone"))
        self.input_device_combo = QComboBox()
        self.input_device_combo.addItems(self._audio_input_options())
        self.input_device_combo.setCurrentText(self._audio_option_for_saved(self.settings.get("voice_input_device"), self.input_device_combo))
        row.addWidget(self.input_device_combo, 1)
        vl.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Output / speakers"))
        self.output_device_combo = QComboBox()
        self.output_device_combo.addItems(self._audio_output_options())
        self.output_device_combo.setCurrentText(self._audio_option_for_saved(self.settings.get("voice_output_device"), self.output_device_combo))
        row.addWidget(self.output_device_combo, 1)
        vl.addLayout(row)

        self.voice_test_status = QLabel("Select a microphone, then test it before joining a call.")
        self.voice_test_status.setProperty("role", "muted")
        self.voice_test_status.setWordWrap(True)
        vl.addWidget(self.voice_test_status)

        test_row = QHBoxLayout()
        test_btn = QPushButton("TEST MICROPHONE (3 SEC)")
        test_btn.setFixedHeight(30)
        test_btn.clicked.connect(self._test_microphone)
        test_row.addWidget(test_btn)
        test_row.addStretch(1)
        vl.addLayout(test_row)
        body_layout.addWidget(devices)

        # ---- Voice 2.0 ----
        v2, v2_layout = section("VOICE 2.0")
        self.voice_toggle_button = QPushButton("＋  VOICE 2.0  —  EXPAND")
        self.voice_toggle_button.setCheckable(True)
        self.voice_toggle_button.clicked.connect(self._toggle_voice_settings)
        v2_layout.addWidget(self.voice_toggle_button)

        self.voice_settings_content = QWidget()
        content_layout = QVBoxLayout(self.voice_settings_content)
        content_layout.setContentsMargins(0, 6, 0, 0)
        content_layout.setSpacing(7)

        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Master voice volume"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 200)
        self.volume_slider.setValue(int(self.voice_volume * 100))
        self.voice_volume_value = QLabel(f"{int(self.voice_volume*100)}%")
        self.volume_slider.valueChanged.connect(lambda v: self.voice_volume_value.setText(f"{int(v)}%"))
        vol_row.addWidget(self.volume_slider, 1)
        vol_row.addWidget(self.voice_volume_value)
        content_layout.addLayout(vol_row)

        gain_row = QHBoxLayout()
        gain_row.addWidget(QLabel("Microphone gain"))
        self.mic_slider = QSlider(Qt.Horizontal)
        self.mic_slider.setRange(0, 200)
        self.mic_slider.setValue(int(self.voice_mic_gain * 100))
        self.voice_gain_value = QLabel(f"{int(self.voice_mic_gain*100)}%")
        self.mic_slider.valueChanged.connect(lambda v: self.voice_gain_value.setText(f"{int(v)}%"))
        gain_row.addWidget(self.mic_slider, 1)
        gain_row.addWidget(self.voice_gain_value)
        content_layout.addLayout(gain_row)

        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel("Quality"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Low", "Balanced", "High", "Ultra"])
        self.quality_combo.setCurrentText(self.voice_quality)
        quality_row.addWidget(self.quality_combo)
        quality_row.addStretch(1)
        content_layout.addLayout(quality_row)

        for label, attr in [
            ("Noise gate", "voice_noise_gate"),
            ("Automatic gain control", "voice_agc"),
            ("Echo guard", "voice_echo_guard"),
            ("Push-to-talk (Right Ctrl)", "voice_ptt"),
            ("Deafen", "voice_deafened"),
            ("Record received voice to WAV", "voice_recording"),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(bool(getattr(self, attr)))
            cb.stateChanged.connect(lambda value, a=attr: setattr(self, a, bool(value)))
            content_layout.addWidget(cb)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Voice profile"))
        self.voice_profile_combo = QComboBox()
        self.voice_profile_combo.addItems(["Casual", "Clear Voice", "Recording", "Low Bandwidth"])
        self.voice_profile_combo.setCurrentText(self.settings.get("voice_profile", "Recording"))
        self.voice_profile_combo.currentTextChanged.connect(self._apply_voice_profile)
        profile_row.addWidget(self.voice_profile_combo)
        content_layout.addLayout(profile_row)

        self.voice_stats_label = QLabel("Voice stats: waiting for a call")
        self.voice_stats_label.setProperty("role", "muted")
        self.voice_stats_label.setWordWrap(True)
        content_layout.addWidget(self.voice_stats_label)

        users_header = QLabel("Per-user volume / mute")
        users_header.setProperty("role", "muted")
        content_layout.addWidget(users_header)
        self.voice_users_settings = QWidget()
        self.voice_users_settings_layout = QVBoxLayout(self.voice_users_settings)
        self.voice_users_settings_layout.setContentsMargins(0, 0, 0, 0)
        self.voice_users_settings_layout.setSpacing(3)
        content_layout.addWidget(self.voice_users_settings)

        self.voice_settings_content.hide()
        v2_layout.addWidget(self.voice_settings_content)
        body_layout.addWidget(v2)

        # ---- NETRA HUB ----
        hub, hl = section("NETRA HUB")
        hub_grid = QGridLayout()
        hub_grid.setHorizontalSpacing(8)
        hub_grid.setVerticalSpacing(8)
        hub_grid.setColumnStretch(0, 1)
        hub_grid.setColumnStretch(1, 1)
        actions = [
            ("PROFILE / PFP", self.upload_pfp),
            ("CHANGE USERNAME", self.rename_username),
            ("THEMES", lambda: self.theme_combo.setFocus()),
            ("FULLSCREEN", self.toggle_fullscreen),
        ]
        for i, (label, fn) in enumerate(actions):
            b = QPushButton(label)
            b.setFixedHeight(28)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setStyleSheet("padding: 2px 4px; font-size: 10px;")
            b.clicked.connect(fn)
            hub_grid.addWidget(b, i // 2, i % 2)
        hl.addLayout(hub_grid)
        body_layout.addWidget(hub)
        end_marker = QLabel("— END OF SETTINGS —")
        end_marker.setAlignment(Qt.AlignCenter)
        end_marker.setProperty("role", "muted")
        end_marker.setMinimumHeight(34)
        body_layout.addWidget(end_marker)
        body_layout.addSpacing(20)

        # ---- fixed footer (always visible) ----
        footer = QFrame(objectName="settingsFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(8)
        self.settings_status = QLabel("Changes are not permanent until SAVE SETTINGS is pressed.")
        self.settings_status.setProperty("role", "muted")
        footer_layout.addWidget(self.settings_status, 1)
        save_btn = QPushButton("SAVE SETTINGS")
        save_btn.setFixedHeight(32)
        save_btn.setFixedWidth(118)
        save_btn.clicked.connect(self.save_settings_from_ui)
        footer_layout.addWidget(save_btn)
        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(32)
        close_btn.setFixedWidth(78)
        close_btn.clicked.connect(self.close_settings)
        footer_layout.addWidget(close_btn)
        outer.addWidget(footer)
    def _test_microphone(self):
        """Run a bounded microphone test without blocking the Qt GUI thread."""
        if not SOUNDDEVICE_AVAILABLE:
            self.voice_test_signals.result.emit(
                "sounddevice is not installed. Install it with: python -m pip install sounddevice",
                True,
            )
            return

        in_device = self._audio_selection_to_index(self.input_device_combo.currentText())
        out_device = self._audio_selection_to_index(self.output_device_combo.currentText())
        self.voice_test_status.setText("Testing microphone + playback for 3 seconds…")
        self.voice_test_status.setProperty("role", "muted")
        self.voice_test_status.style().unpolish(self.voice_test_status)
        self.voice_test_status.style().polish(self.voice_test_status)

        def worker():
            input_stream = None
            try:
                in_info = sd.query_devices(in_device, "input")
                out_info = sd.query_devices(out_device, "output")
                in_channels = int(in_info.get("max_input_channels", 0) or 0)
                out_channels = int(out_info.get("max_output_channels", 0) or 0)
                if in_channels < 1:
                    raise RuntimeError(f"Selected microphone has no input channels: {in_info.get('name', 'unknown')}")
                if out_channels < 1:
                    raise RuntimeError(f"Selected output has no output channels: {out_info.get('name', 'unknown')}")

                rate = max(8000, int(round(float(in_info.get("default_samplerate") or 48000))))
                out_rate = max(8000, int(round(float(out_info.get("default_samplerate") or 48000))))
                sd.check_input_settings(device=in_device, samplerate=rate, channels=1, dtype="int16")
                sd.check_output_settings(device=out_device, samplerate=out_rate, channels=1, dtype="int16")

                chunks = []
                target_seconds = 3.0

                def callback(indata, frames, time_info, status):
                    if status:
                        # Keep capture alive; the final status text will still
                        # report the measured signal level.
                        pass
                    chunks.append(bytes(indata))

                input_stream = sd.InputStream(
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    device=in_device,
                    blocksize=1024,
                    callback=callback,
                    latency="low",
                )
                input_stream.start()

                # Hard wall-clock bound: even if a driver behaves badly, this
                # worker will leave the capture state after a little over 3 sec.
                deadline = time.monotonic() + target_seconds + 0.35
                while time.monotonic() < deadline:
                    time.sleep(0.05)

                try:
                    input_stream.stop()
                finally:
                    input_stream.close()
                    input_stream = None

                raw = b"".join(chunks)
                count = len(raw) // 2
                values = struct.unpack(f"<{count}h", raw[:count * 2]) if count else ()
                peak = max((abs(v) for v in values), default=0)
                rms = math.sqrt(sum(v * v for v in values) / max(1, len(values)))
                db_peak = -60.0 if peak <= 0 else 20.0 * math.log10(peak / 32768.0)
                db_rms = -60.0 if rms <= 0 else 20.0 * math.log10(rms / 32768.0)

                # Use the same RawOutputStream path as NETRA voice chat instead
                # of sd.play(). This is much more reliable for explicitly selected
                # Windows/WASAPI devices and also proves the exact output path that
                # real VC uses.
                playback_error = None
                playback_stream = None
                if raw:
                    try:
                        playback = resample_pcm16_mono(raw, rate, out_rate)
                        playback_stream = sd.RawOutputStream(
                            samplerate=out_rate,
                            channels=1,
                            dtype="int16",
                            device=out_device,
                            blocksize=1024,
                            latency="low",
                        )
                        playback_stream.start()

                        # Write the complete recording in bounded chunks. RawOutputStream
                        # accepts the same signed-16-bit byte format used by VC.
                        chunk_bytes = 1024 * 2
                        for start in range(0, len(playback), chunk_bytes):
                            playback_stream.write(playback[start:start + chunk_bytes])

                    except Exception as exc:
                        playback_error = exc
                    finally:
                        try:
                            if playback_stream is not None:
                                playback_stream.stop()
                                playback_stream.close()
                        except Exception:
                            pass

                if peak <= 100:
                    msg = (
                        "✗ Microphone opened, but almost no signal was captured "
                        f"(peak {peak}). Check Windows mic permissions / mute state."
                    )
                    if playback_error:
                        msg += f" Playback also failed: {type(playback_error).__name__}: {playback_error}"
                    self.voice_test_signals.result.emit(msg, True)
                elif playback_error:
                    msg = (
                        "✓ Mic capture complete // "
                        f"peak {peak} ({db_peak:.1f} dBFS) // RMS {db_rms:.1f} dBFS // "
                        f"Playback failed: {type(playback_error).__name__}: {playback_error}"
                    )
                    self.voice_test_signals.result.emit(msg, True)
                else:
                    msg = (
                        "✓ Mic test complete + playback verified // "
                        f"peak {peak} ({db_peak:.1f} dBFS) // RMS {db_rms:.1f} dBFS"
                    )
                    self.voice_test_signals.result.emit(msg, False)
            except Exception as exc:
                try:
                    if input_stream is not None:
                        input_stream.stop()
                        input_stream.close()
                except Exception:
                    pass
                try:
                    sd.stop()
                except Exception:
                    pass
                self.voice_test_signals.result.emit(
                    f"✗ Microphone test failed: {type(exc).__name__}: {exc}",
                    True,
                )

        threading.Thread(target=worker, daemon=True, name="NETRA-Mic-Test").start()

    def _apply_voice_test_status(self, text, error):
        self.voice_test_status.setText(text)
        self.voice_test_status.setProperty("role", "error" if error else "muted")
        self.voice_test_status.style().unpolish(self.voice_test_status)
        self.voice_test_status.style().polish(self.voice_test_status)

    def _set_voice_test_status(self, text, error):
        self.voice_test_signals.result.emit(text, error)

    # ---------- dialogs / settings ----------

    def _manual_connect(self):
        host = self.server_ip_entry.text().strip() if hasattr(self, "server_ip_entry") else self.server_host
        if not host:
            self.server_status_label.setText("enter a server address")
            return
        self.server_host = host
        self.settings["server_host"] = host
        save_settings(self.settings)
        if self._last_password:
            self.connect_and_auth(self._last_auth_mode or "LOGIN", self.username, self._last_password)
        else:
            self.show_auth()

    def show_auth(self):
        if self.authenticated:
            return
        self.auth_dialog = AuthDialog(self, self.username)
        self.auth_dialog.authenticated.connect(self.connect_and_auth)
        self.auth_dialog.exec()

    def open_settings(self):
        self.settings_overlay.setGeometry(self.rect())
        panel_w = min(860, max(620, self.width() - 24))
        panel_h = max(520, self.height() - 24)
        self.settings_panel.setGeometry(
            max(12, (self.width() - panel_w) // 2),
            12,
            panel_w,
            panel_h,
        )
        QTimer.singleShot(0, self._scroll_settings_to_top)
        self.settings_overlay.show()
        self.settings_overlay.raise_()
        self._refresh_voice_user_settings()

    def close_settings(self):
        self.settings_overlay.hide()

    def _scroll_settings_to_top(self):
        if hasattr(self, "settings_scroll"):
            self.settings_scroll.verticalScrollBar().setValue(0)

    def _toggle_voice_settings(self, checked):
        self.voice_settings_content.setVisible(bool(checked))
        self.voice_toggle_button.setText("－  VOICE 2.0  —  COLLAPSE" if checked else "＋  VOICE 2.0  —  EXPAND")
        self._refresh_voice_user_settings()
        if hasattr(self, "settings_body"):
            self.settings_body.adjustSize()
        QTimer.singleShot(0, lambda: self.settings_body.adjustSize() if hasattr(self, "settings_body") else None)

    def _audio_input_options(self):
        return self._audio_device_options(want_input=True)

    def _audio_output_options(self):
        return self._audio_device_options(want_input=False)

    def _audio_device_options(self, want_input):
        options = ["Default"]
        if not SOUNDDEVICE_AVAILABLE:
            return options
        try:
            devices = sd.query_devices()
            key = "max_input_channels" if want_input else "max_output_channels"
            for idx, device in enumerate(devices):
                if int(device.get(key, 0)) > 0:
                    options.append(f"[{idx}] {str(device.get('name', '')).strip()}")
        except Exception:
            pass
        return options

    def _audio_option_for_saved(self, saved_value, combo):
        if saved_value is None or saved_value == "":
            return "Default"
        if isinstance(saved_value, int):
            prefix = f"[{saved_value}]"
            for i in range(combo.count()):
                if combo.itemText(i).startswith(prefix):
                    return combo.itemText(i)
            return "Default"
        if isinstance(saved_value, str):
            if saved_value.startswith("[") and "]" in saved_value:
                try:
                    idx = int(saved_value[1:saved_value.index("]")])
                    return self._audio_option_for_saved(idx, combo)
                except Exception:
                    pass
            for i in range(combo.count()):
                if combo.itemText(i) == saved_value or combo.itemText(i).endswith(" " + saved_value):
                    return combo.itemText(i)
        return "Default"

    @staticmethod
    def _audio_selection_to_index(text):
        if not text or text == "Default":
            return None
        if text.startswith("[") and "]" in text:
            try:
                return int(text[1:text.index("]")])
            except Exception:
                return None
        return None

    def _apply_voice_profile(self, name):
        profiles = {
            "Casual": {"voice_quality": "High",
        "voice_profile": "Recording", "voice_volume": 1.25, "voice_mic_gain": 1.0, "voice_noise_gate": True, "voice_agc": True},
            "Clear Voice": {"voice_quality": "Ultra", "voice_volume": 1.20, "voice_mic_gain": 1.10, "voice_noise_gate": True, "voice_agc": True},
            "Recording": {"voice_quality": "Ultra", "voice_volume": 1.00, "voice_mic_gain": 0.90, "voice_noise_gate": False, "voice_agc": False},
            "Low Bandwidth": {"voice_quality": "Low", "voice_volume": 1.25, "voice_mic_gain": 1.0, "voice_noise_gate": True, "voice_agc": True},
        }
        cfg = profiles.get(name)
        if not cfg or not hasattr(self, "quality_combo"):
            return
        self.voice_quality = cfg["voice_quality"]
        self.voice_volume = cfg["voice_volume"]
        self.voice_mic_gain = cfg["voice_mic_gain"]
        self.voice_noise_gate = cfg["voice_noise_gate"]
        self.voice_agc = cfg["voice_agc"]
        self.quality_combo.setCurrentText(self.voice_quality)
        self.volume_slider.setValue(int(self.voice_volume * 100))
        self.mic_slider.setValue(int(self.voice_mic_gain * 100))
        self.settings["voice_profile"] = name

    def save_settings_from_ui(self):
        self.voice_volume = self.volume_slider.value() / 100.0
        self.voice_mic_gain = self.mic_slider.value() / 100.0
        self.voice_quality = self.quality_combo.currentText()
        self.settings.update({
            "theme": self.theme_name,
            "dm_sound_mode": self.sound_combo.currentText(),
            "dm_sound_path": self.settings.get("dm_sound_path", ""),
            "voice_input_device": self._audio_selection_to_index(self.input_device_combo.currentText()),
            "voice_output_device": self._audio_selection_to_index(self.output_device_combo.currentText()),
            "voice_profile": self.voice_profile_combo.currentText() if hasattr(self, "voice_profile_combo") else self.settings.get("voice_profile", "Recording"),
            "voice_volume": self.voice_volume,
            "voice_mic_gain": self.voice_mic_gain,
            "voice_quality": self.voice_quality,
            "voice_noise_gate": self.voice_noise_gate,
            "voice_agc": self.voice_agc,
            "voice_echo_guard": self.voice_echo_guard,
            "voice_deafen": self.voice_deafened,
            "voice_ptt": self.voice_ptt,
            "voice_record": self.voice_recording,
            "voice_user_volumes": self.voice_user_volumes,
            "voice_user_mutes": self.voice_user_mutes,
        })
        save_settings(self.settings)
        self.settings_status.setText("✓ SETTINGS SAVED")
        self._refresh_voice_user_settings()

    def change_theme(self, name):
        if name not in THEMES:
            return
        self.theme_name = name
        self.settings["theme"] = name
        save_settings(self.settings)
        self._apply_theme()
        if hasattr(self, "settings_overlay"):
            self.settings_overlay.setStyleSheet("background: rgba(0,0,0,210);")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and self.settings_overlay.isVisible():
            self.close_settings()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
            event.accept()
            return
        if event.key() == Qt.Key_Control and self.voice_ptt:
            self.voice_ptt_down = True
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control and self.voice_ptt:
            self.voice_ptt_down = False
        super().keyReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "settings_overlay"):
            self.settings_overlay.setGeometry(self.rect())
            if hasattr(self, "settings_panel"):
                panel_w = min(860, max(620, self.width() - 24))
                panel_h = max(520, self.height() - 24)
                self.settings_panel.setGeometry(
                    max(12, (self.width() - panel_w) // 2),
                    12,
                    panel_w,
                    panel_h,
                )

    # ---------- persistence ----------

    def _load_chat_cache(self):
        try:
            with open(CHAT_CACHE_FILE, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                for room, messages in raw.items():
                    if isinstance(messages, list):
                        self.chat_history[room] = messages[-500:]
        except Exception:
            pass

    def _save_chat_cache(self):
        try:
            payload = {room: messages[-500:] for room, messages in self.chat_history.items()}
            with open(CHAT_CACHE_FILE, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_profile_image(self):
        for path in (PROFILE_IMAGE_FILE, os.path.join(CONFIG_DIR, "pfp.png")):
            if os.path.exists(path):
                try:
                    return Image.open(path).convert("RGB")
                except Exception:
                    pass
        return Image.new("RGB", (96, 96), "#0F3D0F")

    def _refresh_profile_label(self):
        if not hasattr(self, "pfp_label"):
            return
        image = self.pil_to_pixmap(self.pil_profile, (46, 46))
        self.pfp_label.setPixmap(image)
        self.username_label.setText(self.username)

    def pil_to_pixmap(self, image: Image.Image, size):
        img = image.copy()
        img.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", size, "#101010")
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        canvas.paste(img, (x, y))
        raw = canvas.tobytes("raw", "RGB")
        pix = QPixmap()
        # QImage imports lazily to keep the top-level list manageable.
        from PySide6.QtGui import QImage
        qimg = QImage(raw, size[0], size[1], size[0] * 3, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())

    def upload_pfp(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Profile Picture", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        try:
            img = Image.open(path).convert("RGB")
            img.save(PROFILE_IMAGE_FILE, "PNG")
            self.pil_profile = img
            self.user_pfps[self.username] = img
            self._refresh_profile_label()
            self._refresh_member_list()
            self._refresh_voice_users()
            self.send_own_pfp()
        except Exception as exc:
            self.show_error(str(exc))

    def send_own_pfp(self):
        if not self.client_socket or not self.authenticated:
            return
        try:
            buf = io.BytesIO()
            self.pil_profile.save(buf, format="PNG")
            payload = base64.b64encode(buf.getvalue()).decode("ascii")
            self.client_socket.sendall(f"PFP:{payload}\n".encode("ascii"))
        except Exception:
            pass

    # ---------- network ----------

    def connect_and_auth(self, mode, username, password, silent=False):
        self.username = username or self.username
        if mode == "OFFLINE":
            self.offline_mode = True
            self.authenticated = False
            self._stop_reconnect_timer()
            if self.auth_dialog:
                self.auth_dialog.accept()
                self.auth_dialog = None
            self.server_status_label.setText("offline mode")
            self.chat_status_label.setText("offline mode // cached data")
            self.reload_current_chat_view()
            return
        self.offline_mode = False
        self._last_password = password
        self._last_auth_mode = mode
        # Keep the server selected by the user instead of resetting to the public default.
        self.server_host = str(self.server_host).strip() or DEFAULT_HOST
        try:
            self.server_port = int(self.server_port)
        except (TypeError, ValueError):
            self.server_port = PORT
        if not 1 <= self.server_port <= 65535:
            self.server_port = PORT
        self.settings["server_host"] = self.server_host
        self.settings["server_port"] = self.server_port
        save_settings(self.settings)
        if hasattr(self, "server_ip_entry"):
            self.server_ip_entry.setText(self.server_host)
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.server_host, self.server_port))
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass
            sock.settimeout(None)
            self.client_socket = sock
            self._reconnect_attempts = 0
            encoded = base64.b64encode(password.encode("utf-8")).decode("ascii")
            sock.sendall(f"{mode}:{username}:{encoded}\n".encode("utf-8"))
            if self.network_worker:
                self.network_worker.stop()
            self.network_worker = NetworkWorker(sock)
            self.network_worker.line_received.connect(self._handle_network_line)
            self.network_worker.failed.connect(self._network_error)
            self.network_worker.disconnected.connect(self._network_disconnected)
            self.network_worker.start()
        except Exception as exc:
            if self.auth_dialog:
                self.auth_dialog.status.setText(f"Could not connect: {exc}")
            else:
                self.show_error(str(exc))

    def _network_error(self, message):
        self.chat_status_label.setText("network error // offline cache active")
        if not self.authenticated and self.auth_dialog:
            self.auth_dialog.status.setText(message)
        if self._last_password and not self.offline_mode:
            self._start_smart_reconnect()

    def _network_disconnected(self):
        self.stop_screen_share()
        self._stop_screen_relay()
        self.screen_token = ""
        self.authenticated = False
        if self.offline_mode:
            self.server_status_label.setText("offline mode")
            self.chat_status_label.setText("offline mode // cached data")
            return
        self.server_status_label.setText("disconnected // reconnecting")
        self.chat_status_label.setText("disconnected // cached data available")
        self._start_smart_reconnect()

    def _start_smart_reconnect(self):
        if self.offline_mode or not self.username or not self._last_password:
            return
        if not self._reconnect_timer.isActive():
            self._reconnect_attempts = 0
            self._reconnect_timer.start()

    def _stop_reconnect_timer(self):
        if self._reconnect_timer.isActive():
            self._reconnect_timer.stop()

    def _attempt_smart_reconnect(self):
        if self.offline_mode or self.authenticated or not self._last_password:
            self._stop_reconnect_timer()
            return
        self._reconnect_attempts += 1
        self.server_status_label.setText(f"reconnecting... attempt {self._reconnect_attempts}")
        try:
            self.connect_and_auth(self._last_auth_mode, self.username, self._last_password, silent=True)
        except Exception:
            pass

    def _handle_network_line(self, raw):
        self.incoming_queue.put(raw)

    def _process_incoming_queue(self):
        processed = 0
        while processed < 80:
            try:
                raw = self.incoming_queue.get_nowait()
            except queue.Empty:
                break
            self.handle_incoming_line(raw)
            processed += 1

    def handle_incoming_line(self, raw):
        my_name = self.username

        if raw.startswith("AUTH_OK:"):
            parts = raw.split(":", 2)
            if len(parts) == 3:
                self.account_id = parts[1]
                self.username = parts[2]
                self.authenticated = True
                self.offline_mode = False
                self._stop_reconnect_timer()
                # The server sends a burst of history immediately after AUTH_OK.
                # Defer all expensive chat widget rebuilding and disk writes until
                # READY so the Qt GUI remains responsive during login.
                self.loading_history = True
                self.username_label.setText(self.username)
                try:
                    set_key(ENV_FILE, "CHAT_USERNAME", self.username)
                    set_key(ENV_FILE, "NETRA_ACCOUNT_ID", self.account_id)
                except Exception:
                    pass
                if self.auth_dialog:
                    self.auth_dialog.accept()
                    self.auth_dialog = None
                self.chat_status_label.setText("connected")
                self.send_own_pfp()
                caps = "VOICE,SCREENSHARE,MESSAGE_IDS,MESSAGE_ACK,TYPING,PRESENCE,HEARTBEAT,RATE_LIMIT"
                self._network_send(f"HELLO:2:{caps}", queue_offline=False)
            return

        if raw.startswith("AUTH_FAIL:"):
            reason = raw.split(":", 1)[1]
            self._stop_reconnect_timer()
            if self.auth_dialog:
                self.auth_dialog.status.setText(reason)
            elif not self.offline_mode:
                self.chat_status_label.setText(f"reconnect stopped // {reason}")
            return

        if raw.startswith("SCREEN_TOKEN:"):
            parts = raw.split(":", 2)
            if len(parts) == 3:
                self.screen_token = parts[1]
                try:
                    self.screen_port = int(parts[2])
                except ValueError:
                    self.screen_port = SCREEN_PORT_DEFAULT
                self._connect_screen_relay()
            return

        if raw.startswith("SCREEN_VIEWERS:"):
            self.screen_viewers = {u for u in raw.split(":", 1)[1].split(",") if u}
            return

        if raw.startswith("PING:"):
            self._network_send("PONG:" + raw.split(":", 1)[1], queue_offline=False)
            return

        if raw.startswith("PROTOCOL:") or raw.startswith("PROTOCOL_OK:"):
            parts = raw.split(":", 2)
            if len(parts) >= 2:
                try:
                    self.server_protocol_version = int(parts[1])
                except ValueError:
                    self.server_protocol_version = 1
                self.server_capabilities = set(parts[2].split(",")) if len(parts) == 3 else set()
            return

        if raw.startswith("RATE_LIMITED:"):
            self.chat_status_label.setText("rate limited // slow down")
            return

        if raw.startswith("MESSAGE_ACK:"):
            p = raw.split(":", 2)
            if len(p) == 3:
                client_id, server_id = p[1], p[2]
                self._reconcile_server_message_id(client_id, server_id)
            return

        if raw.startswith("PRESENCE_SNAPSHOT:"):
            snapshot = raw.split(":", 1)[1]
            self.presence_status.clear()
            self.custom_status.clear()
            for item in snapshot.split("\x1e"):
                bits = item.split("\x1f", 2)
                if len(bits) == 3 and bits[0]:
                    self.presence_status[bits[0]] = bits[1]
                    self.custom_status[bits[0]] = bits[2]
            self._refresh_member_list()
            return

        if raw.startswith("PRESENCE:"):
            p = raw.split(":", 3)
            if len(p) >= 3:
                self.presence_status[p[1]] = p[2]
                self.custom_status[p[1]] = p[3] if len(p) == 4 else ""
                self._refresh_member_list()
            return

        if raw.startswith("SCREENSHARE_SNAPSHOT:"):
            self.screen_share_status = {}
            for item in raw.split(":", 1)[1].split("\x1e"):
                bits = item.split("\x1f", 2)
                if len(bits) == 3 and bits[0]:
                    self.screen_share_status[bits[0]] = {"fps": bits[1], "quality": bits[2]}
            return

        if raw.startswith("SCREENSHARE:STARTED:"):
            p = raw.split(":", 4)
            if len(p) >= 4:
                user = p[1]
                self.screen_share_status = getattr(self, "screen_share_status", {})
                self.screen_share_status[user] = {"fps": p[2], "quality": p[3] if len(p) > 3 else "68"}
                self._refresh_member_list()
            return

        if raw.startswith("SCREENSHARE:STOPPED:"):
            user = raw.split(":", 1)[1]
            getattr(self, "screen_share_status", {}).pop(user, None)
            self._refresh_member_list()
            return

        if raw.startswith("RENAME_OK:"):
            parts = raw.split(":", 2)
            if len(parts) == 3:
                self.username = parts[2]
                self.username_label.setText(self.username)
                try:
                    set_key(ENV_FILE, "CHAT_USERNAME", self.username)
                except Exception:
                    pass
                self._refresh_dm_list()
            return

        if raw.startswith("VOICEUSERS:"):
            self.voice_users = [u for u in raw.split(":", 1)[1].split(",") if u]
            self._refresh_voice_users()
            return

        if raw.startswith("VOICE:"):
            if not self.in_voice_chat:
                return
            try:
                parts = raw.split(":", 3)
                if len(parts) == 4:
                    sender = parts[1]
                    sender_rate = int(parts[2])
                    encoded = parts[3]
                else:
                    # Older relay format: VOICE:<sender>:<base64_pcm>
                    old = raw.split(":", 2)
                    if len(old) != 3:
                        return
                    sender = old[1]
                    sender_rate = self._voice_rate()
                    encoded = old[2]
                if sender == my_name:
                    return
                pcm = base64.b64decode(encoded, validate=True)
                if pcm:
                    try:
                        self.voice_play_queue.put_nowait((sender, sender_rate, pcm))
                    except queue.Full:
                        try:
                            self.voice_play_queue.get_nowait()
                            self.voice_play_queue.put_nowait((sender, sender_rate, pcm))
                        except Exception:
                            pass
            except Exception:
                pass
            return

        if raw.startswith("USERS:"):
            self.last_registered_users = [u for u in raw.split(":", 1)[1].split(",") if u]
            self._refresh_member_list()
            self._refresh_dm_list()
            return

        if raw.startswith("ONLINE:"):
            self.online_users = {u for u in raw.split(":", 1)[1].split(",") if u}
            self._refresh_member_list()
            return

        if raw.startswith("HISTORY:"):
            try:
                payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
                msg = self.store_message(
                    payload.get("room", "general-chat"),
                    payload.get("sender", "?"),
                    payload.get("text", ""),
                    local=False,
                    message_id=payload.get("id"),
                    reply_to=payload.get("reply_to"),
                    reactions=payload.get("reactions") or {},
                    kind=payload.get("kind", "message"),
                    file_meta=payload.get("file"),
                    poll=payload.get("poll"),
                )
                if payload.get("file"):
                    self._register_file_metadata(payload.get("file"), msg)
            except Exception:
                pass
            return

        if raw.startswith("MESSAGE:"):
            try:
                payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
                room_name = payload.get("room", "general-chat")
                incoming_id = payload.get("id")
                client_id = payload.get("client_id")
                if payload.get("sender") == my_name and client_id:
                    if self._reconcile_server_message_id(client_id, incoming_id, room_name=room_name):
                        return
                msg = self.store_message(
                    room_name,
                    payload.get("sender", "?"),
                    payload.get("text", ""),
                    local=False,
                    message_id=incoming_id,
                    reply_to=payload.get("reply_to"),
                    reactions=payload.get("reactions") or {},
                    kind=payload.get("kind", "message"),
                    file_meta=payload.get("file"),
                    poll=payload.get("poll"),
                )
                if payload.get("file"):
                    self._register_file_metadata(payload.get("file"), msg)
                if payload.get("sender") != my_name:
                    self.play_ping_sound()
            except Exception:
                pass
            return

        if raw.startswith("FILE_OFFER:"):
            self._handle_file_offer(raw)
            return

        if raw.startswith("FILE_REQUEST:"):
            self._handle_file_request(raw)
            return

        if raw.startswith("FILE_CHUNK:"):
            self._handle_file_chunk(raw)
            return

        if raw.startswith("FILE_DONE:"):
            self._handle_file_done(raw)
            return

        if raw.startswith("POLL:"):
            self._handle_poll_event(raw)
            return

        if raw.startswith("POLL_VOTE:"):
            self._handle_poll_vote(raw)
            return

        if raw.startswith("REACTION:"):
            try:
                payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
                room = payload.get("room", "general-chat")
                mid = payload.get("message_id")
                emoji = payload.get("emoji", "")
                user = payload.get("user", "")
                for msg in self.chat_history.get(room, []):
                    if msg.get("id") == mid:
                        reactions = msg.setdefault("reactions", {})
                        users = reactions.setdefault(emoji, [])
                        active = bool(payload.get("active", True))
                        if active:
                            if user and user not in users:
                                users.append(user)
                        else:
                            if user in users:
                                users.remove(user)
                            if not users:
                                reactions.pop(emoji, None)
                        self._update_message_card(mid, reactions)
                        self._chat_cache_dirty = True
                        break
            except Exception:
                pass
            return

        if raw.startswith("MESSAGE_DELETED:"):
            try:
                payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
                room = payload.get("room", "general-chat")
                mid = payload.get("message_id")
                self.chat_history[room] = [m for m in self.chat_history.get(room, []) if m.get("id") != mid]
                self._remove_message_card(mid)
                self._chat_cache_dirty = True
            except Exception:
                pass
            return

        if raw.startswith("HIST_CHANNEL:"):
            p = raw.split(":", 3)
            if len(p) == 4:
                self.store_message(p[1], p[2], p[3], local=False)
            return

        if raw.startswith("HIST_GLOBAL:"):
            p = raw.split(":", 2)
            if len(p) == 3:
                self.store_message("general-chat", p[1], p[2], local=False)
            return

        if raw.startswith("HIST_DM:"):
            p = raw.split(":", 3)
            if len(p) == 4:
                self.store_message(p[1], p[2], p[3], local=False)
            return

        if raw.startswith("CHANNEL:"):
            p = raw.split(":", 3)
            if len(p) == 4:
                self.store_message(p[1], p[2], p[3], local=False)
                if p[2] != my_name:
                    self.play_ping_sound()
            return

        if raw.startswith("GLOBAL:"):
            p = raw.split(":", 2)
            if len(p) == 3:
                self.store_message("general-chat", p[1], p[2], local=False)
                if p[1] != my_name:
                    self.play_ping_sound()
            return

        if raw.startswith("DM:"):
            p = raw.split(":", 3)
            if len(p) == 4:
                self.store_message(p[1], p[2], p[3], local=False)
                if p[2] != my_name:
                    self.play_ping_sound()
            return

        if raw == "READY":
            self.loading_history = False
            if self._chat_cache_dirty:
                self._save_chat_cache()
                self._chat_cache_dirty = False
            self._refresh_dm_list()
            self.reload_current_chat_view()
            self._flush_outbox()
            self.server_status_label.setText("connected")
            self.chat_status_label.setText("connected")
            return

        if raw.startswith("PFP:"):
            p = raw.split(":", 2)
            if len(p) == 3:
                self.receive_pfp(p[1], p[2])
            return

        if raw.startswith("SERVERPFP:"):
            try:
                img = Image.open(io.BytesIO(base64.b64decode(raw.split(":", 1)[1]))).convert("RGB")
                self.server_pfp = img
                self.server_button.setIcon(QIcon(self.pil_to_pixmap(img, (44, 44))))
                self.server_button.setText("")
            except Exception:
                pass
            return

        if raw.startswith("CHANNEL_LIST:"):
            channels = [x for x in raw.split(":", 1)[1].split(",") if x]
            self.server_channels = channels or ["general-chat", "random"]
            self._refresh_channels()
            return

        if raw.startswith("STATUS:"):
            p = raw.split(":", 3)
            if len(p) >= 3:
                self.presence_status[p[1]] = p[2]
                self.custom_status[p[1]] = p[3] if len(p) == 4 else ""
                self._refresh_member_list()
            return

        if raw.startswith("TYPING:"):
            p = raw.split(":", 2)
            if len(p) == 3 and p[1] != my_name:
                self.chat_status_label.setText(f"{p[1]} is typing…")
                QTimer.singleShot(1500, lambda: self.chat_status_label.setText("connected"))
            return

        if raw.startswith("USER_RENAMED:"):
            p = raw.split(":", 2)
            if len(p) == 3:
                old_name, new_name = p[1], p[2]
                self._rename_local_history(old_name, new_name)
            return

        if raw.startswith("EDITED:"):
            p = raw.split(":", 4)
            if len(p) == 5:
                room, key, _, new_text = p[1:]
                for msg in self.chat_history.get(room, []):
                    if isinstance(msg, dict) and msg.get("id") == key:
                        msg["text"] = new_text
                        msg["edited"] = True
                self.reload_current_chat_view()
            return

        if raw.startswith("DELETED:"):
            p = raw.split(":", 3)
            if len(p) == 4:
                room, key = p[1], p[2]
                self.chat_history[room] = [m for m in self.chat_history.get(room, []) if m.get("id") != key]
                self.reload_current_chat_view()
            return

    def _network_send(self, text, queue_offline=True):
        if self.client_socket and self.authenticated:
            try:
                payload = (text + "\n").encode("utf-8")
                with self.send_lock:
                    self.client_socket.sendall(payload)
                return True
            except Exception as exc:
                self._network_disconnected()
                if queue_offline:
                    self._outbox.append(text)
                self.chat_status_label.setText(f"send queued // {type(exc).__name__}")
                return False
        if queue_offline:
            self._outbox.append(text)
        return False

    def _flush_outbox(self):
        if not (self.client_socket and self.authenticated) or not self._outbox:
            return
        pending = list(self._outbox)
        self._outbox.clear()
        for payload in pending:
            if not self._network_send(payload, queue_offline=False):
                self._outbox.append(payload)
                break


    # ---------- chat / members ----------

    def store_message(self, room, sender, text, local=False, message_id=None, reply_to=None, reactions=None, kind="message", file_meta=None, poll=None):
        room = room or "general-chat"
        self.chat_history.setdefault(room, [])
        message_id = message_id or uuid.uuid4().hex
        reactions = reactions or {}

        existing = next((m for m in self.chat_history[room] if m.get("id") == message_id), None)
        if existing is not None:
            existing.update({"sender": sender, "text": text, "reply_to": reply_to, "reactions": reactions, "kind": kind})
            if file_meta is not None:
                existing["file"] = file_meta
            if poll is not None:
                existing["poll"] = poll
            if local:
                self.pending_local_message_ids.add(message_id)
            else:
                self.pending_local_message_ids.discard(message_id)
            if room == self.current_target and not self.loading_history:
                self._update_message_card(existing.get("id"), existing)
            return existing

        message = {
            "sender": sender,
            "text": text,
            "id": message_id,
            "reply_to": reply_to,
            "reactions": reactions,
            "kind": kind,
        }
        if file_meta is not None:
            message["file"] = file_meta
        if poll is not None:
            message["poll"] = poll
        self.chat_history[room].append(message)
        self.chat_history[room] = self.chat_history[room][-500:]
        self._chat_cache_dirty = True

        if local:
            self.pending_local_message_ids.add(message_id)
        elif sender == self.username and message_id in self.pending_local_message_ids:
            self.pending_local_message_ids.discard(message_id)
            return message

        if self.loading_history:
            return message

        self._save_chat_cache()
        self._chat_cache_dirty = False
        if room == self.current_target:
            self._append_message_widget(message, scroll_to_bottom=True)
        return message

    def _reconcile_server_message_id(self, client_id, server_id, room_name=None):
        if not client_id or not server_id:
            return False
        rooms = [room_name] if room_name else list(self.chat_history.keys())
        for room in rooms:
            for msg in self.chat_history.get(room, []):
                if msg.get("client_id") == client_id or msg.get("id") == client_id:
                    old_id = msg.get("id")
                    msg["id"] = server_id
                    msg["client_id"] = client_id
                    self.pending_local_message_ids.discard(client_id)
                    self.pending_local_message_ids.discard(old_id)
                    if room == self.current_target and old_id != server_id:
                        self.reload_current_chat_view()
                    self._chat_cache_dirty = True
                    return True
        return False

    def send_message(self):
        text = self.message_entry.text().strip()
        if not text:
            return
        if not self.authenticated and not self.offline_mode:
            self.show_error("Not connected. Use CONTINUE OFFLINE or wait for reconnect.")
            return
        room = self.current_target
        message_id = uuid.uuid4().hex
        reply_to = dict(self.reply_target) if self.reply_target else None
        local_msg = self.store_message(room, self.username, text, local=True, message_id=message_id, reply_to=reply_to)
        local_msg["client_id"] = message_id
        self.message_entry.clear()
        payload = {
            "room": room,
            "id": message_id,
            "text": text,
            "reply_to": reply_to,
        }
        encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii")
        self._network_send(f"MESSAGE:{encoded}")
        if self.offline_mode:
            self.chat_status_label.setText("offline draft // will send on reconnect")
        self._clear_reply_target()

    def _register_file_metadata(self, meta, message=None):
        if not isinstance(meta, dict) or not meta.get("file_id"):
            return
        if meta.get("sender") == self.username:
            self._pending_file_sends[meta["file_id"]] = meta
        else:
            self._incoming_file_transfers[meta["file_id"]] = meta
        if message is not None and message.get("id"):
            meta.setdefault("message_id", message.get("id"))

    def _file_digest(self, path):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def choose_file_to_send(self):
        if not self.username:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Select file to send")
        if not path:
            return
        try:
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE:
                self.show_error(f"File is too large. NETRA currently supports up to {format_file_size(MAX_FILE_SIZE)}.")
                return
            file_id = uuid.uuid4().hex
            filename = os.path.basename(path)
            mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            digest = self._file_digest(path)
            cache_path = local_file_path(file_id, filename)
            with open(path, "rb") as src, open(cache_path, "wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
            meta = {
                "file_id": file_id, "name": filename, "size": size, "mime": mime,
                "sha256": digest, "sender": self.username, "room": self.current_target,
            }
            payload = {"room": self.current_target, "id": uuid.uuid4().hex, "text": "", "file": meta, "kind": "file", "reply_to": dict(self.reply_target) if self.reply_target else None}
            meta["message_id"] = payload["id"]
            self._pending_file_sends[file_id] = meta
            self.store_message(self.current_target, self.username, "", local=True, message_id=payload["id"], reply_to=payload["reply_to"], kind="file", file_meta=meta)
            encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii")
            self._network_send(f"MESSAGE:{encoded}")
            self._clear_reply_target()
        except Exception as exc:
            self.show_error(f"Could not prepare file:\n{type(exc).__name__}: {exc}")

    def _handle_file_offer(self, raw):
        try:
            payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
            self._incoming_file_transfers[payload["file_id"]] = payload
            self.chat_status_label.setText(f"file available // {payload.get('name', 'file')}")
            # Attach to the matching cached message without forcing a full rebuild.
            room = payload.get("room", self.current_target)
            for msg in self.chat_history.get(room, []):
                if msg.get("id") == payload.get("message_id"):
                    msg["file"] = payload
                    self._update_message_card(msg.get("id"), msg)
                    break
        except Exception as exc:
            self.chat_status_label.setText(f"file offer error // {exc}")

    def _download_file(self, file_meta):
        if not file_meta:
            return
        file_id = file_meta.get("file_id")
        local = local_file_path(file_id, file_meta.get("name", "file"))
        if os.path.exists(local) and os.path.getsize(local) == int(file_meta.get("size", -1)):
            self._open_local_file(local, file_meta)
            return
        request = {"room": self.current_target, "file_id": file_id, "sender": file_meta.get("sender", "")}
        encoded = base64.b64encode(json.dumps(request, separators=(",", ":")).encode("utf-8")).decode("ascii")
        self._network_send(f"FILE_REQUEST:{encoded}")
        self.chat_status_label.setText(f"downloading // {file_meta.get('name', 'file')}")

    def _open_local_file(self, path, meta=None):
        try:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as exc:
            self.show_error(f"Could not open file: {exc}")

    def _handle_file_request(self, raw):
        try:
            payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
            file_id = payload.get("file_id", "")
            pending = self._pending_file_sends.get(file_id)
            if not pending:
                return
            threading.Thread(target=self._send_file_chunks, args=(pending,), daemon=True).start()
        except Exception:
            pass

    def _send_file_chunks(self, meta):
        path = local_file_path(meta["file_id"], meta.get("name", "file"))
        try:
            with self._file_send_lock, open(path, "rb") as handle:
                index = 0
                while True:
                    chunk = handle.read(FILE_CHUNK_SIZE)
                    if not chunk:
                        break
                    packet = {"file_id": meta["file_id"], "index": index, "data": base64.b64encode(chunk).decode("ascii")}
                    encoded = base64.b64encode(json.dumps(packet, separators=(",", ":")).encode("utf-8")).decode("ascii")
                    self._network_send(f"FILE_CHUNK:{encoded}", queue_offline=False)
                    index += 1
            done = base64.b64encode(json.dumps({"file_id": meta["file_id"], "sha256": meta.get("sha256", "")}, separators=(",", ":")).encode("utf-8")).decode("ascii")
            self._network_send(f"FILE_DONE:{done}", queue_offline=False)
        except Exception as exc:
            self.chat_status_label.setText(f"file send failed // {exc}")

    def _handle_file_chunk(self, raw):
        try:
            packet = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
            fid = packet["file_id"]
            meta = self._incoming_file_transfers.get(fid)
            if not meta:
                return
            state = getattr(self, "_file_receive_state", {}).get(fid) if hasattr(self, "_file_receive_state") else None
            if state is None:
                if not hasattr(self, "_file_receive_state"):
                    self._file_receive_state = {}
                path = local_file_path(fid, meta.get("name", "file")) + ".part"
                state = {"path": path, "next": 0}
                self._file_receive_state[fid] = state
            if int(packet.get("index", -1)) != state["next"]:
                return
            with open(state["path"], "ab") as handle:
                handle.write(base64.b64decode(packet["data"]))
            state["next"] += 1
        except Exception:
            pass

    def _handle_file_done(self, raw):
        try:
            payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
            fid = payload["file_id"]
            meta = self._incoming_file_transfers.get(fid)
            state = getattr(self, "_file_receive_state", {}).pop(fid, None)
            if not meta or not state:
                return
            target = local_file_path(fid, meta.get("name", "file"))
            digest = self._file_digest(state["path"])
            if payload.get("sha256") and digest != payload["sha256"]:
                os.remove(state["path"])
                self.show_error("Downloaded file failed checksum verification.")
                return
            os.replace(state["path"], target)
            self.chat_status_label.setText(f"download complete // {meta.get('name', 'file')}")
            self._open_local_file(target, meta)
            self.reload_current_chat_view(preserve_scroll=True)
        except Exception as exc:
            self.show_error(f"File download failed: {exc}")

    def create_poll(self):
        if not self.authenticated and not self.offline_mode:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // CREATE POLL")
        dialog.setFixedSize(440, 330)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        question = QLineEdit()
        question.setPlaceholderText("Question")
        layout.addWidget(question)
        options = []
        for i in range(4):
            line = QLineEdit()
            line.setPlaceholderText(f"Option {i + 1}")
            layout.addWidget(line)
            options.append(line)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        opts = [w.text().strip() for w in options if w.text().strip()]
        q = question.text().strip()
        if not q or len(opts) < 2:
            self.show_error("A poll needs a question and at least two options.")
            return
        poll = {"question": q[:240], "options": opts[:6], "votes": {str(i): [] for i in range(min(6, len(opts)))}}
        message_id = uuid.uuid4().hex
        payload = {"room": self.current_target, "id": message_id, "text": q, "kind": "poll", "poll": poll, "reply_to": dict(self.reply_target) if self.reply_target else None}
        self.store_message(self.current_target, self.username, q, local=True, message_id=message_id, reply_to=payload["reply_to"], kind="poll", poll=poll)
        encoded = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
        self._network_send(f"POLL_CREATE:{encoded}")
        self._clear_reply_target()

    def _handle_poll_event(self, raw):
        try:
            payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
            self.store_message(payload.get("room", self.current_target), payload.get("sender", "?"), payload.get("text", ""), message_id=payload.get("id"), reply_to=payload.get("reply_to"), reactions=payload.get("reactions") or {}, kind="poll", poll=payload.get("poll") or {})
        except Exception:
            pass

    def _handle_poll_vote(self, raw):
        try:
            payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
            room = payload.get("room", self.current_target)
            for msg in self.chat_history.get(room, []):
                if msg.get("id") == payload.get("message_id"):
                    msg["poll"] = payload.get("poll") or msg.get("poll")
                    break
            self._chat_cache_dirty = True
            self._save_chat_cache()
            if room == self.current_target:
                message_id = payload.get("message_id")
                card = self.message_card_widgets.get(message_id)
                poll_data = next((m.get("poll") for m in self.chat_history.get(room, []) if m.get("id") == message_id), None)
                if card is not None and poll_data is not None and hasattr(card, "poll_count_labels"):
                    votes = poll_data.get("votes") or {}
                    for idx, label in enumerate(card.poll_count_labels):
                        label.setText(str(len(votes.get(str(idx), []))))
                else:
                    # Only rebuild if the poll card is not currently rendered.
                    self.reload_current_chat_view(preserve_scroll=True)
        except Exception:
            pass

    def _set_reply_target(self, message):
        if not message:
            return
        self.reply_target = {
            "id": message.get("id", ""),
            "sender": message.get("sender", "?"),
            "text": message.get("text", "")[:180],
        }
        self.reply_banner_label.setText(f"REPLYING TO {message.get('sender', '?')}: {message.get('text', '')[:160]}")
        self.reply_banner.setVisible(True)
        self.message_entry.setFocus()

    def _clear_reply_target(self):
        self.reply_target = None
        if hasattr(self, "reply_banner"):
            self.reply_banner.setVisible(False)
            self.reply_banner_label.clear()

    def _react_to_message(self, message):
        if not message or not self.authenticated:
            return
        menu = QMenu(self)
        reactions = [
            ("LIKE", "👍"), ("HEART", "❤️"), ("LAUGH", "😂"), ("WOW", "😮"),
            ("SAD", "😢"), ("FIRE", "🔥"), ("PARTY", "🎉"), ("EYES", "👀"),
        ]
        for label, emoji in reactions:
            action = menu.addAction(label)
            action.triggered.connect(lambda checked=False, m=message, e=emoji: self._send_reaction(m, e))
        menu.exec(QCursor.pos())

    def _send_reaction(self, message, emoji):
        room = self.current_target
        mid = message.get("id")
        if not mid:
            return
        encoded = base64.b64encode(json.dumps({
            "room": room, "message_id": mid, "emoji": emoji
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii")
        self._network_send(f"REACT:{encoded}")

    def _delete_message(self, message):
        if not message or message.get("sender") != self.username:
            return
        encoded = base64.b64encode(json.dumps({
            "room": self.current_target, "message_id": message.get("id", "")
        }, separators=(",", ":")).encode("utf-8")).decode("ascii")
        self._network_send(f"DELETE:{encoded}")

    def _add_file_embed(self, body, msg):
        meta = msg.get("file") or {}
        file_id = meta.get("file_id", "")
        name = meta.get("name", "file")
        size = format_file_size(meta.get("size", 0))
        mime = meta.get("mime", "application/octet-stream")
        box = QFrame(objectName="panelAlt")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(8, 8, 8, 8)
        label = QLabel(f"FILE  {name}  //  {size}")
        label.setProperty("role", "messageText")
        box_layout.addWidget(label)
        local = local_file_path(file_id, name)
        if mime.startswith("image/") and os.path.exists(local):
            thumb = QLabel()
            pix = QPixmap(local)
            if not pix.isNull():
                thumb.setPixmap(pix.scaled(360, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                box_layout.addWidget(thumb)
        open_btn = QPushButton("OPEN LOCAL" if os.path.exists(local) else "DOWNLOAD")
        if os.path.exists(local):
            open_btn.clicked.connect(lambda _=False, path=local, m=meta: self._open_local_file(path, m))
        else:
            open_btn.clicked.connect(lambda _=False, m=meta: self._download_file(m))
        box_layout.addWidget(open_btn, alignment=Qt.AlignLeft)
        body.addWidget(box)

    def _vote_poll(self, message, option_index):
        if not message or not message.get("id"):
            return
        payload = {"room": self.current_target, "message_id": message.get("id"), "option": int(option_index)}
        encoded = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
        self._network_send(f"POLL_VOTE:{encoded}")

    def _update_message_card(self, message_id, message_or_reactions):
        card = self.message_card_widgets.get(message_id)
        if card is None:
            return
        if hasattr(message_or_reactions, "get") and "reactions" in message_or_reactions:
            reactions = message_or_reactions.get("reactions") or {}
        else:
            reactions = message_or_reactions or {}
        parts = []
        for emoji, users in reactions.items():
            count = len(users if isinstance(users, list) else [])
            if count:
                parts.append(f"{emoji} {count}")
        card.reaction_label.setText("   ".join(parts))
        card.reaction_label.setVisible(bool(parts))

    def _remove_message_card(self, message_id):
        card = self.message_card_widgets.pop(message_id, None)
        if card is not None:
            card.setParent(None)
            card.deleteLater()
        self._save_chat_cache()

    def select_channel(self, channel):
        self.current_target = channel
        self.chat_title_label.setText(f"# {channel}")
        self.message_entry.setPlaceholderText(f"Message #{channel}")
        self._highlight_channel(channel)
        self.reload_current_chat_view()

    def show_server_view(self):
        self.current_target = self.current_target if self.current_target in self.server_channels else "general-chat"
        self.chat_title_label.setText(f"# {self.current_target}")
        self.message_entry.setPlaceholderText(f"Message #{self.current_target}")
        self._highlight_channel(self.current_target)
        self.reload_current_chat_view()

    def show_dm_view(self):
        if self.dm_partners:
            self.select_dm_channel(self.dm_partners[0])
        else:
            self.chat_title_label.setText("DIRECT MESSAGES")
            self.reload_current_chat_view()

    def select_dm_channel(self, partner):
        self.current_target = partner
        self.chat_title_label.setText(f"@ {partner}")
        self.message_entry.setPlaceholderText(f"Message @{partner}")
        self.reload_current_chat_view()

    def _highlight_channel(self, target):
        c = self.palette_colors()
        active = f"background:{c['hover']}; color:{c['bright']}; border:1px solid {c['border']};"
        normal = f"background:{c['button']}; color:{c['bright']}; border:1px solid {c['border']};"
        self.channel_button.setText("# general-chat")
        self.random_button.setText("# random")
        self.channel_button.setStyleSheet(active if target == "general-chat" else normal)
        self.random_button.setStyleSheet(active if target == "random" else normal)

    def _refresh_channels(self):
        self.channel_button.setVisible("general-chat" in self.server_channels)
        self.random_button.setVisible("random" in self.server_channels)

    def _refresh_dm_list(self):
        partners = []
        for room in self.chat_history:
            if room not in self.server_channels and room:
                partners.append(room)
        for name in self.last_registered_users:
            if name != self.username and name not in partners:
                partners.append(name)
        self.dm_partners = sorted(set(partners), key=str.lower)
        self.dm_list.clear()
        for partner in self.dm_partners:
            self.dm_list.addItem(f"@ {partner}")

    def _dm_item_clicked(self, item):
        text = item.text().removeprefix("@ ")
        if text:
            self.select_dm_channel(text)

    def _make_member_widget(self, user, online=True, status="", voice=False):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(6)
        avatar = QLabel()
        avatar.setFixedSize(30, 30)
        avatar.setAlignment(Qt.AlignCenter)
        avatar_img = self.user_pfps.get(user, Image.new("RGB", (40, 40), "#0F3D0F"))
        avatar.setPixmap(self.pil_to_pixmap(avatar_img, (30, 30)))
        layout.addWidget(avatar)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        name = QLabel(user + ("  [YOU]" if user == self.username else ""))
        name.setProperty("role", "memberName")
        text_col.addWidget(name)
        if status:
            status_label = QLabel(status)
            status_label.setProperty("role", "muted")
            status_label.setWordWrap(True)
            text_col.addWidget(status_label)
        elif voice:
            voice_label = QLabel("VOICE")
            voice_label.setProperty("role", "muted")
            text_col.addWidget(voice_label)
        else:
            online_label = QLabel("ONLINE" if online else "OFFLINE")
            online_label.setProperty("role", "muted")
            text_col.addWidget(online_label)
        layout.addLayout(text_col, 1)
        if voice:
            wave = QLabel("[.....]")
            wave.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            wave.setFixedWidth(58)
            wave.setStyleSheet(f"color:{self.palette_colors()['dim']}; font-family:Consolas; font-size:11px; font-weight:700;")
            layout.addWidget(wave)
            self.voice_wave_labels[user] = wave
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{self.palette_colors()['bright'] if online else self.palette_colors()['faint']};")
        layout.addWidget(dot, alignment=Qt.AlignRight | Qt.AlignVCenter)
        return row

    def _add_widget_item(self, list_widget, widget, height=40):
        item = QListWidgetItem()
        item.setSizeHint(QSize(150, height))
        list_widget.addItem(item)
        list_widget.setItemWidget(item, widget)

    def _refresh_member_list(self):
        self.members_list.clear()
        users = self.last_registered_users or sorted(self.online_users)
        for user in users:
            online = user in self.online_users
            status = self.presence_status.get(user, "")
            widget = self._make_member_widget(user, online=online, status=status)
            self._add_widget_item(self.members_list, widget, 46 if status else 42)

    def _refresh_voice_users(self):
        self.voice_user_list.clear()
        self.voice_wave_labels = {}
        for user in self.voice_users:
            widget = self._make_member_widget(user, online=True, voice=True)
            self._add_widget_item(self.voice_user_list, widget, 44)
        self._refresh_voice_user_settings()

    def _capture_chat_scroll_anchor(self):
        if not hasattr(self, "chat_scroll"):
            return None
        bar = self.chat_scroll.verticalScrollBar()
        value = bar.value()
        maximum = bar.maximum()
        page = max(1, bar.pageStep())
        at_bottom = maximum - value <= max(12, page // 3)
        ratio = (value / maximum) if maximum > 0 else 0.0
        return {
            "value": value,
            "maximum": maximum,
            "ratio": ratio,
            "at_bottom": at_bottom,
        }

    def _restore_chat_scroll_anchor(self, anchor):
        if not anchor or not hasattr(self, "chat_scroll"):
            return
        def restore():
            self.chat_content_layout.activate()
            self.chat_content.adjustSize()
            bar = self.chat_scroll.verticalScrollBar()
            maximum = bar.maximum()
            if anchor.get("at_bottom"):
                target = maximum
            elif maximum <= 0:
                target = 0
            elif anchor.get("maximum", 0) > 0:
                # Preserve the same relative position rather than restoring an
                # obsolete absolute pixel value after a card's height changes.
                target = int(round(maximum * float(anchor.get("ratio", 0.0))))
            else:
                target = min(int(anchor.get("value", 0)), maximum)
            bar.setValue(max(0, min(target, maximum)))
        QTimer.singleShot(0, restore)
        QTimer.singleShot(20, restore)
        QTimer.singleShot(60, restore)

    def reload_current_chat_view(self, preserve_scroll=False):
        # Capture the user's position before rebuilding. Poll votes and file
        # completion used to rebuild the entire chat and reset QScrollArea to
        # the top, which made the view jump unexpectedly.
        anchor = self._capture_chat_scroll_anchor() if preserve_scroll else None
        self._pending_chat_scroll_anchor = anchor
        self._chat_wants_bottom = False

        # Cancel any older incremental render. Rebuilding 500 Qt widgets in one
        # callback makes the window feel frozen, especially immediately after login.
        self._render_generation += 1
        generation = self._render_generation

        self.message_card_widgets.clear()
        while self.chat_content_layout.count():
            item = self.chat_content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        messages = list(self.chat_history.get(self.current_target, []))[-500:]
        if not messages:
            empty = QLabel("No messages yet.")
            empty.setProperty("role", "muted")
            self.chat_content_layout.addWidget(empty)
            if anchor:
                self._restore_chat_scroll_anchor(anchor)
            return

        self._render_messages = messages
        self._render_index = 0
        self._render_messages_in_batches(generation)

    def _append_message_widget(self, msg, scroll_to_bottom=False):
        c = self.palette_colors()
        sender = msg.get("sender", "?")
        text = msg.get("text", "")
        edited = "  [edited]" if msg.get("edited") else ""

        card = HoverMessageCard()
        card.message_id = msg.get("id")
        card.message_data = msg
        layout = QHBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        avatar = QLabel()
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignCenter)
        avatar_img = self.user_pfps.get(sender, Image.new("RGB", (40, 40), "#0F3D0F"))
        avatar.setPixmap(self.pil_to_pixmap(avatar_img, (36, 36)))
        layout.addWidget(avatar, alignment=Qt.AlignTop)

        body = QVBoxLayout()
        body.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(4)
        name = QLabel(sender + edited)
        name.setStyleSheet(f"color:{c['bright']}; font-family:Consolas; font-size:12px; font-weight:700;")
        head.addWidget(name)
        head.addStretch(1)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(3)
        reply_btn = QPushButton("REPLY")
        reply_btn.setObjectName("messageActionButton")
        reply_btn.clicked.connect(lambda _=False, m=msg: self._set_reply_target(m))
        actions_layout.addWidget(reply_btn)
        react_btn = QPushButton("REACT")
        react_btn.setObjectName("messageActionButton")
        react_btn.clicked.connect(lambda _=False, m=msg: self._react_to_message(m))
        actions_layout.addWidget(react_btn)
        if sender == self.username:
            delete_btn = QPushButton("DELETE")
            delete_btn.setObjectName("messageActionButton")
            delete_btn.clicked.connect(lambda _=False, m=msg: self._delete_message(m))
            actions_layout.addWidget(delete_btn)
        actions.setVisible(False)
        head.addWidget(actions)
        body.addLayout(head)

        reply_to = msg.get("reply_to") or {}
        if reply_to:
            preview = QLabel(f"↪ {reply_to.get('sender', '?')}: {reply_to.get('text', '')[:160]}")
            preview.setProperty("role", "replyPreview")
            preview.setWordWrap(True)
            body.addWidget(preview)

        if msg.get("kind") == "poll" and msg.get("poll"):
            poll = msg.get("poll") or {}
            question = QLabel(str(poll.get("question", text)))
            question.setProperty("role", "messageText")
            question.setWordWrap(True)
            body.addWidget(question)
            votes = poll.setdefault("votes", {})
            card.poll_count_labels = []
            for idx, option in enumerate(poll.get("options", [])):
                row = QHBoxLayout()
                vote_btn = QPushButton(str(option))
                vote_btn.clicked.connect(lambda _=False, m=msg, i=idx: self._vote_poll(m, i))
                count = QLabel(str(len(votes.get(str(idx), []))))
                count.setProperty("role", "muted")
                card.poll_count_labels.append(count)
                row.addWidget(vote_btn, 1)
                row.addWidget(count)
                body.addLayout(row)
        elif msg.get("kind") == "file" and msg.get("file"):
            self._add_file_embed(body, msg)
        else:
            msg_label = QLabel(text)
            msg_label.setProperty("role", "messageText")
            msg_label.setWordWrap(True)
            body.addWidget(msg_label)

        reaction_text = []
        for emoji, users in (msg.get("reactions") or {}).items():
            if isinstance(users, list) and users:
                reaction_text.append(f"{emoji} {len(users)}")
        reaction_label = QLabel("   ".join(reaction_text))
        reaction_label.setProperty("role", "reactionRow")
        reaction_label.setVisible(bool(reaction_text))
        card.reaction_label = reaction_label
        body.addWidget(reaction_label)

        layout.addLayout(body, 1)
        card.hovered.connect(actions.setVisible)
        self.chat_content_layout.addWidget(card)
        if msg.get("id"):
            self.message_card_widgets[msg.get("id")] = card

        if scroll_to_bottom:
            self._chat_wants_bottom = True
            QTimer.singleShot(0, self._scroll_chat_to_bottom)
            QTimer.singleShot(25, self._scroll_chat_to_bottom)

    def _on_chat_scroll_range_changed(self, _minimum, _maximum):
        if getattr(self, "_chat_wants_bottom", False):
            self._scroll_chat_to_bottom()

    def _scroll_chat_to_bottom(self):
        if not hasattr(self, "chat_scroll"):
            return
        self.chat_content_layout.activate()
        self.chat_content.adjustSize()
        bar = self.chat_scroll.verticalScrollBar()
        target = bar.maximum()
        if target >= 0:
            bar.setValue(target)
        # Keep the request alive for this layout cycle. rangeChanged will clear
        # it after the final size update below.
        QTimer.singleShot(35, self._clear_chat_bottom_request)

    def _clear_chat_bottom_request(self):
        self._chat_wants_bottom = False

    def _render_messages_in_batches(self, generation, batch_size=35):
        if generation != self._render_generation:
            return

        messages = getattr(self, "_render_messages", [])
        start = getattr(self, "_render_index", 0)
        if start >= len(messages):
            anchor = getattr(self, "_pending_chat_scroll_anchor", None)
            self._pending_chat_scroll_anchor = None
            if anchor:
                self._restore_chat_scroll_anchor(anchor)
            else:
                self._chat_wants_bottom = True
                self._scroll_chat_to_bottom()
                QTimer.singleShot(20, self._scroll_chat_to_bottom)
            return

        end = min(start + batch_size, len(messages))
        for msg in messages[start:end]:
            self._append_message_widget(msg, scroll_to_bottom=False)

        self._render_index = end
        QTimer.singleShot(0, lambda g=generation: self._render_messages_in_batches(g, batch_size))

    # ---------- reactions / pfp / misc ----------

    def receive_pfp(self, sender, b64_data):
        try:
            raw = base64.b64decode(b64_data)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            self.user_pfps[sender] = img
            self._refresh_member_list()
            self._refresh_voice_users()
        except Exception:
            pass

    def _rename_local_history(self, old, new):
        if old in self.chat_history and new not in self.chat_history:
            self.chat_history[new] = self.chat_history.pop(old)
        self._refresh_dm_list()
        self._refresh_member_list()

    def rename_username(self):
        if not self.authenticated:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // CHANGE USERNAME")
        dialog.setFixedSize(360, 190)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        entry = QLineEdit(self.username)
        layout.addWidget(QLabel("NEW USERNAME"))
        layout.addWidget(entry)
        status = QLabel("")
        layout.addWidget(status)
        save = QPushButton("SAVE NAME")
        save.clicked.connect(lambda: self._perform_rename(dialog, status, entry.text()))
        layout.addWidget(save)
        dialog.exec()

    def _perform_rename(self, dialog, status, name):
        name = name.strip()
        if not name:
            status.setText("Enter a username.")
            return
        if self._network_send(f"RENAME:{name}"):
            status.setText("Rename sent…")
            QTimer.singleShot(600, dialog.accept)

    def play_ping_sound(self):
        mode = self.settings.get("dm_sound_mode", "ping")
        if mode == "off":
            return
        try:
            path = generate_ping_wav(mode)
            if os.name == "nt":
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass

    # ---------- Screen sharing ----------

    def _connect_screen_relay(self):
        if not self.authenticated or not self.screen_token or self.offline_mode:
            return
        self._stop_screen_relay()
        try:
            sock = socket.create_connection((self.server_host, self.screen_port), timeout=6)
            sock.settimeout(None)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.sendall(f"HELLO:{self.username}:{self.screen_token}\n".encode("utf-8"))
            self.screen_socket = sock
            self.screen_worker = ScreenReceiveWorker(sock)
            self.screen_worker.frame_received.connect(self._screen_frame_received)
            self.screen_worker.failed.connect(lambda msg: None)
            self.screen_worker.disconnected.connect(self._screen_relay_disconnected)
            self.screen_worker.start()
        except Exception:
            self.screen_socket = None
            self.screen_worker = None

    def _stop_screen_relay(self):
        worker = self.screen_worker
        self.screen_worker = None
        self.screen_socket = None
        if worker:
            worker.stop()
            try:
                worker.wait(500)
            except Exception:
                pass

    def _screen_relay_disconnected(self):
        if self.screen_worker and not self.screen_worker.isRunning():
            self.screen_socket = None

    def _screen_frame_received(self, sender, seq, jpeg):
        # Sender identity is intentionally not trusted from the transport; the
        # current relay is newest-frame-only and the viewer can show the latest.
        self.screen_last_frame = bytes(jpeg)
        if sender and "|" in sender:
            parts = sender.split("|")
            self.screen_last_frame_sender = parts[0] or "REMOTE SCREEN"
            try:
                self.screen_last_frame_meta = {"fps": int(parts[1]), "width": int(parts[2]), "height": int(parts[3])}
            except Exception:
                self.screen_last_frame_meta = {}
        else:
            self.screen_last_frame_sender = sender or "REMOTE SCREEN"
            self.screen_last_frame_meta = {}
        self.screen_last_frame_time = time.monotonic()
        viewer = getattr(self, "screen_viewer", None)
        if viewer is not None and viewer.isVisible():
            self._update_screen_viewer()

    def _selected_screen_image(self):
        try:
            screens = QApplication.screens()
            index = max(0, min(len(screens) - 1, int(self.screen_monitor_combo.currentData()))) if screens else 0
            screen = screens[index] if screens else QApplication.primaryScreen()
            if screen is None:
                return None
            rect = screen.geometry()
            return ImageGrab.grab(bbox=(rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height()))
        except Exception:
            try:
                return ImageGrab.grab()
            except Exception:
                return None

    def _screen_capture_loop(self):
        while self.screen_share_active and not self.screen_capture_stop.is_set():
            started = time.monotonic()
            image = self._selected_screen_image()
            if image is not None and self.screen_socket:
                try:
                    max_width = 1920
                    if image.width > max_width:
                        ratio = max_width / float(image.width)
                        image = image.resize((max_width, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
                    out = io.BytesIO()
                    image.convert("RGB").save(out, format="JPEG", quality=68, optimize=False)
                    jpeg = out.getvalue()
                    if len(jpeg) <= 7_900_000:
                        self.screen_sequence += 1
                        fps_now = max(1, int(self.screen_fps_combo.currentData() or 30))
                        meta_name = self.username.encode("utf-8")[:128]
                        payload = (b"F" + struct.pack("!Q", self.screen_sequence) +
                                   struct.pack("!H", len(meta_name)) + meta_name +
                                   struct.pack("!HHH", fps_now, min(65535, image.width), min(65535, image.height)) + jpeg)
                        packet = struct.pack("!I", len(payload)) + payload
                        with self._screen_send_lock:
                            self.screen_socket.sendall(packet)
                except Exception:
                    self.screen_share_active = False
                    QTimer.singleShot(0, self._finish_screen_share_ui)
                    break
            fps = max(1, int(self.screen_fps_combo.currentData() or 30))
            delay = max(0.001, 1.0 / fps - (time.monotonic() - started))
            self.screen_capture_stop.wait(delay)

    def toggle_screen_share(self):
        if self.screen_share_active:
            self.stop_screen_share()
        else:
            self.start_screen_share()

    def start_screen_share(self):
        if not self.authenticated or not self.screen_socket:
            self.show_error("Screen relay is not connected yet. Reconnect to the server and try again.")
            return
        self.screen_share_active = True
        self.screen_capture_stop.clear()
        self.screen_sequence = 0
        self.screen_share_button.setText("STOP SCREEN SHARE")
        self.chat_status_label.setText("screen share // live")
        self._network_send(f"SCREENSHARE:START:{max(1, int(self.screen_fps_combo.currentData() or 30))}")
        self.screen_capture_thread = threading.Thread(target=self._screen_capture_loop, daemon=True)
        self.screen_capture_thread.start()

    def _finish_screen_share_ui(self):
        self.screen_share_button.setText("SCREEN SHARE")

    def stop_screen_share(self):
        was_active = self.screen_share_active
        self.screen_share_active = False
        self.screen_capture_stop.set()
        if was_active:
            self._network_send("SCREENSHARE:STOP")
        self._finish_screen_share_ui()
        if self.authenticated and not self.in_voice_chat:
            self.chat_status_label.setText("connected")

    def open_screen_viewer(self):
        if not self.screen_last_frame:
            self.show_error("No remote screen frame has arrived yet.")
            return
        if getattr(self, "screen_viewer", None) is not None and self.screen_viewer.isVisible():
            self.screen_viewer.raise_()
            self.screen_viewer.activateWindow()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("NETRA // REMOTE SCREEN")
        dlg.resize(1100, 700)
        layout = QVBoxLayout(dlg)
        label = QLabel("Waiting for frame…")
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumSize(640, 360)
        label.setScaledContents(False)
        layout.addWidget(label, 1)
        status = QLabel("remote screen")
        status.setProperty("role", "muted")
        layout.addWidget(status)
        self.screen_viewer = dlg
        self.screen_viewer_label = label
        self.screen_viewer_status = status
        self._update_screen_viewer()
        dlg.show()

    def _update_screen_viewer(self):
        label = getattr(self, "screen_viewer_label", None)
        if label is None or not self.screen_last_frame:
            return
        pix = QPixmap()
        if not pix.loadFromData(self.screen_last_frame, "JPEG"):
            return
        scaled = pix.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)
        if hasattr(self, "screen_viewer_status"):
            age = max(0.0, time.monotonic() - self.screen_last_frame_time)
            self.screen_viewer_status.setText(f"REMOTE SCREEN  //  {pix.width()}x{pix.height()}  //  {age:.2f}s old")

    # ---------- Voice 2.0 ----------

    def _voice_rate(self):
        return {"Low": 16000, "Balanced": 24000, "High": 32000, "Ultra": 48000}.get(self.voice_quality, VOICE_RATE_DEFAULT)

    def _process_mic_pcm(self, pcm):
        import array
        values = array.array("h")
        values.frombytes(pcm)
        peak = max((abs(x) for x in values), default=0)
        for i, value in enumerate(values):
            value = int(value * self.voice_mic_gain)
            if self.voice_noise_gate and abs(value) < 350:
                value = 0
            values[i] = max(-32768, min(32767, value))
        if self.voice_agc and peak and peak < 9000:
            gain = min(2.5, 18000 / max(peak, 1))
            for i, value in enumerate(values):
                values[i] = max(-32768, min(32767, int(value * gain)))
        return values.tobytes()

    def _apply_voice_gain(self, pcm, gain):
        import array
        values = array.array("h")
        values.frombytes(pcm)
        for i, value in enumerate(values):
            values[i] = max(-32768, min(32767, int(value * gain)))
        return values.tobytes()

    def toggle_voice_chat(self):
        if not SOUNDDEVICE_AVAILABLE:
            self.show_error("Voice chat requires sounddevice. Install it with:\npython -m pip install sounddevice")
            return
        if self.in_voice_chat:
            self.stop_voice_chat()
        else:
            self.start_voice_chat()

    def start_voice_chat(self):
        if not self.authenticated or not self.client_socket:
            return
        if not SOUNDDEVICE_AVAILABLE:
            self.show_error("Voice chat requires sounddevice. Install it with:\npython -m pip install sounddevice")
            return
        try:
            in_device = self.settings.get("voice_input_device")
            out_device = self.settings.get("voice_output_device")

            # Validate saved numeric device IDs; fall back to the system default
            # if a device was removed or its index changed.
            try:
                in_info = sd.query_devices(in_device, "input")
            except Exception:
                in_device = None
                in_info = sd.query_devices(None, "input")
            try:
                out_info = sd.query_devices(out_device, "output")
            except Exception:
                out_device = None
                out_info = sd.query_devices(None, "output")

            if int(in_info.get("max_input_channels", 0) or 0) < 1:
                raise RuntimeError(f"No usable microphone input: {in_info.get('name', 'unknown device')}")
            if int(out_info.get("max_output_channels", 0) or 0) < 1:
                raise RuntimeError(f"No usable speaker output: {out_info.get('name', 'unknown device')}")

            self.voice_input_rate = int(round(float(in_info.get("default_samplerate") or 48000)))
            self.voice_output_rate = int(round(float(out_info.get("default_samplerate") or 48000)))
            self.voice_send_resampler = StreamingPCMResampler(self.voice_input_rate, self._voice_rate())
            sd.check_input_settings(device=in_device, samplerate=self.voice_input_rate, channels=VOICE_CHANNELS, dtype="int16")
            sd.check_output_settings(device=out_device, samplerate=self.voice_output_rate, channels=VOICE_CHANNELS, dtype="int16")

            self.voice_input_stream = sd.RawInputStream(
                samplerate=self.voice_input_rate,
                blocksize=VOICE_CHUNK,
                dtype="int16",
                channels=VOICE_CHANNELS,
                device=in_device,
                latency="low",
            )
            self.voice_output_stream = sd.RawOutputStream(
                samplerate=self.voice_output_rate,
                blocksize=VOICE_CHUNK,
                dtype="int16",
                channels=VOICE_CHANNELS,
                device=out_device,
                latency="high",
            )
            self.voice_input_stream.start()
            self.voice_output_stream.start()
            while not self.voice_play_queue.empty():
                try:
                    self.voice_play_queue.get_nowait()
                except queue.Empty:
                    break
            self.voice_packet_count = 0
            self.voice_bytes_received = 0
            self.voice_jitter_ms = 0.0
            self.voice_resamplers.clear()
            self.in_voice_chat = True
            self.voice_button.setText("LEAVE VOICE")
            self._network_send("VOICEJOIN:1")
            threading.Thread(target=self.voice_send_loop, daemon=True).start()
            threading.Thread(target=self.voice_playback_loop, daemon=True).start()
            self.chat_status_label.setText(
                f"voice // {in_info.get('name', 'mic')} -> {out_info.get('name', 'output')}"
            )
        except Exception as exc:
            self.stop_voice_chat()
            self.show_error(f"Could not start voice chat:\n{type(exc).__name__}: {exc}")

    def voice_send_loop(self):
        while self.in_voice_chat and self.voice_input_stream:
            try:
                data, _ = self.voice_input_stream.read(VOICE_CHUNK)
                pcm = bytes(data)
                if self.voice_muted or (self.voice_ptt and not self.voice_ptt_down):
                    pcm = b"\x00" * len(pcm)
                pcm = self._process_mic_pcm(pcm)
                try:
                    samples = array.array("h")
                    samples.frombytes(pcm[:len(pcm) - (len(pcm) % 2)])
                    if samples:
                        mean_sq = sum(int(v) * int(v) for v in samples) / len(samples)
                        level = min(1.0, math.sqrt(mean_sq) / 32768.0 * 30.0)
                    else:
                        level = 0.0
                    self.voice_levels[self.username] = math.sqrt(mean_sq) / 32768.0 * 30.0 if samples else 0.0
                    self.voice_activity[self.username] = time.monotonic() if level > 0.025 else self.voice_activity.get(self.username, 0.0)
                except Exception:
                    self.voice_levels[self.username] = 0.0
                network_rate = self._voice_rate()
                if (
                    self.voice_send_resampler is None
                    or self.voice_send_resampler.src_rate != int(self.voice_input_rate)
                    or self.voice_send_resampler.dst_rate != int(network_rate)
                ):
                    self.voice_send_resampler = StreamingPCMResampler(self.voice_input_rate, network_rate)
                network_data = self.voice_send_resampler.process(pcm)
                if not network_data:
                    continue
                encoded = base64.b64encode(network_data).decode("ascii")
                if self.client_socket and self.authenticated:
                    payload = f"VOICE:{network_rate}:{encoded}\n".encode("ascii")
                    with self.send_lock:
                        self.client_socket.sendall(payload)
            except Exception as exc:
                self.in_voice_chat = False
                QTimer.singleShot(0, lambda e=str(exc): self.show_error(f"Voice microphone/network stopped:\n{type(exc).__name__}: {e}"))
                break

    def voice_playback_loop(self):
        prebuffer = []
        while self.in_voice_chat and self.voice_output_stream:
            try:
                sender, sender_rate, data = self.voice_play_queue.get(timeout=0.4)
            except queue.Empty:
                continue
            try:
                now = time.monotonic()
                if self.voice_last_packet_time:
                    interval = (now - self.voice_last_packet_time) * 1000
                    self.voice_jitter_ms += (abs(interval - 20) - self.voice_jitter_ms) * 0.05
                self.voice_last_packet_time = now
                self.voice_packet_count += 1
                self.voice_bytes_received += len(data)
                if self.voice_deafened or self.voice_user_mutes.get(sender, False):
                    continue
                prebuffer.append((sender, sender_rate, data))
                if len(prebuffer) < self.voice_prebuffer_packets and self.voice_play_queue.qsize() < 2:
                    continue
                buffered = prebuffer
                prebuffer = []
                for buffered_sender, buffered_rate, buffered_data in buffered:
                    self._play_voice_packet(buffered_sender, buffered_rate, buffered_data)
            except Exception as exc:
                if self.in_voice_chat:
                    self.in_voice_chat = False
                    QTimer.singleShot(0, lambda e=str(exc): self.show_error(f"Voice playback stopped:\n{type(exc).__name__}: {e}"))
                break

    def _play_voice_packet(self, sender, sender_rate, data):
        if self.voice_deafened or self.voice_user_mutes.get(sender, False):
            return
        state = self.voice_resamplers.get(sender)
        if state is None or state.src_rate != int(sender_rate) or state.dst_rate != int(self.voice_output_rate):
            state = StreamingPCMResampler(int(sender_rate), int(self.voice_output_rate))
            self.voice_resamplers[sender] = state
        playback = state.process(data)
        if not playback:
            return
        gain = self.voice_volume * float(self.voice_user_volumes.get(sender, 1.0))
        playback = self._apply_voice_gain(playback, gain)
        self.voice_output_stream.write(playback)
        try:
            samples = array.array("h")
            samples.frombytes(playback[:len(playback) - (len(playback) % 2)])
            if samples:
                mean_sq = sum(int(v) * int(v) for v in samples) / len(samples)
                rms = math.sqrt(mean_sq) / 32768.0 * 30.0
            else:
                rms = 0.0
        except Exception:
            rms = 0.0
        self.voice_levels[sender] = rms
        self.voice_activity[sender] = time.monotonic()
        if self.voice_record_wave:
            self.voice_record_wave.writeframes(playback)

    def toggle_voice_mute(self):
        self.voice_muted = not self.voice_muted
        self.voice_mute_button.setText("UNMUTE MIC" if self.voice_muted else "MUTE MIC")

    def stop_voice_chat(self):
        was_active = self.in_voice_chat
        self.in_voice_chat = False
        if was_active:
            self._network_send("VOICELEAVE:1")
        for stream in (self.voice_input_stream, self.voice_output_stream):
            try:
                if stream:
                    stream.stop()
                    stream.close()
            except Exception:
                pass
        self.voice_input_stream = None
        self.voice_output_stream = None
        self.voice_resamplers.clear()
        self.voice_levels.clear()
        self.voice_wave_labels = {}
        self.voice_send_resampler = None
        self.voice_button.setText("JOIN VOICE")
        self.chat_status_label.setText("connected" if self.authenticated else "offline")

    def _update_voice_stats(self):
        if self.in_voice_chat:
            jitter = self.voice_jitter_ms
            quality = "EXCELLENT" if jitter < 4 else "GOOD" if jitter < 9 else "UNSTABLE" if jitter < 18 else "POOR"
            self.voice_stats_label.setText(
                f"packets {self.voice_packet_count}  bytes {self.voice_bytes_received}  jitter {jitter:.1f}ms  quality {quality}"
            )
        elif hasattr(self, "voice_stats_label"):
            self.voice_stats_label.setText("voice offline")

        if hasattr(self, "voice_radar_label"):
            now = time.monotonic()
            active = []
            for user in self.voice_users:
                age = now - float(self.voice_activity.get(user, 0.0))
                level = float(self.voice_levels.get(user, 0.0))
                if age > 0.25:
                    level *= max(0.0, 1.0 - (age - 0.25) / 0.9)
                filled = max(0, min(5, int(level * 5.0 + 0.5)))
                wave = "[" + ("|" * filled) + ("." * (5 - filled)) + "]"
                label = self.voice_wave_labels.get(user)
                if label:
                    label.setText(wave)
                    label.setStyleSheet(f"color:{self.palette_colors()['bright'] if level > 0.025 else self.palette_colors()['dim']}; font-family:Consolas; font-size:10px; font-weight:700;")
                if level > 0.025 and age < 1.2:
                    active.append(user if user != self.username else "YOU")
            if active:
                self.voice_radar_label.setText("VOICE RADAR\n" + "  ".join(active))
            elif self.voice_users:
                self.voice_radar_label.setText("VOICE RADAR\nlistening…")
            else:
                self.voice_radar_label.setText("VOICE RADAR\nno one connected")

    # ---------- misc ----------

    def _set_user_volume(self, user, value):
        self.voice_user_volumes[user] = max(0.0, min(2.0, float(value) / 100.0))
        self.settings["voice_user_volumes"] = dict(self.voice_user_volumes)
        save_settings(self.settings)

    def _set_user_mute(self, user, state):
        self.voice_user_mutes[user] = bool(state)
        self.settings["voice_user_mutes"] = dict(self.voice_user_mutes)
        save_settings(self.settings)

    def _refresh_voice_user_settings(self):
        """Refresh the per-user voice controls shown in Settings."""
        return self._refresh_voice_user_settings_impl()

    def _refresh_voice_user_settings_impl(self):
        while self.voice_users_settings_layout.count():
            item = self.voice_users_settings_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for user in self.voice_users:
            if user == self.username:
                continue
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(QLabel(user))
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 200)
            slider.setValue(int(float(self.voice_user_volumes.get(user, 1.0)) * 100))
            slider.valueChanged.connect(lambda value, u=user: self._set_user_volume(u, value))
            layout.addWidget(slider)
            mute = QCheckBox("MUTE")
            mute.setChecked(bool(self.voice_user_mutes.get(user, False)))
            mute.stateChanged.connect(lambda value, u=user: self._set_user_mute(u, value))
            layout.addWidget(mute)
            self.voice_users_settings_layout.addWidget(row)

    def show_error(self, message):
        QMessageBox.critical(self, "NETRA", message)

    def closeEvent(self, event):
        try:
            self.settings.update({
                "theme": self.theme_name,
                "dm_sound_mode": self.sound_combo.currentText() if hasattr(self, "sound_combo") else self.settings.get("dm_sound_mode", "ping"),
                "voice_volume": self.voice_volume,
                "voice_mic_gain": self.voice_mic_gain,
                "voice_quality": self.voice_quality,
                "voice_noise_gate": self.voice_noise_gate,
                "voice_agc": self.voice_agc,
                "voice_echo_guard": self.voice_echo_guard,
                "voice_deafen": self.voice_deafened,
                "voice_ptt": self.voice_ptt,
                "voice_record": self.voice_recording,
                "voice_user_volumes": self.voice_user_volumes,
                "voice_user_mutes": self.voice_user_mutes,
                "voice_input_device": self._audio_selection_to_index(self.input_device_combo.currentText()) if hasattr(self, "input_device_combo") else self.settings.get("voice_input_device"),
                "voice_output_device": self._audio_selection_to_index(self.output_device_combo.currentText()) if hasattr(self, "output_device_combo") else self.settings.get("voice_output_device"),
            })
            save_settings(self.settings)
            self._save_chat_cache()
        except Exception:
            pass
        self.stop_screen_share()
        self._stop_screen_relay()
        self.stop_voice_chat()
        if self.network_worker:
            self.network_worker.stop()
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("NETRA")
    app.setStyle("Fusion")
    window = FullDiscordClone()
    window.show()
    sys.exit(app.exec())
