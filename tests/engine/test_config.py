"""Where the platform keeps its data (docs/tasks/M1-05.md)."""

from pathlib import Path

import pytest

from investment_engine.config import (
    ENV_DATA_DIR,
    data_dir,
    market_store_dir,
    operational_db_path,
)


@pytest.mark.unit
def test_the_environment_variable_sets_the_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_DATA_DIR, str(tmp_path / "custom"))
    assert data_dir() == tmp_path / "custom"
    assert operational_db_path() == tmp_path / "custom" / "operational.sqlite3"
    assert market_store_dir() == tmp_path / "custom" / "market"


@pytest.mark.unit
@pytest.mark.parametrize("unset", ["delete", "blank"])
def test_without_the_variable_the_default_is_in_the_home_folder(tmp_path, monkeypatch, unset):
    if unset == "delete":
        monkeypatch.delenv(ENV_DATA_DIR)
    else:
        monkeypatch.setenv(ENV_DATA_DIR, "")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert data_dir() == tmp_path / "home" / ".investment_engine"


@pytest.mark.unit
def test_the_variable_is_read_when_called_not_at_import(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_DATA_DIR, str(tmp_path / "first"))
    assert data_dir() == tmp_path / "first"
    monkeypatch.setenv(ENV_DATA_DIR, str(tmp_path / "second"))
    assert data_dir() == tmp_path / "second"


@pytest.mark.unit
def test_engine_tests_use_their_own_data_dir(_own_data_dir):
    # tests/engine/conftest.py points every engine test at a temporary folder,
    # never the real default. (On this machine the temp folder itself sits
    # inside the home folder, so the check is "not the real default", not
    # "not under home"; see docs/baselines/M1-00-baseline.md.)
    assert data_dir() == _own_data_dir
    assert data_dir() != Path.home() / ".investment_engine"


@pytest.mark.unit
def test_reading_the_config_creates_nothing(_own_data_dir):
    data_dir(), operational_db_path(), market_store_dir()
    assert not _own_data_dir.exists()
