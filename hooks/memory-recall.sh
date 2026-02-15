#!/usr/bin/env bash
# Recall important memories at session start
# Called by Claude Code SessionStart hook

MEMORY_SCRIPT="$HOME/.claude/skills/zvec-memory/scripts/memory.py"

# Skip if memory script doesn't exist
[ -f "$MEMORY_SCRIPT" ] || exit 0

# Get current directory context for a relevant query
CWD=$(pwd)
PROJECT_NAME=$(basename "$CWD")

# Query for high-importance memories relevant to the current context
RESULT=$(python3 "$MEMORY_SCRIPT" query \
  --text "important context preferences instructions for $PROJECT_NAME" \
  --topk 10 \
  --min-importance 0.5 \
  2>/dev/null)

# Only output if we got results with memories
if echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('count',0)>0 else 1)" 2>/dev/null; then
  echo "$RESULT"
fi
