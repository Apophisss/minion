"""The scenario site: static pages plus POST /api/result, which appends what a page reports to /tmp/gym-results.jsonl."""

import http.server
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = "/tmp/gym-results.jsonl"  # (not in the home folder, whose new files act reports)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
        if self.path.startswith("/api/result"):
            try:
                data = json.loads(body)
            except ValueError:
                data = {"raw": body}
            data["at"] = time.strftime("%H:%M:%S")
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
            self.send_response(204)
            self.end_headers()
            return
        # A classic form post: echo the fields back as a page.
        from urllib.parse import parse_qs

        fields = {k: v if len(v) > 1 else v[0] for k, v in parse_qs(body).items()}
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(
                json.dumps({"task": "form-post", "path": self.path, "data": fields, "at": time.strftime("%H:%M:%S")})
                + "\n"
            )
        page = (
            "<!doctype html><title>Received</title><h1>Received</h1><pre id=result>"
            + json.dumps(fields, indent=1)
            + "</pre>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode())


port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
