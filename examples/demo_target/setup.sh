#!/usr/bin/env bash
# Initialise the demo target as a fresh git repo.
set -euo pipefail
cd "$(dirname "$0")"
git init -q
git add -A
git -c user.email=demo@example.com -c user.name="Demo" commit -q -m "demo target initial commit"
echo "demo target ready at $(pwd)"
