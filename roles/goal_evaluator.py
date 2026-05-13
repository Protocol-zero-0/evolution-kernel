#!/usr/bin/env python3
"""Goal evaluator role.

Reads goal_eval_input.json, calls an LLM to decide whether the overall mission
is complete, and writes goal_evaluation.json.

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
    latest_eval = inp.get("latest_evaluation", {})
    metrics = latest_eval.get("metrics", {})

    prompt = f"""You are a goal evaluator for an automated code evolution system.

Mission: {mission}

Latest evaluation metrics:
{json.dumps(metrics, indent=2)}

Based on the mission statement and the latest evaluation metrics, has the mission
been fully accomplished?

Respond with ONLY a JSON object:
- "goal_reached": true if the mission is fully accomplished, false otherwise
- "confidence": a float between 0.0 and 1.0
- "reason": one sentence explaining your decision
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
        result = {"goal_reached": False, "confidence": 0.0, "reason": text[:200]}

    result.setdefault("goal_reached", False)
    result.setdefault("confidence", 0.0)
    result.setdefault("reason", "")

    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
