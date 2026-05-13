from pathlib import Path

import pytest

from quadriga_scaffolding.scaffold import EntryKind, Scaffold, ScaffoldEntry, parse_path, parse_scaffold


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
    pytest.skip("not implemented yet")


def test_parse_scaffold_with_directory_entries() -> None:
    """`+ foo/` and `- foo/` should yield EntryKind.DIR entries."""
    pytest.skip("not implemented yet")


def test_parse_scaffold_delete_entry_kind() -> None:
    """Delete entries should carry the correct EntryKind (file vs. dir)."""
    pytest.skip("not implemented yet")


def test_parse_path_rejects_absolute_paths() -> None:
    """parse_path must raise ValueError on absolute paths."""
    pytest.skip("not implemented yet")


def test_parse_scaffold_rejects_parent_traversal_in_delete() -> None:
    """`..` segments must be rejected in delete entries as well."""
    pytest.skip("not implemented yet")


def test_parse_packaged_scaffold_txt() -> None:
    """Integration smoke test: load_scaffold() on the packaged manifest parses cleanly."""
    pytest.skip("not implemented yet")


def test_validate_scaffold_against_packaged_data() -> None:
    """Integration smoke test: validate_scaffold() returns True for the shipped manifest+data."""
    pytest.skip("not implemented yet")


def test_validate_scaffold_detects_create_delete_overlap() -> None:
    """A path listed under both create and delete should make validate_scaffold return False."""
    pytest.skip("not implemented yet")
