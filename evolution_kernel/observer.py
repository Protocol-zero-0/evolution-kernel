from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

from .config import EvidenceSource

SHELL_TIMEOUT = 30


class Observer:
    def run(
        self,
        sources: Sequence[EvidenceSource],
        worktree: Path,
        run_dir: Path,
    ) -> dict[str, Any]:
        results = [self._collect(s, worktree) for s in sources]
        observation: dict[str, Any] = {"sources": results}
        out = run_dir / "observation.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(observation, indent=2) + "\n", encoding="utf-8")
        return observation

    def _collect(self, source: EvidenceSource, worktree: Path) -> dict[str, Any]:
        if source.type == "file":
            return self._read_file(source, worktree)
        if source.type == "shell":
            return self._run_shell(source, worktree)
        return {"type": source.type, "error": f"unknown source type: {source.type!r}"}

    def _read_file(self, source: EvidenceSource, worktree: Path) -> dict[str, Any]:
        path = worktree / (source.path or "")
        try:
            return {"type": "file", "path": source.path, "content": path.read_text(encoding="utf-8")}
        except Exception as exc:
            return {"type": "file", "path": source.path, "error": str(exc)}

    def _run_shell(self, source: EvidenceSource, worktree: Path) -> dict[str, Any]:
        try:
            result = subprocess.run(
                source.command,
                shell=True,
                cwd=worktree,
                text=True,
                capture_output=True,
                timeout=SHELL_TIMEOUT,
            )
            return {
                "type": "shell",
                "command": source.command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except Exception as exc:
            return {"type": "shell", "command": source.command, "error": str(exc)}
