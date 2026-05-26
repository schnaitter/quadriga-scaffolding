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
    colorize_diff,
    diff_file,
    diff_oer,
    files_differ,
    format_diff,
    format_diff_with_content,
    is_ignored,
    iter_packaged_files,
    should_colorize,
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


def test_files_differ_by_content(pkg: Path, oer: Path) -> None:
    _write(pkg, "f.py", b"same")
    same = _write(oer, "f.py", b"same")
    assert files_differ(same, Path("f.py")) is False
    same.write_bytes(b"changed")
    assert files_differ(same, Path("f.py")) is True


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


@pytest.mark.parametrize(
    ("rel", "ignored"),
    [
        ("pkg/__pycache__/mod.cpython-314.pyc", True),
        ("a/b/__pycache__/x.pyc", True),
        ("mod.pyc", True),
        ("mod.pyo", True),
        (".DS_Store", True),
        ("sub/.DS_Store", True),
        (".ipynb_checkpoints/nb.ipynb", True),
        (".git/config", True),
        ("quadriga/colors.py", False),
        ("_static/quadriga.css", False),
    ],
)
def test_is_ignored(rel: str, ignored: bool) -> None:
    assert is_ignored(Path(rel)) is ignored


def test_iter_packaged_files_skips_artifacts(pkg: Path) -> None:
    _write(pkg, "d/a.py", b"a")
    _write(pkg, "d/__pycache__/a.cpython-314.pyc", b"junk")
    _write(pkg, "d/.DS_Store", b"junk")
    entry = ScaffoldEntry(EntryKind.DIR, Path("d"))
    assert set(iter_packaged_files(entry)) == {Path("d/a.py")}


def test_diff_does_not_report_artifacts_as_untracked(pkg: Path, oer: Path) -> None:
    _write(pkg, "d/a.py", b"a")
    _write(oer, "d/a.py", b"a")
    _write(oer, "d/__pycache__/a.cpython-314.pyc", b"junk")
    _write(oer, "d/.DS_Store", b"junk")
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.DIR, Path("d"))])
    diff = diff_oer(scaffold, oer)
    assert not diff.has_drift()


def test_delete_dir_with_only_artifacts_is_empty(pkg: Path, oer: Path) -> None:
    _write(oer, "old/__pycache__/x.pyc", b"junk")
    _write(oer, "old/.DS_Store", b"junk")
    scaffold = Scaffold(delete=[ScaffoldEntry(EntryKind.DIR, Path("old"))])
    diff = diff_oer(scaffold, oer)
    assert diff.items == [DiffItem(EntryStatus.DELETE, Path("old"))]
    apply_update(scaffold, oer, diff)
    assert not (oer / "old").exists()


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


def test_diff_blocks_symlinked_tracked_file(pkg: Path, oer: Path) -> None:
    """A tracked file that is a symlink is BLOCKED, never compared through its target."""
    _write(pkg, "f.py", b"packaged")
    outside = _write(oer.parent, "outside.py", b"link target")
    (oer / "f.py").symlink_to(outside)
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.FILE, Path("f.py"))])
    diff = diff_oer(scaffold, oer)
    assert diff.items == [DiffItem(EntryStatus.BLOCKED, Path("f.py"), detail="symlink")]


def test_apply_update_does_not_write_through_symlinked_file(pkg: Path, oer: Path) -> None:
    """--update never follows a symlinked target: the link's target stays untouched."""
    _write(pkg, "f.py", b"packaged")
    outside = _write(oer.parent, "outside.py", b"link target")
    (oer / "f.py").symlink_to(outside)
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.FILE, Path("f.py"))])
    post = apply_update(scaffold, oer, diff_oer(scaffold, oer))
    assert outside.read_bytes() == b"link target"  # not clobbered through the link
    assert (oer / "f.py").is_symlink()  # link itself left in place
    assert post.items == [DiffItem(EntryStatus.BLOCKED, Path("f.py"), detail="symlink")]


