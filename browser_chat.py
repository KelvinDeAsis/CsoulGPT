"""Serve the CsoulGPT browser interface on loopback."""

from contextlib import closing
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import webbrowser

from local_chat import ChatError, ReplyTruncated, chat_messages, stream_reply


MAX_REQUEST_BYTES = 1024 * 1024
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/chat.css": ("chat.css", "text/css; charset=utf-8"),
    "/chat.js": ("chat.js", "text/javascript; charset=utf-8"),
}


class ChatHandler(BaseHTTPRequestHandler):
    def __init__(self, *request, args):
        self.args = args
        super().__init__(*request)

    def log_message(self, *args):
        pass

    def local_host(self):
        return f"127.0.0.1:{self.server.server_port}"

    def begin_response(self, content_type, length=None):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def do_GET(self):
        if self.headers.get("Host") != self.local_host():
            self.send_error(403)
            return
        if self.path not in ASSETS:
            self.send_error(404)
            return
        filename, content_type = ASSETS[self.path]
        body = (Path(__file__).resolve().parent / "web" / filename).read_bytes()
        self.begin_response(content_type, len(body))
        self.wfile.write(body)

    def read_messages(self):
        if self.headers.get_content_type() != "application/json":
            raise ValueError
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= MAX_REQUEST_BYTES:
            raise ValueError
        request = json.loads(self.rfile.read(size))
        prompt = request["prompt"]
        history = request["history"]
        incomplete = request.get("partial")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError
        if incomplete is not None and (not isinstance(incomplete, str) or not incomplete.strip()):
            raise ValueError
        if not isinstance(history, list) or len(history) % 2:
            raise ValueError
        for i, message in enumerate(history):
            role = "assistant" if i % 2 else "user"
            if (
                not isinstance(message, dict)
                or set(message) != {"role", "content"}
                or message["role"] != role
                or not isinstance(message["content"], str)
            ):
                raise ValueError
        return chat_messages(history, prompt.strip(), self.args.max_tokens, incomplete)

    def do_POST(self):
        host = self.local_host()
        if self.headers.get("Host") != host or self.headers.get("Origin") != f"http://{host}":
            self.send_error(403)
            return
        if self.path != "/api/chat":
            self.send_error(404)
            return

        def event(**data):
            self.wfile.write(json.dumps(data).encode("utf-8") + b"\n")

        try:
            self.begin_response("application/x-ndjson; charset=utf-8")
            try:
                messages = self.read_messages()
                has_text = False
                with closing(stream_reply(self.args, messages)) as reply:
                    for chunk in reply:
                        has_text = has_text or bool(chunk.strip())
                        event(text=chunk)
                if not has_text:
                    raise ChatError("Ollama returned an empty reply. Try again.")
                event(done=True)
            except ReplyTruncated:
                if has_text:
                    event(done=True, truncated=True)
                else:
                    event(error="The reply reached the token limit before producing text.")
            except ChatError as error:
                event(error=str(error))
            except (KeyError, TypeError, ValueError):
                event(error="The message could not be read or was too large. Try a shorter message.")
        except (BrokenPipeError, ConnectionResetError):
            pass


def serve(args):
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(ChatHandler, args=args))
    except OSError as error:
        print(f"Could not open the local browser server: {error}", file=sys.stderr)
        return 1
    with server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"CsoulGPT is running at {url}\nKeep this window open. Press Ctrl+C to stop.", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0
