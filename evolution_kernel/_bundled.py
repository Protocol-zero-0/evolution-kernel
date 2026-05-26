"""Resolve `bundled:<filename>` argv entries to absolute paths inside the wheel.

The reference roles ship inside the installed package at
`evolution_kernel/roles/`. Templates and example configs reference them
through the `bundled:` prefix so the same config works for both
`pip install evolution-kernel` users and `git clone` developers.
"""
from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path

BUNDLED_PREFIX = "bundled:"


def resolve_bundled(arg: str) -> str:
    """If `arg` starts with `bundled:`, return the absolute path to the
    matching file inside `evolution_kernel/roles/`. Otherwise return `arg`
    unchanged.

    Raises FileNotFoundError when the prefix is used but the file does
    not exist in the bundle (clearer signal than a downstream
    `subprocess` error).
    """
    if not arg.startswith(BUNDLED_PREFIX):
        return arg
    name = arg[len(BUNDLED_PREFIX):]
    if not name or "/" in name or "\\" in name:
        raise ValueError(
            f"bundled: prefix takes a bare filename, got {arg!r}"
        )
    resource = files("evolution_kernel").joinpath("roles", name)
    with as_file(resource) as path:
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(
                f"bundled role {name!r} not found in evolution_kernel.roles "
                f"(looked at {resolved})"
            )
        return str(resolved.resolve())
