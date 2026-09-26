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

        self.title("Discord Lite")
        self.geometry("1000x600")
        self.resizable(False, False)
        self.configure(fg_color="#313338")

        self.client_socket = None
        self.current_target = "GLOBAL"  
        self.chat_history = {"GLOBAL": []} 
        self.all_rendered_widgets = []
        self.last_user_list = []

        # username -> PIL.Image, so we can regenerate CTkImages at any size
        self.default_pil_pfp = Image.new('RGB', (40, 40), color='#5865F2')
        self.user_pil_pfps = {}

        # Shared "server" icon (like a Discord server icon)
        self.server_pil_icon = None
        self.server_default_text = "🏠"

        # Voice chat state
        self.in_voice_chat = False
        self.voice_socket = None
        self.voice_input_stream = None
        self.voice_output_stream = None

        # Server Navigation Rail
        self.server_rail = ctk.CTkFrame(self, width=70, corner_radius=0, fg_color="#1E1F22")
        self.server_rail.pack(side="left", fill="y")
        
        self.server_btn = ctk.CTkButton(self.server_rail, text=self.server_default_text, width=48, height=48, corner_radius=0, fg_color="#5865F2", font=("Arial", 16, "bold"), command=self.select_global_channel)
        self.server_btn.pack(pady=12)
        self.server_btn.bind("<Double-Button-1>", lambda e: self.upload_server_icon())
        self.load_saved_server_icon()

        # Left Channels Sidebar
        self.channel_sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color="#2B2D31")
        self.channel_sidebar.pack(side="left", fill="y")

        self.server_title = ctk.CTkLabel(self.channel_sidebar, text="Main Server", font=("Arial", 14, "bold"), text_color="#F2F3F5")
        self.server_title.pack(pady=15, padx=15, anchor="w")

        self.channel_btn = ctk.CTkButton(self.channel_sidebar, text="# general-chat", font=("Arial", 12, "bold"), fg_color="#404249", text_color="#FFFFFF", height=32, corner_radius=0, command=self.select_global_channel)
        self.channel_btn.pack(fill="x", padx=10, pady=5)

        self.voice_btn = ctk.CTkButton(self.channel_sidebar, text="🎤 Join Voice", font=("Arial", 12, "bold"), fg_color="#404249", hover_color="#4E5058", text_color="#FFFFFF", height=32, corner_radius=0, command=self.toggle_voice_chat)
        self.voice_btn.pack(fill="x", padx=10, pady=(0, 5))

        # Profile Picture & Username Panel
        self.user_section = ctk.CTkFrame(self.channel_sidebar, fg_color="#232428", height=130, corner_radius=0)
        self.user_section.pack(side="bottom", fill="x")

        self.pfp_label = ctk.CTkLabel(self.user_section, text="", width=40, height=40)
        self.pfp_label.pack(pady=(12, 2))
        
        self.load_saved_profile()

        self.pfp_btn = ctk.CTkButton(self.user_section, text="Upload PFP", font=("Arial", 10), fg_color="#383A40", hover_color="#4E5058", height=20, width=90, corner_radius=0, command=self.upload_pfp)
        self.pfp_btn.pack(pady=(0, 8))

        saved_user = os.getenv("CHAT_USERNAME", "User")
        self.username_entry = ctk.CTkEntry(self.user_section, width=140, height=28, corner_radius=0, fg_color="#1E1F22", border_color="#1E1F22", text_color="#F2F3F5", font=("Arial", 11, "bold"), justify="center")
        self.username_entry.insert(0, saved_user)
        self.username_entry.pack(pady=(0, 12), padx=15)
        self.username_entry.bind("<Return>", lambda event: self.connect_and_auth())

        # Right Active User Panel
        self.member_sidebar = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color="#2B2D31")
        self.member_sidebar.pack(side="right", fill="y")

        self.member_header = ctk.CTkLabel(self.member_sidebar, text="ONLINE USERS", font=("Arial", 10, "bold"), text_color="#949BA4")
        self.member_header.pack(padx=15, pady=(15, 5), anchor="w")

        self.user_list_frame = ctk.CTkFrame(self.member_sidebar, fg_color="transparent")
        self.user_list_frame.pack(fill="both", expand=True)

        # Central Message Arena
        self.main_chat_area = ctk.CTkFrame(self, fg_color="#313338", corner_radius=0)
        self.main_chat_area.pack(side="right", fill="both", expand=True)

        self.chat_scroll = ctk.CTkScrollableFrame(self.main_chat_area, fg_color="#313338", corner_radius=0, label_text="")
        self.chat_scroll.pack(fill="both", expand=True, padx=10, pady=(15, 10))

        self.input_container = ctk.CTkFrame(self.main_chat_area, fg_color="#313338", height=60, corner_radius=0)
        self.input_container.pack(fill="x", side="bottom", padx=20, pady=(0, 20))

        self.message_entry = ctk.CTkEntry(self.input_container, placeholder_text="Message #general-chat", height=44, corner_radius=0, fg_color="#383A40", border_color="#383A40", text_color="#DBDEE1", placeholder_text_color="#949BA4", font=("Arial", 13))
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.message_entry.bind("<Return>", lambda event: self.send_message())

        self.send_button = ctk.CTkButton(self.input_container, text="Send", width=80, height=44, corner_radius=0, fg_color="#5865F2", hover_color="#4752C4", text_color="#FFFFFF", font=("Arial", 13, "bold"), command=self.send_message)
        self.send_button.pack(side="right")

        self.after(500, self.connect_and_auth)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- PFP helpers ----------

    def load_saved_profile(self):
        saved_pfp_path = os.getenv("CHAT_PFP_PATH", "")
        if saved_pfp_path and os.path.exists(saved_pfp_path):
            try:
                self.pil_pfp = Image.open(saved_pfp_path).convert('RGB').resize((40, 40), Image.Resampling.LANCZOS)
            except:
                self.pil_pfp = Image.new('RGB', (40, 40), color='#5865F2')
        else:
            self.pil_pfp = Image.new('RGB', (40, 40), color='#5865F2')
        self.ctk_pfp = ctk.CTkImage(light_image=self.pil_pfp, dark_image=self.pil_pfp, size=(40, 40))
        self.pfp_label.configure(image=self.ctk_pfp)

    def get_avatar_ctkimage(self, username, size=(40, 40)):
        pil_img = self.user_pil_pfps.get(username, self.default_pil_pfp)
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)

    def send_own_pfp(self):
        """Send our current pfp to the server so it can relay it to others."""
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

    def play_ping_sound(self):
        try:
            path = generate_ping_wav()
            if os.name == 'nt':
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif sys.platform == 'darwin':
                subprocess.Popen(['afplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(['aplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass  # no working audio backend found - fail silently

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
            self.client_socket.sendall(f"AUTH:{username}\n".encode('utf-8'))
            self.user_pil_pfps[username] = self.pil_pfp
            self.send_own_pfp()
            threading.Thread(target=self.receive_messages_loop, daemon=True).start()
        except Exception as e:
            self.append_system_error(f"Could not link to server at {HOST}: {e}")

    def receive_messages_loop(self):
        buffer = ""  # accumulates partial data between recv() calls
        while True:
            try:
                data = self.client_socket.recv(65536)
                if not data:
                    break
                buffer += data.decode('utf-8')

                # A recv() can contain 0, 1, or several complete lines.
                # Only process complete lines; keep any trailing partial
                # line in the buffer for the next recv().
                while "\n" in buffer:
                    raw_message, buffer = buffer.split("\n", 1)
                    if not raw_message:
                        continue
                    self.handle_incoming_line(raw_message)
            except:
                break

    def handle_incoming_line(self, raw_message):
        my_name = self.username_entry.get().strip()

        if raw_message.startswith("USERS:"):
            users_raw = raw_message.split(":", 1)[1]
            user_list = [u for u in users_raw.split(",") if u]
            self.after(0, self.update_online_users_ui, user_list)
        elif raw_message.startswith("GLOBAL:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                sender, text = parts[1], parts[2]
                self.after(0, self.store_and_render, "GLOBAL", sender, text)
                if sender != my_name:
                    self.play_ping_sound()
        elif raw_message.startswith("DM:"):
            parts = raw_message.split(":", 2)
            if len(parts) == 3:
                sender, text = parts[1], parts[2]
                chat_room = sender if sender != my_name else self.current_target
                self.after(0, self.store_and_render, chat_room, sender, text)
                if sender != my_name:
                    self.play_ping_sound()
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
            # Refresh anything currently on screen that might show this avatar
            self.reload_current_chat_view()
            self.update_online_users_ui(self.last_user_list)
        except Exception:
            pass  # corrupt/partial image data, just skip it

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
        
        if self.current_target == chat_room:
            self.render_single_message(sender, text)

    def update_online_users_ui(self, user_list):
        self.last_user_list = user_list
        for widget in self.user_list_frame.winfo_children():
            widget.destroy()
            
        my_name = self.username_entry.get().strip()
        for user in user_list:
            if user == my_name:
                continue
            avatar_img = self.get_avatar_ctkimage(user, size=(24, 24))
            btn = ctk.CTkButton(self.user_list_frame, image=avatar_img, text=f"  {user}", compound="left", font=("Arial", 12, "bold"), corner_radius=0, fg_color="transparent", text_color="#DBDEE1", anchor="w", height=32, hover_color="#35373C", command=lambda u=user: self.select_dm_channel(u))
            btn.pack(fill="x", padx=10, pady=2)

    def select_global_channel(self):
        self.current_target = "GLOBAL"
        self.message_entry.configure(placeholder_text="Message #general-chat")
        self.channel_btn.configure(fg_color="#404249")
        self.reload_current_chat_view()

    def select_dm_channel(self, username):
        self.current_target = username
        self.message_entry.configure(placeholder_text=f"Message @{username}")
        self.channel_btn.configure(fg_color="transparent")
        self.reload_current_chat_view()

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

        user_label = ctk.CTkLabel(content_frame, text=sender, font=("Arial", 15, "bold"), text_color="#F2F3F5")
        user_label.pack(anchor="w")

        text_label = ctk.CTkLabel(content_frame, text=text, font=("Arial", 13), text_color="#DBDEE1", justify="left", wraplength=450)
        text_label.pack(anchor="w", pady=(2, 0))

        self.after(10, self.scroll_to_bottom)

    def append_system_error(self, error_text):
        err_frame = ctk.CTkFrame(self.chat_scroll, fg_color="transparent", corner_radius=0)
        err_frame.pack(fill="x", pady=4, padx=5, anchor="w")
        self.all_rendered_widgets.append(err_frame)
        
        err_label = ctk.CTkLabel(err_frame, text=error_text, font=("Arial", 12, "italic"), text_color="#F23F43", justify="left", wraplength=500)
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
            self.voice_socket.sendto(f"REGISTER:{username}".encode('utf-8'), (HOST, VOICE_PORT))

            self.voice_input_stream = sd.RawInputStream(
                samplerate=VOICE_RATE, blocksize=VOICE_CHUNK, dtype='int16', channels=VOICE_CHANNELS)
            self.voice_input_stream.start()
            self.voice_output_stream = sd.RawOutputStream(
                samplerate=VOICE_RATE, blocksize=VOICE_CHUNK, dtype='int16', channels=VOICE_CHANNELS)
            self.voice_output_stream.start()

            self.in_voice_chat = True
            self.voice_btn.configure(text="🎤 Leave Voice", fg_color="#DA373C", hover_color="#A12D2F")

            threading.Thread(target=self.voice_send_loop, daemon=True).start()
            threading.Thread(target=self.voice_recv_loop, daemon=True).start()
        except Exception as e:
            self.append_system_error(f"Could not start voice chat: {e}")
            self.stop_voice_chat()

    def voice_send_loop(self):
        while self.in_voice_chat:
            try:
                data, overflowed = self.voice_input_stream.read(VOICE_CHUNK)
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

    def stop_voice_chat(self):
        username = self.username_entry.get().strip()
        self.in_voice_chat = False
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
            self.voice_btn.configure(text="🎤 Join Voice", fg_color="#404249", hover_color="#4E5058")
        except Exception:
            pass

    def on_close(self):
        if self.in_voice_chat:
            self.stop_voice_chat()
        self.destroy()


if __name__ == "__main__":
    app = FullDiscordClone()
    app.mainloop()