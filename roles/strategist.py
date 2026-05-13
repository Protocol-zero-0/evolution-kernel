#!/usr/bin/env python3
"""Strategist role.

Reads strategist_input.json, calls an LLM to produce a high-level strategy
(current stage, next milestone, taboo directions), and writes strategy.json.

LLM provider/model are read from config.json in the same run directory (same
pattern as roles/planner.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def _call_anthropic(prompt: str, model: str, api_key_env: str) -> str:
    import anthropic  # type: ignore
    client = anthropic.Anthropic(api_key=os.environ[api_key_env])
    msg = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _call_openai(prompt: str, model: str, api_key_env: str) -> str:
    import openai  # type: ignore
    client = openai.OpenAI(api_key=os.environ[api_key_env])
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--worktree", required=True)
    args = parser.parse_args()

    inp = json.loads(Path(args.input).read_text(encoding="utf-8"))

    run_dir = Path(args.input).parent
    cfg = {}
    config_path = run_dir / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "anthropic")
    model = llm_cfg.get("model", "claude-sonnet-4-6")
    api_key_env = llm_cfg.get("api_key_env", "ANTHROPIC_API_KEY")

    mission = inp.get("mission", "")
    current_round = inp.get("current_round", 0)
    latest_eval = inp.get("latest_evaluation", {})
    metrics = latest_eval.get("metrics", {})

    prompt = f"""You are a strategist for an automated code evolution system.

Mission: {mission}
Current round: {current_round}
Latest metrics: {json.dumps(metrics)}

Assess the current evolution stage and produce a strategy for the next phase.

Respond with ONLY a JSON object:
- "stage": name of the current evolution stage (e.g. "exploration", "refinement", "convergence")
- "next_milestone": one concrete measurable milestone to reach next
- "taboo_directions": list of approaches that have failed or should be avoided
"""

    if provider == "anthropic":
        text = _call_anthropic(prompt, model, api_key_env)
    elif provider == "openai":
        text = _call_openai(prompt, model, api_key_env)
    else:
        print(f"error: unknown llm.provider: {provider!r}", file=sys.stderr)
        sys.exit(1)

    m = re.search(r"\{.*\}", text, re.DOTALL)
    result = None
    if m:
        try:
            result = json.loads(m.group())
        except json.JSONDecodeError:
            pass
    if result is None:
        result = {"stage": "unknown", "next_milestone": text[:200], "taboo_directions": []}

    result.setdefault("stage", "unknown")
    result.setdefault("next_milestone", "")
    result.setdefault("taboo_directions", [])

    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
