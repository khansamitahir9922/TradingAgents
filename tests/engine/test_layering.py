"""Import boundaries of the investment_engine package.

The platform beside TradingAgents keeps its layers apart (architecture Part I;
docs/tasks/M1-00.md): it never imports TradingAgents or its CLI, the yfinance
vendor library is confined to the importers, and the storage libraries to the
market-data store. The rules are checked now, while the package is empty, so
they guard it from its first line of code.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "investment_engine"


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


def _offenders(libraries: set[str], allowed: Path | None = None) -> list[str]:
    return sorted(
        str(path.relative_to(ROOT))
        for path in PACKAGE.rglob("*.py")
        if (allowed is None or allowed not in path.parents) and _imports(path) & libraries
    )


@pytest.mark.unit
def test_the_scan_covers_the_package():
    # The rules below pass vacuously if the scan finds no files.
    assert (PACKAGE / "__init__.py").is_file()


@pytest.mark.unit
def test_the_package_never_imports_tradingagents_or_its_cli():
    assert _offenders({"tradingagents", "cli"}) == []


@pytest.mark.unit
def test_yfinance_is_imported_only_by_the_importers():
    assert _offenders({"yfinance"}, PACKAGE / "market" / "importers") == []


@pytest.mark.unit
def test_storage_libraries_are_imported_only_by_the_market_data_store():
    assert _offenders({"pyarrow", "duckdb"}, PACKAGE / "market" / "store") == []


@pytest.mark.unit
def test_the_postgresql_driver_is_imported_only_by_the_storage_package():
    # docs/tasks/M3-00.md rule 5: one place owns the Operational Database driver.
    assert _offenders({"psycopg"}, PACKAGE / "storage") == []


@pytest.mark.unit
def test_the_package_imports_and_declares_its_version():
    import investment_engine

    assert investment_engine.__version__ == "0.0.0"
