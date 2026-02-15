#!/usr/bin/env python3
"""zvec-memory CLI — Persistent long-term memory for AI agents.

All output is JSON to stdout. Progress/logs go to stderr.
Every invocation auto-bootstraps: installs deps, starts Ollama, pulls models,
initializes the memory store — all transparently.

Usage:
    python memory.py store --content "User prefers dark mode" --category preference
    python memory.py query --text "user theme preference" --topk 5
    python memory.py list --category fact --limit 10
    python memory.py stats
    python memory.py update --id mem_abc123 --importance 0.9
    python memory.py delete --id mem_abc123
    python memory.py init --provider ollama --dimension 768
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid

# Add scripts directory to path for sibling imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def _resolve_path(args_path: str | None) -> str:
    """Resolve memory store path.

    Priority:
    1. Explicit --path argument
    2. Git repo root + .claude/memory/
    3. ~/.claude/memory/
    """
    if args_path:
        return os.path.abspath(args_path)

    # Try git repo root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            repo_root = result.stdout.strip()
            return os.path.join(repo_root, ".claude", "memory")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fall back to home directory
    return os.path.join(os.path.expanduser("~"), ".claude", "memory")


def _output(data: dict) -> None:
    """Print JSON result to stdout."""
    print(json.dumps(data, ensure_ascii=False))


def _error(code: str, message: str, hint: str = "") -> None:
    """Print JSON error to stdout and exit."""
    result = {"status": "error", "error": code, "message": message}
    if hint:
        result["hint"] = hint
    _output(result)
    sys.exit(1)


def _generate_id() -> str:
    """Generate a unique memory ID."""
    return f"mem_{uuid.uuid4().hex[:12]}"


def _open_collection(config: dict):
    """Open the zvec collection and optimize for queries."""
    import zvec

    db_path = config["db_path"]
    collection = zvec.open(path=db_path, option=zvec.CollectionOption())
    collection.optimize()
    return collection


def cmd_init(args) -> None:
    """Initialize (or re-initialize) the memory store."""
    from setup import ensure_ready

    path = _resolve_path(args.path)

    if args.force and os.path.exists(path):
        import shutil
        shutil.rmtree(path)
        print(f"[zvec-memory] Removed existing store at {path}", file=sys.stderr)

    config = {
        "provider": args.provider,
        "dimension": args.dimension,
    }
    if args.provider == "ollama":
        config["model"] = args.model or "nomic-embed-text"
    elif args.provider == "openai":
        config["model"] = args.model or "text-embedding-3-small"

    result_config = ensure_ready(path, provider=args.provider)

    # Test embedding connectivity
    from embeddings import get_embedding
    try:
        test_vec = get_embedding("connectivity test", result_config)
        dim = len(test_vec)
    except Exception as e:
        _error("embedding_failed", f"Embedding test failed: {e}",
               "Check that your embedding provider is running")

    _output({
        "status": "ok",
        "message": "Memory store initialized",
        "path": path,
        "provider": result_config.get("provider"),
        "model": result_config.get("model"),
        "dimension": dim,
    })


def cmd_store(args) -> None:
    """Store a new memory."""
    from setup import ensure_ready
    from embeddings import get_embedding

    path = _resolve_path(args.path)
    config = ensure_ready(path)

    content = args.content
    if not content:
        _error("missing_content", "Content is required", "Use --content 'your text'")

    # Generate embedding
    try:
        embedding = get_embedding(content, config)
    except Exception as e:
        _error("embedding_failed", f"Failed to generate embedding: {e}")

    now = int(time.time())
    memory_id = args.id or _generate_id()
    category = args.category or "fact"
    tags = args.tags or []
    importance = args.importance if args.importance is not None else 0.5
    source = args.source

    import zvec

    collection = _open_collection(config)
    try:
        doc = zvec.Doc(
            id=memory_id,
            vectors={"embedding": embedding},
            fields={
                "content": content,
                "category": category,
                "tags": tags,
                "source": source,
                "created_at": now,
                "updated_at": now,
                "importance": float(importance),
                "access_count": 0,
            },
        )
        results = collection.insert([doc])
        collection.flush()

        if results[0].ok():
            _output({
                "status": "ok",
                "id": memory_id,
                "content": content,
                "category": category,
                "tags": tags,
                "importance": importance,
                "created_at": now,
            })
        else:
            _error("insert_failed", f"Failed to insert memory: {results[0].message}")
    finally:
        del collection


def cmd_query(args) -> None:
    """Semantic search for memories."""
    from setup import ensure_ready
    from embeddings import get_embedding

    path = _resolve_path(args.path)
    config = ensure_ready(path)

    text = args.text
    if not text:
        _error("missing_text", "Query text is required", "Use --text 'your query'")

    # Generate query embedding
    try:
        query_vec = get_embedding(text, config)
    except Exception as e:
        _error("embedding_failed", f"Failed to generate query embedding: {e}")

    import zvec

    collection = _open_collection(config)
    try:
        topk = args.topk or 5

        # Build filter
        filters = []
        if args.category:
            filters.append(f"category = '{args.category}'")
        if args.tags:
            tag_values = ", ".join(f"'{t}'" for t in args.tags)
            filters.append(f"tags contain_all ({tag_values})")
        if args.min_importance is not None:
            filters.append(f"importance >= {args.min_importance}")

        filter_str = " AND ".join(filters) if filters else None

        query_kwargs = {
            "vectors": zvec.VectorQuery("embedding", vector=query_vec),
            "topk": topk,
            "output_fields": [
                "content", "category", "tags", "source",
                "created_at", "updated_at", "importance", "access_count",
            ],
        }
        if filter_str:
            query_kwargs["filter"] = filter_str

        results = collection.query(**query_kwargs)

        memories = []
        ids_to_update = []
        for doc in results:
            mem = {
                "id": doc.id,
                "score": round(doc.score, 4),
                "content": doc.field("content"),
                "category": doc.field("category"),
                "tags": doc.field("tags"),
                "source": doc.field("source"),
                "created_at": doc.field("created_at"),
                "updated_at": doc.field("updated_at"),
                "importance": doc.field("importance"),
                "access_count": doc.field("access_count"),
            }
            memories.append(mem)
            ids_to_update.append((doc.id, doc.field("access_count") or 0))

        # Update access counts
        for mem_id, count in ids_to_update:
            try:
                update_doc = zvec.Doc(
                    id=mem_id,
                    fields={"access_count": count + 1},
                )
                collection.update(update_doc)
            except Exception as e:
                print(f"[zvec-memory] Warning: access_count update failed for {mem_id}: {e}", file=sys.stderr)

        if ids_to_update:
            collection.flush()

        _output({
            "status": "ok",
            "query": text,
            "count": len(memories),
            "memories": memories,
        })
    finally:
        del collection


def cmd_delete(args) -> None:
    """Delete a memory by ID."""
    from setup import ensure_ready

    path = _resolve_path(args.path)
    config = ensure_ready(path)

    import zvec

    collection = _open_collection(config)
    try:
        statuses = collection.delete([args.id])
        collection.flush()

        if statuses[0].ok():
            _output({"status": "ok", "id": args.id, "message": "Memory deleted"})
        else:
            _error("not_found", f"Memory '{args.id}' not found")
    finally:
        del collection


def cmd_list(args) -> None:
    """List memories with optional filters."""
    from setup import ensure_ready

    path = _resolve_path(args.path)
    config = ensure_ready(path)

    import zvec

    collection = _open_collection(config)
    try:
        dimension = config.get("dimension", 768)
        limit = args.limit or 20

        # Build filter
        filters = []
        if args.category:
            filters.append(f"category = '{args.category}'")
        if args.tags:
            tag_values = ", ".join(f"'{t}'" for t in args.tags)
            filters.append(f"tags contain_all ({tag_values})")

        filter_str = " AND ".join(filters) if filters else None

        # Use unit vector to fetch all (scores are meaningless, but zero
        # vector fails with cosine similarity due to zero norm)
        unit_vec = [1.0] * dimension
        query_kwargs = {
            "vectors": zvec.VectorQuery("embedding", vector=unit_vec),
            "topk": min(limit, 1000),
            "output_fields": [
                "content", "category", "tags", "source",
                "created_at", "updated_at", "importance", "access_count",
            ],
        }
        if filter_str:
            query_kwargs["filter"] = filter_str

        results = collection.query(**query_kwargs)

        memories = []
        for doc in results:
            mem = {
                "id": doc.id,
                "content": doc.field("content"),
                "category": doc.field("category"),
                "tags": doc.field("tags"),
                "source": doc.field("source"),
                "created_at": doc.field("created_at"),
                "updated_at": doc.field("updated_at"),
                "importance": doc.field("importance"),
                "access_count": doc.field("access_count"),
            }
            memories.append(mem)

        # Sort in Python
        sort_by = args.sort_by or "created_at"
        reverse = sort_by in ("created_at", "updated_at", "importance", "access_count")
        memories.sort(key=lambda m: m.get(sort_by, 0) or 0, reverse=reverse)

        _output({
            "status": "ok",
            "count": len(memories),
            "memories": memories[:limit],
        })
    finally:
        del collection


def cmd_stats(args) -> None:
    """Show memory store statistics."""
    from setup import ensure_ready

    path = _resolve_path(args.path)
    config = ensure_ready(path)

    import zvec

    collection = _open_collection(config)
    try:
        stats = collection.stats
        total = stats.doc_count

        # Calculate size from disk (size_bytes not available in all zvec versions)
        db_path = config.get("db_path", "")
        size_bytes = 0
        if os.path.exists(db_path):
            for dirpath, _dirnames, filenames in os.walk(db_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    size_bytes += os.path.getsize(fp)

        # Get per-category breakdown using unit-vector queries
        dimension = config.get("dimension", 768)
        unit_vec = [1.0] * dimension
        categories = [
            "fact", "preference", "conversation", "decision",
            "error", "pattern", "context", "instruction",
        ]
        breakdown = {}
        for cat in categories:
            try:
                results = collection.query(
                    vectors=zvec.VectorQuery("embedding", vector=unit_vec),
                    topk=1000,
                    filter=f"category = '{cat}'",
                    output_fields=["category"],
                )
                count = len(list(results))
                if count > 0:
                    breakdown[cat] = count
            except Exception:
                pass

        _output({
            "status": "ok",
            "total_memories": total,
            "size_bytes": size_bytes,
            "size_human": _human_size(size_bytes),
            "categories": breakdown,
            "provider": config.get("provider"),
            "model": config.get("model"),
            "dimension": config.get("dimension"),
            "path": path,
        })
    finally:
        del collection


def cmd_update(args) -> None:
    """Update an existing memory."""
    from setup import ensure_ready
    from embeddings import get_embedding

    path = _resolve_path(args.path)
    config = ensure_ready(path)

    import zvec

    collection = _open_collection(config)
    try:
        # Verify the memory exists
        fetched = collection.fetch(args.id)
        if args.id not in fetched:
            _error("not_found", f"Memory '{args.id}' not found")

        now = int(time.time())
        fields = {"updated_at": now}

        if args.content is not None:
            fields["content"] = args.content
        if args.category is not None:
            fields["category"] = args.category
        if args.tags is not None:
            fields["tags"] = args.tags
        if args.importance is not None:
            fields["importance"] = float(args.importance)

        # Re-embed if content changed
        vectors = None
        if args.content is not None:
            try:
                embedding = get_embedding(args.content, config)
                vectors = {"embedding": embedding}
            except Exception as e:
                _error("embedding_failed", f"Failed to re-embed: {e}")

        doc_kwargs = {"id": args.id, "fields": fields}
        if vectors:
            doc_kwargs["vectors"] = vectors

        update_doc = zvec.Doc(**doc_kwargs)
        status = collection.update(update_doc)
        collection.flush()

        if status.ok():
            _output({
                "status": "ok",
                "id": args.id,
                "message": "Memory updated",
                "updated_fields": list(fields.keys()),
            })
        else:
            _error("update_failed", f"Failed to update: {status.message}")
    finally:
        del collection


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def main():
    parser = argparse.ArgumentParser(
        description="zvec-memory: Persistent long-term memory for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Shared path argument
    path_help = "Memory store path (default: auto-detect)"

    # init
    p_init = subparsers.add_parser("init", help="Initialize memory store")
    p_init.add_argument("--path", help=path_help)
    p_init.add_argument("--provider", default="ollama",
                        choices=["ollama", "openai"],
                        help="Embedding provider (default: ollama)")
    p_init.add_argument("--model", help="Embedding model name")
    p_init.add_argument("--dimension", type=int, default=768,
                        help="Embedding dimension (default: 768)")
    p_init.add_argument("--force", action="store_true",
                        help="Remove existing store and reinitialize")

    # store
    p_store = subparsers.add_parser("store", help="Store a new memory")
    p_store.add_argument("--path", help=path_help)
    p_store.add_argument("--content", required=True, help="Memory text content")
    p_store.add_argument("--category", default="fact",
                         choices=["fact", "preference", "conversation",
                                  "decision", "error", "pattern",
                                  "context", "instruction"],
                         help="Memory category (default: fact)")
    p_store.add_argument("--tags", nargs="*", default=[],
                         help="Freeform tags")
    p_store.add_argument("--importance", type=float,
                         help="Priority score 0.0-1.0 (default: 0.5)")
    p_store.add_argument("--source", help="Origin of the memory")
    p_store.add_argument("--id", help="Custom memory ID (auto-generated if omitted)")

    # query
    p_query = subparsers.add_parser("query", help="Search memories semantically")
    p_query.add_argument("--path", help=path_help)
    p_query.add_argument("--text", required=True, help="Search query text")
    p_query.add_argument("--topk", type=int, default=5,
                         help="Number of results (default: 5)")
    p_query.add_argument("--category", help="Filter by category")
    p_query.add_argument("--tags", nargs="*", help="Filter by tags (all must match)")
    p_query.add_argument("--min-importance", type=float,
                         help="Minimum importance score")

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete a memory")
    p_delete.add_argument("--path", help=path_help)
    p_delete.add_argument("--id", required=True, help="Memory ID to delete")

    # list
    p_list = subparsers.add_parser("list", help="List memories")
    p_list.add_argument("--path", help=path_help)
    p_list.add_argument("--category", help="Filter by category")
    p_list.add_argument("--tags", nargs="*", help="Filter by tags")
    p_list.add_argument("--limit", type=int, default=20,
                        help="Max results (default: 20)")
    p_list.add_argument("--sort-by", default="created_at",
                        choices=["created_at", "updated_at", "importance",
                                 "access_count", "category"],
                        help="Sort field (default: created_at)")

    # stats
    p_stats = subparsers.add_parser("stats", help="Memory store statistics")
    p_stats.add_argument("--path", help=path_help)

    # update
    p_update = subparsers.add_parser("update", help="Update a memory")
    p_update.add_argument("--path", help=path_help)
    p_update.add_argument("--id", required=True, help="Memory ID to update")
    p_update.add_argument("--content", help="New content (triggers re-embedding)")
    p_update.add_argument("--category",
                          choices=["fact", "preference", "conversation",
                                   "decision", "error", "pattern",
                                   "context", "instruction"],
                          help="New category")
    p_update.add_argument("--tags", nargs="*", help="New tags (replaces existing)")
    p_update.add_argument("--importance", type=float,
                          help="New importance score 0.0-1.0")

    args = parser.parse_args()

    try:
        commands = {
            "init": cmd_init,
            "store": cmd_store,
            "query": cmd_query,
            "delete": cmd_delete,
            "list": cmd_list,
            "stats": cmd_stats,
            "update": cmd_update,
        }
        commands[args.command](args)
    except SystemExit:
        raise
    except Exception as e:
        _error("unexpected_error", str(e),
               "Check stderr for details or run with PYTHONPATH set")


if __name__ == "__main__":
    main()
