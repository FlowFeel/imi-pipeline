#!/usr/bin/env python3
"""Crossref deposit stub for the DOI preprint harness.

Simulates the Crossref deposit API over plain HTTP. Stdlib-only so the
container image needs no pip install and stays deterministic.

Endpoints
---------
POST /servlet/deposit     Crossref-style XML deposit. Body carries the DOI.
GET  /deposits/<id>       Receipt lookup: returns deposit record + status.
POST /admin/script        Script next deposit response:
                          {"doi_suffix": "050", "mode": "timeout"|"malformed"|...}
POST /admin/reset         Wipe all state between scenarios.
GET  /admin/health        Liveness for docker healthcheck.

Scripted modes
--------------
success    201 + deposit id, status "pending" -> flips to "registered".
timeout    Connection stalls then 500 — used to exercise saga retry paths.
malformed  201 but the receipt XML lacks the <doi> element — exercises
           the malformed-receipt guard in the WP plugin.
reject     400 with an error body — bad metadata path.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

PORT = 8000

# ── in-memory state (single container, reset per scenario) ──
_lock = threading.Lock()
_deposits: dict[str, dict[str, Any]] = {}
_seq = {"n": 9000}


class _Stub(BaseHTTPRequestHandler):
    protocol_version: ClassVar[str] = "HTTP/1.1"

    # ── helpers ──
    def _json(self, code: int, payload: dict[str, Any]) -> None:
        import json

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

    # ── Crossref-style deposit ──
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace")

        if self.path == "/admin/script":
            import json

            req = json.loads(raw)
            suffix = str(req.get("doi_suffix", "")).lstrip("0") or "0"
            with _lock:
                _SCRIPTED[suffix] = req.get("mode", "success")
            self._json(200, {"scripted": suffix, "mode": req.get("mode")})
            return

        if self.path == "/admin/reset":
            with _lock:
                _deposits.clear()
                _SCRIPTED.clear()
                _seq["n"] = 9000
            self._json(200, {"reset": True})
            return

        if self.path != "/servlet/deposit":
            self._json(404, {"error": f"unknown path {self.path}"})
            return

        # Pull DOI suffix out of the payload (either doi= or the raw XML).
        doi = ""
        for line in raw.splitlines():
            if line.lower().startswith("doi="):
                doi = line.split("=", 1)[1].split("&")[0]
                break
        if not doi:
            for token in ("doi=", "<doi>", "imi.2026."):
                if token in raw:
                    idx = raw.find(token)
                    doi = raw[idx : idx + 80]
                    break
        suffix = ""
        if "imi.2026." in doi:
            suffix = doi.split("imi.2026.", 1)[1].strip("<>&\"' ").strip()

        mode = _SCRIPTED.get(suffix, "success")

        if mode == "timeout":
            time.sleep(0.8)
            self._xml(500, "<error>upstream timeout</error>")
            return
        if mode == "reject":
            self._json(400, {"error": "malformed deposit batch", "doi": doi})
            return

        with _lock:
            _seq["n"] += 1
            dep_id = f"cr-dep-{_seq['n']}"
            _deposits[dep_id] = {
                "doi": f"10.67767/imi.2026.{suffix}" if suffix else doi,
                "status": "pending",
                "mode": mode,
                "received_at": time.time(),
            }

        if mode == "malformed":
            # 201 but the receipt omits <doi> — plugin must not trust it.
            self._xml(
                201,
                f"<deposit_receipt><cr-dep-id>{dep_id}</cr-dep-id></deposit_receipt>",
            )
            return

        self._xml(
            201,
            "<deposit_receipt>"
            f"<cr-dep-id>{dep_id}</cr-dep-id>"
            f"<doi>10.67767/imi.2026.{suffix or '000'}</doi>"
            "<status>pending</status>"
            "</deposit_receipt>",
        )

    # ── receipt lookup / health ──
    def do_GET(self) -> None:
        if self.path == "/admin/health":
            self._json(200, {"ok": True})
            return
        if self.path.startswith("/deposits/"):
            dep_id = self.path.rsplit("/", 1)[-1]
            with _lock:
                rec = _deposits.get(dep_id)
            if rec is None:
                self._json(404, {"error": "unknown deposit id", "id": dep_id})
            else:
                self._json(200, rec)
            return
        self._json(404, {"error": f"unknown path {self.path}"})

    def log_message(self, fmt: str, *args: Any) -> None:  # keep CI logs quiet
        return


_SCRIPTED: dict[str, str] = {}

if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), _Stub)
    print(f"crossref stub listening on :{PORT}")
    server.serve_forever()