def test_diff_blocks_file_under_symlinked_parent_dir(pkg: Path, oer: Path) -> None:
    """A packaged file whose OER parent dir is a symlink is BLOCKED, not written through."""
    _write(pkg, "d/a.py", b"a")
    real = oer.parent / "real_d"
    real.mkdir()
    (oer / "d").symlink_to(real, target_is_directory=True)
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.DIR, Path("d"))])
    diff = diff_oer(scaffold, oer)
    assert DiffItem(EntryStatus.BLOCKED, Path("d/a.py"), detail="symlink") in diff.items
    apply_update(scaffold, oer, diff)
    assert not (real / "a.py").exists()  # nothing written into the link target


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


def test_diff_file_unified_diff(pkg: Path, oer: Path) -> None:
    _write(pkg, "f.py", b"one\ntwo\nthree\n")
    target = _write(oer, "f.py", b"one\nTWO\nthree\n")
    out = diff_file(target, Path("f.py"))
    lines = out.splitlines()
    assert lines[0] == "--- a/f.py"
    assert lines[1] == "+++ b/f.py"
    assert "-two" in lines
    assert "+TWO" in lines


def test_diff_file_binary_files_differ(pkg: Path, oer: Path) -> None:
    _write(pkg, "img.bin", b"\x00\x01\x02")
    target = _write(oer, "img.bin", b"\x00\x03\x04")
    assert diff_file(target, Path("img.bin")) == "Binary files a/img.bin and b/img.bin differ"


def test_diff_file_invalid_utf8_is_binary(pkg: Path, oer: Path) -> None:
    _write(pkg, "f.dat", b"\xff\xfe text")
    target = _write(oer, "f.dat", b"\xff\xfe other")
    assert diff_file(target, Path("f.dat")) == "Binary files a/f.dat and b/f.dat differ"


def test_format_diff_with_content_appends_diff_after_modify(pkg: Path, oer: Path) -> None:
    _write(pkg, "f.py", b"new\n")
    _write(oer, "f.py", b"old\n")
    _write(pkg, "g.py", b"added\n")  # ADD: no content diff appended
    scaffold = Scaffold(
        create=[
            ScaffoldEntry(EntryKind.FILE, Path("f.py")),
            ScaffoldEntry(EntryKind.FILE, Path("g.py")),
        ]
    )
    diff = diff_oer(scaffold, oer)
    out = format_diff_with_content(diff, oer)
    lines = out.splitlines()
    assert lines[0] == "A g.py"  # ADD sorts before MODIFY; no diff body follows it
    assert lines[1] == "M f.py"
    # The unified diff for f.py follows directly under its M line.
    assert lines[2] == "--- a/f.py"
    assert "-new" in lines
    assert "+old" in lines


GREEN = "\x1b[32m"
RED = "\x1b[31m"
CYAN = "\x1b[36m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"


def test_colorize_diff_wraps_lines_by_kind() -> None:
    text = "\n".join(
        [
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1 +1 @@",
            "-old",
            "+new",
            " context",
            "Binary files a/x and b/x differ",
        ]
    )
    out = colorize_diff(text).splitlines()
    assert out[0] == f"{BOLD}--- a/f.py{RESET}"
    assert out[1] == f"{BOLD}+++ b/f.py{RESET}"
    assert out[2] == f"{CYAN}@@ -1 +1 @@{RESET}"
    assert out[3] == f"{RED}-old{RESET}"
    assert out[4] == f"{GREEN}+new{RESET}"
    assert out[5] == " context"  # context lines untouched
    assert out[6] == f"{BOLD}Binary files a/x and b/x differ{RESET}"


def test_format_diff_with_content_color_wraps_only_body(pkg: Path, oer: Path) -> None:
    _write(pkg, "f.py", b"new\n")
    _write(oer, "f.py", b"old\n")
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.FILE, Path("f.py"))])
    diff = diff_oer(scaffold, oer)
    out = format_diff_with_content(diff, oer, color=True)
    lines = out.splitlines()
    assert lines[0] == "M f.py"  # status line is never colored
    assert RESET in out and (GREEN in out or RED in out)  # body is colored


