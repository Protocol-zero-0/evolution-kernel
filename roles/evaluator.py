#!/usr/bin/env python3
"""LLM evaluator role.

Reads evaluator_input.json, calls an LLM to judge accept/reject, writes evaluation.json.
LLM provider/model are read from config.json in the same run directory.
Reports cost_usd and tokens_used so the kernel can enforce cost guards.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def _call_llm(prompt: str, cfg: dict) -> tuple[str, int, float]:
    provider = cfg.get("provider", "anthropic")
    model = cfg.get("model", "claude-sonnet-4-6")
    api_key_env = cfg.get("api_key_env", "ANTHROPIC_API_KEY")

    if provider == "anthropic":
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=os.environ[api_key_env])
        msg = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        tokens = msg.usage.input_tokens + msg.usage.output_tokens
        return msg.content[0].text, tokens, tokens * 3e-6

    if provider == "openai":
        import openai  # type: ignore
        client = openai.OpenAI(api_key=os.environ[api_key_env])
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        tokens = resp.usage.total_tokens
        return resp.choices[0].message.content, tokens, tokens * 3e-6

    raise ValueError(f"unknown llm.provider: {provider!r}")


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

    goal = inp.get("goal", {})
    patch_path = inp.get("patch_path", "")
    obs_path = inp.get("observation_path", "")

    patch_text = ""
    if patch_path and Path(patch_path).exists():
        patch_text = Path(patch_path).read_text(encoding="utf-8")[:3000]

    obs_text = ""
    if obs_path and Path(obs_path).exists():
        obs_text = Path(obs_path).read_text(encoding="utf-8")[:1000]

    prompt = f"""You are a code evolution evaluator. Decide whether to ACCEPT or REJECT a candidate change.

Goal: {goal.get("objective", goal.get("name", ""))}

Observation (current state):
{obs_text or "(none)"}

Patch applied:
{patch_text or "(no changes)"}

Respond with ONLY a JSON object:
- "hard_gates_passed": true if the change is safe and relevant, false otherwise
- "recommendation": "accept" or "reject"
- "fitness": a float in [0.0, 1.0] — how strongly the change advances the goal (used by
  k-branch parallel exploration to rank sibling branches)
- "reason": one sentence explaining your decision
- "metrics": {{}} (optional key/value metrics you can infer)
"""

    try:
        text, tokens, cost = _call_llm(prompt, llm_cfg)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            result = json.loads(m.group())
        else:
            result = {
                "hard_gates_passed": False,
                "recommendation": "reject",
                "reason": f"evaluator could not parse LLM response: {text[:100]}",
                "metrics": {},
            }
    except Exception as exc:
        result = {
            "hard_gates_passed": False,
            "recommendation": "reject",
            "reason": f"evaluator error: {exc}",
            "metrics": {},
        }
        tokens, cost = 0, 0.0

    result.setdefault("hard_gates_passed", False)
    result.setdefault("recommendation", "reject")
    result.setdefault("reason", "")
    result.setdefault("metrics", {})
    # Back-compat: derive fitness from hard_gates_passed when the evaluator
    # omitted it, so legacy evaluators keep working under k-branch ranking.
    if "fitness" not in result:
        result["fitness"] = 1.0 if result.get("hard_gates_passed") else 0.0
    else:
        try:
            result["fitness"] = float(result["fitness"])
        except (TypeError, ValueError):
            result["fitness"] = 0.0
    result["cost_usd"] = cost
    result["tokens_used"] = tokens

    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
