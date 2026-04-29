from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import HardStopConfig

_STATE_FILE = "state.json"


class HardStopError(RuntimeError):
    pass


@dataclass
class _State:
    iterations: int = 0
    consecutive_failures: int = 0


class HardStopGuard:
    def __init__(self, ledger_dir: Path | str, config: HardStopConfig) -> None:
        self._path = Path(ledger_dir) / _STATE_FILE
        self._config = config

    def check(self) -> None:
        state = self._load()
        cfg = self._config
        if cfg.max_iterations > 0 and state.iterations >= cfg.max_iterations:
            raise HardStopError(
                f"max_iterations reached: {state.iterations} >= {cfg.max_iterations}"
            )
        if cfg.max_consecutive_failures > 0 and state.consecutive_failures >= cfg.max_consecutive_failures:
            raise HardStopError(
                f"max_consecutive_failures reached: "
                f"{state.consecutive_failures} >= {cfg.max_consecutive_failures}"
            )

    def record(self, accepted: bool) -> None:
        state = self._load()
        state.iterations += 1
        state.consecutive_failures = 0 if accepted else state.consecutive_failures + 1
        self._save(state)

    def reset(self) -> None:
        self._save(_State())

    def _load(self) -> _State:
        if not self._path.exists():
            return _State()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return _State(**data)

    def _save(self, state: _State) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
