import asyncio
import socket
import struct
import sys
import asyncudp
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

client_socket = None
session_id = 0
seq = 0
running = True
accepting_input = True
inactivity_timer = None
m_rec=0
client_address=None

async def send_message( command, data=None):
    global seq,session_id,client_address,running,accepting_input,m_rec,client_socket,inactivity_timer
    header = struct.pack("!HBBII", MAGIC_NUMBER, VERSION, command, seq, session_id)
    if data:
        message = header + data
    else:
        message = header

    try:
        client_socket.sendto(message, client_address)
        seq += 1
        start_inactivity_timer()
    except OSError as e:
        print(f"Error sending message: {e}")

def start_inactivity_timer():
    global seq,session_id,client_address,running,accepting_input,m_rec,client_socket,inactivity_timer
    if not inactivity_timer:
        inactivity_timer = asyncio.create_task(handle_inactivity())

async def handle_inactivity():
    global seq,session_id,client_address,running,accepting_input,m_rec,client_socket,inactivity_timer
    await asyncio.sleep(10)
    print("Inactivity timer expired. Client program terminated.")
    running = False
    inactivity_timer = None
    accepting_input = False
    client_socket.close()

def stop_inactivity_timer():
    global seq,session_id,client_address,running,accepting_input,m_rec,client_socket,inactivity_timer
    if inactivity_timer:
        inactivity_timer.cancel()
        inactivity_timer = None

async def receive_message(data_rec):
    if data_rec==None:
        return
    global seq,session_id,client_address,running,accepting_input,m_rec,client_socket,inactivity_timer
    if running:
        data=data_rec
        m_rec+=1
        if inactivity_timer:
            stop_inactivity_timer()
        if(seq>m_rec):
            start_inactivity_timer();
        
        if len(data) < 12:
            print("Received an incomplete message.")

        magic, version, command, sequence, session_id_received = struct.unpack("!HBBII", data[:12])
        if command==HELLO:
            return

        if magic != MAGIC_NUMBER or version != VERSION:
            print("Received an invalid response.")

        if command == GOODBYE:
            print("Received GOODBYE from server. Client program terminated.")
            running = False
            accepting_input = False
            stop_inactivity_timer()
            os._exit(0)
        elif command == ALIVE:
            pass

async def ainput(prompt: str = ""):
    stream = asyncio._get_running_loop().run_in_executor(None, input, prompt)
    return await stream

async def handle_input():
    global seq,session_id,client_address,running,accepting_input,m_rec,client_socket,inactivity_timer
    try:
        if accepting_input:
            await asyncio.sleep(0)
            line = await ainput()
            if line.lower() == 'q' or line.lower() == "eof":
                await send_message(GOODBYE)
                accepting_input = False

            if accepting_input:
                await send_message(DATA, line.encode())
    
    except KeyboardInterrupt:
        print("\nClient terminated.")
        await send_message(GOODBYE)
        accepting_input=False
        os._exit(0)
            
    except EOFError:            
        await send_message(GOODBYE)
        accepting_input=False
        # os._exit(0)

def receive_first_hello(data_rec):
    global seq,session_id,client_address,running,accepting_input,m_rec,client_socket,inactivity_timer
    if session_id == 0:
        stop_inactivity_timer()
        data=data_rec
        if len(data) < 12:
            print("Received an incomplete message.")

        magic, version, command, sequence, session_id_received = struct.unpack("!HBBII", data[:12])

        if magic != MAGIC_NUMBER or version != VERSION:
            print("Received an invalid response.")

        if command == HELLO:
            print("Received HELLO from server.")
            session_id = session_id_received
            start_inactivity_timer()


async def main():
    global seq,session_id,client_address,running,accepting_input,m_rec,client_socket,inactivity_timer,SERVER_HOST,SERVER_PORT
    client_address = ('127.0.0.1', SERVER_PORT)
    try:
        client_socket = await asyncudp.create_socket(remote_addr=client_address)
    except:
        print("socket not created")
        os._exit(0)

    await send_message(HELLO)
    start_inactivity_timer()
    loop=asyncio.get_event_loop()
    loop.create_task(receive_data(client_socket))
    try:
        while True:
            try:
                await asyncio.sleep(0)
                await(handle_input())

            except ConnectionError:
                print("connection might be failed")
                os._exit(0)
    except KeyboardInterrupt:  # Catch KeyboardInterrupt exception
        print("\nClient terminated.")
        await send_message(GOODBYE)
        running = False
        accepting_input = False
        client_socket.close()
        os._exit(0)         

        
async def receive_data(client_socket):
    while True:
        try:
            await asyncio.sleep(0)
            data, client_address = await client_socket.recvfrom()
            receive_first_hello(data)
            await receive_message(data)
        except ConnectionRefusedError:
                print("Connection refused. The server might not be running or not listening.")
                os._exit(0)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Client Terminated.")
        for task in asyncio.all_tasks(loop):
            task.cancel()
        loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(), return_exceptions=True))
        loop.close()
        os._exit(0)        
    except SystemExit:
        pass
    finally:    
        loop.close()
