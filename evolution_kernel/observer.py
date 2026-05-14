"""Collect evidence from file + shell sources into a structured observation bundle.

Writes a single ``observation.json`` document so the planner has reproducible
inputs that an external auditor can replay.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import EvidenceSource

DEFAULT_FILE_LIMIT = 64 * 1024  # 64 KiB
DEFAULT_SHELL_TIMEOUT = 30  # seconds
DEFAULT_HTTP_LIMIT = 64 * 1024  # 64 KiB body cap


def collect_observation(
    sources: Sequence[EvidenceSource],
    cwd: Path | str,
    file_limit: int = DEFAULT_FILE_LIMIT,
    shell_timeout: int = DEFAULT_SHELL_TIMEOUT,
    http_limit: int = DEFAULT_HTTP_LIMIT,
) -> Mapping[str, Any]:
    """Run each evidence source and return a structured bundle."""
    base = Path(cwd).resolve()
    collected: list[dict[str, Any]] = []
    for source in sources:
        if source.type == "file":
            collected.append(_collect_file(source.path or "", base, file_limit))
        elif source.type == "shell":
            collected.append(_collect_shell(source.command or "", base, shell_timeout))
        elif source.type == "http":
            collected.append(_collect_http(source, http_limit))
        else:
            collected.append({"type": source.type, "error": "unknown source type"})
    return {"cwd": str(base), "sources": collected}


def write_observation(path: Path | str, observation: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _collect_file(rel_path: str, cwd: Path, limit: int) -> dict[str, Any]:
    record: dict[str, Any] = {"type": "file", "path": rel_path}
    try:
        target = (cwd / rel_path).resolve()
    except OSError as exc:
        record["error"] = str(exc)
        return record
    try:
        target.relative_to(cwd)
    except ValueError:
        record["error"] = "path escapes observer cwd"
        return record
    if not target.exists():
        record["error"] = "not found"
        return record
    if not target.is_file():
        record["error"] = "not a regular file"
        return record
    try:
        data = target.read_bytes()
    except OSError as exc:
        record["error"] = str(exc)
        return record
    if len(data) > limit:
        record["truncated"] = True
        data = data[:limit]
    record["content"] = data.decode("utf-8", errors="replace")
    record["bytes"] = len(data)
    return record


def _collect_http(source: EvidenceSource, limit: int) -> dict[str, Any]:
    """Fetch one HTTP endpoint into a structured record.

    The observer stays a thin collector: it captures status, headers, and a
    byte-capped body, plus an ``error`` string on failure. Retries, auth
    flows, and content parsing belong upstream (planner / role scripts).
    """
    url = source.url or ""
    method = (source.method or "GET").upper()
    record: dict[str, Any] = {"type": "http", "url": url, "method": method}
    if not url.strip():
        record["error"] = "empty url"
        return record
    request = urllib.request.Request(url, method=method)
    for header_name, header_value in source.headers:
        request.add_header(header_name, header_value)
    try:
        with urllib.request.urlopen(request, timeout=source.timeout) as response:
            status = int(getattr(response, "status", response.getcode() or 0))
            headers_obj = response.headers
            body = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        # Non-2xx responses still carry a body — record it like a success
        # except for the status code so the planner can react to 4xx/5xx.
        try:
            body = exc.read(limit + 1)
        except Exception:
            body = b""
        headers_obj = exc.headers
        status = int(exc.code)
    except urllib.error.URLError as exc:
        record["error"] = f"URLError: {exc.reason!r}"
        return record
    except (TimeoutError, OSError) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record

    if len(body) > limit:
        record["truncated"] = True
        body = body[:limit]
    record["status"] = status
    record["bytes"] = len(body)
    record["body"] = body.decode("utf-8", errors="replace")
    # Sort headers so the observation bundle is stable for ledger diffs.
    record["headers"] = sorted(
        ((str(k), str(v)) for k, v in headers_obj.items()),
        key=lambda kv: (kv[0].lower(), kv[1]),
    )
    return record


def _collect_shell(command: str, cwd: Path, timeout: int) -> dict[str, Any]:
    record: dict[str, Any] = {"type": "shell", "command": command}
    if not command.strip():
        record["error"] = "empty command"
        return record
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        record["error"] = f"timeout after {timeout}s"
        return record
    except OSError as exc:
        record["error"] = str(exc)
        return record
    record["exit"] = completed.returncode
    record["stdout"] = completed.stdout
    record["stderr"] = completed.stderr
    return record
