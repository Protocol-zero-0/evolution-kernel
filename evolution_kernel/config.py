"""Evolution Kernel configuration loader.

Loads and validates a small YAML schema:

    mission: "free-text statement of intent"

    evidence_sources:
      - type: file
        path: "./metrics.json"
      - type: shell
        command: "bash ./scripts/status.sh"

    mutation_scope:
      allowed_paths:
        - "src/"
        - "tests/"

    hard_stops:
      max_iterations: 3
      max_consecutive_failures: 2

Validation prefers human-readable errors over raw tracebacks so that bad configs
can be fixed without reading source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


class ConfigError(ValueError):
    """Raised when the YAML config does not match the expected shape."""


@dataclass(frozen=True)
class EvidenceSource:
    type: str  # "file" or "shell"
    path: str | None = None
    command: str | None = None


@dataclass(frozen=True)
class MutationScope:
    allowed_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class HardStops:
    max_iterations: int = 1
    max_consecutive_failures: int = 1


@dataclass(frozen=True)
class EvolutionConfig:
    mission: str
    evidence_sources: tuple[EvidenceSource, ...] = ()
    mutation_scope: MutationScope = field(default_factory=MutationScope)
    hard_stops: HardStops = field(default_factory=HardStops)
    raw: Mapping[str, Any] = field(default_factory=dict)


def load_config(path: Path | str) -> EvolutionConfig:
    """Read a YAML file from disk and return a validated EvolutionConfig."""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"could not parse YAML in {p}: {exc}") from exc
    if raw is None:
        raise ConfigError(f"config file is empty: {p}")
    if not isinstance(raw, Mapping):
        raise ConfigError(f"config root must be a mapping, got {type(raw).__name__}")
    return parse_config(raw)


def parse_config(raw: Mapping[str, Any]) -> EvolutionConfig:
    """Validate an in-memory mapping and return a typed EvolutionConfig."""
    mission = raw.get("mission")
    if not isinstance(mission, str) or not mission.strip():
        raise ConfigError("`mission` is required and must be a non-empty string")

    evidence_sources = tuple(_parse_evidence_sources(raw.get("evidence_sources", [])))
    mutation_scope = _parse_mutation_scope(raw.get("mutation_scope", {}))
    hard_stops = _parse_hard_stops(raw.get("hard_stops", {}))

    return EvolutionConfig(
        mission=mission.strip(),
        evidence_sources=evidence_sources,
        mutation_scope=mutation_scope,
        hard_stops=hard_stops,
        raw=dict(raw),
    )


def _parse_evidence_sources(value: Any) -> Sequence[EvidenceSource]:
    if not isinstance(value, list):
        raise ConfigError("`evidence_sources` must be a list (may be empty)")
    sources: list[EvidenceSource] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ConfigError(f"evidence_sources[{index}] must be a mapping")
        kind = item.get("type")
        if kind == "file":
            path = item.get("path")
            if not isinstance(path, str) or not path.strip():
                raise ConfigError(
                    f"evidence_sources[{index}] type=file requires a non-empty `path`"
                )
            sources.append(EvidenceSource(type="file", path=path.strip()))
        elif kind == "shell":
            command = item.get("command")
            if not isinstance(command, str) or not command.strip():
                raise ConfigError(
                    f"evidence_sources[{index}] type=shell requires a non-empty `command`"
                )
            sources.append(EvidenceSource(type="shell", command=command.strip()))
        else:
            raise ConfigError(
                f"evidence_sources[{index}].type must be 'file' or 'shell', got {kind!r}"
            )
    return sources


def _parse_mutation_scope(value: Any) -> MutationScope:
    if not isinstance(value, Mapping):
        raise ConfigError("`mutation_scope` must be a mapping")
    allowed_paths = value.get("allowed_paths", [])
    if not isinstance(allowed_paths, list):
        raise ConfigError("`mutation_scope.allowed_paths` must be a list")
    cleaned: list[str] = []
    for index, entry in enumerate(allowed_paths):
        if not isinstance(entry, str) or not entry.strip():
            raise ConfigError(
                f"mutation_scope.allowed_paths[{index}] must be a non-empty string"
            )
        cleaned.append(entry.strip())
    return MutationScope(allowed_paths=tuple(cleaned))


def _parse_hard_stops(value: Any) -> HardStops:
    if not isinstance(value, Mapping):
        raise ConfigError("`hard_stops` must be a mapping")
    max_iterations = value.get("max_iterations", 1)
    max_failures = value.get("max_consecutive_failures", 1)
    for label, n in (("max_iterations", max_iterations), ("max_consecutive_failures", max_failures)):
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ConfigError(f"`hard_stops.{label}` must be a positive integer, got {n!r}")
    return HardStops(max_iterations=max_iterations, max_consecutive_failures=max_failures)
