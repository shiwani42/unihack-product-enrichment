"""Hermetic test defaults: live manufacturer fetches are disabled unless a
test is explicitly marked with @pytest.mark.network."""

import os
from pathlib import Path

import pytest


def _has_network_marker(request) -> bool:
    return request.node.get_closest_marker("network") is not None


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    config.addinivalue_line("markers", "network: test hits live external services")


@pytest.fixture(autouse=True)
def _reset_search_engine():
    from sources.web_search import set_last_search_engine

    set_last_search_engine(None)
    yield
    set_last_search_engine(None)


@pytest.fixture(autouse=True)
def _offline_by_default(request, monkeypatch):
    if not _has_network_marker(request):
        monkeypatch.setenv("UNILOG_LIVE_FETCH", "0")
        monkeypatch.setenv("UNILOG_WEB_SEARCH", "0")
        monkeypatch.setenv("UNILOG_FIRECRAWL", "0")
        monkeypatch.setenv("UNILOG_WIKIDATA", "0")
    yield


@pytest.fixture(autouse=True)
def _isolate_search_paths(tmp_path, monkeypatch):
    """Copy brand URL templates into a temp file so promotions stay out of git."""
    import shutil

    import sources.finder as finder
    import sources.url_patterns as url_patterns

    src = Path(finder.__file__).resolve().parent / "search_paths.json"
    dest = tmp_path / "search_paths.json"
    if src.exists():
        shutil.copy2(src, dest)
    monkeypatch.setattr(finder, "SEARCH_PATHS_FILE", dest)
    monkeypatch.setattr(url_patterns, "SEARCH_PATHS_FILE", dest)
    finder.reset_search_path_cache()
    yield
    finder.reset_search_path_cache()


@pytest.fixture(autouse=True)
def _isolate_learned_paths(tmp_path, monkeypatch):
    """Keep harvest of generic CMS paths out of the committed learned_paths.json."""
    import shutil

    import sources.finder as finder
    import sources.learned_paths as learned_paths

    src = Path(finder.__file__).resolve().parent / "learned_paths.json"
    dest = tmp_path / "learned_paths.json"
    if src.exists():
        shutil.copy2(src, dest)
    monkeypatch.setattr(finder, "LEARNED_PATHS_FILE", dest)
    monkeypatch.setattr(learned_paths, "LEARNED_PATHS_FILE", dest)
    finder.reset_search_path_cache()
    yield
    finder.reset_search_path_cache()


@pytest.fixture(autouse=True)
def _isolate_dead_paths(tmp_path, monkeypatch):
    import sources.dead_paths as dead_paths

    monkeypatch.setattr(dead_paths, "DEAD_PATHS_FILE", tmp_path / "dead_paths.json")
    dead_paths._reset_cache()
    yield
    dead_paths._reset_cache()


@pytest.fixture(autouse=True)
def _isolate_harvest_links(tmp_path, monkeypatch):
    """Keep harvest link catalog writes out of the committed seed during tests."""
    import shutil

    import sources.harvest_links as harvest_links

    src = Path(harvest_links.__file__).resolve().parent / "harvest_links.json"
    dest = tmp_path / "harvest_links.json"
    if src.exists():
        shutil.copy2(src, dest)
    monkeypatch.setattr(harvest_links, "HARVEST_LINKS_FILE", dest)
    harvest_links._reset_cache()
    yield
    harvest_links._reset_cache()


@pytest.fixture(autouse=True)
def _isolate_learned_hosts(tmp_path, monkeypatch):
    import sources.learned_hosts as learned_hosts

    monkeypatch.setattr(learned_hosts, "LEARNED_HOSTS_FILE", tmp_path / "learned_hosts.json")
    learned_hosts._reset_cache()
    yield
    learned_hosts._reset_cache()


@pytest.fixture(autouse=True)
def _isolate_reviewer_memory(tmp_path, monkeypatch):
    import sources.reviewer as reviewer

    monkeypatch.setattr(reviewer, "REVIEWER_FILE", tmp_path / "reviewer_memory.json")
    reviewer._reset_cache()
    yield
    reviewer._reset_cache()


@pytest.fixture(autouse=True)
def _isolate_known_urls(tmp_path, monkeypatch):
    """Keep live-search URL memory out of the committed seed file during tests."""
    import sources.known_urls as known_urls

    monkeypatch.setattr(known_urls, "KNOWN_URLS_FILE", tmp_path / "known_urls.json")
    known_urls._reset_cache()
    yield
    known_urls._reset_cache()
