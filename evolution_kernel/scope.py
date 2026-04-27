"""Mutation scope enforcement.

Compares a candidate's changed files against a configured ``allowed_paths``
list. Any change outside the declared scope is a hard reject (``scope_violation``).

``allowed_paths`` entries follow simple semantics:

* ending with ``/`` denotes a directory prefix (e.g. ``src/`` allows any file
  under ``src/``);
* otherwise the entry must equal the changed path exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ScopeReport:
    ok: bool
    changed_files: tuple[str, ...]
    violations: tuple[str, ...]
    allowed_paths: tuple[str, ...]


def check_scope(changed_files: Sequence[str], allowed_paths: Sequence[str]) -> ScopeReport:
    """Validate ``changed_files`` against ``allowed_paths``."""
    cleaned_changed = tuple(_normalize(p) for p in changed_files if p and p.strip())
    cleaned_allowed = tuple(_normalize(p) for p in allowed_paths if p and p.strip())

    if not cleaned_allowed:
        # Empty scope means no mutation is allowed at all.
        return ScopeReport(
            ok=not cleaned_changed,
            changed_files=cleaned_changed,
            violations=cleaned_changed,
            allowed_paths=cleaned_allowed,
        )

    violations = tuple(p for p in cleaned_changed if not _matches_any(p, cleaned_allowed))
    return ScopeReport(
        ok=not violations,
        changed_files=cleaned_changed,
        violations=violations,
        allowed_paths=cleaned_allowed,
    )


def _normalize(path: str) -> str:
    s = path.strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


def _matches_any(file_path: str, allowed: Sequence[str]) -> bool:
    if ".." in file_path.split("/"):
        return False  # never accept escapes, even if a prefix would technically match
    for entry in allowed:
        if entry.endswith("/"):
            prefix = entry.rstrip("/")
            if file_path == prefix:
                continue  # directory itself is not a file change
            if file_path.startswith(prefix + "/"):
                return True
        else:
            if file_path == entry:
                return True
    return False
