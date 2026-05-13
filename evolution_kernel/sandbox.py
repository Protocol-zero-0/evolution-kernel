"""Process-level sandbox for the executor role.

The kernel already relies on a git worktree to isolate experimental commits and
a post-hoc ``scope`` check to keep ``evolution/accepted`` from advancing on
out-of-bounds writes. Neither of those stops an executor *process* from
writing to ``/tmp``, ``~/.ssh``, or anywhere else on disk during a round.

This module fills that gap by wrapping the executor's argv with a sandbox
launcher (currently firejail) that mounts the rest of the filesystem
read-only and grants writable access only to the worktree and the run-specific
ledger directory.

Design constraints honored here:

- Pure stdlib — no new third-party dependency added to the kernel.
- The wrapper is a single pure function that produces a new argv list; the
  governor is the only caller, and it remains responsible for spawning the
  process and surfacing stderr.
- When ``SandboxConfig.enabled`` is ``False`` the input argv is returned
  unchanged, so disabling the sandbox is bit-for-bit identical to the v0.3
  behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


SUPPORTED_BACKENDS = ("firejail",)


@dataclass(frozen=True)
class SandboxConfig:
    """Configuration controlling how (if at all) the executor is sandboxed."""

    enabled: bool = False
    backend: str = "firejail"
    extra_args: tuple[str, ...] = field(default_factory=tuple)


class SandboxError(RuntimeError):
    """Raised when the requested sandbox backend cannot be used."""


def wrap_argv(
    argv: Sequence[str],
    *,
    worktree: Path | str,
    writable: Iterable[Path | str] = (),
    config: SandboxConfig | None = None,
) -> list[str]:
    """Return ``argv`` wrapped by the configured sandbox launcher.

    When ``config`` is ``None`` or ``config.enabled`` is false, the original
    argv is returned as a plain ``list``. When enabled, the launcher mounts
    the entire filesystem read-only and re-mounts ``worktree`` plus every
    path in ``writable`` as read-write. Any additional ``extra_args``
    declared in the config are appended to the launcher flags before the
    ``--`` separator.
    """
    if config is None or not config.enabled:
        return list(argv)
    if config.backend not in SUPPORTED_BACKENDS:
        raise SandboxError(
            f"unsupported sandbox backend: {config.backend!r}; "
            f"supported: {', '.join(SUPPORTED_BACKENDS)}"
        )
    if config.backend == "firejail":
        return _firejail_wrap(argv, worktree, writable, config.extra_args)
    # Defensive: SUPPORTED_BACKENDS gate above keeps this unreachable.
    raise SandboxError(f"backend not implemented: {config.backend!r}")


def _firejail_wrap(
    argv: Sequence[str],
    worktree: Path | str,
    writable: Iterable[Path | str],
    extra_args: Sequence[str],
) -> list[str]:
    worktree_abs = str(Path(worktree).resolve())
    prefix: list[str] = [
        "firejail",
        "--quiet",
        "--noprofile",
        "--read-only=/",
        f"--read-write={worktree_abs}",
    ]
    seen = {worktree_abs}
    for w in writable:
        abs_path = str(Path(w).resolve())
        if abs_path in seen:
            continue
        seen.add(abs_path)
        prefix.append(f"--read-write={abs_path}")
    prefix.extend(extra_args)
    prefix.append("--")
    prefix.extend(argv)
    return prefix
