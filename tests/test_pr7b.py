"""Tests for Issue #18 / PR7b: HTTP evidence source in the observer.

Layers exercised:

1. Config parsing — ``type: http`` shape, defaults, validation errors.
2. ``observer._collect_http`` — directly invoked against a local
   ``http.server.ThreadingHTTPServer`` running on an ephemeral port in a
   daemon thread. Covers happy path, 5xx with body, and connection-refused.
3. End-to-end ``Governor.run_once`` with a single ``type: http`` evidence
   source — asserts the recorded observation.json reflects the HTTP response.

The new source uses ``urllib.request`` from the stdlib, so no new third-party
dependency is added to the kernel.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from evolution_kernel.config import ConfigError, EvidenceSource, parse_config
from evolution_kernel.governor import Governor, RoleCommand
from evolution_kernel.observer import _collect_http, collect_observation


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _role(name: str) -> RoleCommand:
    return RoleCommand([sys.executable, str(FIXTURES / name)])


def _git(args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout.strip()


def _bootstrap_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["init"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    (repo / "README.md").write_text("# target\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "initial"], repo)


# ---------------------------------------------------------------------------
# Local HTTP test server
# ---------------------------------------------------------------------------


class _EchoHandler(BaseHTTPRequestHandler):
    """A handler that lets each test choose status + body via path.

    /ok      → 200 with a known body
    /500     → 500 with a body
    /headers → 200 echoing inbound headers, so we can verify header passing
    anything else → 404 with empty body
    """

    server_version = "EvolutionKernelTestServer/1.0"

    def log_message(self, format, *args):  # silence test noise
        return

    def do_GET(self):  # noqa: N802 — stdlib mandates this name
        if self.path == "/ok":
            body = b'{"status":"ok","score":0.42}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Test-Marker", "evolution-kernel")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/500":
            body = b"internal failure body"
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/headers":
            received = self.headers.get("X-Auth", "<absent>")
            body = f"X-Auth={received}".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()


class _ServerHandle:
    def __init__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


class TestHttpSourceConfigParsing(unittest.TestCase):

    def test_minimal_http_source_with_defaults(self):
        cfg = parse_config({
            "mission": "x",
            "evidence_sources": [
                {"type": "http", "url": "http://localhost:8000/status"},
            ],
        })
        (src,) = cfg.evidence_sources
        self.assertEqual(src.type, "http")
        self.assertEqual(src.url, "http://localhost:8000/status")
        self.assertEqual(src.method, "GET")
        self.assertEqual(src.headers, ())
        self.assertEqual(src.timeout, 10.0)

    def test_full_http_source_parsed(self):
        cfg = parse_config({
            "mission": "x",
            "evidence_sources": [{
                "type": "http",
                "url": "http://localhost:8000/eval",
                "method": "post",
                "headers": {"Accept": "application/json", "X-Run": 42},
                "timeout": 5,
            }],
        })
        (src,) = cfg.evidence_sources
        self.assertEqual(src.method, "POST")  # uppercased
        self.assertEqual(dict(src.headers), {"Accept": "application/json", "X-Run": "42"})
        self.assertEqual(src.timeout, 5.0)

    def test_missing_url_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({
                "mission": "x",
                "evidence_sources": [{"type": "http"}],
            })

    def test_blank_url_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({
                "mission": "x",
                "evidence_sources": [{"type": "http", "url": "   "}],
            })

    def test_bad_timeout_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({
                "mission": "x",
                "evidence_sources": [{"type": "http", "url": "http://x", "timeout": "soon"}],
            })

    def test_non_positive_timeout_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({
                "mission": "x",
                "evidence_sources": [{"type": "http", "url": "http://x", "timeout": 0}],
            })

    def test_bad_headers_shape_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({
                "mission": "x",
                "evidence_sources": [{"type": "http", "url": "http://x", "headers": [1, 2]}],
            })

    def test_unknown_type_rejected(self):
        with self.assertRaises(ConfigError):
            parse_config({
                "mission": "x",
                "evidence_sources": [{"type": "telnet", "url": "x"}],
            })


# ---------------------------------------------------------------------------
# _collect_http unit tests
# ---------------------------------------------------------------------------


class TestCollectHttp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = _ServerHandle()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def test_200_captures_status_body_headers(self):
        rec = _collect_http(
            EvidenceSource(type="http", url=f"{self.server.base_url}/ok"),
            limit=64 * 1024,
        )
        self.assertEqual(rec["status"], 200)
        self.assertEqual(rec["method"], "GET")
        self.assertIn('"score":0.42', rec["body"])
        # Headers list contains the marker we set on the server side.
        kv = {k.lower(): v for k, v in rec["headers"]}
        self.assertEqual(kv.get("x-test-marker"), "evolution-kernel")
        self.assertNotIn("error", rec)

    def test_500_still_records_body(self):
        rec = _collect_http(
            EvidenceSource(type="http", url=f"{self.server.base_url}/500"),
            limit=64 * 1024,
        )
        self.assertEqual(rec["status"], 500)
        self.assertEqual(rec["body"], "internal failure body")
        self.assertNotIn("error", rec)

    def test_headers_are_sent(self):
        rec = _collect_http(
            EvidenceSource(
                type="http",
                url=f"{self.server.base_url}/headers",
                headers=(("X-Auth", "token-abc"),),
            ),
            limit=64 * 1024,
        )
        self.assertEqual(rec["status"], 200)
        self.assertEqual(rec["body"], "X-Auth=token-abc")

    def test_truncation_marked_when_body_exceeds_limit(self):
        rec = _collect_http(
            EvidenceSource(type="http", url=f"{self.server.base_url}/ok"),
            limit=5,
        )
        self.assertTrue(rec.get("truncated"))
        self.assertEqual(rec["bytes"], 5)

    def test_connection_refused_records_error(self):
        # Bind a socket to grab a free port, then close it so the address is unused.
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
        s.close()
        rec = _collect_http(
            EvidenceSource(type="http", url=f"http://127.0.0.1:{free_port}/", timeout=2.0),
            limit=1024,
        )
        self.assertIn("error", rec)
        # No body / status when the connection never opened.
        self.assertNotIn("status", rec)

    def test_blank_url_records_error(self):
        rec = _collect_http(EvidenceSource(type="http", url=""), limit=1024)
        self.assertEqual(rec.get("error"), "empty url")


# ---------------------------------------------------------------------------
# End-to-end through collect_observation + Governor.run_once
# ---------------------------------------------------------------------------


class TestHttpObservationE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = _ServerHandle()

    @classmethod
    def tearDownClass(cls):
        cls.server.close()

    def test_collect_observation_includes_http_response(self):
        obs = collect_observation(
            (EvidenceSource(type="http", url=f"{self.server.base_url}/ok"),),
            cwd=Path("/tmp"),
        )
        self.assertEqual(len(obs["sources"]), 1)
        src = obs["sources"][0]
        self.assertEqual(src["status"], 200)
        self.assertIn('"score":0.42', src["body"])

    def test_governor_run_once_writes_http_into_observation_json(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            repo = base / "repo"
            ledger = base / "ledger"
            _bootstrap_repo(repo)

            governor = Governor(
                target_repo=repo,
                ledger_dir=ledger,
                planner=_role("planner.py"),
                executor=_role("executor.py"),
                evaluator=_role("evaluator_accept.py"),
                evidence_sources=(
                    EvidenceSource(type="http", url=f"{self.server.base_url}/ok"),
                ),
            )
            result = governor.run_once({"name": "http-e2e"}, run_id="0001")

            obs_path = result.run_dir / "observation.json"
            data = json.loads(obs_path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["sources"]), 1)
            src = data["sources"][0]
            self.assertEqual(src["type"], "http")
            self.assertEqual(src["status"], 200)
            self.assertEqual(src["url"], f"{self.server.base_url}/ok")
            self.assertIn("score", src["body"])


if __name__ == "__main__":
    unittest.main()
