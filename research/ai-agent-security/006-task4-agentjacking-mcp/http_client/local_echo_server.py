#!/usr/bin/env python3
"""Minimal local echo HTTP server for http_client verification."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json


class EchoHandler(BaseHTTPRequestHandler):
    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _respond(self, method):
        body = self._read_body()
        try:
            text = body.decode("utf-8") if body else ""
        except UnicodeDecodeError:
            text = repr(body)

        payload = {
            "method": method,
            "path": self.path,
            "headers": {k: v for k, v in self.headers.items()},
            "body": text,
        }
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Echo-Server", "local-http-client-test")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._respond("GET")

    def do_POST(self):
        self._respond("POST")

    def do_PUT(self):
        self._respond("PUT")

    def do_DELETE(self):
        self._respond("DELETE")

    def do_PATCH(self):
        self._respond("PATCH")

    def log_message(self, fmt, *args):
        # Keep server quiet during tests
        pass


if __name__ == "__main__":
    host, port = "127.0.0.1", 18765
    server = HTTPServer((host, port), EchoHandler)
    print(f"echo server on http://{host}:{port}", flush=True)
    server.serve_forever()