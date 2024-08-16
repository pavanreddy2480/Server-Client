import asyncio
import struct
import time
import asyncudp
import sys
import random
import signal
import os

HELLO = 0
DATA = 1
ALIVE = 2
GOODBYE = 3
MAGIC_NUMBER = 50273  # 0xC461
VERSION = 1

# Dictionary to store active sessions (session_id: Session)
sessions = {}

# Constants for UAP message types, header fields, and other constants
HELLO = 0
DATA = 1
ALIVE = 2
GOODBYE = 3
MAGIC_NUMBER = 50273  # 0xC461
VERSION = 1

# Dictionary to store active sessions (session_id: Session)
sessions = {}

class Session:
    def __init__(self, session_id, client_address, transport):
        self.session_id = session_id
        self.client_address = client_address
        self.expected_sequence_number = 0
        self.transport = transport
        self.inactivity_timer = None
        self.queue_cli=asyncio.Queue()
        self.inactivity_timer=None
        self.data_processing_task = asyncio.create_task(self.manage_data())

    async def start_inactivity_timer(self):
        if self.inactivity_timer:
            self.inactivity_timer.cancel()
        self.inactivity_timer = asyncio.create_task(self.handle_inactivity())

    async def reset_inactivity_timer(self):
        await self.start_inactivity_timer()

    async def handle_inactivity(self):
        global sessions
        await asyncio.sleep(10)
        print(f"Session {hex(self.session_id)} timed out.")
        await self.send_goodbye()
        if self.session_id in sessions:
            del sessions[self.session_id]

    async def stop_inactivity(self):
        if self.inactivity_timer:
            self.inactivity_timer.cancel()

    async def manage_data(self):
        while True:
            await asyncio.sleep(0)
            try:
                data=await self.queue_cli.get()
                await self.handle_message(data)

            except Exception as e:
                print(f"Error processing message: {str(e)}")            

    async def handle_message(self, message):
        header, data = message[:12], message[12:]
        magic, version, command, sequence, session_id = struct.unpack("!HBBII", header)
        if magic != MAGIC_NUMBER or version != VERSION:
            return
        if command == HELLO:
            await self.handle_hello()
            self.expected_sequence_number += 1
            await self.reset_inactivity_timer()
        elif command == DATA:
            if sequence == self.expected_sequence_number:
                print(f"{hex(self.session_id)} {[self.expected_sequence_number]} {data.decode()}")
                self.expected_sequence_number += 1
                await self.send_alive()
                await self.reset_inactivity_timer()
            elif sequence > self.expected_sequence_number:
                for missed_seq in range(self.expected_sequence_number, sequence):
                    print(f"Lost packet {missed_seq}")
                print(f"{hex(self.session_id)} {[sequence]} {data.decode()}")
                self.expected_sequence_number = sequence + 1
                await self.send_alive()
                await self.reset_inactivity_timer()
            elif sequence == self.expected_sequence_number - 1:
                print(f"Duplicate packet {sequence}.")
                await self.send_alive()
            else:
                print(f"Out-of-order packet {sequence}. Closing session.")
                await self.send_goodbye()
                await self.handle_goodbye()
        elif command == GOODBYE:
            if sequence == self.expected_sequence_number:
                print(f"{self.session_id} {[self.expected_sequence_number]} GOODBYE from client")
                self.expected_sequence_number += 1
                await self.send_goodbye()
                await self.handle_goodbye()
            else:
                if sequence > self.expected_sequence_number:
                    for missed_seq in range(self.expected_sequence_number, sequence):
                        print(f"Lost packet {sequence}")
                        await self.send_goodbye()
                        await self.handle_goodbye()
                else:
                    print(f"Duplicate or out-of-order packet {sequence}. Closing session.")
                    await self.send_goodbye()
                    await self.handle_goodbye()

    async def handle_hello(self):
        await self.send_hello()
        await self.reset_inactivity_timer()

    async def handle_alive(self):
        print(f"Received ALIVE from session {self.session_id}")
        await self.reset_inactivity_timer()

    async def handle_goodbye(self):
        if self.session_id in sessions:
            del sessions[self.session_id]
        if self.inactivity_timer:
            self.inactivity_timer.cancel()
        print(f"{hex(self.session_id)} Session closed")

    async def send_hello(self):
        header = struct.pack("!HBBII", MAGIC_NUMBER, VERSION, HELLO, self.expected_sequence_number, self.session_id)
        await self.send_message(header)

    async def send_alive(self):
        header = struct.pack("!HBBII", MAGIC_NUMBER, VERSION, ALIVE, self.expected_sequence_number, self.session_id)
        await self.send_message(header)

    async def send_goodbye(self):
        header = struct.pack("!HBBII", MAGIC_NUMBER, VERSION, GOODBYE, self.expected_sequence_number, self.session_id)
        await self.send_message(header)

    async def send_message(self, header):
        self.transport.sendto(header, self.client_address)

async def mugshot(server_socket,message,client_address):
    global sessions
    header, data = message[:12], message[12:]
    magic, version, command, sequence, session_id = struct.unpack("!HBBII", header)
    if magic!=MAGIC_NUMBER or version!=VERSION:
        print("Invalid message received")
        return
    elif command==HELLO:
        session_id = random.randint(4,(1<<32)-1)
        session = Session(session_id, client_address, server_socket)
        sessions[session_id] = session
        print(f"{hex(session_id)} [0] Session created")
        await session.queue_cli.put((message))
    elif session_id in sessions:
        session=sessions[session_id]
        await session.queue_cli.put((message))
    else:
        pass    

async def signal_handler(sig, frame):
    # Send goodbye messages to all clients and exit the program
    global sessions
    # session_cpy=dict(sessions)
    for session_id in sessions:
        await sessions[session_id].send_goodbye()
    os._exit(0)

async def udp_server():
    HOST = '127.0.0.1'
    PORT = int(sys.argv[1])

    server_socket = await asyncudp.create_socket(local_addr=(HOST, PORT))
    print(f"Waiting on port {PORT}")

    while True:
        data, client_address = await server_socket.recvfrom()
        header, message_data = data[:12], data[12:]
        magic, version, command, sequence, session_id = struct.unpack("!HBBII", header)
        await mugshot(server_socket,data,client_address)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT,lambda: asyncio.create_task(signal_handler(None, None)))
    loop.run_until_complete(udp_server())
