# zvec-memory Advanced Reference

## Embedding Provider Switching & Migration

### Changing providers on an existing store

Switching embedding providers (e.g., Ollama → OpenAI) requires re-initializing because different providers produce different dimensions and vector spaces.

```bash
# Re-initialize with a different provider (destroys existing memories)
python scripts/memory.py init --provider openai --dimension 1536 --force
```

**Dimension mismatch**: If you try to store/query with a provider whose dimension doesn't match the store's dimension, you'll get an error. The store's dimension is locked at init time in `memory_config.json`.

### Migration steps (preserving memories)

1. Export existing memories: `python scripts/memory.py list --limit 1000 > backup.json`
2. Re-initialize: `python scripts/memory.py init --provider openai --force`
3. Re-import: parse `backup.json` and re-store each memory (embeddings will be regenerated with the new provider)

## Database Backup and Recovery

### Backup

The memory store is a directory containing:
- `memories.zvec/` — The zvec collection data
- `memory_config.json` — Provider/model/dimension config

To backup:
```bash
cp -r .claude/memory/ .claude/memory-backup/
```

### Recovery

To restore from backup:
```bash
rm -rf .claude/memory/
cp -r .claude/memory-backup/ .claude/memory/
```

### Corrupt store

If the store becomes corrupt (e.g., due to interrupted writes):
1. Try opening it — zvec may auto-recover
2. If not, re-initialize with `--force` and re-import from backup
3. As a last resort, delete the store directory and start fresh

## HNSW Parameter Tuning

The default HNSW parameters are tuned for general use:

| Parameter | Default | Effect |
|---|---|---|
| `m` | 16 | Max bi-directional connections per node. Higher = more accurate, more memory |
| `ef_construction` | 200 | Search width during index build. Higher = better index quality, slower build |
| `ef` (query-time) | Not set (zvec default) | Higher = more accurate search, slower queries |

These are set at init time and generally don't need changing for typical memory stores (< 100K memories).

### When to tune

- **> 50K memories**: Consider increasing `m` to 32 for better recall
- **Precision-critical queries**: Increase `ef` at query time
- **Memory-constrained environments**: Decrease `m` to 8

## memory_config.json Format

Stored at `{memory_path}/memory_config.json`:

```json
{
  "provider": "ollama",
  "model": "nomic-embed-text",
  "dimension": 768,
  "db_path": "/path/to/.claude/memory/memories.zvec",
  "created_at": 1705000000
}
```

| Field | Type | Description |
|---|---|---|
| `provider` | string | "ollama" or "openai" |
| `model` | string | Model name used for embeddings |
| `dimension` | int | Vector dimension (must match model output) |
| `db_path` | string | Absolute path to the zvec collection |
| `created_at` | int | Unix timestamp of store creation |

## Auto-Bootstrap Flow

Every `memory.py` invocation follows this path:

```
memory.py called
  └─ setup.ensure_ready(path)
       ├─ Check/install Python packages (zvec, requests)
       │    └─ pip install --quiet if missing
       ├─ Check embedding provider
       │    ├─ Ollama running? → check model → pull if missing
       │    ├─ Ollama binary exists? → start it → check model
       │    └─ OPENAI_API_KEY set? → use OpenAI fallback
       └─ Check memory store
            ├─ memory_config.json exists? → load config
            └─ Doesn't exist? → create schema → init collection → save config
  └─ Execute actual command (store/query/list/etc.)
```

All progress messages go to stderr. Only JSON results go to stdout.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Cannot connect to Ollama" | Ollama not running | Run `ollama serve` or install from ollama.ai |
| "Model not found" | Model not pulled | Run `ollama pull nomic-embed-text` |
| "OPENAI_API_KEY not set" | No Ollama, no API key | Start Ollama or `export OPENAI_API_KEY=sk-...` |
| "dimension mismatch" | Store created with different provider | Re-init with `--force` (destroys data) |
| Empty query results | Store is empty or query doesn't match | Check `stats`, try broader query terms |
| "pip install" fails | No internet or permissions | Install manually: `pip install zvec requests` |
| Slow first query | HNSW index building | Normal on first query after many inserts |
| "Collection not found" | Corrupt or missing store | Delete store directory, let auto-init recreate |
| "Illegal instruction" on import | CPU lacks AVX-512 (pre-built wheels) | Build from source: `git clone --recurse-submodules https://github.com/alibaba/zvec.git && cd zvec && pip install -C cmake.define.ENABLE_ZEN3=ON .` (use the appropriate arch flag for your CPU) |

## Store Path Resolution

The memory store path is resolved in this order:

1. Explicit `--path` argument (highest priority)
2. Git repo root: `{git_root}/.claude/memory/`
3. Home directory: `~/.claude/memory/` (fallback)

Per-project stores (option 2) keep memories scoped to the project. Global store (option 3) is used outside git repos.
