#!/usr/bin/env python3
"""LLM planner role.

Reads planner_input.json, calls an LLM to produce a plan, writes plan.json.
LLM provider/model are read from config.json in the same run directory.

Config keys used (under `llm:`):
    provider:    anthropic (default) | openai
    model:       e.g. claude-sonnet-4-6 or gpt-4o
    api_key_env: name of the env var holding the API key
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def _call_anthropic(prompt: str, model: str, api_key_env: str) -> tuple[str, int, float]:
    import anthropic  # type: ignore
    client = anthropic.Anthropic(api_key=os.environ[api_key_env])
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    tokens = msg.usage.input_tokens + msg.usage.output_tokens
    # Approximate cost — exact pricing varies by model; callers may override.
    cost = tokens * 3e-6
    return msg.content[0].text, tokens, cost


def _call_openai(prompt: str, model: str, api_key_env: str) -> tuple[str, int, float]:
    import openai  # type: ignore
    client = openai.OpenAI(api_key=os.environ[api_key_env])
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    tokens = resp.usage.total_tokens
    cost = tokens * 3e-6
    return resp.choices[0].message.content, tokens, cost


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--worktree", required=True)
    args = parser.parse_args()

    inp = json.loads(Path(args.input).read_text(encoding="utf-8"))

    # Load LLM config from run-dir config.json (written by governor).
    run_dir = Path(args.input).parent
    cfg = {}
    config_path = run_dir / "config.json"
    if config_path.exists():
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    llm_cfg = cfg.get("llm", {})
    provider = llm_cfg.get("provider", "anthropic")
    model = llm_cfg.get("model", "claude-sonnet-4-6")
    api_key_env = llm_cfg.get("api_key_env", "ANTHROPIC_API_KEY")

    goal = inp.get("goal", {})
    allowed_paths = inp.get("allowed_paths", [])
    history = inp.get("history", [])

    obs_text = ""
    obs_path = inp.get("observation_path", "")
    if obs_path and Path(obs_path).exists():
        obs_text = Path(obs_path).read_text(encoding="utf-8")

    history_text = "\n".join(
        f"- Run {h['run_id']}: {'ACCEPTED' if h.get('accepted') else 'REJECTED'} — {h.get('summary', '')}"
        for h in history
    ) or "(no history yet — this is the first run)"

    prompt = f"""You are a code evolution planner. Produce a concrete plan to make progress toward the goal.

Goal: {goal.get("objective", goal.get("name", ""))}

Current observation:
{obs_text or "(none)"}

Allowed paths (ONLY modify files under these paths):
{json.dumps(allowed_paths)}

Previous attempts:
{history_text}

Respond with ONLY a JSON object containing:
- "summary": one-line description of the change
- "steps": list of concrete implementation steps
- "expected_improvement": what should improve after this change
- "allowed_paths": paths to be modified (must be a subset of the allowed list above)
- "abort": false  (set true only if you have absolutely no viable approach)
"""

    if provider == "anthropic":
        text, tokens, cost = _call_anthropic(prompt, model, api_key_env)
    elif provider == "openai":
        text, tokens, cost = _call_openai(prompt, model, api_key_env)
    else:
        print(f"error: unknown llm.provider: {provider!r}", file=sys.stderr)
        sys.exit(1)

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        plan = json.loads(m.group())
    else:
        plan = {
            "summary": text[:200],
            "steps": [text],
            "expected_improvement": "",
            "allowed_paths": allowed_paths,
            "abort": False,
        }

    plan.setdefault("run_id", inp.get("run_id", ""))
    plan.setdefault("abort", False)
    plan.setdefault("allowed_paths", allowed_paths)
    plan["_tokens_used"] = tokens
    plan["_cost_usd"] = cost

    Path(args.output).write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
