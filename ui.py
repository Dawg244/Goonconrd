import socket
import threading
import os
import sys
import io
import math
import struct
import wave
import tempfile
import subprocess
import base64
import json
import re
import queue
import time
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image
from dotenv import load_dotenv, set_key

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR = BASE_DIR
try:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    _test_settings_path = os.path.join(CONFIG_DIR, ".netra_write_test")
    with open(_test_settings_path, "a", encoding="utf-8"):
        pass
    os.remove(_test_settings_path)
except Exception:
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "NETRA")
    os.makedirs(CONFIG_DIR, exist_ok=True)

ENV_FILE = os.path.join(CONFIG_DIR, ".env")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
load_dotenv(ENV_FILE, override=True)

DEFAULT_HOST = '108.221.36.120'
PORT = 12155
VOICE_PORT = 12156
MAIN_PORT = 12145

VOICE_CHUNK = 1024
VOICE_RATE = 16000
VOICE_CHANNELS = 1

ctk.set_appearance_mode("Dark")

# ---------------- Retro terminal theme ----------------
FONT_MONO = "Consolas"
BG_ROOT = "#050A05"
BG_RAIL = "#020402"
BG_PANEL = "#0A140A"
BG_PANEL_ALT = "#0E1C0E"
BG_INPUT = "#0C1A0C"
FG_BRIGHT = "#33FF33"
FG_DIM = "#1E8C1E"
FG_FAINT = "#145214"
BORDER_GREEN = "#123312"
BTN_BG = "#0F1F0F"
BTN_HOVER = "#1B3D1B"
BTN_ACTIVE_BG = "#33FF33"
BTN_ACTIVE_HOVER = "#29CC29"
ERROR_RED = "#FF5555"


def resample_pcm16_mono(data, src_rate, dst_rate):
    """Linear-resample signed 16-bit mono PCM between device/network rates."""
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
        value = max(-32768, min(32767, value))
        struct.pack_into("<h", out, i * 2, value)
    return bytes(out)


def generate_ping_wav(style="ping"):
    """Generate a pleasant multi-note notification sound and cache it safely."""
    # Short two/three-note chimes instead of single-frequency beeps.
    melodies = {
        "ping":  [(659.25, 0.00, 0.11), (783.99, 0.09, 0.16), (1046.50, 0.18, 0.20)],
        "ping_2": [(523.25, 0.00, 0.12), (659.25, 0.10, 0.15), (783.99, 0.20, 0.19)],
        "ping_3": [(783.99, 0.00, 0.10), (987.77, 0.08, 0.13), (1174.66, 0.16, 0.18)],
        "ping_4": [(392.00, 0.00, 0.13), (523.25, 0.11, 0.16), (659.25, 0.22, 0.21)],
        "ping_5": [(587.33, 0.00, 0.10), (739.99, 0.08, 0.13), (880.00, 0.16, 0.18)],
    }
    melody = melodies.get(style, melodies["ping"])
    path = os.path.join(tempfile.gettempdir(), f"netra_{style}_v2.wav")
    if os.path.exists(path):
        return path

    framerate = 44100
    tail = 0.18
    total_duration = max(start + duration for _, start, duration in melody) + tail
    n_samples = int(framerate * total_duration)
    frames = bytearray()

    for i in range(n_samples):
        t = i / framerate
        sample = 0.0
        for freq, start_time, duration in melody:
            local = t - start_time
            if 0.0 <= local < duration:
                # Smooth attack/release to avoid clicks.
                attack = min(1.0, local / 0.018)
                release = min(1.0, (duration - local) / 0.055)
                env = attack * release
                # Fundamental + quiet upper harmonics makes it less harsh/monotone.
                sample += env * (
                    0.78 * math.sin(2 * math.pi * freq * local)
                    + 0.16 * math.sin(2 * math.pi * freq * 2 * local)
                    + 0.06 * math.sin(2 * math.pi * freq * 3 * local)
                )

        sample *= 0.22
        sample = max(-1.0, min(1.0, sample))
        frames += struct.pack("<h", int(32767 * sample))

    try:
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)
            wf.writeframes(bytes(frames))
    except Exception:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
        raise
    return path


THEMES = {
    "NETRA Terminal": {
        "root": "#050A05", "rail": "#020402", "panel": "#0A140A",
        "panel_alt": "#0E1C0E", "input": "#0C1A0C", "bright": "#33FF33",
        "dim": "#1E8C1E", "faint": "#145214", "border": "#123312",
        "button": "#0F1F0F", "hover": "#1B3D1B", "active": "#33FF33",
        "active_hover": "#29CC29", "error": "#FF5555", "appearance": "Dark"
    },
    "Midnight": {
        "root": "#080B14", "rail": "#050711", "panel": "#0D1220",
        "panel_alt": "#12192A", "input": "#101729", "bright": "#62B0FF",
        "dim": "#3B78B5", "faint": "#29435F", "border": "#1E3550",
        "button": "#121D30", "hover": "#1B3150", "active": "#62B0FF",
        "active_hover": "#3D8FE0", "error": "#FF667A", "appearance": "Dark"
    },
    "Light": {
        "root": "#E9EDF2", "rail": "#D7DDE5", "panel": "#F6F8FA",
        "panel_alt": "#E1E6ED", "input": "#FFFFFF", "bright": "#146CDA",
        "dim": "#3D6F9F", "faint": "#718096", "border": "#B8C2CF",
        "button": "#DCE4ED", "hover": "#C9D8E8", "active": "#146CDA",
        "active_hover": "#0F5BB9", "error": "#C62828", "appearance": "Light"
    },
    "CRT Amber": {
        "root": "#090704", "rail": "#050402", "panel": "#151008",
        "panel_alt": "#1C150B", "input": "#120D06", "bright": "#FFB000",
        "dim": "#A87300", "faint": "#664900", "border": "#4A3400",
        "button": "#1B1408", "hover": "#332308", "active": "#FFB000",
        "active_hover": "#D99300", "error": "#FF5F56", "appearance": "Dark"
    },
    "Violet": {
        "root": "#0B0710", "rail": "#06040A", "panel": "#140D1C",
        "panel_alt": "#1D1328", "input": "#160E20", "bright": "#D18BFF",
        "dim": "#8D5BB0", "faint": "#593A70", "border": "#412852",
        "button": "#1B1025", "hover": "#302044", "active": "#D18BFF",
        "active_hover": "#A962D5", "error": "#FF668F", "appearance": "Dark"
    },
}


def load_persistent_settings():
    defaults = {
        "dm_sound_mode": "ping",
        "dm_sound_path": "",
        "voice_input_device": None,
        "voice_output_device": None,
        "theme": "NETRA Terminal",
    }
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                defaults.update({k: data[k] for k in defaults if k in data})
    except Exception:
        pass

    # Older NETRA builds could save the device NAME.  A name is not
    # necessarily unique (e.g. the same webcam can appear as DirectSound,
    # WASAPI, and WDM-KS), so convert old names to an exact device ID.
    if SOUNDDEVICE_AVAILABLE:
        try:
            devices = sd.query_devices()

            def migrate_device(value, want_input):
                if value is None or value == "" or value == "Default":
                    return None
                if isinstance(value, int):
                    return value
                if isinstance(value, str):
                    m = re.match(r"^\s*\[(\d+)\]", value)
                    if m:
                        return int(m.group(1))
                    matches = []
                    for idx, dev in enumerate(devices):
                        name = str(dev.get("name", "")).strip()
                        channels = int(dev.get(
                            "max_input_channels" if want_input else "max_output_channels", 0
                        ))
                        if channels > 0 and name == value:
                            matches.append(idx)
                    # If an old name maps to several host-api entries,
                    # use the first valid exact match rather than passing
                    # the ambiguous string to sounddevice.
                    return matches[0] if matches else None
                return None

            defaults["voice_input_device"] = migrate_device(
                defaults["voice_input_device"], True
            )
            defaults["voice_output_device"] = migrate_device(
                defaults["voice_output_device"], False
            )
        except Exception:
            defaults["voice_input_device"] = None
            defaults["voice_output_device"] = None

    return defaults


def save_persistent_settings(data):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    # Verify the file we just wrote can immediately be read back.
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        saved = json.load(f)
    if saved != data:
        raise IOError("NETRA settings verification failed")


