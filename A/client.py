import socket
import struct
import sys
import threading
import time
import os

# Constants for UAP message types
HELLO = 0
DATA = 1
ALIVE = 2
GOODBYE = 3

# Constants for UAP header fields
MAGIC_NUMBER = 50273  # 0xC461
VERSION = 1

# UDP client configuration
SERVER_HOST = sys.argv[1]
SERVER_PORT = int(sys.argv[2])

class ClientSession:
    def __init__(self, client_socket):
        self.client_socket = client_socket
        self.session_id = 0
        self.running = True
        self.inactivity_timer = None
        self.accepting_input=True
        self.seq=0
        self.m_rec=0
        self.receive_event = threading.Event()

    def send_message(self, command, data=None):
        header = struct.pack("!HBBII", MAGIC_NUMBER, VERSION, command, self.seq, self.session_id)
        if data:
            message = header + data
        else:
            message = header
        
        self.client_socket.sendto(message, (SERVER_HOST, SERVER_PORT))
        self.seq += 1
        self.start_inactivity_timer()


    def start_inactivity_timer(self):
        if not self.inactivity_timer:
            self.inactivity_timer = threading.Timer(10, self.handle_inactivity)
            self.inactivity_timer.start()

    def stop_inactivity_timer(self):
        if self.inactivity_timer:
            self.inactivity_timer.cancel()
        self.inactivity_timer=None    

    def handle_inactivity(self):
        print("Inactivity timer expired. Client program terminated.")
        self.running = False
        self.accepting_input=False
        os._exit(0)

    def receive_message(self):
        while self.running:
            try:
                data, _ = self.client_socket.recvfrom(1024)
                
                self.m_rec+=1
                if self.inactivity_timer:
                    self.stop_inactivity_timer()
                if(self.seq>self.m_rec):
                    self.start_inactivity_timer()    
                if len(data) < 12:
                    print("Received an incomplete message.")
                    continue

                magic, version, command, sequence, session_id_received = struct.unpack("!HBBII", data[:12])

                if magic != MAGIC_NUMBER or version != VERSION:
                    print("Received an invalid response.")
                    continue

                if command == GOODBYE:
                    print("Received GOODBYE from server. Client program terminated.")
                    self.running = False
                    self.accepting_input=False
                    self.receive_event.set()
                    os._exit(0)
                    break
                elif command == ALIVE:
                    pass

            except KeyboardInterrupt:
                print("\nClient terminated.")
                self.running = False
                self.stop_inactivity_timer()
                self.receive_event.set()
                os._exit(0)
                break

    def run(self):
        self.send_message(HELLO)
        self.start_inactivity_timer()
        self.receive_first_hello()
        threading.Thread(target=self.receive_message).start()
        try:
            while self.running:
                    if self.accepting_input:
                        line = input()
                        if self.running and (line.lower() == 'q' or line.lower() == "eof"):
                            self.send_message(GOODBYE)
                            self.accepting_input=False
                            break

                        elif self.running:
                            self.send_message(DATA, line.encode())
                    else:
                        break        

        except KeyboardInterrupt:
            print("\nClient terminated.")
            self.send_message(GOODBYE)
            self.running = False
            self.accepting_input=False
            os._exit(0)

        except EOFError:
            self.send_message(GOODBYE)
            self.accepting_input=False
            self.receive_event.wait()
            # self.running=False
            # os._exit(0)
            # return

    def receive_first_hello(self):
            while self.session_id==0:
                try:
                    data, _ = self.client_socket.recvfrom(1024)
                    self.m_rec+=1
                    self.stop_inactivity_timer()
                    if len(data) < 12:
                        print("Received an incomplete message.")
                        continue

                    magic, version, command, sequence, session_id_received = struct.unpack("!HBBII", data[:12])

                    if magic != MAGIC_NUMBER or version != VERSION:
                        print("Received an invalid response.")
                        continue

                    if command == HELLO:
                        print("Received HELLO from server.")
                        self.session_id = session_id_received  # Extract session ID from HELLO message
                        self.stop_inactivity_timer()
                        break

                except KeyboardInterrupt:
                    print("\nClient terminated.")
                    self.running = False
                    os._exit(0)
                    break
def main():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
        client_session = ClientSession(client_socket)
        client_session.run()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: ./client <hostname> <portnum>")
        sys.exit(0)
    main()
