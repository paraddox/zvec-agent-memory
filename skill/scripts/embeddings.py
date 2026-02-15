"""Embedding provider abstraction for zvec-memory.

Supports two backends:
- Ollama nomic-embed-text (768 dims, default)
- OpenAI text-embedding-3-small (1536 dims, fallback)

Dependencies: requests only (no torch, no sentence-transformers).
"""

import os
import re
import sys

import requests


def _preprocess(text: str) -> str:
    """Strip, collapse whitespace, truncate to 8192 chars."""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text[:8192]


def get_embedding(text: str, config: dict | None = None) -> list[float]:
    """Get embedding vector for text using the configured provider.

    Args:
        text: Text to embed.
        config: Dict with 'provider', 'model', 'dimension' keys.
               Defaults to Ollama nomic-embed-text if None.

    Returns:
        List of floats (embedding vector).
    """
    text = _preprocess(text)
    if not text:
        raise ValueError("Cannot embed empty text")

    config = config or {}
    provider = config.get("provider", "ollama")

    if provider == "openai":
        return _embed_openai(text, config)
    else:
        return _embed_ollama(text, config)


def _embed_ollama(text: str, config: dict) -> list[float]:
    """Get embedding from Ollama API."""
    model = config.get("model", "nomic-embed-text")
    base_url = config.get("ollama_url", "http://localhost:11434")

    try:
        resp = requests.post(
            f"{base_url}/api/embed",
            json={"model": model, "input": text},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings")
        if not embeddings or not embeddings[0]:
            raise RuntimeError(f"Ollama returned empty embeddings: {data}")
        return embeddings[0]
    except requests.ConnectionError:
        raise RuntimeError(
            "Cannot connect to Ollama at "
            f"{base_url}. Is it running? Try: ollama serve"
        )
    except requests.HTTPError as e:
        raise RuntimeError(f"Ollama embedding failed: {e} — {resp.text}")


def _embed_openai(text: str, config: dict) -> list[float]:
    """Get embedding from OpenAI API."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Set it or use Ollama instead."
        )

    model = config.get("model", "text-embedding-3-small")

    try:
        resp = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "input": text},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]
    except requests.HTTPError as e:
        raise RuntimeError(f"OpenAI embedding failed: {e} — {resp.text}")


def detect_provider() -> dict:
    """Auto-detect the best available embedding provider.

    Returns config dict with provider, model, dimension.
    """
    # Try Ollama first
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code == 200:
            return {
                "provider": "ollama",
                "model": "nomic-embed-text",
                "dimension": 768,
            }
    except requests.ConnectionError:
        pass

    # Fall back to OpenAI if key is set
    if os.environ.get("OPENAI_API_KEY"):
        return {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "dimension": 1536,
        }

    raise RuntimeError(
        "No embedding provider available. "
        "Either start Ollama (ollama serve) or set OPENAI_API_KEY."
    )


if __name__ == "__main__":
    # Quick test
    config = detect_provider()
    print(f"Provider: {config}", file=sys.stderr)
    vec = get_embedding("Hello, world!", config)
    print(f"Dimension: {len(vec)}")
    print(f"First 5 values: {vec[:5]}")
