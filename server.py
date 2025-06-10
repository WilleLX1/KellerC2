#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

clients = set()

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/register':
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length)
            client_id = None
            try:
                payload = json.loads(data.decode())
                client_id = payload.get('client_id')
            except Exception:
                pass
            if client_id:
                clients.add(client_id)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Registered')
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Bad Request')
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/clients':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(sorted(list(clients))).encode())
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Server is running')

def run(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, Handler)
    print(f'Starting server on port {port}...')
    httpd.serve_forever()

if __name__ == '__main__':
    run()
