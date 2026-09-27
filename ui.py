import array
import ctypes
from ctypes import wintypes
import base64
import io
import json
import math
import hashlib
import mimetypes
import os
import queue
import shutil
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
    import dxcam
    DXCAM_AVAILABLE = True
except ImportError:
    dxcam = None
    DXCAM_AVAILABLE = False

# DXCam's normal desktop-color processor requires OpenCV. Keep OpenCV optional
# so NETRA can automatically fall back to MSS instead of crashing its capture
# thread when cv2 is not installed.
try:
    import cv2  # noqa: F401
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    mss = None
    MSS_AVAILABLE = False

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    SOUNDDEVICE_AVAILABLE = False

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YTDLP_AVAILABLE = False

try:
    import av
    AV_AVAILABLE = True
except ImportError:
    av = None
    AV_AVAILABLE = False

try:
    from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, QSize
    from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPixmap, QCursor, QImage
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
        QSystemTrayIcon,
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
        "notification_settings": {},
        "notification_history": [],
        "rich_presence": {"enabled": True, "activity": "Using NETRA", "details": "Online", "state": "", "show_server": True},
        "customization": {"accent": "", "font_size": 12, "density": "Comfortable"},
        "music_playlists": {},
        "active_playlist": "Favorites",
        "client_plugins": {},
        "server_plugins": {},
        "developer_mode": False,
        "offline_mode": False,
        "screen_share_quality": "Balanced",
        "remember_username": True,
        "auto_open_images": True,
        "desktop_notifications": False,
        "notification_sound_enabled": True,
        "ui_scale": 100,
        "ptt_key": "Control",
        "release_channel": "Stable",
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
        self.send_lock = threading.Lock()
        self.network_worker: Optional[NetworkWorker] = None
        self.authenticated = False
        self.account_id = os.getenv("NETRA_ACCOUNT_ID", "")
        self.username = os.getenv("CHAT_USERNAME", "User")
        self.auth_dialog: Optional[AuthDialog] = None

        self.current_target = "general-chat"
        self.server_channels = ["general-chat", "random"]
        self.chat_history = {"general-chat": [], "random": []}
        self._load_chat_cache()
        self.dm_partners = []
        self.unread_counts = {}
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
        self.voice_wave_state = {}
        self.voice_hud_cards = {}
        self.voice_hud_wave_labels = {}
        self.voice_hud_status_labels = {}
        self.pinned_messages = {}
        self.deleted_undo = None
        self.last_disconnect_at = None
        self.notification_settings = dict(self.settings.get("notification_settings", {}) or {})
        self.notification_history = list(self.settings.get("notification_history", []) or [])[-200:]
        self.drafts = dict(self.settings.get("drafts", {}) or {})
        self.recent_targets = list(self.settings.get("recent_targets", []) or [])[-20:]
        self.dnd_mode = bool(self.settings.get("dnd_mode", False))
        self.rich_presence = dict(self.settings.get("rich_presence", {}) or {})
        self.rich_presence.setdefault("enabled", True)
        self.rich_presence.setdefault("activity", "Using NETRA")
        self.rich_presence.setdefault("details", "Online")
        self.rich_presence.setdefault("state", "")
        self.rich_presence.setdefault("show_server", True)
        self.customization = dict(self.settings.get("customization", {}) or {})
        self.customization.setdefault("accent", "")
        self.customization.setdefault("font_size", 12)
        self.customization.setdefault("density", "Comfortable")
        self.music_playlists = dict(self.settings.get("music_playlists", {}) or {})
        self.music_playlists.setdefault("Favorites", [])
        self.active_playlist = str(self.settings.get("active_playlist", "Favorites"))
        self.client_plugins = dict(self.settings.get("client_plugins", {}) or {})
        self.server_plugins = dict(self.settings.get("server_plugins", {}) or {})
        self.developer_mode = bool(self.settings.get("developer_mode", False))
        self.screen_share_quality = str(self.settings.get("screen_share_quality", "Balanced"))
        self.screen_share_source = str(self.settings.get("screen_share_source", "Virtual Desktop"))
        self.screen_share_fps = int(self.settings.get("screen_share_fps", 30) or 30)
        self.screen_share_cursor = bool(self.settings.get("screen_share_cursor", True))
        self.screen_share_bounds = None
        self.screen_sharing = False
        self.voice_floating_window = None
        self.voice_hud_expanded = False
        self.vc_room_window = None
        self.vc_room_users_list = None
        self.vc_room_share_label = None
        self.vc_room_share_status = None
        self.screen_share_timer = None
        self.screen_capture_thread = None
        self.screen_capture_stop = threading.Event()
        self.screen_capture_lock = threading.Lock()
        self.screen_capture_pending = None
        self.screen_capture_source_bounds = None
        self.screen_share_dialog = None
        self.screen_share_preview_label = None
        self.screen_share_source_combo = None
        self.screen_share_fps = 30
        self.screen_share_last_frame = None
        self.connection_started_at = None
        self.last_ping_ms = None
        self.loading_history = False
        self._chat_cache_dirty = False
        self._render_generation = 0
        self.offline_mode = False
        # Server-authoritative music state. Playback is shared by everyone in voice.
        self.music_state = {"queue": [], "index": 0, "current": None, "playing": False, "paused": False, "position": 0.0}
        self.music_dialog = None
        self.music_listening = False
        self.music_play_queue = queue.Queue(maxsize=120)
        self.music_output_stream = None
        self._local_music_thread = None
        self._local_music_stop = False
        self.music_output_stream = None
        self.music_output_resampler = None
        self.music_listener_thread = None
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
        self.netra_version = "0.2.0"
        self.netra_build = "2026.09.26"
        self.debug_log = list(self.settings.get("debug_log", []) or [])[-1000:]
        self.remember_username = bool(self.settings.get("remember_username", True))
        self.auto_open_images = bool(self.settings.get("auto_open_images", True))
        self.desktop_notifications = bool(self.settings.get("desktop_notifications", False))
        self.notification_sound_enabled = bool(self.settings.get("notification_sound_enabled", True))
        self.ui_scale = int(self.settings.get("ui_scale", 100) or 100)
        self.ptt_key = str(self.settings.get("ptt_key", "Control"))

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
        self.setAcceptDrops(True)
        self.resize(1200, 760)
        self.setMinimumSize(980, 640)
        self._install_icon()
        self._build_ui()
        self._setup_notifications()
        self._apply_theme()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._process_incoming_queue)
        self.timer.start(15)

        self.voice_stats_timer = QTimer(self)
        self.voice_stats_timer.timeout.connect(self._update_voice_stats)
        self.voice_stats_timer.start(100)

        self.presence_timer = QTimer(self)
        self.presence_timer.timeout.connect(self._broadcast_rich_presence)
        self.presence_timer.start(30000)

        self._connect_after_start = QTimer(self)
        self._connect_after_start.setSingleShot(True)
        self._connect_after_start.timeout.connect(self.show_auth)
        self._connect_after_start.start(250)
        self._log_debug("NETRA started")

    def _show_while_away(self, seconds):
        unread = sum(max(0, int(v)) for v in self.unread_counts.values())
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // WHILE YOU WERE AWAY")
        dialog.setFixedSize(460, 260)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        title = QLabel("WHILE YOU WERE AWAY")
        title.setProperty("role", "title")
        layout.addWidget(title)
        mins = seconds // 60
        secs = seconds % 60
        layout.addWidget(QLabel(f"Connection was away for {mins}m {secs}s."))
        layout.addWidget(QLabel(f"Unread notifications: {unread}"))
        layout.addWidget(QLabel(f"Cached rooms: {len(self.chat_history)}"))
        close = QPushButton("CONTINUE")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    # ---------- notifications ----------

    def _setup_notifications(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.windowIcon())
        self.tray_icon.setToolTip("NETRA")
        self.tray_icon.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.Trigger else None)
        # Notifications stay inside NETRA. No Windows bottom-right toast popups.
        self.tray_icon.hide()

    def _notify_incoming(self, room, sender, text):
        if not sender or sender == self.username:
            return
        if room == self.current_target and self.isActiveWindow() and not self.isMinimized():
            return
        if self.notification_settings.get(room, True) is False:
            return

        self.unread_counts[room] = int(self.unread_counts.get(room, 0)) + 1
        self.notification_history.append({
            "room": str(room),
            "sender": str(sender),
            "text": str(text or "New message"),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.notification_history = self.notification_history[-200:]
        self.settings["notification_history"] = self.notification_history
        save_settings(self.settings)
        self._refresh_notification_badges()
        if self.notification_sound_enabled:
            self.play_ping_sound()

    def _refresh_notification_badges(self):
        total = sum(max(0, int(v)) for v in self.unread_counts.values())
        self.dm_button.setText(f"💬 {total}" if total else "💬")
        self.dm_button.setToolTip(f"Direct Messages — {total} unread" if total else "Direct Messages")
        self._refresh_dm_list()

    def _mark_room_read(self, room):
        if room in self.unread_counts:
            self.unread_counts.pop(room, None)
        self._refresh_notification_badges()

    # ---------- styling ----------

    def palette_colors(self):
        return THEMES[self.theme_name]

    def dialog_qss(self):
        c = self.palette_colors()
        return self._stylesheet(c, dialog=True)

    def _stylesheet(self, c, dialog=False):
        accent = self.customization.get("accent", "") if hasattr(self, "customization") else ""
        if accent:
            c = dict(c)
            c["bright"] = accent
            c["active"] = accent
        font_size = int(self.customization.get("font_size", 12)) if hasattr(self, "customization") else 12
        density = self.customization.get("density", "Comfortable") if hasattr(self, "customization") else "Comfortable"
        padding = {"Compact": "3px 5px", "Comfortable": "4px 6px", "Spacious": "7px 9px"}.get(density, "4px 6px")
        return f"""
        QWidget {{
            color: {c['bright']};
            background: {c['root']};
            font-family: Consolas;
            font-size: {font_size}px;
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
            padding: {padding};
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
        self.status_button = QPushButton("CUSTOM STATUS")
        self.status_button.setFixedHeight(22)
        self.status_button.clicked.connect(self.edit_custom_status)
        profile_layout.addWidget(self.status_button)
        self.customize_button = QPushButton("CUSTOMIZE")
        self.customize_button.setFixedHeight(22)
        self.customize_button.clicked.connect(self.open_customization)
        profile_layout.addWidget(self.customize_button)
        self.presence_button = QPushButton("RICH PRESENCE")
        self.presence_button.setFixedHeight(22)
        self.presence_button.clicked.connect(self.open_rich_presence)
        profile_layout.addWidget(self.presence_button)
        self.notifications_button = QPushButton("NOTIFICATIONS")
        self.notifications_button.setFixedHeight(22)
        self.notifications_button.clicked.connect(self.open_notification_center)
        profile_layout.addWidget(self.notifications_button)
        self.tools_button = QPushButton("NETRA TOOLS")
        self.tools_button.setFixedHeight(22)
        self.tools_button.clicked.connect(self.open_netra_tools)
        profile_layout.addWidget(self.tools_button)
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
        self.search_button = QPushButton("SEARCH")
        self.search_button.setFixedHeight(24)
        self.search_button.clicked.connect(self.global_search)
        header.addWidget(self.search_button)
        self.pin_button = QPushButton("PINS")
        self.pin_button.setFixedHeight(24)
        self.pin_button.clicked.connect(self.show_pinned_messages)
        header.addWidget(self.pin_button)
        self.files_button = QPushButton("FILES")
        self.files_button.setFixedHeight(24)
        self.files_button.clicked.connect(self.open_files_gallery)
        header.addWidget(self.files_button)
        self.music_button = QPushButton("MUSIC")
        self.music_button.setFixedHeight(24)
        self.music_button.clicked.connect(self.open_music_player)
        header.addWidget(self.music_button)
        self.notify_button = QPushButton("NOTIFY")
        self.notify_button.setFixedHeight(24)
        self.notify_button.clicked.connect(self.toggle_channel_notifications)
        header.addWidget(self.notify_button)
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

        self._build_voice_hud(chat_layout)

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
        self.paste_image_button = QPushButton("PASTE")
        self.paste_image_button.setFixedSize(62, 44)
        self.paste_image_button.setToolTip("Paste an image from the clipboard")
        self.paste_image_button.clicked.connect(self.paste_clipboard_image)
        compose.addWidget(self.paste_image_button)
        self.emoji_button = QPushButton("😊")
        self.emoji_button.setFixedSize(44, 44)
        self.emoji_button.setToolTip("Emoji picker (Ctrl+E)")
        self.emoji_button.clicked.connect(self.open_emoji_picker)
        compose.addWidget(self.emoji_button)
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
        self.members_list.itemClicked.connect(self._member_item_clicked)
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

    def _build_voice_hud(self, parent_layout):
        """Persistent compact VC HUD that stays visible while browsing NETRA."""
        self.voice_hud = QFrame(objectName="panelAlt")
        self.voice_hud.setMinimumHeight(92)
        self.voice_hud.setMaximumHeight(112)
        hud_layout = QVBoxLayout(self.voice_hud)
        hud_layout.setContentsMargins(8, 6, 8, 6)
        hud_layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.voice_hud_title = QLabel("🔊 VOICE HUD")
        self.voice_hud_title.setProperty("role", "title")
        top.addWidget(self.voice_hud_title)
        self.voice_hud_count = QLabel("OFFLINE")
        self.voice_hud_count.setProperty("role", "muted")
        top.addWidget(self.voice_hud_count)
        top.addStretch(1)

        self.voice_hud_mic = QPushButton("🎤 MIC")
        self.voice_hud_mic.setFixedHeight(25)
        self.voice_hud_mic.clicked.connect(self.toggle_voice_mute)
        top.addWidget(self.voice_hud_mic)

        self.voice_hud_audio = QPushButton("🔊 AUDIO")
        self.voice_hud_audio.setFixedHeight(25)
        self.voice_hud_audio.clicked.connect(self.open_settings)
        top.addWidget(self.voice_hud_audio)

        self.voice_hud_music = QPushButton("🎵 MUSIC")
        self.voice_hud_music.setFixedHeight(25)
        self.voice_hud_music.clicked.connect(self.open_music_player)
        top.addWidget(self.voice_hud_music)

        self.voice_hud_expand = QPushButton("⤢")
        self.voice_hud_expand.setFixedSize(32, 25)
        self.voice_hud_expand.setToolTip("Expand VC")
        self.voice_hud_expand.clicked.connect(self.toggle_voice_hud_expand)
        top.addWidget(self.voice_hud_expand)

        self.voice_hud_settings = QPushButton("⚙")
        self.voice_hud_settings.setFixedSize(30, 25)
        self.voice_hud_settings.setToolTip("Voice settings")
        self.voice_hud_settings.clicked.connect(self.open_settings)
        top.addWidget(self.voice_hud_settings)
        hud_layout.addLayout(top)

        self.voice_hud_scroll = QScrollArea()
        self.voice_hud_scroll.setWidgetResizable(True)
        self.voice_hud_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.voice_hud_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.voice_hud_scroll.setFrameShape(QFrame.NoFrame)
        self.voice_hud_content = QWidget()
        self.voice_hud_row = QHBoxLayout(self.voice_hud_content)
        self.voice_hud_row.setContentsMargins(0, 0, 0, 0)
        self.voice_hud_row.setSpacing(6)
        self.voice_hud_row.addStretch(1)
        self.voice_hud_scroll.setWidget(self.voice_hud_content)
        hud_layout.addWidget(self.voice_hud_scroll, 1)

        # Expanded VC workspace lives inside the normal bottom bar.  It is not
        # a separate pop-out window; expanding simply takes over the chat area.
        self.voice_hud_expanded_panel = QFrame(objectName="panel")
        expanded_layout = QVBoxLayout(self.voice_hud_expanded_panel)
        expanded_layout.setContentsMargins(8, 6, 8, 6)
        expanded_layout.setSpacing(6)
        expanded_header = QHBoxLayout()
        expanded_header.addWidget(QLabel("🔊 VOICE ROOM"))
        self.voice_hud_expanded_count = QLabel("0 IN VC")
        self.voice_hud_expanded_count.setProperty("role", "muted")
        expanded_header.addWidget(self.voice_hud_expanded_count)
        expanded_header.addStretch(1)
        share_btn = QPushButton("🖥 SCREEN SHARE")
        share_btn.clicked.connect(self.open_screen_share)
        expanded_header.addWidget(share_btn)
        music_btn = QPushButton("🎵 MUSIC")
        music_btn.clicked.connect(self.open_music_player)
        expanded_header.addWidget(music_btn)
        collapse_btn = QPushButton("↙ COLLAPSE")
        collapse_btn.clicked.connect(self.toggle_voice_hud_expand)
        expanded_header.addWidget(collapse_btn)
        expanded_layout.addLayout(expanded_header)

        expanded_body = QHBoxLayout()
        self.voice_hud_expanded_users = QListWidget()
        self.voice_hud_expanded_users.setMinimumWidth(250)
        expanded_body.addWidget(self.voice_hud_expanded_users)
        self.voice_hud_expanded_share = QLabel("SCREEN SHARE\nNothing is being shared.")
        self.voice_hud_expanded_share.setAlignment(Qt.AlignCenter)
        self.voice_hud_expanded_share.setMinimumHeight(280)
        self.voice_hud_expanded_share.setStyleSheet("border:1px solid rgba(255,255,255,35); background:rgba(0,0,0,80); border-radius:8px;")
        expanded_body.addWidget(self.voice_hud_expanded_share, 1)
        expanded_layout.addLayout(expanded_body, 1)

        expanded_controls = QHBoxLayout()
        self.voice_hud_expanded_mic = QPushButton("🎤 MIC")
        self.voice_hud_expanded_mic.clicked.connect(self.toggle_voice_mute)
        expanded_controls.addWidget(self.voice_hud_expanded_mic)
        self.voice_hud_expanded_deaf = QPushButton("🔊 AUDIO")
        self.voice_hud_expanded_deaf.clicked.connect(self.toggle_deafen)
        expanded_controls.addWidget(self.voice_hud_expanded_deaf)
        expanded_controls.addStretch(1)
        leave_btn = QPushButton("LEAVE VC")
        leave_btn.clicked.connect(self.stop_voice_chat)
        expanded_controls.addWidget(leave_btn)
        expanded_layout.addLayout(expanded_controls)
        self.voice_hud_expanded_panel.setVisible(False)
        hud_layout.addWidget(self.voice_hud_expanded_panel, 1)

        parent_layout.addWidget(self.voice_hud)
        self.voice_hud.setVisible(bool(self.in_voice_chat))
        self._refresh_voice_hud()

    def toggle_voice_hud_expand(self):
        if not self.in_voice_chat:
            return
        self.voice_hud_expanded = not self.voice_hud_expanded
        expanded = self.voice_hud_expanded
        # The bar remains docked above the composer; the chat viewport yields
        # its space so the VC workspace fills the available central area.
        self.chat_scroll.setVisible(not expanded)
        self.voice_hud_scroll.setVisible(not expanded)
        self.voice_hud_expanded_panel.setVisible(expanded)
        if expanded:
            self.voice_hud.setMinimumHeight(0)
            self.voice_hud.setMaximumHeight(16777215)
            self.voice_hud_expand.setText("↙")
            self.voice_hud_expand.setToolTip("Collapse VC")
            self.voice_hud_title.setText("🔊 VOICE ROOM  //  FULL")
        else:
            self.voice_hud.setMinimumHeight(92)
            self.voice_hud.setMaximumHeight(112)
            self.voice_hud_expand.setText("⤢")
            self.voice_hud_expand.setToolTip("Expand VC")
            self.voice_hud_title.setText("🔊 VOICE HUD  //  LIVE")
        self._refresh_voice_hud()
        self._update_voice_hud_expanded()

    def _update_voice_hud_expanded(self):
        if not getattr(self, "voice_hud_expanded", False) or not self.in_voice_chat:
            return
        users = list(dict.fromkeys(self.voice_users or [self.username]))
        self.voice_hud_expanded_count.setText(f"{len(users)} IN VC")
        self.voice_hud_expanded_users.clear()
        bars = "▁▂▃▄▅▆▇█"
        for user in users:
            state = self.voice_wave_state.get(user, {})
            level = float(state.get("level", 0.0) or 0.0)
            history = list(state.get("history", [0.0] * 7))[-7:]
            wave = "".join(bars[min(7, int(max(0.0, v) * 8.0))] for v in history)
            muted = bool(self.voice_user_mutes.get(user, False)) if user != self.username else self.voice_muted
            state_text = "MUTED" if muted else ("SPEAKING" if level > 0.035 else "LISTENING")
            self.voice_hud_expanded_users.addItem(f"{'🟢' if level > 0.035 else '⚪'} {user}   {state_text}\n   {wave}")
        self.voice_hud_expanded_mic.setText("🔇 MIC OFF" if self.voice_muted else "🎤 MIC")
        self.voice_hud_expanded_deaf.setText("🔇 DEAFENED" if self.voice_deafened else "🔊 AUDIO")
        if self.screen_sharing and self.screen_share_last_frame is not None:
            self.voice_hud_expanded_share.setPixmap(self.pil_to_pixmap(self.screen_share_last_frame, (900, 520)))
            self.voice_hud_expanded_share.setText("")
        else:
            self.voice_hud_expanded_share.setPixmap(QPixmap())
            self.voice_hud_expanded_share.setText("SCREEN SHARE\nNothing is being shared.")

    def _clear_voice_hud_cards(self):
        while self.voice_hud_row.count():
            item = self.voice_hud_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.voice_hud_cards = {}
        self.voice_hud_wave_labels = {}
        self.voice_hud_status_labels = {}
        self.voice_hud_row.addStretch(1)

    def _refresh_voice_hud(self):
        if not hasattr(self, "voice_hud"):
            return

        # The HUD is only part of the layout while actually connected to VC.
        # Do not leave an empty/offline panel taking up chat space.
        if not self.in_voice_chat:
            self.voice_hud.setVisible(False)
            self._clear_voice_hud_cards()
            return

        self.voice_hud.setVisible(True)
        self._clear_voice_hud_cards()
        users = list(dict.fromkeys(self.voice_users or [self.username]))
        self.voice_hud_title.setText("🔊 VOICE HUD  //  LIVE")
        self.voice_hud_count.setText(f"{len(users)} IN VC")
        for user in users:
            card = QFrame(objectName="panel")
            card.setMinimumWidth(180)
            card.setMaximumWidth(230)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(6, 4, 6, 4)
            card_layout.setSpacing(5)

            avatar = QLabel()
            avatar.setFixedSize(30, 30)
            avatar.setAlignment(Qt.AlignCenter)
            avatar_img = self.user_pfps.get(user, Image.new("RGB", (40, 40), "#0F3D0F"))
            avatar.setPixmap(self.pil_to_pixmap(avatar_img, (30, 30)))
            card_layout.addWidget(avatar)

            text_col = QVBoxLayout()
            text_col.setContentsMargins(0, 0, 0, 0)
            text_col.setSpacing(0)
            name = QLabel(("YOU" if user == self.username else user))
            name.setProperty("role", "memberName")
            text_col.addWidget(name)
            status = QLabel("MIC ON")
            status.setProperty("role", "muted")
            text_col.addWidget(status)
            card_layout.addLayout(text_col, 1)

            wave = QLabel("▁▁▁▁▁▁▁")
            wave.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            wave.setFixedWidth(70)
            wave.setStyleSheet(f"color:{self.palette_colors()['dim']}; font-family:Consolas; font-size:12px; font-weight:700;")
            card_layout.addWidget(wave)

            self.voice_hud_cards[user] = card
            self.voice_hud_wave_labels[user] = wave
            self.voice_hud_status_labels[user] = status
            self.voice_hud_row.insertWidget(self.voice_hud_row.count() - 1, card)

        self.voice_hud_mic.setText("🔇 MIC OFF" if self.voice_muted else "🎤 MIC")
        if hasattr(self, "voice_hud_audio"):
            self.voice_hud_audio.setText("🔇 DEAFENED" if self.voice_deafened else "🔊 AUDIO")

    def _update_voice_hud(self):
        if not hasattr(self, "voice_hud"):
            return
        if not self.in_voice_chat:
            if self.voice_hud.isVisible():
                self.voice_hud.setVisible(False)
            return
        if not self.voice_hud.isVisible():
            self.voice_hud.setVisible(True)
            self._refresh_voice_hud()
        users = list(dict.fromkeys(self.voice_users or [self.username]))
        if set(users) != set(self.voice_hud_cards):
            self._refresh_voice_hud()
        self.voice_hud_count.setText(f"{len(users)} IN VC")
        bars = "▁▂▃▄▅▆▇█"
        for user in users:
            wave = self.voice_hud_wave_labels.get(user)
            status = self.voice_hud_status_labels.get(user)
            if wave is None:
                continue
            state = self.voice_wave_state.get(user, {})
            level = float(state.get("level", 0.0) or 0.0)
            history = list(state.get("history", [0.0] * 7))[-7:]
            wave.setText("".join(bars[min(7, int(max(0.0, v) * 8.0))] for v in history))
            active = level > 0.035
            wave.setStyleSheet(
                f"color:{self.palette_colors()['bright'] if active else self.palette_colors()['dim']}; "
                "font-family:Consolas; font-size:12px; font-weight:700;"
            )
            if status:
                if user == self.username:
                    status.setText("MIC OFF" if self.voice_muted else ("SPEAKING" if active else "MIC ON"))
                else:
                    status.setText("SPEAKING" if active else "MIC ON")

        self.voice_hud_mic.setText("🔇 MIC OFF" if self.voice_muted else "🎤 MIC")
        self.voice_hud_audio.setText("🔇 DEAFENED" if self.voice_deafened else "🔊 AUDIO")
        self._update_voice_hud_expanded()

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

        # ---- 0.2 client controls ----
        client20, c20 = section("NETRA 0.2 CLIENT")
        c20.addWidget(QLabel("Client-only improvements are stored locally and do not require Server.py changes."))
        row = QHBoxLayout()
        row.addWidget(QLabel("UI scale"))
        self.ui_scale_combo = QComboBox()
        self.ui_scale_combo.addItems(["80%", "90%", "100%", "110%", "125%", "150%"] )
        self.ui_scale_combo.setCurrentText(f"{self.ui_scale}%")
        self.ui_scale_combo.currentTextChanged.connect(self._apply_ui_scale_setting)
        row.addWidget(self.ui_scale_combo, 1)
        c20.addLayout(row)
        self.remember_username_cb = QCheckBox("Remember username")
        self.remember_username_cb.setChecked(self.remember_username)
        self.remember_username_cb.stateChanged.connect(lambda v: setattr(self, "remember_username", bool(v)))
        c20.addWidget(self.remember_username_cb)
        self.auto_open_images_cb = QCheckBox("Automatically download and display images")
        self.auto_open_images_cb.setChecked(self.auto_open_images)
        self.auto_open_images_cb.stateChanged.connect(lambda v: setattr(self, "auto_open_images", bool(v)))
        c20.addWidget(self.auto_open_images_cb)
        self.desktop_notifications_cb = QCheckBox("In-app notification center alerts")
        self.desktop_notifications_cb.setChecked(self.desktop_notifications)
        self.desktop_notifications_cb.stateChanged.connect(lambda v: setattr(self, "desktop_notifications", bool(v)))
        c20.addWidget(self.desktop_notifications_cb)
        ptt_row = QHBoxLayout()
        ptt_row.addWidget(QLabel("Push-to-talk key"))
        self.ptt_key_combo = QComboBox()
        self.ptt_key_combo.addItems(["Control", "Shift", "Alt", "Space"])
        self.ptt_key_combo.setCurrentText(self.ptt_key if self.ptt_key in ["Control","Shift","Alt","Space"] else "Control")
        self.ptt_key_combo.currentTextChanged.connect(lambda v: setattr(self, "ptt_key", v))
        ptt_row.addWidget(self.ptt_key_combo, 1)
        c20.addLayout(ptt_row)
        tools = QGridLayout()
        for i, (label, fn) in enumerate([
            ("IMPORT SETTINGS", self.import_settings), ("EXPORT SETTINGS", self.export_settings),
            ("RESET UI", self.reset_ui_preferences), ("RESET SETTINGS", self.reset_all_settings),
            ("DEBUG LOG", self.open_debug_log), ("IMAGE CACHE", self.open_files_gallery),
            ("GLOBAL SEARCH", self.global_search), ("NOTIFICATIONS", self.open_notification_center),
        ]):
            b = QPushButton(label); b.setFixedHeight(28); b.clicked.connect(fn); tools.addWidget(b, i // 2, i % 2)
        c20.addLayout(tools)
        version = QLabel(f"NETRA {self.netra_version} // build {self.netra_build} // client-only release")
        version.setProperty("role", "muted")
        c20.addWidget(version)
        body_layout.addWidget(client20)

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
            ("CUSTOMIZE UI", self.open_customization),
            ("NOTIFICATIONS", self.open_notification_center),
            ("RICH PRESENCE", self.open_rich_presence),
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

    # ---------- NETRA feature pack ----------

    def _save_feature_settings(self):
        self.settings.update({
            "notification_history": self.notification_history[-200:],
            "rich_presence": self.rich_presence,
            "customization": self.customization,
            "music_playlists": self.music_playlists,
            "active_playlist": self.active_playlist,
            "client_plugins": self.client_plugins,
            "server_plugins": self.server_plugins,
            "developer_mode": self.developer_mode,
            "screen_share_quality": self.screen_share_quality,
            "screen_share_source": self.screen_share_source,
            "screen_share_fps": self.screen_share_fps,
            "screen_share_cursor": self.screen_share_cursor,
            "offline_mode": self.offline_mode,
        })
        save_settings(self.settings)

    def open_notification_center(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // NOTIFICATION CENTER")
        dialog.resize(620, 520)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        title = QLabel("NOTIFICATION CENTER")
        title.setProperty("role", "title")
        layout.addWidget(title)
        sub = QLabel("In-app notifications only — Windows toast alerts are disabled.")
        sub.setProperty("role", "muted")
        layout.addWidget(sub)
        items = QListWidget()
        for item in reversed(self.notification_history[-200:]):
            room = item.get("room", "?")
            sender = item.get("sender", "?")
            text_value = str(item.get("text", "")).replace("\\n", " ")
            stamp = item.get("time", "")
            label = f"{stamp}   {sender}  →  {room}   {text_value[:180]}"
            items.addItem(label)
        layout.addWidget(items, 1)
        buttons = QHBoxLayout()
        mark = QPushButton("MARK ALL READ")
        mark.clicked.connect(lambda: (self.unread_counts.clear(), self._refresh_notification_badges(), dialog.accept()))
        buttons.addWidget(mark)
        clear = QPushButton("CLEAR HISTORY")
        def clear_history():
            self.notification_history.clear()
            self.settings["notification_history"] = []
            save_settings(self.settings)
            items.clear()
        clear.clicked.connect(clear_history)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        close = QPushButton("CLOSE")
        close.clicked.connect(dialog.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        dialog.exec()

    def open_customization(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // CUSTOMIZATION")
        dialog.resize(560, 470)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        title = QLabel("CUSTOMIZATION")
        title.setProperty("role", "title")
        layout.addWidget(title)
        layout.addWidget(QLabel("Customize NETRA independently from the main settings menu."))

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme"))
        theme = QComboBox()
        theme.addItems(list(THEMES.keys()))
        theme.setCurrentText(self.theme_name)
        theme.currentTextChanged.connect(self.change_theme)
        theme_row.addWidget(theme, 1)
        layout.addLayout(theme_row)

        accent_row = QHBoxLayout()
        accent_row.addWidget(QLabel("Accent color"))
        accent = QLineEdit(str(self.customization.get("accent", "")))
        accent.setPlaceholderText("#33FF33 or blank for theme default")
        accent_row.addWidget(accent, 1)
        layout.addLayout(accent_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("UI font size"))
        font = QSlider(Qt.Horizontal)
        font.setRange(9, 18)
        font.setValue(int(self.customization.get("font_size", 12)))
        font_value = QLabel(str(font.value()))
        font.valueChanged.connect(lambda v: font_value.setText(str(v)))
        font_row.addWidget(font, 1)
        font_row.addWidget(font_value)
        layout.addLayout(font_row)

        density_row = QHBoxLayout()
        density_row.addWidget(QLabel("Message density"))
        density = QComboBox()
        density.addItems(["Compact", "Comfortable", "Spacious"])
        density.setCurrentText(str(self.customization.get("density", "Comfortable")))
        density_row.addWidget(density, 1)
        layout.addLayout(density_row)

        preview = QLabel("Preview: NETRA // customization is applied when you press APPLY")
        preview.setProperty("role", "muted")
        preview.setWordWrap(True)
        layout.addWidget(preview)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        reset = QPushButton("RESET CUSTOMIZATION")
        def reset_custom():
            self.customization = {"accent": "", "font_size": 12, "density": "Comfortable"}
            self._save_feature_settings()
            self._apply_theme()
            dialog.accept()
        reset.clicked.connect(reset_custom)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        apply_btn = QPushButton("APPLY")
        def apply_custom():
            value = accent.text().strip()
            if value and not (value.startswith("#") and len(value) in (4, 7)):
                QMessageBox.warning(dialog, "NETRA", "Accent must be a hex color such as #33FF33, or blank.")
                return
            self.customization = {"accent": value, "font_size": font.value(), "density": density.currentText()}
            self._save_feature_settings()
            self._apply_theme()
            dialog.accept()
        apply_btn.clicked.connect(apply_custom)
        buttons.addWidget(apply_btn)
        close = QPushButton("CLOSE")
        close.clicked.connect(dialog.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        dialog.exec()

    def open_rich_presence(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // RICH PRESENCE")
        dialog.setFixedSize(500, 390)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        title = QLabel("RICH PRESENCE")
        title.setProperty("role", "title")
        layout.addWidget(title)
        enabled = QCheckBox("Show Rich Presence")
        enabled.setChecked(bool(self.rich_presence.get("enabled", True)))
        layout.addWidget(enabled)
        activity = QLineEdit(str(self.rich_presence.get("activity", "Using NETRA")))
        activity.setPlaceholderText("Activity")
        layout.addWidget(QLabel("ACTIVITY")); layout.addWidget(activity)
        details = QLineEdit(str(self.rich_presence.get("details", "Online")))
        details.setPlaceholderText("Details")
        layout.addWidget(QLabel("DETAILS")); layout.addWidget(details)
        state = QLineEdit(str(self.rich_presence.get("state", "")))
        state.setPlaceholderText("State / extra line")
        layout.addWidget(QLabel("STATE")); layout.addWidget(state)
        show_server = QCheckBox("Show current server/channel")
        show_server.setChecked(bool(self.rich_presence.get("show_server", True)))
        layout.addWidget(show_server)
        layout.addStretch(1)
        buttons = QHBoxLayout(); buttons.addStretch(1)
        save = QPushButton("SAVE")
        def save_presence():
            self.rich_presence = {"enabled": enabled.isChecked(), "activity": activity.text().strip() or "Using NETRA", "details": details.text().strip() or "Online", "state": state.text().strip(), "show_server": show_server.isChecked()}
            self._save_feature_settings()
            self._broadcast_rich_presence()
            dialog.accept()
        save.clicked.connect(save_presence); buttons.addWidget(save)
        close = QPushButton("CLOSE"); close.clicked.connect(dialog.reject); buttons.addWidget(close)
        layout.addLayout(buttons)
        dialog.exec()

    def _broadcast_rich_presence(self):
        if not self.rich_presence.get("enabled", True):
            payload = {"enabled": False}
        else:
            payload = dict(self.rich_presence)
            if payload.get("show_server", True):
                payload["server"] = self.current_target or ""
        try:
            self._network_send("RICH_PRESENCE:" + json.dumps(payload, separators=(",", ":")), queue_offline=False)
        except Exception:
            pass

    def open_netra_tools(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // TOOLS")
        dialog.resize(560, 500)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        title = QLabel("NETRA TOOLS")
        title.setProperty("role", "title")
        layout.addWidget(title)
        buttons = [
            ("NOTIFICATION CENTER", self.open_notification_center),
            ("MUSIC PLAYER", self.open_music_player),
            ("CONNECTION DIAGNOSTICS", self.open_connection_diagnostics),
            ("PLUGIN MANAGER", self.open_plugin_manager),
            ("SCREEN SHARE", self.open_screen_share),
            ("COMMAND PALETTE", self.open_command_palette),
            ("KEYBOARD SHORTCUTS", self.open_shortcuts),
            ("0.2 QOL CENTER", self.open_qol_center),
        ]
        for label, fn in buttons:
            b = QPushButton(label); b.setFixedHeight(34); b.clicked.connect(lambda checked=False, f=fn: (dialog.accept(), f())); layout.addWidget(b)
        dev = QPushButton("DEVELOPER MODE" + (" [ON]" if self.developer_mode else " [OFF]"))
        dev.setFixedHeight(34)
        dev.clicked.connect(lambda: (dialog.accept(), self.open_developer_mode()))
        layout.addWidget(dev)
        layout.addStretch(1)
        close = QPushButton("CLOSE"); close.clicked.connect(dialog.accept); layout.addWidget(close)
        dialog.exec()

    def open_connection_diagnostics(self):
        dialog = QDialog(self); dialog.setWindowTitle("NETRA // CONNECTION DIAGNOSTICS"); dialog.resize(560, 430); dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog); title=QLabel("CONNECTION DIAGNOSTICS"); title.setProperty("role","title"); layout.addWidget(title)
        info=QLabel(); info.setWordWrap(True); info.setProperty("role","muted"); layout.addWidget(info)
        def refresh():
            state = "OFFLINE" if self.offline_mode or not self.authenticated else "CONNECTED"
            uptime = "n/a"
            if self.connection_started_at: uptime = f"{max(0, time.monotonic()-self.connection_started_at):.1f}s"
            info.setText("\n".join([
                f"Status: {state}", f"Server: {self.server_host}:{self.server_port}", f"WebSocket/TCP: {'CONNECTED' if self.client_socket else 'DISCONNECTED'}",
                f"Connection uptime: {uptime}", f"Reconnect attempts: {self._reconnect_attempts}", f"Last disconnect: {self.last_disconnect_at or 'none'}",
                f"Voice: {'CONNECTED' if self.in_voice_chat else 'offline'}", f"Voice packets: {self.voice_packet_count}", f"Voice jitter: {self.voice_jitter_ms:.1f} ms",
                f"Offline outbox: {len(self._outbox)}", f"Cached rooms: {len(self.chat_history)}", f"File cache: {FILE_CACHE_DIR}",
            ]))
        refresh(); layout.addStretch(1)
        r=QPushButton("REFRESH"); r.clicked.connect(refresh); layout.addWidget(r)
        close=QPushButton("CLOSE"); close.clicked.connect(dialog.accept); layout.addWidget(close); dialog.exec()

    def open_developer_mode(self):
        dialog = QDialog(self); dialog.setWindowTitle("NETRA // DEVELOPER MODE"); dialog.resize(640, 520); dialog.setStyleSheet(self.dialog_qss())
        layout=QVBoxLayout(dialog); title=QLabel("DEVELOPER MODE"); title.setProperty("role","title"); layout.addWidget(title)
        enabled=QCheckBox("Enable Developer Mode"); enabled.setChecked(self.developer_mode); layout.addWidget(enabled)
        info=QLabel(); info.setWordWrap(True); info.setProperty("role","muted"); layout.addWidget(info)
        def refresh():
            info.setText(f"Username: {self.username}\nUser ID: {self.username}\nCurrent target: {self.current_target}\nServer: {self.server_host}:{self.server_port}\nOffline: {self.offline_mode}\nMembers: {len(self.online_users)}\nVoice users: {len(self.voice_users)}\nCached messages: {sum(len(v) for v in self.chat_history.values())}\nPython: {sys.version.split()[0]}")
        refresh()
        copy_btn=QPushButton("COPY CURRENT TARGET ID")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(str(self.current_target or "")))
        layout.addWidget(copy_btn, alignment=Qt.AlignLeft)
        buttons=QHBoxLayout(); apply_btn=QPushButton("APPLY")
        def apply_dev():
            self.developer_mode=enabled.isChecked(); self._save_feature_settings(); dialog.accept()
        apply_btn.clicked.connect(apply_dev); buttons.addWidget(apply_btn); close=QPushButton("CLOSE"); close.clicked.connect(dialog.reject); buttons.addWidget(close); layout.addLayout(buttons); dialog.exec()

    def open_plugin_manager(self):
        for folder in (os.path.join(CONFIG_DIR,"plugins","client"), os.path.join(CONFIG_DIR,"plugins","server")):
            os.makedirs(folder, exist_ok=True)
        dialog=QDialog(self); dialog.setWindowTitle("NETRA // PLUGINS"); dialog.resize(700, 520); dialog.setStyleSheet(self.dialog_qss())
        layout=QVBoxLayout(dialog); title=QLabel("PLUGIN MANAGER"); title.setProperty("role","title"); layout.addWidget(title)
        tabs=QStackedWidget(); client=QWidget(); server=QWidget()
        selector=QComboBox(); selector.addItems(["CLIENT PLUGINS", "SERVER PLUGINS"]); selector.currentIndexChanged.connect(tabs.setCurrentIndex); layout.addWidget(selector)
        def make_page(kind, parent_widget):
            l=QVBoxLayout(parent_widget); path=os.path.join(CONFIG_DIR,"plugins",kind); l.addWidget(QLabel(f"{kind.upper()} PLUGINS  //  {path}"))
            listing=QListWidget(); l.addWidget(listing,1)
            plugins=self.client_plugins if kind=="client" else self.server_plugins
            for name, enabled in sorted(plugins.items()): listing.addItem(("[ON] " if enabled else "[OFF] ")+name)
            scan=QPushButton("SCAN / REFRESH")
            def do_scan():
                plugins.clear()
                for fn in sorted(os.listdir(path)):
                    if fn.endswith((".py",".json")) and fn not in ("__init__.py",): plugins[fn]=bool(plugins.get(fn, False))
                self._save_feature_settings(); listing.clear()
                for name, enabled in sorted(plugins.items()): listing.addItem(("[ON] " if enabled else "[OFF] ")+name)
            scan.clicked.connect(do_scan); l.addWidget(scan)
            return parent_widget
        tabs.addWidget(make_page("client",client)); tabs.addWidget(make_page("server",server)); layout.addWidget(tabs,1)
        note=QLabel("Client plugins run locally. Server plugins are advertised/configured here and require matching server support."); note.setProperty("role","muted"); note.setWordWrap(True); layout.addWidget(note)
        close=QPushButton("CLOSE"); close.clicked.connect(dialog.accept); layout.addWidget(close); dialog.exec()

    def _request_music_state(self):
        # Music is intentionally client-local.  Do not contact the NETRA server.
        self._refresh_music_dialog()

    def _music_command(self, action, value=None):
        action = str(action).upper()
        if action == "ADD" and value is not None:
            self._local_music_add(str(value))
        elif action == "REMOVE" and value is not None:
            try:
                row = int(value)
                if 0 <= row < len(self.music_state.get("queue", [])):
                    if row == self.music_state.get("index", 0) and self.music_listening:
                        self._stop_local_music()
                    self.music_state["queue"].pop(row)
                    if self.music_state["queue"]:
                        self.music_state["index"] = min(self.music_state.get("index", 0), len(self.music_state["queue"]) - 1)
                    else:
                        self.music_state.update({"index": 0, "current": None, "playing": False, "paused": False})
                    self._refresh_music_dialog()
            except Exception:
                pass
        elif action == "CLEAR":
            self._stop_local_music()
            self.music_state = {"queue": [], "index": 0, "current": None, "playing": False, "paused": False, "position": 0.0}
            self._refresh_music_dialog()
        elif action == "PLAY":
            self._play_local_music()
        elif action == "PAUSE":
            self._pause_local_music()
        elif action == "RESUME":
            self._resume_local_music()
        elif action == "STOP":
            self._stop_local_music()
        elif action == "SKIP" or action == "NEXT":
            self._next_local_music()
        elif action == "PREV":
            self._previous_local_music()

    def _local_ydl_opts(self, flat=False):
        return {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "extract_flat": flat,
            "skip_download": True,
            "ignoreerrors": True,
            "default_search": "ytsearch",
            "source_address": "0.0.0.0",
        }

    def _local_music_add(self, query):
        if not YTDLP_AVAILABLE:
            self.show_error("Local YouTube playback requires yt-dlp. Install it with:\npython -m pip install -U yt-dlp")
            return
        self.music_status_label.setText("IMPORTING INTO LOCAL PLAYLIST...") if hasattr(self, "music_status_label") else None
        threading.Thread(target=self._local_music_add_worker, args=(query,), daemon=True, name="NETRA-Local-Music-Import").start()

    def _local_music_add_worker(self, query):
        try:
            with yt_dlp.YoutubeDL(self._local_ydl_opts(flat=True)) as ydl:
                info = ydl.extract_info(query, download=False)
            if not info:
                raise RuntimeError("No playable result was found.")
            entries = info.get("entries") if isinstance(info, dict) else None
            if entries is None:
                entries = [info]
            added = []
            for entry in entries:
                if not entry:
                    continue
                item = {
                    "title": entry.get("title") or entry.get("id") or "Unknown track",
                    "webpage_url": entry.get("webpage_url") or entry.get("original_url") or entry.get("url"),
                    "url": entry.get("webpage_url") or entry.get("original_url") or entry.get("url"),
                    "id": entry.get("id"),
                    "duration": entry.get("duration") or 0,
                }
                if item["url"]:
                    added.append(item)
            if not added:
                raise RuntimeError("The playlist did not contain any playable tracks.")
            self.music_state.setdefault("queue", []).extend(added)
            if self.music_state.get("current") is None:
                self.music_state["index"] = 0
                self.music_state["current"] = self.music_state["queue"][0]
                threading.Thread(target=self._prefetch_local_track, args=(self.music_state["queue"][0],), daemon=True, name="NETRA-Music-Prefetch").start()
            self._refresh_music_dialog()
            if hasattr(self, "music_status_label"):
                self.music_status_label.setText(f"LOCAL PLAYLIST // ADDED {len(added)} TRACK{'S' if len(added) != 1 else ''}")
        except Exception as exc:
            self._music_import_error = str(exc)
            try:
                self.show_error(f"Could not import music: {exc}")
            except Exception:
                pass
        finally:
            self._refresh_music_dialog()

    def _prefetch_local_track(self, item):
        try:
            if not isinstance(item, dict) or item.get("direct_url"):
                return
            query = item.get("webpage_url") or item.get("url")
            if not query or not YTDLP_AVAILABLE:
                return
            with yt_dlp.YoutubeDL({**self._local_ydl_opts(flat=False), "noplaylist": True}) as ydl:
                info = ydl.extract_info(query, download=False)
            if not info:
                return
            formats = info.get("formats") or []
            audio = [f for f in formats if f.get("url") and f.get("acodec") not in (None, "none")]
            if audio:
                audio.sort(key=lambda f: ((f.get("abr") or 0), (f.get("asr") or 0)), reverse=True)
                direct = audio[0].get("url")
            else:
                direct = info.get("url")
            if direct:
                item["direct_url"] = direct
                item["direct_url_time"] = time.time()
        except Exception:
            pass

    def _local_track_stream(self, item):
        if not YTDLP_AVAILABLE:
            raise RuntimeError("yt-dlp is not installed.")
        cached = item.get("direct_url") if isinstance(item, dict) else None
        cached_at = float(item.get("direct_url_time", 0) or 0) if isinstance(item, dict) else 0.0
        if cached and cached_at and time.time() - cached_at < 1500:
            return cached, item
        query = item.get("webpage_url") or item.get("url")
        with yt_dlp.YoutubeDL({**self._local_ydl_opts(flat=False), "noplaylist": True}) as ydl:
            info = ydl.extract_info(query, download=False)
        if not info:
            raise RuntimeError("Could not resolve this track.")
        formats = info.get("formats") or []
        audio = [f for f in formats if f.get("url") and (f.get("acodec") not in (None, "none"))]
        if not audio:
            direct = info.get("url")
        else:
            audio.sort(key=lambda f: ((f.get("abr") or 0), (f.get("asr") or 0)), reverse=True)
            direct = audio[0].get("url")
        if not direct:
            raise RuntimeError("No direct audio stream was available for this track.")
        if isinstance(item, dict):
            item["direct_url"] = direct
            item["direct_url_time"] = time.time()
        return direct, info

    def _play_local_music(self):
        if not SOUNDDEVICE_AVAILABLE:
            self.show_error("Local music playback requires sounddevice. Install it with:\npython -m pip install sounddevice")
            return
        if not AV_AVAILABLE:
            self.show_error("Local music playback requires PyAV. Install it with:\npython -m pip install av")
            return
        q = self.music_state.get("queue", [])
        if not q:
            self.show_error("Your local music playlist is empty.")
            return
        self.music_state["playing"] = True
        self.music_state["paused"] = False
        if self.music_state.get("current") is None:
            self.music_state["index"] = min(int(self.music_state.get("index", 0)), len(q)-1)
            self.music_state["current"] = q[self.music_state["index"]]
        self._start_local_music_worker()
        self._refresh_music_dialog()

    def _start_local_music_worker(self):
        if getattr(self, "_local_music_thread", None) and self._local_music_thread.is_alive():
            return
        self._local_music_stop = False
        self._local_music_thread = threading.Thread(target=self._local_music_worker, daemon=True, name="NETRA-Local-Music")
        self._local_music_thread.start()

    def _local_music_worker(self):
        try:
            while self.music_state.get("playing") and not getattr(self, "_local_music_stop", False):
                q = self.music_state.get("queue", [])
                idx = int(self.music_state.get("index", 0))
                if not q or idx >= len(q):
                    break
                item = q[idx]
                self.music_state["current"] = item
                self.music_state["position"] = 0.0
                direct, info = self._local_track_stream(item)
                container = av.open(direct, mode="r", options={"reconnect": "1", "reconnect_streamed": "1", "reconnect_delay_max": "5"})
                audio_stream = next((st for st in container.streams if st.type == "audio"), None)
                if audio_stream is None:
                    container.close(); raise RuntimeError("Track contains no audio stream.")
                resampler = av.AudioResampler(format="s16", layout="mono", rate=32000)
                stream = None
                try:
                    for frame in container.decode(audio=audio_stream.index):
                        if not self.music_state.get("playing") or getattr(self, "_local_music_stop", False):
                            break
                        while self.music_state.get("paused") and self.music_state.get("playing") and not getattr(self, "_local_music_stop", False):
                            time.sleep(0.05)
                        for out in resampler.resample(frame):
                            pcm = out.to_ndarray().tobytes()
                            if not pcm:
                                continue
                            if stream is None:
                                stream = sd.RawOutputStream(samplerate=32000, channels=1, dtype="int16", device=getattr(self, "voice_output_device", None), blocksize=0)
                                stream.start()
                                self.music_output_stream = stream
                            stream.write(pcm)
                            self.music_state["position"] = float(frame.time or 0.0)
                finally:
                    if stream is not None:
                        try: stream.stop(); stream.close()
                        except Exception: pass
                    if self.music_output_stream is stream:
                        self.music_output_stream = None
                    container.close()
                if not self.music_state.get("playing") or getattr(self, "_local_music_stop", False):
                    break
                # Automatically advance to the next local track.
                if idx + 1 < len(q):
                    self.music_state["index"] = idx + 1
                    self.music_state["current"] = q[idx + 1]
                else:
                    self.music_state["playing"] = False
                    self.music_state["paused"] = False
                    self.music_state["position"] = 0.0
                    break
        except Exception as exc:
            self.music_state["playing"] = False
            self.music_state["paused"] = False
            self._local_music_error = str(exc)
            QTimer.singleShot(0, lambda e=str(exc): self.show_error(f"NETRA local music playback failed: {e}"))
        finally:
            self.music_output_stream = None
            QTimer.singleShot(0, self._refresh_music_dialog)

    def _pause_local_music(self):
        if self.music_state.get("playing"):
            self.music_state["paused"] = True
            self._refresh_music_dialog()

    def _resume_local_music(self):
        if self.music_state.get("playing"):
            self.music_state["paused"] = False
            self._refresh_music_dialog()
        else:
            self._play_local_music()

    def _stop_local_music(self):
        self._local_music_stop = True
        self.music_state["playing"] = False
        self.music_state["paused"] = False
        try:
            if self.music_output_stream is not None:
                self.music_output_stream.stop(); self.music_output_stream.close()
        except Exception:
            pass
        self.music_output_stream = None
        self._refresh_music_dialog()

    def _next_local_music(self):
        q = self.music_state.get("queue", [])
        if not q:
            return
        idx = min(int(self.music_state.get("index", 0)) + 1, len(q)-1)
        self.music_state["index"] = idx
        self.music_state["current"] = q[idx]
        self.music_state["position"] = 0.0
        self.music_state["playing"] = True
        self.music_state["paused"] = False
        self._local_music_stop = True
        time.sleep(0.03)
        self._local_music_stop = False
        self._start_local_music_worker()
        self._refresh_music_dialog()

    def _previous_local_music(self):
        q = self.music_state.get("queue", [])
        if not q:
            return
        idx = max(int(self.music_state.get("index", 0)) - 1, 0)
        self.music_state["index"] = idx
        self.music_state["current"] = q[idx]
        self.music_state["position"] = 0.0
        self.music_state["playing"] = True
        self.music_state["paused"] = False
        self._local_music_stop = True
        time.sleep(0.03)
        self._local_music_stop = False
        self._start_local_music_worker()
        self._refresh_music_dialog()

    def _select_local_music_row(self, item):
        try:
            row = self.music_queue_list.row(item)
            q = self.music_state.get("queue", [])
            if row < 0 or row >= len(q):
                return
            self._stop_local_music()
            self.music_state["index"] = row
            self.music_state["current"] = q[row]
            self.music_state["position"] = 0.0
            self.music_state["playing"] = True
            self.music_state["paused"] = False
            self.music_listening = True
            self._play_local_music()
            self._refresh_music_dialog()
        except Exception as exc:
            self.show_error(f"Could not start that track: {exc}")

    def open_music_player(self):
        if self.music_dialog is not None:
            try:
                self.music_dialog.raise_()
                self.music_dialog.activateWindow()
                return
            except Exception:
                self.music_dialog = None

        dialog = QDialog(self)
        self.music_dialog = dialog
        dialog.setWindowTitle("NETRA // MUSIC / PLAYLIST")
        dialog.setMinimumSize(560, 500)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("MUSIC // LOCAL PLAYER")
        title.setProperty("role", "title")
        layout.addWidget(title)
        status = QLabel("Private playback — only you hear this music. It does not use or update the NETRA server.")
        status.setProperty("role", "muted")
        status.setWordWrap(True)
        layout.addWidget(status)
        self.music_status_label = status

        listen_btn = QPushButton("STOP MUSIC" if self.music_listening else "LISTEN IN NETRA")
        listen_btn.clicked.connect(self._toggle_music_listener)
        layout.addWidget(listen_btn)
        self.music_listen_button = listen_btn

        add_row = QHBoxLayout()
        self.music_query_entry = QLineEdit()
        self.music_query_entry.setPlaceholderText("YouTube / YouTube Music URL, playlist URL, or search text")
        add_row.addWidget(self.music_query_entry, 1)
        add_btn = QPushButton("IMPORT")
        add_btn.clicked.connect(self._music_add_from_dialog)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)
        self.music_query_entry.returnPressed.connect(self._music_add_from_dialog)

        self.music_queue_list = QListWidget()
        self.music_queue_list.itemClicked.connect(lambda item: self._music_play_selected(self.music_queue_list.row(item)))
        layout.addWidget(self.music_queue_list, 1)

        controls = QHBoxLayout()
        for label, action in [("PREV", "PREV"), ("PLAY", "PLAY"), ("PAUSE", "PAUSE"), ("RESUME", "RESUME"), ("SKIP", "SKIP"), ("STOP", "STOP")]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, a=action: self._music_command(a))
            controls.addWidget(button)
        layout.addLayout(controls)

        remove_row = QHBoxLayout()
        remove_btn = QPushButton("REMOVE SELECTED")
        remove_btn.clicked.connect(self._music_remove_selected)
        remove_row.addWidget(remove_btn)
        clear_btn = QPushButton("CLEAR PLAYLIST")
        clear_btn.clicked.connect(lambda: self._music_command("CLEAR"))
        remove_row.addWidget(clear_btn)
        remove_row.addStretch(1)
        layout.addLayout(remove_row)

        close_btn = QPushButton("CLOSE")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)

        dialog.finished.connect(lambda _: setattr(self, "music_dialog", None))
        self._refresh_music_dialog()
        dialog.show()

    def _music_add_from_dialog(self):
        entry = getattr(self, "music_query_entry", None)
        if entry is None:
            return
        query = entry.text().strip()
        if not query:
            return
        entry.clear()
        self._music_command("ADD", query)

    def _music_remove_selected(self):
        widget = getattr(self, "music_queue_list", None)
        if widget is None:
            return
        row = widget.currentRow()
        if row >= 0:
            self._music_command("REMOVE", row)

    def _music_play_selected(self, row):
        try:
            row = int(row)
        except Exception:
            return
        q = self.music_state.get("queue", []) or []
        if row < 0 or row >= len(q):
            return
        self._local_music_stop = True
        self.music_state["index"] = row
        self.music_state["current"] = q[row]
        self.music_state["position"] = 0.0
        self.music_state["playing"] = True
        self.music_state["paused"] = False
        self.music_listening = True
        try:
            if self.music_output_stream is not None:
                self.music_output_stream.stop(); self.music_output_stream.close()
        except Exception:
            pass
        self.music_output_stream = None
        self._local_music_stop = False
        self._start_local_music_worker()
        self._refresh_music_dialog()

    def _refresh_music_dialog(self):
        widget = getattr(self, "music_queue_list", None)
        if widget is None:
            return
        state = self.music_state if isinstance(self.music_state, dict) else {}
        queue_items = state.get("queue") or []
        current_index = int(state.get("index", 0) or 0)
        widget.clear()
        for idx, item in enumerate(queue_items):
            title = str((item or {}).get("title") or (item or {}).get("url") or "Unknown track")
            prefix = "▶ " if idx == current_index and state.get("playing") else "   "
            widget.addItem(f"{prefix}{idx + 1}. {title}")
        current = state.get("current") or {}
        title = current.get("title") if isinstance(current, dict) else None
        listen_button = getattr(self, "music_listen_button", None)
        if listen_button is not None:
            listen_button.setText("STOP LISTENING" if self.music_listening else "LISTEN IN NETRA")
        if title:
            mode = "PAUSED" if state.get("paused") else "PLAYING" if state.get("playing") else "STOPPED"
            position = float(state.get("position", 0) or 0)
            listen = " // LOCAL AUDIO ON" if self.music_listening else ""
            self.music_status_label.setText(f"{mode} // {title} // {position:.1f}s{listen}")
        else:
            listen = " // LOCAL AUDIO ON" if self.music_listening else ""
            self.music_status_label.setText("Playlist empty // add a YouTube URL or search text" + listen)

    def open_vc_room(self):
        """Open the inline VC workspace instead of creating a second window."""
        if not self.in_voice_chat:
            self.show_error("Join a voice channel first.")
            return
        if not self.voice_hud_expanded:
            self.toggle_voice_hud_expand()
        else:
            self._update_voice_hud_expanded()

    def _vc_room_user_menu(self, pos):
        item = self.vc_room_users_list.itemAt(pos) if self.vc_room_users_list is not None else None
        if item is None:
            return
        text = item.text().split("   ", 1)[0].replace("🟢 ", "").replace("⚪ ", "").strip()
        menu = QMenu(self)
        copy_action = menu.addAction("COPY USERNAME")
        menu.addSeparator()
        mute_action = menu.addAction("MUTE USER" if not self.voice_user_mutes.get(text, False) else "UNMUTE USER")
        chosen = menu.exec(self.vc_room_users_list.mapToGlobal(pos))
        if chosen == copy_action:
            QApplication.clipboard().setText(text)
        elif chosen == mute_action and text != self.username:
            self.voice_user_mutes[text] = not self.voice_user_mutes.get(text, False)
            self._save_feature_settings()
            self._refresh_vc_room()

    def _refresh_vc_room(self):
        window = getattr(self, "vc_room_window", None)
        if window is None or not window.isVisible():
            return
        users = list(dict.fromkeys(self.voice_users or [self.username])) if self.in_voice_chat else []
        if getattr(self, "vc_room_count", None) is not None:
            self.vc_room_count.setText(f"{len(users)} IN VC")
        if self.vc_room_users_list is not None:
            self.vc_room_users_list.clear()
            for user in users:
                state = self.voice_wave_state.get(user, {})
                level = float(state.get("level", 0.0))
                speaking = level > 0.035
                wave_chars = "▁▂▃▄▅▆▇█"
                idx = min(len(wave_chars) - 1, max(0, int(level * len(wave_chars))))
                wave = wave_chars[idx] * 7 if speaking else "▁▁▁▁▁▁▁"
                muted = bool(self.voice_user_mutes.get(user, False)) if user != self.username else self.voice_muted
                state_text = "MUTED" if muted else ("SPEAKING" if speaking else "LISTENING")
                self.vc_room_users_list.addItem(f"{'🟢' if speaking else '⚪'} {user}   {state_text}\n   {wave}")
        if getattr(self, "vc_room_share_label", None) is not None and self.screen_sharing and self.screen_share_last_frame is not None:
            pix = self.pil_to_pixmap(self.screen_share_last_frame, (self.vc_room_share_label.width() - 20, self.vc_room_share_label.height() - 20))
            self.vc_room_share_label.setPixmap(pix)
            self.vc_room_share_label.setText("")
        elif getattr(self, "vc_room_share_label", None) is not None and not self.screen_sharing:
            self.vc_room_share_label.setPixmap(QPixmap())
            self.vc_room_share_label.setText("SCREEN SHARE\nNobody is sharing yet.")

    def _windows_monitor_list(self):
        """Return real Windows displays using Qt's screen enumeration.
        This is more reliable than mixing Win32 logical coordinates with
        PIL coordinates, especially on multi-monitor/high-DPI setups.
        """
        monitors = []
        try:
            screens = QApplication.screens()
            primary = QApplication.primaryScreen()
            for i, screen in enumerate(screens):
                geo = screen.geometry()
                monitors.append({
                    "index": i,
                    "screen": screen,
                    "name": screen.name() or f"Display {i + 1}",
                    "left": int(geo.left()), "top": int(geo.top()),
                    "right": int(geo.right() + 1), "bottom": int(geo.bottom() + 1),
                    "width": int(geo.width()), "height": int(geo.height()),
                    "primary": screen is primary,
                })
        except Exception:
            monitors = []
        return monitors

    def _selected_screen_capture_bounds(self, source_label):
        if source_label and source_label.startswith("Virtual Desktop"):
            monitors = self._windows_monitor_list()
            if not monitors:
                return None
            left = min(m["left"] for m in monitors); top = min(m["top"] for m in monitors)
            right = max(m["right"] for m in monitors); bottom = max(m["bottom"] for m in monitors)
            return {"left": left, "top": top, "width": right - left, "height": bottom - top}
        for label, rect in self._screen_capture_sources():
            if label == source_label and rect:
                return {"left": rect["left"], "top": rect["top"], "width": rect["width"], "height": rect["height"]}
        return None

    def _screen_capture_sources(self):
        sources = [("Virtual Desktop — ALL MONITORS", None)]
        for i, rect in enumerate(self._windows_monitor_list(), 1):
            primary = " • PRIMARY" if rect["primary"] else ""
            label = f"Monitor {i} — {rect['name']} — {rect['width']}×{rect['height']}{primary}"
            sources.append((label, rect))
        return sources

    def _qimage_to_pil(self, qimage):
        image = qimage.convertToFormat(QImage.Format_RGBA8888)
        w, h = image.width(), image.height()
        ptr = image.bits()
        data = bytes(ptr)
        return Image.frombuffer("RGBA", (w, h), data, "raw", "RGBA", 0, 1).convert("RGB")

    def _screen_capture_loop(self):
        """Capture desktop frames using a Windows GPU-friendly backend.

        DXCam/DXGI is preferred on Windows because it avoids the expensive
        full-screen PIL conversion that made 30/60 FPS capture hitch the UI.
        MSS is retained as a fallback. Only the newest frame is ever kept.
        """
        dx = None
        grabber = None
        try:
            bounds = self.screen_capture_source_bounds or {
                "left": 0, "top": 0, "width": 1280, "height": 720
            }
            target_fps = max(1, int(self.screen_share_fps or 30))

            # Prefer DXGI/DXCam on Windows. It captures the desktop through
            # the graphics stack instead of repeatedly copying a PIL image.
            if DXCAM_AVAILABLE and CV2_AVAILABLE and os.name == "nt":
                dx = dxcam.create(output_idx=0, output_color="BGR")
                region = (
                    int(bounds["left"]),
                    int(bounds["top"]),
                    int(bounds["left"] + bounds["width"]),
                    int(bounds["top"] + bounds["height"]),
                )
                dx.start(region=region, target_fps=target_fps, video_mode=True)
                while self.screen_sharing and not self.screen_capture_stop.is_set():
                    frame = dx.get_latest_frame()
                    if frame is not None:
                        # DXCam returns a numpy BGR array. Keep it as-is here;
                        # conversion to a small preview happens only when Qt
                        # actually needs to paint a new frame.
                        with self.screen_capture_lock:
                            self.screen_capture_pending = frame
                    self.screen_capture_stop.wait(0.001)
                return

            if MSS_AVAILABLE:
                grabber = mss.mss()

            while self.screen_sharing and not self.screen_capture_stop.is_set():
                started = time.monotonic()
                if grabber is not None:
                    raw = grabber.grab({
                        "left": int(bounds["left"]),
                        "top": int(bounds["top"]),
                        "width": int(bounds["width"]),
                        "height": int(bounds["height"]),
                    })
                    # Delay PIL conversion until the GUI actually consumes a
                    # frame. This fallback still avoids building a frame queue.
                    frame = raw
                else:
                    frame = ImageGrab.grab(
                        bbox=(int(bounds["left"]), int(bounds["top"]),
                              int(bounds["left"] + bounds["width"]),
                              int(bounds["top"] + bounds["height"])),
                        all_screens=True,
                    )
                with self.screen_capture_lock:
                    self.screen_capture_pending = frame
                delay = max(0.001, (1.0 / target_fps) - (time.monotonic() - started))
                self.screen_capture_stop.wait(delay)
        except Exception as exc:
            self._screen_capture_error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                if dx is not None:
                    dx.stop()
                    dx.release()
            except Exception:
                pass
            try:
                if grabber is not None:
                    grabber.close()
            except Exception:
                pass


    def _capture_screen_frame(self):
        """Display only the newest worker-produced frame on the GUI thread."""
        if not self.screen_sharing:
            return
        err = getattr(self, "_screen_capture_error", None)
        if err:
            self.screen_sharing = False
            self._stop_screen_share_capture()
            if getattr(self, "screen_share_status", None) is not None:
                self.screen_share_status.setText(f"Capture error: {err}")
            return
        frame = None
        with self.screen_capture_lock:
            if self.screen_capture_pending is not None:
                frame = self.screen_capture_pending
                self.screen_capture_pending = None
        if frame is not None:
            now = time.monotonic()
            if now - self.screen_capture_last_preview >= (1.0 / self.screen_capture_preview_fps):
                self.screen_capture_last_preview = now
                try:
                    # Convert only the newest frame, and immediately scale it
                    # to the preview size. No full-size PIL resize per frame.
                    if hasattr(frame, "shape") and hasattr(frame, "tobytes"):
                        h, w = int(frame.shape[0]), int(frame.shape[1])
                        qimg = QImage(frame.data, w, h, int(frame.strides[0]), QImage.Format_BGR888).copy()
                        pix = QPixmap.fromImage(qimg).scaled(640, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    elif hasattr(frame, "bgra"):
                        qimg = QImage(frame.bgra, frame.width, frame.height, frame.width * 4, QImage.Format_ARGB32).copy()
                        pix = QPixmap.fromImage(qimg).scaled(640, 360, Qt.KeepAspectRatio, Qt.FastTransformation)
                    else:
                        if not isinstance(frame, Image.Image):
                            frame = Image.frombytes("RGB", frame.size, frame.rgb)
                        pix = self.pil_to_pixmap(frame, (640, 360))
                    if self.screen_share_preview_label is not None:
                        self.screen_share_preview_label.setPixmap(pix)
                except Exception as exc:
                    self._screen_capture_error = f"Preview error: {type(exc).__name__}: {exc}"
                self._update_voice_hud_expanded()
            # Keep the latest object available for future server transport.
            self.screen_share_last_frame = frame

    def _screen_monitor_images(self):
        images = []
        for m in self._windows_monitor_list():
            try:
                images.append(m["screen"].grabWindow(0).toImage())
            except Exception:
                pass
        return images

    def open_screen_share(self):
        if not self.in_voice_chat:
            self.show_error("Join a voice channel before starting screen share.")
            return
        if self.screen_share_dialog is not None and self.screen_share_dialog.isVisible():
            self.screen_share_dialog.raise_(); self.screen_share_dialog.activateWindow(); return
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // SCREEN SHARE")
        dialog.setMinimumSize(620, 520)
        dialog.resize(720, 600)
        dialog.setStyleSheet(self.dialog_qss())
        self.screen_share_dialog = dialog
        layout = QVBoxLayout(dialog)
        title = QLabel("🖥 SCREEN SHARE")
        title.setProperty("role", "title")
        layout.addWidget(title)
        status = QLabel("Screen sharing is stopped.")
        status.setProperty("role", "muted")
        self.screen_share_status = status
        layout.addWidget(status)

        row = QHBoxLayout()
        row.addWidget(QLabel("SHARE THIS DISPLAY"))
        source = QComboBox()
        source_labels = [label for label, _rect in self._screen_capture_sources()]
        source.addItems(source_labels)
        saved_source = self.screen_share_source
        if saved_source in source_labels:
            source.setCurrentText(saved_source)
        row.addWidget(source, 1)
        row.addWidget(QLabel("QUALITY"))
        quality = QComboBox(); quality.addItems(["Low", "Balanced", "High", "Ultra"]); quality.setCurrentText(self.screen_share_quality)
        row.addWidget(quality)
        fps = QComboBox(); fps.addItems(["20 FPS", "30 FPS", "60 FPS"]); fps.setCurrentText(f"{self.screen_share_fps} FPS")
        if fps.currentIndex() < 0:
            fps.setCurrentText("30 FPS")
        row.addWidget(fps)
        layout.addLayout(row)
        self.screen_share_source_combo = source

        options = QHBoxLayout()
        cursor_box = QCheckBox("Capture cursor")
        cursor_box.setChecked(self.screen_share_cursor)
        options.addWidget(cursor_box)
        options.addWidget(QLabel("Tip: choose a monitor above to share only that display."))
        options.addStretch(1)
        layout.addLayout(options)

        preview = QLabel("SCREEN PREVIEW\nPress START to capture your desktop.")
        preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumHeight(320)
        preview.setStyleSheet("border: 1px solid rgba(255,255,255,35); background: rgba(0,0,0,90); border-radius: 8px;")
        self.screen_share_preview_label = preview
        layout.addWidget(preview, 1)
        backend_note = "DXCam / DXGI + OpenCV" if (DXCAM_AVAILABLE and CV2_AVAILABLE and os.name == "nt") else ("MSS fallback (install OpenCV to enable DXCam / DXGI)" if MSS_AVAILABLE else "Windows desktop capture fallback")
        info = QLabel(f"Capture backend: {backend_note}. Remote viewers require a future server-side screen-share relay; this client does not pretend the current server supports it.")
        info.setWordWrap(True); info.setProperty("role", "muted")
        layout.addWidget(info)

        controls = QHBoxLayout()
        start = QPushButton("STOP SCREEN SHARE" if self.screen_sharing else "START SCREEN SHARE")
        controls.addWidget(start)
        expand_vc = QPushButton("EXPAND VC")
        expand_vc.clicked.connect(self.open_vc_room)
        controls.addWidget(expand_vc)
        controls.addStretch(1)
        close = QPushButton("CLOSE"); close.clicked.connect(dialog.accept); controls.addWidget(close)
        layout.addLayout(controls)

        def toggle():
            self.screen_share_quality = quality.currentText()
            self.screen_share_fps = int(fps.currentText().split()[0])
            self.screen_share_cursor = bool(cursor_box.isChecked())
            self.screen_share_source = source.currentText()
            self._save_feature_settings()
            self.screen_sharing = not self.screen_sharing
            if self.screen_sharing:
                status.setText("Screen sharing ACTIVE — capturing locally.")
                start.setText("STOP SCREEN SHARE")
                self.screen_share_last_frame = None
                self._screen_capture_error = None
                self.screen_capture_stop.clear()
                self.screen_capture_source_bounds = self._selected_screen_capture_bounds(self.screen_share_source)
                if self.screen_share_timer is None:
                    self.screen_share_timer = QTimer(self)
                    self.screen_share_timer.timeout.connect(self._capture_screen_frame)
                # Preview rendering is capped at 30 FPS; capture itself still runs at 20/30/60.
                self.screen_share_timer.start(33)
                self.screen_capture_thread = threading.Thread(target=self._screen_capture_loop, name="NETRA-ScreenCapture", daemon=True)
                self.screen_capture_thread.start()
                # Kept for future server support; the current server ignores this message.
                self._network_send("SCREENSHARE:START:" + self.screen_share_quality, queue_offline=False)
            else:
                self._stop_screen_share_capture()
                status.setText("Screen sharing is stopped.")
                start.setText("START SCREEN SHARE")
                self._network_send("SCREENSHARE:STOP:" + self.screen_share_quality, queue_offline=False)
            self._refresh_vc_room()

        source.currentTextChanged.connect(lambda value: (setattr(self, "screen_share_source", value), setattr(self, "screen_capture_source_bounds", self._selected_screen_capture_bounds(value))))
        quality.currentTextChanged.connect(lambda value: setattr(self, "screen_share_quality", value))
        fps.currentTextChanged.connect(lambda value: setattr(self, "screen_share_fps", int(value.split()[0])))
        cursor_box.toggled.connect(lambda value: setattr(self, "screen_share_cursor", bool(value)))
        start.clicked.connect(toggle)
        dialog.finished.connect(lambda _=0: setattr(self, "screen_share_dialog", None))
        if self.screen_sharing:
            status.setText("Screen sharing ACTIVE — capturing locally.")
            start.setText("STOP SCREEN SHARE")
            self._screen_capture_error = None
            self.screen_capture_stop.clear()
            self.screen_capture_source_bounds = self._selected_screen_capture_bounds(self.screen_share_source)
            if self.screen_share_timer is None:
                self.screen_share_timer = QTimer(self); self.screen_share_timer.timeout.connect(self._capture_screen_frame)
            self.screen_share_timer.start(33)
            self.screen_capture_thread = threading.Thread(target=self._screen_capture_loop, name="NETRA-ScreenCapture", daemon=True)
            self.screen_capture_thread.start()
        dialog.show()

    def _stop_screen_share_capture(self):
        self.screen_sharing = False
        self.screen_capture_stop.set()
        if self.screen_share_timer is not None:
            self.screen_share_timer.stop()
        with self.screen_capture_lock:
            self.screen_capture_pending = None
        self.screen_share_last_frame = None
        self.screen_capture_preview_fps = 15
        self.screen_capture_last_preview = 0.0
        self.screen_capture_source_bounds = None
        self._screen_capture_error = None
        self.screen_capture_thread = None
        if self.screen_share_preview_label is not None:
            self.screen_share_preview_label.setPixmap(QPixmap())
            self.screen_share_preview_label.setText("SCREEN PREVIEW\nPress START to capture your desktop.")
        self._update_voice_hud_expanded()

    def open_floating_voice_window(self):
        """Legacy name retained; VC now expands inline instead of opening a pop-out."""
        if self.in_voice_chat:
            if not self.voice_hud_expanded:
                self.toggle_voice_hud_expand()
            else:
                self.toggle_voice_hud_expand()

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

    def _log_debug(self, message):
        entry = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}"
        self.debug_log.append(entry)
        self.debug_log = self.debug_log[-1000:]
        try:
            self.settings["debug_log"] = self.debug_log[-1000:]
            save_settings(self.settings)
        except Exception:
            pass

    def _apply_ui_scale_setting(self, text):
        try:
            value = int(str(text).replace("%", ""))
        except Exception:
            value = 100
        self.ui_scale = max(80, min(150, value))
        self.settings["ui_scale"] = self.ui_scale
        save_settings(self.settings)
        # Qt's global font scaling is safe to apply without rebuilding widgets.
        app = QApplication.instance()
        if app:
            font = app.font()
            base = 9.0
            font.setPointSizeF(base * self.ui_scale / 100.0)
            app.setFont(font)

    def export_settings(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export NETRA settings", "netra-settings.json", "JSON (*.json)")
        if not path:
            return
        try:
            data = dict(self.settings)
            data.pop("debug_log", None)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
            self.settings_status.setText("✓ SETTINGS EXPORTED")
        except Exception as exc:
            self.show_error(f"Could not export settings: {exc}")

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import NETRA settings", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("Settings file is not a JSON object.")
            # Keep credentials/session data out of imported preferences.
            for key in ("debug_log", "account_id"):
                data.pop(key, None)
            self.settings.update(data)
            save_settings(self.settings)
            self.show_info("Settings imported. NETRA will use the imported preferences; restart if a global UI setting needs a full refresh.")
        except Exception as exc:
            self.show_error(f"Could not import settings: {exc}")

    def reset_ui_preferences(self):
        if QMessageBox.question(self, "Reset UI", "Reset theme, density, font size, accent and UI scale?") != QMessageBox.Yes:
            return
        self.customization = {"accent": "", "font_size": 12, "density": "Comfortable"}
        self.ui_scale = 100
        self.settings["customization"] = dict(self.customization)
        self.settings["ui_scale"] = 100
        save_settings(self.settings)
        self.theme_name = "NETRA Terminal"
        self.settings["theme"] = self.theme_name
        self._apply_theme()
        if hasattr(self, "ui_scale_combo"):
            self.ui_scale_combo.setCurrentText("100%")

    def reset_all_settings(self):
        if QMessageBox.question(self, "Reset Settings", "Reset NETRA preferences to defaults? This keeps chat cache and downloaded files.") != QMessageBox.Yes:
            return
        try:
            if os.path.exists(SETTINGS_FILE):
                os.remove(SETTINGS_FILE)
            self.settings = load_settings()
            self.show_info("Settings reset. Restart NETRA for a completely clean client session.")
        except Exception as exc:
            self.show_error(f"Could not reset settings: {exc}")

    def open_debug_log(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // DEBUG LOG")
        dialog.resize(820, 520)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        view = QListWidget()
        view.addItems(self.debug_log[-1000:] or ["No debug entries yet."])
        layout.addWidget(view, 1)
        row = QHBoxLayout()
        clear = QPushButton("CLEAR")
        def clear_log():
            self.debug_log.clear(); self.settings["debug_log"] = []; save_settings(self.settings); view.clear()
        clear.clicked.connect(clear_log); row.addWidget(clear)
        close = QPushButton("CLOSE"); close.clicked.connect(dialog.accept); row.addWidget(close)
        layout.addLayout(row)
        dialog.exec()

    def show_info(self, message):
        QMessageBox.information(self, "NETRA", message)

    def open_emoji_picker(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // EMOJI")
        dialog.setFixedSize(420, 300)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        search = QLineEdit(); search.setPlaceholderText("Filter emoji…"); layout.addWidget(search)
        grid = QGridLayout(); layout.addLayout(grid)
        emojis = ["😀","😂","🤣","😊","😍","😎","🤔","😮","😢","😭","😡","👍","👎","❤️","🔥","🎉","👀","💀","✨","💯","🙏","🤝","👏","🚀","🎵","🎮","🖼️","⚡","✅","❌","⭐","😴","🤖","🫡","🗿"]
        buttons = []
        def rebuild():
            while grid.count():
                item = grid.takeAt(0); w=item.widget()
                if w: w.deleteLater()
            q=search.text().strip()
            shown=emojis if not q else [e for e in emojis if q in e]
            for i,e in enumerate(shown):
                b=QPushButton(e); b.setFixedSize(48,38); b.clicked.connect(lambda _, x=e: self._insert_emoji(x, dialog)); grid.addWidget(b,i//7,i%7)
        search.textChanged.connect(rebuild); rebuild()
        close=QPushButton("CLOSE"); close.clicked.connect(dialog.reject); layout.addWidget(close)
        dialog.exec()

    def _insert_emoji(self, emoji, dialog=None):
        self.message_entry.insert(emoji)
        self.message_entry.setFocus()
        if dialog: dialog.accept()

    def open_image_viewer(self, path):
        try:
            pix = QPixmap(path)
            if pix.isNull():
                self._open_local_file(path); return
            dialog = QDialog(self); dialog.setWindowTitle(f"NETRA // IMAGE // {os.path.basename(path)}"); dialog.resize(900, 700); dialog.setStyleSheet(self.dialog_qss())
            layout=QVBoxLayout(dialog); scroll=QScrollArea(); scroll.setWidgetResizable(True)
            label=QLabel(); label.setAlignment(Qt.AlignCenter); label.setPixmap(pix.scaled(840, 620, Qt.KeepAspectRatio, Qt.SmoothTransformation)); scroll.setWidget(label); layout.addWidget(scroll,1)
            controls = QHBoxLayout()
            copy_btn = QPushButton("COPY IMAGE")
            def copy_image():
                QApplication.clipboard().setPixmap(pix)
                self.chat_status_label.setText("image copied")
            copy_btn.clicked.connect(copy_image); controls.addWidget(copy_btn)
            save_btn = QPushButton("SAVE AS")
            def save_image():
                dest, _ = QFileDialog.getSaveFileName(dialog, "Save Image", os.path.basename(path), "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
                if dest:
                    pix.save(dest)
            save_btn.clicked.connect(save_image); controls.addWidget(save_btn)
            controls.addStretch(1)
            close=QPushButton("CLOSE"); close.clicked.connect(dialog.accept); controls.addWidget(close)
            layout.addLayout(controls); dialog.exec()
        except Exception as exc:
            self.show_error(f"Could not display image: {exc}")

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
            "remember_username": self.remember_username,
            "auto_open_images": self.auto_open_images,
            "desktop_notifications": self.desktop_notifications,
            "notification_sound_enabled": self.notification_sound_enabled,
            "ui_scale": self.ui_scale,
            "ptt_key": self.ptt_key,
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
        self._save_feature_settings()
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

    def _ptt_key_pressed(self, key):
        return {"Control": Qt.Key_Control, "Shift": Qt.Key_Shift, "Alt": Qt.Key_Alt, "Space": Qt.Key_Space}.get(self.ptt_key, Qt.Key_Control) == key

    def _save_drafts(self):
        try:
            self.settings["drafts"] = dict(self.drafts)
            self.settings["recent_targets"] = list(self.recent_targets)[-20:]
            self.settings["dnd_mode"] = bool(self.dnd_mode)
            save_settings(self.settings)
        except Exception:
            pass

    def _save_current_draft(self):
        try:
            target = str(self.current_target or "")
            if not target or not hasattr(self, "message_entry"):
                return
            value = self.message_entry.text()
            if value:
                self.drafts[target] = value
            else:
                self.drafts.pop(target, None)
            self._save_drafts()
        except Exception:
            pass

    def _restore_draft(self, target):
        try:
            value = str(self.drafts.get(str(target), ""))
            if hasattr(self, "message_entry"):
                self.message_entry.setText(value)
        except Exception:
            pass

    def open_command_palette(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // COMMAND PALETTE")
        dialog.resize(700, 560)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        query = QLineEdit()
        query.setPlaceholderText("Type a command or search…")
        layout.addWidget(query)
        results = QListWidget()
        layout.addWidget(results, 1)

        commands = [
            ("Search messages", self.global_search),
            ("Open notifications", self.open_notification_center),
            ("Open settings", self.open_settings),
            ("Open music player", self.open_music_player),
            ("Open connection diagnostics", self.open_connection_diagnostics),
            ("Open files gallery", self.open_files_gallery),
            ("Open emoji picker", self.open_emoji_picker),
            ("Open VC", self.open_vc_room),
            ("Screen share", self.open_screen_share),
            ("Toggle fullscreen", self.toggle_fullscreen),
            ("Toggle DND", self.toggle_dnd_mode),
            ("Clear image cache", self.flush_image_cache),
            ("Reset UI preferences", self.reset_ui_preferences),
            ("Export settings", self.export_settings),
            ("Import settings", self.import_settings),
            ("Keyboard shortcuts", self.open_shortcuts),
            ("Open 0.2 QoL center", self.open_qol_center),
        ]
        for name in ("general-chat", "random"):
            if name in getattr(self, "server_channels", []):
                commands.append((f"Jump to #{name}", lambda n=name: self.select_channel(n)))
        for partner in getattr(self, "dm_partners", [])[:20]:
            commands.append((f"Open DM @{partner}", lambda n=partner: self.select_dm_channel(n)))

        def populate(text=""):
            results.clear()
            q = str(text).strip().lower()
            matches = [(name, fn) for name, fn in commands if not q or q in name.lower()]
            for name, fn in matches[:80]:
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, fn)
                results.addItem(item)
            if results.count():
                results.setCurrentRow(0)
        def run():
            item = results.currentItem()
            if item is None:
                return
            fn = item.data(Qt.UserRole)
            dialog.accept()
            QTimer.singleShot(0, fn)
        query.textChanged.connect(populate)
        query.returnPressed.connect(run)
        results.itemDoubleClicked.connect(lambda _item: run())
        populate()
        query.setFocus()
        dialog.exec()

    def toggle_dnd_mode(self):
        self.dnd_mode = not bool(self.dnd_mode)
        self._save_drafts()
        self.chat_status_label.setText("DND // notifications muted" if self.dnd_mode else "notifications enabled")

    def open_qol_center(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // 0.2 QOL CENTER")
        dialog.resize(680, 600)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        title = QLabel("NETRA 0.2 // QUALITY OF LIFE")
        title.setProperty("role", "title")
        layout.addWidget(title)
        subtitle = QLabel("Client-side controls available without changing Server.py.")
        subtitle.setProperty("role", "muted")
        layout.addWidget(subtitle)

        grid = QGridLayout()
        actions = [
            ("🔎 SEARCH", self.global_search), ("⌨ SHORTCUTS", self.open_shortcuts),
            ("🔔 NOTIFICATIONS", self.open_notification_center), ("😊 EMOJI", self.open_emoji_picker),
            ("🎵 MUSIC", self.open_music_player), ("🖼 MEDIA", self.open_files_gallery),
            ("🎙 VC", self.open_vc_room), ("🖥 SCREEN SHARE", self.open_screen_share),
            ("⚙ SETTINGS", self.open_settings), ("🛠 DIAGNOSTICS", self.open_connection_diagnostics),
            ("💾 EXPORT SETTINGS", self.export_settings), ("📥 IMPORT SETTINGS", self.import_settings),
            ("🗑 FLUSH IMAGE CACHE", self.flush_image_cache), ("🐛 DEBUG LOG", self.open_debug_log),
        ]
        for i, (label, fn) in enumerate(actions):
            btn = QPushButton(label)
            btn.setMinimumHeight(38)
            btn.clicked.connect(lambda checked=False, f=fn: (dialog.accept(), QTimer.singleShot(0, f)))
            grid.addWidget(btn, i // 2, i % 2)
        layout.addLayout(grid)

        notify = QCheckBox("Notification sounds")
        notify.setChecked(bool(self.notification_sound_enabled))
        notify.toggled.connect(lambda v: (setattr(self, "notification_sound_enabled", bool(v)), self.settings.__setitem__("notification_sound_enabled", bool(v)), save_settings(self.settings)))
        layout.addWidget(notify)
        dnd = QCheckBox("Do Not Disturb")
        dnd.setChecked(bool(self.dnd_mode))
        dnd.toggled.connect(lambda v: (setattr(self, "dnd_mode", bool(v)), self._save_drafts()))
        layout.addWidget(dnd)
        backend = "DXCam/DXGI" if (DXCAM_AVAILABLE and CV2_AVAILABLE and os.name == "nt") else ("MSS fallback" if MSS_AVAILABLE else "PIL fallback")
        layout.addWidget(QLabel(f"Screen capture backend: {backend}"))
        layout.addStretch(1)
        close = QPushButton("CLOSE")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def open_shortcuts(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // KEYBOARD SHORTCUTS")
        dialog.resize(560, 480)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        rows = [
            ("Ctrl + K", "Command palette / search"),
            ("Ctrl + E", "Emoji picker"),
            ("Ctrl + Shift + N", "Notification center"),
            ("Ctrl + L", "Focus message box"),
            ("Ctrl + Shift + F", "Fullscreen"),
            ("Ctrl + Shift + M", "Music player"),
            ("Ctrl + Shift + V", "Open VC"),
            ("Ctrl + Shift + S", "Screen share"),
            ("F11", "Fullscreen"),
            ("Esc", "Close overlays / fullscreen"),
            ("Enter", "Send message"),
            ("↑", "Edit last message when supported"),
        ]
        for key, desc in rows:
            label = QLabel(f"{key:<20}  {desc}")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(label)
        close = QPushButton("CLOSE")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def reset_ui_preferences(self):
        self.settings["ui_scale"] = 100
        self.settings["customization"] = {}
        self.settings["theme"] = "NETRA Terminal"
        self.ui_scale = 100
        self.customization = {}
        self.theme_name = "NETRA Terminal"
        save_settings(self.settings)
        self._apply_theme()
        self.chat_status_label.setText("UI preferences reset")

    def export_settings(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export NETRA Settings", "netra-settings.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            self.chat_status_label.setText("settings exported")
        except Exception as exc:
            self.show_error(f"Could not export settings: {exc}")

    def import_settings(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import NETRA Settings", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                incoming = json.load(f)
            if not isinstance(incoming, dict):
                raise ValueError("Settings file is not an object")
            self.settings.update(incoming)
            save_settings(self.settings)
            self.chat_status_label.setText("settings imported — restart NETRA to apply everything")
        except Exception as exc:
            self.show_error(f"Could not import settings: {exc}")

    def dragEnterEvent(self, event):
        try:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
            else:
                event.ignore()
        except Exception:
            event.ignore()

    def dropEvent(self, event):
        try:
            urls = [u for u in event.mimeData().urls() if u.isLocalFile()]
            if not urls:
                event.ignore(); return
            sent = 0
            for url in urls:
                path = url.toLocalFile()
                if os.path.isfile(path):
                    self._send_local_file_path(path)
                    sent += 1
            if sent:
                self.chat_status_label.setText(f"queued {sent} dropped file{'s' if sent != 1 else ''}")
            event.acceptProposedAction()
        except Exception as exc:
            self.show_error(f"Could not handle dropped files: {exc}")
            event.ignore()

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
        if self.voice_ptt and self._ptt_key_pressed(event.key()):
            self.voice_ptt_down = True
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_K:
            self.open_command_palette(); event.accept(); return
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_E:
            self.open_emoji_picker(); event.accept(); return
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_L:
            self.message_entry.setFocus(); event.accept(); return
        if event.modifiers() & Qt.ControlModifier and event.modifiers() & Qt.ShiftModifier and event.key() == Qt.Key_N:
            self.open_notification_center(); event.accept(); return
        if event.modifiers() & Qt.ControlModifier and event.modifiers() & Qt.ShiftModifier and event.key() == Qt.Key_F:
            self.toggle_fullscreen(); event.accept(); return
        if event.modifiers() & Qt.ControlModifier and event.modifiers() & Qt.ShiftModifier and event.key() == Qt.Key_M:
            self.open_music_player(); event.accept(); return
        if event.modifiers() & Qt.ControlModifier and event.modifiers() & Qt.ShiftModifier and event.key() == Qt.Key_V:
            self.open_vc_room(); event.accept(); return
        if event.modifiers() & Qt.ControlModifier and event.modifiers() & Qt.ShiftModifier and event.key() == Qt.Key_S:
            self.open_screen_share(); event.accept(); return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.voice_ptt and self._ptt_key_pressed(event.key()):
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
            self.connection_started_at = time.monotonic()
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
        self.last_disconnect_at = time.time()
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
                self.connection_started_at = self.connection_started_at or time.monotonic()
                self._stop_reconnect_timer()
                self._broadcast_rich_presence()
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
                if self.last_disconnect_at:
                    away = int(max(0, time.time() - self.last_disconnect_at))
                    if away >= 30:
                        self._show_while_away(away)
                    self.last_disconnect_at = None
                self.send_own_pfp()
            return

        if raw.startswith("AUTH_FAIL:"):
            reason = raw.split(":", 1)[1]
            self._stop_reconnect_timer()
            if self.auth_dialog:
                self.auth_dialog.status.setText(reason)
            elif not self.offline_mode:
                self.chat_status_label.setText(f"reconnect stopped // {reason}")
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

        # Music is client-local.  Ignore legacy server music packets so an older
        # server cannot overwrite this user's private playlist or playback state.
        if raw.startswith(("MUSIC_STATE:", "MUSIC_ADDED:", "MUSIC_ERROR:", "MUSIC_LISTEN:", "MUSIC_PCM:")):
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
                if payload.get("sender") != my_name:
                    self._notify_incoming(payload.get("room", "general-chat"), payload.get("sender", ""), payload.get("text", "New message"))
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
                    self._notify_incoming(p[1], p[2], p[3])
            return

        if raw.startswith("GLOBAL:"):
            p = raw.split(":", 2)
            if len(p) == 3:
                self.store_message("general-chat", p[1], p[2], local=False)
                if p[1] != my_name:
                    self._notify_incoming("general-chat", p[1], p[2])
            return

        if raw.startswith("DM:"):
            p = raw.split(":", 3)
            if len(p) == 4:
                self.store_message(p[1], p[2], p[3], local=False)
                if p[2] != my_name:
                    self._notify_incoming(p[1], p[2], p[3])
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

        if raw.startswith("AUDIT:"):
            try:
                payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
                if not hasattr(self, "audit_log"):
                    self.audit_log = []
                self.audit_log.append(payload)
            except Exception:
                pass
            return

        if raw.startswith("PINNED:"):
            try:
                payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
                room = payload.get("room", self.current_target)
                for msg in self.chat_history.get(room, []):
                    if msg.get("id") == payload.get("message_id"):
                        msg["pinned"] = bool(payload.get("pinned", True))
                        break
                self.reload_current_chat_view(preserve_scroll=True)
            except Exception:
                pass
            return

        if raw.startswith("UNDELETED:"):
            try:
                payload = json.loads(base64.b64decode(raw.split(":", 1)[1]).decode("utf-8"))
                self.store_message(payload.get("room", self.current_target), payload.get("sender", self.username), payload.get("text", ""), message_id=payload.get("id"), reply_to=payload.get("reply_to"), reactions=payload.get("reactions") or {})
            except Exception:
                pass
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
        self.store_message(room, self.username, text, local=True, message_id=message_id, reply_to=reply_to)
        self.message_entry.clear()
        self.drafts.pop(room, None)
        self._save_drafts()
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
            # Images are cached automatically so image messages can render without
            # making the user press DOWNLOAD first. Other file types remain manual.
            if str(payload.get("mime", "")).startswith("image/"):
                self._download_file(payload, auto_open=self.auto_open_images)
        except Exception as exc:
            self.chat_status_label.setText(f"file offer error // {exc}")

    def _download_file(self, file_meta, auto_open=True):
        if not file_meta:
            return
        file_id = file_meta.get("file_id")
        local = local_file_path(file_id, file_meta.get("name", "file"))
        if os.path.exists(local) and os.path.getsize(local) == int(file_meta.get("size", -1)):
            if auto_open:
                self._open_local_file(local, file_meta)
            return
        request = {"room": self.current_target, "file_id": file_id, "sender": file_meta.get("sender", "")}
        encoded = base64.b64encode(json.dumps(request, separators=(",", ":")).encode("utf-8")).decode("ascii")
        self._network_send(f"FILE_REQUEST:{encoded}")
        self.chat_status_label.setText(f"downloading // {file_meta.get('name', 'file')}")

    def _open_local_file(self, path, meta=None):
        try:
            mime = str((meta or {}).get("mime", "")) or (mimetypes.guess_type(path)[0] or "")
            if mime.startswith("image/"):
                self.open_image_viewer(path)
                return
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

    def _member_item_clicked(self, item):
        widget = self.members_list.itemWidget(item)
        if widget is None:
            return
        name_labels = widget.findChildren(QLabel, "memberName")
        if name_labels:
            self.show_user_profile(name_labels[0].text().replace("  [YOU]", ""))

    def show_user_profile(self, user):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"NETRA // PROFILE // {user}")
        dialog.setFixedSize(420, 360)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        avatar = QLabel()
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedHeight(110)
        avatar_img = self.user_pfps.get(user, Image.new("RGB", (96, 96), "#0F3D0F"))
        avatar.setPixmap(self.pil_to_pixmap(avatar_img, (96, 96)))
        layout.addWidget(avatar)
        title = QLabel(user)
        title.setProperty("role", "title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        status = self.presence_status.get(user, "UNKNOWN")
        custom = self.custom_status.get(user, "")
        info = QLabel(f"STATUS: {status}\nCUSTOM: {custom or 'none'}\nVOICE: {'connected' if user in self.voice_users else 'not connected'}")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch(1)
        if user != self.username:
            dm = QPushButton("MESSAGE")
            dm.clicked.connect(lambda: (dialog.accept(), self.select_dm_channel(user)))
            layout.addWidget(dm)
        # These commands are harmless UI-side requests; the server decides permissions.
        if self.authenticated and user != self.username:
            mod = QPushButton("MODERATION / ROLES")
            mod.clicked.connect(lambda: (dialog.accept(), self.open_moderation_panel(user)))
            layout.addWidget(mod)
        close = QPushButton("CLOSE")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def open_moderation_panel(self, user):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"NETRA // MODERATION // {user}")
        dialog.setFixedSize(420, 430)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"TARGET: {user}"))
        role = QLineEdit()
        role.setPlaceholderText("Role name for ADD/REMOVE ROLE")
        layout.addWidget(role)
        for label, command in (("ADD ROLE", "ROLE_ADD"), ("REMOVE ROLE", "ROLE_REMOVE"),
                               ("TIMEOUT", "TIMEOUT"), ("KICK", "KICK"), ("BAN", "BAN")):
            btn = QPushButton(label)
            def send(cmd=command, target=user):
                payload = {"target": target, "role": role.text().strip()} if cmd.startswith("ROLE_") else {"target": target}
                if cmd == "TIMEOUT":
                    payload["seconds"] = 60
                enc = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
                self._network_send(f"{cmd}:{enc}")
                dialog.accept()
            btn.clicked.connect(send)
            layout.addWidget(btn)
        audit = QPushButton("OPEN AUDIT LOG")
        audit.clicked.connect(lambda: (dialog.accept(), self.open_audit_log()))
        layout.addWidget(audit)
        dialog.exec()

    def open_audit_log(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // AUDIT LOG")
        dialog.resize(700, 520)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        view = QListWidget()
        entries = getattr(self, "audit_log", [])
        if not entries:
            view.addItem("No audit events received by this client.")
        else:
            for entry in entries[-500:]:
                view.addItem(str(entry))
        layout.addWidget(view)
        close = QPushButton("CLOSE")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def edit_custom_status(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // CUSTOM STATUS")
        dialog.setFixedSize(420, 180)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        entry = QLineEdit(self.custom_status.get(self.username, ""))
        entry.setPlaceholderText("What are you doing?")
        layout.addWidget(entry)
        save = QPushButton("SAVE STATUS")
        def save_status():
            value = entry.text().strip()[:180]
            self.custom_status[self.username] = value
            self.presence_status[self.username] = self.presence_status.get(self.username, "online")
            enc = base64.b64encode(json.dumps({"status": self.presence_status[self.username], "custom": value}, separators=(",", ":")).encode()).decode()
            self._network_send(f"STATUS_SET:{enc}")
            self._refresh_member_list()
            dialog.accept()
        save.clicked.connect(save_status)
        layout.addWidget(save)
        dialog.exec()

    def global_search(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // GLOBAL SEARCH")
        dialog.resize(760, 560)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        query = QLineEdit()
        query.setPlaceholderText("Search messages, users, files…")
        layout.addWidget(query)
        results = QListWidget()
        layout.addWidget(results, 1)
        def run():
            results.clear()
            q = query.text().strip().lower()
            if not q:
                return
            found = []
            for room, messages in self.chat_history.items():
                for msg in messages:
                    hay = f"{room} {msg.get('sender','')} {msg.get('text','')}".lower()
                    if q in hay:
                        found.append((room, msg))
            for room, msg in found[-300:][::-1]:
                item = QListWidgetItem(f"#{room} // {msg.get('sender','?')}: {msg.get('text','')[:220]}")
                item.setData(Qt.UserRole, (room, msg.get("id")))
                results.addItem(item)
            if not found:
                results.addItem("No local cached matches.")
        query.textChanged.connect(run)
        def jump(item):
            data = item.data(Qt.UserRole)
            if data:
                self.select_channel(data[0])
                dialog.accept()
        results.itemDoubleClicked.connect(jump)
        close = QPushButton("CLOSE")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def toggle_pin_message(self, message):
        if not message or not message.get("id"):
            return
        room = self.current_target
        mid = message["id"]
        state = not bool(message.get("pinned"))
        message["pinned"] = state
        self.pinned_messages.setdefault(room, {})[mid] = message if state else None
        if not state:
            self.pinned_messages[room].pop(mid, None)
        self._chat_cache_dirty = True
        self._save_chat_cache()
        payload = {"room": room, "message_id": mid, "pinned": state}
        enc = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
        self._network_send(f"PIN:{enc}")
        self.reload_current_chat_view(preserve_scroll=True)

    def show_pinned_messages(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"NETRA // PINS // #{self.current_target}")
        dialog.resize(700, 500)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        view = QListWidget()
        for msg in self.chat_history.get(self.current_target, []):
            if msg.get("pinned"):
                view.addItem(f"{msg.get('sender','?')}: {msg.get('text','')[:300]}")
        if not view.count():
            view.addItem("No pinned messages in this channel.")
        layout.addWidget(view, 1)
        close = QPushButton("CLOSE")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def edit_message(self, message):
        if not message or message.get("sender") != self.username:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // EDIT MESSAGE")
        dialog.setFixedSize(520, 190)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        entry = QLineEdit(message.get("text", ""))
        layout.addWidget(entry)
        save = QPushButton("SAVE EDIT")
        def commit():
            text = entry.text().strip()
            if not text:
                return
            message["text"] = text
            message["edited"] = True
            payload = {"room": self.current_target, "message_id": message.get("id"), "text": text}
            enc = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
            self._network_send(f"EDIT:{enc}")
            self._save_chat_cache()
            self.reload_current_chat_view(preserve_scroll=True)
            dialog.accept()
        save.clicked.connect(commit)
        entry.returnPressed.connect(commit)
        layout.addWidget(save)
        dialog.exec()

    def open_thread(self, message):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // THREAD")
        dialog.resize(650, 520)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        root = QLabel(f"THREAD ROOT // {message.get('sender','?')}: {message.get('text','')}")
        root.setWordWrap(True)
        layout.addWidget(root)
        view = QListWidget()
        root_id = message.get("id")
        replies = []
        for msg in self.chat_history.get(self.current_target, []):
            if (msg.get("reply_to") or {}).get("id") == root_id:
                replies.append(msg)
        for reply in replies:
            view.addItem(f"{reply.get('sender','?')}: {reply.get('text','')}")
        if not replies:
            view.addItem("No replies cached for this thread.")
        layout.addWidget(view, 1)
        reply = QPushButton("REPLY IN THREAD")
        reply.clicked.connect(lambda: (dialog.accept(), self._set_reply_target(message)))
        layout.addWidget(reply)
        dialog.exec()

    def toggle_channel_notifications(self):
        room = self.current_target
        current = self.notification_settings.get(room, True)
        self.notification_settings[room] = not current
        self.settings["notification_settings"] = dict(self.notification_settings)
        save_settings(self.settings)
        self.notify_button.setText("NOTIFY" if self.notification_settings[room] else "MUTED")

    def open_files_gallery(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("NETRA // FILES / IMAGE GALLERY")
        dialog.resize(820, 600)
        dialog.setStyleSheet(self.dialog_qss())
        layout = QVBoxLayout(dialog)
        view = QListWidget()
        files = []
        for name in os.listdir(FILE_CACHE_DIR):
            path = os.path.join(FILE_CACHE_DIR, name)
            if os.path.isfile(path) and not name.endswith(".part"):
                files.append(path)
        for path in sorted(files, key=os.path.getmtime, reverse=True):
            item = QListWidgetItem(f"{os.path.basename(path)}  //  {format_file_size(os.path.getsize(path))}")
            item.setData(Qt.UserRole, path)
            view.addItem(item)
        if not files:
            view.addItem("No cached files yet.")
        view.itemDoubleClicked.connect(lambda item: self._open_local_file(item.data(Qt.UserRole)) if item.data(Qt.UserRole) else None)
        layout.addWidget(view, 1)
        flush = QPushButton("FLUSH IMAGE CACHE")
        flush.clicked.connect(self.flush_image_cache)
        layout.addWidget(flush)
        close = QPushButton("CLOSE")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def flush_image_cache(self):
        removed = 0
        for name in os.listdir(FILE_CACHE_DIR):
            path = os.path.join(FILE_CACHE_DIR, name)
            if os.path.isfile(path) and not name.endswith(".part"):
                try:
                    mime = mimetypes.guess_type(path)[0] or ""
                    if mime.startswith("image/"):
                        os.remove(path); removed += 1
                except Exception:
                    pass
        self.chat_status_label.setText(f"image cache flushed // {removed} removed")
        self.reload_current_chat_view(preserve_scroll=True)

    def paste_clipboard_image(self):
        clipboard = QApplication.clipboard()
        image = clipboard.image()
        if image.isNull():
            self.show_error("Clipboard does not contain an image.")
            return
        path = os.path.join(FILE_CACHE_DIR, f"clipboard_{uuid.uuid4().hex}.png")
        if not image.save(path, "PNG"):
            self.show_error("Could not save the clipboard image.")
            return
        self._send_local_file_path(path)

    def _send_local_file_path(self, path):
        # Reuse the normal file sender by temporarily routing through its metadata path.
        try:
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE:
                self.show_error("Clipboard image is too large.")
                return
            file_id = uuid.uuid4().hex
            mime = mimetypes.guess_type(path)[0] or "image/png"
            meta = {"file_id": file_id, "name": os.path.basename(path), "size": size, "mime": mime,
                    "sha256": self._file_digest(path), "sender": self.username, "room": self.current_target}
            # local_file_path uses the file id, so copy into the canonical cache location.
            target = local_file_path(file_id, meta["name"])
            if os.path.abspath(path) != os.path.abspath(target):
                with open(path, "rb") as src, open(target, "wb") as dst: dst.write(src.read())
            payload = {"room": self.current_target, "id": uuid.uuid4().hex, "text": "", "file": meta, "kind": "file"}
            meta["message_id"] = payload["id"]
            self._pending_file_sends[file_id] = meta
            self.store_message(self.current_target, self.username, "", local=True, message_id=payload["id"], kind="file", file_meta=meta)
            enc = base64.b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).decode()
            self._network_send(f"MESSAGE:{enc}")
            threading.Thread(target=self._send_file_chunks, args=(meta,), daemon=True).start()
        except Exception as exc:
            self.show_error(f"Could not paste image: {exc}")

    def open_first_url(self, text):
        import re
        match = re.search(r"https?://[^\\s<>]+", str(text))
        if not match:
            return
        try:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(match.group(0)))
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

    def _copy_message_text(self, message):
        try:
            text = str((message or {}).get("text", ""))
            if not text and (message or {}).get("file"):
                file_meta = message.get("file") or {}
                text = str(file_meta.get("name", ""))
            QApplication.clipboard().setText(text)
            self.chat_status_label.setText("message copied")
        except Exception as exc:
            self.show_error(f"Could not copy message: {exc}")

    def _copy_message_id(self, message):
        try:
            mid = str((message or {}).get("id", ""))
            if not mid:
                return
            QApplication.clipboard().setText(mid)
            self.chat_status_label.setText("message ID copied")
        except Exception as exc:
            self.show_error(f"Could not copy message ID: {exc}")

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
        self.deleted_undo = (self.current_target, dict(message))
        self._network_send(f"DELETE:{encoded}")
        self._show_undo_delete_banner()

    def _show_undo_delete_banner(self):
        if not self.deleted_undo or not hasattr(self, "reply_banner"):
            return
        room, msg = self.deleted_undo
        self.reply_banner_label.setText(f"MESSAGE DELETED: {msg.get('text','')[:100]}")
        self.reply_banner.setVisible(True)
        self.reply_cancel_button.setText("UNDO")
        try:
            self.reply_cancel_button.clicked.disconnect()
        except Exception:
            pass
        self.reply_cancel_button.clicked.connect(self.undo_delete_message)
        QTimer.singleShot(6000, self._clear_undo_delete_banner)

    def undo_delete_message(self):
        if not self.deleted_undo:
            return
        room, msg = self.deleted_undo
        payload = dict(msg)
        enc = base64.b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).decode()
        self._network_send(f"UNDELETE:{enc}")
        self.store_message(room, payload.get("sender", self.username), payload.get("text", ""), local=True, message_id=payload.get("id"), reply_to=payload.get("reply_to"), reactions=payload.get("reactions") or {})
        self.deleted_undo = None
        self._clear_undo_delete_banner()
        self.reload_current_chat_view(preserve_scroll=True)

    def _clear_undo_delete_banner(self):
        if not hasattr(self, "reply_banner"):
            return
        if self.deleted_undo is None:
            self.reply_banner.setVisible(False)
            self.reply_banner_label.clear()
            try:
                self.reply_cancel_button.clicked.disconnect()
            except Exception:
                pass
            self.reply_cancel_button.clicked.connect(self._clear_reply_target)
            self.reply_cancel_button.setText("CANCEL")

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
        self._save_current_draft()
        self.current_target = channel
        self.recent_targets = [x for x in self.recent_targets if x != channel] + [channel]
        self._mark_room_read(channel)
        self._broadcast_rich_presence()
        self.chat_title_label.setText(f"# {channel}")
        self.message_entry.setPlaceholderText(f"Message #{channel}")
        self._highlight_channel(channel)
        self._restore_draft(channel)
        self._save_drafts()
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
        self._save_current_draft()
        self.current_target = partner
        self.recent_targets = [x for x in self.recent_targets if x != partner] + [partner]
        self._mark_room_read(partner)
        self._broadcast_rich_presence()
        self.chat_title_label.setText(f"@ {partner}")
        self.message_entry.setPlaceholderText(f"Message @{partner}")
        self._restore_draft(partner)
        self._save_drafts()
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
            unread = int(self.unread_counts.get(partner, 0))
            label = f"@ {partner}" + (f"  ({unread})" if unread else "")
            item = QListWidgetItem(label)
            if unread:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.dm_list.addItem(item)

    def _dm_item_clicked(self, item):
        text = item.text().removeprefix("@ ")
        if "  (" in text:
            text = text.rsplit("  (", 1)[0]
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
            wave = QLabel("▁▂▃▄▅▆▇")
            wave.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            wave.setFixedWidth(72)
            wave.setStyleSheet(f"color:{self.palette_colors()['dim']}; font-family:Consolas; font-size:12px; font-weight:700;")
            layout.addWidget(wave)
            self.voice_wave_labels[user] = wave
            self.voice_wave_state.setdefault(user, {"level": 0.0, "peak": 0.0, "history": [0.0] * 7})
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
        self.voice_wave_state = {}
        for user in self.voice_users:
            widget = self._make_member_widget(user, online=True, voice=True)
            self._add_widget_item(self.voice_user_list, widget, 44)
        self._refresh_voice_user_settings()
        self._refresh_voice_hud()

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
        copy_btn = QPushButton("COPY")
        copy_btn.setObjectName("messageActionButton")
        copy_btn.setToolTip("Copy message text")
        copy_btn.clicked.connect(lambda _=False, m=msg: self._copy_message_text(m))
        actions_layout.addWidget(copy_btn)
        copy_id_btn = QPushButton("ID")
        copy_id_btn.setObjectName("messageActionButton")
        copy_id_btn.setToolTip("Copy message ID")
        copy_id_btn.clicked.connect(lambda _=False, m=msg: self._copy_message_id(m))
        actions_layout.addWidget(copy_id_btn)
        react_btn = QPushButton("REACT")
        react_btn.setObjectName("messageActionButton")
        react_btn.clicked.connect(lambda _=False, m=msg: self._react_to_message(m))
        actions_layout.addWidget(react_btn)
        thread_btn = QPushButton("THREAD")
        thread_btn.setObjectName("messageActionButton")
        thread_btn.clicked.connect(lambda _=False, m=msg: self.open_thread(m))
        actions_layout.addWidget(thread_btn)
        pin_btn = QPushButton("UNPIN" if msg.get("pinned") else "PIN")
        pin_btn.setObjectName("messageActionButton")
        pin_btn.clicked.connect(lambda _=False, m=msg: self.toggle_pin_message(m))
        actions_layout.addWidget(pin_btn)
        if sender == self.username:
            edit_btn = QPushButton("EDIT")
            edit_btn.setObjectName("messageActionButton")
            edit_btn.clicked.connect(lambda _=False, m=msg: self.edit_message(m))
            actions_layout.addWidget(edit_btn)
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
            lower = str(text).lower()
            if "youtube.com/watch?v=" in lower or "youtu.be/" in lower or "youtube.com/shorts/" in lower:
                yt = QPushButton("▶ OPEN YOUTUBE")
                yt.setObjectName("messageActionButton")
                yt.clicked.connect(lambda _=False, t=text: self.open_first_url(t))
                body.addWidget(yt, alignment=Qt.AlignLeft)

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
            # PFPs are sent separately from chat history during login.
            # Refresh the current message view so cached/history messages
            # replace the green fallback avatar as soon as the PFP arrives.
            if self.current_target:
                self.reload_current_chat_view()
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
                winsound.PlaySound(None, 0)
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return
        except Exception:
            pass

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

    def _stop_music_listener(self):
        self._stop_local_music()

    def _toggle_music_listener(self):
        if self.music_listening or self.music_state.get("playing"):
            self.music_listening = False
            self._stop_local_music()
        else:
            if not SOUNDDEVICE_AVAILABLE:
                self.show_error("Local music playback requires sounddevice. Install it with:\npython -m pip install sounddevice")
                return
            if not AV_AVAILABLE:
                self.show_error("Local music playback requires PyAV. Install it with:\npython -m pip install av")
                return
            self.music_listening = True
            self._play_local_music()
        self._refresh_music_dialog()

    def toggle_voice_mute(self):
        self.voice_muted = not self.voice_muted
        if hasattr(self, "voice_mute_button"):
            self.voice_mute_button.setText("UNMUTE MIC" if self.voice_muted else "MUTE MIC")
        self._refresh_voice_hud()

    def toggle_deafen(self):
        self.voice_deafened = not self.voice_deafened
        self.settings["voice_deafen"] = self.voice_deafened
        save_settings(self.settings)
        if hasattr(self, "voice_deafen_button"):
            self.voice_deafen_button.setText("UNDEAFEN" if self.voice_deafened else "DEAFEN")
        self._refresh_voice_hud()
        # Deafen only affects incoming voice.  Keep the microphone running.
        if self.voice_deafened:
            try:
                while True:
                    self.voice_play_queue.get_nowait()
            except Exception:
                pass

    def stop_voice_chat(self):
        self.voice_hud_expanded = False
        if hasattr(self, "chat_scroll"):
            self.chat_scroll.setVisible(True)
        if hasattr(self, "voice_hud_expanded_panel"):
            self.voice_hud_expanded_panel.setVisible(False)
            self.voice_hud_scroll.setVisible(True)
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
        self.voice_wave_state = {}
        self.voice_send_resampler = None
        self.voice_button.setText("JOIN VOICE")
        if self.screen_sharing:
            self._stop_screen_share_capture()
        self._refresh_voice_hud()
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

        now = time.monotonic()
        bright = self.palette_colors()["bright"]
        dim = self.palette_colors()["dim"]
        levels = list(self.voice_levels.items())
        for user in self.voice_users:
            raw = max(0.0, min(1.0, float(self.voice_levels.get(user, 0.0))))
            age = now - float(self.voice_activity.get(user, 0.0))
            if age > 0.12:
                raw *= max(0.0, 1.0 - (age - 0.12) / 0.85)
            state = self.voice_wave_state.setdefault(user, {"level": 0.0, "peak": 0.0, "history": [0.0] * 7})
            # Fast attack, slower release gives speech a lively but stable meter.
            old = state["level"]
            state["level"] = old + (raw - old) * (0.55 if raw > old else 0.18)
            state["peak"] = max(state["level"], state["peak"] * 0.94)
            hist = state["history"]
            hist.append(state["level"])
            del hist[:-7]
            label = self.voice_wave_labels.get(user)
            if label:
                bars = "▁▂▃▄▅▆▇█"
                wave = "".join(bars[min(7, int(max(0.0, v) * 8.0))] for v in hist)
                label.setText(wave)
                label.setStyleSheet(f"color:{bright if state['level'] > 0.035 else dim}; font-family:Consolas; font-size:12px; font-weight:700;")
            if state["level"] > 0.035 and age < 1.2:
                self.voice_radar_label.setText(
                    "VOICE RADAR\n" + "  ".join(
                        (u if u != self.username else "YOU") for u in self.voice_users
                        if self.voice_wave_state.get(u, {}).get("level", 0.0) > 0.035
                    )
                )

        if self.voice_users and not any(self.voice_wave_state.get(u, {}).get("level", 0.0) > 0.035 for u in self.voice_users):
            self.voice_radar_label.setText("VOICE RADAR\nlistening…")
        elif not self.voice_users:
            self.voice_radar_label.setText("VOICE RADAR\nno one connected")

        self._update_voice_hud()

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
                "notification_settings": self.notification_settings,
                "notification_history": self.notification_history[-200:],
                "rich_presence": self.rich_presence,
                "customization": self.customization,
                "music_playlists": self.music_playlists,
                "active_playlist": self.active_playlist,
                "client_plugins": self.client_plugins,
                "server_plugins": self.server_plugins,
                "developer_mode": self.developer_mode,
                "screen_share_quality": self.screen_share_quality,
            "screen_share_source": self.screen_share_source,
            "screen_share_fps": self.screen_share_fps,
            "screen_share_cursor": self.screen_share_cursor,
                "offline_mode": self.offline_mode,
                "voice_input_device": self._audio_selection_to_index(self.input_device_combo.currentText()) if hasattr(self, "input_device_combo") else self.settings.get("voice_input_device"),
                "voice_output_device": self._audio_selection_to_index(self.output_device_combo.currentText()) if hasattr(self, "output_device_combo") else self.settings.get("voice_output_device"),
                "remember_username": self.remember_username,
                "auto_open_images": self.auto_open_images,
                "desktop_notifications": self.desktop_notifications,
                "notification_sound_enabled": self.notification_sound_enabled,
                "ui_scale": self.ui_scale,
                "ptt_key": self.ptt_key,
                "debug_log": self.debug_log[-1000:],
            })
            self._save_feature_settings()
            save_settings(self.settings)
            self._save_chat_cache()
        except Exception:
            pass
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
