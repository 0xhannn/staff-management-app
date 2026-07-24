import socket
import threading
import sys

# Configuration
LISTEN_PORT = 80
TARGET_PORT = 3786
TARGET_HOST = '127.0.0.1'

def handle_client(client_socket):
    try:
        target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_socket.connect((TARGET_HOST, TARGET_PORT))
        
        def forward(src, dst):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.sendall(data)
            except:
                pass
            finally:
                src.close()
                dst.close()

        # Start two threads for bidirectional forwarding
        threading.Thread(target=forward, args=(client_socket, target_socket), daemon=True).start()
        threading.Thread(target=forward, args=(target_socket, client_socket), daemon=True).start()
    except Exception as e:
        print(f"Error handling client: {e}")
        client_socket.close()

def start_proxy():
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', LISTEN_PORT))
        server.listen(100)
        print(f"Proxy listening on port {LISTEN_PORT} -> {TARGET_PORT}")
        
        while True:
            client_sock, addr = server.accept()
            handle_client(client_sock)
    except PermissionError:
        print("Error: Permission denied. Please run as root to bind to port 80.")
        sys.exit(1)
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_proxy()
