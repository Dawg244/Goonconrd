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

HOST = '108.221.36.120'
PORT = 12145
VOICE_PORT = 12146

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
    """Generate one of several built-in notification sounds."""
    sounds = {
        "ping": (880, 0.15, 0.30),
        "ping_2": (660, 0.18, 0.28),
        "ping_3": (1047, 0.12, 0.28),
        "ping_4": (523, 0.22, 0.26),
        "ping_5": (740, 0.20, 0.30),
    }
    freq, duration, volume = sounds.get(style, sounds["ping"])
    path = os.path.join(tempfile.gettempdir(), f"netra_{style}.wav")
    if os.path.exists(path):
        return path
    framerate = 44100
    n_samples = int(framerate * duration)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        frames = bytearray()
        for i in range(n_samples):
            # Small fade-in/out keeps the notification from clicking.
            t = i / framerate
            fade = min(1.0, i / (framerate * 0.01), (n_samples - i) / (framerate * 0.02))
            value = int(32767 * volume * fade * math.sin(2 * math.pi * freq * t))
            frames += struct.pack("<h", value)
        wf.writeframes(bytes(frames))
    return path


def load_persistent_settings():
    defaults = {
        "dm_sound_mode": "ping",
        "dm_sound_path": "",
        "voice_input_device": None,
        "voice_output_device": None,
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

        self.title("NETRA // TERMINAL")
        self.geometry("1000x600")
        self.resizable(False, False)
        self.configure(fg_color=BG_ROOT)

        self.client_socket = None
        self.current_target = "GLOBAL"
        self.chat_history = {"GLOBAL": []}
        self.all_rendered_widgets = []
        self.last_user_list = []
        self.online_user_set = set()
        self.last_voice_user_list = []
        self.sidebar_mode = "server"  # "server" or "dms"

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
        saved = load_persistent_settings()
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

        self.server_title = ctk.CTkLabel(self.channel_sidebar, text="NETRA // Main Server", font=(FONT_MONO, 14, "bold"), text_color=FG_BRIGHT)
        self.server_title.pack(pady=15, padx=15, anchor="w")

        self.sidebar_body = ctk.CTkFrame(self.channel_sidebar, fg_color="transparent", corner_radius=0)
        self.sidebar_body.pack(fill="both", expand=True)

        self.channel_btn = ctk.CTkButton(self.sidebar_body, text="# general-chat", font=(FONT_MONO, 12, "bold"), fg_color=BTN_HOVER, hover_color=BTN_HOVER, text_color=FG_BRIGHT, height=32, corner_radius=0, command=self.go_to_server_view)
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
        self.username_entry.bind("<Return>", lambda event: self.connect_and_auth())

        self.settings_btn = ctk.CTkButton(
            self.user_section, text="⚙ SETTINGS", font=(FONT_MONO, 10, "bold"),
            fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=FG_BRIGHT,
            height=24, width=120, corner_radius=0, command=self.open_settings
        )
        self.settings_btn.pack(pady=(0, 8))

        # ---------------- Right Active User Panel ----------------
        self.member_sidebar = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color=BG_PANEL)
        self.member_sidebar.pack(side="right", fill="y")

        self.voice_header = ctk.CTkLabel(self.member_sidebar, text="IN VOICE 🔊", font=(FONT_MONO, 10, "bold"), text_color=FG_DIM)
        self.voice_header.pack(padx=15, pady=(15, 5), anchor="w")

        self.voice_user_frame = ctk.CTkFrame(self.member_sidebar, fg_color="transparent")
        self.voice_user_frame.pack(fill="x")
        self.update_voice_users_ui([])

        self.member_header = ctk.CTkLabel(self.member_sidebar, text="ONLINE USERS", font=(FONT_MONO, 10, "bold"), text_color=FG_DIM)
        self.member_header.pack(padx=15, pady=(15, 5), anchor="w")

        self.user_list_frame = ctk.CTkFrame(self.member_sidebar, fg_color="transparent")
        self.user_list_frame.pack(fill="both", expand=True)

        # ---------------- Central Message Arena ----------------
        self.main_chat_area = ctk.CTkFrame(self, fg_color=BG_ROOT, corner_radius=0)
        self.main_chat_area.pack(side="right", fill="both", expand=True)

        # decorative retro divider (as close to "scanlines" as a widget-based UI can do)
        self.scanline_deco = ctk.CTkLabel(self.main_chat_area, text="·" * 160, font=(FONT_MONO, 8), text_color=BORDER_GREEN, anchor="w")
        self.scanline_deco.pack(fill="x", padx=10, pady=(6, 0))

        self.chat_scroll = ctk.CTkScrollableFrame(self.main_chat_area, fg_color=BG_ROOT, corner_radius=0, label_text="")
        self.chat_scroll.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.input_container = ctk.CTkFrame(self.main_chat_area, fg_color=BG_ROOT, height=60, corner_radius=0)
        self.input_container.pack(fill="x", side="bottom", padx=20, pady=(0, 20))

        self.message_entry = ctk.CTkEntry(self.input_container, placeholder_text="Message #general-chat", height=44, corner_radius=0, fg_color=BG_INPUT, border_color=BORDER_GREEN, text_color=FG_BRIGHT, placeholder_text_color=FG_FAINT, font=(FONT_MONO, 13))
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.message_entry.bind("<Return>", lambda event: self.send_message())

        self.send_button = ctk.CTkButton(self.input_container, text="SEND", width=80, height=44, corner_radius=0, fg_color=FG_DIM, hover_color=BTN_ACTIVE_HOVER, text_color="black", font=(FONT_MONO, 13, "bold"), command=self.send_message)
        self.send_button.pack(side="right")

        self.show_server_view()

        self.after(500, self.connect_and_auth)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- Sidebar navigation (server channels <-> DMs) ----------

    def go_to_server_view(self):
        self.show_server_view()
        self.select_global_channel()

    def show_server_view(self):
        self.sidebar_mode = "server"
        self.server_title.configure(text="Main Server")
        self.dm_list_frame.pack_forget()
        self.channel_btn.pack(fill="x", padx=10, pady=5)
        self.voice_btn.pack(fill="x", padx=10, pady=(0, 2))
        self.voice_mute_btn.pack(fill="x", padx=10, pady=(0, 5))

    def show_dm_view(self):
        self.sidebar_mode = "dms"
        self.server_title.configure(text="Direct Messages")
        self.channel_btn.pack_forget()
        self.voice_btn.pack_forget()
        self.voice_mute_btn.pack_forget()

        if self.current_target == "GLOBAL":
            candidates = sorted(set(self.chat_history.keys()) - {"GLOBAL"})
            if candidates:
                self.current_target = candidates[0]
                self.message_entry.configure(placeholder_text=f"Message @{self.current_target}")

        self.refresh_dm_list()
        self.dm_list_frame.pack(fill="both", expand=True)
        self.reload_current_chat_view()

    def refresh_dm_list(self):
        for widget in self.dm_list_frame.winfo_children():
            widget.destroy()

        my_name = self.username_entry.get().strip()
        partners = set(self.chat_history.keys()) - {"GLOBAL"}
        # last_user_list is the persistent account list sent by the server,
        # so offline accounts remain available for DMs.
        partners |= set(u for u in self.last_user_list if u != my_name)
        partners.discard(my_name)

        if not partners:
            lbl = ctk.CTkLabel(self.dm_list_frame, text="No conversations yet.\nClick a name on the right\nto start one.", font=(FONT_MONO, 11), text_color=FG_FAINT, justify="left")
            lbl.pack(anchor="w", padx=10, pady=10)
            return

        for user in sorted(partners):
            avatar_img = self.get_avatar_ctkimage(user, size=(24, 24))
            is_selected = (user == self.current_target)
            btn = ctk.CTkButton(self.dm_list_frame, image=avatar_img, text=f"  {user}", compound="left", font=(FONT_MONO, 12, "bold"), corner_radius=0, fg_color=(BTN_HOVER if is_selected else "transparent"), text_color=FG_BRIGHT, anchor="w", height=32, hover_color=BTN_HOVER, command=lambda u=user: self.select_dm_channel(u))
            btn.pack(fill="x", padx=10, pady=2)

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

    # ---------- Sound ----------

    def save_settings_file(self, dm_mode, dm_path, input_device, output_device):
        data = {
            "dm_sound_mode": dm_mode,
            "dm_sound_path": dm_path,
            "voice_input_device": input_device,
            "voice_output_device": output_device,
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
        """Play the configured DM notification sound without blocking the UI."""
        if self.dm_sound_mode == "off":
            return
        try:
            if self.dm_sound_mode == "custom" and self.dm_sound_path and os.path.exists(self.dm_sound_path):
                path = self.dm_sound_path
            else:
                path = generate_ping_wav(self.dm_sound_mode)
            if os.name == "nt":
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif sys.platform == "darwin":
                subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["aplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    def connect_and_auth(self):
        username = self.username_entry.get().strip()
        if not username:
            return

        if not os.path.exists(ENV_FILE):
            with open(ENV_FILE, 'w') as f:
                pass
        set_key(ENV_FILE, "CHAT_USERNAME", username)

        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass

        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((HOST, PORT))
            self.loading_history = True
            self._history_ready = False
            self.client_socket.sendall(f"AUTH:{username}\n".encode('utf-8'))
            self.user_pil_pfps[username] = self.pil_pfp
            self.send_own_pfp()
            threading.Thread(target=self.receive_messages_loop, daemon=True).start()
        except Exception as e:
            self.append_system_error(f"Could not link to server at {HOST}: {e}")

    def receive_messages_loop(self):
        buffer = ""
        while True:
            try:
                data = self.client_socket.recv(65536)
                if not data:
                    break
                buffer += data.decode('utf-8')
                while "\n" in buffer:
                    raw_message, buffer = buffer.split("\n", 1)
                    if not raw_message:
                        continue
                    self.handle_incoming_line(raw_message)
            except:
                break

    def handle_incoming_line(self, raw_message):
        my_name = self.username_entry.get().strip()

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
        elif raw_message.startswith("HIST_GLOBAL:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                sender, text = parts[1], parts[2]
                self.after(0, self.store_and_render, "GLOBAL", sender, text)
        elif raw_message.startswith("HIST_DM:"):
            parts = raw_message.split(":", 3)
            if len(parts) == 4:
                partner, sender, text = parts[1], parts[2], parts[3]
                self.after(0, self.store_and_render, partner, sender, text)
        elif raw_message.startswith("GLOBAL:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                sender, text = parts[1], parts[2]
                self.after(0, self.store_and_render, "GLOBAL", sender, text)
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

        msg_data = {"sender": sender, "text": text}
        self.chat_history[chat_room].append(msg_data)

        if self.current_target == chat_room and not self.loading_history:
            self.render_single_message(sender, text)

        if self.sidebar_mode == "dms" and chat_room != "GLOBAL" and not self.loading_history:
            self.refresh_dm_list()

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
        self.update_online_users_ui(self.last_user_list, force=True)

    def update_online_users_ui(self, user_list, force=False):
        normalized = list(dict.fromkeys(user_list))
        if normalized == self.last_user_list and not force:
            return
        self.last_user_list = normalized
        for widget in self.user_list_frame.winfo_children():
            widget.destroy()

        my_name = self.username_entry.get().strip()
        for user in sorted(user_list, key=str.lower):
            if user == my_name:
                continue
            avatar_img = self.get_avatar_ctkimage(user, size=(24, 24))
            online = user in self.online_user_set
            status = "●" if online else "○"
            status_color = FG_BRIGHT if online else FG_FAINT
            btn = ctk.CTkButton(
                self.user_list_frame, image=avatar_img,
                text=f"  {status} {user}", compound="left",
                font=(FONT_MONO, 12, "bold"), corner_radius=0,
                fg_color="transparent", text_color=(FG_BRIGHT if online else FG_DIM),
                anchor="w", height=32, hover_color=BTN_HOVER,
                command=lambda u=user: self.select_dm_channel(u))
            btn.pack(fill="x", padx=10, pady=2)

        if self.sidebar_mode == "dms":
            self.refresh_dm_list()

    def select_global_channel(self):
        self.current_target = "GLOBAL"
        self.message_entry.configure(placeholder_text="Message #general-chat")
        self.channel_btn.configure(fg_color=BTN_HOVER)
        self.reload_current_chat_view()

    def select_dm_channel(self, username):
        self.current_target = username
        self.message_entry.configure(placeholder_text=f"Message @{username}")
        self.show_dm_view()

    def reload_current_chat_view(self):
        for widget in self.all_rendered_widgets:
            widget.destroy()
        self.all_rendered_widgets.clear()

        messages = self.chat_history.get(self.current_target, [])
        for msg in messages:
            self.render_single_message(msg["sender"], msg["text"])
        self.after(10, self.scroll_to_bottom)

    def render_single_message(self, sender, text):
        msg_frame = ctk.CTkFrame(self.chat_scroll, fg_color="transparent", corner_radius=0)
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

        self.after(10, self.scroll_to_bottom)

    def append_system_error(self, error_text):
        err_frame = ctk.CTkFrame(self.chat_scroll, fg_color="transparent", corner_radius=0)
        err_frame.pack(fill="x", pady=4, padx=5, anchor="w")
        self.all_rendered_widgets.append(err_frame)

        err_label = ctk.CTkLabel(err_frame, text=error_text, font=(FONT_MONO, 12, "italic"), text_color=ERROR_RED, justify="left", wraplength=500)
        err_label.pack(anchor="w")
        self.after(10, self.scroll_to_bottom)

    def send_message(self):
        message = self.message_entry.get().strip()
        if not message or not self.client_socket:
            return

        self.message_entry.delete(0, "end")

        if self.current_target == "GLOBAL":
            network_payload = f"GLOBAL:{message}\n"
        else:
            network_payload = f"DM:{self.current_target}:{message}\n"

        try:
            self.client_socket.sendall(network_payload.encode('utf-8'))
        except Exception as e:
            self.append_system_error(f"Message delivery lost: {e}")

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
            self.voice_socket.sendto(f"REGISTER:{username}".encode('utf-8'), (HOST, VOICE_PORT))

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
                self.voice_socket.sendto(network_data, (HOST, VOICE_PORT))
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
                self.voice_socket.sendto(f"UNREGISTER:{username}".encode('utf-8'), (HOST, VOICE_PORT))
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