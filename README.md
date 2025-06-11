# KellerC2

This repository contains a simple example of a command and control setup with a
Python web server and a minimal C++ client. The server keeps track of clients
that register with it and exposes an endpoint to view the list of currently
connected clients. The server also allows sending commands to individual
clients and stores their latest results.  Each client now reports its **public
IP address** so the server can display an approximate location on a map.

## Server

The server is implemented in `server.py` using Python's built-in HTTP
modules. It relies on `ThreadingHTTPServer` so multiple clients can poll
for commands at the same time without blocking one another.
Responses now include a `Content-Length` header so the C++ client can
determine message boundaries reliably.

### Running the server

```bash
python server.py
```

By default the server listens on port `8000`.

All client registrations, queued commands and results are stored in an
`SQLite` database named `keller.db`. Each time a client polls the `/poll`
endpoint its `last_seen` timestamp is updated. A background task runs every
minute to remove clients that have not been seen for an hour. The interval can
be changed by setting the `REMOVE_CLIENT_AFTER` environment variable.
The server keeps the most recent 100 command results for each client. This
limit can be adjusted by setting the `RESULT_HISTORY_LIMIT` environment
variable.

### Endpoints

- `POST /register` – Clients post a JSON payload
  `{"client_id": "<id>", "public_ip": "<ip>"}` to register themselves.
- `GET /clients` – Returns a JSON array describing each connected client:
  `[{"id": "<id>", "ip": "<ip>", "lat": <latitude>, "lon": <longitude>,
  "result": "<last>", "last_seen": <epoch_seconds>}]`. The latitude and
  longitude are estimated from the reported public IP and `last_seen` reflects
  the last time the server heard from each client.
- `GET /poll?client_id=<id>` – Long polls the server for a pending command for
  the given client. Returns `{"command": "..."}`.
- `POST /result` – Clients post back command results using a JSON payload
  `{"client_id": "<id>", "result": "<output>"}`.
- `POST /send` – Queues a command for a specific client using a payload
  `{"client_id": "<id>", "command": "<cmd>"}`.
- `GET /result?client_id=<id>` – Retrieves the latest stored result for a
  client.
- `GET /history?client_id=<id>` – Returns up to 10 recent results for a client
  as `{"result": "<output>", "ts": <epoch_seconds>}, ...]`. The server retains
  at most 100 results per client unless `RESULT_HISTORY_LIMIT` is set.
- `GET /commands?client_id=<id>` – Returns up to 10 recent commands queued for a client as `[{"command": "<cmd>", "ts": <epoch_seconds>}, ...]`.

## Client

`client.cpp` demonstrates a small program that connects to the server and
registers itself. On startup it contacts `api.ipify.org` to determine its
public IP address and includes that when registering. When it receives a
command, the client executes it on the local system and sends the command output
back to the server.

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

The sample client polls the server roughly once per second to look for
commands and post results. When no command is available it prints
"waiting..." so you can tell it is still running.

The client now parses HTTP responses using the reported `Content-Length`
header, which lets it handle large command output reliably.

After running one or more clients, visiting `http://localhost:8000/` opens a
web page with a world map. Each connected client appears as a marker on the
map. The server estimates each client's location using the public IP reported
by the client so the markers roughly indicate where clients are connecting
from. If multiple clients share the same IP, the server adds a small random
offset to each one so their markers don't overlap. Clicking a marker reveals
the client's ID, its IP address, a small form for sending a command and
displays its most recent result.
