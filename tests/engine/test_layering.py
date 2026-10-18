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


# ---------------------------------------------------------------- M4-03: the execution boundary (Laws 1, 2; D24, D32)

HARNESS_MAY_IMPORT = {"investment_engine.execution.worker", "investment_engine.execution.factory",
                      "investment_engine.execution.broker_port", "investment_engine.execution.simulated_broker"}
ANALYSIS = ("quant", "decision", "evaluation", "reporting", "research", "simulation")


def _modules(path: Path, root: Path) -> set[str]:
    """Every investment_engine module a file imports, fully named; `root` is the investment_engine directory."""
    names = set()
    parts = path.relative_to(root.parent).with_suffix("").parts
    package = ".".join(parts[:-1])  # the importing module's package (an __init__ is its own package)
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join([*parts, base]) if base else ".".join(parts)
            names.add(base)
            names |= {f"{base}.{a.name}" for a in node.names}
    return {n for n in names if n.startswith("investment_engine")}


def execution_boundary_offenders(package: Path) -> list[str]:
    """The four M4-03 rule-2 violations under `package` (an investment_engine tree)."""
    offenders = []
    for path in sorted(package.rglob("*.py")):
        rel = path.relative_to(package).as_posix()
        mods = _modules(path, package)
        execution = {m for m in mods if m == "investment_engine.execution" or m.startswith("investment_engine.execution.")}
        if rel.startswith("execution/"):
            bad = {m for m in mods for a in ANALYSIS if m == f"investment_engine.{a}" or m.startswith(f"investment_engine.{a}.")}
            if bad:
                offenders.append(f"{rel}: execution imports analysis/harness {sorted(bad)}")
        elif rel.startswith("simulation/"):
            bad = {m for m in execution if m not in HARNESS_MAY_IMPORT and m != "investment_engine.execution"}
            if bad:
                offenders.append(f"{rel}: the harness may import only {sorted(HARNESS_MAY_IMPORT)}, not {sorted(bad)}")
        elif execution:
            offenders.append(f"{rel}: imports the execution package {sorted(execution)}")
        if "investment_engine.execution.secrets" in mods and rel != "execution/__main__.py":
            offenders.append(f"{rel}: only execution/__main__.py reads the worker's secrets")
        if any(m == "investment_engine.simulation" or m.startswith("investment_engine.simulation.") for m in mods) \
                and rel not in ("intents_cli.py",) and not rel.startswith("simulation/"):
            offenders.append(f"{rel}: only intents_cli.py imports the simulation harness")
    return offenders


@pytest.mark.unit
def test_only_the_worker_reaches_the_broker_port_and_its_secrets():
    assert execution_boundary_offenders(PACKAGE) == []


@pytest.mark.unit
@pytest.mark.parametrize("rel, source, expected", [
    ("risk/bad.py", "from investment_engine.execution.broker_port import BrokerPort\n", "imports the execution"),
    ("oms/bad.py", "import investment_engine.execution.worker\n", "imports the execution"),
    ("simulation/run.py", "from investment_engine.execution.secrets import load_worker_secrets\n",
     "only execution/__main__.py"),
    ("simulation/run.py", "from investment_engine.execution.gate import check_gate\n", "the harness may import only"),
    ("execution/gate.py", "from investment_engine.quant import features\n", "execution imports analysis"),
    ("execution/worker.py", "from investment_engine.execution.secrets import load_worker_secrets\n",
     "only execution/__main__.py"),
    ("reporting/bad.py", "from investment_engine.simulation import run\n", "only intents_cli.py"),
], ids=["risk", "oms", "harness-secrets", "harness-gate", "execution-quant", "worker-secrets", "reporting-sim"])
def test_each_execution_rule_catches_its_fixture(tmp_path, rel, source, expected):
    package = tmp_path / "investment_engine"
    (package / rel).parent.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / rel).write_text(source, encoding="utf-8")
    offenders = execution_boundary_offenders(package)
    assert any(expected in o for o in offenders), offenders


@pytest.mark.unit
def test_the_harness_may_import_its_four_named_execution_modules(tmp_path):
    package = tmp_path / "investment_engine"
    (package / "simulation").mkdir(parents=True)
    (package / "simulation" / "run.py").write_text(
        "from investment_engine.execution import worker, factory, broker_port, simulated_broker\n"
        "import investment_engine.execution.worker\n", encoding="utf-8")
    assert execution_boundary_offenders(package) == []
