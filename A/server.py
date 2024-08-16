import socket
import struct
import threading
import time
import sys
import queue
import signal
import os
import random

HELLO = 0
DATA = 1
ALIVE = 2
GOODBYE = 3

MAGIC_NUMBER = 50273  # 0xC461
VERSION = 1
sessions = {}
lis={}

class Session:
    def __init__(self, session_id, client_address,socket):
        self.session_id = session_id
        self.client_address = client_address
        self.expected_sequence_number = 0
        self.inactivity_timer = None
        self.socket = socket
        self.message_queue=queue.Queue()
        self.thread=threading.Thread(target=self.manage_data)
        self.thread.start()

    def start_inactivity_timer(self):
        self.inactivity_timer = threading.Timer(10, self.handle_inactivity)
        self.inactivity_timer.start()

    def reset_inactivity_timer(self):
        if self.inactivity_timer:
            self.inactivity_timer.cancel()
        self.start_inactivity_timer()

    def handle_inactivity(self):
        global sessions
        print(f"Session {hex(self.session_id)} timed out.")
        self.send_goodbye()
        if (self.session_id,self.client_address) in sessions:
            del sessions[(self.session_id,self.client_address)]

    def manage_data(self):
        while True:
            try:
                session_id,client_address,data = self.message_queue.get()
                self.handle_message(data)
                
            except Exception as e:
                print(f"Error processing message: {str(e)}")

    def handle_message(self, message):
        header, data = message[:12], message[12:]
        magic, version, command, sequence, session_id = struct.unpack("!HBBII", header)
        
        if magic != MAGIC_NUMBER or version != VERSION:
            return

        if command == HELLO:
            self.handle_hello()
            self.expected_sequence_number += 1
            self.reset_inactivity_timer()
        
        elif command == DATA:
            if sequence == self.expected_sequence_number:
                print(f"{hex(self.session_id)} {[self.expected_sequence_number]} {data.decode()}")
                self.expected_sequence_number += 1
                self.send_alive()
                self.reset_inactivity_timer()

            elif sequence > self.expected_sequence_number:
                for missed_seq in range(self.expected_sequence_number, sequence):
                    print(f"Lost packet {missed_seq}")
                print(f"{hex(self.session_id)} {[sequence]} {data.decode()}")
                self.expected_sequence_number=sequence+1
                self.send_alive()
                self.reset_inactivity_timer() 

            elif sequence == self.expected_sequence_number - 1:
                print(f"Duplicate packet {sequence}.")
                self.send_alive()
            else:
                print(f"Out-of-order packet {sequence}. Closing session.")
                self.send_goodbye()
                self.handle_goodbye()
        
        elif command == GOODBYE:
            if sequence==self.expected_sequence_number:
                print(f"{hex(self.session_id)} {[self.expected_sequence_number]} GOODBYE from client")
                self.expected_sequence_number+=1
                self.send_goodbye()
                self.handle_goodbye()
            else:    
                if sequence > self.expected_sequence_number:
                    for missed_seq in range(self.expected_sequence_number, sequence):
                        print(f"Lost packet {sequence}")
                        self.send_goodbye()    
                        self.handle_goodbye()                            
                else:
                    print(f"Duplicate or out-of-order packet {sequence}. Closing session.")
                    self.send_goodbye()
                    self.handle_goodbye()


    def handle_hello(self):
        self.send_hello()
        self.reset_inactivity_timer()

    def handle_alive(self):
        print(f"Received ALIVE from session {self.session_id}")
        self.reset_inactivity_timer()

    def handle_goodbye(self):
        global sessions
        if (self.session_id,self.client_address) in sessions:
            del sessions[(self.session_id,self.client_address)]
        if self.inactivity_timer:
            self.inactivity_timer.cancel()
        print(f"{hex(self.session_id)} Session closed")

    def send_hello(self):
        header = struct.pack("!HBBII", MAGIC_NUMBER, VERSION, HELLO, self.expected_sequence_number, self.session_id)
        self.send_message(header)

    def send_alive(self):
        header = struct.pack("!HBBII", MAGIC_NUMBER, VERSION, ALIVE, self.expected_sequence_number, self.session_id)
        self.send_message(header)

    def send_goodbye(self):
        header = struct.pack("!HBBII", MAGIC_NUMBER, VERSION, GOODBYE, self.expected_sequence_number, self.session_id)
        self.send_message(header)

    def send_message(self, header):
        self.socket.sendto(header, self.client_address)


def handle_client(session_id, client_address, data,server_socket):
    if (session_id,client_address) in sessions:
        session = sessions[(session_id,client_address)]
        session.message_queue.put((session_id,client_address,data))
        
    else:
        if data[4] == HELLO:
            session_id=random.randint(4,(1<<32)-1)
            new_session = Session(session_id, client_address,server_socket)
            sessions[(session_id,client_address)] = new_session
            print(f"{hex(session_id)} [0] Session created")
            new_session.message_queue.put((session_id,client_address,data))
        else:
            print("received unknown packet")
    

def process_messages(message_queue):
    while True:
        try:
            data,client_address,server_socket = message_queue.get()
            header, message_data = data[:12], data[12:]
            magic, version, command, sequence, session_id = struct.unpack("!HBBII", header)
            handle_client(session_id,client_address,data,server_socket)
            
        except Exception as e:
            print(f"Error processing message: {str(e)}")

server_running = True

def signal_handler(sig, frame):
    global server_running
    print("\nServer shutting down...")
    sessions_copy=dict(sessions)
    server_running = False
    for session_id, client_address in sessions_copy.keys():
        session = sessions[(session_id, client_address)]
        session.send_goodbye()
        session.handle_goodbye()
    os._exit(0)    

def bucket(server_socket):
    message_queue = queue.Queue()
    message_thread = threading.Thread(target=process_messages, args=(message_queue,))
    message_thread.start()
    while True:
        data, client_address = server_socket.recvfrom(1024)
        message_queue.put((data,client_address,server_socket))

def udp_server():
    HOST = "localhost"
    PORT = int(sys.argv[1])

    signal.signal(signal.SIGINT, signal_handler)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((HOST, PORT))
    print(f"Waiting on port {PORT}")

    bucket(server_socket)

if __name__ == "__main__":
    udp_server()
