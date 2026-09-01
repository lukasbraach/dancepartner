"""Build the browser target: a static stlite bundle for GitHub Pages (SPEC.md 14).

Produces a directory that can be served by anything -- ``index.html`` with the whole app
inlined, a web manifest, and icons. There is no server, no Python runtime and no secret in it;
treat everything this writes as public.

What ships is the *editor*: Home, Team and Survey, plus the feasibility pre-check. Solving is
absent because ortools has no WebAssembly wheel, so ``solver.py`` and ``cli.py`` are excluded
outright rather than merely left unimported -- a stray ``import dancepartner.solver`` then
fails as a plain ModuleNotFoundError instead of a bewildering micropip error about a package
that was never going to resolve.

The virtual filesystem mirrors the repository, with one move: ``src/dancepartner/`` is written
to ``app/dancepartner/``. Streamlit puts the entry script's directory on ``sys.path`` -- the
same mechanism that lets the pages ``import common`` under ``make ui`` -- so the package rides
it, and ``common.REPO_ROOT`` (the parent of ``app/``) still lands where ``data/`` is.

Usage:
    python wasm/build_static.py --out wasm/dist --base-path /dancepartner/
    python wasm/build_static.py --check-lock      # the one step that needs the network
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import urllib.request
from pathlib import Path
from typing import Final

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from dancepartner.i18n import TABLES, Language

HERE: Final = Path(__file__).resolve().parent
REPO_ROOT: Final = HERE.parent

STLITE_VERSION: Final = "1.8.1"
"""Pinned, never a floating CDN tag: a bump moves Pyodide, and Pyodide pins pydantic."""

PYODIDE_VERSION: Final = "0.29.3"
"""What ``@stlite/browser`` 1.8.1 loads. Only used to re-check the vendored package index."""

SERVER_ONLY: Final = frozenset({"solver.py", "cli.py"})
"""Core modules kept out of the bundle -- the only two that import ortools and typer."""

DEFAULT_BASE_PATH: Final = "/dancepartner/"
"""GitHub Pages serves a project site under /<repo>/, not at the root."""

IDBFS_MOUNTPOINT: Final = "/mnt"
"""Where the draft lives, in IndexedDB. Must equal ``app/persistence.py``'s ``MOUNTPOINT``.