class FullDiscordClone(ctk.CTk):
    def __init__(self):
        super().__init__()

        saved = load_persistent_settings()
        self.theme_name = saved.get("theme", "NETRA Terminal") if saved.get("theme") in THEMES else "NETRA Terminal"
        self._apply_theme_palette(self.theme_name, update_widgets=False)

        self.title("NETRA // TERMINAL")
        self.geometry("1000x600")
        self.resizable(False, False)
        self.configure(fg_color=BG_ROOT)

        self.client_socket = None
        self.server_host = os.getenv("NETRA_SERVER_IP", DEFAULT_HOST)
        self.server_port = PORT
        self.voice_port = VOICE_PORT
        if ":" in self.server_host and self.server_host.count(":") == 1:
            _h,_p=self.server_host.rsplit(":",1)
            if _p.isdigit(): self.server_host,self.server_port=_h,int(_p)
        self.account_id = os.getenv("NETRA_ACCOUNT_ID", "")
        self.authenticated = False
        self.auth_window = None
        self.auth_waiting = True
        self.current_target = "general-chat"
        self.chat_history = {"general-chat": [], "random": []}
        self.all_rendered_widgets = []
        self.chat_room_frames = {}
        self.chat_room_built = set()
        self.dm_list_buttons = {}
        self.last_dm_partners = None
        self.last_user_list = []
        self.last_registered_user_list = []
        self.online_user_set = set()
        self._incoming_queue = queue.Queue()
        self.last_server_message_time = 0.0
        self.last_voice_user_list = []
        self.sidebar_mode = "server"  # "server" or "dms"
        self.server_channels = ["general-chat", "random"]
        self.unread_counts = {}
        self.presence_status = {}
        self.custom_status = {}
        self.typing_users = {}
        self.reactions = {}
        self.pinned_messages = {}
        self.message_ids = {}
        self.draft_messages = {}
        self.favorites = set()
        self.blocked_users = set()

        # username -> PIL.Image, so we can regenerate CTkImages at any size
        self.default_pil_pfp = Image.new('RGB', (40, 40), color='#0F3D0F')
        self.user_pil_pfps = {}

        # Shared "server" icon (like a Discord server icon)
        self.server_pil_icon = None
        self.server_default_text = "🏠"

        # Voice chat state
        self.in_voice_chat = False
        self.voice_socket = None
        self.voice_input_stream = None
        self.voice_output_stream = None
        self.voice_device_input = None
        self.voice_device_output = None
        self.voice_muted = False
        self.dm_sound_mode = saved["dm_sound_mode"]
        self.dm_sound_path = saved["dm_sound_path"]
        self.voice_device_input = saved["voice_input_device"]
        self.voice_device_output = saved["voice_output_device"]
        self.loading_history = True
        self._history_ready = False

        # ---------------- Server Navigation Rail ----------------
        self.server_rail = ctk.CTkFrame(self, width=70, corner_radius=0, fg_color=BG_RAIL)
        self.server_rail.pack(side="left", fill="y")

        self.server_btn = ctk.CTkButton(self.server_rail, text=self.server_default_text, width=48, height=48, corner_radius=0, fg_color=FG_DIM, hover_color=BTN_HOVER, text_color="black", font=(FONT_MONO, 16, "bold"), command=self.go_to_server_view)
        self.server_btn.pack(pady=(12, 4))
        self.server_btn.bind("<Double-Button-1>", lambda e: self.upload_server_icon())
        self.load_saved_server_icon()

        self.dm_rail_btn = ctk.CTkButton(self.server_rail, text="💬", width=48, height=40, corner_radius=0, fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 16), command=self.show_dm_view)
        self.dm_rail_btn.pack(pady=4)

        # ---------------- Left Channels / DM Sidebar ----------------
        self.channel_sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=BG_PANEL)
        self.channel_sidebar.pack(side="left", fill="y")

        self.server_title = ctk.CTkLabel(self.channel_sidebar, text="NETRA // SERVER", font=(FONT_MONO, 14, "bold"), text_color=FG_BRIGHT)
        self.server_title.pack(pady=(15, 5), padx=15, anchor="w")
        self.server_ip_small = ctk.CTkLabel(self.channel_sidebar, text=f"{self.server_host}:{self.server_port}", font=(FONT_MONO, 9), text_color=FG_FAINT)
        self.server_ip_small.pack(pady=(0, 10), padx=15, anchor="w")

        self.sidebar_body = ctk.CTkFrame(self.channel_sidebar, fg_color="transparent", corner_radius=0)
        self.sidebar_body.pack(fill="both", expand=True)

        self.channel_btn = ctk.CTkButton(self.sidebar_body, text="# general-chat", font=(FONT_MONO, 12, "bold"), fg_color=BTN_HOVER, hover_color=BTN_HOVER, text_color=FG_BRIGHT, height=32, corner_radius=0, command=lambda: self.select_channel("general-chat"))
        self.channel_btn.pack(fill="x", padx=8, pady=(4, 2))
        self.random_channel_btn = ctk.CTkButton(self.sidebar_body, text="# random", font=(FONT_MONO, 12, "bold"), fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, height=32, corner_radius=0, command=lambda: self.select_channel("random"))
        self.random_channel_btn.pack(fill="x", padx=8, pady=2)
        self.feature_btn = ctk.CTkButton(self.sidebar_body, text="✨ NETRA HUB", font=(FONT_MONO, 11, "bold"), fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, height=30, corner_radius=0, command=self.open_netra_hub)
        self.feature_btn.pack(fill="x", padx=8, pady=(8,2))
        self.voice_btn = ctk.CTkButton(self.sidebar_body, text="🎤 Join Voice", font=(FONT_MONO, 12, "bold"), fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, height=32, corner_radius=0, command=self.toggle_voice_chat)
        self.voice_mute_btn = ctk.CTkButton(self.sidebar_body, text="🔇 Mute Mic", font=(FONT_MONO, 11, "bold"), fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, height=28, corner_radius=0, command=self.toggle_voice_mute)
        self.dm_list_frame = ctk.CTkFrame(self.sidebar_body, fg_color="transparent", corner_radius=0)

        # Profile Picture & Username Panel
        self.user_section = ctk.CTkFrame(self.channel_sidebar, fg_color=BG_PANEL_ALT, height=130, corner_radius=0)
        self.user_section.pack(side="bottom", fill="x")

        self.pfp_label = ctk.CTkLabel(self.user_section, text="", width=40, height=40)
        self.pfp_label.pack(pady=(12, 2))

        self.load_saved_profile()

        self.pfp_btn = ctk.CTkButton(self.user_section, text="Upload PFP", font=(FONT_MONO, 10), fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, height=20, width=90, corner_radius=0, command=self.upload_pfp)
        self.pfp_btn.pack(pady=(0, 8))

        saved_user = os.getenv("CHAT_USERNAME", "User")
        self.username_entry = ctk.CTkEntry(self.user_section, width=140, height=28, corner_radius=0, fg_color=BG_INPUT, border_color=BORDER_GREEN, text_color=FG_BRIGHT, font=(FONT_MONO, 11, "bold"), justify="center")
        self.username_entry.insert(0, saved_user)
        self.username_entry.pack(pady=(0, 12), padx=15)
        self.username_entry.configure(state="disabled")

        self.settings_btn = ctk.CTkButton(
            self.user_section, text="⚙ SETTINGS", font=(FONT_MONO, 10, "bold"),
            fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT,
            height=24, width=120, corner_radius=0, command=self.open_settings
        )
        self.settings_btn.pack(pady=(0, 4))

        self.rename_btn = ctk.CTkButton(
            self.user_section, text="CHANGE USERNAME", font=(FONT_MONO, 9, "bold"),
            fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT,
            height=22, width=120, corner_radius=0, command=self.rename_username
        )
        self.rename_btn.pack(pady=(0, 8))

        # ---------------- Right Active User Panel ----------------
        self.member_sidebar = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color=BG_PANEL)
        self.member_sidebar.pack(side="right", fill="y")

        self.voice_header = ctk.CTkLabel(self.member_sidebar, text="IN VOICE 🔊", font=(FONT_MONO, 10, "bold"), text_color=FG_DIM)
        self.voice_header.pack(padx=15, pady=(15, 5), anchor="w")

        self.voice_user_frame = ctk.CTkFrame(self.member_sidebar, fg_color="transparent")
        self.voice_user_frame.pack(fill="x")
        self.update_voice_users_ui([])

        self.member_header = ctk.CTkLabel(self.member_sidebar, text="MEMBERS", font=(FONT_MONO, 10, "bold"), text_color=FG_DIM)
        self.member_header.pack(padx=15, pady=(15, 5), anchor="w")

        self.member_search_var = ctk.StringVar(value="")
        self.member_search = ctk.CTkEntry(self.member_sidebar, textvariable=self.member_search_var, placeholder_text="Find a member...", height=28, corner_radius=0, fg_color=BG_INPUT, border_color=BORDER_GREEN, text_color=FG_BRIGHT, placeholder_text_color=FG_FAINT, font=(FONT_MONO, 9))
        self.member_search.pack(fill="x", padx=10, pady=(0, 6))
        self.member_search_var.trace_add("write", lambda *_: self.update_online_users_ui(self.last_registered_user_list, force=True))

        self.user_list_frame = ctk.CTkScrollableFrame(self.member_sidebar, fg_color="transparent", corner_radius=0)
        self.user_list_frame.pack(fill="both", expand=True)

        # ---------------- Central Message Arena ----------------
        self.main_chat_area = ctk.CTkFrame(self, fg_color=BG_ROOT, corner_radius=0)
        self.main_chat_area.pack(side="right", fill="both", expand=True)

        # ---------------- Server connection bar ----------------
        self.server_bar = ctk.CTkFrame(self.main_chat_area, fg_color=BG_PANEL, corner_radius=0, height=48)
        self.server_bar.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(self.server_bar, text="SERVER", font=(FONT_MONO, 10, "bold"), text_color=FG_DIM).pack(side="left", padx=(10, 6))
        self.server_ip_entry = ctk.CTkEntry(self.server_bar, width=230, height=30, corner_radius=0, fg_color=BG_INPUT, border_color=BORDER_GREEN, text_color=FG_BRIGHT, font=(FONT_MONO, 11))
        self.server_ip_entry.insert(0, self.server_host)
        self.server_ip_entry.pack(side="left", padx=4)
        self.server_ip_entry.bind("<Return>", lambda event: self.connect_to_server_from_bar())
        self.server_connect_btn = ctk.CTkButton(self.server_bar, text="CONNECT", width=90, height=30, corner_radius=0, fg_color=FG_DIM, hover_color=BTN_ACTIVE_HOVER, text_color="black", font=(FONT_MONO, 10, "bold"), command=self.connect_to_server_from_bar)
        self.server_connect_btn.pack(side="left", padx=6)
        self.search_btn = ctk.CTkButton(self.server_bar, text="SEARCH", width=80, height=30, corner_radius=0, fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 9, "bold"), command=self.open_search)
        self.search_btn.pack(side="left", padx=2)
        self.browser_btn = ctk.CTkButton(self.server_bar, text="SERVERS", width=80, height=30, corner_radius=0, fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 9, "bold"), command=self.open_server_browser)
        self.browser_btn.pack(side="left", padx=2)
        self.server_status_label = ctk.CTkLabel(self.server_bar, text="offline", font=(FONT_MONO, 9), text_color=FG_FAINT)
        self.server_status_label.pack(side="right", padx=10)

        # decorative retro divider
        self.scanline_deco = ctk.CTkLabel(self.main_chat_area, text="·" * 160, font=(FONT_MONO, 8), text_color=BORDER_GREEN, anchor="w")
        self.scanline_deco.pack(fill="x", padx=10, pady=(4, 0))

        self.chat_scroll = ctk.CTkScrollableFrame(self.main_chat_area, fg_color=BG_ROOT, corner_radius=0, label_text="")
        self.chat_scroll.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.input_container = ctk.CTkFrame(self.main_chat_area, fg_color=BG_ROOT, height=60, corner_radius=0)
        self.input_container.pack(fill="x", side="bottom", padx=20, pady=(0, 20))

        self.message_entry = ctk.CTkEntry(self.input_container, placeholder_text=f"Message #{self.current_target}", height=44, corner_radius=0, fg_color=BG_INPUT, border_color=BORDER_GREEN, text_color=FG_BRIGHT, placeholder_text_color=FG_FAINT, font=(FONT_MONO, 13))
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.message_entry.bind("<Return>", lambda event: self.send_message())
        self.message_entry.bind("<KeyRelease>", lambda event: self.send_typing_indicator())

        self.send_button = ctk.CTkButton(self.input_container, text="SEND", width=80, height=44, corner_radius=0, fg_color=FG_DIM, hover_color=BTN_ACTIVE_HOVER, text_color="black", font=(FONT_MONO, 13, "bold"), command=self.send_message)
        self.send_button.pack(side="right")

        self.show_server_view()

        self.after(20, self._pump_incoming_messages)
        self.after(250, self.open_auth_window)
        self.bind("<Control-f>", lambda _e: self.open_search())
        self.bind("<Control-k>", lambda _e: self.member_search.focus_set())
        self.bind("<Escape>", lambda _e: self.message_entry.focus_set())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def select_channel(self, channel):
        if channel not in self.server_channels:
            return
        self._save_current_draft()
        self.sidebar_mode = "server"
        self.current_target = channel
        self.unread_counts[channel]=0
        self.server_title.configure(text="NETRA // SERVER")
        self.channel_btn.configure(fg_color=BTN_HOVER if channel == "general-chat" else BTN_BG)
        self.random_channel_btn.configure(fg_color=BTN_HOVER if channel == "random" else BTN_BG)
        self.show_chat_room(channel)
        self.update_input_placeholder()
        self._restore_current_draft()
        self._refresh_unread_badges()

    def connect_to_server_from_bar(self):
        host = self.server_ip_entry.get().strip()
        if not host:
            return
        server_port = PORT
        if ":" in host and host.count(":") == 1:
            raw_host, raw_port = host.rsplit(":", 1)
            if raw_port.isdigit():
                host, server_port = raw_host.strip(), int(raw_port)
        self.server_host = host
        self.server_port = server_port
        self.voice_port = server_port + 1
        set_key(ENV_FILE, "NETRA_SERVER_IP", f"{host}:{server_port}")
        self.server_ip_small.configure(text=f"{host}:{server_port}")
        self.server_status_label.configure(text="connecting...", text_color=FG_DIM)
        self.authenticated = False
        self.open_auth_window()

    # ---------- Sidebar navigation (server channels <-> DMs) ----------

    def go_to_server_view(self):
        self.show_server_view()
        self.select_channel("general-chat")

    def show_server_view(self):
        self.sidebar_mode = "server"
        self.server_title.configure(text="NETRA // SERVER")
        self.dm_list_frame.pack_forget()
        self.channel_btn.pack(fill="x", padx=10, pady=(4, 2))
        self.random_channel_btn.pack(fill="x", padx=10, pady=2)
        self.voice_btn.pack(fill="x", padx=10, pady=(0, 2))
        self.voice_mute_btn.pack(fill="x", padx=10, pady=(0, 5))

    def show_dm_view(self):
        self.sidebar_mode = "dms"
        self.server_title.configure(text="Direct Messages")
        self.channel_btn.pack_forget()
        self.random_channel_btn.pack_forget()
        self.voice_btn.pack_forget()
        self.voice_mute_btn.pack_forget()
        self.dm_list_frame.pack(fill="both", expand=True)

        if self.current_target in self.server_channels:
            candidates = sorted(set(self.chat_history.keys()) - set(self.server_channels))
            if candidates:
                self.current_target = candidates[0]
                self.message_entry.configure(placeholder_text=f"Message @{self.current_target}")

        self.refresh_dm_list()
        self.show_chat_room(self.current_target)

    def refresh_dm_list(self):
        my_name = self.username_entry.get().strip()
        partners = set(self.chat_history.keys()) - set(self.server_channels)
        partners |= set(u for u in self.last_user_list if u != my_name)
        partners.discard(my_name)
        partners_tuple = tuple(sorted(partners, key=str.lower))

        # Don't destroy/recreate the entire DM sidebar every time a message or
        # presence update arrives. That was causing visible lag and occasional
        # blank DMs while Tk rebuilt the widgets.
        if partners_tuple == self.last_dm_partners:
            for user, btn in self.dm_list_buttons.items():
                btn.configure(fg_color=(BTN_HOVER if user == self.current_target else "transparent"))
            return

        self.last_dm_partners = partners_tuple
        for widget in self.dm_list_frame.winfo_children():
            widget.destroy()
        self.dm_list_buttons.clear()

        if not partners_tuple:
            lbl = ctk.CTkLabel(self.dm_list_frame, text="No conversations yet.\nClick a name on the right\nto start one.", font=(FONT_MONO, 11), text_color=FG_FAINT, justify="left")
            lbl.pack(anchor="w", padx=10, pady=10)
            return

        for user in partners_tuple:
            avatar_img = self.get_avatar_ctkimage(user, size=(24, 24))
            btn = ctk.CTkButton(
                self.dm_list_frame, image=avatar_img, text=f"  {user}" + (f"  [{self.unread_counts.get(user,0)}]" if self.unread_counts.get(user,0) else ""),
                compound="left", font=(FONT_MONO, 12, "bold"),
                corner_radius=0,
                fg_color=(BTN_HOVER if user == self.current_target else "transparent"),
                text_color=FG_BRIGHT, anchor="w", height=32,
                hover_color=BTN_HOVER,
                command=lambda u=user: self.select_dm_channel(u))
            btn.pack(fill="x", padx=10, pady=2)
            self.dm_list_buttons[user] = btn

    # ---------- PFP helpers ----------


    def load_saved_profile(self):
        saved_pfp_path = os.getenv("CHAT_PFP_PATH", "")
        if saved_pfp_path and os.path.exists(saved_pfp_path):
            try:
                self.pil_pfp = Image.open(saved_pfp_path).convert('RGB').resize((40, 40), Image.Resampling.LANCZOS)
            except:
                self.pil_pfp = Image.new('RGB', (40, 40), color='#0F3D0F')
        else:
            self.pil_pfp = Image.new('RGB', (40, 40), color='#0F3D0F')
        self.ctk_pfp = ctk.CTkImage(light_image=self.pil_pfp, dark_image=self.pil_pfp, size=(40, 40))
        self.pfp_label.configure(image=self.ctk_pfp)

    def get_avatar_ctkimage(self, username, size=(40, 40)):
        pil_img = self.user_pil_pfps.get(username, self.default_pil_pfp)
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)

    def send_own_pfp(self):
        if not self.client_socket:
            return
        try:
            buf = io.BytesIO()
            self.pil_pfp.save(buf, format="PNG")
            b64_data = base64.b64encode(buf.getvalue()).decode('ascii')
            self.client_socket.sendall(f"PFP:{b64_data}\n".encode('utf-8'))
        except Exception as e:
            self.append_system_error(f"Failed to send profile picture: {e}")

    def upload_pfp(self):
        file_path = filedialog.askopenfilename(title="Select Profile Picture", filetypes=[("Image Files", "*.png *.jpg *.jpeg")])
        if file_path:
            try:
                self.pil_pfp = Image.open(file_path).convert('RGB').resize((40, 40), Image.Resampling.LANCZOS)
                self.ctk_pfp = ctk.CTkImage(light_image=self.pil_pfp, dark_image=self.pil_pfp, size=(40, 40))
                self.pfp_label.configure(image=self.ctk_pfp)

                my_name = self.username_entry.get().strip()
                if my_name:
                    self.user_pil_pfps[my_name] = self.pil_pfp

                if not os.path.exists(ENV_FILE):
                    open(ENV_FILE, 'w').close()
                set_key(ENV_FILE, "CHAT_PFP_PATH", file_path)

                self.send_own_pfp()
                self.reload_current_chat_view()
                self.update_online_users_ui(self.last_user_list)
                self.update_voice_users_ui(self.last_voice_user_list)
            except Exception as e:
                self.append_system_error(f"Failed to load image: {e}")

    # ---------- Server icon helpers ----------

    def load_saved_server_icon(self):
        saved_path = os.getenv("CHAT_SERVER_ICON_PATH", "")
        if saved_path and os.path.exists(saved_path):
            try:
                self.server_pil_icon = Image.open(saved_path).convert('RGB').resize((48, 48), Image.Resampling.LANCZOS)
            except:
                self.server_pil_icon = None
        self.refresh_server_icon_widget()

    def refresh_server_icon_widget(self):
        if self.server_pil_icon:
            img = ctk.CTkImage(light_image=self.server_pil_icon, dark_image=self.server_pil_icon, size=(48, 48))
            self.server_btn.configure(image=img, text="")
        else:
            self.server_btn.configure(image=None, text=self.server_default_text)

    def upload_server_icon(self):
        file_path = filedialog.askopenfilename(title="Select Server Icon", filetypes=[("Image Files", "*.png *.jpg *.jpeg")])
        if not file_path:
            return
        try:
            self.server_pil_icon = Image.open(file_path).convert('RGB').resize((48, 48), Image.Resampling.LANCZOS)
            self.refresh_server_icon_widget()

            if not os.path.exists(ENV_FILE):
                open(ENV_FILE, 'w').close()
            set_key(ENV_FILE, "CHAT_SERVER_ICON_PATH", file_path)

            self.send_server_icon()
        except Exception as e:
            self.append_system_error(f"Failed to load server icon: {e}")

    def send_server_icon(self):
        if not self.client_socket or not self.server_pil_icon:
            return
        try:
            buf = io.BytesIO()
            self.server_pil_icon.save(buf, format="PNG")
            b64_data = base64.b64encode(buf.getvalue()).decode('ascii')
            self.client_socket.sendall(f"SERVERPFP:{b64_data}\n".encode('utf-8'))
        except Exception as e:
            self.append_system_error(f"Failed to send server icon: {e}")

    def receive_server_icon(self, b64_data):
        try:
            raw_bytes = base64.b64decode(b64_data)
            img = Image.open(io.BytesIO(raw_bytes)).convert('RGB').resize((48, 48), Image.Resampling.LANCZOS)
            self.server_pil_icon = img
            self.refresh_server_icon_widget()
        except Exception:
            pass

    # ---------- Themes ----------

    def _apply_theme_palette(self, theme_name, update_widgets=True):
        global BG_ROOT, BG_RAIL, BG_PANEL, BG_PANEL_ALT, BG_INPUT
        global FG_BRIGHT, FG_DIM, FG_FAINT, BORDER_GREEN, BTN_BG, BTN_HOVER
        global BTN_ACTIVE_BG, BTN_ACTIVE_HOVER, ERROR_RED

        palette = THEMES.get(theme_name, THEMES["NETRA Terminal"])
        old = {
            "root": BG_ROOT, "rail": BG_RAIL, "panel": BG_PANEL, "panel_alt": BG_PANEL_ALT,
            "input": BG_INPUT, "bright": FG_BRIGHT, "dim": FG_DIM, "faint": FG_FAINT,
            "border": BORDER_GREEN, "button": BTN_BG, "hover": BTN_HOVER,
            "active": BTN_ACTIVE_BG, "active_hover": BTN_ACTIVE_HOVER, "error": ERROR_RED,
        }

        BG_ROOT = palette["root"]; BG_RAIL = palette["rail"]; BG_PANEL = palette["panel"]
        BG_PANEL_ALT = palette["panel_alt"]; BG_INPUT = palette["input"]
        FG_BRIGHT = palette["bright"]; FG_DIM = palette["dim"]; FG_FAINT = palette["faint"]
        BORDER_GREEN = palette["border"]; BTN_BG = palette["button"]; BTN_HOVER = palette["hover"]
        BTN_ACTIVE_BG = palette["active"]; BTN_ACTIVE_HOVER = palette["active_hover"]; ERROR_RED = palette["error"]
        ctk.set_appearance_mode(palette.get("appearance", "Dark"))
        self.theme_name = theme_name

        if not update_widgets:
            return

        frame_map = {old["root"]: BG_ROOT, old["rail"]: BG_RAIL, old["panel"]: BG_PANEL,
                     old["panel_alt"]: BG_PANEL_ALT, old["input"]: BG_INPUT}
        text_map = {old["bright"]: FG_BRIGHT, old["dim"]: FG_DIM, old["faint"]: FG_FAINT, old["error"]: ERROR_RED}
        color_map = {**frame_map, old["button"]: BTN_BG, old["hover"]: BTN_HOVER,
                     old["active"]: BTN_ACTIVE_BG, old["active_hover"]: BTN_ACTIVE_HOVER,
                     old["border"]: BORDER_GREEN, **text_map}

        def mapped(value):
            if isinstance(value, tuple):
                return value
            return color_map.get(value, value)

        def update_widget(widget):
            try:
                cls = widget.__class__.__name__
                if cls in ("CTkFrame", "CTkScrollableFrame"):
                    value = widget.cget("fg_color")
                    if value in frame_map:
                        widget.configure(fg_color=frame_map[value])
                elif cls == "CTkButton":
                    fg = widget.cget("fg_color")
                    hover = widget.cget("hover_color")
                    txt = widget.cget("text_color")
                    widget.configure(fg_color=mapped(fg), hover_color=mapped(hover), text_color=mapped(txt))
                elif cls == "CTkLabel":
                    widget.configure(text_color=mapped(widget.cget("text_color")))
                elif cls == "CTkEntry":
                    widget.configure(fg_color=mapped(widget.cget("fg_color")), border_color=mapped(widget.cget("border_color")), text_color=mapped(widget.cget("text_color")))
                elif cls == "CTkOptionMenu":
                    widget.configure(fg_color=mapped(widget.cget("fg_color")), button_color=mapped(widget.cget("button_color")), button_hover_color=mapped(widget.cget("button_hover_color")), text_color=mapped(widget.cget("text_color")))
                elif cls == "CTkCheckBox":
                    widget.configure(fg_color=mapped(widget.cget("fg_color")), hover_color=mapped(widget.cget("hover_color")), text_color=mapped(widget.cget("text_color")))
            except Exception:
                pass
            try:
                for child in widget.winfo_children():
                    update_widget(child)
            except Exception:
                pass

        try:
            for top in self.winfo_toplevel().winfo_children():
                update_widget(top)
            self.configure(fg_color=BG_ROOT)
            for top in self.winfo_toplevel().winfo_children():
                try: top.configure(fg_color=BG_ROOT)
                except Exception: pass
        except Exception:
            pass

    def apply_theme(self, theme_name):
        if theme_name not in THEMES:
            return
        self._apply_theme_palette(theme_name, update_widgets=True)
        self._save_theme_preference()

    def _save_theme_preference(self):
        try:
            data = load_persistent_settings()
            data["theme"] = self.theme_name
            save_persistent_settings(data)
        except Exception:
            pass

    def open_themes(self):
        win = ctk.CTkToplevel(self)
        win.title("NETRA // THEMES")
        win.geometry("520x430")
        win.resizable(False, False)
        win.configure(fg_color=BG_ROOT)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text="NETRA // THEMES", font=(FONT_MONO, 18, "bold"), text_color=FG_BRIGHT).pack(pady=(22, 5))
        ctk.CTkLabel(win, text="Pick a theme and it changes the actual interface immediately.", font=(FONT_MONO, 9), text_color=FG_DIM).pack(pady=(0, 18))

        var = ctk.StringVar(value=self.theme_name)
        menu = ctk.CTkOptionMenu(win, variable=var, values=list(THEMES.keys()), width=320, height=38,
                                 fg_color=BTN_BG, button_color=FG_DIM, button_hover_color=BTN_HOVER,
                                 text_color=FG_BRIGHT, font=(FONT_MONO, 11, "bold"))
        menu.pack(pady=8)

        preview = ctk.CTkFrame(win, fg_color=BG_PANEL, corner_radius=0, width=400, height=120)
        preview.pack(padx=35, pady=15, fill="x")
        preview.pack_propagate(False)
        preview_title = ctk.CTkLabel(preview, text="THEME PREVIEW", font=(FONT_MONO, 12, "bold"), text_color=FG_BRIGHT)
        preview_title.pack(pady=(18, 5))
        preview_text = ctk.CTkLabel(preview, text="Buttons, panels, text, inputs and windows all update.", font=(FONT_MONO, 9), text_color=FG_DIM)
        preview_text.pack()

        def refresh_preview():
            # Preview follows the currently selected palette without changing the app yet.
            pal = THEMES.get(var.get(), THEMES["NETRA Terminal"])
            preview.configure(fg_color=pal["panel"])
            preview_title.configure(text_color=pal["bright"])
            preview_text.configure(text_color=pal["dim"])

        menu.configure(command=lambda _choice: refresh_preview())
        refresh_preview()

        buttons = ctk.CTkFrame(win, fg_color="transparent")
        buttons.pack(pady=10)
        ctk.CTkButton(buttons, text="APPLY THEME", width=180, height=38, corner_radius=0,
                      fg_color=FG_DIM, hover_color=BTN_ACTIVE_HOVER, text_color="black",
                      font=(FONT_MONO, 11, "bold"), command=lambda: (self.apply_theme(var.get()), win.destroy())).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="CANCEL", width=120, height=38, corner_radius=0,
                      fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT,
                      font=(FONT_MONO, 10, "bold"), command=win.destroy).pack(side="left", padx=6)

    # ---------- Sound ----------

    def save_settings_file(self, dm_mode, dm_path, input_device, output_device):
        data = {
            "dm_sound_mode": dm_mode,
            "dm_sound_path": dm_path,
            "voice_input_device": input_device,
            "voice_output_device": output_device,
            "theme": self.theme_name,
        }
        try:
            save_persistent_settings(data)
            self.dm_sound_mode = dm_mode
            self.dm_sound_path = dm_path
            self.voice_device_input = input_device
            self.voice_device_output = output_device
            return True
        except Exception as e:
            self.append_system_error(f"Could not save settings: {e}")
            return False

    def play_ping_sound(self):
        """Play the configured notification sound without blocking the UI."""
        if self.dm_sound_mode == "off":
            return
        try:
            if self.dm_sound_mode == "custom" and self.dm_sound_path and os.path.isfile(self.dm_sound_path):
                path = self.dm_sound_path
            else:
                path = generate_ping_wav(self.dm_sound_mode)

            if os.name == "nt":
                import winsound
                # SND_ASYNC keeps the network/UI thread responsive.
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            elif sys.platform == "darwin":
                subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["aplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            # Do not silently disable notifications if a sound file fails.
            try:
                self.after(0, self.append_system_error, f"Notification sound failed: {e}")
            except Exception:
                pass

    def open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("NETRA // Settings")
        win.geometry("560x570")
        win.resizable(False, False)
        win.configure(fg_color=BG_ROOT)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text="NETRA // SETTINGS", font=(FONT_MONO, 16, "bold"), text_color=FG_BRIGHT).pack(pady=(18, 12))
        ctk.CTkLabel(
            win,
            text=f"Saved automatically to: {SETTINGS_FILE}",
            font=(FONT_MONO, 8),
            text_color=FG_FAINT,
        ).pack(pady=(0, 8))

        sound_frame = ctk.CTkFrame(win, fg_color=BG_PANEL, corner_radius=0)
        sound_frame.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(sound_frame, text="DM NOTIFICATIONS", font=(FONT_MONO, 11, "bold"), text_color=FG_BRIGHT).pack(anchor="w", padx=12, pady=(10, 5))
        sound_var = ctk.StringVar(value=self.dm_sound_mode)
        sound_menu = ctk.CTkOptionMenu(sound_frame, variable=sound_var, values=["ping", "ping_2", "ping_3", "ping_4", "ping_5", "custom", "off"], width=220, fg_color=BTN_BG, button_color=FG_DIM, button_hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 10))
        sound_menu.pack(anchor="w", padx=12, pady=(0, 8))
        sound_path_label = ctk.CTkLabel(sound_frame, text=self.dm_sound_path or "Built-in notification", font=(FONT_MONO, 9), text_color=FG_FAINT)
        sound_path_label.pack(anchor="w", padx=12, pady=(0, 6))

        def choose_sound():
            path = filedialog.askopenfilename(title="Choose DM notification sound", filetypes=[("WAV audio", "*.wav"), ("Audio files", "*.wav *.mp3 *.ogg"), ("All files", "*.*")])
            if path:
                sound_var.set("custom")
                self.dm_sound_path = path
                sound_path_label.configure(text=path)

        ctk.CTkButton(sound_frame, text="CHOOSE CUSTOM WAV", command=choose_sound, width=170, height=28, corner_radius=0, fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 10, "bold")).pack(anchor="w", padx=12, pady=(0, 5))

        def test_sound():
            old_mode, old_path = self.dm_sound_mode, self.dm_sound_path
            self.dm_sound_mode = sound_var.get()
            if self.dm_sound_mode == "custom":
                self.dm_sound_path = self.dm_sound_path
            self.play_ping_sound()
            self.dm_sound_mode, self.dm_sound_path = old_mode, old_path

        ctk.CTkButton(sound_frame, text="🔊 TEST SOUND", command=test_sound, width=140, height=26, corner_radius=0, fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 9, "bold")).pack(anchor="w", padx=12, pady=(0, 10))

        voice_frame = ctk.CTkFrame(win, fg_color=BG_PANEL, corner_radius=0)
        voice_frame.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(voice_frame, text="VOICE DEVICES", font=(FONT_MONO, 11, "bold"), text_color=FG_BRIGHT).pack(anchor="w", padx=12, pady=(10, 6))
        input_names, output_names = self.get_audio_device_names()
        input_values = ["Default"] + input_names
        output_values = ["Default"] + output_names
        input_current = self.audio_index_to_selection(self.voice_device_input, input_values)
        output_current = self.audio_index_to_selection(self.voice_device_output, output_values)
        input_var = ctk.StringVar(value=input_current)
        output_var = ctk.StringVar(value=output_current)
        ctk.CTkLabel(voice_frame, text="Microphone", font=(FONT_MONO, 9), text_color=FG_DIM).pack(anchor="w", padx=12)
        ctk.CTkOptionMenu(voice_frame, variable=input_var, values=input_values, width=480, fg_color=BTN_BG, button_color=FG_DIM, button_hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 9)).pack(padx=12, pady=(2, 7))
        ctk.CTkLabel(voice_frame, text="Output / speakers", font=(FONT_MONO, 9), text_color=FG_DIM).pack(anchor="w", padx=12)
        ctk.CTkOptionMenu(voice_frame, variable=output_var, values=output_values, width=480, fg_color=BTN_BG, button_color=FG_DIM, button_hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 9)).pack(padx=12, pady=(2, 10))

        status = ctk.CTkLabel(win, text="Changes are not permanent until SAVE SETTINGS is pressed.", font=(FONT_MONO, 9), text_color=FG_DIM)
        status.pack(pady=(3, 5))

        def save_and_close():
            mode = sound_var.get()
            inp = self.audio_selection_to_index(input_var.get())
            out = self.audio_selection_to_index(output_var.get())
            path = self.dm_sound_path if mode == "custom" else self.dm_sound_path
            if self.save_settings_file(mode, path, inp, out):
                status.configure(text=f"✓ SAVED: {SETTINGS_FILE}", text_color=FG_BRIGHT)
                win.after(350, win.destroy)

        def reset_defaults():
            sound_var.set("ping")
            input_var.set("Default")
            output_var.set("Default")
            self.dm_sound_path = ""
            sound_path_label.configure(text="Built-in notification")
            status.configure(text="Defaults selected — press SAVE SETTINGS", text_color=FG_DIM)

        buttons = ctk.CTkFrame(win, fg_color="transparent")
        buttons.pack(pady=8)
        ctk.CTkButton(buttons, text="SAVE SETTINGS", command=save_and_close, width=170, height=38, corner_radius=0, fg_color=FG_DIM, hover_color=BTN_ACTIVE_HOVER, text_color="black", font=(FONT_MONO, 11, "bold")).pack(side="left", padx=6)
        ctk.CTkButton(buttons, text="RESET DEFAULTS", command=reset_defaults, width=150, height=38, corner_radius=0, fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 10, "bold")).pack(side="left", padx=6)
    def get_audio_device_names(self):
        if not SOUNDDEVICE_AVAILABLE:
            return [], []
        try:
            devices = sd.query_devices()
            inputs = []
            outputs = []
            for idx, d in enumerate(devices):
                name = str(d.get("name", "")).strip()
                if not name:
                    continue
                label = f"[{idx}] {name}"
                if int(d.get("max_input_channels", 0)) > 0:
                    inputs.append(label)
                if int(d.get("max_output_channels", 0)) > 0:
                    outputs.append(label)
            return inputs, outputs
        except Exception:
            return [], []

    @staticmethod
    def audio_selection_to_index(value):
        if not value or value == "Default":
            return None
        try:
            if value.startswith("[") and "]" in value:
                return int(value[1:value.index("]")])
            # Migrate old settings that stored the raw device name.
            if SOUNDDEVICE_AVAILABLE:
                for idx, d in enumerate(sd.query_devices()):
                    if str(d.get("name", "")).strip() == value:
                        return idx
        except Exception:
            pass
        return None

    def audio_index_to_selection(self, value, values):
        if value is None:
            return "Default"
        try:
            idx = int(value)
            prefix = f"[{idx}] "
            for item in values:
                if item.startswith(prefix):
                    return item
        except Exception:
            pass
        if isinstance(value, str):
            for item in values:
                if item == value or item.endswith(" " + value):
                    return item
        return "Default"

    # ---------- Networking ----------

    def open_auth_window(self):
        if self.auth_window is not None and self.auth_window.winfo_exists():
            self.auth_window.focus_force()
            return
        win = ctk.CTkToplevel(self)
        self.auth_window = win
        win.title("NETRA // Account")
        win.geometry("430x520")
        win.resizable(False, False)
        win.configure(fg_color=BG_PANEL)
        win.transient(self)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", self.on_close)

        ctk.CTkLabel(win, text="NETRA // ACCOUNT", font=(FONT_MONO, 22, "bold"), text_color=FG_BRIGHT).pack(pady=(28, 4))
        ctk.CTkLabel(win, text="Sign in to your permanent NETRA identity", font=(FONT_MONO, 11), text_color=FG_DIM).pack(pady=(0, 12))

        # Server selection is intentionally available BEFORE authentication so a
        # user is never trapped on a stale/saved server address.
        ctk.CTkLabel(win, text="SERVER ADDRESS", font=(FONT_MONO, 9, "bold"), text_color=FG_DIM).pack(pady=(2, 4))
        server_entry = ctk.CTkEntry(
            win, width=320, height=38, corner_radius=0,
            fg_color=BG_INPUT, border_color=BORDER_GREEN,
            text_color=FG_BRIGHT, font=(FONT_MONO, 12)
        )
        server_entry.insert(0, f"{self.server_host}:{self.server_port}")
        server_entry.pack(pady=(0, 5))

        server_status = ctk.CTkLabel(win, text="", font=(FONT_MONO, 8), text_color=FG_DIM)
        server_status.pack(pady=(0, 8))

        def apply_server():
            raw = server_entry.get().strip()
            if not raw:
                server_status.configure(text="Enter a server address.", text_color=ERROR_RED)
                return
            new_host = raw
            new_port = PORT
            if ":" in raw and raw.count(":") == 1:
                candidate_host, candidate_port = raw.rsplit(":", 1)
                if candidate_port.isdigit():
                    new_host = candidate_host.strip()
                    new_port = int(candidate_port)
            new_host = new_host.strip()
            if not new_host:
                server_status.configure(text="Invalid server address.", text_color=ERROR_RED)
                return
            self.server_host = new_host
            self.server_port = new_port
            self.voice_port = new_port + 1
            try:
                set_key(ENV_FILE, "NETRA_SERVER_IP", f"{new_host}:{new_port}")
            except Exception:
                pass
            self.server_ip_entry.delete(0, "end")
            self.server_ip_entry.insert(0, f"{new_host}:{new_port}")
            self.server_ip_small.configure(text=f"{new_host}:{new_port}")
            server_status.configure(text=f"Using {new_host}:{new_port}", text_color=FG_DIM)
            if getattr(self, "_auth_status_label", None):
                self._auth_status_label.configure(text="")

        ctk.CTkButton(
            win, text="USE SERVER", width=145, height=32, corner_radius=0,
            fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT,
            font=(FONT_MONO, 10, "bold"), command=apply_server
        ).pack(pady=(0, 8))

        mode = ctk.StringVar(value="LOGIN")
        username = ctk.CTkEntry(win, placeholder_text="Username", width=320, height=42, corner_radius=0, fg_color=BG_INPUT, border_color=BORDER_GREEN, text_color=FG_BRIGHT, font=(FONT_MONO, 13))
        username.pack(pady=8)
        password = ctk.CTkEntry(win, placeholder_text="Password", show="•", width=320, height=42, corner_radius=0, fg_color=BG_INPUT, border_color=BORDER_GREEN, text_color=FG_BRIGHT, font=(FONT_MONO, 13))
        password.pack(pady=8)

        status = ctk.CTkLabel(win, text="", font=(FONT_MONO, 10), text_color=ERROR_RED, wraplength=340)
        status.pack(pady=(8, 10))

        def submit():
            u = username.get().strip()
            pw = password.get()
            if not u or not pw:
                status.configure(text="Enter a username and password.")
                return
            self._auth_username = u
            self._auth_password = pw
            self._auth_mode = mode.get()
            self._auth_status_label = status
            self.connect_and_auth(u, pw, self._auth_mode)

        ctk.CTkButton(win, text="LOGIN", width=145, height=40, corner_radius=0, fg_color=FG_DIM, hover_color=BTN_ACTIVE_HOVER, text_color="black", font=(FONT_MONO, 12, "bold"), command=lambda: (mode.set("LOGIN"), submit())).pack(pady=(4, 6))
        ctk.CTkButton(win, text="CREATE ACCOUNT", width=145, height=40, corner_radius=0, fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT, font=(FONT_MONO, 11, "bold"), command=lambda: (mode.set("REGISTER"), submit())).pack(pady=4)
        ctk.CTkLabel(win, text="Your username can be changed later without creating a new person.\nPasswords are stored as salted PBKDF2 hashes on the server.", font=(FONT_MONO, 9), text_color=FG_FAINT, justify="center").pack(pady=(18, 0))
        username.focus_set()

    def connect_and_auth(self, username=None, password=None, mode="LOGIN"):
        username = (username if username is not None else self.username_entry.get()).strip()
        if not username or password is None:
            return
        import base64
        encoded_password = base64.b64encode(password.encode("utf-8")).decode("ascii")
        if self.client_socket:
            try:
                self.client_socket.close()
            except Exception:
                pass
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.server_host, self.server_port))
            self.loading_history = True
            self._history_ready = False
            self.authenticated = False
            self.client_socket.sendall(f"{mode}:{username}:{encoded_password}\n".encode("utf-8"))
            threading.Thread(target=self.receive_messages_loop, daemon=True).start()
        except Exception as e:
            if getattr(self, "_auth_status_label", None):
                self._auth_status_label.configure(text=f"Could not connect: {e}")
            else:
                self.append_system_error(f"Could not link to server at {self.server_host}: {e}")

    def rename_username(self):
        if not self.authenticated or not self.client_socket:
            return
        win = ctk.CTkToplevel(self)
        win.title("NETRA // Change Username")
        win.geometry("380x220")
        win.resizable(False, False)
        win.configure(fg_color=BG_PANEL)
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(win, text="CHANGE USERNAME", font=(FONT_MONO, 18, "bold"), text_color=FG_BRIGHT).pack(pady=(24, 8))
        entry = ctk.CTkEntry(win, width=280, height=38, corner_radius=0, fg_color=BG_INPUT, border_color=BORDER_GREEN, text_color=FG_BRIGHT, font=(FONT_MONO, 12))
        entry.pack(pady=8)
        status = ctk.CTkLabel(win, text="", font=(FONT_MONO, 9), text_color=ERROR_RED)
        status.pack(pady=5)
        def do_rename():
            value = entry.get().strip()
            if not value:
                return
            self._rename_status_label = status
            try:
                self.client_socket.sendall(f"RENAME:{value}\n".encode("utf-8"))
            except Exception as e:
                status.configure(text=str(e))
        ctk.CTkButton(win, text="SAVE NAME", width=130, height=34, corner_radius=0, fg_color=FG_DIM, hover_color=BTN_ACTIVE_HOVER, text_color="black", command=do_rename).pack(pady=8)
        entry.focus_set()

    def _finish_auth_window(self):
        if self.auth_window is not None:
            try:
                self.auth_window.grab_release()
                self.auth_window.destroy()
            except Exception:
                pass
            self.auth_window = None
        self.auth_waiting = False

    def receive_messages_loop(self):
        """Socket reader. It never touches Tk widgets directly."""
        buffer = ""
        while True:
            try:
                data = self.client_socket.recv(65536)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    raw_message, buffer = buffer.split("\n", 1)
                    if raw_message:
                        self._incoming_queue.put(raw_message)
                        self.last_server_message_time = time.monotonic()
            except Exception:
                break
        self._incoming_queue.put("__NETRA_DISCONNECTED__")

    def _pump_incoming_messages(self):
        """Process a bounded packet batch so large histories do not freeze the UI."""
        processed = 0
        while processed < 60:
            try:
                raw = self._incoming_queue.get_nowait()
            except queue.Empty:
                break
            if raw == "__NETRA_DISCONNECTED__":
                self.server_status_label.configure(text="disconnected", text_color=ERROR_RED)
            else:
                try:
                    self.handle_incoming_line(raw)
                except Exception as exc:
                    self.append_system_error(f"NETRA packet error: {exc}")
            processed += 1
        self.after(20, self._pump_incoming_messages)

    def handle_incoming_line(self, raw_message):
        my_name = self.username_entry.get().strip()

        if raw_message.startswith("AUTH_OK:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                self.account_id = parts[1]
                self.authenticated = True
                name = parts[2]
                self.username_entry.configure(state="normal")
                self.username_entry.delete(0, "end")
                self.username_entry.insert(0, name)
                self.username_entry.configure(state="disabled")
                if not os.path.exists(ENV_FILE):
                    with open(ENV_FILE, "w", encoding="utf-8"):
                        pass
                set_key(ENV_FILE, "CHAT_USERNAME", name)
                set_key(ENV_FILE, "NETRA_ACCOUNT_ID", self.account_id)
                self.after(0, self._finish_auth_window)
            return
        elif raw_message.startswith("AUTH_FAIL:"):
            self.server_status_label.configure(text="authentication failed", text_color=ERROR_RED)
            reason = raw_message.split(":", 1)[1]
            self.after(0, lambda: getattr(self, "_auth_status_label", None) and self._auth_status_label.configure(text=reason))
            return
        elif raw_message.startswith("RENAME_OK:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                old_name, new_name = parts[1], parts[2]
                self.username_entry.configure(state="normal")
                self.username_entry.delete(0, "end")
                self.username_entry.insert(0, new_name)
                self.username_entry.configure(state="disabled")
                set_key(ENV_FILE, "CHAT_USERNAME", new_name)
                self.after(0, self.refresh_dm_list)
                label = getattr(self, "_rename_status_label", None)
                if label is not None:
                    label.configure(text="Username changed successfully.", text_color=FG_BRIGHT)
                    try: label.master.after(500, label.master.destroy)
                    except Exception: pass
            return
        elif raw_message.startswith("RENAME_FAIL:"):
            reason = raw_message.split(":", 1)[1]
            label = getattr(self, "_rename_status_label", None)
            if label is not None:
                self.after(0, lambda: label.configure(text=reason))
            return
        elif raw_message.startswith("USER_RENAMED:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                old_name, new_name = parts[1], parts[2]
                if old_name in self.chat_history and new_name not in self.chat_history:
                    self.chat_history[new_name] = self.chat_history.pop(old_name)
                if old_name in self.user_pil_pfps:
                    self.user_pil_pfps[new_name] = self.user_pil_pfps.pop(old_name)
                self.after(0, self.refresh_dm_list)
                self.after(0, self.update_online_users_ui, self.last_user_list, True)
            return

        if raw_message.startswith("VOICEUSERS:"):
            names_raw = raw_message.split(":", 1)[1]
            voice_user_list = [u for u in names_raw.split(",") if u]
            self.after(0, self.update_voice_users_ui, voice_user_list)
        elif raw_message.startswith("USERS:"):
            users_raw = raw_message.split(":", 1)[1]
            user_list = [u for u in users_raw.split(",") if u]
            self.after(0, self.update_online_users_ui, user_list)
        elif raw_message.startswith("ONLINE:"):
            names_raw = raw_message.split(":", 1)[1]
            online_list = [u for u in names_raw.split(",") if u]
            self.after(0, self.update_online_presence_ui, online_list)
        elif raw_message.startswith("HIST_CHANNEL:"):
            parts = raw_message.split(":", 3)
            if len(parts) == 4:
                channel, sender, text = parts[1], parts[2], parts[3]
                self.after(0, self.store_and_render, channel, sender, text)
        elif raw_message.startswith("HIST_GLOBAL:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                sender, text = parts[1], parts[2]
                self.after(0, self.store_and_render, "general-chat", sender, text)
        elif raw_message.startswith("HIST_DM:"):
            parts = raw_message.split(":", 3)
            if len(parts) == 4:
                partner, sender, text = parts[1], parts[2], parts[3]
                self.after(0, self.store_and_render, partner, sender, text)
        elif raw_message.startswith("CHANNEL:"):
            parts = raw_message.split(":", 3)
            if len(parts) == 4:
                channel, sender, text = parts[1], parts[2], parts[3]
                self.after(0, self.store_and_render, channel, sender, text)
                if sender != my_name:
                    self.play_ping_sound()
        elif raw_message.startswith("GLOBAL:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                sender, text = parts[1], parts[2]
                self.after(0, self.store_and_render, "general-chat", sender, text)
                if sender != my_name:
                    self.play_ping_sound()
        elif raw_message.startswith("DM:"):
            # DM:<room_partner>:<actual_sender>:<text>
            parts = raw_message.split(":", 3)
            if len(parts) == 4:
                chat_room, sender, text = parts[1], parts[2], parts[3]
                self.after(0, self.store_and_render, chat_room, sender, text)
                if sender != my_name:
                    self.play_ping_sound()
        elif raw_message == "READY":
            self.loading_history = False
            self._history_ready = True
            self.after(0, self.refresh_dm_list)
            self.after(0, self.reload_current_chat_view)
        elif raw_message.startswith("SERVERPFP:"):
            b64_data = raw_message.split(":", 1)[1]
            self.after(0, self.receive_server_icon, b64_data)
        elif raw_message.startswith("STATUS:"):
            p=raw_message.split(':',3)
            if len(p)>=3:
                who=p[1]; self.presence_status[who]=p[2]; self.custom_status[who]=p[3] if len(p)>3 else ''
                self.after(0,self.update_online_users_ui,self.last_user_list,True)
        elif raw_message.startswith("TYPING:"):
            p=raw_message.split(':',2)
            if len(p)==3 and p[1]!=my_name:
                self.typing_users[p[2]]=p[1]
                self.server_status_label.configure(text=f"{p[1]} is typing...", text_color=FG_DIM)
                self.after(1500,lambda:self.server_status_label.configure(text="connected", text_color=FG_DIM))
        elif raw_message.startswith("REACTION:"):
            p=raw_message.split(':',4)
            if len(p)==5: self.reactions.setdefault(p[1],{}).setdefault(p[2],[]).append(f'{p[3]}:{p[4]}')
        elif raw_message.startswith("EDITED:"):
            p=raw_message.split(':',4)
            if len(p)==5:
                room,key,who,newtext=p[1:];
                for m in self.chat_history.get(room,[]):
                    if m.get('id')==key: m['text']=newtext; m['edited']=True
                self.reload_current_chat_view()
        elif raw_message.startswith("DELETED:"):
            p=raw_message.split(':',3)
            if len(p)==4:
                room,key,_=p[1:]; self.chat_history[room]=[m for m in self.chat_history.get(room,[]) if m.get('id')!=key]; self.reload_current_chat_view()
        elif raw_message.startswith("PINNED:"):
            p=raw_message.split(':',3)
            if len(p)==4: self.pinned_messages.setdefault(p[1],[]).append(p[2])
        elif raw_message.startswith("SEARCH_RESULT:"):
            p=raw_message.split(':',3)
            if len(p)==4 and hasattr(self,'search_results_frame'):
                ctk.CTkLabel(self.search_results_frame,text=f'[{p[1]}] {p[2]}: {p[3]}',font=(FONT_MONO,10),text_color=FG_DIM,justify='left',wraplength=480).pack(fill='x',pady=4)
        elif raw_message.startswith("SEARCH_DONE:") or raw_message=="SEARCH_DONE":
            pass
        elif raw_message.startswith("CHANNEL_LIST:"):
            self.server_channels=[x for x in raw_message.split(':',1)[1].split(',') if x]
            self.after(0,self.refresh_channel_buttons)
        elif raw_message.startswith("FILE:"):
            p=raw_message.split(':',4)
            if len(p)==5: self.after(0,self.receive_file,p[1],p[2],p[3],p[4])
        elif raw_message.startswith("PFP:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                sender, b64_data = parts[1], parts[2]
                self.after(0, self.receive_pfp, sender, b64_data)

    def receive_pfp(self, sender, b64_data):
        try:
            raw_bytes = base64.b64decode(b64_data)
            img = Image.open(io.BytesIO(raw_bytes)).convert('RGB')
            self.user_pil_pfps[sender] = img
            self.reload_current_chat_view()
            self.update_online_users_ui(self.last_user_list)
            self.update_voice_users_ui(self.last_voice_user_list)
        except Exception:
            pass

    # ---------- Chat rendering ----------

    def scroll_to_bottom(self):
        try:
            self.chat_scroll.update_idletasks()
            self.chat_scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def store_and_render(self, chat_room, sender, text):
        if chat_room not in self.chat_history:
            self.chat_history[chat_room] = []

        import hashlib as _hashlib
        msg_id = _hashlib.sha1(f"{chat_room}|{sender}|{text}|{len(self.chat_history.get(chat_room,[]))}".encode()).hexdigest()[:12]
        msg_data = {"id": msg_id, "sender": sender, "text": text}
        self.chat_history[chat_room].append(msg_data)

        if self.current_target != chat_room and sender != self.username_entry.get().strip():
            self.unread_counts[chat_room]=self.unread_counts.get(chat_room,0)+1
        if self.current_target == chat_room and not self.loading_history:
            self.render_single_message(sender, text, room=chat_room)
            self.chat_room_built.add(chat_room)

        if self.sidebar_mode == "dms" and chat_room not in self.server_channels and not self.loading_history:
            self.refresh_dm_list()
        self._refresh_unread_badges()

    def update_voice_users_ui(self, user_list):
        normalized = list(dict.fromkeys(user_list))
        if normalized == self.last_voice_user_list:
            return
        self.last_voice_user_list = normalized
        for widget in self.voice_user_frame.winfo_children():
            widget.destroy()

        if not user_list:
            empty_label = ctk.CTkLabel(self.voice_user_frame, text="Nobody in voice", font=(FONT_MONO, 11), text_color=FG_FAINT)
            empty_label.pack(anchor="w", padx=10, pady=2)
            return

        for user in user_list:
            avatar_img = self.get_avatar_ctkimage(user, size=(20, 20))
            row = ctk.CTkLabel(self.voice_user_frame, image=avatar_img, text=f"  {user}", compound="left", font=(FONT_MONO, 12, "bold"), text_color=FG_BRIGHT, anchor="w")
            row.pack(fill="x", padx=10, pady=2)

    def update_online_presence_ui(self, user_list):
        self.online_user_set = set(user_list)
        self.update_online_users_ui(self.last_registered_user_list or self.last_user_list, force=True)

    def update_online_users_ui(self, user_list, force=False):
        """Show every registered account with a live online/offline indicator."""
        normalized = sorted(list(dict.fromkeys([u for u in user_list if u])), key=str.lower)
        self.last_registered_user_list = normalized
        self.last_user_list = normalized
        search = self.member_search_var.get().strip().casefold() if hasattr(self, "member_search_var") else ""
        my_name = self.username_entry.get().strip()
        visible = [u for u in normalized if u != my_name and (not search or search in u.casefold())]
        for widget in self.user_list_frame.winfo_children():
            widget.destroy()
        if not visible:
            ctk.CTkLabel(self.user_list_frame, text="No matching members" if search else "No other members", font=(FONT_MONO, 10), text_color=FG_FAINT, anchor="w").pack(fill="x", padx=8, pady=8)
        else:
            for user in visible:
                online = user in self.online_user_set
                status = "●" if online else "○"
                avatar_img = self.get_avatar_ctkimage(user, size=(24, 24))
                btn = ctk.CTkButton(self.user_list_frame, image=avatar_img, text=f"  {status} {user}", compound="left", font=(FONT_MONO, 10, "bold"), corner_radius=0, fg_color=(BTN_HOVER if user == self.current_target else "transparent"), text_color=(FG_BRIGHT if online else FG_DIM), anchor="w", height=34, hover_color=BTN_HOVER, command=lambda u=user: self.select_dm_channel(u))
                btn.pack(fill="x", padx=4, pady=1)
        if self.sidebar_mode == "dms":
            self.refresh_dm_list()

    def select_global_channel(self):
        self.select_channel("general-chat")

    def select_dm_channel(self, username):
        if not username or username == self.username_entry.get().strip():
            return
        self._save_current_draft()
        already_selected = (self.current_target == username and self.sidebar_mode == "dms")
        self.current_target = username
        self.unread_counts[username]=0
        self.message_entry.configure(placeholder_text=f"Message @{username}")
        if self.sidebar_mode != "dms":
            self.show_dm_view()
        else:
            self.refresh_dm_list()
            if not already_selected:
                self.show_chat_room(username)
        self._restore_current_draft()
        self._refresh_unread_badges()

    def get_chat_room_frame(self, room):
        frame = self.chat_room_frames.get(room)
        if frame is None or not frame.winfo_exists():
            frame = ctk.CTkFrame(self.chat_scroll, fg_color="transparent", corner_radius=0)
            self.chat_room_frames[room] = frame
            self.chat_room_built.discard(room)
        return frame

    def show_chat_room(self, room):
        frame = self.get_chat_room_frame(room)

        # Hide the previous room instead of destroying all of its widgets.
        # Switching chats is therefore just a couple of Tk operations.
        for other in self.chat_room_frames.values():
            if other is not frame and other.winfo_manager():
                other.pack_forget()
        if not frame.winfo_manager():
            frame.pack(fill="both", expand=True, padx=5, pady=5, anchor="nw")

        if room not in self.chat_room_built:
            for msg in self.chat_history.get(room, []):
                self.render_single_message(msg["sender"], msg["text"], room=room)
            self.chat_room_built.add(room)

        self.after_idle(self.scroll_to_bottom)

    def reload_current_chat_view(self):
        # Kept for the existing message/PFP update paths. It no longer rebuilds
        # the whole conversation on every navigation.
        self.show_chat_room(self.current_target)

    def render_single_message(self, sender, text, room=None):
        room = room or self.current_target
        parent = self.get_chat_room_frame(room)
        msg_frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        msg_frame.pack(fill="x", pady=6, padx=5, anchor="w")
        self.all_rendered_widgets.append(msg_frame)

        avatar_img = self.get_avatar_ctkimage(sender, size=(40, 40))
        avatar_label = ctk.CTkLabel(msg_frame, image=avatar_img, text="")
        avatar_label.pack(side="left", anchor="n", padx=(0, 10))

        content_frame = ctk.CTkFrame(msg_frame, fg_color="transparent", corner_radius=0)
        content_frame.pack(side="left", fill="x", expand=True)

        user_label = ctk.CTkLabel(content_frame, text=sender, font=(FONT_MONO, 15, "bold"), text_color=FG_BRIGHT)
        user_label.pack(anchor="w")

        text_label = ctk.CTkLabel(content_frame, text=text, font=(FONT_MONO, 13), text_color=FG_DIM, justify="left", wraplength=450)
        text_label.pack(anchor="w", pady=(2, 0))

        def menu(event):
            m=__import__('tkinter').Menu(self,tearoff=0)
            m.add_command(label='Reply',command=lambda:self.message_entry.insert(0,f'@{sender} '))
            m.add_command(label='React 👍',command=lambda:self.send_reaction(room,text))
            m.add_command(label='React ❤️',command=lambda:self.send_reaction(room,text,'❤️'))
            m.add_command(label='Pin',command=lambda:self.send_pin(room,text))
            if sender==self.username_entry.get().strip():
                m.add_command(label='Edit',command=lambda:self.open_edit_message(room,text))
                m.add_command(label='Delete',command=lambda:self.send_delete(room,text))
            m.tk_popup(event.x_root,event.y_root)
        for w in (msg_frame,avatar_label,content_frame,user_label,text_label): w.bind('<Button-3>',menu)

        if room == self.current_target:
            self.after_idle(self.scroll_to_bottom)

    def append_system_error(self, error_text):
        err_frame = ctk.CTkFrame(self.chat_scroll, fg_color="transparent", corner_radius=0)
        err_frame.pack(fill="x", pady=4, padx=5, anchor="w")
        self.all_rendered_widgets.append(err_frame)

        err_label = ctk.CTkLabel(err_frame, text=error_text, font=(FONT_MONO, 12, "italic"), text_color=ERROR_RED, justify="left", wraplength=500)
        err_label.pack(anchor="w")
        self.after(10, self.scroll_to_bottom)

    def send_typing_indicator(self):
        if not self.client_socket or not self.authenticated: return
        try: self.client_socket.sendall(f"TYPING:{self.current_target}\n".encode('utf-8'))
        except Exception: pass

    def send_message(self):
        message=self.message_entry.get().strip()
        if not message or not self.client_socket or not self.authenticated: return
        self.draft_messages.pop(self.current_target,None); self.message_entry.delete(0,'end')
        if self.current_target in self.server_channels: payload=f"CHANNEL:{self.current_target}:{message}\n"
        else: payload=f"DM:{self.current_target}:{message}\n"
        try: self.client_socket.sendall(payload.encode('utf-8'))
        except Exception as e: self.append_system_error(f"Message delivery lost: {e}")
        self._refresh_unread_badges()

    def open_netra_hub(self):
        win=ctk.CTkToplevel(self); win.title('NETRA // HUB'); win.geometry('520x620'); win.configure(fg_color=BG_ROOT); win.transient(self)
        ctk.CTkLabel(win,text='NETRA // FEATURES',font=(FONT_MONO,20,'bold'),text_color=FG_BRIGHT).pack(pady=(20,10))
        items=[('👤 PROFILE',self.open_profile),('🟢 PRESENCE / STATUS',self.open_status),('⭐ FAVORITES',self.open_favorites),('🔔 NOTIFICATIONS',self.open_notifications),('📌 PINNED MESSAGES',self.open_pins),('🔎 SEARCH MESSAGES',self.open_search),('🌐 SERVER BROWSER',self.open_server_browser),('🎨 THEMES',self.open_themes),('🛡️ SERVER / CHANNEL TOOLS',self.open_channel_tools)]
        for text,cmd in items: ctk.CTkButton(win,text=text,command=cmd,height=38,corner_radius=0,fg_color=BTN_BG,hover_color=BTN_HOVER,text_color=FG_BRIGHT,font=(FONT_MONO,11,'bold')).pack(fill='x',padx=35,pady=5)
        ctk.CTkLabel(win,text='Right-click messages for reply / edit / delete / react / pin.',font=(FONT_MONO,9),text_color=FG_FAINT).pack(pady=18)

    def simple_window(self,title,lines,buttons=None,size='460x420'):
        win=ctk.CTkToplevel(self); win.title(title); win.geometry(size); win.configure(fg_color=BG_ROOT); win.transient(self)
        ctk.CTkLabel(win,text=title,font=(FONT_MONO,18,'bold'),text_color=FG_BRIGHT).pack(pady=(20,10))
        for line in lines: ctk.CTkLabel(win,text=line,font=(FONT_MONO,10),text_color=FG_DIM,justify='left',wraplength=400).pack(anchor='w',padx=25,pady=4)
        if buttons:
            for label,cmd in buttons: ctk.CTkButton(win,text=label,command=cmd,height=34,corner_radius=0,fg_color=BTN_BG,hover_color=BTN_HOVER,text_color=FG_BRIGHT,font=(FONT_MONO,10,'bold')).pack(fill='x',padx=35,pady=4)
        return win

    def open_profile(self):
        name=self.username_entry.get().strip(); status=self.presence_status.get(name,'Online'); custom=self.custom_status.get(name,'')
        self.simple_window('NETRA // PROFILE',[f'Username: {name}',f'Status: {status}',f'Custom status: {custom or "(none)"}',f'Account ID: {self.account_id or "unknown"}'],size='480x300')

    def open_status(self):
        win=ctk.CTkToplevel(self); win.title('NETRA // STATUS'); win.geometry('420x330'); win.configure(fg_color=BG_ROOT)
        var=ctk.StringVar(value=self.presence_status.get(self.username_entry.get().strip(),'Online')); custom=ctk.StringVar(value=self.custom_status.get(self.username_entry.get().strip(),''))
        ctk.CTkLabel(win,text='PRESENCE',font=(FONT_MONO,18,'bold'),text_color=FG_BRIGHT).pack(pady=18)
        ctk.CTkOptionMenu(win,variable=var,values=['Online','Idle','DND','Invisible'],fg_color=BTN_BG,button_color=FG_DIM,button_hover_color=BTN_HOVER,text_color=FG_BRIGHT).pack(pady=8)
        ctk.CTkEntry(win,textvariable=custom,width=300,height=38,fg_color=BG_INPUT,border_color=BORDER_GREEN,text_color=FG_BRIGHT,placeholder_text='Custom status').pack(pady=8)
        def save():
            self.presence_status[self.username_entry.get().strip()]=var.get(); self.custom_status[self.username_entry.get().strip()]=custom.get(); self.client_socket.sendall(f'STATUS:{var.get()}:{custom.get()}\n'.encode()); win.destroy()
        ctk.CTkButton(win,text='SAVE STATUS',command=save,fg_color=FG_DIM,text_color='black',height=36).pack(pady=12)

    def open_favorites(self):
        self.simple_window('NETRA // FAVORITES',[*(sorted(self.favorites) or ['No favorites yet.'])],size='400x300')

    def open_notifications(self):
        self.simple_window('NETRA // NOTIFICATIONS',[f'Unread rooms: {sum(self.unread_counts.values())}', 'Notifications are generated for DMs, mentions, replies, reactions and server events.'],size='460x260')

    def open_pins(self):
        pins=[]
        for room,arr in self.pinned_messages.items(): pins += [f'[{room}] {x}' for x in arr]
        self.simple_window('NETRA // PINNED MESSAGES',pins or ['No pinned messages in this session.'],size='500x400')

    def open_channel_tools(self):
        win=ctk.CTkToplevel(self); win.title('NETRA // SERVER TOOLS'); win.geometry('440x360'); win.configure(fg_color=BG_ROOT)
        e=ctk.CTkEntry(win,placeholder_text='new-channel',width=300); e.pack(pady=25)
        def create():
            if e.get().strip() and self.client_socket: self.client_socket.sendall(f'CREATE_CHANNEL:{e.get().strip()}\n'.encode())
        ctk.CTkButton(win,text='CREATE CHANNEL',command=create,fg_color=FG_DIM,text_color='black').pack(pady=8)
        ctk.CTkLabel(win,text='Server-side permissions should be enforced before exposing this to untrusted users.',font=(FONT_MONO,9),text_color=FG_FAINT,wraplength=360).pack(pady=15)

    def open_search(self):
        win=ctk.CTkToplevel(self); win.title('NETRA // SEARCH'); win.geometry('560x500'); win.configure(fg_color=BG_ROOT)
        e=ctk.CTkEntry(win,placeholder_text='Search messages...',width=430,height=36); e.pack(pady=15); out=ctk.CTkScrollableFrame(win,fg_color=BG_PANEL); out.pack(fill='both',expand=True,padx=15,pady=10)
        def go():
            for w in out.winfo_children(): w.destroy()
            if self.client_socket: self.client_socket.sendall(f'SEARCH:{e.get().strip()}\n'.encode())
        ctk.CTkButton(win,text='SEARCH',command=go,fg_color=FG_DIM,text_color='black').pack(pady=4)
        self.search_results_frame=out

    def open_server_browser(self):
        win=ctk.CTkToplevel(self); win.title('NETRA // SERVER BROWSER'); win.geometry('600x500'); win.configure(fg_color=BG_ROOT)
        out=ctk.CTkScrollableFrame(win,fg_color=BG_PANEL); out.pack(fill='both',expand=True,padx=15,pady=15)
        def refresh():
            for w in out.winfo_children(): w.destroy()
            try:
                with socket.create_connection((self.server_host,MAIN_PORT),timeout=5) as s:
                    s.sendall(b'SERVER_LIST\n'); data=s.recv(65536).decode().strip()
                if data.startswith('SERVERS:'):
                    import json as _j
                    items=_j.loads(data.split(':',1)[1])
                    for sid,info in items.items():
                        ctk.CTkButton(out,text=f"{info.get('name','Server')}  //  {info.get('host','')}",height=42,corner_radius=0,fg_color=BTN_BG,hover_color=BTN_HOVER,text_color=FG_BRIGHT,command=lambda hp=info.get('host',''): self.connect_to_server_address(hp)).pack(fill='x',pady=4)
            except Exception as ex: ctk.CTkLabel(out,text=f'Main server unavailable: {ex}',text_color=ERROR_RED).pack(pady=20)
        ctk.CTkButton(win,text='REFRESH',command=refresh,fg_color=FG_DIM,text_color='black').pack(pady=(0,12)); refresh()

    def connect_to_server_address(self,hostport):
        self.server_ip_entry.delete(0,'end'); self.server_ip_entry.insert(0,hostport); self.connect_to_server_from_bar()

    def send_reaction(self,room,text,emoji='👍'):
        import hashlib as _h; key=_h.sha1(f'{room}|{text}'.encode()).hexdigest()[:12]
        try:self.client_socket.sendall(f'REACT:{room}:{key}:{emoji}\n'.encode())
        except Exception:pass
    def send_pin(self,room,text):
        import hashlib as _h; key=_h.sha1(f'{room}|{text}'.encode()).hexdigest()[:12]
        try:self.client_socket.sendall(f'PIN:{room}:{key}\n'.encode())
        except Exception:pass
    def send_delete(self,room,text):
        import hashlib as _h; key=_h.sha1(f'{room}|{text}'.encode()).hexdigest()[:12]
        try:self.client_socket.sendall(f'DELETE:{room}:{key}\n'.encode())
        except Exception:pass
    def open_edit_message(self,room,text):
        win=ctk.CTkToplevel(self); win.title('EDIT MESSAGE'); win.geometry('500x190'); win.configure(fg_color=BG_ROOT)
        e=ctk.CTkEntry(win,width=400,height=40); e.insert(0,text); e.pack(pady=25)
        def save():
            import hashlib as _h; key=_h.sha1(f'{room}|{text}'.encode()).hexdigest()[:12]
            try:self.client_socket.sendall(f'EDIT:{room}:{key}:{e.get()}\n'.encode())
            except Exception:pass
            win.destroy()
        ctk.CTkButton(win,text='SAVE EDIT',command=save,fg_color=FG_DIM,text_color='black').pack()
    def refresh_channel_buttons(self):
        # Keep the first two controls and add dynamic channels below them.
        for w in getattr(self,'dynamic_channel_buttons',[]):
            try:w.destroy()
            except:pass
        self.dynamic_channel_buttons=[]
        for ch in self.server_channels[2:]:
            b=ctk.CTkButton(self.sidebar_body,text=f'# {ch}',font=(FONT_MONO,11,'bold'),fg_color=BTN_BG,hover_color=BTN_HOVER,text_color=FG_BRIGHT,height=30,corner_radius=0,command=lambda x=ch:self.select_channel(x)); b.pack(fill='x',padx=8,pady=2); self.dynamic_channel_buttons.append(b)
    def receive_file(self,room,sender,name,b64):
        try:
            raw=base64.b64decode(b64); path=os.path.join(CONFIG_DIR,'downloads'); os.makedirs(path,exist_ok=True); safe=re.sub(r'[^A-Za-z0-9._-]','_',name); full=os.path.join(path,safe)
            with open(full,'wb') as f:f.write(raw)
            self.store_and_render(room,sender,f'📎 {safe} saved to {full}')
        except Exception as e:self.append_system_error(f'File receive failed: {e}')

    # ---------- Voice chat ----------

    def toggle_voice_chat(self):
        if not SOUNDDEVICE_AVAILABLE:
            self.append_system_error("Voice chat needs the 'sounddevice' package. Install it with: pip install sounddevice")
            return
        if self.in_voice_chat:
            self.stop_voice_chat()
        else:
            self.start_voice_chat()

    def start_voice_chat(self):
        username = self.username_entry.get().strip()
        if not username:
            return
        try:
            self.voice_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.voice_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
            self.voice_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
            self.voice_socket.sendto(f"REGISTER:{username}".encode('utf-8'), (self.server_host, self.voice_port if hasattr(self,"voice_port") else VOICE_PORT))

            input_device = self.voice_device_input
            output_device = self.voice_device_output

            # Never pass a duplicate device NAME to sounddevice.  NETRA
            # always uses a concrete numeric device ID here.
            if isinstance(input_device, str) or isinstance(output_device, str):
                self.append_system_error(
                    "NETRA voice settings contained an old device name. "
                    "Open Settings, select the exact [ID] device, then SAVE SETTINGS."
                )
                raise RuntimeError("old/ambiguous audio device setting")

            # 16 kHz is NETRA's network format, but many Windows devices
            # (especially webcam/USB microphones) do not accept 16 kHz directly.
            # Use each device's advertised default/native rate and resample at the
            # network boundary instead of asking PortAudio for an unsupported rate.
            def device_default_rate(device_id, is_input):
                try:
                    info = sd.query_devices(device_id, "input" if is_input else "output")
                    rate = int(round(float(info.get("default_samplerate", 48000))))
                    if rate > 0:
                        return rate
                except Exception:
                    pass
                return 48000

            self.voice_input_rate = device_default_rate(input_device, True)
            self.voice_output_rate = device_default_rate(output_device, False)

            try:
                sd.check_input_settings(device=input_device, samplerate=self.voice_input_rate, channels=VOICE_CHANNELS, dtype='int16')
            except Exception as e:
                raise RuntimeError(f"Microphone does not accept {self.voice_input_rate} Hz: {e}")
            try:
                sd.check_output_settings(device=output_device, samplerate=self.voice_output_rate, channels=VOICE_CHANNELS, dtype='int16')
            except Exception as e:
                raise RuntimeError(f"Output device does not accept {self.voice_output_rate} Hz: {e}")

            self.voice_input_stream = sd.RawInputStream(
                samplerate=self.voice_input_rate, blocksize=VOICE_CHUNK, dtype='int16',
                channels=VOICE_CHANNELS, device=input_device, latency="low")
            self.voice_input_stream.start()
            self.voice_output_stream = sd.RawOutputStream(
                samplerate=self.voice_output_rate, blocksize=VOICE_CHUNK, dtype='int16',
                channels=VOICE_CHANNELS, device=output_device, latency="low")
            self.voice_output_stream.start()

            self.in_voice_chat = True
            self.voice_btn.configure(text="🎤 Leave Voice", fg_color=BTN_ACTIVE_BG, hover_color=BTN_ACTIVE_HOVER, text_color="black")

            # Tell the server over TCP too, so "who's in voice" works even if
            # the UDP voice port isn't forwarded on your router.
            try:
                self.client_socket.sendall(b"VOICEJOIN:1\n")
            except Exception:
                pass

            threading.Thread(target=self.voice_send_loop, daemon=True).start()
            threading.Thread(target=self.voice_recv_loop, daemon=True).start()
        except Exception as e:
            self.append_system_error(f"Could not start voice chat: {e}")
            self.stop_voice_chat()

    def voice_send_loop(self):
        while self.in_voice_chat:
            try:
                data, overflowed = self.voice_input_stream.read(VOICE_CHUNK)
                if self.voice_muted:
                    data = b"\x00" * len(data)
                # Convert device-native PCM to NETRA's fixed 16 kHz network format.
                network_data = resample_pcm16_mono(bytes(data), self.voice_input_rate, VOICE_RATE)
                self.voice_socket.sendto(network_data, (self.server_host, self.voice_port if hasattr(self,"voice_port") else VOICE_PORT))
            except Exception:
                break

    def voice_recv_loop(self):
        try:
            self.voice_socket.settimeout(1.0)
        except Exception:
            pass
        while self.in_voice_chat:
            try:
                data, _ = self.voice_socket.recvfrom(4096)
                if self.voice_output_stream:
                    # Convert NETRA's 16 kHz network audio to the selected output
                    # device's native rate before handing it to PortAudio.
                    playback_data = resample_pcm16_mono(data, VOICE_RATE, self.voice_output_rate)
                    self.voice_output_stream.write(playback_data)
            except socket.timeout:
                continue
            except Exception:
                break

    def toggle_voice_mute(self):
        self.voice_muted = not self.voice_muted
        if self.voice_muted:
            self.voice_mute_btn.configure(text="🎤 Unmute Mic", fg_color=BTN_ACTIVE_BG, text_color="black")
        else:
            self.voice_mute_btn.configure(text="🔇 Mute Mic", fg_color=BTN_BG, text_color=FG_BRIGHT)

    def stop_voice_chat(self):
        self.in_voice_chat = False
        try:
            if self.client_socket:
                self.client_socket.sendall(b"VOICELEAVE:1\n")
        except Exception:
            pass
        username = self.username_entry.get().strip()
        try:
            if self.voice_socket and username:
                self.voice_socket.sendto(f"UNREGISTER:{username}".encode('utf-8'), (self.server_host, self.voice_port if hasattr(self,"voice_port") else VOICE_PORT))
        except Exception:
            pass
        for stream in (self.voice_input_stream, self.voice_output_stream):
            try:
                if stream:
                    stream.stop()
                    stream.close()
            except Exception:
                pass
        self.voice_input_stream = None
        self.voice_output_stream = None
        try:
            if self.voice_socket:
                self.voice_socket.close()
        except Exception:
            pass
        self.voice_socket = None
        try:
            self.voice_btn.configure(text="🎤 Join Voice", fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT)
        except Exception:
            pass

    def on_close(self):
        if self.in_voice_chat:
            self.stop_voice_chat()
        self.destroy()


if __name__ == "__main__":
    app = FullDiscordClone()
    app.mainloop()