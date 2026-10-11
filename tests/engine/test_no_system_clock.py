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


_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


class _Scope:
    """One Python scope (module, function or class) and the names it binds.

    `imports` maps a name to every module path an import in this scope binds
    it to; `other` holds names this scope binds some other way (assignment,
    parameter, def). A name bound in a scope is local to all of it, so its
    import candidates are all considered: the scan errs towards flagging.
    """

    def __init__(self, node: ast.AST, parent: "_Scope | None"):
        self.node, self.parent = node, parent
        self.imports: dict[str, set[str]] = {}
        self.other: set[str] = set()
        self.globals: set[str] = set()
        self.children: dict[ast.AST, _Scope] = {}

    def binds(self, name: str) -> bool:
        return name in self.imports or name in self.other


def _outside_comprehensions(scope: _Scope) -> _Scope:
    while isinstance(scope.node, _COMPREHENSIONS):
        scope = scope.parent
    return scope


def _comprehension_parts(node: ast.AST) -> tuple[ast.AST, list[ast.AST]]:
    """Split a comprehension into its first iterable (evaluated in the
    enclosing scope) and everything else (evaluated in its own scope)."""
    first, *rest = node.generators
    inner: list[ast.AST] = [first.target, *first.ifs]
    for gen in rest:
        inner += [gen.target, gen.iter, *gen.ifs]
    inner += [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
    return first.iter, inner


def _bind(node: ast.AST, scope: _Scope, module: _Scope) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _COMPREHENSIONS):
            first_iter, inner_parts = _comprehension_parts(child)
            _bind_node(first_iter, scope, module)
            inner = scope.children[child] = _Scope(child, scope)
            for part in inner_parts:
                _bind_node(part, inner, module)
        elif isinstance(child, ast.NamedExpr):
            # `x := …` binds in the enclosing function, even from inside a
            # comprehension.
            target = _outside_comprehensions(scope)
            (module if child.target.id in target.globals else target).other.add(child.target.id)
            _bind_node(child.value, scope, module)
        elif isinstance(child, _SCOPE_NODES):
            scope.other.add(child.name)
            inner = scope.children[child] = _Scope(child, scope)
            if not isinstance(child, ast.ClassDef):
                args = child.args
                for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
                    if arg is not None:
                        inner.other.add(arg.arg)
            _bind(child, inner, module)
        elif isinstance(child, ast.Global):
            scope.globals.update(child.names)
        elif isinstance(child, ast.Import | ast.ImportFrom):
            if isinstance(child, ast.ImportFrom) and (child.level or not child.module):
                continue
            for alias in child.names:
                if isinstance(child, ast.Import):
                    name = alias.asname or alias.name.split(".")[0]
                    target = alias.name if alias.asname else alias.name.split(".")[0]
                else:
                    name, target = alias.asname or alias.name, f"{child.module}.{alias.name}"
                owner = module if name in scope.globals else scope
                owner.imports.setdefault(name, set()).add(target)
        else:
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store | ast.Del):
                (module if child.id in scope.globals else scope).other.add(child.id)
            _bind(child, scope, module)


def _bind_node(node: ast.AST, scope: _Scope, module: _Scope) -> None:
    """Bind `node` itself as well as its children (`_bind` covers children only)."""
    holder = ast.Expr(value=node) if isinstance(node, ast.expr) else ast.Module(body=[node], type_ignores=[])
    _bind(holder, scope, module)


def _candidates(scope: _Scope, module: _Scope, name: str) -> set[str]:
    """What `name` may refer to in `scope`, resolved as Python does (LEGB).

    Class bodies are not visible from functions nested inside them.
    """
    current, innermost = scope, True
    while current is not None:
        if name in current.globals:
            current = module
        if (innermost or not isinstance(current.node, ast.ClassDef)) and current.binds(name):
            return current.imports.get(name, set())
        current, innermost = current.parent, False
    return set()


def _visit(node: ast.AST, scope: _Scope, module: _Scope, found: list[str]) -> None:
    if isinstance(node, _COMPREHENSIONS) and node in scope.children:
        first_iter, inner_parts = _comprehension_parts(node)
        _visit(first_iter, scope, module, found)
        for part in inner_parts:
            _visit(part, scope.children[node], module, found)
        return
    if node in scope.children:
        # A def or class: decorators, defaults, annotations and base classes
        # are evaluated in the enclosing scope; only the body runs in its own.
        for field, value in ast.iter_fields(node):
            target = scope.children[node] if field == "body" else scope
            for part in value if isinstance(value, list) else [value]:
                if isinstance(part, ast.AST):
                    _visit(part, target, module, found)
        return
    _check(node, scope, module, found)
    for child in ast.iter_child_nodes(node):
        _visit(child, scope, module, found)


