"""The browser bundle, built into a temporary directory and inspected (SPEC.md 14).

Everything here is offline. The one networked check -- re-reading the Pyodide index to see
whether the vendored trim has gone stale -- is ``build_static.py --check-lock``, which runs in
the Pages workflow and nowhere else.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_static
from dancepartner.i18n import TABLES, Language

REPO_ROOT = Path(__file__).resolve().parents[1]


def _build(tmp_path: Path, base_path: str = "/dancepartner/") -> Path:
    """Build into ``tmp_path`` and return it, asserting a clean exit."""
    assert build_static.main(["--out", str(tmp_path), "--base-path", base_path]) == 0
    return tmp_path


def _files(out: Path) -> dict[str, str]:
    """The virtual filesystem inlined into ``index.html``."""
    html = (out / "index.html").read_text(encoding="utf-8")
    match = re.search(r"files: (\{.*?\}),\n\s+requirements:", html, re.S)
    assert match, "the files mapping is not where the template puts it"
    parsed: dict[str, str] = json.loads(match.group(1))
    return parsed


def test_the_bundle_carries_the_whole_editor(tmp_path: Path) -> None:
    files = _files(_build(tmp_path))
    expected = {
        "app/Home.py",
        "app/common.py",
        "app/persistence.py",
        "app/pages/team.py",
        "app/pages/survey.py",
        "app/pages/solution.py",
        "app/pages/analysis.py",
        "data/team.example.yaml",
    }
    assert expected <= set(files)


def test_the_core_ships_where_the_entry_script_can_import_it(tmp_path: Path) -> None:
    """Under ``app/``, because Streamlit puts the entry script's directory on sys.path.

    That is the same mechanism the pages already rely on for ``import common``, and it leaves
    ``common.REPO_ROOT`` -- the parent of ``app/`` -- pointing at the directory holding
    ``data/``, so the example team resolves with no code change.
    """
    files = _files(_build(tmp_path))
    for module in ("__init__", "model", "storage", "i18n", "scoring", "feasibility", "reporting"):
        assert f"app/dancepartner/{module}.py" in files
    assert "data/team.example.yaml" in files


def test_the_solver_and_the_cli_are_left_out(tmp_path: Path) -> None:
    files = _files(_build(tmp_path))
    assert [name for name in files if name.endswith(("solver.py", "cli.py"))] == []


def test_nothing_in_the_bundle_imports_ortools(tmp_path: Path) -> None:
    """The build fails rather than shipping a page that dies on boot."""
    files = _files(_build(tmp_path))
    build_static._assert_no_ortools(files)  # must not raise on what was actually written


def test_the_build_refuses_a_module_that_imports_ortools() -> None:
    with pytest.raises(RuntimeError, match="ortools"):
        build_static._assert_no_ortools({"app/x.py": "from ortools.sat.python import cp_model\n"})


def test_the_stlite_version_is_pinned_not_floating(tmp_path: Path) -> None:
    html = (_build(tmp_path) / "index.html").read_text(encoding="utf-8")
    assert f"@stlite/browser@{build_static.STLITE_VERSION}/" in html
    assert "@stlite/browser@latest" not in html


def test_the_base_path_reaches_every_absolute_link(tmp_path: Path) -> None:
    """Project sites are served under /<repo>/, and getting this wrong is the usual failure."""
    out = _build(tmp_path)
    manifest = json.loads((out / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["start_url"] == "/dancepartner/"
    assert manifest["scope"] == "/dancepartner/"
    assert all(icon["src"].startswith("/dancepartner/icons/") for icon in manifest["icons"])
    html = (out / "index.html").read_text(encoding="utf-8")
    assert '"/dancepartner/manifest.webmanifest"' in html


def test_serving_from_the_root_needs_no_prefix(tmp_path: Path) -> None:
    out = _build(tmp_path, base_path="/")
    manifest = json.loads((out / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["start_url"] == "/"
    assert all(icon["src"].startswith("/icons/") for icon in manifest["icons"])


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("/dancepartner/", "/dancepartner/"),
        ("dancepartner", "/dancepartner/"),
        ("/", "/"),
        ("", "/"),
    ],
)
def test_a_base_path_is_normalised(given: str, expected: str) -> None:
    assert build_static.normalize_base_path(given) == expected


def test_the_icons_are_written(tmp_path: Path) -> None:
    icons = _build(tmp_path) / "icons"
    for name in ("icon-192.png", "icon-512.png", "icon-192-maskable.png", "icon-512-maskable.png"):
        assert (icons / name).is_file()


def test_the_shell_says_it_is_loading_in_both_languages(tmp_path: Path) -> None:
    """It renders before Python exists, so it cannot use the runtime language switch."""
    html = (_build(tmp_path) / "index.html").read_text(encoding="utf-8")
    assert TABLES[Language.EN]["ui.loading"] in html
    assert TABLES[Language.DE]["ui.loading"] in html


def test_the_draft_mount_matches_what_persistence_writes_to(tmp_path: Path) -> None:
    """Two places name this path; if they drift, the draft silently stops surviving reloads."""
    import persistence

    assert build_static.IDBFS_MOUNTPOINT == str(persistence.MOUNTPOINT)
    html = (_build(tmp_path) / "index.html").read_text(encoding="utf-8")
    assert f'idbfsMountpoints: ["{build_static.IDBFS_MOUNTPOINT}"]' in html


def test_the_draft_mount_is_a_single_top_level_directory() -> None:
    """A nested mountpoint fails the boot: stlite mounts with a bare, single-level FS.mkdir."""
    mount = build_static.IDBFS_MOUNTPOINT
    assert mount.startswith("/")
    assert mount.count("/") == 1, f"{mount} is nested; stlite cannot mkdir its parent"


def test_the_requirements_are_what_the_bundle_asks_micropip_for(tmp_path: Path) -> None:
    html = (_build(tmp_path) / "index.html").read_text(encoding="utf-8")
    match = re.search(r"requirements: (\[.*?\]),", html, re.S)
    assert match
    assert json.loads(match.group(1)) == build_static.read_requirements()


def test_rebuilding_replaces_the_previous_output(tmp_path: Path) -> None:
    out = _build(tmp_path)
    stale = out / "stale.txt"
    stale.write_text("from an older build", encoding="utf-8")
    _build(tmp_path)
    assert not stale.exists()
