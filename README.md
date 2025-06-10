# KellerC2

This repository contains a simple example of a command and control setup with a
Python web server and a minimal C++ client. The server keeps track of clients
that register with it and exposes an endpoint to view the list of currently
connected clients. The server also allows sending commands to individual
clients and stores their latest results.

## Server

The server is implemented in `server.py` and uses Python's built-in HTTP
modules, so no additional dependencies are required.

### Running the server

```bash
python server.py
```

By default the server listens on port `8000`.

### Endpoints

- `POST /register` – Clients post a JSON payload `{"client_id": "<id>"}` to
  register themselves.
- `GET /clients` – Returns a JSON array containing the IDs of all registered
  clients.
- `GET /poll?client_id=<id>` – Long polls the server for a pending command 
  for the given client. Returns `{"command": "..."}`.
- `POST /result` – Clients post back command results using a JSON payload
  `{"client_id": "<id>", "result": "<output>"}`.
- `POST /send` – Queues a command for a specific client using a payload
  `{"client_id": "<id>", "command": "<cmd>"}`.
- `GET /result?client_id=<id>` – Retrieves the latest stored result for a
  client.

## Client

`client.cpp` demonstrates a small program that connects to the server and
registers itself.

### Building the client (Windows)

Use a Windows toolchain such as Visual Studio or MinGW. With MSVC, you can
compile the client using:

```cmd
cl /EHsc client.cpp ws2_32.lib
```

If you are using MinGW, the command is:

```bash
g++ -std=c++11 client.cpp -lws2_32 -o client.exe
```

### Running the client

```bash
client.exe my_client_id
```

After running one or more clients, requesting `http://localhost:8000/clients`
will show the list of registered clients. The web interface available at
`http://localhost:8000/` lets you send commands to individual clients and view
their most recent results.