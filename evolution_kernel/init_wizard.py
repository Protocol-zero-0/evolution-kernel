"""Interactive `evolution-kernel init` — 3 questions, drops a valid evolution.yml.

No interactive prompt libraries. No template base class. No Python template
generator. Templates are plain YAML files under `evolution_kernel/templates/`
with `{{mission}}` and `{{allowed_paths_yaml}}` placeholders substituted via
str.replace before the result is fed through `load_config` for validation.
"""
from __future__ import annotations

import sys
from importlib.resources import files
from pathlib import Path

from .config import ConfigError, load_config

TEMPLATES = ("lint", "coverage", "perf", "benchmark", "custom")


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw or (default or "")


def _render(name: str, mission: str, allowed_paths: list[str]) -> str:
    body = files("evolution_kernel.templates").joinpath(f"{name}.yml").read_text(encoding="utf-8")
    paths_yaml = "\n".join(f"    - \"{p}\"" for p in allowed_paths) or "    []"
    return body.replace("{{mission}}", mission.replace('"', '\\"')).replace(
        "{{allowed_paths_yaml}}", paths_yaml
    )


def main(argv: list[str] | None = None) -> int:
    out_path = Path("evolution.yml")
    if out_path.exists():
        print(f"error: {out_path} already exists — remove it or run init in an empty dir", file=sys.stderr)
        return 2

    print("evolution-kernel init — 3 questions, drops ./evolution.yml")
    mission = _ask("1) Mission (one sentence)", "Improve the target codebase toward its goal")

    print("2) Template:")
    for i, name in enumerate(TEMPLATES, start=1):
        print(f"   {i}. {name}")
    pick_raw = _ask("   Pick 1-5", "1")
    try:
        idx = int(pick_raw)
        template = TEMPLATES[idx - 1]
    except (ValueError, IndexError):
        print(f"error: not a valid template choice: {pick_raw!r}", file=sys.stderr)
        return 2

    paths_raw = _ask("3) Allowed mutation paths (comma-separated)", "src/")
    allowed_paths = [p.strip() for p in paths_raw.split(",") if p.strip()]
    if not allowed_paths:
        print("error: at least one allowed path is required", file=sys.stderr)
        return 2

    rendered = _render(template, mission, allowed_paths)
    out_path.write_text(rendered, encoding="utf-8")

    try:
        load_config(str(out_path))
    except ConfigError as e:
        out_path.unlink(missing_ok=True)
        print(f"error: rendered template did not validate ({e}) — please file a bug", file=sys.stderr)
        return 1

    print(f"\nwrote {out_path.resolve()} (template: {template})")
    print("next:")
    print("  evolution-kernel --config evolution.yml --repo /path/to/target --ledger /tmp/ledger --loop")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
