"""Tests for the OER diff and update logic.

These build a fake packaged ``data/`` tree under ``tmp_path`` and monkeypatch
``quadriga_scaffolding.scaffold.package_data_root`` to return it. A ``Path``
exposes enough of the ``Traversable`` API (``iterdir``, ``joinpath``,
``read_bytes``, ``is_file``, ``is_dir``, ``name``) for the helpers under test.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from quadriga_scaffolding import scaffold as sc
from quadriga_scaffolding.scaffold import (
    DiffItem,
    EntryKind,
    EntryStatus,
    OerDiff,
    Scaffold,
    ScaffoldEntry,
    apply_update,
    diff_oer,
    format_diff,
    iter_packaged_files,
)

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_BAD_MANIFEST = 2


def _write(root: Path, rel: str, content: bytes) -> Path:
    """Write ``content`` to ``root/rel``, creating parents, and return the path."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def pkg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake packaged data/ root, registered as ``package_data_root``."""
    data = tmp_path / "pkg"
    data.mkdir()
    monkeypatch.setattr(sc, "package_data_root", lambda: data)
    return data


@pytest.fixture
def oer(tmp_path: Path) -> Path:
    """An empty OER root directory."""
    root = tmp_path / "oer"
    root.mkdir()
    return root


def test_iter_packaged_files_expands_directory(pkg: Path) -> None:
    _write(pkg, "d/a.py", b"a")
    _write(pkg, "d/sub/b.py", b"b")
    entry = ScaffoldEntry(EntryKind.DIR, Path("d"))
    assert set(iter_packaged_files(entry)) == {Path("d/a.py"), Path("d/sub/b.py")}


def test_diff_detects_add(pkg: Path, oer: Path) -> None:
    _write(pkg, "f.py", b"hi")
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.FILE, Path("f.py"))])
    diff = diff_oer(scaffold, oer)
    assert diff.items == [DiffItem(EntryStatus.ADD, Path("f.py"))]


def test_diff_detects_modify(pkg: Path, oer: Path) -> None:
    _write(pkg, "f.py", b"new")
    _write(oer, "f.py", b"old")
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.FILE, Path("f.py"))])
    diff = diff_oer(scaffold, oer)
    assert diff.items == [DiffItem(EntryStatus.MODIFY, Path("f.py"))]


def test_diff_reports_ok_when_bytes_match(pkg: Path, oer: Path) -> None:
    _write(pkg, "f.py", b"same")
    _write(oer, "f.py", b"same")
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.FILE, Path("f.py"))])
    diff = diff_oer(scaffold, oer)
    assert diff.items == [DiffItem(EntryStatus.OK, Path("f.py"))]
    assert not diff.has_drift()


def test_diff_reports_untracked_inside_managed_dir(pkg: Path, oer: Path) -> None:
    _write(pkg, "d/a.py", b"a")
    _write(oer, "d/a.py", b"a")
    _write(oer, "d/extra.py", b"x")
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.DIR, Path("d"))])
    diff = diff_oer(scaffold, oer)
    assert DiffItem(EntryStatus.UNTRACKED, Path("d/extra.py")) in diff.items


def test_diff_dedups_path_covered_by_dir_and_file(pkg: Path, oer: Path) -> None:
    """A path under both `+ dir/` and `+ file` yields one item, the most-drifted status."""
    _write(pkg, "d/a.py", b"a")
    # OER matches the packaged file, so the dir entry alone would report OK;
    # the explicit file entry reports the same path. Either way: one item.
    _write(oer, "d/a.py", b"a")
    scaffold = Scaffold(
        create=[
            ScaffoldEntry(EntryKind.DIR, Path("d")),
            ScaffoldEntry(EntryKind.FILE, Path("d/a.py")),
        ]
    )
    diff = diff_oer(scaffold, oer)
    assert diff.items == [DiffItem(EntryStatus.OK, Path("d/a.py"))]

    # Now make it drift: the modify status must win over a hypothetical ok.
    (oer / "d" / "a.py").write_bytes(b"changed")
    diff = diff_oer(scaffold, oer)
    assert diff.items == [DiffItem(EntryStatus.MODIFY, Path("d/a.py"))]


def test_diff_delete_file_present_and_absent(pkg: Path, oer: Path) -> None:
    scaffold = Scaffold(delete=[ScaffoldEntry(EntryKind.FILE, Path("gone.py"))])
    assert diff_oer(scaffold, oer).items == []  # absent -> omitted

    _write(oer, "gone.py", b"x")
    diff = diff_oer(scaffold, oer)
    assert diff.items == [DiffItem(EntryStatus.DELETE, Path("gone.py"))]


def test_diff_delete_empty_dir(pkg: Path, oer: Path) -> None:
    (oer / "empty" / "nested").mkdir(parents=True)
    scaffold = Scaffold(delete=[ScaffoldEntry(EntryKind.DIR, Path("empty"))])
    diff = diff_oer(scaffold, oer)
    assert diff.items == [DiffItem(EntryStatus.DELETE, Path("empty"))]


def test_diff_delete_nonempty_dir_is_blocked(pkg: Path, oer: Path) -> None:
    _write(oer, "full/a.py", b"a")
    _write(oer, "full/b.py", b"b")
    scaffold = Scaffold(delete=[ScaffoldEntry(EntryKind.DIR, Path("full"))])
    diff = diff_oer(scaffold, oer)
    assert len(diff.items) == 1
    item = diff.items[0]
    assert item.status is EntryStatus.BLOCKED
    assert item.path == Path("full")
    assert "2" in item.detail


