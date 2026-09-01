"""The browser build's dependency rules, checked without a browser (SPEC.md 14).

Three things have to hold for the stlite target to boot, and all three fail invisibly -- a
white page and a stack trace in the browser console -- if they stop holding:

* every wheel in ``requirements-wasm.txt`` exists in the Pyodide distribution stlite loads,
  at exactly the pinned version;
* nothing the browser imports reaches ``ortools``, which has no WebAssembly wheel;
* ``dancepartner/__init__`` still resolves the solver names lazily, so importing the data
  model does not drag CP-SAT in.

All of it is offline: the Pyodide index is vendored at ``wasm/pyodide-lock.trimmed.json``. The
one networked check -- re-downloading that index to see whether it still matches -- lives in
the Pages workflow as ``build_static.py --check-lock``, never here.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE = REPO_ROOT / "src" / "dancepartner"
LOCKFILE = REPO_ROOT / "wasm" / "pyodide-lock.trimmed.json"
REQUIREMENTS = REPO_ROOT / "wasm" / "requirements-wasm.txt"

# Excluded from the bundle by wasm/build_static.py, so they may import whatever they like:
# solver.py is the only home of ortools, and the CLI never ships to a browser.
SERVER_ONLY = frozenset({"solver", "cli"})


def _normalize(name: str) -> str:
    """PEP 503 name comparison: the lockfile mixes ``-`` and ``_`` between entries."""
    return name.lower().replace("_", "-")


def _requirements() -> list[tuple[str, str]]:
    """Parse ``requirements-wasm.txt`` into ``(name, version)`` pairs."""
    pairs = []
    for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            name, _, version = line.partition("==")
            pairs.append((name.strip(), version.strip()))
    return pairs


def _packages() -> dict[str, str]:
    """The vendored Pyodide index, keyed by normalized name."""
    raw = json.loads(LOCKFILE.read_text(encoding="utf-8"))["packages"]
    return {_normalize(name): version for name, version in raw.items()}


def test_every_wheel_is_pinned_not_ranged() -> None:
    """A range is the failure mode, not a style nit -- see the file's header comment."""
    for name, version in _requirements():
        assert version, f"{name} must be pinned with ==, not left open"


def test_every_wheel_exists_in_the_pyodide_distribution_stlite_loads() -> None:
    """Exactly the pinned version, because pydantic_core has no wheel anywhere else."""
    available = _packages()
    for name, version in _requirements():
        key = _normalize(name)
        assert key in available, f"{name} is not in Pyodide {LOCKFILE.name}"
        assert available[key] == version, (
            f"{name} is pinned to {version} but Pyodide carries {available[key]}"
        )


def test_the_distribution_carries_no_solver() -> None:
    """The premise of the whole editor-only design: no CP-SAT in the browser."""
    available = _packages()
    assert "ortools" not in available
    assert [name for name, _ in _requirements() if _normalize(name) == "ortools"] == []


def _is_type_checking(test: ast.expr) -> bool:
    """Whether an ``if`` guards a block that only a type checker ever reads."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _runtime_imports(body: list[ast.stmt]) -> set[str]:
    """Modules imported when ``body`` actually runs, as bare top-level names.

    Three kinds of import are deliberately *not* counted, because none of them executes on
    the browser build: anything under ``if TYPE_CHECKING:``, anything inside a function (the
    deferred-import pattern this whole design rests on), and anything inside a class body.
    """
    found: set[str] = set()
    for node in body:
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and not node.module:  # from . import solver
                found.update(alias.name for alias in node.names)
            elif node.module:
                found.add(node.module.split(".")[0] if not node.level else node.module)
        elif isinstance(node, ast.If):
            if not _is_type_checking(node.test):
                found |= _runtime_imports(node.body)
            found |= _runtime_imports(node.orelse)
        elif isinstance(node, ast.Try):
            for block in (node.body, node.orelse, node.finalbody):
                found |= _runtime_imports(block)
            for handler in node.handlers:
                found |= _runtime_imports(handler.body)
    return found


def _imports(path: Path) -> set[str]:
    """The runtime import set of one module file."""
    return _runtime_imports(ast.parse(path.read_text(encoding="utf-8"), str(path)).body)


def test_the_browser_safe_core_never_reaches_ortools() -> None:
    """Walk the import closure of what ships, and prove ``solver`` is not in it.

    Transitive on purpose: a single module checked in isolation would miss the case that
    actually bit us, which is ``__init__`` re-exporting the solver and every submodule import
    running ``__init__`` first.
    """
    seen: set[str] = set()
    pending = ["__init__", "model", "storage", "i18n", "scoring", "feasibility", "reporting"]
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        path = CORE / f"{module}.py"
        assert path.exists(), f"{module} is listed as browser-safe but does not exist"
        for imported in _imports(path):
            head = imported.split(".")[0]
            assert head != "ortools", f"{module} imports ortools"
            if (CORE / f"{head}.py").exists():
                pending.append(head)

    assert not (seen & SERVER_ONLY), (
        f"the browser-safe closure reaches {sorted(seen & SERVER_ONLY)}; "
        "keep the solver re-export in dancepartner/__init__.py lazy (SPEC.md 14)"
    )


def test_the_ui_never_imports_the_solver_at_module_level() -> None:
    """Every solver reference in ``app/`` sits inside a function, behind SOLVER_AVAILABLE."""
    offenders = []
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in tree.body:  # module level only -- deferred imports live inside functions
            if isinstance(node, ast.ImportFrom) and node.module == "dancepartner.solver":
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


_NO_ORTOOLS = """
import sys


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name == "ortools" or name.startswith("ortools."):
            raise ImportError("the browser-safe core must not import ortools")
        return None


sys.meta_path.insert(0, _Blocker())

import dancepartner
from dancepartner.model import Team
from dancepartner.storage import parse_team

# dir() must still advertise the deferred names, or the public surface silently shrank.
assert "solve" in dir(dancepartner), dir(dancepartner)
assert "SolveResult" in dir(dancepartner)
"""


def test_the_core_imports_with_ortools_made_unimportable() -> None:
    """The runtime proof, in a subprocess so a blocked import cannot poison this session."""
    done = subprocess.run(
        [sys.executable, "-c", _NO_ORTOOLS],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert done.returncode == 0, done.stderr


def test_the_public_surface_still_advertises_the_deferred_names() -> None:
    """``dir()`` has to list them before first access, or the surface silently shrank.

    The subprocess above asserts the same thing without ortools; this covers the in-process
    path, so the lazy machinery is exercised on both sides of the capability.
    """
    import dancepartner

    listed = dir(dancepartner)
    assert {"solve", "SolveResult", "InfeasibleInstanceError"} <= set(listed)
    assert set(dancepartner.__all__) <= set(listed)


def test_the_lazy_reexport_still_resolves() -> None:
    """Deferring the import must not change what ``dancepartner.solve`` is."""
    pytest.importorskip("ortools")
    import dancepartner
    import dancepartner.solver

    assert dancepartner.solve is dancepartner.solver.solve
    assert dancepartner.SolveResult is dancepartner.solver.SolveResult
    with pytest.raises(AttributeError):
        _ = dancepartner.no_such_name
