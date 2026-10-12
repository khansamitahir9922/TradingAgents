"""Fixtures for investment_engine tests.

Every engine test gets its own data directory, so nothing reads or writes the
user's real one (~/.investment_engine), in the spirit of tests/conftest.py,
which does the same for TradingAgents' results and caches.
"""

import pytest

from investment_engine.config import ENV_DATA_DIR


@pytest.fixture(autouse=True)
def _own_data_dir(tmp_path, monkeypatch):
    data = tmp_path / "engine-data"
    monkeypatch.setenv(ENV_DATA_DIR, str(data))
    return data
