#!/usr/bin/env bash
# Executor role: calls a configurable coding agent to apply the plan.
#
# Reads executor_input.json (--input), writes executor_output.json (--output).
# Coding agent is selected via `coding_agent.tool` in config.json (same run dir).
# Supported tools: aider | claude-code
#
# Usage: executor.sh --input <path> --output <path> --worktree <path>
set -euo pipefail

INPUT="" OUTPUT="" WORKTREE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)    INPUT="$2";    shift 2 ;;
    --output)   OUTPUT="$2";   shift 2 ;;
    --worktree) WORKTREE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$INPUT" && -n "$OUTPUT" && -n "$WORKTREE" ]] || { echo "missing required args" >&2; exit 1; }

RUN_DIR="$(dirname "$INPUT")"

# Load plan
PLAN_PATH="$(python3 -c "import json,sys; d=json.load(open('$INPUT')); print(d.get('plan_path',''))" 2>/dev/null || echo "")"
if [[ -z "$PLAN_PATH" || ! -f "$PLAN_PATH" ]]; then
  PLAN_PATH="$RUN_DIR/plan.json"
fi
SUMMARY="$(python3 -c "import json; d=json.load(open('$PLAN_PATH')); print(d.get('summary','improve the codebase'))" 2>/dev/null || echo "improve the codebase")"
STEPS="$(python3 -c "import json; d=json.load(open('$PLAN_PATH')); print('\n'.join(d.get('steps',[])) or 'Apply the plan.')" 2>/dev/null || echo "Apply the plan.")"

# Load coding agent tool from config.json
TOOL="aider"
CONFIG_PATH="$RUN_DIR/config.json"
if [[ -f "$CONFIG_PATH" ]]; then
  TOOL="$(python3 -c "import json; d=json.load(open('$CONFIG_PATH')); print(d.get('coding_agent',{}).get('tool','aider'))" 2>/dev/null || echo "aider")"
fi

PROMPT="$SUMMARY

Steps:
$STEPS

Important: only modify files within the allowed paths specified in the plan."

cd "$WORKTREE"

case "$TOOL" in
  aider)
    aider --message "$PROMPT" --yes --no-pretty --auto-commits=false 2>&1 || true
    ;;
  claude-code)
    claude -p "$PROMPT" 2>&1 || true
    ;;
  *)
    echo "error: unknown coding_agent.tool: $TOOL" >&2
    exit 1
    ;;
esac

CHANGED=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
python3 -c "
import json
print(json.dumps({'changed_files': $CHANGED, 'tool': '$TOOL', 'summary': '''$SUMMARY'''}, indent=2))
" > "$OUTPUT"
