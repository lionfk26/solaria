"""
microdot.py

A tiny, self-contained HTTP helper for MicroPython, used by Solaria's
table firmware to expose a couple of local diagnostic endpoints
(e.g. GET /status, GET /ping) over Wi-Fi without pulling in a full web
framework. Not a general-purpose replacement for anything -
deliberately minimal for a Pico W with limited RAM.

Usage:

    from microdot import App

    app = App()

    @app.route("/status")
    def status(request):
        return {"table_id": TABLE_ID, "uptime_ms": time.ticks_ms()}

    app.run(port=80)
"""

import json
import socket

try:
    import uselect as select
except ImportError:
    import select


class Request:
    def __init__(self, method, path, headers, body):
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body


class App:
    def __init__(self):
        self._routes = {}

    def route(self, path, methods=("GET",)):
        def decorator(handler):
            self._routes[path] = (handler, methods)
            return handler
        return decorator

    def _parse_request(self, client_stream):
        request_line = client_stream.readline()
        if not request_line:
            return None
        try:
            method, path, _ = request_line.decode().split(" ", 2)
        except ValueError:
            return None

        headers = {}
        while True:
            line = client_stream.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            try:
                key, value = line.decode().split(":", 1)
                headers[key.strip().lower()] = value.strip()
            except ValueError:
                continue

        body = b""
        content_length = int(headers.get("content-length", 0))
        if content_length:
            body = client_stream.read(content_length)

        return Request(method, path, headers, body)

    def _send_response(self, client_stream, status_code, body_obj):
        if isinstance(body_obj, (dict, list)):
            payload = json.dumps(body_obj).encode()
            content_type = "application/json"
        elif isinstance(body_obj, str):
            payload = body_obj.encode()
            content_type = "text/plain"
        else:
            payload = b""
            content_type = "text/plain"

        reason = "OK" if status_code == 200 else "Error"
        header = (
            f"HTTP/1.1 {status_code} {reason}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        client_stream.write(header.encode())
        if payload:
            client_stream.write(payload)

    def handle_client(self, client_sock):
        client_stream = client_sock.makefile("rwb")
        try:
            request = self._parse_request(client_stream)
            if request is None:
                return
            entry = self._routes.get(request.path)
            if entry is None:
                self._send_response(client_stream, 404, {"error": "not found"})
                return
            handler, methods = entry
            if request.method not in methods:
                self._send_response(client_stream, 405, {"error": "method not allowed"})
                return
            result = handler(request)
            self._send_response(client_stream, 200, result)
        except Exception as exc:  # noqa: BLE001 - keep the server alive
            try:
                self._send_response(client_stream, 500, {"error": str(exc)})
            except Exception:
                pass
        finally:
            try:
                client_stream.close()
            except Exception:
                pass
            client_sock.close()

    def run(self, host="0.0.0.0", port=80, poll_ms=200):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((host, port))
        server_sock.listen(2)
        server_sock.setblocking(False)

        poller = select.poll()
        poller.register(server_sock, select.POLLIN)

        while True:
            events = poller.poll(poll_ms)
            for sock, _event in events:
                try:
                    client_sock, _addr = sock.accept()
                except OSError:
                    continue
                self.handle_client(client_sock)
            yield  # cooperative: caller's main loop can service audio/touch too
