from socket import *
import json
import threading
from datetime import datetime



online_users = {}
online_users_lock = threading.Lock()
#pending_peer_to_peer_connections = {} # {requesting_client}:{}}
#connected_peer_to_peer_connections = {} # {(client1, client2):{} }etc:
class Server:
    

    def start_server():
         serverPort = 12000
         serverSocket = socket(AF_INET, SOCK_STREAM)
         serverSocket.bind(('', serverPort))
         serverSocket.listen(5)

         print("Server is listening")

         while True:
              connectionSocket, addr = serverSocket.accept()
              print(f"New connection from {addr}")

              threading.Thread(
                   target = Server.handle_client,
                   args = (connectionSocket,),
                  daemon = True
              ).start()


    def handle_client(connectionSocket):
        username = None
        is_notification_socket = False

        try:
            while True:
                request = connectionSocket.recv(1024).decode()

                if not request:
                    break

                parts = request.strip().split(",")
                request_type = parts[0]
                request_list = parts[1:]

                if request_type == "LoginRequest":
                    reply = Server.login(request_list, connectionSocket)
                    username = request_list[0]

                elif request_type == "NewUserRequest":
                    reply = Server.new_user(request_list, connectionSocket)

                elif request_type == "AddContactRequest":
                    reply = Server.add_contact(request_list, connectionSocket)

                elif request_type == "UpdateMessageRequest":
                    reply = Server.update_message(request_list, connectionSocket)

                elif request_type == "CreateGroupRequest":
                    reply = Server.create_group(request_list, connectionSocket)

                elif request_type == "DeleteChatRequest":
                    reply = Server.delete_chat(request_list, connectionSocket)

                elif request_type == "DeleteMessageRequest":
                    reply = Server.delete_message(request_list, connectionSocket)

                elif request_type == "GetAllUsersRequest":
                    reply = Server.get_all_users(request_list[0],connectionSocket)

                elif request_type == "SendMessageRequest":
                    reply = Server.send_message(request_list, connectionSocket)

                elif request_type == "GetOnlineUserRequest":
                    reply = Server.get_online_user(request_list, connectionSocket)

                elif request_type == "ConnectRequest_Request":
                    reply = Server.connect_to_user(request_list, connectionSocket)

                elif request_type == "GetMessageIDRequest":
                    reply = Server.get_message_ID(request_list, connectionSocket)   

                elif request_type == "CallRequest": # new method added 
                    reply = Server.handle_call_request(request_list)

                elif request_type == "CallResponse": # new method added 
                    reply = Server.handle_call_response(request_list) 

                elif request_type == "NotificationListenerRequest":
                    listener_username = request_list[0]
                    is_notification_socket = True

                    with online_users_lock:
                        if listener_username in online_users:
                            online_users[listener_username]["notification_socket"] = connectionSocket

                    # Keep this socket open indefinitely for notifications
                    # Set a timeout so it doesn't block forever
                    connectionSocket.settimeout(300)  # 5 minute timeout
                    try:
                        while True:
                            connectionSocket.recv(1024)  # Just keep it alive
                    except Exception as e:
                        pass
                    return  

                else:
                    reply = "Unknown request"

                connectionSocket.sendall(reply.encode())

        except Exception as e:
            print(f"Error: {e}")

        finally:
            # Only close and remove user if this isn't a notification socket
            if not is_notification_socket and username and username in online_users:
                with online_users_lock:
                    del online_users[username]
                    print(f"{username} went offline")

            connectionSocket.close()

    """----Adding the call handle method sat the top for visibility------------ """

    @staticmethod
    def handle_call_request(request_list: list) -> str:
        """
        Client sends:  CallRequest, <caller> , <target>
        Server forwards  IncomingCall, <caller>  to target's notification socket.
        """
        if len(request_list) < 2:
            return "CallRequest error: missing fields"

        caller = request_list[0]
        target = request_list[1]

        with online_users_lock:
            target_info = online_users.get(target)

        if not target_info:
            return f"User {target} is not online."

        target_notify = target_info.get("notification_socket")
        if not target_notify:
            return f"User {target} has no notification channel."

        try:
            target_notify.sendall(f"IncomingCall,{caller}".encode())
            print(f"SERVER: Call request from: {caller} → {target}")
            return "Call request sent."
        except Exception as e:
            return f"Could not reach {target}: {e}"

    @staticmethod
    def handle_call_response(request_list: list) -> str:
        """
        User calling  sends:  CallResponse, <caller>, ACCEPTED   or   CallResponse, <caller>, REJECTED
        Server forwards  CallAccepted, <user calling >  or  CallRejected, <user calling>  to the caller.

        The callee's username is deduced from the notification socket lookup — but since
        we don't have it in request_list we pass it as:  CallResponse, <caller>, <response>, <user calling >
        """
        if len(request_list) < 3:
            return "CallResponse error: missing fields"

        caller   = request_list[0]
        response = request_list[1]          # "ACCEPTED" or "REJECTED"
        # callee is optional 4th field — used only for the notification text
        callee   = request_list[2] if len(request_list) > 2 else "peer"

        with online_users_lock:
            caller_info = online_users.get(caller)

        if not caller_info:
            return f"Caller {caller} is no longer online."

        caller_notif = caller_info.get("notification_socket")
        if not caller_notif:
            return f"Caller {caller} has no notification channel."

        try:
            if response == "ACCEPTED":
                caller_notif.sendall(f"CallAccepted,{callee}".encode())
                print(f"SERVER: {callee} accepted call from {caller}")
                return "CallAccepted forwarded."
            else:
                caller_notif.sendall(f"CallRejected,{callee}".encode())
                print(f"SERVER: {callee} has been rejected call from {caller}")
                return "CallRejected forwarded."
        except Exception as e:
            return f"Could not reach caller {caller}: {e}"

    """---Previous TCP methods--------------------------------------------"""
    
    @staticmethod
    def login(request_list : list, connectionSocket):
       

        username = request_list[0]
        password = request_list[1]
        time = request_list[2]
        udp_port = request_list[3]

        try:
            #load file 
            with open('Users.json') as file:
                data = json.load(file)

            user_found = False

            for user in data["Users"]:
                if user["Username"] == username and user["Password"] == password:
                    user["lastUpdate"] = time
                    user_found = True
                    break
            
            if user_found:
                with open('Users.json', 'w') as file:
                    json.dump(data, file, indent = 4)

                ip_address = connectionSocket.getpeername()[0]

                with online_users_lock:
                    online_users[username] = {
                        "socket": connectionSocket,
                        "ip": ip_address,
                        "udp_port": int(udp_port)
                        }
                
                return f"User {username} has successfully logged in."
            else:
                return "Username not found in database."
        except FileNotFoundError:
            return "error Users.json file not found."
        except Exception as e :
            return f"An error has occured: {e}."

    @staticmethod
    def new_user(request_list : list, connectionSocket):
        username = request_list[0]
        password = request_list[1]
        time = request_list[2]

        # search for username , if not there make new user 
        try:
            #load file 
            with open('Users.json') as file:
                data = json.load(file)

            for user in data["Users"]:
                if user["Username"] == username :
                   return "Username already found in database."
            
            new_entry = {
                "Username": username,
                "Password": password,
                "DateOfCreation": time,
                "lastUpdate": time,
                "NumberOfContacts": 0,
                "ContactList": []

            }

            data["Users"].append(new_entry)
            
            with open('Users.json', 'w') as file:
                    json.dump(data, file, indent = 4)

            return f"User {username} has successfully signed in."
            
        except FileNotFoundError:
            return "error Users.json file not found."
        except Exception as e :
            return f"An error has occured: {e}."

    @staticmethod
    def add_contact(request_list : list, connectionSocket):
        username = request_list[0]
        contact = request_list[1]
        savedname = contact # for now for simplicity we will keep them the sam e
        try:
            with open('Users.json') as file:
                    data = json.load(file)
            user_found = False
            for user in data["Users"]:
                    if user["Username"] == username :

                        all_users = [u["Username"] for u in data["Users"]]

                        if contact not in all_users:
                            return "Contact does not exist."

                        new_contact = {
                             "Username": contact,
                             "SavedName": savedname

                        }
                        user["ContactList"].append(new_contact)
                        user["NumberOfContacts"] = len(user["ContactList"])
                        user_found = True
                        break


            if user_found:
                with open('Users.json', 'w') as file:
                            json.dump(data, file, indent = 4)
                return f"Contact {contact} successfully added to contact list for user {username}"
            else: 
                return "Does Not Exist"
            
        except FileNotFoundError:
                return "error Users.json file not found."
        except Exception as e :
            return f"An error has occured: {e}."

    @staticmethod
    def update_message(request_list : list, connectionSocket):
        # get last update time form server #time = request_list[1]
        username = request_list[0]
        message_ID = request_list[1]
        message_body = request_list[2]
        group_chat_name = request_list[3]
        current_update_time = request_list[4]

        # going to fix this 
        try:
            with open('Users.json') as file:
                    data = json.load(file)

            message_updated = False

            for m in data["Messages"]:
                    if m["message_ID"] == message_ID and m["destination_chat_or_groupchat"] == group_chat_name :
                        m["body"] = message_body
                        m["time_sent"] = current_update_time
                        
                        message_updated = True
                        break


            if message_updated:
                with open('Users.json', 'w') as file:
                            json.dump(data, file, indent = 4)
                return f"Message updated at {current_update_time}"
            else: 
                return "Message ID Does Not Exist"
        except FileNotFoundError:
                return "error Users.json file not found."
        except Exception as e :
            return f"An error has occured: {e}."
    
    @staticmethod
    def create_group(request_list : list, connectionSocket):
        username = request_list[0]
        group_name = request_list[1]

        contacts= request_list[2:]
       
        contact_in_database = []
        contact_not_added = []

        try:
            with open('Users.json') as file:
                    data = json.load(file)

            group_chat_made = False

            all_db_user = [user["Username"] for user in data["Users"]]
            for x in contacts:# checking if the contact s in the database
                if x in all_db_user:
                    contact_in_database.append(x)
                else: 
                    contact_not_added.append(x)
            group_id = str(len(data["Groups"])+ 1)

            if len(contact_in_database) == 0:
                group_chat_made = False
            else:
                contact_in_database.append(username)  # add origonal user 
                new_entry = {
                    "group_name": group_name,
                    "members": contact_in_database,
                    "group_ID": group_id
                       
                }

                data["Groups"].append(new_entry)
                separator = ", "
                users_not_in_database  = separator.join(contact_not_added)
                group_chat_made = True

            if group_chat_made:
                with open('Users.json', 'w') as file:
                                json.dump(data, file, indent = 4)
                currentTime = datetime.now()
                last_update_time = currentTime.strftime("%Y-%m-%d %H:%M:%S")

                if len(contact_not_added) == 0: 
                    return f"Group chat {group_name} created at {last_update_time} "
                else:
                     return f"Group chat {group_name} created at {last_update_time} and the contact not added are {users_not_in_database} due to them not being in the database.  "
                
            else: 
                return "No valid memebers to create group "
        except FileNotFoundError:
                return "error Users.json file not found."
        except Exception as e :
            return f"An error has occured: {e}."
        
    
    @staticmethod
    def connect_to_user(request_list, connectionSocket):

        requester = request_list[0]
        target = request_list[1]

        #read data with lock 
        with online_users_lock:
            requester_info = online_users.get(requester)
            target_info = online_users.get(target)

        if not requester_info or not target_info:
            return "User not online."

        # get lock when needed 
        requester_socket = requester_info.get("notification_socket")
        target_socket = target_info.get("notification_socket")

        if not requester_socket:
            return "Requester notification channel not ready"

        if not target_socket:
            return "Target notification channel not ready"

        # send notificaitio without lock 
        try:
            requester_socket.sendall(
                f"ConnectionAccepted,{target_info['ip']},{target_info['udp_port']}".encode()
            )
        except Exception as e:
            return "Requester notification channel unavailable"

        try:
            target_socket.sendall(
                f"ConnectionConfirmed,{requester_info['ip']},{requester_info['udp_port']}".encode()
            )
        except Exception as e:
            return "Target notification channel unavailable"

        return "Connection established."
    

    @staticmethod
    def delete_chat(request_list : list, connectionSocket):
        username = request_list[0]
        group_chat = request_list[1]
    

        try:
            with open('Users.json') as file:
                    data = json.load(file)

            delete_chat = False

            for group in data["Groups"]:
                    if group["group_name"] == group_chat :
                        if username in group["members"]:
                            group["members"].remove(username)
                            delete_chat  = True
                            break


            if delete_chat:
                with open('Users.json', 'w') as file:
                            json.dump(data, file, indent = 4)
                return f"Contact {username} successfully deleted from {group_chat}"
            else: 
                return "Does Not Exist"
            
        except FileNotFoundError:
                return "error Users.json file not found."
        except Exception as e :
            return f"An error has occured: {e}."


    @staticmethod
    def delete_message(request_list : list, connectionSocket):
        username = request_list[0]
        contact_or_group = request_list[1]
        delete_for = request_list[2] # me or everyone 
        message_ID = request_list[3]
        
        # going to fix this 
        try:
            with open('Users.json') as file:
                    data = json.load(file)

            message_deleted = False

            for m in data["Messages"]:
                    if (str(m["message_ID"]) == message_ID and m["destination_chat_or_groupchat"] == contact_or_group ):
                        if delete_for == "everyone":
                            if m["sender_name"] != username:
                                 return "You can only delete your own messages"
                            data["Messages"].remove(m)     
                            message_deleted = True
                        break

            if message_deleted:
                with open('Users.json', 'w') as file:
                    json.dump(data, file, indent = 4)
                return f"Message deleted."
            else: 
                return "Message ID Does Not Exist"
        except FileNotFoundError:
                return "error Users.json file not found."
        except Exception as e :
            return f"An error has occured: {e}."

    @staticmethod
    def get_all_users(Username:str, connectionSocket):
        all_users = []

        try:
            with open('Users.json') as file:
                    data = json.load(file)

            return  ", ".join(user["Username"] for user in data["Users"])
           
        except FileNotFoundError:
                return "error Users.json file not found."
        except Exception as e :
            return f"An error has occured: {e}."

    @staticmethod
    def send_message(request_list : list, connectionSocket):
        username = request_list[0]
        message_type = request_list[1]
        contact_or_group = request_list[2]
        chunk_num = request_list[3]
        message_time = request_list[4]
        body = request_list[5]
        contact_or_group_True_or_False = request_list[6]

        with open ('Users.json') as file:
             data = json.load(file)

        message_id = str(len(data.get("Messages",[]))+1)

        new_message = {
             
             "sender_name": username,
             "destination_chat_or_groupchat": contact_or_group,
             "message_type": message_type,
             "is_group": contact_or_group_True_or_False, # include code to ask for this 
             "chunk_num": chunk_num,
             "time_sent":message_time,
             "message_ID": message_id,
             "body": body,
            
        }

        data["Messages"].append(new_message)

        with open('Users.json', 'w') as file:
            json.dump(data, file, indent=4)

        with online_users_lock:
            target_info = online_users.get(contact_or_group)

        if target_info and "notification_socket" in target_info:
            try:
                target_info["notification_socket"].sendall(
                    f"NewMessage,{username},{body},{message_time}".encode()
                )
                return "Delivered."
            except:
                return "User online but delivery failed."

        return "Message saved. User offline"


    @staticmethod
    def get_online_user(request_list : list, connectionSocket):
        username = request_list[0]

        try:
             with online_users_lock:
                online_list = [user for user in online_users if user != username]

             if not online_list:
                  return "No other users are online."
             
             return ", ".join(online_list)
                
        except Exception as e :
             return f"An error has occured: {e}"

    @staticmethod
    def get_message_ID(request_list: list, connectionSocket):
       
        username = request_list[0]
        target = request_list[1]
        
        try:
            with open('Users.json', 'r') as file:
                data = json.load(file)
            
            found_messages = []
            for m in data.get("Messages", []):
               
                if m["destination_chat_or_groupchat"] == target:
                    found_messages.append(f"{m['message_ID']}: {m['body']}") # shows ID : message to client
            
            if not found_messages:
                return "No messages found."
                
            return ",".join(found_messages) # Client splits by comma
            
        except Exception as e:
            return f"Error retrieving message IDs: {e}"   

if __name__== "__main__":
     Server.start_server()
