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
    planner: list[str]
    executor: list[str]
    evaluator: list[str]


@dataclass(frozen=True)
class EvolutionConfig:
    mission: str
    evidence_sources: tuple[EvidenceSource, ...]
    mutation_scope: MutationScope
    hard_stops: HardStopConfig
    roles: RolesConfig | None


def load_config(path: Path) -> EvolutionConfig:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    sources = tuple(
        EvidenceSource(
            type=s["type"],
            path=s.get("path"),
            command=s.get("command"),
        )
        for s in data.get("evidence_sources", [])
    )

    scope_data = data.get("mutation_scope", {})
    scope = MutationScope(
        allowed_paths=tuple(scope_data.get("allowed_paths", [])),
    )

    stops_data = data.get("hard_stops", {})
    stops = HardStopConfig(
        max_iterations=int(stops_data.get("max_iterations", 0)),
        max_consecutive_failures=int(stops_data.get("max_consecutive_failures", 0)),
    )

    roles_data = data.get("roles")
    roles: RolesConfig | None = None
    if roles_data:
        roles = RolesConfig(
            planner=list(roles_data["planner"]),
            executor=list(roles_data["executor"]),
            evaluator=list(roles_data["evaluator"]),
        )

    return EvolutionConfig(
        mission=str(data.get("mission", "")),
        evidence_sources=sources,
        mutation_scope=scope,
        hard_stops=stops,
        roles=roles,
    )
