# KellerC2

This repository contains a simple example of a command and control setup with a
Python web server and a minimal C++ client. The server keeps track of clients
that register with it and exposes an endpoint to view the list of currently
connected clients.

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
will show the list of registered clients.