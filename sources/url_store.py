"""URL memory that survives Vercel’s windowed SKU requests.

The deployment image is read-only. `/tmp` is writable but empty on a cold
start and is not shared across invocations (each `/api/enrich/window` can
be a different instance). Local CLI can write `sources/*.json` on disk.
On Vercel the browser holds a snapshot and sends it with the next SKU.
The page also writes that snapshot to localStorage (free, same browser)
so a refresh still overlays learned hosts. A new visitor starts from
committed seeds unless UPSTASH_REDIS_REST_URL + TOKEN (or a Blob token)
are set; then this process also reads/writes a shared snapshot so Judge 2
can reuse hosts Judge 1 learned. Missing or failing store is a no-op.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from io_utils import atomic_write_text
from sources.shared_memory import load_shared, merge_memory, save_shared

_SOURCES = Path(__file__).resolve().parent


def _on_vercel() -> bool:
    return bool(os.environ.get("VERCEL"))


def runtime_dir() -> Path:
    if _on_vercel():
        path = Path("/tmp/unilog/url_runtime")
    else:
        path = Path(__file__).resolve().parents[1] / "data" / "url_runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _redirect_writers(directory: Path) -> None:
    import sources.dead_paths as dead_paths
    import sources.finder as finder
    import sources.known_urls as known_urls
    import sources.url_patterns as url_patterns

    known_urls.KNOWN_URLS_FILE = directory / "known_urls.json"
    finder.SEARCH_PATHS_FILE = directory / "search_paths.json"
    url_patterns.SEARCH_PATHS_FILE = directory / "search_paths.json"
    dead_paths.DEAD_PATHS_FILE = directory / "dead_paths.json"
    known_urls._reset_cache()
    finder.reset_search_path_cache()
    dead_paths._reset_cache()


def activate() -> None:
    """On Vercel, copy bundled seeds into /tmp so remember/promote can write."""
    if not _on_vercel():
        return
    directory = runtime_dir()
    for name in ("known_urls.json", "search_paths.json"):
        src = _SOURCES / name
        dest = directory / name
        if src.exists():
            shutil.copy2(src, dest)
        elif not dest.exists():
            _write_json(dest, {})
    dead = directory / "dead_paths.json"
    if not dead.exists():
        _write_json(dead, {})
    _redirect_writers(directory)


def _reset_runtime_from_seeds() -> None:
    activate()


def snapshot() -> dict:
    import sources.dead_paths as dead_paths
    import sources.finder as finder
    import sources.known_urls as known_urls
    from sources.web_search import last_search_engine

    return {
        "known_urls": dict(known_urls._payload()),
        "search_paths": dict(finder._domain_paths()),
        "dead_paths": dict(dead_paths._read()),
        "search_engine": last_search_engine(),
    }


def restore(memory: dict | None) -> None:
    if not memory or not isinstance(memory, dict):
        return
    import sources.dead_paths as dead_paths
    import sources.finder as finder
    import sources.known_urls as known_urls
    import sources.url_patterns as url_patterns

    known = memory.get("known_urls")
    if isinstance(known, dict):
        _write_json(known_urls.KNOWN_URLS_FILE, known)
        known_urls._reset_cache()
    paths = memory.get("search_paths")
    if isinstance(paths, dict):
        _write_json(finder.SEARCH_PATHS_FILE, paths)
        finder.reset_search_path_cache()
    dead = memory.get("dead_paths")
    if isinstance(dead, dict):
        _write_json(dead_paths.DEAD_PATHS_FILE, dead)
        dead_paths._reset_cache()
    url_patterns.SEARCH_PATHS_FILE = finder.SEARCH_PATHS_FILE
    if "search_engine" in memory:
        from sources.web_search import set_last_search_engine

        set_last_search_engine(memory.get("search_engine") if isinstance(memory.get("search_engine"), str) else None)


def persist_shared(current: dict | None) -> dict:
    """Merge this request's snapshot into the shared store. Always returns a dict."""
    snap = current if isinstance(current, dict) else snapshot()
    shared = load_shared()
    merged = merge_memory(shared, snap)
    save_shared(merged)
    return merged


def begin_request(memory: dict | None) -> None:
    """Start an invocation from bundled seeds (Vercel) then apply shared + session memory."""
    if _on_vercel():
        _reset_runtime_from_seeds()
        restore(load_shared())
    restore(memory)