class _FakeStream:
    def __init__(self, isatty: bool) -> None:
        self._isatty = isatty

    def isatty(self) -> bool:
        return self._isatty


def test_should_colorize_always_and_never(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert should_colorize("always", _FakeStream(isatty=False)) is True
    assert should_colorize("never", _FakeStream(isatty=True)) is False


def test_should_colorize_auto_follows_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert should_colorize("auto", _FakeStream(isatty=True)) is True
    assert should_colorize("auto", _FakeStream(isatty=False)) is False


def test_should_colorize_no_color_overrides_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert should_colorize("auto", _FakeStream(isatty=True)) is False
    # NO_COLOR does not override an explicit --color=always.
    assert should_colorize("always", _FakeStream(isatty=True)) is True


def test_cli_diff_not_colored_when_piped(tmp_path: Path) -> None:
    """Captured (non-TTY) output carries no ANSI codes under default --color=auto."""
    oer = tmp_path / "oer"
    oer.mkdir()
    real = sc.load_scaffold()
    for entry in real.create:
        for rel in iter_packaged_files(entry):
            _write(oer, str(rel), sc.read_packaged_bytes(rel))
    first_file = next(
        rel for entry in real.create for rel in iter_packaged_files(entry) if entry.kind is EntryKind.FILE
    )
    (oer / first_file).write_bytes(b"drifted\n")

    piped = _run_cli(oer, "--diff")
    assert "\x1b[" not in piped.stdout  # auto -> off when captured

    forced = _run_cli(oer, "--diff", "--color=always")
    assert "\x1b[" in forced.stdout  # always -> on even when captured


def test_format_diff_with_content_matches_format_diff_without_modify(pkg: Path, oer: Path) -> None:
    """With no MODIFY items, content mode produces the same lines as format_diff."""
    _write(pkg, "f.py", b"hi")
    scaffold = Scaffold(create=[ScaffoldEntry(EntryKind.FILE, Path("f.py"))])
    diff = diff_oer(scaffold, oer)  # ADD only
    assert format_diff_with_content(diff, oer) == format_diff(diff)


def test_cli_diff_flag_prints_unified_diff(tmp_path: Path) -> None:
    """--diff prints a unified diff body under each M line of a drifted OER."""
    oer = tmp_path / "oer"
    oer.mkdir()
    real = sc.load_scaffold()
    for entry in real.create:
        for rel in iter_packaged_files(entry):
            _write(oer, str(rel), sc.read_packaged_bytes(rel))

    first_file = next(
        rel for entry in real.create for rel in iter_packaged_files(entry) if entry.kind is EntryKind.FILE
    )
    (oer / first_file).write_bytes(b"drifted\n")

    result = _run_cli(oer, "--diff")
    assert result.returncode == EXIT_DRIFT
    assert f"M {first_file.as_posix()}" in result.stdout
    assert "--- a/" in result.stdout
    assert "+drifted" in result.stdout


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


def test_cli_show_ok_independent_of_verbose(tmp_path: Path) -> None:
    """--show-ok prints ok lines without INFO log spam; --verbose does not print ok lines."""
    oer = tmp_path / "oer"
    oer.mkdir()
    real = sc.load_scaffold()
    for entry in real.create:
        for rel in iter_packaged_files(entry):
            _write(oer, str(rel), sc.read_packaged_bytes(rel))

    # In-sync tree: default output is empty.
    assert _run_cli(oer).stdout == ""

    # --show-ok prints ok lines on stdout; logging (stderr) stays quiet.
    shown = _run_cli(oer, "--show-ok")
    assert "  " in shown.stdout  # at least one "  <path>" ok line
    assert shown.stderr == ""

    # --verbose emits INFO logs (stderr) but no ok lines on stdout.
    verbose = _run_cli(oer, "--verbose")
    assert verbose.stdout == ""
    assert "OER Path" in verbose.stderr
