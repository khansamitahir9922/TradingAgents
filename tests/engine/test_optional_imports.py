"""The engine's storage libraries stay optional (docs/tasks/M1-10.md).

pyarrow and duckdb are in the optional `engine` extra, so importing the
package (and its non-storage modules) must not load them; only the
market-data store does.
"""

import subprocess
import sys

import pytest

LIGHT_MODULES = [
    "investment_engine",
    "investment_engine.clock",
    "investment_engine.money",
    "investment_engine.config",
    "investment_engine.market.instruments",
    "investment_engine.market.symbols",
    "investment_engine.market.calendar",
    "investment_engine.market.availability",
    "investment_engine.market.candles",
    "investment_engine.market.corporate_actions",
    "investment_engine.market.store",
    "investment_engine.storage.sqlite",
]


@pytest.mark.unit
def test_importing_the_package_does_not_load_the_storage_libraries():
    code = (
        "import importlib, sys\n"
        f"for name in {LIGHT_MODULES!r}:\n"
        "    importlib.import_module(name)\n"
        "print(sorted(m for m in ('pyarrow', 'duckdb') if m in sys.modules))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"


@pytest.mark.unit
def test_the_writer_is_where_pyarrow_is_loaded():
    code = (
        "import sys\n"
        "import investment_engine.market.store.writer\n"
        "print('pyarrow' in sys.modules)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "True"
