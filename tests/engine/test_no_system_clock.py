"""Business code never reads the system clock (architecture Law 5; docs/tasks/M1-01.md).

Time comes from an injected Clock. The scan below fails on any reference to a
system-clock function anywhere in investment_engine except clock.py, where
LiveClock is the one sanctioned reader. It follows imports and aliases, so
`from datetime import datetime as dt; dt.now()` is caught as surely as
`datetime.datetime.now()`.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "investment_engine"
ALLOWED = PACKAGE / "clock.py"

SYSTEM_CLOCK = {
    "datetime.datetime.now",
    "datetime.datetime.utcnow",
    "datetime.datetime.today",
    "datetime.date.today",
    "time.time",
    "time.time_ns",
    "time.localtime",
    "time.gmtime",
}


def _system_clock_references(path: Path) -> list[str]:
    """Return 'line: name' for each reference to a system-clock function."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    def dotted(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return aliases.get(node.id)
        if isinstance(node, ast.Attribute):
            base = dotted(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name | ast.Attribute):
            name = dotted(node)
            if name in SYSTEM_CLOCK:
                found.append(f"{node.lineno}: {name}")
    return found


def _offenders(package: Path, allowed: Path | None) -> dict[str, list[str]]:
    return {
        str(path.relative_to(package.parent)): refs
        for path in sorted(package.rglob("*.py"))
        if path != allowed and (refs := _system_clock_references(path))
    }


@pytest.mark.unit
def test_the_scan_covers_the_package():
    # The rule below passes vacuously if the scan finds no files.
    assert (PACKAGE / "__init__.py").is_file()
    assert ALLOWED.is_file()


@pytest.mark.unit
def test_business_code_never_reads_the_system_clock():
    assert _offenders(PACKAGE, ALLOWED) == {}


@pytest.mark.unit
def test_clock_py_is_the_sanctioned_reader():
    # LiveClock reads the system clock here; if it stopped doing so, the
    # exemption above would be guarding nothing.
    assert _system_clock_references(ALLOWED)


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        "import datetime\nstamp = datetime.datetime.now()\n",
        "from datetime import datetime\nstamp = datetime.utcnow()\n",
        "from datetime import datetime as dt\nstamp = dt.today()\n",
        "from datetime import date\nday = date.today()\n",
        "import time\nstamp = time.time()\n",
        "import time as t\nstamp = t.time_ns()\n",
        "from time import localtime\nparts = localtime()\n",
        "from time import gmtime as g\nnow_fn = g\n",
    ],
)
def test_the_scan_catches_a_planted_system_clock_read(tmp_path, source):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "business.py").write_text(source, encoding="utf-8")
    assert list(_offenders(package, None)) == [str(Path("pkg") / "business.py")]


@pytest.mark.unit
def test_the_scan_ignores_safe_uses_of_the_same_modules(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "safe.py").write_text(
        "from datetime import UTC, datetime, timedelta\n"
        "import time\n"
        "start = datetime(2024, 6, 3, tzinfo=UTC) + timedelta(hours=1)\n"
        "time.sleep(0)\n",
        encoding="utf-8",
    )
    assert _offenders(package, None) == {}
