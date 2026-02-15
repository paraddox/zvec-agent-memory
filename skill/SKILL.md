---
name: zvec-memory
description: Persistent long-term memory for AI agents using zvec vector database. Store facts, preferences, decisions, errors, and patterns as vector-embedded memories, then retrieve them via semantic search. Fully self-bootstrapping — zero manual setup required.
allowed-tools:
  - Bash
---

# zvec-memory

## Overview

Give yourself persistent memory across sessions. Store anything worth remembering — user preferences, decisions, error resolutions, project patterns — and recall it instantly via semantic search. Everything auto-bootstraps: dependencies install, Ollama starts, models pull, and the store initializes on first use.

## Zero Setup

**Everything is automatic.** Just call the scripts. On first run, `memory.py` will:
1. Install `zvec` and `requests` if missing
2. Start Ollama if not running (or fall back to OpenAI if `OPENAI_API_KEY` is set)
3. Pull `nomic-embed-text` model if not available
4. Initialize the memory store at the auto-detected path

No `init` command needed unless you want to customize the provider or dimension.

## When to Store Memories

Store memories **proactively** whenever you encounter:

| Trigger | Category | Example |
|---|---|---|
| User states a preference | `preference` | "I prefer tabs over spaces" |
| A decision is made | `decision` | "We chose PostgreSQL over MySQL for this project" |
| An error is resolved | `error` | "Fixed CORS by adding allowed origins to nginx config" |
| User corrects your behavior | `instruction` | "Don't add comments to obvious code" |
| You discover a project pattern | `pattern` | "This repo uses barrel exports in index.ts files" |
| Important context is shared | `context` | "The API is deployed on AWS us-east-1" |
| A notable fact is learned | `fact` | "The project uses Python 3.11 with FastAPI" |
| A conversation insight emerges | `conversation` | "User is building a CLI tool for data migration" |

**Importance guidelines:**
- `0.9-1.0` — Critical: user corrections, explicit preferences, breaking-change decisions
- `0.7-0.8` — High: project architecture, tech stack choices, recurring patterns
- `0.4-0.6` — Medium: general facts, context, one-time decisions
- `0.1-0.3` — Low: minor observations, temporary context

## When to Query Memories

Query memories **before** taking action:

- **Starting a new task**: What do I know about this project/user?
- **Making recommendations**: What has the user preferred before?
- **Proposing tech choices**: What decisions were made previously?
- **Encountering errors**: Have I seen this before? What fixed it?
- **Writing code**: What patterns does this project follow?

## Script API Quick Reference

All scripts are in the skill's `scripts/` directory. All output is JSON to stdout.

### Store a memory
```bash
python scripts/memory.py store \
  --content "User prefers dark mode in all applications" \
  --category preference \
  --tags ui theme \
  --importance 0.8 \
  --source "conversation on 2024-01-15"
```

### Query memories (semantic search)
```bash
python scripts/memory.py query \
  --text "what theme does the user prefer" \
  --topk 5 \
  --category preference
```

### List memories
```bash
python scripts/memory.py list --category fact --limit 10 --sort-by importance
```

### Get statistics
```bash
python scripts/memory.py stats
```

### Update a memory
```bash
python scripts/memory.py update --id mem_abc123 --importance 0.9
python scripts/memory.py update --id mem_abc123 --content "Updated content" --tags new-tag
```

### Delete a memory
```bash
python scripts/memory.py delete --id mem_abc123
```

### Initialize with custom settings
```bash
python scripts/memory.py init --provider openai --dimension 1536 --force
```

## Memory Categories

| Category | Use Case | Example Content |
|---|---|---|
| `fact` | Objective project/user facts | "Project uses monorepo with pnpm workspaces" |
| `preference` | User likes/dislikes | "User prefers functional React components over class" |
| `decision` | Choices made with rationale | "Chose Tailwind over styled-components for CSS" |
| `error` | Errors and their resolutions | "ENOSPC: fixed by increasing inotify watchers" |
| `pattern` | Recurring code/workflow patterns | "All API routes follow /api/v1/{resource} convention" |
| `instruction` | Behavioral directives from user | "Always run tests before committing" |
| `context` | Environmental/situational info | "Staging deploys via GitHub Actions to fly.io" |
| `conversation` | Notable interaction insights | "User is migrating from Express to Hono" |

## Common Arguments

All subcommands accept:
- `--path PATH` — Override memory store path (default: `.claude/memory/` in git repos, `~/.claude/memory/` otherwise)

## Example Workflows

### Starting a new task
```bash
# Query for relevant context before beginning
python scripts/memory.py query --text "project architecture and tech stack"
python scripts/memory.py query --text "user coding preferences and style"
```

### After resolving an error
```bash
python scripts/memory.py store \
  --content "psycopg2 'connection refused': PostgreSQL wasn't running. Fix: sudo systemctl start postgresql" \
  --category error \
  --tags postgres database connection \
  --importance 0.7
```

### After user gives feedback
```bash
python scripts/memory.py store \
  --content "User wants concise PR descriptions, no emoji, focus on what changed and why" \
  --category instruction \
  --importance 0.9 \
  --tags pr git workflow
```

## Resources

### scripts/
- `memory.py` — Main CLI with all subcommands (store, query, list, stats, update, delete, init)
- `embeddings.py` — Embedding provider abstraction (Ollama/OpenAI)
- `setup.py` — Auto-bootstrap module (dependency install, Ollama management, store init)

### references/
- `advanced.md` — Migration, recovery, tuning, troubleshooting guide
