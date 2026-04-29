#!/usr/bin/env bash
echo "status: ready"
echo "score: $(python3 -c "import json,pathlib; d=json.loads(pathlib.Path('metrics.json').read_text()); print(d.get('score',0))" 2>/dev/null || echo 0)"
