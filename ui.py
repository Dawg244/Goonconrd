import base64
import io
import json
import math
import os
import queue
import socket
import struct
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv, set_key
from PIL import Image

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    SOUNDDEVICE_AVAILABLE = False

try:
    from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, QSize
    from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPixmap
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
PROFILE_IMAGE_FILE = os.path.join(CONFIG_DIR, "profile.png")
ICON_DIR = os.path.join(BASE_DIR, "assets", "icons")
os.makedirs(ICON_DIR, exist_ok=True)
load_dotenv(ENV_FILE, override=True)

DEFAULT_HOST = "108.221.36.120"
PORT = 12145
VOICE_RATE_DEFAULT = 24000
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


def save_settings(data: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def load_settings() -> dict:
    defaults = {
        "theme": "NETRA Terminal",
        "dm_sound_mode": "ping",
        "dm_sound_path": "",
        "voice_input_device": None,
        "voice_output_device": None,
        "voice_volume": 1.25,
        "voice_mic_gain": 1.0,
        "voice_quality": "High",
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
        self.setFixedSize(430, 440)
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
        layout.addSpacing(10)

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

        footer = QLabel(
            "Your account is stored on the NETRA main server.\n"
            f"Server: {DEFAULT_HOST}:{PORT}"
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setProperty("role", "muted")
        layout.addWidget(footer)

        self.password.returnPressed.connect(lambda: self.submit("LOGIN"))
        self.username.returnPressed.connect(self.password.setFocus)
        self.username.setFocus()

    def submit(self, mode):
        username = self.username.text().strip()
        password = self.password.text()
        if not username:
            self.status.setText("Enter a username.")
            self.username.setFocus()
            return
        if not password:
            self.status.setText("Enter a password.")
            self.password.setFocus()
            return
        self.status.setProperty("role", "muted")
        self.style().unpolish(self.status)
        self.style().polish(self.status)
        self.status.setText("Connecting to NETRA...")
        self.authenticated.emit(mode, username, password)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class FullDiscordClone(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.theme_name = self.settings.get("theme", "NETRA Terminal")
        if self.theme_name not in THEMES:
            self.theme_name = "NETRA Terminal"

        self.server_host = DEFAULT_HOST
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
        self.voice_activity = {}
        self.loading_history = False
        self._chat_cache_dirty = False
        self._render_generation = 0

        self.voice_muted = False
        self.in_voice_chat = False
        self.voice_input_stream = None
        self.voice_output_stream = None
        self.voice_input_rate = 48000
        self.voice_output_rate = 48000
        self.voice_play_queue = queue.Queue(maxsize=80)
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
        self.voice_stats_timer.start(500)

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
        QFrame#messageCard {{ background: transparent; border: none; }}
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
            padding: 5px 8px;
            font-family: Consolas;
            font-size: 11px;
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

        self.voice_button = QPushButton("🎤 Join Voice")
        self.voice_button.setFixedHeight(32)
        self.voice_button.clicked.connect(self.toggle_voice_chat)
        side.addWidget(self.voice_button)

        self.voice_mute_button = QPushButton("🔇 Mute Mic")
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
        self.server_ip_entry.setReadOnly(True)
        server_bar_layout.addWidget(self.server_ip_entry)
        self.server_connect_btn = QPushButton("CONNECT")
        self.server_connect_btn.setFixedWidth(90)
        self.server_connect_btn.setFixedHeight(30)
        self.server_connect_btn.clicked.connect(self.connect_and_auth)
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
        chat_layout.addWidget(self.chat_scroll, 1)

        compose = QHBoxLayout()
        compose.setSpacing(6)
        self.message_entry = QLineEdit()
        self.message_entry.setPlaceholderText("Message #general-chat")
        self.message_entry.setFixedHeight(44)
        self.message_entry.returnPressed.connect(self.send_message)
        compose.addWidget(self.message_entry, 1)
        self.send_button = QPushButton("SEND")
        self.send_button.setFixedSize(80, 44)
        self.send_button.clicked.connect(self.send_message)
        compose.addWidget(self.send_button)
        chat_layout.addLayout(compose)
        root.addWidget(self.chat_frame, 1)

        # ---------------- right member panel ----------------
        self.members = QFrame(objectName="panel")
        self.members.setFixedWidth(180)
        mem = QVBoxLayout(self.members)
        mem.setContentsMargins(10, 10, 10, 10)
        mem.setSpacing(5)
        self.voice_header = QLabel("IN VOICE 🔊")
        mem.addWidget(self.voice_header)
        self.voice_user_list = QListWidget()
        self.voice_user_list.setFixedHeight(125)
        mem.addWidget(self.voice_user_list)
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
        outer.setContentsMargins(20, 16, 20, 14)
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
        body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
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
        test_btn = QPushButton("🎙 TEST MICROPHONE (3 SEC)")
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
            ("👤 PROFILE / PFP", self.upload_pfp),
            ("✏ CHANGE USERNAME", self.rename_username),
            ("🎨 THEMES", lambda: self.theme_combo.setFocus()),
            ("⛶ FULLSCREEN", self.toggle_fullscreen),
        ]
        for i, (label, fn) in enumerate(actions):
            b = QPushButton(label)
            b.setMinimumHeight(34)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
        save_btn.setFixedHeight(36)
        save_btn.setMinimumWidth(150)
        save_btn.clicked.connect(self.save_settings_from_ui)
        footer_layout.addWidget(save_btn)
        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(36)
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.close_settings)
        footer_layout.addWidget(close_btn)
        outer.addWidget(footer)
    def _test_microphone(self):
        if not SOUNDDEVICE_AVAILABLE:
            self.voice_test_status.setText("sounddevice is not installed. Install it with: python -m pip install sounddevice")
            return

        in_device = self._audio_selection_to_index(self.input_device_combo.currentText())
        out_device = self._audio_selection_to_index(self.output_device_combo.currentText())
        self.voice_test_status.setText("Testing microphone + playback for 3 seconds…")
        self.voice_test_status.setProperty("role", "muted")
        self.voice_test_status.style().unpolish(self.voice_test_status)
        self.voice_test_status.style().polish(self.voice_test_status)

        def worker():
            try:
                in_info = sd.query_devices(in_device, "input")
                out_info = sd.query_devices(out_device, "output")
                in_channels = int(in_info.get("max_input_channels", 0) or 0)
                out_channels = int(out_info.get("max_output_channels", 0) or 0)
                if in_channels < 1:
                    raise RuntimeError(f"Selected microphone has no input channels: {in_info.get('name', 'unknown')}")
                if out_channels < 1:
                    raise RuntimeError(f"Selected output has no output channels: {out_info.get('name', 'unknown')}")

                rate = int(round(float(in_info.get("default_samplerate") or 48000)))
                out_rate = int(round(float(out_info.get("default_samplerate") or 48000)))
                sd.check_input_settings(device=in_device, samplerate=rate, channels=1, dtype="int16")
                sd.check_output_settings(device=out_device, samplerate=out_rate, channels=1, dtype="int16")

                duration = 3.0
                recording = sd.rec(
                    int(rate * duration),
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    device=in_device,
                    blocking=True,
                )
                raw = recording.tobytes()
                count = len(raw) // 2
                values = struct.unpack(f"<{count}h", raw[:count * 2]) if count else ()
                peak = max((abs(v) for v in values), default=0)
                rms = math.sqrt(sum(v * v for v in values) / max(1, len(values)))
                db_peak = -60.0 if peak <= 0 else 20.0 * math.log10(peak / 32768.0)
                db_rms = -60.0 if rms <= 0 else 20.0 * math.log10(rms / 32768.0)

                # Play the recording back through the selected output so this
                # test validates both the mic and speakers/headphones.
                playback = resample_pcm16_mono(raw, rate, out_rate)
                sd.play(playback, samplerate=out_rate, device=out_device, blocking=True)
                sd.stop()

                if peak <= 100:
                    msg = (
                        "✗ Microphone opened, but almost no signal was captured "
                        f"(peak {peak}). Check Windows mic permissions / mute state."
                    )
                    self._set_voice_test_status(msg, True)
                else:
                    msg = (
                        "✓ Mic test complete + playback verified // "
                        f"peak {peak} ({db_peak:.1f} dBFS) // RMS {db_rms:.1f} dBFS"
                    )
                    self._set_voice_test_status(msg, False)
            except Exception as exc:
                try:
                    sd.stop()
                except Exception:
                    pass
                self._set_voice_test_status(f"✗ Microphone test failed: {type(exc).__name__}: {exc}", True)

        threading.Thread(target=worker, daemon=True).start()

    def _set_voice_test_status(self, text, error):
        def apply():
            self.voice_test_status.setText(text)
            self.voice_test_status.setProperty("role", "error" if error else "muted")
            self.voice_test_status.style().unpolish(self.voice_test_status)
            self.voice_test_status.style().polish(self.voice_test_status)
        QTimer.singleShot(0, apply)

    # ---------- dialogs / settings ----------

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

    def connect_and_auth(self, mode, username, password):
        self.username = username
        self.server_host = DEFAULT_HOST
        self.server_port = PORT
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
        self.chat_status_label.setText("network error")
        if not self.authenticated and self.auth_dialog:
            self.auth_dialog.status.setText(message)

    def _network_disconnected(self):
        self.chat_status_label.setText("disconnected")
        self.authenticated = False

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
            return

        if raw.startswith("AUTH_FAIL:"):
            reason = raw.split(":", 1)[1]
            if self.auth_dialog:
                self.auth_dialog.status.setText(reason)
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

    def _network_send(self, text):
        if self.client_socket and self.authenticated:
            try:
                payload = (text + "\n").encode("utf-8")
                with self.send_lock:
                    self.client_socket.sendall(payload)
                return True
            except Exception as exc:
                self.show_error(f"Network error: {exc}")
        return False

    # ---------- chat / members ----------

    def store_message(self, room, sender, text, local=False):
        room = room or "general-chat"
        self.chat_history.setdefault(room, [])
        key = (room, sender, text)
        if local:
            self.pending_local_messages.add(key)
        elif sender == self.username and key in self.pending_local_messages:
            self.pending_local_messages.discard(key)
            return
        message = {"sender": sender, "text": text, "id": f"{time.time_ns()}"}
        self.chat_history[room].append(message)
        self.chat_history[room] = self.chat_history[room][-500:]
        self._chat_cache_dirty = True

        # During post-login history replay, don't write JSON or rebuild hundreds
        # of Qt widgets once per packet. READY performs the single final update.
        if self.loading_history:
            return

        self._save_chat_cache()
        self._chat_cache_dirty = False
        if room == self.current_target:
            self.reload_current_chat_view()

    def send_message(self):
        text = self.message_entry.text().strip()
        if not text or not self.authenticated:
            return
        room = self.current_target
        self.store_message(room, self.username, text, local=True)
        self.message_entry.clear()
        if room in self.server_channels:
            if room == "general-chat":
                self._network_send(f"GLOBAL:{text}")
            else:
                self._network_send(f"CHANNEL:{room}:{text}")
        else:
            self._network_send(f"DM:{room}:{text}")

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
        layout.setSpacing(7)

        avatar = QLabel()
        avatar.setFixedSize(30, 30)
        avatar.setAlignment(Qt.AlignCenter)
        avatar_img = self.user_pfps.get(user, Image.new("RGB", (40, 40), "#0F3D0F"))
        avatar.setPixmap(self.pil_to_pixmap(avatar_img, (30, 30)))
        layout.addWidget(avatar)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        name = QLabel(("🔊 " if voice else "") + user + ("  [YOU]" if user == self.username else ""))
        name.setProperty("role", "memberName")
        text_col.addWidget(name)
        if status:
            status_label = QLabel(status)
            status_label.setProperty("role", "muted")
            status_label.setWordWrap(True)
            text_col.addWidget(status_label)
        else:
            online_label = QLabel("ONLINE" if online else "OFFLINE")
            online_label.setProperty("role", "muted")
            text_col.addWidget(online_label)
        layout.addLayout(text_col, 1)

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
        for user in self.voice_users:
            widget = self._make_member_widget(user, online=True, voice=True)
            self._add_widget_item(self.voice_user_list, widget, 44)
        self._refresh_voice_user_settings()

    def reload_current_chat_view(self):
        # Cancel any older incremental render. Rebuilding 500 Qt widgets in one
        # callback makes the window feel frozen, especially immediately after login.
        self._render_generation += 1
        generation = self._render_generation

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
            return

        self._render_messages = messages
        self._render_index = 0
        self._render_messages_in_batches(generation)

    def _render_messages_in_batches(self, generation, batch_size=35):
        if generation != self._render_generation:
            return

        messages = getattr(self, "_render_messages", [])
        start = getattr(self, "_render_index", 0)
        if start >= len(messages):
            self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            )
            return

        c = self.palette_colors()
        end = min(start + batch_size, len(messages))
        for msg in messages[start:end]:
            sender = msg.get("sender", "?")
            text = msg.get("text", "")
            edited = "  [edited]" if msg.get("edited") else ""

            card = QFrame(objectName="messageCard")
            layout = QHBoxLayout(card)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(8)

            avatar = QLabel()
            avatar.setFixedSize(36, 36)
            avatar.setAlignment(Qt.AlignCenter)
            avatar_img = self.user_pfps.get(
                sender, Image.new("RGB", (40, 40), "#0F3D0F")
            )
            avatar.setPixmap(self.pil_to_pixmap(avatar_img, (36, 36)))
            layout.addWidget(avatar, alignment=Qt.AlignTop)

            body = QVBoxLayout()
            body.setSpacing(1)
            name = QLabel(sender + edited)
            name.setStyleSheet(
                f"color:{c['bright']}; font-family:Consolas; font-size:12px; font-weight:700;"
            )
            body.addWidget(name)

            msg_label = QLabel(text)
            msg_label.setWordWrap(True)
            msg_label.setStyleSheet(
                f"color:{c['dim']}; font-family:Consolas; font-size:13px;"
            )
            body.addWidget(msg_label)
            layout.addLayout(body, 1)
            self.chat_content_layout.addWidget(card)

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

    # ---------- Voice 2.0 ----------

    def _voice_rate(self):
        return {"Low": 12000, "Balanced": 16000, "High": 24000, "Ultra": 32000}.get(self.voice_quality, VOICE_RATE_DEFAULT)

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
                latency="low",
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
            self.in_voice_chat = True
            self.voice_button.setText("🎤 Leave Voice")
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
                network_rate = self._voice_rate()
                network_data = resample_pcm16_mono(pcm, self.voice_input_rate, network_rate)
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
                gain = self.voice_volume * float(self.voice_user_volumes.get(sender, 1.0))
                playback = resample_pcm16_mono(data, sender_rate, self.voice_output_rate)
                playback = self._apply_voice_gain(playback, gain)
                self.voice_output_stream.write(playback)
                self.voice_activity[sender] = now
                if self.voice_record_wave:
                    self.voice_record_wave.writeframes(playback)
            except Exception as exc:
                if self.in_voice_chat:
                    QTimer.singleShot(0, lambda e=str(exc): self.show_error(f"Voice playback stopped:\n{type(exc).__name__}: {e}"))
                    self.in_voice_chat = False
                break

    def toggle_voice_mute(self):
        self.voice_muted = not self.voice_muted
        self.voice_mute_button.setText("🎤 Unmute Mic" if self.voice_muted else "🔇 Mute Mic")

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
        self.voice_button.setText("🎤 Join Voice")
        self.chat_status_label.setText("connected" if self.authenticated else "offline")

    def _update_voice_stats(self):
        if self.in_voice_chat:
            self.voice_stats_label.setText(
                f"packets {self.voice_packet_count}  bytes {self.voice_bytes_received}  jitter {self.voice_jitter_ms:.1f}ms"
            )
        elif hasattr(self, "voice_stats_label"):
            self.voice_stats_label.setText("voice offline")

    # ---------- misc ----------

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
