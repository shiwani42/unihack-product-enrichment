"""Hermetic test defaults: live manufacturer fetches are disabled unless a
test is explicitly marked with @pytest.mark.network."""

import os

import pytest


def _has_network_marker(request) -> bool:
    return request.node.get_closest_marker("network") is not None


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    config.addinivalue_line("markers", "network: test hits live external services")


@pytest.fixture(autouse=True)
def _offline_by_default(request, monkeypatch):
    if not _has_network_marker(request):
        monkeypatch.setenv("UNILOG_LIVE_FETCH", "0")
    yield