A single top-level directory, not a nested path: stlite mounts with a bare
``FS.mkdir(mountpoint)``, so the parent has to exist and the directory itself must not. Getting
this wrong fails the whole boot with an ErrnoError, before Streamlit renders anything.
``tests/test_static_build.py`` holds the two constants together.
"""

_LOCKFILE: Final = HERE / "pyodide-lock.trimmed.json"
_REQUIREMENTS: Final = HERE / "requirements-wasm.txt"


def normalize_base_path(value: str) -> str:
    """Force a base path into the ``/prefix/`` shape the manifest and asset links need."""
    trimmed = value.strip().strip("/")
    return f"/{trimmed}/" if trimmed else "/"


def read_requirements() -> list[str]:
    """The wheels micropip should install, comments and blank lines dropped."""
    lines = _REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    return [stripped for line in lines if (stripped := line.split("#", 1)[0].strip())]


def collect_files() -> dict[str, str]:
    """The virtual filesystem stlite mounts, as ``virtual path -> file contents``.

    Raises:
        RuntimeError: A module that imports ortools slipped into the bundle.
    """
    files: dict[str, str] = {}

    def add(virtual: str, source: Path) -> None:
        files[virtual] = source.read_text(encoding="utf-8")

    app = REPO_ROOT / "app"
    add("app/Home.py", app / "Home.py")
    add("app/common.py", app / "common.py")
    add("app/persistence.py", app / "persistence.py")
    for page in sorted((app / "pages").glob("*.py")):
        add(f"app/pages/{page.name}", page)

    for module in sorted((REPO_ROOT / "src" / "dancepartner").glob("*.py")):
        if module.name not in SERVER_ONLY:
            add(f"app/dancepartner/{module.name}", module)

    add("data/team.example.yaml", REPO_ROOT / "data" / "team.example.yaml")

    _assert_no_ortools(files)
    return files


def _assert_no_ortools(files: dict[str, str]) -> None:
    """Fail the build if anything in the bundle would import ortools.

    Checked as imports rather than as the substring ``ortools``: ``app/common.py`` names the
    package legitimately, in the ``find_spec`` capability probe, and several modules mention
    it in prose. What must not appear is an import that could actually run.

    Raises:
        RuntimeError: A bundled module imports ortools.
    """
    offenders = []
    for name, text in files.items():
        if not name.endswith(".py"):
            continue
        for node in ast.walk(ast.parse(text, name)):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(n == "ortools" or n.startswith("ortools.") for n in names):
                offenders.append(name)
                break
    if offenders:
        raise RuntimeError(
            f"the browser bundle must not import ortools: {sorted(offenders)}; "
            "it has no WebAssembly wheel (SPEC.md 14)"
        )


def render(out: Path, base_path: str) -> None:
    """Write ``index.html``, the manifest and the icons into ``out``."""
    env = Environment(  # noqa: S701 -- output is HTML we author, values are JSON-encoded
        loader=FileSystemLoader(HERE),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    files = collect_files()
    context = {
        "base_path": base_path,
        "stlite_version": STLITE_VERSION,
        # The shell renders before Python exists, so it cannot use the runtime language
        # switch. Both languages go in, which is the one sanctioned exception to SPEC.md 2.
        "title": TABLES[Language.EN]["ui.title"],
        "description": TABLES[Language.EN]["ui.subtitle"],
        "loading_en": TABLES[Language.EN]["ui.loading"],
        "loading_de": TABLES[Language.DE]["ui.loading"],
        "files_json": json.dumps(files, ensure_ascii=False),
        "requirements_json": json.dumps(read_requirements()),
        "idbfs_mountpoint": IDBFS_MOUNTPOINT,
    }

    out.mkdir(parents=True, exist_ok=True)
    pages = (("index.html.j2", "index.html"), ("manifest.webmanifest.j2", "manifest.webmanifest"))
    for template, name in pages:
        (out / name).write_text(env.get_template(template).render(**context), encoding="utf-8")

    icons = out / "icons"
    icons.mkdir(exist_ok=True)
    for icon in sorted((HERE / "static").glob("*.png")):
        shutil.copyfile(icon, icons / icon.name)


def check_lock() -> int:
    """Re-download the Pyodide index and diff it against the vendored trim. Needs the network.

    Runs in the Pages workflow, never in the test suite: this is what fails loudly the day a
    stlite bump moves pydantic out from under ``requirements-wasm.txt``.

    Returns:
        A process exit code.
    """
    url = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/pyodide-lock.json"
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 -- literal https
        live = json.loads(response.read())["packages"]
    vendored = json.loads(_LOCKFILE.read_text(encoding="utf-8"))["packages"]

    drift = [
        f"  {name}: vendored {version}, live {live.get(name, {}).get('version', 'absent')}"
        for name, version in vendored.items()
        if live.get(name, {}).get("version") != version
    ]
    if drift:
        print(f"{_LOCKFILE.name} is stale against Pyodide {PYODIDE_VERSION}:", *drift, sep="\n")
        return 1
    print(f"{_LOCKFILE.name} matches Pyodide {PYODIDE_VERSION} ({len(vendored)} packages).")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Build the bundle.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        A process exit code.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=HERE / "dist", help="output directory")
    parser.add_argument(
        "--base-path",
        default=DEFAULT_BASE_PATH,
        help=f"path the site is served under (default {DEFAULT_BASE_PATH}); / to serve locally",
    )
    parser.add_argument(
        "--check-lock",
        action="store_true",
        help="verify the vendored Pyodide index against the CDN instead of building",
    )
    args = parser.parse_args(argv)

    if args.check_lock:
        return check_lock()

    out = Path(args.out)
    base_path = normalize_base_path(args.base_path)
    if out.exists():
        shutil.rmtree(out)
    render(out, base_path)

    total = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    print(f"built {out} for base path {base_path} ({total / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
