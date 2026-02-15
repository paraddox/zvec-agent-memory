"""Auto-bootstrap module for zvec-memory.

Ensures the entire environment is ready with zero manual intervention:
1. Installs Python packages (zvec, requests) if missing
2. Starts Ollama if not running (or falls back to OpenAI)
3. Pulls the embedding model if not available
4. Initializes the memory store if it doesn't exist

Called by memory.py at startup via ensure_ready().
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
import time


def _log(msg: str) -> None:
    """Print progress to stderr so stdout stays clean for JSON."""
    print(f"[zvec-memory] {msg}", file=sys.stderr)


def _install_packages() -> None:
    """Install zvec and requests if not importable."""
    missing = []
    for pkg in ["zvec", "requests"]:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        _log(f"Installing missing packages: {', '.join(missing)}")
        cmd = [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        try:
            subprocess.check_call(cmd, stdout=sys.stderr, stderr=sys.stderr)
        except subprocess.CalledProcessError:
            # Retry with --break-system-packages for PEP 668 environments
            _log("Retrying with --break-system-packages...")
            cmd = [
                sys.executable, "-m", "pip", "install", "--quiet",
                "--break-system-packages",
            ] + missing
            subprocess.check_call(cmd, stdout=sys.stderr, stderr=sys.stderr)
        # Force re-import after install
        importlib.invalidate_caches()
        for pkg in missing:
            if pkg in sys.modules:
                del sys.modules[pkg]


def _ollama_is_running(base_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama is reachable."""
    import requests as req

    try:
        resp = req.get(f"{base_url}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def _start_ollama() -> bool:
    """Try to start Ollama if the binary exists. Returns True if started."""
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        return False

    _log("Starting Ollama server...")
    subprocess.Popen(
        [ollama_bin, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Wait up to 15 seconds for Ollama to become reachable
    for i in range(30):
        time.sleep(0.5)
        if _ollama_is_running():
            _log("Ollama server started successfully")
            return True

    _log("Warning: Ollama started but not reachable after 15s")
    return False


def _ensure_model(model: str = "nomic-embed-text") -> None:
    """Pull the embedding model if not already available."""
    import requests as req

    resp = req.get("http://localhost:11434/api/tags", timeout=5)
    resp.raise_for_status()
    models = [m.get("name", "").split(":")[0] for m in resp.json().get("models", [])]

    if model not in models:
        _log(f"Pulling model '{model}' (this may take a few minutes)...")
        pull_resp = req.post(
            "http://localhost:11434/api/pull",
            json={"name": model, "stream": True},
            stream=True,
            timeout=600,
        )
        pull_resp.raise_for_status()
        for line in pull_resp.iter_lines():
            if line:
                try:
                    data = json.loads(line)
                    status = data.get("status", "")
                    if "pulling" in status or "downloading" in status:
                        total = data.get("total", 0)
                        completed = data.get("completed", 0)
                        if total:
                            pct = int(completed / total * 100)
                            _log(f"  {status}: {pct}%")
                    elif status:
                        _log(f"  {status}")
                except json.JSONDecodeError:
                    pass
        _log(f"Model '{model}' pulled successfully")


def _ensure_ollama_provider(config: dict) -> dict:
    """Ensure Ollama is available with the required model."""
    if _ollama_is_running():
        _ensure_model(config.get("model", "nomic-embed-text"))
        return config

    # Try starting Ollama
    if _start_ollama():
        _ensure_model(config.get("model", "nomic-embed-text"))
        return config

    # Fall back to OpenAI
    if os.environ.get("OPENAI_API_KEY"):
        _log("Ollama unavailable, falling back to OpenAI embeddings")
        return {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "dimension": 1536,
        }

    raise RuntimeError(
        "Cannot start Ollama and OPENAI_API_KEY is not set. "
        "Install Ollama (https://ollama.ai) or set OPENAI_API_KEY."
    )


def _init_store(path: str, config: dict) -> dict:
    """Initialize the zvec memory store if it doesn't exist."""
    import zvec

    config_path = os.path.join(path, "memory_config.json")

    if os.path.exists(config_path):
        # Load existing config
        with open(config_path) as f:
            stored_config = json.load(f)
        return stored_config

    # Create directory
    os.makedirs(path, exist_ok=True)

    dimension = config.get("dimension", 768)

    _log(f"Initializing memory store at {path} (dim={dimension})")

    schema = zvec.CollectionSchema(
        name="memories",
        fields=[
            zvec.FieldSchema("content", zvec.DataType.STRING),
            zvec.FieldSchema("category", zvec.DataType.STRING),
            zvec.FieldSchema("tags", zvec.DataType.ARRAY_STRING),
            zvec.FieldSchema("source", zvec.DataType.STRING, nullable=True),
            zvec.FieldSchema("created_at", zvec.DataType.INT64),
            zvec.FieldSchema("updated_at", zvec.DataType.INT64),
            zvec.FieldSchema("importance", zvec.DataType.DOUBLE),
            zvec.FieldSchema("access_count", zvec.DataType.INT32),
        ],
        vectors=zvec.VectorSchema(
            "embedding",
            zvec.DataType.VECTOR_FP32,
            dimension=dimension,
            index_param=zvec.HnswIndexParam(ef_construction=200, m=16),
        ),
    )

    db_path = os.path.join(path, "memories.zvec")
    collection = zvec.create_and_open(path=db_path, schema=schema)
    collection.flush()
    del collection

    # Save config
    store_config = {
        "provider": config.get("provider", "ollama"),
        "model": config.get("model", "nomic-embed-text"),
        "dimension": dimension,
        "db_path": db_path,
        "created_at": int(time.time()),
    }
    with open(config_path, "w") as f:
        json.dump(store_config, f, indent=2)

    _log("Memory store initialized successfully")
    return store_config


def ensure_ready(path: str, provider: str = "ollama") -> dict:
    """Ensure everything is set up. Returns config dict.

    Installs packages, starts Ollama, pulls models, inits store — all as needed.
    Prints progress to stderr. Returns silently if everything is already ready.

    Args:
        path: Path to the memory store directory.
        provider: Embedding provider ("ollama" or "openai").

    Returns:
        Config dict with provider, model, dimension, db_path.
    """
    # Step 1: Ensure packages are installed
    _install_packages()

    # Step 2: Check if store already exists with config
    config_path = os.path.join(path, "memory_config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)
        provider = config.get("provider", provider)
    else:
        # Build default config
        if provider == "openai":
            config = {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 1536,
            }
        else:
            config = {
                "provider": "ollama",
                "model": "nomic-embed-text",
                "dimension": 768,
            }

    # Step 3: Ensure embedding provider is available
    if provider == "ollama":
        config = _ensure_ollama_provider(config)
    elif provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY not set for OpenAI provider")

    # Step 4: Ensure store is initialized
    config = _init_store(path, config)

    return config
