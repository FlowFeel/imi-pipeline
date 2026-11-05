#!/usr/bin/env python3
"""Crossref Schema 5.3.1 deposit & DOI resolution simulator for the DOI preprint harness.

Simulates the Crossref deposit API and doi.org resolver over plain HTTP.
Stdlib-only so the container image requires no pip install and stays hermetic.

Endpoints
---------
POST /servlet/deposit     Crossref Schema 5.3.1 XML deposit. Validates schema and registers DOI.
GET  /deposits/<id>       Receipt lookup: returns deposit record + status.
GET  /resolve/<doi>       Hermetic DOI resolver: returns 302 redirect to registered landing page.
GET  /10.67767/<suffix>   Direct DOI path resolver: returns 302 redirect.
POST /admin/script        Script next deposit response:
                          {"doi_suffix": "050", "mode": "timeout"|"malformed"|"reject"}
POST /admin/reset         Wipe all state between scenarios.
GET  /admin/health        Liveness for docker healthcheck.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

from crossref_simulator import CrossrefSimulatorEngine

PORT = 8000
_ENGINE = CrossrefSimulatorEngine(allowed_prefix="10.67767")


class _Stub(BaseHTTPRequestHandler):
    protocol_version: ClassVar[str] = "HTTP/1.1"

    # ── helpers ──
    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _xml(self, code: int, text: str) -> None:
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── Crossref-style deposit & admin ──
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace")

        if self.path == "/admin/script":
            req = json.loads(raw)
            suffix = str(req.get("doi_suffix", "")).lstrip("0") or "0"
            mode = req.get("mode", "success")
            _ENGINE.script_mode(suffix, mode)
            self._json(200, {"scripted": suffix, "mode": mode})
            return

        if self.path == "/admin/reset":
            _ENGINE.reset()
            self._json(200, {"reset": True})
            return

        if self.path != "/servlet/deposit":
            self._json(404, {"error": f"unknown path {self.path}"})
            return

        # Delegate to high-fidelity Schema 5.3.1 simulator engine
        result = _ENGINE.deposit(raw)
        self._xml(result.status_code, result.response_body)

    # ── receipt lookup, health, and DOI 302 resolution ──
    def do_GET(self) -> None:
        if self.path == "/admin/health":
            self._json(200, {"ok": True, "engine": "CrossrefSchema5.3.1Simulator"})
            return

        # Deposit lookup
        if self.path.startswith("/deposits/"):
            dep_id = self.path.rsplit("/", 1)[-1]
            rec = _ENGINE.get_deposit(dep_id)
            if rec is None:
                self._json(404, {"error": "unknown deposit id", "id": dep_id})
            else:
                self._json(200, rec)
            return

        # DOI Resolution
        doi_to_resolve = ""
        if self.path.startswith("/resolve/"):
            doi_to_resolve = self.path.replace("/resolve/", "", 1)
        elif self.path.startswith("/10.67767/"):
            doi_to_resolve = self.path.lstrip("/")

        if doi_to_resolve:
            target_url = _ENGINE.resolve_doi(doi_to_resolve)
            if target_url:
                self.send_response(302)
                self.send_header("Location", target_url)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            else:
                body = f"DOI Not Found or Pending: {doi_to_resolve}".encode()
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        self._json(404, {"error": f"unknown path {self.path}"})

    def log_message(self, fmt: str, *args: Any) -> None:  # keep CI logs quiet
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), _Stub)
    print(f"crossref simulator listening on :{PORT}")
    server.serve_forever()
