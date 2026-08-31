# 💬 Socket Chat — TCP/UDP Messaging App (Python)

A terminal-based, real-time messaging application built entirely with **raw Python sockets** — no external frameworks. Users can register, log in, add contacts, create group chats, send messages through a central server, connect directly peer-to-peer over UDP, transfer files/images, and even make live voice calls — all from the command line.

This project was built to demonstrate core **network programming** and **concurrent systems** skills.

---

## 🚀 What This Project Demonstrates

- **TCP client/server architecture** — a persistent multi-client server built on raw sockets (`socket`, `AF_INET`, `SOCK_STREAM`)
- **UDP peer-to-peer communication** — direct client-to-client messaging that bypasses the server once a connection is established
- **Custom application-layer protocol** — comma-delimited request/response messages (e.g. `LoginRequest,username,password,...`) parsed and routed server-side
- **Binary chunked file transfer over UDP** — a hand-rolled header format (`struct.pack`/`struct.unpack`) to split, label, and reassemble files/images larger than a single UDP datagram
- **Multithreading & concurrency** — `threading` used for handling multiple simultaneous clients, background notification listeners, mic streaming, and UDP receive loops
- **Real-time server-push notifications** — a dedicated persistent socket per user for live updates (incoming messages, connection requests, call invites) without polling
- **Live audio streaming (VoIP-style calls)** — optional real-time microphone capture and playback over UDP using `pyaudio`
- **JSON-based persistence** — a flat-file "database" (`Users.json`) storing users, contacts, groups, and message history
- **Thread-safe shared state** — use of `threading.Lock()` to protect shared client state across threads

---

## 🗂️ Project Structure

| File | Description |
|---|---|
| `Server.py` | The central TCP server. Handles login/registration, contact & group management, message routing/storage, online-user tracking, and brokering peer-to-peer/call connections. |
| `Client.py` | The terminal client. Handles the user-facing menu system, sends requests to the server, and manages the direct UDP peer connection (messaging, file/image transfer, and audio calls). |
| `Users.json` | Local JSON "database" storing registered users, their contact lists, groups, and message history. |

---

## ✨ Features

### Account & Contacts
- Register a new account (`username` + `password`)
- Log in (starts a persistent connection + background notification listener)
- Add contacts
- View which users are currently online

### Messaging (via Server)
- Send a text message to a contact or a group
- Delete a chat entirely
- Delete an individual message (for yourself or for everyone)
- Receive new messages in real time via server push notifications

### Groups
- Create a group chat with any number of existing users

### Peer-to-Peer (Direct UDP Connection)
Once two users establish a P2P connection (brokered by the server), they can:
- Send instant messages directly to each other (no server round-trip)
- Send an image file
- Send an audio file or PDF (sent in chunks and reassembled automatically on arrival)
- End the peer-to-peer stream at any time

### Live Voice Calls
- Call any online user
- Recipient can **Accept** or **Decline** the incoming call
- On acceptance, both sides open a live microphone stream and audio is sent over UDP in real time
- Hang up at any time by typing `q`

---

## 🖥️ How to Use It

### 1. Requirements
```bash
python3 -m pip install pyaudio   # optional — only needed for voice calls
```
> If `pyaudio` isn't installed, everything except voice calls will still work — the client automatically detects and disables audio.

### 2. Start the server
On the host machine, run:
```bash
python3 Server.py
```
The server listens on port `12000` and will print `Server is listening` once ready.

### 3. Start the client
On each machine/terminal that wants to chat (can also be run in multiple terminals on the same machine for local testing):
```bash
python3 Client.py
```

### 4. Register / Log in
```
--- Welcome ---
1) Register
2) Login
q) Quit
```
Register a username + password, then log in. Logging in opens a background thread that listens for real-time server notifications (new messages, connection requests, incoming calls).

### 5. Main Menu
Once logged in:
```
----Main Menu ----
1) Add Contact
2) Create Group
3) Send Message (Server)
4) Delete Chat
5) Delete Message
6) View Online Users
7) Start Peer-to-Peer (UDP)
8) Start Audio Call (UDP)
9) Logout
```

### 6. Example: sending a message remotely
1. Run `Server.py` on the machine that will act as the host.
2. Run `Client.py` in two separate terminals (or on two separate machines pointed at the same server).
3. Register/log in as two different users in each terminal.
4. In one terminal, use **1) Add Contact** to add the other user.
5. Use **3) Send Message (Server)** to send a message — it will arrive instantly in the other terminal via the notification listener.
6. Alternatively, use **7) Start Peer-to-Peer (UDP)** to connect directly and exchange messages, images, and files without going through the server for each message.

---

## 🔧 How It Works (Under the Hood)

- **Server ↔ Client (TCP, port 12000):** All account, contact, group, and message-storage actions go through the server using a simple text protocol: `RequestType,arg1,arg2,...`. The server parses the request type and routes it to the matching handler method.
- **Notification channel:** After login, the client opens a *second*, dedicated TCP connection purely for receiving push notifications (new messages, call requests, connection approvals) so the main request/response socket stays free.
- **Peer-to-Peer (UDP):** When two users want to connect directly, the server exchanges each user's IP/UDP port with the other, then gets out of the way — all further messages, files, and audio for that session travel directly between the two clients over UDP.
- **Chunked transfer protocol:** Files and images are split into chunks under the UDP size limit, each prefixed with a small custom header (`type | filename length | chunk index | total chunks`) so the receiving client can reassemble them in the correct order, regardless of arrival order.

---

## 🛠️ Tech Stack

- **Language:** Python 3
- **Networking:** `socket` (TCP + UDP), `struct` (binary packet framing)
- **Concurrency:** `threading`
- **Audio:** `pyaudio` (optional)
- **Storage:** `json`

---

## 📌 Status

This is a personal/learning project exploring low-level socket programming, custom protocol design, and real-time concurrent applications in Python — built without any web frameworks or messaging libraries.

