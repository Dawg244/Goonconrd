import socket
import threading
import customtkinter as ctk

# Note: Make sure this matches your actual server machine's local IP address
HOST = '192.168.1.223'
PORT = 12145

ctk.set_appearance_mode("System")  
ctk.set_default_color_theme("blue") 

class ChatApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Local Socket Chat")
        self.geometry("500x550")
        self.resizable(False, False)

        # Username Label
        self.username_label = ctk.CTkLabel(self, text="Your Handle:", font=("Arial", 12, "bold"))
        self.username_label.pack(pady=(15, 0), padx=20, anchor="w")
        
        # Username Entry
        self.username_entry = ctk.CTkEntry(self, placeholder_text="Enter username here...", width=460)
        self.username_entry.insert(0, "User")  
        self.username_entry.pack(pady=(5, 15), padx=20)

        # Log Label
        self.log_label = ctk.CTkLabel(self, text="Message Log:", font=("Arial", 12, "bold"))
        self.log_label.pack(padx=20, anchor="w")
        
        # Chat Log
        self.chat_log = ctk.CTkTextbox(self, width=460, height=280, activate_scrollbars=True)
        self.chat_log.configure(state="disabled")  
        self.chat_log.pack(pady=(5, 15), padx=20)

        # 🟢 FIXED: Create a bottom frame to hold the input row cleanly
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.pack(fill="x", padx=20, pady=(0, 20))

        # Message Entry (Now inside bottom_frame)
        self.message_entry = ctk.CTkEntry(self.bottom_frame, placeholder_text="Type a message...", width=340)
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.message_entry.bind("<Return>", lambda event: self.start_send_thread())

        # Send Button (Now inside bottom_frame)
        self.send_button = ctk.CTkButton(self.bottom_frame, text="Send", width=100, command=self.start_send_thread)
        self.send_button.pack(side="right")

    def append_to_log(self, text):
        self.chat_log.configure(state="normal")
        self.chat_log.insert("end", text + "\n")
        self.chat_log.configure(state="disabled")
        self.chat_log.see("end")  

    def start_send_thread(self):
        message = self.message_entry.get().strip()
        username = self.username_entry.get().strip()

        if not message:
            return  

        if not username:
            self.append_to_log("[System Error]: Please enter a username handle.")
            return

        self.message_entry.delete(0, "end")
        sent_message = f"{username}: {message}"
        threading.Thread(target=self.send_socket_data, args=(sent_message,), daemon=True).start()

    def send_socket_data(self, full_message):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(4.0) 
                s.connect((HOST, PORT))
                data = full_message.encode('utf-8')
                s.sendall(data)
                self.append_to_log(full_message)
        except socket.timeout:
            self.append_to_log(f"[Error]: Connection timed out. Is the server running at {HOST}?")
        except Exception as e:
            self.append_to_log(f"[Error]: Could not connect. ({str(e)})")

if __name__ == "__main__":
    app = ChatApp()
    app.mainloop()
