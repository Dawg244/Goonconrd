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
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image
from dotenv import load_dotenv, set_key

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

ENV_FILE = ".env"
load_dotenv(ENV_FILE)

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


def generate_ping_wav():
    """Builds (once) a short beep .wav in the temp dir and returns its path."""
    path = os.path.join(tempfile.gettempdir(), "discordlite_ping.wav")
    if os.path.exists(path):
        return path
    framerate = 44100
    duration = 0.15
    freq = 880.0
    n_samples = int(framerate * duration)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        frames = bytearray()
        for i in range(n_samples):
            value = int(32767 * 0.3 * math.sin(2 * math.pi * freq * (i / framerate)))
            frames += struct.pack('<h', value)
        wf.writeframes(bytes(frames))
    return path


class FullDiscordClone(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Discord Lite // TERMINAL")
        self.geometry("1000x600")
        self.resizable(False, False)
        self.configure(fg_color=BG_ROOT)

        self.client_socket = None
        self.current_target = "GLOBAL"
        self.chat_history = {"GLOBAL": []}
        self.all_rendered_widgets = []
        self.last_user_list = []
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
        self.dm_sound_mode = os.getenv("DM_SOUND", "ping")
        self.dm_sound_path = os.getenv("DM_SOUND_PATH", "")
        self.voice_device_input = os.getenv("VOICE_INPUT_DEVICE", "") or None
        self.voice_device_output = os.getenv("VOICE_OUTPUT_DEVICE", "") or None
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

        self.server_title = ctk.CTkLabel(self.channel_sidebar, text="Main Server", font=(FONT_MONO, 14, "bold"), text_color=FG_BRIGHT)
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

    def _save_setting(self, key, value):
        try:
            if not os.path.exists(ENV_FILE):
                open(ENV_FILE, "w").close()
            set_key(ENV_FILE, key, str(value))
            os.environ[key] = str(value)
        except Exception as e:
            self.append_system_error(f"Could not save setting: {e}")

    def play_ping_sound(self):
        """Play the configured DM notification sound without blocking the UI."""
        if self.dm_sound_mode == "off":
            return
        try:
            if self.dm_sound_mode == "custom" and self.dm_sound_path and os.path.exists(self.dm_sound_path):
                path = self.dm_sound_path
            else:
                path = generate_ping_wav()
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
        win.title("Settings")
        win.geometry("520x430")
        win.resizable(False, False)
        win.configure(fg_color=BG_ROOT)
        win.transient(self)
        win.grab_set()

        title = ctk.CTkLabel(win, text="CLIENT SETTINGS", font=(FONT_MONO, 16, "bold"), text_color=FG_BRIGHT)
        title.pack(pady=(18, 12))

        # DM notification sound
        sound_frame = ctk.CTkFrame(win, fg_color=BG_PANEL, corner_radius=0)
        sound_frame.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(sound_frame, text="DM notification sound", font=(FONT_MONO, 11, "bold"),
                     text_color=FG_BRIGHT).pack(anchor="w", padx=12, pady=(10, 4))
        sound_var = ctk.StringVar(value=self.dm_sound_mode)
        sound_menu = ctk.CTkOptionMenu(
            sound_frame, variable=sound_var,
            values=["ping", "custom", "off"], width=180,
            fg_color=BTN_BG, button_color=FG_DIM, button_hover_color=BTN_HOVER,
            text_color=FG_BRIGHT, font=(FONT_MONO, 10)
        )
        sound_menu.pack(anchor="w", padx=12, pady=(0, 8))
        sound_path_label = ctk.CTkLabel(sound_frame, text=self.dm_sound_path or "No custom sound selected",
                                        font=(FONT_MONO, 9), text_color=FG_FAINT)
        sound_path_label.pack(anchor="w", padx=12, pady=(0, 8))

        def choose_sound():
            path = filedialog.askopenfilename(
                title="Choose DM notification sound",
                filetypes=[("WAV audio", "*.wav"), ("Audio files", "*.wav *.mp3 *.ogg"), ("All files", "*.*")]
            )
            if path:
                self.dm_sound_path = path
                self.dm_sound_mode = "custom"
                sound_var.set("custom")
                sound_path_label.configure(text=path)

        ctk.CTkButton(sound_frame, text="CHOOSE WAV", command=choose_sound,
                      width=120, height=28, corner_radius=0, fg_color=BTN_BG,
                      hover_color=BTN_HOVER, text_color=FG_BRIGHT,
                      font=(FONT_MONO, 10, "bold")).pack(anchor="w", padx=12, pady=(0, 10))

        # Voice devices
        voice_frame = ctk.CTkFrame(win, fg_color=BG_PANEL, corner_radius=0)
        voice_frame.pack(fill="x", padx=20, pady=8)
        ctk.CTkLabel(voice_frame, text="VOICE DEVICES", font=(FONT_MONO, 11, "bold"),
                     text_color=FG_BRIGHT).pack(anchor="w", padx=12, pady=(10, 6))

        input_names, output_names = self.get_audio_device_names()
        input_values = ["Default"] + input_names
        output_values = ["Default"] + output_names
        input_var = ctk.StringVar(value=self.voice_device_input or "Default")
        output_var = ctk.StringVar(value=self.voice_device_output or "Default")

        ctk.CTkLabel(voice_frame, text="Microphone", font=(FONT_MONO, 9), text_color=FG_DIM).pack(anchor="w", padx=12)
        input_menu = ctk.CTkOptionMenu(voice_frame, variable=input_var, values=input_values, width=440,
                                       fg_color=BTN_BG, button_color=FG_DIM, button_hover_color=BTN_HOVER,
                                       text_color=FG_BRIGHT, font=(FONT_MONO, 9))
        input_menu.pack(padx=12, pady=(2, 7))
        ctk.CTkLabel(voice_frame, text="Output / speakers", font=(FONT_MONO, 9), text_color=FG_DIM).pack(anchor="w", padx=12)
        output_menu = ctk.CTkOptionMenu(voice_frame, variable=output_var, values=output_values, width=440,
                                        fg_color=BTN_BG, button_color=FG_DIM, button_hover_color=BTN_HOVER,
                                        text_color=FG_BRIGHT, font=(FONT_MONO, 9))
        output_menu.pack(padx=12, pady=(2, 10))

        def save_and_close():
            self.dm_sound_mode = sound_var.get()
            self.voice_device_input = None if input_var.get() == "Default" else input_var.get()
            self.voice_device_output = None if output_var.get() == "Default" else output_var.get()
            self._save_setting("DM_SOUND", self.dm_sound_mode)
            self._save_setting("DM_SOUND_PATH", self.dm_sound_path)
            self._save_setting("VOICE_INPUT_DEVICE", self.voice_device_input or "")
            self._save_setting("VOICE_OUTPUT_DEVICE", self.voice_device_output or "")
            win.destroy()

        ctk.CTkButton(win, text="SAVE", command=save_and_close, width=150, height=34,
                      corner_radius=0, fg_color=FG_DIM, hover_color=BTN_ACTIVE_HOVER,
                      text_color="black", font=(FONT_MONO, 11, "bold")).pack(pady=12)

    def get_audio_device_names(self):
        if not SOUNDDEVICE_AVAILABLE:
            return [], []
        try:
            devices = sd.query_devices()
            inputs = []
            outputs = []
            for d in devices:
                name = str(d.get("name", "")).strip()
                if not name:
                    continue
                if int(d.get("max_input_channels", 0)) > 0 and name not in inputs:
                    inputs.append(name)
                if int(d.get("max_output_channels", 0)) > 0 and name not in outputs:
                    outputs.append(name)
            return inputs, outputs
        except Exception:
            return [], []

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

    def update_online_users_ui(self, user_list):
        normalized = list(dict.fromkeys(user_list))
        if normalized == self.last_user_list:
            return
        self.last_user_list = normalized
        for widget in self.user_list_frame.winfo_children():
            widget.destroy()

        my_name = self.username_entry.get().strip()
        for user in user_list:
            if user == my_name:
                continue
            avatar_img = self.get_avatar_ctkimage(user, size=(24, 24))
            btn = ctk.CTkButton(self.user_list_frame, image=avatar_img, text=f"  {user}", compound="left", font=(FONT_MONO, 12, "bold"), corner_radius=0, fg_color="transparent", text_color=FG_BRIGHT, anchor="w", height=32, hover_color=BTN_HOVER, command=lambda u=user: self.select_dm_channel(u))
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

            input_device = self.voice_device_input or None
            output_device = self.voice_device_output or None
            self.voice_input_stream = sd.RawInputStream(
                samplerate=VOICE_RATE, blocksize=VOICE_CHUNK, dtype='int16',
                channels=VOICE_CHANNELS, device=input_device, latency="low")
            self.voice_input_stream.start()
            self.voice_output_stream = sd.RawOutputStream(
                samplerate=VOICE_RATE, blocksize=VOICE_CHUNK, dtype='int16',
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
                self.voice_socket.sendto(bytes(data), (HOST, VOICE_PORT))
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
                    self.voice_output_stream.write(data)
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