def test_apply_update_resolves_add_modify_delete(pkg: Path, oer: Path) -> None:
    _write(pkg, "add.py", b"added")
    _write(pkg, "mod.py", b"new")
    _write(oer, "mod.py", b"old")
    _write(oer, "del.py", b"bye")
    scaffold = Scaffold(
        create=[
            ScaffoldEntry(EntryKind.FILE, Path("add.py")),
            ScaffoldEntry(EntryKind.FILE, Path("mod.py")),
        ],
        delete=[ScaffoldEntry(EntryKind.FILE, Path("del.py"))],
    )
    post = apply_update(scaffold, oer, diff_oer(scaffold, oer))
    assert (oer / "add.py").read_bytes() == b"added"
    assert (oer / "mod.py").read_bytes() == b"new"
    assert not (oer / "del.py").exists()
    assert not post.has_drift()


def test_apply_update_leaves_untracked_in_place(pkg: Path, oer: Path) -> None:
    _write(pkg, "d/a.py", b"a")
    _write(oer, "d/a.py", b"a")
    _write(oer, "d/extra.py", b"x")
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.DIR, Path("d"))])
    post = apply_update(scaffold, oer, diff_oer(scaffold, oer))
    assert (oer / "d" / "extra.py").read_bytes() == b"x"
    drifted = [i for i in post.items if i.status is not EntryStatus.OK]
    assert drifted == [DiffItem(EntryStatus.UNTRACKED, Path("d/extra.py"))]


def test_apply_update_does_not_remove_blocked_dir(pkg: Path, oer: Path) -> None:
    _write(oer, "full/a.py", b"a")
    scaffold = Scaffold(delete=[ScaffoldEntry(EntryKind.DIR, Path("full"))])
    post = apply_update(scaffold, oer, diff_oer(scaffold, oer))
    assert (oer / "full" / "a.py").exists()
    assert post.items[0].status is EntryStatus.BLOCKED


def test_apply_update_is_idempotent(pkg: Path, oer: Path) -> None:
    _write(pkg, "add.py", b"added")
    _write(pkg, "mod.py", b"new")
    _write(oer, "mod.py", b"old")
    _write(oer, "del.py", b"bye")
    scaffold = Scaffold(
        create=[
            ScaffoldEntry(EntryKind.FILE, Path("add.py")),
            ScaffoldEntry(EntryKind.FILE, Path("mod.py")),
        ],
        delete=[ScaffoldEntry(EntryKind.FILE, Path("del.py"))],
    )
    first = apply_update(scaffold, oer, diff_oer(scaffold, oer))
    second = apply_update(scaffold, oer, first)
    assert not second.has_drift()


def test_format_diff_letters_and_detail() -> None:
    """format_diff maps each status to its legend letter and appends details.

    Items are rendered in the order given (diff_oer is responsible for the
    drift-first ordering); here we pin the per-status letter mapping.
    """
    diff = OerDiff(
        items=[
            DiffItem(EntryStatus.ADD, Path("new.py")),
            DiffItem(EntryStatus.MODIFY, Path("changed.css")),
            DiffItem(EntryStatus.DELETE, Path("old.py")),
            DiffItem(EntryStatus.UNTRACKED, Path("d/extra.py")),
            DiffItem(EntryStatus.BLOCKED, Path("legacy"), detail="3 files inside"),
            DiffItem(EntryStatus.OK, Path("ok.py")),
        ]
    )
    out = format_diff(diff, show_ok=True)
    assert out.splitlines() == [
        "A new.py",
        "M changed.css",
        "D old.py",
        "? d/extra.py",
        "! legacy (3 files inside)",
        "  ok.py",
    ]


def test_format_diff_skips_ok_by_default() -> None:
    diff = OerDiff(items=[DiffItem(EntryStatus.OK, Path("ok.py"))])
    assert format_diff(diff) == ""
    assert format_diff(diff, show_ok=True) == "  ok.py"


def _run_cli(oer: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "quadriga_scaffolding", str(oer), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_exit_codes(tmp_path: Path) -> None:
    """End-to-end exit codes against the real packaged manifest/data."""
    oer = tmp_path / "oer"
    oer.mkdir()
    real = sc.load_scaffold()

    # Build a clean OER from the real packaged tree.
    for entry in real.create:
        for rel in iter_packaged_files(entry):
            _write(oer, str(rel), sc.read_packaged_bytes(rel))
    assert _run_cli(oer).returncode == EXIT_OK

    # Drift: modify a tracked file.
    first_file = next(
        rel for entry in real.create for rel in iter_packaged_files(entry) if entry.kind is EntryKind.FILE
    )
    (oer / first_file).write_bytes(b"drifted")
    assert _run_cli(oer).returncode == EXIT_DRIFT

    # Broken manifest: same path under create and delete -> validate fails -> exit 2.
    manifest = tmp_path / "broken.txt"
    manifest.write_text(f"+ {first_file.as_posix()}\n- {first_file.as_posix()}\n")
    assert _run_cli(oer, "--manifest", str(manifest)).returncode == EXIT_BAD_MANIFEST