def _check(node: ast.AST, scope: _Scope, module: _Scope, found: list[str]) -> None:
    if isinstance(node, ast.Name | ast.Attribute):
        for name in sorted(_dotted(node, scope, module) & SYSTEM_CLOCK):
            found.append(f"{node.lineno}: {name}")


def _dotted(node: ast.expr, scope: _Scope, module: _Scope) -> set[str]:
    if isinstance(node, ast.Name):
        return _candidates(scope, module, node.id)
    if isinstance(node, ast.Attribute):
        return {f"{base}.{node.attr}" for base in _dotted(node.value, scope, module)}
    return set()


def _system_clock_references(path: Path) -> list[str]:
    """Return 'line: name' for each reference to a system-clock function."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module = _Scope(tree, None)
    _bind(tree, module, module)
    found: list[str] = []
    for child in ast.iter_child_nodes(tree):
        _visit(child, module, module, found)
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


FUNCTION_LOCAL_READ = (
    "def bad():\n"
    "    from datetime import datetime\n"
    "    return datetime.now()\n"
)
FUNCTION_LOCAL_MODULE_IMPORT = (
    "def format_timestamp(t):\n"
    "    import datetime\n"
    "    return datetime.datetime.fromtimestamp(t)\n"
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        FUNCTION_LOCAL_READ + "\n" + FUNCTION_LOCAL_MODULE_IMPORT,
        FUNCTION_LOCAL_MODULE_IMPORT + "\n" + FUNCTION_LOCAL_READ,
    ],
    ids=["read-first", "read-last"],
)
def test_another_functions_import_cannot_hide_a_read(tmp_path, source):
    # Codex finding on M1-01: one function's `import datetime` must not
    # change what `datetime` means inside another function.
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "business.py").write_text(source, encoding="utf-8")
    offenders = _offenders(package, None)
    assert list(offenders) == [str(Path("pkg") / "business.py")]
    assert [ref.split(": ")[1] for ref in offenders[str(Path("pkg") / "business.py")]] == [
        "datetime.datetime.now"
    ]


@pytest.mark.unit
@pytest.mark.parametrize("local_import_first", [True, False], ids=["local-first", "local-last"])
def test_a_local_import_cannot_hide_a_read_through_a_module_import(tmp_path, local_import_first):
    # Codex finding on M1-01: a module-level `from datetime import datetime`
    # still applies in a function that has no import of its own, whatever
    # other functions import locally.
    reader = "def stamp():\n    return datetime.now()\n"
    local = "def fmt(t):\n    import datetime\n    return datetime.datetime.fromtimestamp(t)\n"
    body = local + "\n" + reader if local_import_first else reader + "\n" + local
    source = "from datetime import datetime\n\n" + body
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "business.py").write_text(source, encoding="utf-8")
    offenders = _offenders(package, None)
    assert list(offenders) == [str(Path("pkg") / "business.py")]
    assert [ref.split(": ")[1] for ref in offenders[str(Path("pkg") / "business.py")]] == [
        "datetime.datetime.now"
    ]


@pytest.mark.unit
def test_a_local_rebinding_is_not_mistaken_for_a_read(tmp_path):
    # Scoping works both ways: inside fmt(), `datetime` is the module, so
    # datetime.datetime.fromtimestamp is safe even though the module level
    # binds `datetime` to the class.
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "safe.py").write_text(
        "from datetime import UTC, datetime\n\n"
        "START = datetime(2024, 6, 3, tzinfo=UTC)\n\n"
        "def fmt(t):\n"
        "    import datetime\n"
        "    return datetime.datetime.fromtimestamp(t, datetime.UTC)\n",
        encoding="utf-8",
    )
    assert _offenders(package, None) == {}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # A `global` import inside one function binds the module-level name.
        (
            "def setup():\n    global datetime\n    from datetime import datetime\n\n"
            "def use():\n    return datetime.now()\n",
            ["datetime.datetime.now"],
        ),
        # A class body's import is visible in the class body...
        ("class C:\n    from datetime import datetime\n    STAMP = datetime.now()\n", ["datetime.datetime.now"]),
        # ...but not inside its methods, where a parameter shadows it.
        ("class C:\n    from datetime import datetime\n    def m(self, datetime):\n        return datetime.now()\n", []),
        # A nested function sees its enclosing function's import.
        ("def outer():\n    import time\n    def inner():\n        return time.time()\n    return inner\n", ["time.time"]),
        # Defaults and decorators are evaluated in the enclosing scope.
        ("import time\ndef deco(f):\n    return f\n@deco\ndef g(x=time.time()):\n    return x\n", ["time.time"]),
        # A parameter shadows a module-level import.
        ("from datetime import datetime\ndef f(datetime):\n    return datetime.now()\n", []),
        # Nested comprehensions: an inner loop variable shadows only inside it...
        (
            "from datetime import datetime as dt\ndef f(vs):\n"
            "    x = [[dt for dt in row] for row in vs]\n    return dt.now()\n",
            ["datetime.datetime.now"],
        ),
        # ...and an outer loop variable is visible to the inner one.
        ("from datetime import datetime as dt\ndef f(vs):\n    return [[dt.now() for _ in row] for dt in vs]\n", []),
        # A later `for` clause's iterable sees earlier loop variables.
        ("from datetime import datetime as dt\ndef f(vs):\n    return [x for dt in vs for x in dt.now()]\n", []),
        # `:=` inside a comprehension binds in the enclosing function.
        ("from datetime import datetime as dt\ndef f(vs):\n    [(dt := v) for v in vs]\n    return dt.now()\n", []),
        # A comprehension in a class body sees module-level imports.
        ("from datetime import datetime as dt\nclass C:\n    xs = [dt.now() for _ in range(1)]\n", ["datetime.datetime.now"]),
    ],
    ids=[
        "global", "class-body", "method-param", "nested", "default-arg", "param-shadow",
        "nested-comp-inner", "nested-comp-outer", "later-for-clause", "walrus", "class-comp",
    ],
)
def test_the_scan_follows_python_scoping(tmp_path, source, expected):
    path = tmp_path / "module.py"
    path.write_text(source, encoding="utf-8")
    assert [ref.split(": ")[1] for ref in _system_clock_references(path)] == expected


COMPREHENSIONS = {
    "list": "[{elt} for {var} in {it}{cond}]",
    "set": "{{{elt} for {var} in {it}{cond}}}",
    "dict": "{{{var}: {elt} for {var} in {it}{cond}}}",
    "generator": "list({elt} for {var} in {it}{cond})",
}


def _comprehension_module(kind: str, *, elt: str, var: str, it: str, cond: str = "", after: str = "") -> str:
    expr = COMPREHENSIONS[kind].format(elt=elt, var=var, it=it, cond=cond)
    return (
        "from datetime import datetime as dt\n\n"
        "def stamp(values):\n"
        f"    labels = {expr}\n"
        f"    return {after or 'labels'}\n"
    )


def _scan_source(tmp_path, source: str) -> list[str]:
    path = tmp_path / "module.py"
    path.write_text(source, encoding="utf-8")
    return [ref.split(": ")[1] for ref in _system_clock_references(path)]


@pytest.mark.unit
@pytest.mark.parametrize("kind", list(COMPREHENSIONS))
def test_a_comprehension_variable_cannot_hide_an_enclosing_import(tmp_path, kind):
    # Codex finding on M1-01: the iteration variable `dt` belongs to the
    # comprehension, not the function, so `dt.now()` afterwards is still
    # datetime.now.
    source = _comprehension_module(kind, elt="dt.isoformat()", var="dt", it="values", after="dt.now()")
    assert _scan_source(tmp_path, source) == ["datetime.datetime.now"]


@pytest.mark.unit
@pytest.mark.parametrize("kind", list(COMPREHENSIONS))
@pytest.mark.parametrize(
    ("place", "parts"),
    [
        ("element", {"elt": "dt.now()", "var": "v", "it": "values"}),
        ("condition", {"elt": "v", "var": "v", "it": "values", "cond": " if dt.now()"}),
        # The first iterable is evaluated in the enclosing scope, so even a
        # loop variable named `dt` doesn't hide the import there.
        ("first-iterable", {"elt": "dt", "var": "dt", "it": "[dt.now()]"}),
    ],
)
def test_a_read_inside_a_comprehension_is_still_caught(tmp_path, kind, place, parts):
    assert _scan_source(tmp_path, _comprehension_module(kind, **parts)) == ["datetime.datetime.now"]


@pytest.mark.unit
@pytest.mark.parametrize("kind", list(COMPREHENSIONS))
def test_a_comprehension_variable_shadows_inside_its_own_scope(tmp_path, kind):
    # Inside the comprehension `dt` is each value, not the datetime class.
    source = _comprehension_module(kind, elt="dt.now()", var="dt", it="values")
    assert _scan_source(tmp_path, source) == []


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
