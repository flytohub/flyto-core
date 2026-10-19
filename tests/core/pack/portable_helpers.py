"""Helpers for portable-pack and bundle tests: a source copy of the example, a fake provider."""

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_DIR = ROOT / "examples" / "packs" / "ratings-connector"
FIXTURES = Path(__file__).parent / "fixtures"
LOCK = FIXTURES / "portable_requirements.lock"
WORKFLOW = FIXTURES / "bundle_workflow.json"
RECORDED = json.loads((FIXTURES / "connector_recorded.json").read_text(encoding="utf-8"))
TOKEN = "test-token-not-real"

#: An operation the example does not have, so annotations are tested on both ends.
IRREVERSIBLE_OP = {
    "id": "finding.dismiss",
    "label": "Dismiss a finding",
    "method": "POST",
    "path": "/v1/findings/{finding}/dismiss",
    "consequence": "irreversible",
    "inputs": {"finding": {"type": "string", "description": "Finding identifier"}},
}


def example_source(tmp_path, *, base_url=None, mutate=None, name="ratings-src"):
    """A copy of the example pack directory, optionally pointed elsewhere or changed."""
    target = tmp_path / name
    shutil.copytree(EXAMPLE_DIR, target)
    doc = json.loads((target / "flyto-pack.json").read_text(encoding="utf-8"))
    if base_url is not None:
        doc["connector"]["base_url"] = base_url
    if mutate is not None:
        mutate(doc)
    (target / "flyto-pack.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return target


def example_doc(mutate=None):
    doc = json.loads((EXAMPLE_DIR / "flyto-pack.json").read_text(encoding="utf-8"))
    if mutate is not None:
        mutate(doc)
    return doc


class Provider(BaseHTTPRequestHandler):
    """A loopback stand-in for the provider, answering with recorded-shape bodies."""

    seen = []

    def log_message(self, *args):
        return None

    def _reply(self, status, payload):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        Provider.seen.append({"path": url.path, "query": query, "auth": self.headers.get("Authorization")})
        if url.path == "/v1/companies/c-1":
            self._reply(200, RECORDED["company"])
        elif url.path == "/v1/portfolio":
            self._reply(200, RECORDED["portfolio"])
        else:
            self._reply(404, {"detail": "not found"})


def start_provider():
    """Start the fake provider; returns ``(base_url, port, stop)``."""
    Provider.seen = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]

    def stop():
        httpd.shutdown()
        httpd.server_close()

    return f"http://127.0.0.1:{port}", port, stop
