#!/usr/bin/env python3
"""
OpsGenome Local Development Web Server.
Serves the OpsGenome Web App at http://localhost:3000/ with full soft 3D claymorphism UI,
proxies API calls to the OpsGenome daemon at port 8765, and serves the Styleguide at /styleguide.
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import sys
import urllib.request
import urllib.error

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
DAEMON_STATIC = os.path.join(WORKSPACE_ROOT, "opsgenome", "daemon", "static")
DAEMON_BACKEND = "http://127.0.0.1:8765"

class OpsGenomeFrontendHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        # Forward API calls to backend daemon
        if self.path.startswith("/api/"):
            return self._proxy_request("GET")
        
        # Route root & dashboard to OpsGenome App
        if self.path in ("/", "/dashboard", "/dashboard/"):
            self._serve_file(os.path.join(DAEMON_STATIC, "index.html"), "text/html")
            return

        # Route styleguide
        if self.path in ("/styleguide", "/styleguide/"):
            self._serve_file(os.path.join(WORKSPACE_ROOT, "product_ui_styleguide.html"), "text/html")
            return

        # Route static assets
        if self.path.startswith("/static/"):
            rel_path = self.path[len("/static/"):].split("?")[0]
            target = os.path.join(DAEMON_STATIC, rel_path)
            if os.path.exists(target):
                self._serve_file(target)
                return

        # Fallback to standard handler
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._proxy_request("POST")
        self.send_error(404, "Not found")

    def _serve_file(self, filepath: str, content_type: str | None = None):
        if not os.path.exists(filepath):
            self.send_error(404, f"File {filepath} not found")
            return
        
        with open(filepath, "rb") as f:
            data = f.read()

        if not content_type:
            if filepath.endswith(".html"):
                content_type = "text/html"
            elif filepath.endswith(".jsx") or filepath.endswith(".js"):
                content_type = "application/javascript"
            elif filepath.endswith(".css"):
                content_type = "text/css"
            elif filepath.endswith(".json"):
                content_type = "application/json"
            else:
                content_type = "text/plain"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _proxy_request(self, method: str):
        target_url = f"{DAEMON_BACKEND}{self.path}"
        headers = {}
        for h in ("Content-Type", "Authorization", "Accept"):
            v = self.headers.get(h)
            if v:
                headers[h] = v

        data = None
        if method in ("POST", "PUT"):
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                data = self.rfile.read(length)

        try:
            req = urllib.request.Request(target_url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp_data = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-length", "access-control-allow-origin"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(resp_data)))
                self.end_headers()
                self.wfile.write(resp_data)
        except urllib.error.HTTPError as e:
            err_data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_data)))
            self.end_headers()
            self.wfile.write(err_data)
        except Exception as e:
            # Fallback error when daemon is not reachable
            msg = f'{{"error": "Daemon unavailable at {DAEMON_BACKEND}", "details": "{str(e)}"}}'.encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

def run(port: int = 3000):
    os.chdir(WORKSPACE_ROOT)
    server_address = ("127.0.0.1", port)
    try:
        httpd = HTTPServer(server_address, OpsGenomeFrontendHandler)
    except OSError as e:
        if e.errno == 48:
            print(f"\n=======================================================")
            print(f" [!] Notice: Port {port} is already in use.")
            print(f"     OpsGenome Web App is already running at:")
            print(f"     • http://localhost:{port}/")
            print(f"     To restart fresh: lsof -ti :{port} | xargs kill -9")
            print(f"=======================================================\n")
            return
        raise
    print(f"\n=======================================================")
    print(f" OpsGenome Claymorphic Web App Online on Port {port}")
    print(f"   • Web App:     http://localhost:{port}/")
    print(f"   • Styleguide:  http://localhost:{port}/styleguide")
    print(f"   • API Proxy:   {DAEMON_BACKEND}")
    print(f"=======================================================\n")
    httpd.serve_forever()

if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    run(p)
