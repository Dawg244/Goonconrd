import socket

host = '0.0.0.0'
port = 12145

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
    server_socket.bind((host, port))
    server_socket.listen(1)
    print(f"Server works.")

    connection, address = server_socket.accept()
    with connection:
        print(f"Connected to {address}")
        receivedbytes = connection.recv(1024)
        receivedmessage = receivedbytes.decode('utf-8')
        
        print(f"Received message: {receivedmessage}")