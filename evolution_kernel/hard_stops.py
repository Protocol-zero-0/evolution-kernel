"""Persistent circuit breaker for evolution runs.

State lives in a small JSON file (typically ``<ledger>/.evolution_state.json``)
so a triggered hard stop survives process restarts. ``reset`` clears the state.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping


STATE_FILENAME = ".evolution_state.json"


@dataclass
class HardStopState:
    iterations: int = 0
    consecutive_failures: int = 0
    halted: bool = False
    halt_reason: str | None = None

    def to_json(self) -> Mapping[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "HardStopState":
        return cls(
            iterations=int(data.get("iterations", 0)),
            consecutive_failures=int(data.get("consecutive_failures", 0)),
            halted=bool(data.get("halted", False)),
            halt_reason=data.get("halt_reason"),
        )


def state_path(ledger_dir: Path | str) -> Path:
    return Path(ledger_dir) / STATE_FILENAME


def load_state(ledger_dir: Path | str) -> HardStopState:
    p = state_path(ledger_dir)
    if not p.exists():
        return HardStopState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return HardStopState()
    if not isinstance(data, Mapping):
        return HardStopState()
    return HardStopState.from_json(data)


def save_state(ledger_dir: Path | str, state: HardStopState) -> None:
    p = state_path(ledger_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: a crash mid-write must not leave a truncated file that
    # silently resets the circuit breaker on the next load.
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def precheck(state: HardStopState, max_iterations: int, max_consecutive_failures: int) -> tuple[bool, str | None]:
    """Return (allowed, reason). reason is None when allowed."""
    if state.halted:
        return False, state.halt_reason or "halted"
    if state.iterations >= max_iterations:
        return False, f"max_iterations reached ({max_iterations})"
    if state.consecutive_failures >= max_consecutive_failures:
        return False, f"max_consecutive_failures reached ({max_consecutive_failures})"
    return True, None


def record_outcome(
    state: HardStopState,
    *,
    accepted: bool,
    max_iterations: int,
    max_consecutive_failures: int,
) -> HardStopState:
    """Update counters after a run; mark halted if any limit just tripped."""
    state.iterations += 1
    if accepted:
        state.consecutive_failures = 0
    else:
        state.consecutive_failures += 1
    if state.iterations >= max_iterations:
        state.halted = True
        state.halt_reason = f"max_iterations reached ({max_iterations})"
    elif state.consecutive_failures >= max_consecutive_failures:
        state.halted = True
        state.halt_reason = f"max_consecutive_failures reached ({max_consecutive_failures})"
    return state


def reset(ledger_dir: Path | str) -> bool:
    """Delete the persisted hard-stop state. Returns True if anything was removed."""
    p = state_path(ledger_dir)
    if p.exists():
        p.unlink()
        return True
    return False
