from pathlib import Path

import pytest

from quadriga_scaffolding.scaffold import (
    EntryKind,
    Scaffold,
    ScaffoldEntry,
    load_scaffold,
    parse_path,
    parse_scaffold,
    validate_scaffold,
)


def test_parse_scaffold_with_filenames() -> None:
    test_file = ["comment\n", "+ add\n", "- subtract\n"]
    assert parse_scaffold(test_file) == Scaffold(
        create=[ScaffoldEntry(EntryKind.FILE, Path("add"))],
        delete=[ScaffoldEntry(EntryKind.FILE, Path("subtract"))],
    )


def test_parse_scaffold_disallows_navigation_to_parent() -> None:
    test_file = ["comment\n", "+ ..\n", "- subtract\n"]
    with pytest.raises(ValueError):
        parse_scaffold(test_file)


def test_parse_path_as_file() -> None:
    assert ScaffoldEntry(EntryKind.FILE, Path("test/test.py")) == parse_path("test/test.py")
    assert ScaffoldEntry(EntryKind.FILE, Path("test")) == parse_path("test")


def test_parse_path_as_directory() -> None:
    assert ScaffoldEntry(EntryKind.DIR, Path("test/test/")) == parse_path("test/test/")
    assert ScaffoldEntry(EntryKind.DIR, Path("test/")) == parse_path("test/")


def test_parse_scaffold_skips_blank_lines() -> None:
    """Regression: empty lines must not crash parse_scaffold (was an IndexError)."""
    scaffold = parse_scaffold(["\n", "   \n", "+ a\n"])
    assert scaffold == Scaffold(create=[ScaffoldEntry(EntryKind.FILE, Path("a"))])


def test_parse_scaffold_with_directory_entries() -> None:
    """`+ foo/` and `- foo/` should yield EntryKind.DIR entries."""
    scaffold = parse_scaffold(["+ foo/\n", "- bar/\n"])
    assert scaffold == Scaffold(
        create=[ScaffoldEntry(EntryKind.DIR, Path("foo"))],
        delete=[ScaffoldEntry(EntryKind.DIR, Path("bar"))],
    )


def test_parse_scaffold_delete_entry_kind() -> None:
    """Delete entries should carry the correct EntryKind (file vs. dir)."""
    scaffold = parse_scaffold(["- foo\n", "- foo/\n"])
    assert scaffold.delete == [
        ScaffoldEntry(EntryKind.FILE, Path("foo")),
        ScaffoldEntry(EntryKind.DIR, Path("foo")),
    ]


def test_parse_path_rejects_absolute_paths() -> None:
    """parse_path must raise ValueError on absolute paths."""
    with pytest.raises(ValueError):
        parse_path("/etc/passwd")


def test_parse_scaffold_rejects_parent_traversal_in_delete() -> None:
    """`..` segments must be rejected in delete entries as well."""
    with pytest.raises(ValueError):
        parse_scaffold(["- ../foo\n"])


def test_parse_packaged_scaffold_txt() -> None:
    """Integration smoke test: load_scaffold() on the packaged manifest parses cleanly."""
    scaffold = load_scaffold()
    assert scaffold.create


def test_validate_scaffold_against_packaged_data() -> None:
    """Integration smoke test: validate_scaffold() returns True for the shipped manifest+data."""
    assert validate_scaffold(load_scaffold()) is True


def test_validate_scaffold_detects_create_delete_overlap() -> None:
    """A path listed under both create and delete should make validate_scaffold return False."""
    scaffold = Scaffold(
        create=[ScaffoldEntry(EntryKind.FILE, Path("quadriga/colors.py"))],
        delete=[ScaffoldEntry(EntryKind.FILE, Path("quadriga/colors.py"))],
    )
    assert validate_scaffold(scaffold) is False
