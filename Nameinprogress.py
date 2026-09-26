import socket

host = "192.168.1.50"
port = 12145

print(("As of now, the project has no UI (yet) but I am working on it."))
username = input("Please put in your handle: ")

while True:
    message = input()
    sentmessage = str(username) + ": " + str(message)
    print(sentmessage)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        data = sentmessage.encode('utf-8')
        s.sendall(data)
