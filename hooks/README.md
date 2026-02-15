# Session Hook Setup

To automatically recall memories at the start of each Claude Code session, add the following to your `~/.claude/settings.json` under the `hooks` key:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash $HOME/.claude/hooks/memory-recall.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Then copy the hook script:

```bash
mkdir -p ~/.claude/hooks
cp hooks/memory-recall.sh ~/.claude/hooks/memory-recall.sh
chmod +x ~/.claude/hooks/memory-recall.sh
```

The hook queries the top 10 memories with importance >= 0.5 at session start, using the current project name as search context. It silently skips if no memories exist yet.
