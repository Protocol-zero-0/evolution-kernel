from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class EvidenceSource:
    type: str
    path: str | None = None
    command: str | None = None


@dataclass(frozen=True)
class MutationScope:
    allowed_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class HardStopConfig:
    max_iterations: int = 0
    max_consecutive_failures: int = 0


@dataclass(frozen=True)
class RolesConfig:
    planner: tuple[str, ...]
    executor: tuple[str, ...]
    evaluator: tuple[str, ...]


@dataclass(frozen=True)
class EvolutionConfig:
    mission: str
    evidence_sources: tuple[EvidenceSource, ...]
    mutation_scope: MutationScope
    hard_stops: HardStopConfig
    roles: RolesConfig | None


def load_config(path: Path) -> EvolutionConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"config file must be a YAML mapping, got {type(raw).__name__}: {path}")
    data: dict[str, Any] = raw

    try:
        sources = tuple(
            EvidenceSource(
                type=s["type"],
                path=s.get("path"),
                command=s.get("command"),
            )
            for s in data.get("evidence_sources", [])
        )
    except KeyError as exc:
        raise ValueError(f"evidence_source entry missing required key {exc} in {path}") from exc

    scope_data = data.get("mutation_scope", {})
    scope = MutationScope(
        allowed_paths=tuple(scope_data.get("allowed_paths", [])),
    )

    stops_data = data.get("hard_stops", {})
    try:
        stops = HardStopConfig(
            max_iterations=int(stops_data.get("max_iterations", 0)),
            max_consecutive_failures=int(stops_data.get("max_consecutive_failures", 0)),
        )
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid hard_stops value in {path}: {exc}") from exc

    roles_data = data.get("roles")
    roles: RolesConfig | None = None
    if roles_data:
        try:
            roles = RolesConfig(
                planner=tuple(roles_data["planner"]),
                executor=tuple(roles_data["executor"]),
                evaluator=tuple(roles_data["evaluator"]),
            )
        except KeyError as exc:
            raise ValueError(f"roles block missing required key {exc} in {path}") from exc

    return EvolutionConfig(
        mission=str(data.get("mission", "")),
        evidence_sources=sources,
        mutation_scope=scope,
        hard_stops=stops,
        roles=roles,
    )
