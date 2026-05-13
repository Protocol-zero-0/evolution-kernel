"""Evolution Kernel configuration loader.

Loads and validates a small YAML schema:

    mission: "free-text statement of intent"

    llm:
      provider: anthropic        # anthropic | openai
      model: claude-sonnet-4-6
      api_key_env: ANTHROPIC_API_KEY

    coding_agent:
      tool: aider                # aider | claude-code

    history:
      max_entries: 10

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
      max_iterations: 10
      max_consecutive_failures: 3
      max_total_usd: 1.00        # 0.0 = unlimited
      max_total_tokens: 500000   # 0 = unlimited

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
    max_total_usd: float = 0.0    # 0.0 = unlimited
    max_total_tokens: int = 0     # 0 = unlimited


@dataclass(frozen=True)
class Roles:
    planner: tuple[str, ...] = ()
    executor: tuple[str, ...] = ()
    evaluator: tuple[str, ...] = ()
    goal_evaluator: tuple[str, ...] = ()
    strategist: tuple[str, ...] = ()


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "anthropic"          # anthropic | openai
    model: str = "claude-sonnet-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"


@dataclass(frozen=True)
class CodingAgentConfig:
    tool: str = "aider"                  # aider | claude-code


@dataclass(frozen=True)
class HistoryConfig:
    max_entries: int = 10


@dataclass(frozen=True)
class GoalEvaluatorConfig:
    enabled: bool = False


@dataclass(frozen=True)
class StrategistConfig:
    enabled: bool = False
    every_n_rounds: int = 3


@dataclass(frozen=True)
class EvolutionConfig:
    mission: str
    evidence_sources: tuple[EvidenceSource, ...] = ()
    mutation_scope: MutationScope = field(default_factory=MutationScope)
    hard_stops: HardStops = field(default_factory=HardStops)
    roles: Roles = field(default_factory=Roles)
    llm: LLMConfig = field(default_factory=LLMConfig)
    coding_agent: CodingAgentConfig = field(default_factory=CodingAgentConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    goal_evaluator: GoalEvaluatorConfig = field(default_factory=GoalEvaluatorConfig)
    strategist: StrategistConfig = field(default_factory=StrategistConfig)
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
    roles = _parse_roles(raw.get("roles", {}))
    llm = _parse_llm(raw.get("llm", {}))
    coding_agent = _parse_coding_agent(raw.get("coding_agent", {}))
    history = _parse_history(raw.get("history", {}))
    goal_evaluator = _parse_goal_evaluator(raw.get("goal_evaluator", {}))
    strategist = _parse_strategist(raw.get("strategist", {}))

    return EvolutionConfig(
        mission=mission.strip(),
        evidence_sources=evidence_sources,
        mutation_scope=mutation_scope,
        hard_stops=hard_stops,
        roles=roles,
        llm=llm,
        coding_agent=coding_agent,
        history=history,
        goal_evaluator=goal_evaluator,
        strategist=strategist,
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


def _parse_roles(value: Any) -> Roles:
    if not isinstance(value, Mapping):
        raise ConfigError("`roles` must be a mapping")
    if not value:
        return Roles()

    def _argv(label: str) -> tuple[str, ...]:
        v = value.get(label)
        if v is None:
            return ()
        if isinstance(v, str):
            return (v,)
        if isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v):
            return tuple(x.strip() for x in v)
        raise ConfigError(
            f"`roles.{label}` must be a string or a list of non-empty strings"
        )

    return Roles(
        planner=_argv("planner"),
        executor=_argv("executor"),
        evaluator=_argv("evaluator"),
        goal_evaluator=_argv("goal_evaluator"),
        strategist=_argv("strategist"),
    )


def _parse_hard_stops(value: Any) -> HardStops:
    if not isinstance(value, Mapping):
        raise ConfigError("`hard_stops` must be a mapping")
    max_iterations = value.get("max_iterations", 1)
    max_failures = value.get("max_consecutive_failures", 1)
    for label, n in (("max_iterations", max_iterations), ("max_consecutive_failures", max_failures)):
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ConfigError(f"`hard_stops.{label}` must be a positive integer, got {n!r}")
    usd_raw = value.get("max_total_usd", 0.0)
    tok_raw = value.get("max_total_tokens", 0)
    try:
        max_total_usd = float(usd_raw)
    except (TypeError, ValueError):
        raise ConfigError(f"`hard_stops.max_total_usd` must be a number, got {usd_raw!r}")
    try:
        max_total_tokens = int(tok_raw)
    except (TypeError, ValueError):
        raise ConfigError(f"`hard_stops.max_total_tokens` must be an integer, got {tok_raw!r}")
    if max_total_usd < 0:
        raise ConfigError("`hard_stops.max_total_usd` must be >= 0")
    if max_total_tokens < 0:
        raise ConfigError("`hard_stops.max_total_tokens` must be >= 0")
    return HardStops(
        max_iterations=max_iterations,
        max_consecutive_failures=max_failures,
        max_total_usd=max_total_usd,
        max_total_tokens=max_total_tokens,
    )


def _parse_llm(value: Any) -> LLMConfig:
    if not isinstance(value, Mapping):
        raise ConfigError("`llm` must be a mapping")
    provider = value.get("provider", "anthropic")
    model = value.get("model", "claude-sonnet-4-6")
    api_key_env = value.get("api_key_env", "ANTHROPIC_API_KEY")
    for label, v in (("provider", provider), ("model", model), ("api_key_env", api_key_env)):
        if not isinstance(v, str) or not v.strip():
            raise ConfigError(f"`llm.{label}` must be a non-empty string")
    return LLMConfig(provider=provider.strip(), model=model.strip(), api_key_env=api_key_env.strip())


def _parse_coding_agent(value: Any) -> CodingAgentConfig:
    if not isinstance(value, Mapping):
        raise ConfigError("`coding_agent` must be a mapping")
    tool = value.get("tool", "aider")
    if not isinstance(tool, str) or not tool.strip():
        raise ConfigError("`coding_agent.tool` must be a non-empty string")
    return CodingAgentConfig(tool=tool.strip())


def _parse_history(value: Any) -> HistoryConfig:
    if not isinstance(value, Mapping):
        raise ConfigError("`history` must be a mapping")
    max_entries = value.get("max_entries", 10)
    if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
        raise ConfigError("`history.max_entries` must be a positive integer")
    return HistoryConfig(max_entries=max_entries)


def _parse_goal_evaluator(value: Any) -> GoalEvaluatorConfig:
    if not isinstance(value, Mapping):
        raise ConfigError("`goal_evaluator` must be a mapping")
    return GoalEvaluatorConfig(enabled=bool(value.get("enabled", False)))


def _parse_strategist(value: Any) -> StrategistConfig:
    if not isinstance(value, Mapping):
        raise ConfigError("`strategist` must be a mapping")
    every_n = value.get("every_n_rounds", 3)
    if not isinstance(every_n, int) or isinstance(every_n, bool) or every_n < 1:
        raise ConfigError("`strategist.every_n_rounds` must be a positive integer")
    return StrategistConfig(enabled=bool(value.get("enabled", False)), every_n_rounds=every_n)
