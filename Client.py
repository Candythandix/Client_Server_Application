from datetime import datetime
import socket
import threading
import time
import os
import struct
import random 

"""
for the audio part 
sometimes you have to manually import this
pip install pyaudio  or else it wont work 

"""
try:
    import pyaudio
    PYAUDIO_OK = True
except ImportError:
    PYAUDIO_OK = False


class Client:

    """
    Server / peer to peer connection instance variables 
    """
    udp_port = None
    peer_ip = None
    peer_port = None        # peer's UDP port (set from server notification)
    server_socket = None    # Persistent connection to server

    """ 
    
    Only 1 UDP socket and lister for the clients session , 
    it is created at login 
    """

    # ── UDP instance state (set once per login) ----------------------------------
    udp_socket   = None    # the one persistent UDP socket for the current session
    recv_buffer    = {}      # chunk reassembly: {filename: {idx: bytes}}
    recv_tot     = {}      # {filename: total_chunks}
    print_lock   = threading.Lock()


    """ UDP packet type bytes , including the live mic """
    # ── Chunked-transfer constants -----------------------------------------------
    TYPE_AUDIO = b'\x01'   # Live mike 
    TYPE_FILE    = b'\x02'   # audio / pdf file
    TYPE_IMAGE   = b'\x03'   # image

    """ Chunk headers for tranfering"""
    HDR_FMT      = "!B H I I"   # type(1)|name_len(2)|chunk_idx(4)|total(4)
    HDR_SIZE     = struct.calcsize("!B H I I")
    MAX_UDP      = 60_000

    """Audio call instance variables """
    #----Audio call------------------------------------------------------
    in_call = False
    call_lock = threading.Lock()
    audio_ok = False
    stream_in = None 
    stream_out = None
    pa = None # PYAUDIO object  access microphone 
    CHUNK = 1024
    CHANNELS = 1
    RATE = 44100

    """---Main Menu ---------------------------------------------------------"""
    @staticmethod
    def main():
        while True:
            print("\n--- Welcome ---")
            print("1) Register")
            print("2) Login")
            print("q) Quit")

            choice = input("Choice: ").strip()

            if choice == "1":
                Client.register_flow()

            elif choice == "2":
                username = Client.login_flow()
                if username:
                    Client.application_menu(username)

            elif choice.lower() == "q":
                print("Goodbye 👋")
                break
        
    @staticmethod
    def register_flow():
        username = input("Enter username: ")
        password = input("Enter password: ")
        response = Client.new_user(username, password)
        print(response)  

    @staticmethod
    def login_flow():
        username = input("Enter username: ")
        password = input("Enter password: ")

        success = Client.attempt_login(username, password)

        if success:
            # start notification listener
            threading.Thread(
                target=Client.listen_for_server_notifiations,
                args=(username,),
                daemon=True
            ).start()

            return username
        else:
            return None          

    @staticmethod
    def application_menu(username):
        while True:
            print("\n----Main Menu ----")
            print("1) Add Contact")
            print("2) Create Group")
            print("3) Send Message (Server)")
            print("4) Delete Chat")
            print("5) Delete Message")
            print("6) View Online Users")
            print("7) Start Peer-to-Peer(UDP)")
            print("8) Start Audio Call (UDP)")
            print("9) Logout")

            choice = input("Choice: ").strip()

            if choice == "1":
                Client.add_contact_menu(username)

            elif choice == "2":
                Client.create_group(username)

            elif choice == "3":
                Client.send_message(username)

            elif choice == "4":
                Client.delete_a_chat(username)

            elif choice == "5":
                Client.delete_message_menu(username)

            elif choice == "6":
                print(Client.get_online_user(username))

            elif choice == "7": 
                if Client.peer_ip:
                    Client.peer_menu(username)
                else:
                    Client.connect_to_online_user(username)

            elif choice == "8":
                Client.call_flow(username)

            elif choice == "9":
                print("Logging out...")
                if Client.server_socket:
                    Client.server_socket.close()
                    Client.server_socket = None
                break

            else:
                print("Invalid choice.")

    """----Peer to Peer Menu ----------------------------------------------"""
   
    @staticmethod
    def peer_menu(username):
        while True:
            print("\n---Peer-to-Peer Menu over UDP connection ---")
            print("1) Send Message to peer")
            print("2) Send image")
            print("3) Send audio file or pdf file")
            print("4) End Stream")
            print("5) Back to Main Menu")

            choice = input("Choice: ").strip()

            if choice == "1":
                Client.send_peer_message()

            elif choice =="2":
                path = input("  Image path: ").strip()
                Client.send_peer_image(path) 

            elif choice == "3":
                path = input("  Audio file path (.wav): ").strip()
                Client.send_audio_file_or_pdf(path)

            elif choice == "4":
                break

            else:
                print("Invalid option.")

    """-----Audio call methods------------------------------------------"""
    
    @staticmethod
    def call_flow(username:str):
        """1. show all online user 
        2. Client will pick someone to call 
        3. Client will sned a clal- request via server (TCP)
        4. Server send request to contact 
        5. request accepted/ rejected 
        6. just like UDP peer to peer if accpeted call begins. """

        online_contact = Client.get_online_user(username)
        
        if not online_contact or "No other" in online_contact or "error" in online_contact.lower():
            print("No other users are online right now.")
            return

        current_online_users = [u.strip() for u in online_contact.split(",") if u.strip()]
        # printing online users 
        print("\----Online Users ------")
        for n in current_online_users:
            print(f"   . {n}\n")

        choice = input("Enter the username to call: ").strip
        if not choice:
            return 
        if choice == username:
            print("You cant call yourself.")
        if choice not in current_online_users:
            print(f"{choice} is not currenlty online.")
            return 

        """ Establishing peer to peer connection """
        if not Client.peer_ip:
            print(f"Setting up connection to {choice}.")

            response = Client.send_connection_request(username, choice)
            if "Connection established" not in response:
                print(f"Could not establish a connection.")
                return 

            wait_time = 0 
            while Client.peer_ip is None and wait_time < 7:
                time.sleep(0.1)
                wait_time +=0.1 

            if not Client.peer_ip:
                print("Could not reach you contact - try again.")
                return 

        print(f"\n Calling {choice} ... waiting for an answer.....")

        reply = Client.send_Call_request(username, choice)
        print(f"Server response: {reply}") 


    @staticmethod
    def initiate_audio():
        # opens pyaudio stream, and sends audio data over UDP 
        # sets audio_ok form False to True 

        if not PYAUDIO_OK:
            print("AUDIO: pyaudio not installed - voice disabled")
            return 
        try:
            Client.pa = pyaudio.PyAudio()
            Client.stream_in = Client.pa.open(
                format = pyaudio.paInt16,
                channels = Client.CHANNELS,
                rate = Client.RATE, 
                input = True,
                frames_per_buffer = Client.CHUNK
            )

            Client.stream_put = Client.pa.open(
                format = pyaudio.paInt16,
                channels = Client.CHANNELS,
                rate = Client.RATE, 
                output = True,
                frames_per_buffer = Client.CHUNK
            )

            Client.audio_ok = True
            print("AUDIO: Audio device ready  ")
        except OSError as e:
            print (f"AUDIO: No audio device {e} - voice disables")
            Client.audio_ok = False

    @staticmethod
    def begin_call():
        # Audio has began on both clients sides 

        # Initialise audio fresh for each call
        Client.initiate_audio()

        with Client.call_lock:
            Client.in_call = True

        print("\n" + "-" * 50)
        if Client._audio_ok:
            print(" Audio call is connected  —  type q + Enter to hang up")
            threading.Thread(target = Client.mic_sender, daemon=True).start()
        else:
            print(" Call is Connected (no audio device — voice disabled)")
            print("  Type q + Enter to hang up.")
        print("-" * 52 + "\n")

        # Block the calling thread until the user hangs up or peer ends call
        while Client.in_call:
            try:
                cmd = input("").strip().lower()
            except EOFError:
                break
            if cmd == "q":
                break

        # Mark call ended
        with Client.call_lock:
            Client.in_call = False

        # Signal the peer over UDP
        if Client.udp_socket and Client.peer_ip and Client.peer_port:
            try:
                Client.udp_socket.sendto(b"END_CALL", (Client.peer_ip, Client.peer_port))
            except Exception:
                pass

        print(" Call has ended.\n")
        Client.cleanup_audio()

    @staticmethod
    def mic_sender():
        """Background thread: reads mic  then -   TYPE_AUDIO UDP packets and then - peer."""

        while Client.in_call:
            try:
                frame = Client.stream_in.read(Client.CHUNK, exception_on_overflow = False)
                Client._udp_socket.sendto(
                    Client.TYPE_AUDIO + frame,
                    (Client.peer_ip, Client.peer_port)
                )
            except Exception:
                break


    @staticmethod
    def cleanup_audio():
        """Close PyAudio when the call has ended """
        try:
            if Client.stream_in:
                Client.stream_in.stop_stream()
                Client.stream_in.close()
                Client.stream_in = None
            if Client.stream_out:
                Client.stream_out.stop_stream()
                Client.stream_out.close()
                Client.stream_out = None
            if Client.pa:
                Client.pa.terminate()
                Client.pa = None
        except Exception:
            pass
        Client._audio_ok = False
    

    @staticmethod
    def attempt_login(Username, Password):

        Client.udp_port = random.randint(20000, 30000)

        currentTime = datetime.now()
        last_update_time = currentTime.strftime("%Y-%m-%d %H:%M:%S")

        response = Client.login(
            Username,
            Password,
            last_update_time,
            Client.udp_port
        )

        for x in range(3):
            if "successfully logged in" in response:
                # Create and store the persistent UDP socket
                Client.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                Client.udp_socket.bind(("", Client.udp_port))
                print(f"[UDP] Listening on port {Client.udp_port}")

                # Start the unified UDP receiver (handles messages, files, images)
                threading.Thread(
                    target=Client.udp_receiver_loop,
                    daemon=True
                ).start()
                return True
            
            if x < 2:
                print("Login failed. Try again.")
                Username = input("Username: ")
                Password = input("Password: ")
                response = Client.login(
                    Username,
                    Password,
                    last_update_time,
                    Client.udp_port
                )
        
        return False

    @staticmethod
    def attempt_new_user_creation(Username:str, Password:str):
        login_successful = False
        response=Client.new_user(Username,Password)
            
        if response=="Error":
            print("Account creation failed.")
            login_successful = False
            return login_successful
            
        else:
            print("Account created successfully.")
            print("Add contact or Group. ")
            ContactOrGroup = input("Menu \n 1) Connect to a Contact .\n 2) Create a group chat \n Choice: ")

            notification_thread = threading.Thread(
                target= Client.listen_for_server_notifiations,
                args=(Username,),
                daemon=True
            )
            notification_thread.start()
            time.sleep(0.5)  # Give thread time to start
            login_successful = True 
            return login_successful

    """Creating a group Methods """
    
    @staticmethod
    def create_group(Username:str):
        name_of_group = input("Enter the name of the group you will create: ")

        get_all_users = Client.get_all_users(Username)
        print("Below are list of all users in the system: ")
        print(get_all_users)

        numberOfUsers= int(input("Enter the number of users you want to add in the group: "))
        group=[]
        
        for i in range(numberOfUsers):
            user = input("Enter the user's Username: ")
            group.append(user)
        
        response=Client.create(Username,name_of_group,group)
        print(response)

        """
        if response =="OK":
            print("Group  create successfully.")
            
        elif response =="Does Not Exist":
            print("Could not find one or more users.")
            print("Try again.") 
        else:
            print("Error creating group.") 
        """
        



    """Connecting to peers or groups methods """
    @staticmethod
    def add_contact_menu(Username: str):
        contact = Client.get_online_user(Username) # server will give all users in the sytem 

        if contact == None:
            online_users_list = ""
        else:              
            online_users_list = contact.split(",")
        # server sends back a lsit of online users 
        print("List of online users: ")
        for n in online_users_list: # prints out all the users,
            print(n)
        
        user = input("Enter the user's Username: ")

        response=Client.add_contact(Username,user)
        
        print(response)
       

    @staticmethod
    def connect_to_online_user(Username:str):
        """ What happens here:
        1, display list of online users , from server
        2. user selects a contact
        3. Connection request to srever 
        4. Wait for a respons 
        5. if accepted stat a UDP peer to Peer interaction ."""

        try:
            online_users_response = Client.get_online_user(Username)
            
            if online_users_response is None or online_users_response == "":
                print("No online users available to connect to.")
                return

            users = online_users_response.split(",")
            online_users_list = [u.strip() for u in users if u.strip()]
            
            if not online_users_list:
                print("No other users are online.")
                return
        

            print("\n" + "-" * 50) # seperator
            print("All available users online:")
            print("-" * 50)
            for user in online_users_list:
                print(f"  • {user}")

            choose_contact = input("Enter the username to connect to : ").strip()

            if choose_contact == Username:
                print("You cannot connect to yourself ")
                return
            
            if choose_contact not in online_users_list:
                print(f"User {choose_contact} is not online.")
                return 
            #send request to connect to server 
            print(f"Sending connection request to {choose_contact}...")

            response = Client.send_connection_request(Username, choose_contact)

            if "Connection established" in response:
                print("Waiting for peer response...")
                # Wait for notification to arrive and set peer_ip
                wait_time = 0
                while Client.peer_ip is None and wait_time < 5:
                    time.sleep(0.1)
                    wait_time += 0.1
                
                if Client.peer_ip:
                    print(f"\n✓ Connection established with {choose_contact}!")
                    print(f"  Peer IP: {Client.peer_ip}, Port: {Client.peer_port}")
                    # Now enter peer menu
                    Client.peer_menu(Username)
                else:
                    print("Connection failed - peer did not respond in time")
            else:
                print(response)

        except Exception as e:
            print(f"Error connecting to user: {e}")

            
    

  

    # -------------------------------- Unified UDP receiver--------------------------------

    @staticmethod
    def start_udp_listener(udp_port: int):
        pass  # replaced by udp_receiver_loop — kept so nothing breaks

    @staticmethod
    def udp_receiver_loop():
        """Single background thread — handles plain messages, files, images.
            for Files and images ,it reassemble and saves them 
            For Audio it will play through speakers (during the call )
            For test it will prin out the message in the chat 
        """
        while True:
            try:
                raw, addr = Client.udp_socket.recvfrom(Client.MAX_UDP + 512)
            except Exception as e:
                print(f"[UDP] Receive error: {e}")
                break

            if not raw:
                continue

            ptype = raw[:1]
            
            """ --------Live audio --------------------------------------"""
            if ptype == Client.TYPE_AUDIO:
                if Client.in_call and Client.stream_out:
                    try:
                        Client.stream_out.write(raw[1:])
                    except Exception:
                        pass
                continue

            """ ----Plain messages , chunked files and images---------------------- """

            # ── Plain text message (legacy — no header, just raw text) --------
            if ptype not in (Client.TYPE_FILE, Client.TYPE_IMAGE):
                try:
                    message = raw.decode()
                    sender_ip, sender_port = addr

                    if message == "END_STREAM":
                        print("\n[UDP] Peer to Peer ended the connection.")
                        Client.peer_ip   = None
                        Client.peer_port = None

                    elif message == "END_CALL":
                        # Peer hung up
                        with Client._call_lock:
                            Client._in_call = False
                        Client.notify("\n Peer has ended the call.\n> ", end="")
                        Client.cleanup_audio()

                    else:
                        Client.notify(f"\n[UDP MESSAGE from {sender_ip}:{sender_port}]\n{message}\n> ", end="")
                except Exception:
                    pass
                continue

            # --- Chunked file or image ----------------------------------------
            parsed = Client.parse_packet(raw)
            if parsed is None:
                continue

            ptype_b, name, idx, total, payload = parsed

            if name not in Client.recv_buffer:
                Client.recv_buffer[name] = {}
                Client.recv_tot[name] = total
            Client.recv_buffer[name][idx] = payload

            if len(Client.recv_buffer[name]) == total:
                ordered = b"".join(Client.recv_buffer[name][i] for i in range(total))
                del Client.recv_buffer[name], Client.recv_tot[name]

                out   = f"received_{name}"
                label = "FILE" if ptype_b == Client.TYPE_FILE else "IMAGE"
                with open(out, "wb") as f:
                    f.write(ordered)
                Client.notify(f"\n  [{label}] Received '{name}' → saved as '{out}'\n> ", end="")

    # -------------------------------------Packet helper methods  -------------------------------------

    @staticmethod
    def build_packet(ptype: bytes, name: str, idx: int, total: int, data: bytes) -> bytes:
        nb = name.encode()
        return struct.pack(Client.HDR_FMT, ptype[0], len(nb), idx, total) + nb + data

    @staticmethod
    def parse_packet(raw: bytes):
        try:
            ptype_int, name_len, idx, total = struct.unpack_from(Client.HDR_FMT, raw)
            off     = Client.HDR_SIZE
            name    = raw[off: off + name_len].decode()
            payload = raw[off + name_len:]
            return bytes([ptype_int]), name, idx, total, payload
        except Exception:
            return None

    @staticmethod
    def notify(msg: str, end: str = "\n"):
        with Client.print_lock:
            print(msg, end=end, flush=True)

    # ------------------------------------- Send helpers -------------------------------------

    @staticmethod
    def send_chunks_static(ptype: bytes, filepath: str, label: str):
        """Send any file in chunks over UDP to the current peer."""
        if not Client.udp_socket:
            print("  Error : No active UDP socket.")
            return
        if not Client.peer_ip or not Client.peer_port:
            print("  Error: No active peer connection.")
            return
        if not os.path.isfile(filepath):
            print(f"  {label}: File not found: {filepath}")
            return

        name = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            data = f.read()

        ps     = Client.MAX_UDP - Client.HDR_SIZE - len(name.encode())
        chunks = [data[i: i + ps] for i in range(0, len(data), ps)]
        total  = len(chunks)

        print(f"  [{label}] Sending '{name}' — {total} chunk(s) to {Client.peer_ip}:{Client.peer_port} …")
        for idx, chunk in enumerate(chunks):
            pkt = Client.build_packet(ptype, name, idx, total, chunk)
            Client.udp_socket.sendto(pkt, (Client.peer_ip, Client.peer_port))
            time.sleep(0.002)
        print(f"  [{label}] '{name}' sent ✓")

    @staticmethod
    def send_peer_image(path: str):
        threading.Thread(
            target=Client.send_chunks_static,
            args=(Client.TYPE_IMAGE, path, "IMAGE"),
            daemon=True
        ).start()

    @staticmethod
    def send_audio_file_or_pdf(path: str):
        threading.Thread(
            target = Client.send_chunks_static,
            args=(Client.TYPE_FILE, path, "FILE"),
            daemon=True
        ).start()


    # send_peer_message uses the shared udp_socket
    @staticmethod
    def send_peer_message():
        if not Client.peer_ip:
            print("No active peer connection.")
            return
        msg = input("Enter message: ")
        Client.udp_socket.sendto(msg.encode(), (Client.peer_ip, Client.peer_port))


    @staticmethod
    def listen_for_server_notifiations(username:str):

        serverName = socket.gethostname()
        serverPort = 12000

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as notification_socket:
                notification_socket.connect((serverName, serverPort))

                #rejister listener
                notification_socket.sendall(f"NotificationListenerRequest,{username}".encode())
                print(f"Notification listener started for {username}")

                while True:
                    try:
                        notification = notification_socket.recv(1024).decode()
                        if not notification:
                            break
                        
                        #connection accepted
                        if "ConnectionAccepted" in notification:
                            parts = notification.split(",")
                            Client.peer_ip = parts[1]
                            Client.peer_port = int(parts[2])

                            print("\nPeer connection ready.")
                            print("You can now use option 7 again to send UDP messages.")

                        #connection confirmed
                        elif "ConnectionConfirmed" in notification:
                            parts = notification.split(",")
                            Client.peer_ip = parts[1] if len(parts) > 1 else ""
                            Client.peer_port = int(parts[2]) if len(parts) > 2 else 13000

                            print(f"\n{'-' * 50}")
                            print("Connection confirmed")    
                            print(f"\n{'-' * 50}")     
                            print(f"  Connected to peer:{Client.peer_ip}:{Client.peer_port}")
                            print(f"   Starting UDP connection")
                            print(f"\n{'-' * 50}")

                            #start up listened here 
                            print("> ", end="", flush=True)


                            """Now for the call requests """
                            # incomming call 
  
                        elif notification.startswith("IncomingCall,"):
                            caller = notification.split(",")[1].strip()
                            # Handle in a separate thread so we don't block notifications
                            threading.Thread(
                                target = Client.handle_incoming_call,
                                args = (caller, username),
                                daemon = True
                            ).start()

                        # Peer has accepted the ccall request
                        elif notification.startswith("CallAccepted,"):
                            user_calling = notification.split(",")[1].strip()
                            Client.notify(f"\n  {user_calling} has accepted your call!\n")
                            threading.Thread(
                                target = Client.begin_call,
                                daemon = True
                            ).start()


                        #   Contact hass rejected call request 
                        elif notification.startswith("CallRejected,"):
                            user_calling = notification.split(",")[1].strip()
                            Client.notify(f"\n {user_calling} has declined your call.\n> ", end="")


                            """ Server relayed chat messages """
                        elif notification.startswith("NewMessage,"):
                            parts = notification.split(",")
                            sender  = parts[1] if len(parts) > 1 else "?"
                            body    = parts[2] if len(parts) > 2 else ""
                            ts      = parts[3] if len(parts) > 3 else ""
                            Client.notify(
                                f"\n  [{ts}] {sender}: {body}\n> ", end=""
                            )


                    except Exception as e:
                        print(f"Error in notfication handler: {e}")
                        break

        except Exception as e:
            print(f"Notifiation listener error: {e}")



    @staticmethod
    def send_message(Username:str):
        """Message flow methods"""
        ContactOrGroup=input("Enter a name of contact or Group: ")
        destination = input("Enter is the contact is a group or user by True - Group, False - contact. Capatalize the first letter: \n ")
        messageType=input("Enter the message type: \n")
        message=input("Enter your message: \n")
        TimeSent = datetime.now()
        message_time = TimeSent.strftime("%Y-%m-%d %H:%M:%S")
        Chunknum=512


        response = Client.send(Username,messageType,ContactOrGroup,Chunknum,message_time,message,destination)

        print(response)
        
    @staticmethod
    def delete_message_menu(Username:str):
        ContactOrGroup = input("Enter a name of contact or Group: ")
        DeleteForWho = input("Delete for everyone or me?(me /everyone): ")

        messageID_list = Client.get_message_ID(Username,ContactOrGroup) # a list of messages
        if "No messages found" in messageID_list:
            print(messageID_list)
            return 
        
        parts = messageID_list.split(",")
        for p in parts: # prints message ID list with message and user chooses which message to delete
            print(p)
        
        choice_ID = input("Choose the message ID you want to delete.")

        while DeleteForWho not in["me","everyone"]:
            print("Invalid choice")
            DeleteForWho= input("Delete for everyone or me(Enter me / everyone): ")
            
        response = Client.delete_message(Username,ContactOrGroup,DeleteForWho,choice_ID)
        print(response)

     
               
    @staticmethod
    def delete_a_chat(Username:str):
        ContactOrGroup = input("Enter a name of contact or Group: ")
        response=Client.delete_chat(Username,ContactOrGroup)

        print(response)
       

    @staticmethod
    def send_to_server(message: str, use_persistent=False):
        serverName = socket.gethostname()
        serverPort = 12000

        try:
            # Use persistent connection if available and requested
            if use_persistent and Client.server_socket:
                Client.server_socket.sendall(message.encode())
                server_reply = Client.server_socket.recv(1024).decode().strip()
                return server_reply
            else:
                # Create new socket for one-off requests
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as clientSocket:
                    clientSocket.connect((serverName, serverPort))
                    clientSocket.sendall(message.encode())
                    server_reply = clientSocket.recv(1024).decode().strip()
                    return server_reply
            
        except ConnectionRefusedError:
            print("Could not connect to the server, is this the correct port")
        except Exception as e:
            print("An error occurred:", e)

    @staticmethod
    def handle_incoming_call(caller: str, my_username: str):
        """Runs in its own thread so the notification loop stays unblocked."""

        Client.notify(
            f"\n{'-'* 50}"
            f"\n  Incoming call from  {caller}"
            f"\n{'-'* 50}", end="\n"
        )
        answer = input("  Do you Accept this call? (yes / no): ").strip().lower()

        if answer in ("yes", "y"):
            Client.send_call_response(caller, "ACCEPTED")
            Client.begin_call()                             # blocks until call ends
        else:
            Client.send_call_response(caller, "REJECTED")
            print("  Call has been rejected.\n> ", end="", flush=True)

    @staticmethod
    def login(username:str, password:str, time:str, udp_port: int):
        message = f"LoginRequest,{username},{password},{time},{udp_port}"
        
        serverName = socket.gethostname()
        serverPort = 12000
        
        try:
            # Create persistent connection
            Client.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            Client.server_socket.connect((serverName, serverPort))
            Client.server_socket.sendall(message.encode())
            server_reply = Client.server_socket.recv(1024).decode().strip()
            return server_reply
        except Exception as e:
            print(f"Login connection error: {e}")
            return f"Error: {e}"
    
    @staticmethod
    def add_contact(username:str, contact:str):
        message = f"AddContactRequest,{username},{contact}"
        return Client.send_to_server(message, use_persistent=True)
    
    @staticmethod
    def new_user(username:str , password:str):
        currentTime = datetime.now()
        lastUpdate = currentTime.strftime("%Y-%m-%d %H:%M:%S")

        message = f"NewUserRequest,{username},{password},{lastUpdate}"

        return Client.send_to_server(message)

    # updating a message in a chat
    @staticmethod
    def update_message(username:str, message_ID:str, message_body:str, group_chat_name:str):
        # last_update_time was in the parameter, removed it 
        currentTime = datetime.now()
        current_Update_time = currentTime.strftime("%Y-%m-%d %H:%M:%S")

        message = f"UpdateMessageRequest,{username},{message_ID},{message_body},{group_chat_name},{current_Update_time}"
        return Client.send_to_server(message, use_persistent=True)
    
    @staticmethod
    def create(username: str, group_name:str,contacts_list:list ): # creating a group
        
        message = f"CreateGroupRequest,{username},{group_name},{','.join(contacts_list)}"

        return Client.send_to_server(message, use_persistent=True)
    
    @staticmethod
    def delete_chat(username:str, group_chat_name:str):
         
         message = f"DeleteChatRequest,{username},{group_chat_name}"

         return Client.send_to_server(message, use_persistent=True)
    
    @staticmethod
    def delete_message(username:str, contact_or_group:str, delete_for:str, message_id:str):
        message = f"DeleteMessageRequest,{username},{contact_or_group},{delete_for},{message_id}"
        return Client.send_to_server(message, use_persistent=True)
    
    @staticmethod
    def get_message_ID(username:str, contact_or_group:str):
        message = f"GetMessageIDRequest,{username},{contact_or_group}"
        return Client.send_to_server(message, use_persistent=True)

    @staticmethod
    def get_all_users(username: str): # get all user usernames
        message = f"GetAllUsersRequest,{username}"
        return Client.send_to_server(message, use_persistent=True) 

    @staticmethod
    def send(username: str, message_type:str, contact_or_group : str, chunk_num:str, message_time:str,body:str, destination: str):
        message = f"SendMessageRequest,{username},{message_type},{contact_or_group},{chunk_num},{message_time},{body},{destination}"

        return Client.send_to_server(message, use_persistent=True)
    
    @staticmethod
    def get_online_user(username: str):

        message = f"GetOnlineUserRequest,{username}"
        return Client.send_to_server(message, use_persistent=True)

    @staticmethod
    def send_connection_request(username: str, contact: str):
        # sending the connection request to the serv er , server will send this to contact

        message = f"ConnectRequest_Request,{username},{contact}"
        return Client.send_to_server(message, use_persistent=True) 

    def send_call_request(caller: str, contact: str):
        """Tell the server to forward a CallRequest to the contect choosen by the client/user ."""
        message = f"CallRequest,{caller},{contact}"
        return Client.send_to_server(message, use_persistent=True)  

    @staticmethod
    def send_call_response(caller: str, response: str):
        """
        Tells the server the call whether the call was ACCEPTED or REJECTED.
        response is 'ACCEPTED' or 'REJECTED'.
        """
        message = f"CallResponse,{caller},{response}"
        return Client.send_to_server(message, use_persistent=True)


if __name__ == "__main__":
    Client.main()
  
    
    











