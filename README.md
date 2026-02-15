# zvec-agent-memory

Persistent long-term memory for AI agents using Alibaba's [zvec](https://github.com/alibaba/zvec) embedded vector database. Store facts, preferences, decisions, errors, and patterns as vector-embedded memories, then retrieve them via semantic search across sessions.

Built as a [Claude Code skill](https://docs.anthropic.com/en/docs/claude-code/skills) — fully self-bootstrapping with zero manual setup.

## Features

- **Semantic search** — find memories by meaning, not keywords
- **Auto-bootstrap** — dependencies, Ollama, models, and store all set up on first use
- **Ollama + OpenAI** — uses local `nomic-embed-text` by default, falls back to OpenAI
- **Per-project or global** — stores scoped to git repos, with a global fallback
- **JSON output** — machine-parseable by agents, progress on stderr

## Quick Start

### Install the skill

```bash
cp -r skill/ ~/.claude/skills/zvec-memory
```

### (Optional) Install the session hook

Automatically recalls relevant memories at the start of each Claude Code session:

```bash
mkdir -p ~/.claude/hooks
cp hooks/memory-recall.sh ~/.claude/hooks/memory-recall.sh
chmod +x ~/.claude/hooks/memory-recall.sh
```

Then add to `~/.claude/settings.json`:

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

### Manual usage

```bash
# Store a memory
python3 ~/.claude/skills/zvec-memory/scripts/memory.py store \
  --content "User prefers dark mode" --category preference --importance 0.9

# Search memories
python3 ~/.claude/skills/zvec-memory/scripts/memory.py query --text "theme preferences"

# List all memories
python3 ~/.claude/skills/zvec-memory/scripts/memory.py list

# Stats
python3 ~/.claude/skills/zvec-memory/scripts/memory.py stats
```

## Memory Categories

| Category | Use Case |
|---|---|
| `fact` | Objective project/user facts |
| `preference` | User likes/dislikes |
| `decision` | Choices made with rationale |
| `error` | Errors and their resolutions |
| `pattern` | Recurring code/workflow patterns |
| `instruction` | Behavioral directives from user |
| `context` | Environmental/situational info |
| `conversation` | Notable interaction insights |

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai) (auto-started if installed) or `OPENAI_API_KEY`

### zvec AVX-512 Workaround

The pre-built zvec wheels require AVX-512 CPU instructions. If you get an "Illegal instruction" crash on import, build from source targeting your CPU architecture:

```bash
git clone --recurse-submodules https://github.com/alibaba/zvec.git
cd zvec
pip install -C cmake.define.ENABLE_ZEN3=ON .    # AMD Zen 3 (Ryzen 5000)
```

Replace `ENABLE_ZEN3` with the flag matching your CPU:

| Flag | CPU Family |
|---|---|
| `ENABLE_ZEN3=ON` | AMD Zen 3 (Ryzen 5000, EPYC 7003) |
| `ENABLE_ZEN2=ON` | AMD Zen 2 (Ryzen 3000, EPYC 7002) |
| `ENABLE_ZEN1=ON` | AMD Zen/Zen+ (Ryzen 1000/2000) |
| `ENABLE_HASWELL=ON` | Intel Haswell (4th gen Core) |
| `ENABLE_BROADWELL=ON` | Intel Broadwell (5th gen Core) |
| `ENABLE_SKYLAKE=ON` | Intel Skylake (6th-7th gen Core) |
| `ENABLE_SKYLAKE_AVX512=ON` | Intel Skylake-X / Xeon (AVX-512 capable) |

See `references/advanced.md` in the skill for more troubleshooting.

## Project Structure

```
├── hooks/
│   ├── memory-recall.sh     # SessionStart hook for auto-recall
│   └── README.md            # Hook setup instructions
└── skill/
    ├── SKILL.md             # Skill definition + behavioral instructions
    ├── requirements.txt     # Python dependencies
    ├── scripts/
    │   ├── memory.py        # Main CLI (store, query, list, stats, update, delete, init)
    │   ├── embeddings.py    # Embedding provider abstraction (Ollama/OpenAI)
    │   └── setup.py         # Auto-bootstrap module
    └── references/
        └── advanced.md      # Migration, recovery, tuning, troubleshooting
```

## License

Apache 2.0
